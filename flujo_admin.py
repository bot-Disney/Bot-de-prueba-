import time
from config_y_estado import (
    ADMIN_ID,
    esperando_captura_pago,
    esperando_nuevo_nombre_perfil,
    esperando_busqueda_admin,
    asistente_cuenta_datos,
    asistente_edicion_admin,
    asistente_cupon_admin,
    esperando_codigo_cupon_cliente,
    detalles_pago_activos,
    asistente_difusion_admin,
    registros_pendientes_info,
    safe_get,
    obtener_hora_venezuela
)
from teclados import get_main_menu_keyboard, get_back_keyboard, quitar_botones_telegram
from servicios_sheets import (
    conectar_sheets,
    generar_reporte_admin,
    generar_resumen_completo_negocio,
    obtener_clientes_pendientes,
    obtener_suscripciones_vencidas,
    obtener_clientes_activos_general,
    liberar_y_eliminar_fila_suscripcion,
    procesar_asignacion_stock_masivo
)


def enviar_difusion_masiva(texto_mensaje, enviar_msg_cb):
    """Envía un mensaje masivo a todos los clientes únicos registrados en Google Sheets."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        telegrams_enviados = set()
        contador = 0

        for r in registros:
            tid = safe_get(r, "Telegram_ID", "").strip()
            if tid and tid not in telegrams_enviados:
                telegrams_enviados.add(tid)
                try:
                    enviar_msg_cb(int(tid), texto_mensaje, get_main_menu_keyboard())
                    contador += 1
                    time.sleep(0.1)
                except Exception as e:
                    print(f"No se pudo enviar difusión a {tid}: {e}")
        return contador
    except Exception as e:
        print(f"Error en difusión masiva: {e}")
        return 0


def verificar_y_notificar_vencimientos_admin(enviar_msg_cb):
    """Revisa las pantallas que ya vencieron y envía una alerta al admin con un botón directo para borrarlas y liberar el cupo."""
    if not ADMIN_ID:
        return "No hay ADMIN_ID configurado."

    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        hoy = obtener_hora_venezuela().date()
        avisos_enviados = 0

        for idx, row in enumerate(registros, start=2):
            estado = safe_get(row, "Estado", "").lower()
            vencimiento_str = safe_get(row, "Vencimiento", "")
            correo = safe_get(row, "Cuenta", "")
            nombre_cliente = safe_get(row, "Nombre", "Cliente")
            servicio = safe_get(row, "Servicio", "Disney+")
            pantalla = safe_get(row, "Pantalla", "Perfil 1")
            tid = safe_get(row, "Telegram_ID", "")

            if correo and correo.lower() not in ("por asignar", "pendiente de stock"):
                if "pendiente" in estado:
                    continue

                fecha_venc = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
                        break
                    except ValueError:
                        continue

                if fecha_venc:
                    dias_restantes = (fecha_venc - hoy).days

                    if dias_restantes < 0:
                        dias_vencido = abs(dias_restantes)
                        
                        alerta_vencimiento_admin = (
                            "🔴 *ALERTA: PERFIL VENCIDO — ACCIÓN REQUERIDA* 🔴\n\n"
                            f"• *Vencimiento:* Hace {dias_vencido} día(s)\n"
                            f"• *Cliente:* {nombre_cliente} (`{tid}`)\n"
                            f"• *Servicio:* {servicio} ({pantalla})\n"
                            f"• *Correo Maestro:* `{correo}`\n\n"
                            "🛠️ *Pasos a seguir:*\n"
                            "1️⃣ Entra a Netflix o Disney+ y **cierra la sesión / cambia el PIN** de este perfil para bloquear el acceso.\n"
                            "2️⃣ Presiona el botón de abajo para **borrar la fila y liberar el cupo** de la hoja automáticamente."
                        )

                        teclado_borrar_admin = {
                            "inline_keyboard": [
                                [{"text": "🗑️ Liberar Perfil y Borrar Fila", "callback_data": f"admin_liberar_{idx}"}],
                                [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                            ]
                        }

                        try:
                            enviar_msg_cb(int(ADMIN_ID), alerta_vencimiento_admin, teclado_borrar_admin)
                            avisos_enviados += 1
                            time.sleep(0.2)
                        except Exception as e:
                            print(f"No se pudo enviar alerta de vencimiento al admin: {e}")

        return f"Revisión completada. Alertas enviadas: {avisos_enviados}."
    except Exception as e:
        print(f"Error verificando vencimientos: {e}")
        return f"Error: {e}"
