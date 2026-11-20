import os
import json
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
from whatsapp_api import enviar_mensaje_whatsapp, descargar_media_whatsapp

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Diccionario temporal para prevenir doble clic / spam de botones en Telegram
clics_procesados = {}

# Diccionario temporal para mapear opciones numeradas de WhatsApp -> callback_data
menus_whatsapp_activos = {}


# =============================================================
# ENVÍO INTELIGENTE (DETECTA SI ES TELEGRAM O WHATSAPP)
# =============================================================
def enviar_mensaje_unificado(chat_id, texto, teclado=None):
    """Enruta el mensaje hacia WhatsApp o Telegram según el formato del ID."""
    str_id = str(chat_id).strip()
    # Los números de WhatsApp incluyen código de país (ej: 58424...) y suelen tener 11+ dígitos
    if str_id.isdigit() and len(str_id) >= 11:
        enviar_mensaje_whatsapp_wrapper(str_id, texto, teclado)
    else:
        enviar_mensaje_telegram(chat_id, texto, teclado)


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
                                    print(f"🧹 Fila {idx} liberada automáticamente tras superar 30 minutos sin reporte de pago.", flush=True)

                                    if tid_cliente:
                                        try:
                                            msg_vencido = (
                                                "⏳ *TIEMPO DE ESPERA AGOTADO*\n\n"
                                                f"Tu orden pendiente para *{srv_vencido}* ha expirado al superarse los 30 minutos sin reportar pago.\n"
                                                "Tu cupo ha sido liberado. Cuando gustes, puedes generar una nueva solicitud desde el menú."
                                            )
                                            enviar_mensaje_unificado(tid_cliente, msg_vencido)
                                        except Exception:
                                            pass
                            except ValueError:
                                pass
            except Exception as e:
                print(f"Error en el hilo vigilante de pagos de 30 min: {e}", flush=True)

            time.sleep(120)

    hilo_v = threading.Thread(target=bucle_vigilante, daemon=True)
    hilo_v.start()
    print("🛡️ Vigilante automático de 30 minutos para pagos pendientes iniciado en segundo plano.", flush=True)


# =============================================================
# HILO EN SEGUNDO PLANO PARA LAS ALERTAS DIARIAS
# =============================================================
def iniciar_reloj_alertas():
    """Ejecuta la revisión de vencimientos cada 24 horas (86400 segundos) en segundo plano."""
    def bucle_diario():
        time.sleep(30)
        while True:
            try:
                print("⏰ Ejecutando revisión automática diaria de vencimientos...", flush=True)
                revisar_y_enviar_alertas_vencimiento(enviar_mensaje_unificado)
            except Exception as e:
                print(f"Error en el bucle automático de alertas: {e}", flush=True)
            time.sleep(86400)

    hilo = threading.Thread(target=bucle_diario, daemon=True)
    hilo.start()
    print("🚀 Reloj automático de alertas diarias iniciado correctamente en segundo plano.", flush=True)


def configurar_webhook_automatico():
    """Registra o actualiza el webhook de Telegram al arrancar el servicio en Render."""
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if not base_url:
        print("⚠️ RENDER_EXTERNAL_URL no está disponible; se omite el registro automático del webhook.", flush=True)
        return

    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "TU_TOKEN_DE_TELEGRAM":
        print("⚠️ TELEGRAM_TOKEN no está configurado; se omite el registro automático del webhook.", flush=True)
        return

    webhook_url = f"{base_url}/webhook"
    try:
        res = requests.post(
            f"{TELEGRAM_API_URL}/setWebhook",
            json={"url": webhook_url},
            timeout=10,
        )
        data_res = res.json()
        if data_res.get("ok"):
            print(f"✅ Webhook de Telegram sincronizado automáticamente: {webhook_url}", flush=True)
        else:
            print(f"⚠️ Telegram respondió al setWebhook con error: {data_res}", flush=True)
    except Exception as e:
        print(f"⚠️ Error al registrar el webhook automáticamente al iniciar: {e}", flush=True)


