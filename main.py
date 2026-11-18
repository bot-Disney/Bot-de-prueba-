import os
import time
import datetime
import threading
import requests
from fastapi import FastAPI, Request
from bot_logic import procesar_mensaje_bot, conectar_sheets, safe_get, liberar_y_eliminar_fila_suscripcion, obtener_hora_venezuela
from alertas import revisar_y_enviar_alertas_vencimiento

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
        time.sleep(15)  # Espera inicial al arrancar el servidor
        while True:
            try:
                sheet = conectar_sheets()
                registros = sheet.get_all_records()
                ahora_local = obtener_hora_venezuela().replace(tzinfo=None)

                for idx, row in enumerate(registros, start=2):
                    estado = safe_get(row, "Estado", "").lower()
                    
                    # Solo vigilamos a los que se quedaron estáticos en 'Pendiente Pago'
                    if estado == "pendiente pago":
                        # Buscamos la fecha o timestamp guardado en Vencimiento u otra celda temporal
                        timestamp_orden = safe_get(row, "Vencimiento", "")
                        
                        if timestamp_orden and len(timestamp_orden) == 19 and "-" in timestamp_orden:
                            try:
                                hora_orden = datetime.datetime.strptime(timestamp_orden, "%Y-%m-%d %H:%M:%S")
                                diferencia_minutos = (ahora_local - hora_orden).total_seconds() / 60
                                
                                if diferencia_minutos > 30:
                                    tid_cliente = safe_get(row, "Telegram_ID", "")
                                    srv_vencido = safe_get(row, "Servicio", "Streaming")
                                    
                                    # Liberamos la fila y el cupo en stock
                                    liberar_y_eliminar_fila_suscripcion(idx)
                                    print(f"🧹 Fila {idx} eliminada automáticamente por superar los 30 minutos sin reportar pago.")
                                    
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
            
            time.sleep(120)  # Revisa cada 2 minutos

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

@app.post("/webhook")
async def recibir_webhook(request: Request):
    """Recibe mensajes, clics de botones (callbacks) y fotos desde Telegram."""
    try:
        data = await request.json()
        
        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            callback_data = cb["data"]
            callback_id = cb["id"]
            
            nombre = cb["from"].get("first_name", "Cliente")
            username = cb["from"].get("username", "")
            
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
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = teclado
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def enviar_foto_telegram(chat_id, photo_file_id, caption, teclado=None):
    url = f"{TELEGRAM_API_URL}/sendPhoto"
    payload = {"chat_id": chat_id, "photo": photo_file_id, "caption": caption, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = teclado
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando foto a Telegram: {e}")

def editar_mensaje_telegram(chat_id, message_id, texto, teclado=None):
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": texto, "parse_mode": "Markdown"}
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
