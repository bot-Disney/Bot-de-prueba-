import time
from gmail_otp import obtener_ultimo_codigo_disney, obtener_ultimo_codigo_netflix
from config_y_estado import (
    WHATSAPP_NUMERO,
    PRECIO_DISNEY_USD,
    PRECIO_NETFLIX_USD,
    control_intentos_otp,
    MAX_INTENTOS_RAPIDOS,
    COOLDOWN_SEGUNDOS,
    esperando_captura_pago,
    detalles_pago_activos,
    safe_get,
    obtener_tasa_usdt_hoy
)
from teclados import get_main_menu_keyboard, get_datos_keyboard, get_back_keyboard
from servicios_sheets import (
    conectar_sheets,
    existen_cupones_activos,
    obtener_suscripciones_por_id,
    verificar_cliente_activo,
    obtener_pin_asignado_cliente,
    limpiar_fila_cancelada_o_renovacion,
    crear_nueva_fila_pendiente
)


def ejecutar_busqueda_otp(chat_id, str_chat_id, servicio, message_id, enviar_cb, editar_cb, es_cb):
    ahora = time.time()
    if str_chat_id not in control_intentos_otp:
        control_intentos_otp[str_chat_id] = {"intentos": 0, "ultimo_tiempo": 0}

    datos_usuario = control_intentos_otp[str_chat_id]
    if ahora - datos_usuario["ultimo_tiempo"] > COOLDOWN_SEGUNDOS:
        datos_usuario["intentos"] = 0

    if datos_usuario["intentos"] >= MAX_INTENTOS_RAPIDOS:
        transcurrido = ahora - datos_usuario["ultimo_tiempo"]
        if transcurrido < COOLDOWN_SEGUNDOS:
            restante = int(COOLDOWN_SEGUNDOS - transcurrido)
            mensaje = f"⏳ *LÍMITE ALCANZADO*\n\nEspera *{restante // 60}m {restante % 60}s* antes de pedir otro código."
            teclado = get_back_keyboard()
            if es_cb and editar_cb:
                editar_cb(chat_id, message_id, mensaje, teclado)
            else:
                enviar_cb(chat_id, mensaje, teclado)
            return

    datos_usuario["intentos"] += 1
    datos_usuario["ultimo_tiempo"] = ahora

    es_netflix = "netflix" in servicio
    nombre_plataforma = "Netflix" if es_netflix else "Disney+"

    msg_espera = f"🔍 Buscando código reciente en el correo de *{nombre_plataforma}*, un momento..."
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, msg_espera, get_back_keyboard())
    else:
        enviar_cb(chat_id, msg_espera)

    codigo = obtener_ultimo_codigo_netflix() if es_netflix else obtener_ultimo_codigo_disney()

    if codigo:
        mensaje = f"🔑 *Tu código de acceso de {nombre_plataforma} es:*\n\n`{codigo}`\n\n_(Cópialo e ingrésalo en tu pantalla)_"
    else:
        mensaje = f"⚠️ No se encontraron códigos recientes de *{nombre_plataforma}*. Asegúrate de haberlo solicitado en tu TV hace unos segundos e intenta de nuevo."

    teclado = get_back_keyboard()
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado)
    else:
        enviar_cb(chat_id, mensaje, teclado)


def registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_cb, ADMIN_ID):
    str_chat_id = str(chat_id).strip()
    ahora = time.time()
    
    if "intentos_anormales" not in control_intentos_otp:
        control_intentos_otp["intentos_anormales"] = {}
        
    if str_chat_id not in control_intentos_otp["intentos_anormales"]:
        control_intentos_otp["intentos_anormales"][str_chat_id] = {"contador": 0, "primer_intento": ahora}
        
    registro = control_intentos_otp["intentos_anormales"][str_chat_id]
    
    if ahora - registro["primer_intento"] > 3600:
        registro["contador"] = 0
        registro["primer_intento"] = ahora
        
    registro["contador"] += 1
    
    if registro["contador"] >= 3 and ADMIN_ID and enviar_mensaje_cb:
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        alerta_anomalia = (
            "🚨 *¡ALERTA DE COMPORTAMIENTO SOSPECHOSO!* 🚨\n\n"
            f"• *Usuario:* {nombre_completo}\n"
            f"• *Telegram ID:* `{str_chat_id}`\n"
            f"• *Incidente:* Ha intentado solicitar códigos de acceso múltiples veces sin tener una suscripción activa o con cuenta vencida.\n\n"
            "💡 Es posible que este usuario esté intentando acceder sin pagar o buscando filtrar accesos. Puedes buscar su ID en `/admin` para verificarlo."
        )
        try:
            enviar_mensaje_cb(int(ADMIN_ID), alerta_anomalia)
            registro["contador"] = 0
        except Exception as e:
            print(f"Error enviando alerta de anomalía al admin: {e}")


