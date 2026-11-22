import os
import time
import requests

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("PHONE_NUMBER_ID", "")

# Registro en memoria de la última vez que cada número escribió (ventana de 24h de Meta)
ultima_interaccion_whatsapp = {}

# Freno temporal si Meta reporta cuenta bloqueada (error 131031)
whatsapp_pausado_hasta = 0.0


def registrar_interaccion_whatsapp(telefono):
    """Guarda el momento exacto en que el usuario escribió para respetar la ventana de 24 horas."""
    num = str(telefono).strip()
    if num:
        ultima_interaccion_whatsapp[num] = time.time()


def puede_enviar_whatsapp_libre(telefono):
    """Verifica que no haya bloqueo activo y que el usuario haya escrito en las últimas 23.5 horas."""
    ahora = time.time()
    if ahora < whatsapp_pausado_hasta:
        restante = int((whatsapp_pausado_hasta - ahora) / 60) + 1
        print(f"⏸️ Envío a WhatsApp omitido: cuenta pausada por error 131031 (~{restante} min restantes).", flush=True)
        return False

    num = str(telefono).strip()
    ultimo_msg = ultima_interaccion_whatsapp.get(num)
    if not ultimo_msg:
        print(f"🛡️ Envío proactivo bloqueado para {num}: sin mensaje entrante reciente (ventana 24h).", flush=True)
        return False

    # 84600 segundos = 23.5 horas (margen de seguridad antes de las 24h exactas de Meta)
    if (ahora - ultimo_msg) > 84600:
        print(f"🛡️ Envío bloqueado para {num}: expiró la ventana de 24 horas de WhatsApp.", flush=True)
        return False

    return True


def enviar_mensaje_whatsapp(telefono_destino, texto_mensaje, forzar_respuesta=False):
    """Envía un mensaje de texto a WhatsApp respetando la ventana de 24h y frenando ante errores 131031."""
    global whatsapp_pausado_hasta

    token_actual = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
    phone_id_actual = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("PHONE_NUMBER_ID") or PHONE_NUMBER_ID

    if not token_actual or not phone_id_actual:
        print("⚠️ Error: Faltan WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID en Render.", flush=True)
        return False

    if not forzar_respuesta and not puede_enviar_whatsapp_libre(telefono_destino):
        return False

    url = f"https://graph.facebook.com/v18.0/{phone_id_actual}/messages"
    headers = {
        "Authorization": f"Bearer {token_actual}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": str(telefono_destino),
        "type": "text",
        "text": {"body": texto_mensaje}
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=8)
        if response.status_code == 200:
            return True

        resp_text = response.text
        print(f"❌ Error enviando mensaje de WhatsApp ({response.status_code}): {resp_text}", flush=True)

        # Si Meta indica cuenta bloqueada (131031), pausamos salientes por 15 minutos
        if "131031" in resp_text or "Business Account locked" in resp_text:
            whatsapp_pausado_hasta = time.time() + 900
            print("🚨 Freno activado por 15 min debido a error 131031 en Meta.", flush=True)

        return False
    except Exception as e:
        print(f"❌ Excepción al conectar con la API de WhatsApp: {e}", flush=True)
        return False


def descargar_media_whatsapp(media_id):
    """Consulta la URL de descarga en Meta y devuelve los bytes de la imagen enviada por WhatsApp."""
    token_actual = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
    if not token_actual or not media_id:
        print("⚠️ Error: Falta WHATSAPP_TOKEN o media_id para descargar imagen.", flush=True)
        return None

    headers = {"Authorization": f"Bearer {token_actual}"}
    try:
        meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
        res_meta = requests.get(meta_url, headers=headers, timeout=10).json()
        download_url = res_meta.get("url")
        if not download_url:
            print(f"❌ No se obtuvo URL de descarga para media {media_id}: {res_meta}", flush=True)
            return None

        res_img = requests.get(download_url, headers=headers, timeout=20)
        if res_img.status_code == 200:
            return res_img.content

        print(f"❌ Error descargando imagen desde Meta (HTTP {res_img.status_code})", flush=True)
        return None
    except Exception as e:
        print(f"❌ Excepción descargando media de WhatsApp: {e}", flush=True)
        return None
