import os
import requests

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

def enviar_mensaje_whatsapp(telefono_destino, texto_mensaje):
    """Envía un mensaje de texto plano o con formato básico a un número de WhatsApp."""
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("⚠️ Error: Faltan las credenciales de WhatsApp en las variables de entorno.")
        return False

    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
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
