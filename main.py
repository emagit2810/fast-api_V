import os
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from pathlib import Path
from groq import AsyncGroq
import time
import uuid

import httpx
from urllib.parse import quote

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

# ======================
# Configuración de n8n webhooks (PRODUCCIÓN Y TEST)
# ======================

ENVIRONMENT = _getenv_clean("ENVIRONMENT") or "prod"

# URLs de webhooks de n8n - PRODUCCIÓN y TEST
N8N_WEBHOOK_URL_PROD = "https://n8n-service-ea3k.onrender.com/webhook/9e097731-681a-4ca4-aab9-ebf3700e63d4"
N8N_WEBHOOK_URL_TEST = "https://n8n-service-ea3k.onrender.com/webhook-test/9e097731-681a-4ca4-aab9-ebf3700e63d4"

print(f"✅ N8N_WEBHOOK_URL_PROD configurada: {N8N_WEBHOOK_URL_PROD}")
print(f"✅ N8N_WEBHOOK_URL_TEST configurada: {N8N_WEBHOOK_URL_TEST}")

# Cliente Groq (usa el endpoint OpenAI-compatible por defecto)
client = AsyncGroq(api_key=GROQ_API_KEY)

# Seguridad Bearer (auto_error=False para manejarlo a mano)
bearer_scheme = HTTPBearer(auto_error=False)

# ======================
# Helper: Enviar a n8n (una URL)
# ======================

async def send_to_single_n8n_webhook(url: str, data: dict, origin: str, webhook_type: str):
    """
    Envía un payload JSON a una URL específica de n8n y loguea todo el proceso
    para depuración en Render.
    
    Args:
        url: URL del webhook de n8n
        data: Diccionario con los datos a enviar
        origin: Nombre del endpoint que origina la llamada (ej: "/query")
        webhook_type: Tipo de webhook ("PROD" o "TEST")
    """
    if not url:
        print(f"⚠️ [{origin}] URL de n8n {webhook_type} no configurada. Saltando envío.")
        return

    print(f"\n{'='*70}")
    print(f"🚀 [{origin}] INICIANDO ENVÍO A N8N WEBHOOK {webhook_type}")
    print(f"{'='*70}")
    print(f"🔗 Target URL: {url}")
    
    # IMPORTANTE: Crear una copia para no modificar el dict original
    payload = data.copy()
    
    # Añadimos timestamp si no viene
    if "timestamp" not in payload:
        payload["timestamp"] = datetime.utcnow().isoformat()
    
    payload["origin_endpoint"] = origin
    payload["environment"] = ENVIRONMENT
    payload["webhook_type"] = webhook_type  # Agregar tipo de webhook

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "FastAPI-GastosTracker/1.0"
    }

    print(f"\n📋 HEADERS que se enviarán:")
    for k, v in headers.items():
        print(f"   {k}: {v}")
    
    print(f"\n📦 BODY (JSON) que se enviará:")
    body_json_str = json.dumps(payload, indent=2, ensure_ascii=False)
    print(body_json_str)
    
    # Generar CURL equivalente para debugging
    body_escaped = json.dumps(payload, ensure_ascii=False).replace('"', '\\"')
    curl_command = (
        f'curl -X POST "{url}" \\\n'
        f'  -H "Content-Type: application/json" \\\n'
        f'  -H "Accept: application/json" \\\n'
        f'  --data-raw "{body_escaped}"'
    )
    print(f"\n🔧 CURL EQUIVALENTE (para testing manual):")
    print(curl_command)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            print(f"\n⏳ [{origin}] Enviando request POST a n8n {webhook_type}...")
            start_n8n = time.time()
            
            response = await client.post(
                url, 
                json=payload, 
                headers=headers
            )
            
            duration = time.time() - start_n8n
            
            print(f"\n📩 [{origin}] RESPUESTA DE N8N {webhook_type} RECIBIDA (⏱️ {duration:.3f}s):")
            print(f"{'─'*70}")
            print(f"   ✓ Status Code: {response.status_code}")
            print(f"   ✓ Reason: {response.reason_phrase}")
            print(f"   📋 Response Headers:")
            for k, v in response.headers.items():
                print(f"      {k}: {v}")
            print(f"   📄 Response Body: {response.text[:500]}")
            
            if response.status_code >= 400:
                print(f"\n⚠️ [{origin}] ¡ALERTA! n8n {webhook_type} devolvió código de error {response.status_code}")
                print(f"   Detalles: {response.text}")
            elif response.status_code >= 200 and response.status_code < 300:
                print(f"\n✅ [{origin}] ¡ÉXITO! Webhook {webhook_type} procesado correctamente por n8n")
            else:
                print(f"\n❓ [{origin}] Respuesta inesperada de {webhook_type}: {response.status_code}")
                
            print(f"{'='*70}\n")

    except httpx.TimeoutException as e:
        print(f"\n❌ [{origin}] TIMEOUT al contactar n8n {webhook_type} (>20s): {e}")
        print(f"   Verifica que n8n esté ejecutándose y la URL sea correcta.")
        
    except httpx.ConnectError as e:
        print(f"\n❌ [{origin}] ERROR DE CONEXIÓN a n8n {webhook_type}: {e}")
        print(f"   ¿Está n8n online? ¿La URL es correcta?")
        
    except Exception as e:
        print(f"\n❌ [{origin}] ERROR CRÍTICO INESPERADO al contactar n8n {webhook_type}:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensaje: {str(e)}")
        import traceback
        print(f"   Traceback:\n{traceback.format_exc()}")
        
    # No re-lanzamos la excepción para no romper el flujo principal de la API