@app.on_event("startup")
def startup_event():
    print("¡El servidor, el lector de Gmail y el bot interactivo se han iniciado en Render!", flush=True)
    configurar_webhook_automatico()
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
    """Recibe mensajes de texto e imágenes enviados por los clientes en WhatsApp y los enruta al cerebro del bot."""
    try:
        body = await request.json()
        print(f"📥 Webhook de WhatsApp recibido: {body}", flush=True)

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
            remitente = str(msg.get("from", "")).strip()
            tipo_msg = msg.get("type")

            contacts = value.get("contacts", [])
            nombre_cliente = "Cliente WhatsApp"
            if contacts:
                nombre_cliente = contacts[0].get("profile", {}).get("name", "Cliente WhatsApp")

            if tipo_msg == "text":
                texto_usuario = msg.get("text", {}).get("body", "").strip()
                print(f"💬 Mensaje de {remitente} ({nombre_cliente}): {texto_usuario}", flush=True)

                # Comprobar si el usuario respondió con un número de un menú activo
                opciones_usuario = menus_whatsapp_activos.get(remitente, {})
                if texto_usuario in opciones_usuario:
                    accion_elegida = opciones_usuario[texto_usuario]

                    if accion_elegida.startswith("http"):
                        enviar_mensaje_whatsapp(remitente, f"🔗 Abre este enlace para continuar:\n{accion_elegida}")
                    else:
                        procesar_mensaje_bot(
                            chat_id=remitente,
                            texto="",
                            nombre=nombre_cliente,
                            username="",
                            enviar_mensaje_callback=enviar_mensaje_unificado,
                            es_callback=True,
                            callback_data=accion_elegida,
                            enviar_foto_callback=enviar_foto_telegram,
                        )
                else:
                    # Flujo normal de texto (ej: "Hola", escribir código de cupón, nuevo nombre, etc.)
                    procesar_mensaje_bot(
                        chat_id=remitente,
                        texto=texto_usuario,
                        nombre=nombre_cliente,
                        username="",
                        enviar_mensaje_callback=enviar_mensaje_unificado,
                        enviar_foto_callback=enviar_foto_telegram,
                    )

            elif tipo_msg == "image":
                media_id = msg.get("image", {}).get("id")
                caption_img = msg.get("image", {}).get("caption", "").strip()
                print(f"📸 Imagen recibida de {remitente} ({nombre_cliente}) - media_id: {media_id}", flush=True)

                bytes_imagen = descargar_media_whatsapp(media_id) if media_id else None
                if bytes_imagen:
                    procesar_mensaje_bot(
                        chat_id=remitente,
                        texto=caption_img,
                        nombre=nombre_cliente,
                        username="",
                        enviar_mensaje_callback=enviar_mensaje_unificado,
                        photo_file_id=bytes_imagen,
                        enviar_foto_callback=enviar_foto_telegram,
                    )
                else:
                    enviar_mensaje_whatsapp(
                        remitente,
                        "⚠️ No pudimos procesar la imagen recibida. Por favor, intenta enviarla nuevamente o escribe los datos de tu referencia."
                    )

        return {"status": "success"}
    except Exception as e:
        print(f"❌ Error procesando webhook de WhatsApp: {e}", flush=True)
        return {"status": "error"}


def enviar_mensaje_whatsapp_wrapper(chat_id, texto, teclado=None):
    """Convierte mensajes y teclados de Telegram en texto con opciones numeradas para WhatsApp."""
    str_id = str(chat_id).strip()
    texto_final = texto

    if teclado and isinstance(teclado, dict) and "inline_keyboard" in teclado:
        opciones_mapa = {}
        lineas_opciones = []
        contador = 1

        for fila in teclado["inline_keyboard"]:
            for boton in fila:
                etiqueta = boton.get("text", "").strip()
                cb_data = boton.get("callback_data")
                url_btn = boton.get("url")

                if cb_data:
                    opciones_mapa[str(contador)] = cb_data
                    lineas_opciones.append(f"*{contador}.* {etiqueta}")
                    contador += 1
                elif url_btn:
                    opciones_mapa[str(contador)] = url_btn
                    lineas_opciones.append(f"*{contador}.* {etiqueta}")
                    contador += 1

        if lineas_opciones:
            menus_whatsapp_activos[str_id] = opciones_mapa
            texto_final += "\n\n" + "\n".join(lineas_opciones) + "\n\n_Responde con el número de la opción que deseas._"
    else:
        # Si el bot solicita escribir un dato libre (cupón, nombre, etc.), limpiamos el menú previo
        menus_whatsapp_activos.pop(str_id, None)

    enviar_mensaje_whatsapp(str_id, texto_final)


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
                enviar_mensaje_callback=enviar_mensaje_unificado,
                editar_mensaje_callback=editar_mensaje_telegram,
                message_id=message_id,
                es_callback=True,
                callback_data=callback_data,
                enviar_foto_callback=enviar_foto_telegram,
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
                enviar_mensaje_callback=enviar_mensaje_unificado,
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
                enviar_mensaje_callback=enviar_mensaje_unificado,
                enviar_foto_callback=enviar_foto_telegram,
            )

        return {"status": "ok"}

    except Exception as e:
        print(f"Error procesando el webhook: {e}", flush=True)
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
        print(f"Error enviando mensaje a Telegram: {e}", flush=True)


def enviar_foto_telegram(chat_id, photo_file_id, caption, teclado=None):
    """Reenvía una foto (por file_id de Telegram o bytes descargados de WhatsApp) al Admin."""
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    try:
        if isinstance(photo_file_id, bytes):
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            if teclado:
                data["reply_markup"] = json.dumps(teclado)
            files = {"photo": ("comprobante_whatsapp.jpg", photo_file_id, "image/jpeg")}
            requests.post(url, data=data, files=files)
        else:
            payload = {
                "chat_id": chat_id,
                "photo": photo_file_id,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            if teclado:
                payload["reply_markup"] = teclado
            requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando foto a Telegram: {e}", flush=True)


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
        print(f"Error editando mensaje en Telegram: {e}", flush=True)


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
        print(f"Error respondiendo callback: {e}", flush=True)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
