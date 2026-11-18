import os
import time
import datetime
import threading
import requests
from sheets_db import conectar_sheets
from gmail_otp import obtener_ultimo_codigo_disney, obtener_ultimo_codigo_netflix

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

# =============================================================
# CONTROL DE CONCURRENCIA (THREADS LOCK)
# =============================================================
candado_operaciones = threading.Lock()

WHATSAPP_NUMERO = "584247091547"
ADMIN_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "")).strip()

# =============================================================
# CONFIGURACIÓN DE HORA LOCAL (VENEZUELA / UTC-4)
# =============================================================
def obtener_hora_venezuela():
    """Retorna la fecha y hora actual ajustada estrictamente a la zona horaria de Venezuela (UTC-4)."""
    if ZoneInfo:
        try:
            return datetime.datetime.now(ZoneInfo("America/Caracas"))
        except Exception:
            pass
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)

# =============================================================
# CONFIGURACIÓN DE PRECIOS (USD/USDT) Y DATOS DE PAGO MÓVIL
# =============================================================
PRECIO_DISNEY_USD = 5.0   # Precio en USD de Disney+
PRECIO_NETFLIX_USD = 4.5  # Precio en USD de Netflix
TASA_RESPALDO_BS = 1100.0   # Tasa de respaldo por si fallan las consultas externas

PAGO_MOVIL_BANCO = "Provincial (0108)"
PAGO_MOVIL_CEDULA = "27538779"
PAGO_MOVIL_TELEFONO = "04247091547"

control_intentos_otp = {}
MAX_INTENTOS_RAPIDOS = 2
COOLDOWN_SEGUNDOS = 180

# Control de estados temporales, asistentes y memoria temporal de pagos/cupones/difusión
esperando_captura_pago = {}
esperando_nuevo_nombre_perfil = {}
esperando_busqueda_admin = {}
asistente_cuenta_datos = {}
asistente_edicion_admin = {}
asistente_cupon_admin = {}
esperando_codigo_cupon_cliente = {} 
detalles_pago_activos = {} 
asistente_difusion_admin = {} 
registros_pendientes_info = {} 


def safe_get(row_dict, key, default=""):
    """Lee de manera segura un diccionario de Google Sheets ignorando espacios y mayúsculas en los encabezados."""
    if not isinstance(row_dict, dict):
        return default
    for k, v in row_dict.items():
        if str(k).strip().lower() == str(key).strip().lower():
            val = str(v).strip()
            return val if val != "" else default
    return default


def obtener_tasa_usdt_hoy():
    """Consulta la tasa USDT/VES del día (Binance P2P con respaldo automático) sin bloquear el bot."""
    try:
        url_binance = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        payload = {
            "asset": "USDT",
            "fiat": "VES",
            "merchantCheck": False,
            "page": 1,
            "payTypes": [],
            "publisherType": None,
            "rows": 5,
            "tradeType": "BUY"
        }
        res = requests.post(url_binance, json=payload, timeout=4)
        if res.status_code == 200:
            anuncios = res.json().get("data", [])
            precios = [float(a["adv"]["price"]) for a in anuncios if "adv" in a and "price" in a["adv"]]
            if precios:
                return round(sum(precios) / len(precios), 2)
    except Exception as e:
        print(f"Aviso: No se pudo leer Binance P2P ({e}), probando respaldo...")

    try:
        res_alt = requests.get("https://pydolarve.org/api/v1/dollar?monitor=enparalelovzla", timeout=3)
        if res_alt.status_code == 200:
            precio = res_alt.json().get("price")
            if precio:
                return round(float(precio), 2)
    except Exception:
        pass

    return TASA_RESPALDO_BS