async def send_payload_to_n8n(data: dict, origin: str):
    """
    Envía un payload JSON a AMBAS URLs de n8n (PROD y TEST) en paralelo.
    
    Args:
        data: Diccionario con los datos a enviar
        origin: Nombre del endpoint que origina la llamada (ej: "/query")
    """
    import asyncio
    
    print(f"\n{'🎯'*35}")
    print(f"📡 [{origin}] ENVIANDO A N8N - PRODUCCIÓN Y TEST")
    print(f"{'🎯'*35}")
    
    # Enviar a ambos webhooks en paralelo
    await asyncio.gather(
        send_to_single_n8n_webhook(N8N_WEBHOOK_URL_PROD, data, origin, "PROD"),
        send_to_single_n8n_webhook(N8N_WEBHOOK_URL_TEST, data, origin, "TEST"),
        return_exceptions=True  # No falla si uno de los webhooks falla
    )
    
    print(f"\n{'✨'*35}")
    print(f"✅ [{origin}] ENVÍO A N8N COMPLETADO (PROD + TEST)")
    print(f"{'✨'*35}\n")


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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)

# ======================
# Modelos Pydantic
# ======================

class QueryIn(BaseModel):
    pregunta: str

class QueryOut(BaseModel):
    respuesta: str
    whatsapp_link: str | None = None

class ReminderIn(BaseModel):
    text: str
    priority: int | None = None
    task_id: str | None = None
    due_date: str | None = None
    type: str | None = None
    response_mode: str = "whatsapp_link"  # "whatsapp_link" | "text_only"

    @field_validator("response_mode")
    @classmethod
    def validate_response_mode(cls, v: str) -> str:
        if v not in ["whatsapp_link", "text_only"]:
            raise ValueError("response_mode debe ser 'whatsapp_link' o 'text_only'")
        return v

class ReminderOut(BaseModel):
    reminder_text: str
    whatsapp_link: str | None = None
    response_type: str  # "whatsapp_link" | "text_only"

# ======================
# Endpoints
# ======================