def iniciar_proceso_pago_con_descuento(chat_id, str_chat_id, nombre, username, servicio_clave, tipo_operacion, row_idx_target, message_id, enviar_cb, editar_cb, es_cb, cupon_aplicado=None):
    esperando_captura_pago[str_chat_id] = row_idx_target
    
    es_netflix = (servicio_clave == "netflix")
    servicio_elegido = "Netflix" if es_netflix else "Disney+"
    precio_base = PRECIO_NETFLIX_USD if es_netflix else PRECIO_DISNEY_USD
    precio_usd = precio_base
    sin_stock = False

    texto_descuento_nota = ""
    codigo_usado_str = "Ninguno (Precio Regular)"

    if cupon_aplicado:
        codigo_usado_str = cupon_aplicado["codigo"]
        tipo_desc = cupon_aplicado["tipo"]
        valor_desc = cupon_aplicado["valor"]

        if tipo_desc.lower() == "fijo":
            precio_usd = max(0.50, precio_base - valor_desc)
            texto_descuento_nota = f"🎟️ *Cupón aplicado:* `{codigo_usado_str}` (-${valor_desc:.2f} USD)\n"
        else:
            descuento_calculado = (precio_base * valor_desc) / 100
            precio_usd = max(0.50, precio_base - descuento_calculado)
            texto_descuento_nota = f"🎟️ *Cupón aplicado:* `{codigo_usado_str}` (-{valor_desc}%)\n"

    try:
        sheet = conectar_sheets()
        hora_actual_iso = obtener_hora_venezuela().strftime("%Y-%m-%d %H:%M:%S") if 'obtener_hora_venezuela' in globals() else ""
        # Usamos time si hace falta o importamos de config
        from config_y_estado import obtener_hora_venezuela
        hora_actual_iso = obtener_hora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
        sheet.update_cell(row_idx_target, 5, hora_actual_iso) 
        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")
        
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
        if "pendiente de stock" in safe_get(fila_obj, "Cuenta", "").lower():
            sin_stock = True
    except Exception as e:
        print(f"Error actualizando celda de pago: {e}")

    tasa_usdt = obtener_tasa_usdt_hoy()
    monto_bs = round(precio_usd * tasa_usdt, 2)

    detalles_pago_activos[str_chat_id] = {
        "cupon": codigo_usado_str,
        "monto_usd": precio_usd,
        "tasa": tasa_usdt,
        "total_bs": monto_bs
    }

    texto_soporte = f"Hola, tengo dudas o necesito asistencia técnica con mi servicio de Streaming. Mi ID de Telegram es: {str_chat_id}."
    url_whatsapp_soporte = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_soporte.replace(' ', '%20')}"

    aviso_stock = ""
    if sin_stock:
        aviso_stock = (
            "⏳ *NOTA DE DISPONIBILIDAD:* Nuestras cuentas de entrega inmediata para "
            f"*{servicio_elegido}* están al 100% en este instante, pero puedes realizar tu pago "
            "para asegurar **prioridad #1** en la asignación de nuestra próxima cuenta.\n\n"
        )
    
    from config_y_estado import PAGO_MOVIL_BANCO, PAGO_MOVIL_CEDULA, PAGO_MOVIL_TELEFONO
    mensaje = (
        f"💳 *DATOS DE PAGO — {servicio_elegido.upper()}*\n\n"
        f"{aviso_stock}"
        f"{texto_descuento_nota}"
        f"💵 *Monto a Pagar:* `{precio_usd:.2f} USDT`\n"
        f"📈 *Tasa del día:* `{tasa_usdt} Bs`\n"
        f"💰 *Total en Bolívares:* `{monto_bs} Bs`\n\n"
        f"📲 *Datos de Pago Móvil (Toca para copiar):*\n"
        f"• *Banco:* {PAGO_MOVIL_BANCO}\n"
        f"• *Cédula:* `{PAGO_MOVIL_CEDULA}`\n"
        f"• *Teléfono:* `{PAGO_MOVIL_TELEFONO}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📸 *PASO FINAL:* Realiza el pago y **envía tu captura o referencia por este mismo chat**."
    )
    
    teclado_pago_botones = []
    if not cupon_aplicado and existen_cupones_activos():
        teclado_pago_botones.append([{"text": "🎟️ ¿Tienes un cupón? Canjéalo aquí", "callback_data": f"usar_cupon_{row_idx_target}"}])
    
    teclado_pago_botones.append([{"text": "💬 Soporte Técnico (Solo dudas)", "url": url_whatsapp_soporte}])
    teclado_pago_botones.append([{"text": "🔙 Cancelar y Volver", "callback_data": "menu_principal"}])

    teclado_pago = {"inline_keyboard": teclado_pago_botones}

    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado_pago)
    else:
        enviar_cb(chat_id, mensaje, teclado_pago)


def notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_target, detalle_operacion, enviar_cb, editar_cb=None, message_id=None, es_cb=False, ADMIN_ID=None):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
        servicio_elegido = safe_get(fila_obj, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_obj, "Pantalla", "Perfil 1")
        cuenta_asignada = safe_get(fila_obj, "Cuenta", "Por Asignar")
        precio_usd = PRECIO_NETFLIX_USD if "netflix" in str(servicio_elegido).lower() else PRECIO_DISNEY_USD

        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")

        aviso_stock = ""
        if "pendiente de stock" in str(cuenta_asignada).lower():
            aviso_stock = (
                "\n⏳ *Nota de Disponibilidad:* Nuestras cuentas inmediatas están llenas, "
                "pero al entregar tu pago quedas asegurado con **prioridad #1** en la asignación.\n"
            )

        mensaje_cliente = (
            "💵 *PAGO EN EFECTIVO REGISTRADO*\n\n"
            f"• *Operación:* {detalle_operacion}\n"
            f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
            f"• *Monto a cancelar:* `${precio_usd:.2f} USD`\n"
            f"{aviso_stock}\n"
            "👤 Entrega el efectivo al encargado del local para que proceda a verificar y activar tu cuenta."
        )
        if es_cb and editar_cb:
            editar_cb(chat_id, message_id, mensaje_cliente, get_back_keyboard())
        else:
            enviar_cb(chat_id, mensaje_cliente, get_back_keyboard())

        if ADMIN_ID:
            texto_admin = (
                "🔔 *¡NUEVO PAGO EN EFECTIVO REPORTADO!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username})\n"
                f"• *Telegram ID:* `{str_chat_id}`\n"
                f"• *Tipo:* {detalle_operacion}\n"
                f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
                f"• *Correo/Cuenta:* {cuenta_asignada}\n"
                f"• *Monto esperado:* `${precio_usd:.2f} USD`"
            )
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar Efectivo (+30 días)", "callback_data": f"aprobar_{row_idx_target}_efectivo"}],
                    [{"text": "❌ Rechazar Pago", "callback_data": f"rechazar_{row_idx_target}"}]
                ]
            }
            enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)
    except Exception as e:
        print(f"Error procesando notificación de efectivo: {e}")
        enviar_cb(chat_id, "⚠️ Ocurrió un error al registrar el pago en efectivo.", get_back_keyboard())


def procesar_texto_reporte(chat_id, texto, nombre, username, enviar_cb, str_chat_id, row_idx_pendiente, enviar_foto_callback, ADMIN_ID=None):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_pendiente - 2] if (row_idx_pendiente - 2) < len(registros) else {}
        cuenta_asociada = safe_get(fila_obj, "Cuenta", "Por Asignar")
        servicio_asociado = safe_get(fila_obj, "Servicio", "Disney+")
        pantalla_asociada = safe_get(fila_obj, "Pantalla", "Perfil 1")
    except Exception:
        cuenta_asociada = "Por Asignar"
        servicio_asociado = "Disney+"
        pantalla_asociada = "Perfil 1"

    info_pago = detalles_pago_activos.get(str_chat_id, {})
    cupon_txt = info_pago.get("cupon", "Ninguno (Precio Regular)")
    monto_usd = info_pago.get("monto_usd", 0.0)
    tasa_bs = info_pago.get("tasa", 0.0)
    total_bs = info_pago.get("total_bs", 0.0)

    if ADMIN_ID:
        texto_admin = (
            "🔔 *¡NUEVO REPORTE DE PAGO (TEXTO/REFERENCIA)!* 🔔\n\n"
            f"• *Cliente:* {nombre} (@{username})\n"
            f"• *Telegram ID:* `{str_chat_id}`\n"
            f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})\n"
            f"• *Cuenta/Correo:* {cuenta_asociada}\n"
            f"• *Referencia/Detalle:* `{texto}`\n\n"
            f"🎟️ *Cupón utilizado:* `{cupon_txt}`\n"
            f"💵 *Monto en USD:* `${monto_usd:.2f} USDT`\n"
            f"📈 *Tasa aplicada:* `{tasa_bs} Bs`\n"
            f"💰 *Total exacto a transferir:* `{total_bs} Bs`"
        )
        
        teclado_admin = {
            "inline_keyboard": [
                [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                [{"text": "❌ Rechazar Pago", "callback_data": f"rechazar_{row_idx_pendiente}"}]
            ]
        }
        enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)

    enviar_cb(chat_id, "✅ Reporte enviado con éxito al administrador. En breve verificaremos tu referencia.", get_main_menu_keyboard())
