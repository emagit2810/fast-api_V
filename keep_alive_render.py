import time
import requests
from datetime import datetime, timedelta

# ============ CAMBIA ESTO SOLO =============
URL = "https://fast-api-v.onrender.com/healthz"   # <--- tu URL real
INTERVALO_SEGUNDOS = 600   # 10 minutos = seguro (Render permite hasta 15 min)
HORAS_A_MANTENER = 3       # 0 = infinito
# ===========================================

def ping():
    try:
        r = requests.get(URL, timeout=10)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Ping OK → {r.status_code}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error → {e}")

print(f"Keep-alive iniciado → {URL}")
print(f"Mantendrá vivo {'para siempre' if HORAS_A_MANTENER == 0 else f'las próximas {HORAS_A_MANTENER} horas'}")
print("Ctrl+C para detener")

start_time = datetime.now()
end_time = start_time + timedelta(hours=HORAS_A_MANTENER) if HORAS_A_MANTENER > 0 else None

while True:
    ping()
    if end_time and datetime.now() > end_time:
        print(f"\nTiempo terminado ({HORAS_A_MANTENER}h). Chau!")
        break
    time.sleep(INTERVALO_SEGUNDOS)