@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "gestor de tareas API",
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
    request: Request,
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
# -----------------------------------------------------------------
# CURL equivalente a la petición que recibió FastAPI (para debugging)
# -----------------------------------------------------------------
    body = json.dumps({"pregunta": payload.pregunta}, ensure_ascii=False)
    incoming_curl = (
        f'curl -X POST "{request.url}" '
        f' -H "Content-Type: application/json" '
        f' -H "Authorization: Bearer {authorization.credentials}" '
        f" --data-raw '{body}'"
    )
    print("🔧 CURL equivalente:\n" + incoming_curl)
    # -----------------------------------------------------------------
# -----------------------------------------------------------------
# Preparar llamada a Groq (mostramos también el curl equivalente)
# -----------------------------------------------------------------
    groq_payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": (
                 "Eres un asistente experto en tareas relacionadas con gmail, jerarquizacion de tareas respecto a parametros: tiempo, impacto, dificultad, "
                    "asistente de tareas que recomienda mejoras a la tareas o pasos primeros"
                    "Responde en español claro y concreto."
                    'haz chiste espontaneos y cortos cada 2 - 3 respuestas sin  avisar'
            )},
            {"role": "user", "content": payload.pregunta},
        ],
        "max_tokens": 300,
        "temperature": 0.8,
    }

    groq_curl = (
        f'curl -X POST "{BASE_URL}/chat/completions" '
        f'-H "Authorization: Bearer {GROQ_API_KEY}" '
        f'-H "Content-Type: application/json" '
        f"-d '{json.dumps(groq_payload)}'"
    )
    print("🚀 CURL equivalente a la llamada a Groq:\n" + groq_curl)


    # 2) Llamada al modelo Groq (gpt-oss-20b)
    try:
        print(f"🚀 Llamando a Groq con modelo: {MODEL_NAME}")

        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente experto en tareas relacionadas con gmail, jerarquizacion de tareas respecto a parametros: tiempo, impacto, dificultad, "
                        "asistente de tareas que recomienda mejoras a la tareas o pasos primeros "
                        "Responde en español claro y concreto."
                        'haz chiste espontaneos y cortos cada 2 - 3 respuestas sin  avisar'
                    ),
                },
                {
                    "role": "user",
                    "content": payload.pregunta,
                },
            ],
            max_tokens=300,
            temperature=0.8,
        )

        respuesta = completion.choices[0].message.content or "Sin respuesta"
        print(f"✅ Texto extraído: {respuesta[:120]}...")

        # --- NUEVO: construir link de WhatsApp con wa.me ---
        whatsapp_number = "573115226848"

        msg = (
            "🤖 Nuevo mensaje de Groq\n\n"
            f"❓ Pregunta:\n{payload.pregunta}\n\n"
            f"💬 Respuesta:\n{respuesta}"
        )

        # Codificamos el texto para URL (espacios, saltos de línea, emojis, etc.)
        encoded_msg = quote(msg, safe="")
        whatsapp_link = f"https://wa.me/{whatsapp_number}?text={encoded_msg}"
        print(f"🔗 WhatsApp link generado: {whatsapp_link}")
        # --- FIN NUEVO ---
        
        # Llamada a n8n webhook DESPUÉS de Groq (refactorizado)
        # Preparamos los datos completos que queremos que n8n reciba
        payload_n8n = {
            "evento": "query_received",
            "pregunta": payload.pregunta,
            "respuesta_groq": respuesta,
            "whatsapp_link": whatsapp_link,
            # Metadata extra
            "model_name": MODEL_NAME
        }
        
        # Enviamos usando el helper
        await send_payload_to_n8n(payload_n8n, origin="/query")
        
        print("="*50)
        print("✅ PETICIÓN /query COMPLETADA")
        print("="*50 + "\n")

        return QueryOut(respuesta=respuesta, whatsapp_link=whatsapp_link)

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

