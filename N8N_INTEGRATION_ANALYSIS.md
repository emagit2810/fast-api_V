# Análisis y Correcciones para la Integración con n8n Webhook

## 📋 Resumen de Cambios Implementados

### 1. **Correcciones Críticas Realizadas**

#### ✅ Evitar Mutación del Diccionario Original
**Problema anterior:** La función modificaba el diccionario `data` original, causando efectos secundarios.
```python
# ANTES (INCORRECTO):
data["origin_endpoint"] = origin  # Modifica el dict original

# AHORA (CORRECTO):
payload = data.copy()  # Crea una copia
payload["origin_endpoint"] = origin  # Modifica solo la copia
```

#### ✅ Headers Completos y Correctos
**Añadido:** Header `Accept: application/json` para indicar a n8n qué tipo de respuesta esperamos.
```python
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "FastAPI-GastosTracker/1.0"
}
```

#### ✅ Timeouts Más Robustos
**Mejorado:** Timeout total de 20s + timeout de conexión de 5s específico.
```python
# ANTES:
timeout=15.0  # Solo timeout general

# AHORA:
timeout=httpx.Timeout(20.0, connect=5.0)  # General + Conexión específica
```

#### ✅ Manejo de Errores Específicos
**Añadido:** Captura de errores por categoría (Timeout, Conexión, Otros).
```python
except httpx.TimeoutException as e:
    # Manejo específico para timeouts
except httpx.ConnectError as e:
    # Manejo específico para errores de conexión
except Exception as e:
    # Otros errores con traceback completo
```

---

## 🔍 Verificación de Compatibilidad con n8n

### Configuración de n8n (según tus capturas):
- ✅ **Método HTTP:** POST (correcto en el código)
- ✅ **Path:** `9e097731-681a-4ca4-aab9-ebf3700e63d4` (correcto en URL)
- ✅ **Authentication:** None (sin headers de auth, correcto)
- ✅ **Respond:** Immediately (n8n responderá inmediatamente, timeout de 20s es adecuado)

### URL Utilizada:
```
https://n8n-service-ea3k.onrender.com/webhook-test/9e097731-681a-4ca4-aab9-ebf3700e63d4
```

⚠️ **IMPORTANTE:** Esta es la URL de TEST. Solo funciona cuando:
1. Tienes la ventana de n8n abierta
2. Has presionado "Listen for test event"
3. El workflow NO necesita estar activado (el botón "Active" puede estar OFF)

---

## 📊 Logs Mejorados - Qué Verás en Render

Cuando tu API envíe datos a n8n, verás logs como estos:

```
======================================================================
🚀 [/query] INICIANDO ENVÍO A N8N WEBHOOK
======================================================================
🔗 Target URL: https://n8n-service-ea3k.onrender.com/webhook-test/9e097731-681a-4ca4-aab9-ebf3700e63d4

📋 HEADERS que se enviarán:
   Content-Type: application/json
   Accept: application/json
   User-Agent: FastAPI-GastosTracker/1.0

📦 BODY (JSON) que se enviará:
{
  "evento": "query_received",
  "pregunta": "¿Cómo organizo mis tareas?",
  "respuesta_groq": "Aquí está mi recomendación...",
  "whatsapp_link": "https://wa.me/573115226848?text=...",
  "model_name": "openai/gpt-oss-20b",
  "timestamp": "2026-01-04T07:55:46.123456",
  "origin_endpoint": "/query",
  "environment": "prod"
}

🔧 CURL EQUIVALENTE (para testing manual):
curl -X POST "https://n8n-service-ea3k.onrender.com/webhook-test/9e097731-681a-4ca4-aab9-ebf3700e63d4" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-raw "{\"evento\":\"query_received\",\"pregunta\":\"¿Cómo organizo mis tareas?\",...}"

⏳ [/query] Enviando request POST a n8n...

📩 [/query] RESPUESTA DE N8N RECIBIDA (⏱️ 0.234s):
──────────────────────────────────────────────────────────────────────
   📊 Status Code: 200
   📝 Reason: OK
   📋 Response Headers:
      content-type: application/json
      content-length: 42
      date: Sat, 04 Jan 2026 07:55:46 GMT
   📄 Response Body: {"status": "received"}

✅ [/query] ¡ÉXITO! Webhook procesado correctamente por n8n
======================================================================
```

