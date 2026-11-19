import os
import requests

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


def enviar_mensaje_whatsapp(telefono_destino, texto_mensaje):
    """Envía un mensaje de texto plano o con formato básico a un número de WhatsApp."""
    token_actual = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
    phone_id_actual = os.getenv("PHONE_NUMBER_ID", PHONE_NUMBER_ID)

    if not token_actual or not phone_id_actual:
        print("⚠️ Error: Faltan las credenciales de WhatsApp en las variables de entorno.")
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
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 200:
            return True
        else:
            print(f"Error enviando mensaje de WhatsApp: {response.text}")
            return False
    except Exception as e:
        print(f"Excepción al conectar con la API de WhatsApp: {e}")
        return False


def descargar_media_whatsapp(media_id):
    """Consulta la URL de descarga en Meta y devuelve los bytes de la imagen enviada por WhatsApp."""
    token_actual = os.getenv("WHATSAPP_TOKEN", WHATSAPP_TOKEN)
    if not token_actual or not media_id:
        print("⚠️ Error: Falta WHATSAPP_TOKEN o media_id para descargar imagen.")
        return None

    headers = {"Authorization": f"Bearer {token_actual}"}
    try:
        meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
        res_meta = requests.get(meta_url, headers=headers, timeout=10).json()
        download_url = res_meta.get("url")
        if not download_url:
            print(f"❌ No se obtuvo URL de descarga para media {media_id}: {res_meta}")
            return None

        res_img = requests.get(download_url, headers=headers, timeout=20)
        if res_img.status_code == 200:
            return res_img.content

        print(f"❌ Error descargando imagen desde Meta (HTTP {res_img.status_code})")
        return None
    except Exception as e:
        print(f"❌ Excepción descargando media de WhatsApp: {e}")
        return None