@app.post("/reminder", response_model=ReminderOut)
async def reminder_endpoint(
    payload: ReminderIn,
    request: Request,
    authorization: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """
    Endpoint para procesar recordatorios desde la TODO app.
    """
    print("\n" + "="*50)
    print("🔔 NUEVA PETICIÓN /reminder")
    print("="*50)

    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if authorization.credentials != API_BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de autorización inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    print(f"🔑 Token válido: {authorization.credentials[:10]}...")

    # Curl de debug
    body = json.dumps(payload.model_dump(), ensure_ascii=False)
    incoming_curl = (
        f'curl -X POST "{request.url}" '
        f' -H "Content-Type: application/json" '
        f' -H "Authorization: Bearer {authorization.credentials}" '
        f" --data-raw '{body}'"
    )
    print("🔧 CURL equivalente /reminder:\n" + incoming_curl)

    try:
        print(f"🚀 Llamando a Groq (reminder) con modelo: {MODEL_NAME}")

        user_message = (
            f"Texto: {payload.text}\n"
            f"ID de tarea: {payload.task_id}\n"
            f"Fecha límite: {payload.due_date}\n"
            f"Prioridad: {payload.priority}\n"
            f"Tipo: {payload.type}\n\n"
            "Instrucciones:\n"
            "1. Si el texto es una pregunta, respóndela.\n"
            "2. Si es un recordatorio, responde con una frase como: 'Recordatorio: [lo que se pidió] fue hecho'.\n"
        )

        completion = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente inteligente. "
                        "Si recibes una pregunta, responde la pregunta. "
                        "Si recibes una orden de recordatorio, confirma que se realizó con una frase tipo: 'Recordatorio: [resumen] fue hecho'. "
                        "Responde SIEMPRE en español."
                    ),
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],
            max_tokens=300,
            temperature=0.4,
        )

        reminder_text = completion.choices[0].message.content or "Recordatorio procesado."
        print(f"✅ Reminder generado: {reminder_text[:120]}...")

        # --- NUEVO: construir link de WhatsApp con wa.me ---
        whatsapp_number = "573115226848"

        msg = (
            "🤖 Nuevo mensaje de Groq (Reminder)\n\n"
            f"📝 Texto original:\n{payload.text}\n\n"
            f"💬 Respuesta:\n{reminder_text}"
        )

        # Codificamos el texto para URL
        encoded_msg = quote(msg, safe="")
        whatsapp_link = f"https://wa.me/{whatsapp_number}?text={encoded_msg}"
        print(f"🔗 WhatsApp link generado: {whatsapp_link}")
        # --- FIN NUEVO ---

        print("="*50)
        # --- NUEVO: Enviar datos a n8n ---
        payload_n8n = {
            "evento": "reminder_received",
            "text": payload.text,
            "task_id": payload.task_id,
            "due_date": payload.due_date,
            "priority": payload.priority,
            "type": payload.type,
            "response_mode": payload.response_mode,
            "respuesta_groq": reminder_text,
            "whatsapp_link": whatsapp_link
        }
        await send_payload_to_n8n(payload_n8n, origin="/reminder")
        # ---------------------------------

        print("="*50)
        print("✅ PETICIÓN /reminder COMPLETADA")
        print("="*50 + "\n")

        response_type = payload.response_mode
        print(f"📊 Response type establecido: {response_type}")

        return ReminderOut(
            reminder_text=reminder_text,
            whatsapp_link=whatsapp_link,
            response_type=response_type
        )

    except Exception as e:
        print(f"❌ ERROR EN /reminder: {type(e).__name__} -> {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Error en Groq (reminder): {str(e)}"
        )

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "API Test Groq",
        "version": "1.0.0",
        "model": MODEL_NAME,
        "environment": ENVIRONMENT,
        "n8n_webhooks": {
            "production": {
                "configured": N8N_WEBHOOK_URL_PROD is not None,
                "url": N8N_WEBHOOK_URL_PROD if N8N_WEBHOOK_URL_PROD else "Not configured"
            },
            "test": {
                "configured": N8N_WEBHOOK_URL_TEST is not None,
                "url": N8N_WEBHOOK_URL_TEST if N8N_WEBHOOK_URL_TEST else "Not configured"
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
