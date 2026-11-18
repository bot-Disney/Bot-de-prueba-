import os
import requests
from config_y_estado import safe_get

def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / pantallas", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código", "callback_data": "obtener_codigo"}],
            [{"text": "🔄 Renovar (+30 días)", "callback_data": "renovar_suscripcion"}, {"text": "🛒 Comprar Pantalla", "callback_data": "comprar_extra"}],
            [{"text": "💬 Soporte / Pagos", "callback_data": "soporte"}]
        ]
    }


def get_datos_keyboard(mostrar_renovar=False, suscripciones=None):
    botones = []
    if suscripciones:
        tiene_activas = any(safe_get(s, "Estado", "").lower() == "activo" and "pendiente" not in safe_get(s, "Cuenta", "").lower() for s in suscripciones)
        if tiene_activas:
            botones.append([{"text": "✏️ Personalizar Nombres de Perfil", "callback_data": "menu_renombrar"}])

    if mostrar_renovar: 
        botones.append([{"text": "🔄 Renovar Suscripción", "callback_data": "renovar_suscripcion"}],)
        
    botones.append([{"text": "🛒 Comprar Pantalla Adicional", "callback_data": "comprar_extra"}])
    botones.append([{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}])
    return {"inline_keyboard": botones}


def get_back_keyboard():
    return {
        "inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]
    }


def quitar_botones_telegram(chat_id, message_id):
    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/editMessageReplyMarkup"
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []}
        }, timeout=3)
    except Exception as e:
        print(f"No se pudieron quitar los botones: {e}")
