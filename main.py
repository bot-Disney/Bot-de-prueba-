import os
import time
import threading
import requests
from fastapi import FastAPI, Request
from bot_logic import procesar_mensaje_bot
from alertas import revisar_y_enviar_alertas_vencimiento  # <--- Importamos tu módulo de alertas

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Diccionario temporal para prevenir doble clic / spam de botones
clics_procesados = {}

# =============================================================
# HILO EN SEGUNDO PLANO PARA LAS ALERTAS DIARIAS
# =============================================================
def iniciar_reloj_alertas():
    """Ejecuta la revisión de vencimientos cada 24 horas (86400 segundos) en segundo plano."""
    def bucle_diario():
        time.sleep(30)
        while True:
            try:
                print("⏰ Ejecutando revisión automática diaria de vencimientos...")
                revisar_y_enviar_alertas_vencimiento(enviar_mensaje_telegram)
            except Exception as e:
                print(f"Error en el bucle automático de alertas: {e}")
            time.sleep(86400)

    hilo = threading.Thread(target=bucle_diario, daemon=True)
    hilo.start()
    print("🚀 Reloj automático de alertas diarias iniciado correctamente en segundo plano.")


@app.on_event("startup")
def startup_event():
    print("¡El servidor, el lector de Gmail y el bot interactivo se han iniciado en Render!")
    iniciar_reloj_alertas()


@app.get("/")
def home():
    return {"status": "El bot de streaming está activo y funcionando"}

@app.post("/webhook")
async def recibir_webhook(request: Request):
    """Recibe mensajes, clics de botones (callbacks) y fotos desde Telegram."""
    try:
        data = await request.json()
        
        # 1. Si el usuario hizo clic en un botón flotante (Inline Keyboard)
        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            callback_data = cb["data"]
            callback_id = cb["id"]
            
            nombre = cb["from"].get("first_name", "Cliente")
            username = cb["from"].get("username", "")
            
            # --- FILTRO ANTISPAM / DOBLE CLIC ESTRICTO ---
            ahora = time.time()
            if str(chat_id) in clics_procesados:
                tiempo_transcurrido = ahora - clics_procesados[str(chat_id)]
                if tiempo_transcurrido < 2.0:  # Si intenta repetir en menos de 2 segundos
                    # ¡Solo al usuario ansioso le sale el aviso flotante!
                    responder_callback_telegram(callback_id, "⏳ ¡Acción en proceso, espera un momento!")
                    return {"status": "ignorado_por_doble_clic"}
            
            clics_procesados[str(chat_id)] = ahora
            
            if len(clics_procesados) > 200:
                for k, t in list(clics_procesados.items()):
                    if ahora - t > 5:
                        clics_procesados.pop(k, None)
            # ---------------------------------------------
            
            # Clic normal: limpia el botón de forma totalmente silenciosa
            responder_callback_telegram(callback_id, "")
            
            procesar_mensaje_bot(
                chat_id=chat_id,
                texto="",
                nombre=nombre,
                username=username,
                enviar_mensaje_callback=enviar_mensaje_telegram,
                editar_mensaje_callback=editar_mensaje_telegram,
                message_id=message_id,
                es_callback=True,
                callback_data=callback_data
            )
            
        # 2. Si el usuario envió una FOTO / CAPTURA DE PANTALLA
        elif "message" in data and "photo" in data["message"]:
            message = data["message"]
            chat_id = message["chat"]["id"]
            nombre = message["from"].get("first_name", "Cliente")
            username = message["from"].get("username", "")
            photo_file_id = message["photo"][-1]["file_id"]
            
            procesar_mensaje_bot(
                chat_id=chat_id,
                texto="",
                nombre=nombre,
                username=username,
                enviar_mensaje_callback=enviar_mensaje_telegram,
                photo_file_id=photo_file_id,
                enviar_foto_callback=enviar_foto_telegram
            )

        # 3. Si el usuario envió un mensaje de texto normal
        elif "message" in data and "text" in data["message"]:
            message = data["message"]
            chat_id = message["chat"]["id"]
            texto = message.get("text", "")
            nombre = message["from"].get("first_name", "Cliente")
            username = message["from"].get("username", "")
            
            procesar_mensaje_bot(
                chat_id=chat_id,
                texto=texto,
                nombre=nombre,
                username=username,
                enviar_mensaje_callback=enviar_mensaje_telegram,
                enviar_foto_callback=enviar_foto_telegram
            )

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return {"status": "error", "message": str(e)}

def enviar_mensaje_telegram(chat_id, texto, teclado=None):
    """Envía un mensaje nuevo al chat de Telegram."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    if teclado:
        payload["reply_markup"] = teclado
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def enviar_foto_telegram(chat_id, photo_file_id, caption, teclado=None):
    """Reenvía una foto (captura de pago) con texto y botones al chat (ej: al Admin)."""
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_file_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    if teclado:
        payload["reply_markup"] = teclado
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando foto a Telegram: {e}")

def editar_mensaje_telegram(chat_id, message_id, texto, teclado=None):
    """Edita un mensaje existente para una experiencia más fluida."""
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    if teclado:
        payload["reply_markup"] = teclado
    try:
        response = requests.post(url, json=payload)
        res_json = response.json()
        if not res_json.get("ok"):
            enviar_mensaje_telegram(chat_id, texto, teclado)
    except Exception as e:
        print(f"Error editando mensaje en Telegram: {e}")

def responder_callback_telegram(callback_id, texto_alerta=""):
    """Responde al callback. Si hay texto, muestra la alerta flotante (para usuarios ansiosos)."""
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_id}
    if texto_alerta:
        payload["text"] = texto_alerta
        payload["show_alert"] = False
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error respondiendo callback: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
