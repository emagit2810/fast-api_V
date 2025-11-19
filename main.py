import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from groq import Groq
import time
import uuid
import requests  # Para POST a n8n webhook

# ======================
# Carga de configuración
# ======================

BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=dotenv_path)

def _getenv_clean(name: str):
    v = os.getenv(name)
    if v is None:
        return None
    return v.strip().strip('"').strip("'")

GROQ_API_KEY = _getenv_clean("GROQ_API_KEY")
API_BEARER_TOKEN = _getenv_clean("API_BEARER_TOKEN")

# CAMBIO: por defecto usamos openai/gpt-oss-20b
MODEL_NAME = _getenv_clean("MODEL_NAME") or "openai/gpt-oss-20b"
BASE_URL = _getenv_clean("BASE_URL") or "https://api.groq.com/openai/v1"

if not GROQ_API_KEY or not API_BEARER_TOKEN:
    raise RuntimeError("Faltan GROQ_API_KEY o API_BEARER_TOKEN en .env")

# Cliente Groq (usa el endpoint OpenAI-compatible por defecto)
client = Groq(api_key=GROQ_API_KEY)

# Seguridad Bearer (auto_error=False para manejarlo a mano)
bearer_scheme = HTTPBearer(auto_error=False)

# ======================
# App FastAPI
# ======================

app = FastAPI(
    title="Gastos Tracker API",
    version="1.0.0",
    openapi_url="/openapi.json",
    docs_url="/docs"
)

# --------- Middleware de logging ---------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"🆔 Request ID: {request_id}")
    print(f"🌐 PETICIÓN ENTRANTE: {request.method} {request.url.path}")
    print(f"🔗 URL completa: {request.url}")
    print(f"📍 Client: {request.client.host if request.client else 'Unknown'}")

    body_json = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                body_str = body.decode()
                body_json = json.loads(body_str)
                print(f"📄 Body JSON: {body_json}")
        except json.JSONDecodeError:
            # CAMBIO: leer primero y luego cortar, no slice sobre coroutine
            raw_body = await request.body()
            print(f"📄 Body no JSON: {raw_body[:100]}...")

    print("📋 Headers clave:")
    print(f"  - Content-Type: {request.headers.get('content-type', 'N/A')}")
    auth = request.headers.get('authorization', 'N/A')
    if auth.startswith('Bearer '):
        print(f"  - Authorization: Bearer {auth[7:17]}...")
    else:
        print(f"  - Authorization: {auth}")
    print(f"{'='*60}")

    response = await call_next(request)

    process_time = time.time() - start_time
    print(f"⏱️  Tiempo de procesamiento: {process_time:.3f}s | Request ID: {request_id}")
    print(f"📤 Status code: {response.status_code}")
    print(f"{'='*60}\n")

    return response

# --------- CORS ---------

ALLOWED_ORIGINS = _getenv_clean("ALLOWED_ORIGINS") or "*"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOWED_ORIGINS == "*" else ALLOWED_ORIGINS.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ======================
# Modelos Pydantic
# ======================

class QueryIn(BaseModel):
    pregunta: str

class QueryOut(BaseModel):
    respuesta: str

# ======================
# Endpoints
# ======================

@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "Gastos Tracker API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/test")
async def test_endpoint(request: Request):
    print("\n🧪 TEST ENDPOINT")
    headers_echo = {
        k: v for k, v in request.headers.items()
        if k.lower() in ['content-type', 'authorization', 'user-agent']
    }
    print(f"📋 Headers eco: {headers_echo}")

    try:
        body_bytes = await request.body()
        print(f"📦 Body bytes: {body_bytes}")
        body_str = body_bytes.decode()
        print(f"📝 Body string: {body_str}")
        body_json = json.loads(body_str)
        print(f"📋 Body JSON: {body_json}")

        return {
            "success": True,
            "received_body": body_json,
            "received_headers": headers_echo,
            "message": "JSON y headers parseados correctamente"
        }
    except Exception as e:
        print(f"❌ Error en test: {e}")
        return {
            "success": False,
            "error": str(e),
            "headers_echo": headers_echo
        }

# --------- /query protegido con Bearer + Groq gpt-oss-20b ---------

@app.post("/query", response_model=QueryOut)
async def query_endpoint(
    payload: QueryIn,
    authorization: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """
    Endpoint para consultar el modelo de Groq (openai/gpt-oss-20b).
    Espera JSON: {"pregunta": "..."} y header Authorization: Bearer <API_BEARER_TOKEN>.
    """

    print("\n" + "="*50)
    print("🔔 NUEVA PETICIÓN /query")
    print("="*50)

    # 1) Autenticación
    if authorization is None:
        print("❌ Falta encabezado Authorization")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if authorization.credentials != API_BEARER_TOKEN:
        print("❌ Token de autorización inválido")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de autorización inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"🔑 Token válido: {authorization.credentials[:10]}...")
    print(f"📩 Pregunta: {payload.pregunta}")

    # 2) Llamada al modelo Groq (gpt-oss-20b)
    try:
        print(f"🚀 Llamando a Groq con modelo: {MODEL_NAME}")

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente experto en análisis de gastos, "
                        "tendencias financieras y contexto económico. "
                        "Responde en español claro y concreto."
                    ),
                },
                {
                    "role": "user",
                    "content": payload.pregunta,
                },
            ],
            max_tokens=300,
            temperature=0.4,
        )

        respuesta = completion.choices[0].message.content or "Sin respuesta"
        print(f"✅ Texto extraído: {respuesta[:120]}...")
        
        # Llamada a n8n webhook DESPUÉS de Groq (solo si éxito)
        try:
            n8n_url = "http://n8n-service-ea3k.onrender.com/webhook-test/test-groq"
            payload_n8n = {
                "pregunta": payload.pregunta,
                "respuesta_groq": respuesta,
                "timestamp": datetime.utcnow().isoformat()
            }
            headers_n8n = {"Content-Type": "application/json"}
            response_n8n = requests.post(n8n_url, json=payload_n8n, headers=headers_n8n)
            response_n8n.raise_for_status()
        except Exception as e:
            print(f"❌ Error llamando n8n: {e}")
            # Log solo, continúa – n8n es "fire-and-forget" para no impactar UX
        
        print("="*50)
        print("✅ PETICIÓN /query COMPLETADA")
        print("="*50 + "\n")

        return QueryOut(respuesta=respuesta)

    except Exception as e:
        print(f"❌ ERROR EN GROQ: {type(e).__name__}")
        print(f"❌ Meaaansaje: {str(e)}")
        print(f"❌ Detalles: {repr(e)}")
        print("="*50 + "\n")
        # 502 aquí para que el cliente (Custom GPT) sepa que es fallo aguas arriba (Groq)
        raise HTTPException(
            status_code=502,
            detail=f"Error en Groq: {str(e)}"
        )

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "API Test Groq",
        "version": "1.0.0",
        "model": MODEL_NAME,
    }
