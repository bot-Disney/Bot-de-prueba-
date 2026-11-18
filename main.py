import os
import time
import datetime
import threading
import requests
from fastapi import FastAPI, Request, Response
from bot_logic import (
    procesar_mensaje_bot,
    conectar_sheets,
    safe_get,
    limpiar_fila_cancelada_o_renovacion,
    obtener_hora_venezuela,
)
from alertas import revisar_y_enviar_alertas_vencimiento
from whatsapp_api import enviar_mensaje_whatsapp

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Diccionario temporal para prevenir doble clic / spam de botones
clics_procesados = {}


# =============================================================
# HILO VIGILANTE DE PAGOS PENDIENTES (30 MINUTOS)
# =============================================================
def iniciar_vigilante_pagos_pendientes():
    """Revisa cada 2 minutos si hay filas en 'Pendiente Pago' con más de 30 minutos sin comprobante y las libera."""
    def bucle_vigilante():
        time.sleep(15)
        while True:
            try:
                sheet = conectar_sheets()
                registros = sheet.get_all_records()
                ahora_local = obtener_hora_venezuela().replace(tzinfo=None)

                # Iteramos en orden inverso para evitar que al borrar filas se corran los índices
                for idx in range(len(registros) + 1, 1, -1):
                    row = registros[idx - 2]
                    estado = safe_get(row, "Estado", "").lower()

                    # Solo vigila órdenes congeladas que NO han enviado comprobante
                    if estado == "pendiente pago":
                        timestamp_orden = safe_get(row, "Vencimiento", "")

                        if timestamp_orden and len(timestamp_orden) == 19 and "-" in timestamp_orden:
                            try:
                                hora_orden = datetime.datetime.strptime(timestamp_orden, "%Y-%m-%d %H:%M:%S")
                                diferencia_minutos = (ahora_local - hora_orden).total_seconds() / 60

                                if diferencia_minutos > 30:
                                    tid_cliente = safe_get(row, "Telegram_ID", "")
                                    srv_vencido = safe_get(row, "Servicio", "Streaming")

                                    limpiar_fila_cancelada_o_renovacion(idx)
                                    print(f"🧹 Fila {idx} liberada automáticamente tras superar 30 minutos sin reporte de pago.")

                                    if tid_cliente:
                                        try:
                                            msg_vencido = (
                                                "⏳ *TIEMPO DE ESPERA AGOTADO*\n\n"
                                                f"Tu orden pendiente para *{srv_vencido}* ha expirado al superarse los 30 minutos sin reportar pago.\n"
                                                "Tu cupo ha sido liberado. Cuando gustes, puedes generar una nueva solicitud desde el menú."
                                            )
                                            enviar_mensaje_telegram(int(tid_cliente), msg_vencido)
                                        except Exception:
                                            pass
                            except ValueError:
                                pass
            except Exception as e:
                print(f"Error en el hilo vigilante de pagos de 30 min: {e}")

            time.sleep(120)

    hilo_v = threading.Thread(target=bucle_vigilante, daemon=True)
    hilo_v.start()
    print("🛡️ Vigilante automático de 30 minutos para pagos pendientes iniciado en segundo plano.")


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
    iniciar_vigilante_pagos_pendientes()


@app.get("/")
def home():
    return {"status": "El bot de streaming está activo y funcionando"}


# =============================================================
# WEBHOOK DE WHATSAPP (META CLOUD API)
# =============================================================
@app.get("/webhook/whatsapp")
def verificar_webhook_whatsapp(request: Request):
    """Verifica el token de seguridad configurado en el panel de desarrolladores de Meta."""
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "tu_token_secreto_personalizado")
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == verify_token:
            return Response(content=challenge, media_type="text/plain", status_code=200)
        return Response(status_code=403)
    return Response(status_code=400)


@app.post("/webhook/whatsapp")
async def recibir_mensaje_whatsapp(request: Request):
    """Recibe mensajes de texto enviados por los clientes a través de WhatsApp y los enruta al cerebro del bot."""
    try:
        body = await request.json()
        print(f"📥 Webhook de WhatsApp recibido: {body}")

        entry = body.get("entry", [])
        if not entry:
            return {"status": "ignored"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ignored"}

        value = changes[0].get("value", {})
        messages = value.get("messages")

        if messages:
            msg = messages[0]
            remitente = msg.get("from")  # Número de teléfono de WhatsApp del cliente (Ej: 58424...)
            tipo_msg = msg.get("type")

            # Obtenemos el nombre del contacto si viene en el payload de Meta
            contacts = value.get("contacts", [])
            nombre_cliente = "Cliente WhatsApp"
            if contacts:
                nombre_cliente = contacts[0].get("profile", {}).get("name", "Cliente WhatsApp")

            if tipo_msg == "text":
                texto_texto = msg.get("text", {}).get("body", "").strip()
                print(f"💬 Mensaje de {remitente} ({nombre_cliente}): {texto_texto}")
                
                # Enrutamos directamente al cerebro principal del bot unificado
                procesar_mensaje_bot(
                    chat_id=remitente,
                    texto=texto_texto,
                    nombre=nombre_cliente,
                    username="",
                    enviar_mensaje_callback=enviar_mensaje_whatsapp_wrapper,
                )

        return {"status": "success"}
    except Exception as e:
        print(f"❌ Error procesando webhook de WhatsApp: {e}")
        return {"status": "error"}


def enviar_mensaje_whatsapp_wrapper(chat_id, texto, teclado=None):
    """Función puente para adaptar el envío de mensajes de texto hacia WhatsApp."""
    enviar_mensaje_whatsapp(chat_id, texto)


# =============================================================
# WEBHOOK DE TELEGRAM
# =============================================================
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
                if tiempo_transcurrido < 2.0:
                    responder_callback_telegram(callback_id, "⏳ ¡Acción en proceso, espera un momento!")
                    return {"status": "ignorado_por_doble_clic"}

            clics_procesados[str(chat_id)] = ahora

            if len(clics_procesados) > 200:
                for k, t in list(clics_procesados.items()):
                    if ahora - t > 5:
                        clics_procesados.pop(k, None)
            # ---------------------------------------------

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
                callback_data=callback_data,
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
                enviar_foto_callback=enviar_foto_telegram,
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
                enviar_foto_callback=enviar_foto_telegram,
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
        "parse_mode": "Markdown",
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
        "parse_mode": "Markdown",
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
        "parse_mode": "Markdown",
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
