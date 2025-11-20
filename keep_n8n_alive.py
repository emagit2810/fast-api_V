import time
import requests
from datetime import datetime, timedelta

# ======= CAMBIA SOLO ESTO =======
URL = "https://n8n-service-ea3k.onrender.com"   # cualquier endpoint público (/ o /workflow/...)
INTERVALO = 600   # 10 minutos en segundos
HORAS = 2         # 0 = infinito
# ===============================

def ping():
    try:
        r = requests.get(URL, timeout=15)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ n8n despierto → {r.status_code}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Error → {e}")

print(f"Keep-alive n8n iniciado por {HORAS if HORAS > 0 else 'siempre'} horas")
start = datetime.now()
end = start + timedelta(hours=HORAS) if HORAS > 0 else None

while True:
    ping()
    if end and datetime.now() > end:
        print("⏰ Tiempo terminado. n8n se dormirá en 15 min si no hay más tráfico.")
        break
    time.sleep(INTERVALO)