---

## 🎯 Campos que Recibirá n8n

### Para `/query`:
```json
{
  "evento": "query_received",
  "pregunta": "texto de la pregunta del usuario",
  "respuesta_groq": "respuesta generada por Groq",
  "whatsapp_link": "link generado de WhatsApp",
  "model_name": "openai/gpt-oss-20b",
  "timestamp": "2026-01-04T07:55:46.123456Z",
  "origin_endpoint": "/query",
  "environment": "prod"
}
```

### Para `/reminder`:
```json
{
  "evento": "reminder_received",
  "text": "texto del recordatorio",
  "task_id": "id de la tarea",
  "due_date": "fecha límite",
  "priority": 1,
  "type": "tipo de tarea",
  "response_mode": "whatsapp_link o text_only",
  "respuesta_groq": "respuesta del AI",
  "whatsapp_link": "link generado",
  "timestamp": "2026-01-04T07:55:46.123456Z",
  "origin_endpoint": "/reminder",
  "environment": "prod"
}
```

---

## 🚨 7 Errores Comunes y Cómo los Prevenimos

### 1. **Mutación del Diccionario de Entrada**
- ❌ **Error:** Modificar `data` directamente causa bugs sutiles
- ✅ **Solución:** Usar `payload = data.copy()`

### 2. **URL de Test vs Producción**
- ❌ **Error:** Dejar `/webhook-test/` en producción → 404 cuando cierras n8n
- ✅ **Solución:** Documentado claramente, cambiar a `/webhook/` para producción

### 3. **Timeouts Demasiado Cortos**
- ❌ **Error:** Render puede estar lento al despertar, timeout de 5s falla
- ✅ **Solución:** 20s total + 5s específicos para conexión

### 4. **Errores No Capturados**
- ❌ **Error:** Una falla en n8n tumba toda la API
- ✅ **Solución:** Try-except que NO re-lanza, solo loguea

### 5. **Headers Incompletos**
- ❌ **Error:** Faltar `Content-Type` causa que n8n no parsee el JSON
- ✅ **Solución:** Headers explícitos y completos

### 6. **Falta de Debugging**
- ❌ **Error:** No saber qué se envió cuando algo falla
- ✅ **Solución:** Logs exhaustivos + comando CURL para reproducir manualmente

### 7. **Response sin Validar**
- ❌ **Error:** Asumir que status 200 = éxito siempre
- ✅ **Solución:** Revisar `status_code` y loguear response headers + body

---

## 🧪 Cómo Probar

### Paso 1: Abrir n8n
1. Ve a tu interfaz de n8n
2. Abre el workflow con el webhook
3. Presiona "Listen for test event"

### Paso 2: Hacer una Petición a tu API
```bash
curl -X POST "https://tu-api-render.com/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TU_TOKEN_AQUI" \
  --data-raw '{"pregunta": "Hola, esto es un test"}'
```

### Paso 3: Verificar los Logs
1. **En Render:** Verás todos los logs detallados del envío a n8n
2. **En n8n:** Deberías ver el evento de prueba recibido con todos los campos

---

## 🔄 Para Pasar a Producción

Cuando tu workflow esté listo para producción:

1. **Activar el workflow en n8n** (botón "Active" en ON)
2. **Cambiar la URL en `main.py`:**
   ```python
   # Línea 48:
   N8N_WEBHOOK_URL = "https://n8n-service-ea3k.onrender.com/webhook/9e097731-681a-4ca4-aab9-ebf3700e63d4"
   # (sin el "-test")
   ```
3. **Hacer commit y push a Render**
4. **Ya no necesitas tener n8n abierto** - funcionará 24/7

---

## ✅ Estado Actual

- ✅ URL de n8n configurada correctamente (modo TEST)
- ✅ Logs exhaustivos implementados
- ✅ Manejo de errores robusto
- ✅ Headers correctos para n8n
- ✅ Timeout adecuado
- ✅ Evita efectos secundarios (copia del dict)
- ✅ CURL generado para debugging manual
- ✅ Integración en ambos endpoints (`/query` y `/reminder`)

**Todo está listo para funcionar correctamente con tu webhook de n8n!** 🎉
