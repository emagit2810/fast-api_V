# 🔍 Instrucciones de Debug - API Groq

## ✅ Mejoras Implementadas

### 1. **Middleware de Logging Global**
- Captura TODAS las peticiones HTTP entrantes
- Muestra método, URL, client IP, headers y body
- Tiempo de procesamiento de cada request
- Status code de respuesta

### 2. **Debug Detallado en `/query`**
- Logs en cada etapa del proceso
- Validación de payload JSON
- Verificación de autenticación paso a paso
- Logs antes, durante y después de la llamada a Groq
- Manejo de errores mejorado con tipo y detalles completos

### 3. **Nuevos Endpoints de Prueba**

#### `GET /` - Health Check
```bash
curl http://localhost:8000/
```

#### `POST /test` - Verificar JSON Parsing
```bash
curl -X POST http://localhost:8000/test \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "test"}'
```

#### `POST /query` - Endpoint principal (mejorado)
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer s3cr3t-Xjd94jf2kLl" \
  -d '{"pregunta": "Hola, ¿cómo estás?"}'
```

## 🐛 Diagnóstico del Problema "0 API Calls"

### Posibles Causas:

1. **❌ Modelo incorrecto**: Tu `.env` tiene `openai/gpt-oss-20b` que podría no existir
   - **Solución**: Cambiar a un modelo válido de Groq
   - Modelos recomendados:
     - `llama-3.3-70b-versatile`
     - `llama-3.1-70b-versatile`
     - `mixtral-8x7b-32768`
     - `gemma2-9b-it`

2. **❌ Autenticación fallando**: El token no coincide o no se envía correctamente
   - Los logs ahora te mostrarán exactamente dónde falla

3. **❌ Peticiones duplicadas**: Posible problema de CORS o preflight
   - El middleware ahora registra cada petición
   - Verifica si ves peticiones OPTIONS (preflight CORS)

4. **❌ Error en el parsing de JSON**: El body no llega correctamente
   - El endpoint `/test` te ayudará a verificar esto

## 📊 Cómo Interpretar los Logs

### Logs Normales (Exitosos):
```
===========================================================
🌐 PETICIÓN ENTRANTE: POST /query
📄 Body JSON: {'pregunta': 'Hola'}
📋 Headers:
  - Authorization: Bearer s3cr3t-Xjd94jf2kLl...
===========================================================

==================================================
🔔 NUEVA PETICIÓN RECIBIDA
==================================================
📦 Payload recibido: pregunta='Hola'
📩 Pregunta: Hola
🔑 Authorization header: Bearer s3cr3t-...
🔐 Token extraído: s3cr3t-Xjd...
✅ Autenticación exitosa
🚀 Iniciando llamada a Groq...
📋 Modelo: openai/gpt-oss-20b
💬 Mensaje: Hola
🤖 Respuesta completa de Groq: {...}
✅ Texto extraído: ....
✅ PETICIÓN COMPLETADA CON ÉXITO
```

### Logs con Error:
```
❌ ERROR: Falta el Bearer token
❌ ERROR: Token inválido
❌ ERROR EN GROQ: InvalidModelError
❌ Mensaje de error: Model 'openai/gpt-oss-20b' not found
```

## 🔧 Pasos de Verificación

### 1. Verifica tu modelo en el .env
Edita `rag/.env` y cambia:
```env
MODEL_NAME=llama-3.3-70b-versatile
```

### 2. Reinicia el servidor FastAPI
```bash
# Detén el servidor actual (Ctrl+C)
# Luego reinicia:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Prueba con el endpoint de test
```bash
curl -X POST http://localhost:8000/test \
  -H "Content-Type: application/json" \
  -d '{"pregunta": "test"}'
```

### 4. Prueba el endpoint real
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer s3cr3t-Xjd94jf2kLl" \
  -d '{"pregunta": "Explica qué es FastAPI en una frase"}'
```

## 📝 Qué Observar en la Consola

1. **Número de peticiones**: ¿Ves 1 o 2 peticiones por cada request?
   - Si ves 2: Una es OPTIONS (CORS preflight), la otra es POST
   
2. **¿Llega el payload?**: Verifica que `📄 Body JSON` muestra tu pregunta

3. **¿Se valida el token?**: Verifica que llegues hasta "✅ Autenticación exitosa"

4. **¿Se llama a Groq?**: Verifica que veas "🚀 Iniciando llamada a Groq..."

5. **¿Hay error en Groq?**: Si ves "❌ ERROR EN GROQ", lee el mensaje de error

## 🎯 Siguiente Paso

Ejecuta el servidor y envía una petición. Los logs te dirán EXACTAMENTE dónde está el problema.
