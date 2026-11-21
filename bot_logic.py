import os
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
from teclados import get_main_menu_keyboard, get_datos_keyboard, get_back_keyboard, quitar_botones_telegram
from servicios_sheets import (
    conectar_sheets,
    existen_cupones_activos,
    validar_y_consumir_cupon,
    guardar_nuevo_cupon_sheet,
    obtener_pin_asignado_cliente,
    limpiar_fila_cancelada_o_renovacion,
    rechazar_pago_seguro,
    asignar_correo_desde_stock,
    procesar_asignacion_stock_masivo,
    obtener_suscripciones_por_id,
    crear_nueva_fila_pendiente,
    verificar_cliente_activo,
    obtener_clientes_pendientes,
    obtener_clientes_activos_general,
    obtener_suscripciones_vencidas,
    liberar_y_eliminar_fila_suscripcion,
    aprobar_suscripcion_sheet,
    registrar_venta_en_historial,
    verificar_alerta_vencimiento,
    generar_reporte_admin,
    generar_resumen_completo_negocio
)
from flujo_cliente import (
    ejecutar_busqueda_otp,
    registrar_intento_sospechoso_otp,
    iniciar_proceso_pago_con_descuento,
    notificar_pago_efectivo,
    procesar_texto_reporte
)
from flujo_admin import (
    enviar_difusion_masiva,
    verificar_y_notificar_vencimientos_admin
)


def procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback=None, message_id=None, es_callback=False, callback_data=None, photo_file_id=None, enviar_foto_callback=None):
    """Cerebro enrutador industrial conectado con los submódulos de la arquitectura limpia."""
    
    str_chat_id = str(chat_id).strip()
    accion = callback_data if es_callback else texto.lower().strip()

    # -------------------------------------------------------------
    # CLIENTE: ACEPTAR TÉRMINOS Y NORMAS (BOTÓN OK)
    # -------------------------------------------------------------
    if es_callback and accion == "aceptar_terminos_ok":
        try:
            if message_id and editar_mensaje_callback:
                editar_mensaje_callback(
                    chat_id, 
                    message_id, 
                    "✅ *¡Normas aceptadas con éxito!*\n\nYa puedes disfrutar de tu servicio con total tranquilidad. Usa el menú principal cuando lo necesites.", 
                    get_main_menu_keyboard()
                )
            else:
                enviar_mensaje_callback(chat_id, "✅ ¡Gracias por confirmar! Disfruta tu contenido.", get_main_menu_keyboard())
        except Exception as e:
            print(f"Error al procesar OK de términos: {e}")
        return

    # -------------------------------------------------------------
    # CLIENTE: SOLICITAR REGISTRO MANUAL (PALABRA "registrar")
    # -------------------------------------------------------------
    elif accion == "registrar" or accion == "/registrar":
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        suscripciones_previas = obtener_suscripciones_por_id(chat_id)
        if suscripciones_previas:
            enviar_mensaje_callback(
                chat_id,
                "⚠️ Ya tienes una pantalla o suscripción registrada con este usuario en nuestro sistema.\nPuedes consultarla en el botón *📲 Ver mis datos / pantallas*.",
                get_main_menu_keyboard()
            )
            return

        nombre_completo_reg = f"{nombre} (@{username})" if username else nombre
        registros_pendientes_info[str_chat_id] = nombre_completo_reg

        mensaje_cliente_reg = (
            "📝 *¡SOLICITUD DE REGISTRO RECIBIDA!*\n\n"
            "Hemos tomado tus datos para asociar tu cuenta externa al sistema.\n\n"
            "🤖 *Guía rápida de cómo funciona nuestro bot:*\n"
            "1️⃣ **Ver mis datos:** Aquí podrás consultar tu correo, el perfil que te fue asignado y tu PIN de seguridad personal.\n"
            "2️⃣ **Solicitar Código:** Úsalo cuando tu pantalla o televisor te pida un código de acceso temporal (OTP) al iniciar sesión.\n"
            "3️⃣ **Renovar / Comprar:** Te permite mantener tu servicio activo o adquirir pantallas adicionales cuando lo necesites.\n\n"
            "⏳ *Estado actual:* El administrador está vinculando tu perfil en este momento. En cuanto finalice, podrás presionar **📲 Ver mis datos / pantallas** para ingresar."
        )
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje_cliente_reg, get_main_menu_keyboard())
        else:
            enviar_mensaje_callback(chat_id, mensaje_cliente_reg, get_main_menu_keyboard())

        if ADMIN_ID:
            texto_admin_reg = (
                "🚨 *¡NUEVA SOLICITUD DE REGISTRO MANUAL!* 🚨\n\n"
                f"• *Cliente:* {nombre_completo_reg}\n"
                f"• *Telegram ID:* `{str_chat_id}`\n\n"
                "🛠️ *Acción requerida:* Selecciona a continuación la cuenta que deseas asignarle de tu inventario:"
            )
            try:
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
                registros_cuentas = sheet_cuentas.get_all_records()

                botones_cuentas_reg = []
                for idx_c, c in enumerate(registros_cuentas, start=2):
                    srv_c = safe_get(c, "Servicio", "")
                    correo_c = safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", ""))
                    
                    botones_cuentas_reg.append([{
                        "text": f"📧 {srv_c} - {correo_c}",
                        "callback_data": f"admin_reg_cuenta_{str_chat_id}_{idx_c}"
                    }])
                
                if not botones_cuentas_reg:
                    enviar_mensaje_callback(int(ADMIN_ID), f"{texto_admin_reg}\n\n❌ *Aviso:* No hay cuentas cargadas en la pestaña 'Cuentas'.")
                else:
                    enviar_mensaje_callback(int(ADMIN_ID), texto_admin_reg, {"inline_keyboard": botones_cuentas_reg})
            except Exception as e:
                enviar_mensaje_callback(int(ADMIN_ID), f"⚠️ Error cargando cuentas para registro manual: {e}")
        return

    # -------------------------------------------------------------
    # ASISTENTE ADMIN: DIFUSIÓN Y MENSAJERÍA (GLOBAL O INDIVIDUAL)
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in asistente_difusion_admin and texto:
        sesion_dif = asistente_difusion_admin[str_chat_id]
        alcance = sesion_dif.get("alcance")
        tipo_plantilla = sesion_dif.get("tipo")
        parametro = texto.strip()

        if alcance == "individual":
            if "telegram_id_target" not in sesion_dif:
                termino_busqueda = parametro.lower()
                activos = obtener_clientes_activos_general()
                encontrados = []

                for idx, row_idx, act in activos:
                    nom_a = safe_get(act, "Nombre", "").lower()
                    tid_a = safe_get(act, "Telegram_ID", "").lower()
                    cta_a = safe_get(act, "Cuenta", "").lower()
                    srv_a = safe_get(act, "Servicio", "").lower()

                    if (termino_busqueda in nom_a or 
                        termino_busqueda in tid_a or 
                        termino_busqueda in cta_a or 
                        termino_busqueda in srv_a):
                        encontrados.append((tid_a, nom_a, srv_a, cta_a))

                if not encontrados:
                    enviar_mensaje_callback(
                        chat_id, 
                        f"❌ No se encontró ningún cliente que coincida con: *{texto}*.\n\nIntenta escribir otro nombre, correo o ID:",
                        {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_mensajeria"}]]}
                    )
                    return

                botones_resultados = []
                for tid_u, nom_u, srv_u, cta_u in encontrados:
                    botones_resultados.append([{
                        "text": f"👤 {nom_u} ({srv_u})", 
                        "callback_data": f"admin_enviar_a_{tid_u}_{tipo_plantilla}"
                    }])
                botones_resultados.append([{"text": "🔙 Cancelar", "callback_data": "admin_mensajeria"}])

                enviar_mensaje_callback(
                    chat_id, 
                    f"🔍 *Resultados de búsqueda para:* `{texto}`\n\nSelecciona el cliente al que deseas enviar el mensaje:",
                    {"inline_keyboard": botones_resultados}
                )
                return
            else:
                tid_destino = sesion_dif["telegram_id_target"]
                asistente_difusion_admin.pop(str_chat_id, None)

                if tipo_plantilla == "sospechoso":
                    mensaje_final = (
                        "⚠️ *AVISO IMPORTANTE DE SEGURIDAD Y TÉRMINOS* ⚠️\n\n"
                        f"Estimado usuario, hemos detectado la siguiente incidencia en su cuenta: *{parametro}*.\n\n"
                        "Recordamos que compartir credenciales o usar más dispositivos de los permitidos viola nuestros términos de servicio y puede ocasionar la suspensión definitiva. Por favor, regularice su situación a la brevedad."
                    )
                else:
                    mensaje_final = parametro

                try:
                    enviar_mensaje_callback(int(tid_destino), mensaje_final, get_main_menu_keyboard())
                    enviar_mensaje_callback(
                        chat_id,
                        f"✅ *¡Mensaje enviado con éxito al usuario!*\n\n• *Telegram ID:* `{tid_destino}`\n• *Contenido:* {mensaje_final}",
                        {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                    )
                except Exception as e:
                    enviar_mensaje_callback(
                        chat_id,
                        f"❌ No se pudo enviar el mensaje al ID `{tid_destino}`. Es posible que el usuario no tenga abierto el bot.\nError: {e}",
                        {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                    )
                return

        asistente_difusion_admin.pop(str_chat_id, None)

        if tipo_plantilla == "cupon":
            mensaje_final = (
                "🎟️ *¡NUEVO CUPÓN DE DESCUENTO DISPONIBLE!* 🎟️\n\n"
                f"Usa el código `{parametro.upper()}` al momento de renovar o comprar tu pantalla para disfrutar de un descuento especial.\n\n"
                "🤖 Entra a nuestro bot para canjearlo ahora mismo."
            )
        elif tipo_plantilla == "novedad":
            mensaje_final = (
                "📢 *¡NOVEDADES EN NUESTRO SERVICIO!* 📢\n\n"
                f"{parametro}\n\n"
                "✨ Gracias por confiar en nosotros."
            )
        else:
            mensaje_final = parametro

        enviados = enviar_difusion_masiva(mensaje_final, enviar_mensaje_callback)
        enviar_mensaje_callback(
            chat_id,
            f"✅ *Difusión masiva completada con éxito.*\n\nMensaje enviado a *{enviados}* clientes únicos.",
            {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
        )
        return

    if es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and accion.startswith("admin_enviar_a_"):
        try:
            partes = accion.split("_")
            tid_seleccionado = partes[3]
            tipo_plantilla = partes[4]

            if str_chat_id not in asistente_difusion_admin:
                asistente_difusion_admin[str_chat_id] = {}

            asistente_difusion_admin[str_chat_id]["alcance"] = "individual"
            asistente_difusion_admin[str_chat_id]["tipo"] = tipo_plantilla
            asistente_difusion_admin[str_chat_id]["telegram_id_target"] = tid_seleccionado

            if tipo_plantilla == "sospechoso":
                prompt_detalle = f"🚨 *USUARIO SELECCIONADO (ID: `{tid_seleccionado}`)*\n\nAhora escribe la **infracción o motivo específico** (Ej: `Uso simultáneo en más de 2 dispositivos`):"
            else:
                prompt_detalle = f"💬 *USUARIO SELECCIONADO (ID: `{tid_seleccionado}`)*\n\nAhora escribe el **mensaje personalizado** que deseas enviarle:"

            teclado_c = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_mensajeria"}]]}
            if editar_mensaje_callback and message_id:
                editar_mensaje_callback(chat_id, message_id, prompt_detalle, teclado_c)
            else:
                enviar_mensaje_callback(chat_id, prompt_detalle, teclado_c)
        except Exception as e:
            print(f"Error seleccionando usuario individual: {e}")
        return

    # -------------------------------------------------------------
    # CLIENTE: VALIDACIÓN DE CÓDIGO DE CUPÓN ESCRITO
    # -------------------------------------------------------------
    if not es_callback and str_chat_id in esperando_codigo_cupon_cliente and texto:
        datos_pago_temp = esperando_codigo_cupon_cliente.pop(str_chat_id)
        codigo_ingresado = texto.strip()

        if codigo_ingresado.lower() in ("no", "cancelar", "salir", "volver"):
            iniciar_proceso_pago_con_descuento(
                chat_id, str_chat_id, nombre, username, 
                datos_pago_temp["servicio_clave"], datos_pago_temp["tipo_operacion"], 
                datos_pago_temp["row_idx_target"], datos_pago_temp["message_id"], 
                enviar_mensaje_callback, editar_mensaje_callback, es_callback, cupon_aplicado=None
            )
            return

        valido, resultado = validar_y_consumir_cupon(codigo_ingresado)
        
        if not valido:
            esperando_codigo_cupon_cliente[str_chat_id] = datos_pago_temp
            enviar_mensaje_callback(
                chat_id,
                f"{resultado}\n\nPor favor, escribe otro código de cupón válido o escribe `cancelar` para volver a los datos de pago normales:",
                {
                    "inline_keyboard": [
                        [{"text": "🔙 Volver al Pago", "callback_data": f"volver_pago_sin_cupon_{datos_pago_temp['row_idx_target']}"}]
                    ]
                }
            )
            return

        iniciar_proceso_pago_con_descuento(
            chat_id, str_chat_id, nombre, username, 
            datos_pago_temp["servicio_clave"], datos_pago_temp["tipo_operacion"], 
            datos_pago_temp["row_idx_target"], datos_pago_temp["message_id"], 
            enviar_mensaje_callback, editar_mensaje_callback, es_callback, cupon_aplicado=resultado
        )
        return

    if es_callback and accion.startswith("volver_pago_sin_cupon_"):
        try:
            esperando_codigo_cupon_cliente.pop(str_chat_id, None)
            row_idx_target = int(accion.split("_")[-1])
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
            srv_nombre = safe_get(fila_obj, "Servicio", "Disney+").lower()
            srv_clave = "netflix" if "netflix" in srv_nombre else "disney"
            
            venc_previo = safe_get(fila_obj, "Vencimiento", "").strip()
            tipo_op = "renovacion" if (venc_previo and len(venc_previo) == 10 and ("-" in venc_previo or "/" in venc_previo)) else "nueva"

            iniciar_proceso_pago_con_descuento(
                chat_id, str_chat_id, nombre, username, srv_clave, tipo_op, 
                row_idx_target, message_id, enviar_mensaje_callback, editar_mensaje_callback, True, cupon_aplicado=None
            )
        except Exception as e:
            print(f"Error volviendo al pago: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # ASISTENTE ADMIN: CREACIÓN DE CUPONES PASO A PASO
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in asistente_cupon_admin and texto:
        sesion_c = asistente_cupon_admin[str_chat_id]
        paso_c = sesion_c.get("paso")

        if paso_c == "esperando_codigo":
            sesion_c["codigo"] = texto.strip().upper()
            sesion_c["paso"] = "esperando_tipo"
            enviar_mensaje_callback(
                chat_id,
                f"🎟️ *CUPÓN:* `{sesion_c['codigo']}`\n\n"
                "Paso 2: ¿Qué tipo de descuento deseas aplicar?",
                {
                    "inline_keyboard": [
                        [{"text": "💵 Descuento Fijo (USD)", "callback_data": "admin_cupontipo_Fijo"}],
                        [{"text": "📊 Descuento Porcentual (%)", "callback_data": "admin_cupontipo_Porcentaje"}],
                        [{"text": "🔙 Cancelar", "callback_data": "admin_gestionar_cupones"}]
                    ]
                }
            )
            return

        elif paso_c == "esperando_valor":
            try:
                valor = float(texto.strip())
                sesion_c["valor"] = valor
                
                if sesion_c["modo"] == "horas":
                    sesion_c["paso"] = "esperando_duracion_horas"
                    enviar_mensaje_callback(chat_id, "Paso 4: ¿Cuántas horas estará activo este cupón relámpago? (Ej: `3`, `12`, `24`):")
                else:
                    sesion_c["paso"] = "esperando_usos_maximos"
                    enviar_mensaje_callback(chat_id, "Paso 4: ¿Cuántos usos máximos tendrá este cupón? (Ej: `10`, `50`, `100`):")
            except ValueError:
                enviar_mensaje_callback(chat_id, "⚠️ Por favor ingresa un número válido (Ej: `1.00` o `10`):")
            return

        elif paso_c == "esperando_duracion_horas":
            try:
                horas = int(texto.strip())
                sesion_c["duracion_horas"] = horas
                sesion_c["usos_maximos"] = 999999
                guardar_nuevo_cupon_sheet(chat_id, sesion_c, enviar_mensaje_callback)
                asistente_cupon_admin.pop(str_chat_id, None)
            except ValueError:
                enviar_mensaje_callback(chat_id, "⚠️ Ingresa un número entero de horas válido (Ej: `3`):")
            return

        elif paso_c == "esperando_usos_maximos":
            try:
                usos = int(texto.strip())
                sesion_c["usos_maximos"] = usos
                sesion_c["duracion_horas"] = 0
                guardar_nuevo_cupon_sheet(chat_id, sesion_c, enviar_mensaje_callback)
                asistente_cupon_admin.pop(str_chat_id, None)
            except ValueError:
                enviar_mensaje_callback(chat_id, "⚠️ Ingresa un número entero de usos válido (Ej: `20`):")
            return

    if es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and accion.startswith("admin_cupontipo_") and str_chat_id in asistente_cupon_admin:
        tipo_desc = accion.split("_")[-1]
        sesion_c = asistente_cupon_admin[str_chat_id]
        sesion_c["tipo"] = tipo_desc
        sesion_c["paso"] = "esperando_valor"
        
        simbolo = "$" if tipo_desc == "Fijo" else "%"
        enviar_mensaje_callback(
            chat_id,
            f"🎟️ *CUPÓN:* `{sesion_c['codigo']}` ({tipo_desc})\n\n"
            f"Paso 3: Escribe el valor del descuento (Ej: `1.00` si es un dólar, o `15` si es 15{simbolo}):"
        )
        return

    # -------------------------------------------------------------
    # ASISTENTE ADMIN: CARGA PASO A PASO DE CUENTA Y PINS
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in asistente_cuenta_datos and texto:
        estado_actual = asistente_cuenta_datos[str_chat_id]
        paso = estado_actual.get("paso")

        if paso == "esperando_correo":
            estado_actual["correo"] = texto.strip()
            limite = estado_actual["limite"]
            estado_actual["paso"] = "esperando_pin"
            estado_actual["perfil_actual"] = 1
            estado_actual["pins"] = {}

            enviar_mensaje_callback(
                chat_id,
                f"🔑 *CONFIGURACIÓN DE PINS DE SEGURIDAD*\n\n"
                f"Servicio: *{estado_actual['servicio']}* ({limite} perfiles en total).\n\n"
                f"Por favor, escribe el PIN correspondiente al *Perfil 1* (Ej: `1234` o escribe `ninguno` si no usa):"
            )
            return

        elif paso == "esperando_pin":
            p_num = estado_actual["perfil_actual"]
            limite = estado_actual["limite"]
            pin_ingresado = texto.strip()
            
            estado_actual["pins"][f"Perfil {p_num}"] = pin_ingresado
            p_num += 1
            estado_actual["perfil_actual"] = p_num

            if p_num <= limite:
                enviar_mensaje_callback(
                    chat_id,
                    f"✅ PIN del Perfil {p_num - 1} guardado.\n\n"
                    f"Ahora escribe el PIN correspondiente al *Perfil {p_num}*:"
                )
                return
            else:
                srv = estado_actual["servicio"]
                correo = estado_actual["correo"]
                pins_dict = estado_actual["pins"]
                
                pins_formato_texto = " | ".join([f"{k}: {v}" for k, v in pins_dict.items()])

                try:
                    sheet_principal = conectar_sheets()
                    spreadsheet = sheet_principal.spreadsheet
                    
                    try:
                        sheet_cuentas = spreadsheet.worksheet("Cuentas")
                    except Exception:
                        sheet_cuentas = spreadsheet.add_worksheet(title="Cuentas", rows="1000", cols="7")
                        sheet_cuentas.append_row(["Servicio", "Correo", "Contraseña", "Capacidad Total", "Perfiles Ocupados", "Estado", "PINs de Perfiles"])

                    try:
                        fila_1 = sheet_cuentas.row_values(1)
                        if len(fila_1) < 7:
                            sheet_cuentas.update("A1:G1", [["Servicio", "Correo", "Contraseña", "Capacidad Total", "Perfiles Ocupados", "Estado", "PINs de Perfiles"]])
                    except Exception:
                        pass

                    sheet_cuentas.append_row([
                        srv,
                        correo,
                        "",
                        str(limite),
                        "0",
                        "Activa",
                        pins_formato_texto
                    ])

                    asistente_cuenta_datos.pop(str_chat_id)

                    enviar_mensaje_callback(
                        chat_id,
                        f"✅ *¡CUENTA MAESTRA Y PINS CONFIGURADOS CON ÉXITO!*\n\n"
                        f"• *Servicio:* {srv}\n"
                        f"• *Correo:* `{correo}`\n"
                        f"• *Capacidad:* {limite} perfiles\n"
                        f"• *PINs Registrados:* `{pins_formato_texto}`\n"
                        f"• *Estado:* Activa (0 ocupados)\n\n"
                        "El sistema ya está listo para entregar automáticamente el PIN correcto a cada cliente.",
                        {
                            "inline_keyboard": [
                                [{"text": "📦 Asignar Stock Pendiente Ahora", "callback_data": "admin_asignar_stock"}],
                                [{"text": "🔙 Volver a Gestión de Cuentas", "callback_data": "admin_gestionar_cuentas"}]
                            ]
                        }
                    )
                except Exception as e:
                    asistente_cuenta_datos.pop(str_chat_id)
                    print(f"Error guardando cuenta y pins: {e}")
                    enviar_mensaje_callback(chat_id, f"❌ Ocurrió un error al guardar en Google Sheets: {e}", {
                        "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                    })
                return

    # -------------------------------------------------------------
    # EDICIÓN MANUAL DE CLIENTES (TEXTO NUEVA FECHA)
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in asistente_edicion_admin and texto:
        sesion = asistente_edicion_admin[str_chat_id]
        paso_actual = sesion.get("paso")

        if paso_actual == "esperando_nueva_fecha":
            nueva_fecha = texto.strip()
            row_idx = sesion.get("row_idx")
            asistente_edicion_admin.pop(str_chat_id)

            try:
                sheet = conectar_sheets()
                sheet.update_cell(row_idx, 5, nueva_fecha)
                enviar_mensaje_callback(
                    chat_id,
                    f"✅ *¡Fecha de vencimiento actualizada con éxito!*\n\nLa fila {row_idx} ahora vence el: `{nueva_fecha}`",
                    {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                )
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al actualizar la fecha: {e}", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            return

        elif paso_actual == "esperando_fecha_registro_manual":
            fecha_vencimiento = texto.strip()
            tid_target = str(sesion.get("tid_target")).strip()
            correo_sel = sesion.get("correo")
            srv_sel = sesion.get("servicio")
            perfil_sel = sesion.get("perfil")
            asistente_edicion_admin.pop(str_chat_id)

            try:
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
                registros_cuentas = sheet_cuentas.get_all_records()

                nombre_cliente_encontrado = registros_pendientes_info.pop(tid_target, None)
                if not nombre_cliente_encontrado:
                    nombre_cliente_encontrado = f"Usuario ID {tid_target}"

                sheet_principal.append_row([
                    tid_target,
                    nombre_cliente_encontrado,
                    correo_sel,
                    perfil_sel,
                    fecha_vencimiento,
                    "Activo",
                    srv_sel
                ])

                for idx_c, c_row in enumerate(registros_cuentas, start=2):
                    correo_cta = safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", ""))
                    if correo_cta.lower() == correo_sel.lower():
                        try:
                            ocupados = int(safe_get(c_row, "Perfiles Ocupados", "0"))
                        except ValueError:
                            ocupados = 0
                        
                        nuevos_ocupados = ocupados + 1
                        sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)
                        
                        limite_max = 5 if "netflix" in srv_sel.lower() else 7
                        if nuevos_ocupados >= limite_max:
                            sheet_cuentas.update_cell(idx_c, 6, "Llena")
                        break

                enviar_mensaje_callback(
                    chat_id,
                    f"✅ *¡CLIENTE REGISTRADO MANUALMENTE CON ÉXITO!*\n\n"
                    f"• *Cliente:* {nombre_cliente_encontrado}\n"
                    f"• *Telegram ID:* `{tid_target}`\n"
                    f"• *Servicio:* {srv_sel} ({perfil_sel})\n"
                    f"• *Correo:* `{correo_sel}`\n"
                    f"• *Vencimiento:* `{fecha_vencimiento}`",
                    {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                )

                try:
                    msg_para_cliente = (
                        "🎉 *¡TU CUENTA HA SIDO REGISTRADA CON ÉXITO!*\n\n"
                        f"Ya puedes consultar los datos de tu acceso de *{srv_sel}* ({perfil_sel}) presionando el botón de abajo:"
                    )
                    enviar_mensaje_callback(
                        int(tid_target),
                        msg_para_cliente,
                        {
                            "inline_keyboard": [
                                [{"text": "📲 Ver mis datos / pantallas", "callback_data": "ver_datos"}],
                                [{"text": "🔑 Solicitar Código", "callback_data": "obtener_codigo"}]
                            ]
                        }
                    )
                except Exception as e:
                    print(f"No se pudo notificar al cliente registrado {tid_target}: {e}")

            except Exception as e:
                enviar_mensaje_callback(
                    chat_id,
                    f"❌ Error al registrar el cliente en la hoja: {e}",
                    {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                )
            return

    # -------------------------------------------------------------
    # BÚSQUEDA DE CLIENTE POR PARTE DEL ADMINISTRADOR
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in esperando_busqueda_admin and texto:
        esperando_busqueda_admin.pop(str_chat_id)
        termino_busqueda = texto.strip().lower()
        
        activos = obtener_clientes_activos_general()
        encontrados = []
        
        for idx, row_idx, act in activos:
            nom_a = safe_get(act, "Nombre", "").lower()
            tid_a = safe_get(act, "Telegram_ID", "").lower()
            cta_a = safe_get(act, "Cuenta", "").lower()
            srv_a = safe_get(act, "Servicio", "").lower()
            
            if (termino_busqueda in nom_a or 
                termino_busqueda in tid_a or 
                termino_busqueda in cta_a or 
                termino_busqueda in srv_a):
                encontrados.append((row_idx, act))

        if not encontrados:
            enviar_mensaje_callback(
                chat_id, 
                f"❌ No se encontró ningún cliente activo que coincida con: *{texto}*.", 
                {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
            )
            return

        enviar_mensaje_callback(chat_id, f"🔍 *Resultados de la búsqueda para:* `{texto}` ({len(encontrados)} encontrados)")
        
        for row_idx, act in encontrados:
            srv_a = safe_get(act, "Servicio", "Disney+")
            pnt_a = safe_get(act, "Pantalla", "Perfil 1")
            cta_a = safe_get(act, "Cuenta", "Cuenta")
            nom_a = safe_get(act, "Nombre", "Cliente")
            tid_a = safe_get(act, "Telegram_ID", "")
            fec_a = safe_get(act, "Vencimiento", "N/A")
            
            txt = (
                f"🟢 *Fila {row_idx}*\n"
                f"• *Cliente:* {nom_a}\n"
                f"• *Telegram ID:* `{tid_a}`\n"
                f"• *Servicio:* {srv_a} ({pnt_a})\n"
                f"• *Correo:* `{cta_a}`\n"
                f"• *Vence el:* `{fec_a}`"
            )
            teclado_gestion = {
                "inline_keyboard": [
                    [{"text": "✏️ Editar Datos Manualmente", "callback_data": f"admin_edit_menu_{row_idx}"}],
                    [{"text": "🚨 Expulsar y Liberar Cupo", "callback_data": f"admin_expulsar_{row_idx}"}]
                ]
            }
            enviar_mensaje_callback(chat_id, txt, teclado_gestion)
            
        enviar_mensaje_callback(chat_id, "Gestión de resultados finalizada.", {
            "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
        })
        return

    # -------------------------------------------------------------
    # CAPTURA DE TEXTO: NUEVO NOMBRE DE PERFIL PERSONALIZADO
    # -------------------------------------------------------------
    if not es_callback and str_chat_id in esperando_nuevo_nombre_perfil and texto:
        row_idx_perfil = esperando_nuevo_nombre_perfil.pop(str_chat_id)
        nuevo_nombre = texto.strip()

        if len(nuevo_nombre) > 20:
            enviar_mensaje_callback(chat_id, "⚠️ El nombre es demasiado largo (máximo 20 caracteres). Por favor escribe uno más corto:", get_back_keyboard())
            esperando_nuevo_nombre_perfil[str_chat_id] = row_idx_perfil
            return

        try:
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_perfil - 2] if (row_idx_perfil - 2) < len(registros) else {}
            
            servicio_perfil = safe_get(fila_obj, "Servicio", "Streaming")
            cuenta_perfil = safe_get(fila_obj, "Cuenta", "Correo")
            perfil_actual_texto = safe_get(fila_obj, "Pantalla", "Perfil 1")
            
            numero_base = "Perfil 1"
            for n in range(1, 8):
                if f"perfil {n}" in perfil_actual_texto.lower():
                    numero_base = f"Perfil {n}"
                    break

            nuevo_valor_celda = f"{numero_base} ({nuevo_nombre})"
            sheet.update_cell(row_idx_perfil, 4, nuevo_valor_celda)

            if ADMIN_ID:
                texto_admin = (
                    "✏️ *¡SOLICITUD DE CAMBIO DE NOMBRE DE PERFIL!* ✏️\n\n"
                    f"• *Cliente:* {nombre} (@{username})\n"
                    f"• *Telegram ID:* `{str_chat_id}`\n"
                    f"• *Servicio:* {servicio_perfil}\n"
                    f"• *Correo/Cuenta:* `{cuenta_perfil}`\n"
                    f"• *Perfil base:* {numero_base}\n"
                    f"• *Nuevo nombre solicitado:* `{nuevo_nombre}`\n\n"
                    "💡 *Acción:* Entra a la plataforma y cambia el nombre de este perfil para que coincida."
                )
                enviar_mensaje_callback(int(ADMIN_ID), texto_admin)

            enviar_mensaje_callback(
                chat_id,
                f"✅ *¡Nombre de perfil actualizado con éxito!*\n\n"
                f"Tu perfil ahora aparece como: *{nuevo_valor_celda}*.\n"
                "Hemos notificado al administrador para que aplique el cambio visual en la plataforma.",
                get_main_menu_keyboard()
            )
        except Exception as e:
            print(f"Error actualizando nombre de perfil: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al actualizar el nombre. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # CANCELAR Y VOLVER AL MENÚ (LIMPIA FILAS HUÉRFANAS O RESTAURA RENOVACIÓN)
    # -------------------------------------------------------------
    if accion == "menu_principal" or accion == "/start" or accion == "/menu":
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        for diccionario in [
            esperando_nuevo_nombre_perfil, esperando_busqueda_admin,
            asistente_cuenta_datos, asistente_edicion_admin, asistente_cupon_admin,
            esperando_codigo_cupon_cliente, detalles_pago_activos, asistente_difusion_admin
        ]:
            diccionario.pop(str_chat_id, None)
            
        texto_menu = (
            "🤖 *!Hola! Bienvenido a tu Streaming* 🎬\n\n"
            "¿Quieres adquirir tu primera pantalla? Toca *🛒 Comprar Pantalla* para ver los servicios disponibles.\n\n"
            "*Si ya eres cliente, aquí también puedes consultar tus pantallas, pedir códigos de acceso o renovar.*"
        )
        teclado = get_main_menu_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, teclado)
        else:
            enviar_mensaje_callback(chat_id, texto_menu, teclado)
        return

    # -------------------------------------------------------------
    # CAPTURA DE FOTO / COMPROBANTE ENVIADO POR EL CLIENTE
    # -------------------------------------------------------------
    if photo_file_id and str_chat_id in esperando_captura_pago:
        row_idx_pendiente = esperando_captura_pago.pop(str_chat_id)
        
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

        if ADMIN_ID and enviar_foto_callback:
            caption_admin = (
                "🔔 *¡NUEVO COMPROBANTE DE PAGO (FOTO)!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username})\n"
                f"• *Telegram ID:* `{str_chat_id}`\n"
                f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})\n"
                f"• *Cuenta/Detalle:* {cuenta_asociada}\n\n"
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
            enviar_foto_callback(int(ADMIN_ID), photo_file_id, caption_admin, teclado_admin)

        texto_confirmacion = (
            "✅ *¡Captura de pago recibida con éxito!*\n\n"
            "Se la hemos enviado al administrador. En breve tu pago será verificado y tu cuenta activada."
        )
        
        teclado_cliente = {
            "inline_keyboard": [
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        enviar_mensaje_callback(chat_id, texto_confirmacion, teclado_cliente)
        return

    if not es_callback and str_chat_id in esperando_captura_pago and texto and texto.lower().strip() not in ("efectivo", "/efectivo"):
        row_idx_pendiente = esperando_captura_pago.pop(str_chat_id)
        procesar_texto_reporte(chat_id, texto, nombre, username, enviar_mensaje_callback, str_chat_id, row_idx_pendiente, enviar_foto_callback, ADMIN_ID)
        return

    # -------------------------------------------------------------
    # PAGO EN EFECTIVO
    # -------------------------------------------------------------
    if accion == "efectivo" or accion == "/efectivo":
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        suscripciones = obtener_suscripciones_por_id(chat_id)
        botones_selector = []

        for sub in suscripciones:
            r_idx = sub.get("_row_index")
            srv = safe_get(sub, "Servicio", "Disney+")
            pnt = safe_get(sub, "Pantalla", "Perfil 1")
            cta = safe_get(sub, "Cuenta", "Cuenta")
            botones_selector.append([{"text": f"🔄 Renovar {srv} - {pnt} ({cta})", "callback_data": f"efectivo_fila_{r_idx}"}])

        from config_y_estado import PRECIO_DISNEY_USD, PRECIO_NETFLIX_USD
        botones_selector.append([{"text": f"➕ Nueva Pantalla Disney+ (${PRECIO_DISNEY_USD:.2f})", "callback_data": "efectivo_nuevo_disney"}])
        botones_selector.append([{"text": f"➕ Nueva Pantalla Netflix (${PRECIO_NETFLIX_USD:.2f})", "callback_data": "efectivo_nuevo_netflix"}])
        botones_selector.append([{"text": "🔙 Cancelar y Volver", "callback_data": "menu_principal"}])

        mensaje = (
            "💵 *PAGO EN EFECTIVO*\n\n"
            "Selecciona qué pantalla vas a renovar o si deseas adquirir una pantalla adicional nueva:"
        )
        enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("efectivo_fila_"):
        try:
            row_idx_elegido = int(accion.split("_")[-1])
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_elegido, "Renovación", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback, ADMIN_ID)
        except Exception as e:
            print(f"Error en efectivo fila: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    elif accion.startswith("efectivo_nuevo_"):
        try:
            servicio_elegido = "Netflix" if "netflix" in accion else "Disney+"
            nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido, enviar_mensaje_callback)
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, nueva_fila_idx, "Pantalla Nueva", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback, ADMIN_ID)
        except Exception as e:
            print(f"Error en efectivo nuevo: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # PANEL DE ADMINISTRADOR Y GESTIÓN GENERAL
    # -------------------------------------------------------------
    if accion == "/admin" or accion == "admin_volver":
        for diccionario in [
            esperando_captura_pago, esperando_busqueda_admin, asistente_cuenta_datos,
            asistente_edicion_admin, asistente_cupon_admin, esperando_codigo_cupon_cliente,
            detalles_pago_activos, asistente_difusion_admin
        ]:
            diccionario.pop(str_chat_id, None)

        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            teclado = {
                "inline_keyboard": [
                    [{"text": "📊 Resumen General del Negocio", "callback_data": "admin_resumen_negocio"}],
                    [{"text": "📋 Ver Pagos Pendientes", "callback_data": "admin_ver_pendientes"}],
                    [{"text": "🔑 Crear y Gestionar Cuentas (Stock)", "callback_data": "admin_gestionar_cuentas"}],
                    [{"text": "🎟️ Crear y Gestionar Cupones", "callback_data": "admin_gestionar_cupones"}],
                    [{"text": "📢 Difusión y Mensajería (CRM)", "callback_data": "admin_mensajeria"}],
                    [{"text": "🔍 Buscar y Gestionar Cliente Activo", "callback_data": "admin_pedir_busqueda"}],
                    [{"text": "🗑️ Gestionar / Eliminar Vencidos", "callback_data": "admin_ver_vencidos"}],
                    [{"text": "📦 Asignar Stock Pendiente", "callback_data": "admin_asignar_stock"}],
                    [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
                ]
            }
            if es_callback and editar_mensaje_callback and accion == "admin_volver":
                editar_mensaje_callback(chat_id, message_id, reporte, teclado)
            else:
                enviar_mensaje_callback(chat_id, reporte, teclado)
        else:
            enviar_mensaje_callback(chat_id, "⛔ No tienes permisos para acceder a este panel.", get_main_menu_keyboard())
        return

    # -------------------------------------------------------------
    # CRM & MENSAJERÍA ADMIN
    # -------------------------------------------------------------
    elif accion == "admin_mensajeria":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            asistente_difusion_admin.pop(str_chat_id, None)
            texto_msg = (
                "📢 *CENTRO DE MENSAJERÍA Y COMUNICACIÓN (CRM)*\n\n"
                "¿Qué tipo de gestión de mensajes deseas realizar?"
            )
            teclado_msg = {
                "inline_keyboard": [
                    [{"text": "🌐 Difusión Masiva (A todos los usuarios)", "callback_data": "admin_alcance_global"}],
                    [{"text": "👤 Contactar / Reportar a un Usuario Específico", "callback_data": "admin_alcance_individual"}],
                    [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_msg, teclado_msg)
            else:
                enviar_mensaje_callback(chat_id, texto_msg, teclado_msg)
        return

    elif accion == "admin_alcance_global":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            texto_g = (
                "🌐 *DIFUSIÓN MASIVA (GLOBAL)*\n\n"
                "Selecciona la plantilla profesional que deseas enviar a toda la base de clientes:"
            )
            teclado_g = {
                "inline_keyboard": [
                    [{"text": "🎟️ Anuncio de Cupón Relámpago", "callback_data": "admin_tipo_global_cupon"}],
                    [{"text": "✨ Novedad o Actualización General", "callback_data": "admin_tipo_global_novedad"}],
                    [{"text": "🔙 Volver", "callback_data": "admin_mensajeria"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_g, teclado_g)
            else:
                enviar_mensaje_callback(chat_id, texto_g, teclado_g)
        return

    elif accion == "admin_alcance_individual":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            texto_i = (
                "👤 *MENSAJERÍA INDIVIDUAL / PRIVADA*\n\n"
                "Selecciona el tipo de aviso que deseas enviar a ese usuario específico:"
            )
            teclado_i = {
                "inline_keyboard": [
                    [{"text": "⚠️ Aviso por Usuario Sospechoso / Infracción", "callback_data": "admin_tipo_ind_sospechoso"}],
                    [{"text": "💬 Mensaje Personalizado / Soporte Directo", "callback_data": "admin_tipo_ind_libre"}],
                    [{"text": "🔙 Volver", "callback_data": "admin_mensajeria"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_i, teclado_i)
            else:
                enviar_mensaje_callback(chat_id, texto_i, teclado_i)
        return

    elif accion.startswith("admin_tipo_global_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            tipo = accion.split("_")[-1]
            asistente_difusion_admin[str_chat_id] = {"alcance": "global", "tipo": tipo}

            instruccion = (
                "🎟️ *DIFUSIÓN GLOBAL: CUPÓN*\n\nEscribe únicamente el **código del cupón** (Ej: `VIP2026`):"
                if tipo == "cupon" else
                "✨ *DIFUSIÓN GLOBAL: NOVEDAD*\n\nEscribe el **texto del anuncio** que deseas enviar masivamente:"
            )
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_alcance_global"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, instruccion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, instruccion, teclado_canc)
        return

    elif accion.startswith("admin_tipo_ind_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            tipo = accion.split("_")[-1]
            asistente_difusion_admin[str_chat_id] = {"alcance": "individual", "tipo": tipo}

            instruccion = (
                "⚠️ *AVISO A USUARIO SOSPECHOSO*\n\nEscribe el **nombre**, **usuario (@)**, **ID** o **correo** del cliente:"
                if tipo == "sospechoso" else
                "💬 *MENSAJE DIRECTO A USUARIO*\n\nEscribe el **nombre**, **usuario (@)**, **ID** o **correo** del cliente:"
            )
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_alcance_individual"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, instruccion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, instruccion, teclado_canc)
        return

    elif accion == "admin_gestionar_cupones":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            asistente_cupon_admin.pop(str_chat_id, None)
            texto_gc = (
                "🎟️ *GESTIÓN DE CUPONES DE DESCUENTO*\n\n"
                "Aquí puedes crear nuevos códigos promocionales o administrar los existentes:"
            )
            teclado_gc = {
                "inline_keyboard": [
                    [{"text": "➕ Crear Nuevo Cupón", "callback_data": "admin_crear_cupon"}],
                    [{"text": "📋 Ver / Listar Cupones Existentes", "callback_data": "admin_ver_cupones"}],
                    [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_gc, teclado_gc)
            else:
                enviar_mensaje_callback(chat_id, texto_gc, teclado_gc)
        return

    elif accion == "admin_ver_cupones":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                try:
                    sheet_cupones = spreadsheet.worksheet("Cupones")
                    registros = sheet_cupones.get_all_records()
                except Exception:
                    registros = []

                if not registros:
                    teclado_vacio = {"inline_keyboard": [
                        [{"text": "➕ Crear Nuevo Cupón", "callback_data": "admin_crear_cupon"}],
                        [{"text": "🔙 Volver", "callback_data": "admin_gestionar_cupones"}]
                    ]}
                    if es_callback and editar_mensaje_callback:
                        editar_mensaje_callback(chat_id, message_id, "🎟️ No hay cupones registrados en Google Sheets.", teclado_vacio)
                    else:
                        enviar_mensaje_callback(chat_id, "🎟️ No hay cupones registrados en Google Sheets.", teclado_vacio)
                    return

                enviar_mensaje_callback(chat_id, f"📋 *LISTA DE CUPONES REGISTRADOS* ({len(registros)} en total):")

                for idx, row in enumerate(registros, start=2):
                    codigo = safe_get(row, "Codigo", "S/C")
                    tipo = safe_get(row, "Tipo", "Fijo")
                    valor = safe_get(row, "Valor", "0")
                    duracion = safe_get(row, "Duracion (Horas)", "0")
                    usos_max = safe_get(row, "Usos Maximos", "0")
                    veces_usado = safe_get(row, "Veces Usado", "0")
                    estado = safe_get(row, "Estado", "Activo")

                    simbolo = "$" if tipo.lower() == "fijo" else "%"
                    limite_txt = f"{duracion}h relámpago" if int(duracion) > 0 else f"{usos_max} usos máx"

                    txt_c = (
                        f"🎟️ *Cupón:* `{codigo}`\n"
                        f"• *Descuento:* {valor}{simbolo} ({tipo})\n"
                        f"• *Límite:* {limite_txt}\n"
                        f"• *Usados:* `{veces_usado}` veces\n"
                        f"• *Estado:* *{estado}*"
                    )
                    teclado_estado = {
                        "inline_keyboard": [
                            [{"text": "🗑️ Eliminar / Desactivar Cupón", "callback_data": f"admin_delcupun_{idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt_c, teclado_estado)

                enviar_mensaje_callback(chat_id, "Gestión de listado finalizada.", {
                    "inline_keyboard": [
                        [{"text": "➕ Crear Otro Cupón", "callback_data": "admin_crear_cupon"}],
                        [{"text": "🔙 Volver a Gestión de Cupones", "callback_data": "admin_gestionar_cupones"}]
                    ]
                })
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al listar cupones: {e}", get_back_keyboard())
        return

    elif accion.startswith("admin_delcupun_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_cupon = int(accion.split("_")[-1])
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                sheet_cupones = spreadsheet.worksheet("Cupones")
                sheet_cupones.delete_rows(row_idx_cupon)
                
                texto_editado = "🗑️ *Cupón eliminado exitosamente de la base de datos.*"
                teclado_fin = {
                    "inline_keyboard": [
                        [{"text": "📋 Ver Cupones Restantes", "callback_data": "admin_ver_cupones"}],
                        [{"text": "🔙 Volver a Gestión", "callback_data": "admin_gestionar_cupones"}]
                    ]
                }
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, texto_editado, teclado_fin)
                else:
                    enviar_mensaje_callback(chat_id, texto_editado, teclado_fin)
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al eliminar el cupón: {e}", get_back_keyboard())
        return

    elif accion == "admin_crear_cupon":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            texto_c = (
                "🎟️ *CREAR NUEVO CUPÓN DE DESCUENTO*\n\n"
                "¿Cómo deseas limitar este cupón?"
            )
            teclado_modo = {
                "inline_keyboard": [
                    [{"text": "⏱️ Por Horas (Cupón Relámpago)", "callback_data": "admin_cuponmodo_horas"}],
                    [{"text": "🔢 Por Cantidad de Usos", "callback_data": "admin_cuponmodo_usos"}],
                    [{"text": "🔙 Volver", "callback_data": "admin_gestionar_cupones"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_c, teclado_modo)
            else:
                enviar_mensaje_callback(chat_id, texto_c, teclado_modo)
        return

    elif accion.startswith("admin_cuponmodo_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            modo = accion.split("_")[-1]
            asistente_cupon_admin[str_chat_id] = {
                "modo": modo,
                "paso": "esperando_codigo"
            }
            
            modo_texto = "por Horas (Relámpago)" if modo == "horas" else "por Cantidad de Usos"
            texto_p1 = (
                f"🎟️ *NUEVO CUPÓN ({modo_texto})*\n\n"
                "Paso 1: Escribe el código del cupón en mayúsculas (Ej: `FLASH3`, `VIP2026`):"
            )
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_gestionar_cupones"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_p1, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, texto_p1, teclado_canc)
        return

    # -------------------------------------------------------------
    # GESTIÓN DE CUENTAS MAESTRAS (STOCK)
    # -------------------------------------------------------------
    elif accion == "admin_gestionar_cuentas":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            asistente_cuenta_datos.pop(str_chat_id, None)
            texto_gcta = (
                "🔑 *GESTIÓN DE CUENTAS MAESTRAS (STOCK)*\n\n"
                "Aquí puedes cargar nuevas cuentas con sus PINs o ver las existentes en tu inventario:"
            )
            teclado_gcta = {
                "inline_keyboard": [
                    [{"text": "➕ Cargar Cuenta y PINs (Stock)", "callback_data": "admin_cargar_cuenta"}],
                    [{"text": "📋 Ver / Listar Cuentas Existentes", "callback_data": "admin_ver_cuentas"}],
                    [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, texto_gcta, teclado_gcta)
            else:
                enviar_mensaje_callback(chat_id, texto_gcta, teclado_gcta)
        return

    elif accion == "admin_ver_cuentas":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                try:
                    sheet_cuentas = spreadsheet.worksheet("Cuentas")
                    registros_c = sheet_cuentas.get_all_records()
                except Exception:
                    registros_c = []

                if not registros_c:
                    teclado_vacio_c = {"inline_keyboard": [
                        [{"text": "➕ Cargar Cuenta", "callback_data": "admin_cargar_cuenta"}],
                        [{"text": "🔙 Volver", "callback_data": "admin_gestionar_cuentas"}]
                    ]}
                    if es_callback and editar_mensaje_callback:
                        editar_mensaje_callback(chat_id, message_id, "🔑 No hay cuentas maestras registradas en Google Sheets.", teclado_vacio_c)
                    else:
                        enviar_mensaje_callback(chat_id, "🔑 No hay cuentas maestras registradas en Google Sheets.", teclado_vacio_c)
                    return

                enviar_mensaje_callback(chat_id, f"📋 *LISTA DE CUENTAS MAESTRAS* ({len(registros_c)} en total):")

                for idx, row in enumerate(registros_c, start=2):
                    srv = safe_get(row, "Servicio", "Disney+")
                    correo = safe_get(row, "Correo (Usuario)", safe_get(row, "Correo", "S/C"))
                    cap = safe_get(row, "Capacidad Total", "5")
                    ocu = safe_get(row, "Perfiles Ocupados", "0")
                    est = safe_get(row, "Estado", "Activa")
                    pins = safe_get(row, "PINs de Perfiles", "S/PIN")

                    txt_cta = (
                        f"📺 *Servicio:* {srv}\n"
                        f"• *Correo:* `{correo}`\n"
                        f"• *Ocupados:* `{ocu} / {cap}` perfiles\n"
                        f"• *Estado:* *{est}*\n"
                        f"• *PINs:* `{pins}`"
                    )
                    teclado_cta_op = {
                        "inline_keyboard": [
                            [{"text": "🗑️ Eliminar Cuenta Maestra", "callback_data": f"admin_delcuenta_{idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt_cta, teclado_cta_op)

                enviar_mensaje_callback(chat_id, "Gestión de cuentas finalizada.", {
                    "inline_keyboard": [
                        [{"text": "➕ Cargar Otra Cuenta", "callback_data": "admin_cargar_cuenta"}],
                        [{"text": "🔙 Volver a Gestión de Cuentas", "callback_data": "admin_gestionar_cuentas"}]
                    ]
                })
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al listar cuentas: {e}", get_back_keyboard())
        return

    elif accion.startswith("admin_delcuenta_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_cuenta = int(accion.split("_")[-1])
                sheet_principal = conectar_sheets()
                spreadsheet = sheet_principal.spreadsheet
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
                sheet_cuentas.delete_rows(row_idx_cuenta)
                
                texto_editado = "🗑️ *Cuenta maestra eliminada exitosamente del inventario.*"
                teclado_fin = {
                    "inline_keyboard": [
                        [{"text": "📋 Ver Cuentas Restantes", "callback_data": "admin_ver_cuentas"}],
                        [{"text": "🔙 Volver a Gestión", "callback_data": "admin_gestionar_cuentas"}]
                    ]
                }
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, texto_editado, teclado_fin)
                else:
                    enviar_mensaje_callback(chat_id, texto_editado, teclado_fin)
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al eliminar la cuenta: {e}", get_back_keyboard())
        return

    elif accion == "admin_cargar_cuenta":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            mensaje_carga = "➕ *CARGAR NUEVA CUENTA Y PINS*\n\nSelecciona a qué plataforma pertenece la cuenta:"
            teclado_servicios = {
                "inline_keyboard": [
                    [{"text": "📺 Netflix (5 Perfiles)", "callback_data": "admin_cuenta_netflix"}],
                    [{"text": "📺 Disney+ (7 Perfiles)", "callback_data": "admin_cuenta_disney"}],
                    [{"text": "🔙 Volver", "callback_data": "admin_gestionar_cuentas"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_carga, teclado_servicios)
            else:
                enviar_mensaje_callback(chat_id, mensaje_carga, teclado_servicios)
        return

    elif accion == "admin_cuenta_netflix" or accion == "admin_cuenta_disney":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            es_netflix = "netflix" in accion
            servicio_elegido = "Netflix" if es_netflix else "Disney+"
            limite_perfiles = 5 if es_netflix else 7

            asistente_cuenta_datos[str_chat_id] = {
                "servicio": servicio_elegido,
                "limite": limite_perfiles,
                "paso": "esperando_correo"
            }

            mensaje_peticion = (
                f"➕ *NUEVA CUENTA DE {servicio_elegido.upper()}*\n\n"
                "Paso 1/2: Escribe o pega el **correo y contraseña** de la cuenta\n(Ej: `correo@gmail.com : tucontraseña`):"
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "admin_gestionar_cuentas"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        return

    # -------------------------------------------------------------
    # APROBACIONES, PENDIENTES Y EXPULSIONES ADMIN
    # -------------------------------------------------------------
    elif accion == "admin_resumen_negocio":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resumen_detallado = generar_resumen_completo_negocio()
            teclado_resumen = {
                "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, resumen_detallado, teclado_resumen)
            else:
                enviar_mensaje_callback(chat_id, resumen_detallado, teclado_resumen)
        return

    elif accion == "admin_pedir_busqueda":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            esperando_busqueda_admin[str_chat_id] = True
            mensaje_busqueda = (
                "🔍 *BUSCAR CLIENTE ACTIVO*\n\n"
                "Escribe a continuación el **nombre**, **usuario (@)**, **ID de Telegram** o **correo**:"
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "admin_volver"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_busqueda, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_busqueda, teclado_canc)
        return

    elif accion == "admin_asignar_stock":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resultado_asignacion = procesar_asignacion_stock_masivo(enviar_mensaje_callback)
            enviar_mensaje_callback(chat_id, resultado_asignacion, {
                "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
            })
        return

    elif accion == "admin_ver_pendientes":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            pendientes = obtener_clientes_pendientes()
            if not pendientes:
                enviar_mensaje_callback(chat_id, "✅ No hay pagos pendientes en este momento.", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            else:
                for idx, row_idx, p in pendientes:
                    srv_p = safe_get(p, "Servicio", "Disney+")
                    pnt_p = safe_get(p, "Pantalla", "Perfil 1")
                    txt = (
                        f"🟡 *Pago Pendiente #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {safe_get(p, 'Nombre')}\n"
                        f"• *Telegram ID:* `{safe_get(p, 'Telegram_ID')}`\n"
                        f"• *Servicio:* {srv_p} ({pnt_p})\n"
                        f"• *Cuenta/Correo:* {safe_get(p, 'Cuenta')}"
                    )
                    teclado_aprobar = {
                        "inline_keyboard": [
                            [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx}_digital"}],
                            [{"text": "❌ Rechazar Pago", "callback_data": f"rechazar_{row_idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_aprobar)
        return

    elif accion.startswith("admin_expulsar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_expulsar = int(accion.split("_")[-1])
                sheet_principal = conectar_sheets()
                registros = sheet_principal.get_all_records()
                fila_obj = registros[row_idx_expulsar - 2] if (row_idx_expulsar - 2) < len(registros) else {}
                tid_cliente = safe_get(fila_obj, "Telegram_ID", "")
                srv_exp = safe_get(fila_obj, "Servicio", "Streaming")
                pnt_exp = safe_get(fila_obj, "Pantalla", "Perfil")

                resultado_expulsion = liberar_y_eliminar_fila_suscripcion(row_idx_expulsar)
                
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                enviar_mensaje_callback(chat_id, f"🚨 {resultado_expulsion}", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })

                if tid_cliente:
                    try:
                        msg_usuario = (
                            "⚠️ *AVISO DE SUSPENSIÓN*\n\n"
                            f"Tu suscripción a *{srv_exp}* ({pnt_exp}) ha sido finalizada por el administrador.\n"
                            "Si consideras que se trata de un error, comunícate con soporte."
                        )
                        enviar_mensaje_callback(int(tid_cliente), msg_usuario, get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al expulsar el usuario: {e}", get_back_keyboard())
        return

    elif accion == "admin_ver_vencidos":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            vencidos = obtener_suscripciones_vencidas()
            if not vencidos:
                enviar_mensaje_callback(chat_id, "✅ No hay pantallas vencidas para depurar.", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            else:
                for idx, row_idx, v in vencidos:
                    srv_v = safe_get(v, "Servicio", "Disney+")
                    pnt_v = safe_get(v, "Pantalla", "Perfil 1")
                    cta_v = safe_get(v, "Cuenta", "Cuenta")
                    fec_v = safe_get(v, "Vencimiento", "N/A")
                    txt = (
                        f"🔴 *Pantalla Vencida #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {safe_get(v, 'Nombre')}\n"
                        f"• *Servicio:* {srv_v} ({pnt_v})\n"
                        f"• *Correo:* `{cta_v}`\n"
                        f"• *Venció el:* `{fec_v}`"
                    )
                    teclado_borrar = {
                        "inline_keyboard": [
                            [{"text": "🗑️ Liberar Perfil y Borrar Fila", "callback_data": f"admin_liberar_{row_idx}"}],
                            [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_borrar)
        return

    elif accion.startswith("admin_liberar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_a_borrar = int(accion.split("_")[-1])
                resultado_liberacion = liberar_y_eliminar_fila_suscripcion(row_idx_a_borrar)
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)
                enviar_mensaje_callback(chat_id, resultado_liberacion, {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al liberar la fila: {e}", get_back_keyboard())
        return

    elif accion.startswith("aprobar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                partes_ap = accion.split("_")
                row_idx = int(partes_ap[1])
                es_efectivo = (len(partes_ap) > 2 and partes_ap[2].strip() == "efectivo")
                metodo_pago = "Efectivo" if es_efectivo else "Pago Móvil / Digital"

                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                exito, tid_cliente, ya_estaba_activa, nombre_cliente, srv_aprobado, perfil_asignado, tipo_operacion, cuenta_fila = aprobar_suscripcion_sheet(row_idx)

                if ya_estaba_activa:
                    texto_res = f"ℹ️ La suscripción de la fila {row_idx} ya había sido aprobada previamente."
                elif exito:
                    from config_y_estado import PRECIO_NETFLIX_USD, PRECIO_DISNEY_USD
                    monto_venta = PRECIO_NETFLIX_USD if "netflix" in str(srv_aprobado).lower() else PRECIO_DISNEY_USD
                    registrar_venta_en_historial(
                        nombre_cliente, tid_cliente, srv_aprobado, perfil_asignado,
                        monto_venta, tipo_operacion, metodo_pago
                    )
                    texto_res = (
                        f"✅ *¡PAGO APROBADO CON ÉXITO!* (Fila {row_idx})\n\n"
                        f"• *Cliente:* {nombre_cliente}\n"
                        f"• *Servicio:* {srv_aprobado} ({perfil_asignado})\n"
                        f"• *Cuenta:* `{cuenta_fila}`\n"
                        f"• *Tipo:* {tipo_operacion}\n"
                        f"• *Método:* {metodo_pago}"
                    )
                    if tid_cliente:
                        try:
                            pin_entregado = obtener_pin_asignado_cliente(cuenta_fila, perfil_asignado)
                            if "pendiente de stock" in str(cuenta_fila).lower():
                                msg_cliente = (
                                    "🎉 *¡Tu pago ha sido verificado y aprobado!*\n\n"
                                    f"Tu suscripción de *{srv_aprobado}* ({perfil_asignado}) está **Activa** con **prioridad #1**.\n"
                                    "⏳ Estamos preparando tu cuenta; te notificaremos en cuanto tu correo quede asignado."
                                )
                                teclado_cliente = get_main_menu_keyboard()
                            else:
                                if tipo_operacion == "Pantalla Nueva":
                                    aviso_tv_especial = (
                                        "\n\n📺 *Nota para Smart TVs (como Damasco u otros):*\n"
                                        "Si tu televisor no muestra código numérico de 4 dígitos y te pide aprobar por correo, "
                                        "avísanos por soporte para ayudarte a confirmarlo de inmediato."
                                    )
                                    msg_cliente = (
                                        "🎉 *¡Tu pago ha sido verificado y aprobado!*\n\n"
                                        f"Tu servicio de *{srv_aprobado}* ({perfil_asignado}) ya se encuentra *Activo*.\n"
                                        f"• *Correo:* `{cuenta_fila}`\n"
                                        f"• *PIN de seguridad:* `{pin_entregado}` 🔒"
                                        f"{aviso_tv_especial}\n\n"
                                        "📜 *NORMAS IMPORTANTES DE USO:*\n"
                                        "1️⃣ Tu pantalla es para **1 solo dispositivo** en simultáneo.\n"
                                        "2️⃣ Usa únicamente tu PIN asignado; está prohibido modificar perfiles ajenos.\n"
                                        "3️⃣ No compartas tus datos de acceso.\n\n"
                                        "Presiona el botón de abajo para confirmar que has leído y aceptas las normas:"
                                    )
                                    teclado_cliente = {
                                        "inline_keyboard": [
                                            [{"text": "✅ Entendido y Aceptado (OK)", "callback_data": "aceptar_terminos_ok"}],
                                            [{"text": "📲 Ver mis datos", "callback_data": "ver_datos"}]
                                        ]
                                    }
                                else:
                                    msg_cliente = (
                                        "🎉 *¡Renovación exitosa por 30 días más!*\n\n"
                                        f"Tu servicio de *{srv_aprobado}* ({perfil_asignado}) ha sido renovado.\n"
                                        f"• *PIN de seguridad:* `{pin_entregado}` 🔒\n\n"
                                        "💡 *Recuerda:* Mantén el uso de un solo dispositivo para evitar bloqueos en tu pantalla.\n\n"
                                        "Presiona OK para confirmar:"
                                    )
                                    teclado_cliente = {
                                        "inline_keyboard": [
                                            [{"text": "✅ OK, entendido", "callback_data": "aceptar_terminos_ok"}]
                                        ]
                                    }

                            enviar_mensaje_callback(int(tid_cliente), msg_cliente, teclado_cliente)
                        except Exception as e:
                            print(f"Error notificando al cliente: {e}")
                else:
                    texto_res = f"❌ Error al actualizar la hoja de cálculo para la fila {row_idx}."

                teclado_vol = {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, texto_res, teclado_vol)
                else:
                    enviar_mensaje_callback(chat_id, texto_res, teclado_vol)
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    elif accion.startswith("rechazar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx = int(accion.split("_")[1])
                sheet_principal = conectar_sheets()
                registros = sheet_principal.get_all_records()
                fila_obj = registros[row_idx - 2] if (row_idx - 2) < len(registros) else {}
                tid_cliente = safe_get(fila_obj, "Telegram_ID", "")
                srv_rechazado = safe_get(fila_obj, "Servicio", "Streaming")

                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                resultado_rechazo = rechazar_pago_seguro(row_idx)

                texto_res = f"❌ *Pago Rechazado*\n\n{resultado_rechazo}"
                teclado_vol = {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
                
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, texto_res, teclado_vol)
                else:
                    enviar_mensaje_callback(chat_id, texto_res, teclado_vol)

                if tid_cliente:
                    try:
                        msg_rechazo = (
                            "⚠️ *COMPROBANTE RECHAZADO*\n\n"
                            f"Tu comprobante de pago para *{srv_rechazado}* no pudo ser verificado (puede ser ilegible, incorrecto o duplicado).\n\n"
                            "Tu suscripción sigue intacta. Por favor, verifica los datos e intenta reportar tu pago nuevamente."
                        )
                        enviar_mensaje_callback(int(tid_cliente), msg_rechazo, get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al rechazar: {e}", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # MENÚ PRINCIPAL Y CLIENTE (VER DATOS, OTP, RENOVACIONES, ETC.)
    # -------------------------------------------------------------
    elif accion == "ver_datos" or "cuenta" in accion:
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        suscripciones = obtener_suscripciones_por_id(chat_id)
        if not suscripciones:
            mensaje = "⚠️ Aún no tienes ninguna pantalla registrada con este ID de Telegram.\n\nSelecciona *🛒 Comprar Pantalla* o *🔄 Renovar* en el menú para comenzar."
            teclado = get_back_keyboard()
        else:
            total = len(suscripciones)
            encabezado = f"📋 *TUS DATOS DE SUSCRIPCIÓN ({total} {'pantalla' if total == 1 else 'pantallas'})*\n\n"
            bloques = []
            tiene_por_renovar = False

            for idx, sub in enumerate(suscripciones, start=1):
                servicio = safe_get(sub, "Servicio", "Disney+")
                correo_raw = safe_get(sub, "Cuenta", "Por Asignar")
                pantalla = safe_get(sub, "Pantalla", "Perfil 1")
                vencimiento = safe_get(sub, "Vencimiento", "Sin fecha")
                estado = safe_get(sub, "Estado", "Pendiente Pago")
                
                pin_perfil = obtener_pin_asignado_cliente(correo_raw, pantalla)

                if "pendiente de stock" in correo_raw.lower():
                    correo_mostrar = "⏳ En asignación prioritaria (Stock en curso)"
                    pin_mostrar = "Pendiente de asignar"
                else:
                    correo_mostrar = f"`{correo_raw}`"
                    pin_mostrar = f"`{pin_perfil}`"

                alerta_vencimiento = verificar_alerta_vencimiento(vencimiento, estado)
                if "Vencida" in alerta_vencimiento or "Vence" in alerta_vencimiento or estado.lower() != "activo":
                    tiene_por_renovar = True

                bloques.append(
                    f"🔹 *Suscripción #{idx} ({servicio})*\n"
                    f"• *Correo:* {correo_mostrar}\n"
                    f"• *Perfil:* {pantalla}\n"
                    f"• *PIN de seguridad:* {pin_mostrar} 🔒\n"
                    f"• *Vencimiento:* {vencimiento} {alerta_vencimiento}\n"
                    f"• *Estado:* {estado}"
                )

            mensaje = encabezado + "\n\n".join(bloques)
            teclado = get_datos_keyboard(mostrar_renovar=tiene_por_renovar, suscripciones=suscripciones)
            
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    elif accion == "menu_renombrar":
        suscripciones_activas = [
            s for s in obtener_suscripciones_por_id(chat_id)
            if safe_get(s, "Estado", "").lower() == "activo"
            and "pendiente" not in safe_get(s, "Cuenta", "").lower()
        ]

        if not suscripciones_activas:
            enviar_mensaje_callback(chat_id, "⚠️ No tienes pantallas activas disponibles para renombrar.", get_back_keyboard())
            return

        botones_selector = []
        for sub in suscripciones_activas:
            r_idx = sub.get("_row_index")
            srv = safe_get(sub, "Servicio", "Disney+")
            pnt = safe_get(sub, "Pantalla", "Perfil 1")
            cta = safe_get(sub, "Cuenta", "Cuenta")
            botones_selector.append([{"text": f"✏️ {srv} - {pnt} ({cta})", "callback_data": f"renombrar_perfil_{r_idx}"}])

        botones_selector.append([{"text": "🔙 Volver", "callback_data": "ver_datos"}])
        mensaje = "✏️ *PERSONALIZAR NOMBRE DE PERFIL*\n\nSelecciona la pantalla a la que deseas cambiarle el nombre:"
        
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
        else:
            enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("renombrar_perfil_"):
        try:
            row_idx_renombrar = int(accion.split("_")[-1])
            esperando_nuevo_nombre_perfil[str_chat_id] = row_idx_renombrar

            mensaje_peticion = (
                "✏️ *ESCRIBE TU NUEVO NOMBRE*\n\n"
                "Escribe a continuación el nombre que deseas asignarle a tu perfil (Ej: *Papá*, *Sofía*, *Cine*)."
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "menu_renombrar"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        except Exception as e:
            print(f"Error iniciando renombrado: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    elif accion == "obtener_codigo" or "codigo" in accion:
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        if not verificar_cliente_activo(chat_id):
            registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_callback, ADMIN_ID)
            mensaje = "🔒 *ACCESO RESTRINGIDO*\n\nPara solicitar códigos, debes tener al menos una pantalla en estado *Activo* y con correo asignado."
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [
            s for s in obtener_suscripciones_por_id(chat_id)
            if safe_get(s, "Estado", "").lower() == "activo"
            and "pendiente" not in safe_get(s, "Cuenta", "").lower()
            and safe_get(s, "Cuenta", "").lower() not in ("", "por asignar")
        ]

        if len(suscripciones_activas) > 1 and not accion.startswith("pedir_otp_"):
            botones_selector = []
            for idx, sub in enumerate(suscripciones_activas):
                srv = safe_get(sub, "Servicio", "Disney+")
                cta = safe_get(sub, "Cuenta", "Cuenta")
                pnt = safe_get(sub, "Pantalla", "Perfil 1")
                botones_selector.append([{"text": f"📺 {srv} - {pnt} ({cta})", "callback_data": f"pedir_otp_{idx}"}])
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            
            mensaje = "📺 Tienes varias pantallas activas. *¿Para cuál pantalla deseas solicitar el código?*:"
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
            return

        servicio_seleccionado = safe_get(suscripciones_activas[0], "Servicio", "Disney").lower() if suscripciones_activas else "disney"
        ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)

    elif accion.startswith("pedir_otp_"):
        try:
            idx_sub = int(accion.split("_")[-1])
            suscripciones_activas = [
                s for s in obtener_suscripciones_por_id(chat_id)
                if safe_get(s, "Estado", "").lower() == "activo"
                and "pendiente" not in safe_get(s, "Cuenta", "").lower()
            ]
            if idx_sub < len(suscripciones_activas):
                servicio_seleccionado = safe_get(suscripciones_activas[idx_sub], "Servicio", "Disney").lower()
            else:
                servicio_seleccionado = "disney"
            ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception as e:
            print(f"Error en selector OTP: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())

    elif accion == "renovar_suscripcion":
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        suscripciones = obtener_suscripciones_por_id(chat_id)
        if not suscripciones:
            procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback, message_id, True, "comprar_extra", None, enviar_foto_callback)
            return

        if len(suscripciones) == 1:
            sub_unica = suscripciones[0]
            row_idx_unico = sub_unica.get("_row_index")
            srv_unico = safe_get(sub_unica, "Servicio", "Disney+").lower()
            srv_clave = "netflix" if "netflix" in srv_unico else "disney"
            
            iniciar_proceso_pago_con_descuento(chat_id, str_chat_id, nombre, username, srv_clave, "renovacion", row_idx_unico, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback, cupon_aplicado=None)
        else:
            botones_selector = []
            for sub in suscripciones:
                r_idx = sub.get("_row_index")
                srv = safe_get(sub, "Servicio", "Disney+")
                pnt = safe_get(sub, "Pantalla", "Perfil 1")
                cta = safe_get(sub, "Cuenta", "Cuenta")
                botones_selector.append([{"text": f"🔄 {srv} - {pnt} ({cta})", "callback_data": f"renovar_fila_{r_idx}"}])
            
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            mensaje = "🔄 Tienes múltiples pantallas. *¿Cuál de ellas deseas renovar por 30 días?*:"
            
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})

    elif accion.startswith("renovar_fila_"):
        try:
            row_idx_elegido = int(accion.split("_")[-1])
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_elegido - 2] if (row_idx_elegido - 2) < len(registros) else {}
            srv_fila = safe_get(fila_obj, "Servicio", "Disney+").lower()
            srv_clave = "netflix" if "netflix" in srv_fila else "disney"
            
            iniciar_proceso_pago_con_descuento(chat_id, str_chat_id, nombre, username, srv_clave, "renovacion", row_idx_elegido, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback, cupon_aplicado=None)
        except Exception as e:
            print(f"Error procesando renovación: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())

    elif accion == "comprar_extra":
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        from config_y_estado import PRECIO_DISNEY_USD, PRECIO_NETFLIX_USD
        mensaje = (
            "🛒 *COMPRAR NUEVA PANTALLA*\n\n"
            "¿Qué plataforma deseas comprar como nueva pantalla?\n\n"
            f"• *Disney+:* `${PRECIO_DISNEY_USD:.2f} USDT`\n"
            f"• *Netflix:* `${PRECIO_NETFLIX_USD:.2f} USDT`"
        )
        teclado_servicios = {
            "inline_keyboard": [
                [{"text": f"📺 Disney+ (${PRECIO_DISNEY_USD:.2f})", "callback_data": "pagar_servicio_disney_nueva"}],
                [{"text": f"📺 Netflix (${PRECIO_NETFLIX_USD:.2f})", "callback_data": "pagar_servicio_netflix_nueva"}],
                [{"text": "🔙 Volver", "callback_data": "menu_principal"}]
            ]
        }
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_servicios)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_servicios)

    elif accion.startswith("pagar_servicio_"):
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        es_netflix = "netflix" in accion
        servicio_elegido = "Netflix" if es_netflix else "Disney+"
        srv_clave = "netflix" if es_netflix else "disney"
        
        nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido, enviar_mensaje_callback)
        iniciar_proceso_pago_con_descuento(chat_id, str_chat_id, nombre, username, srv_clave, "nueva", nueva_fila_idx, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback, cupon_aplicado=None)

    elif accion.startswith("usar_cupon_"):
        try:
            row_idx_target = int(accion.split("_")[-1])
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}

            srv_nombre = safe_get(fila_obj, "Servicio", "Disney+").lower()
            srv_clave = "netflix" if "netflix" in srv_nombre else "disney"

            venc_previo = safe_get(fila_obj, "Vencimiento", "").strip()
            tipo_op_actual = "renovacion" if (venc_previo and len(venc_previo) == 10 and ("-" in venc_previo or "/" in venc_previo)) else "nueva"

            esperando_codigo_cupon_cliente[str_chat_id] = {
                "servicio_clave": srv_clave,
                "tipo_operacion": tipo_op_actual,
                "row_idx_target": row_idx_target,
                "message_id": message_id
            }

            msg_c = "🎟️ *CANJEAR CUPÓN DE DESCUENTO*\n\nPor favor, escribe a continuación el código de tu cupón:"
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, msg_c, {"inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": f"volver_pago_sin_cupon_{row_idx_target}"}]]})
            else:
                enviar_mensaje_callback(chat_id, msg_c, {"inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": f"volver_pago_sin_cupon_{row_idx_target}"}]]})
        except Exception as e:
            print(f"Error pidiendo cupón: {e}")
        return

    # -------------------------------------------------------------
    # SOPORTE, FAQ Y TÉRMINOS
    # -------------------------------------------------------------
    elif accion == "soporte" or "pago" in accion:
        row_huerta = esperando_captura_pago.pop(str_chat_id, None)
        limpiar_fila_cancelada_o_renovacion(row_huerta, chat_id_respaldo=str_chat_id)

        from config_y_estado import WHATSAPP_NUMERO
        texto_wa = f"Hola, necesito soporte con mi servicio de Streaming. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "❓ Preguntas Frecuentes (FAQ)", "callback_data": "ver_faq"}],
                [{"text": "📜 Términos y Condiciones", "callback_data": "ver_terminos"}],
                [{"text": "💬 Soporte Técnico en WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *CENTRO DE AYUDA Y SOPORTE*\n\nSelecciona una opción para resolver tus dudas rápidamente o comunícate con nosotros por WhatsApp:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    elif accion == "ver_faq":
        mensaje_faq = (
            "❓ *PREGUNTAS FRECUENTES (FAQ)* ❓\n\n"
            "1️⃣ *¿Cuál es la diferencia entre el PIN y el Código de Acceso (OTP)?*\n"
            "• **El Código (OTP):** Código temporal de 4 a 6 dígitos que envía la plataforma al correo para *iniciar sesión*.\n"
            "• **El PIN de Perfil:** Clave fija de 4 números que protege tu pantalla personal.\n\n"
            "2️⃣ *¿Cuánto dura la suscripción?*\n"
            "Cada pago aprobado activa tu pantalla por exactamente **30 días**."
        )
        teclado_faq = {"inline_keyboard": [[{"text": "🔙 Volver a Soporte", "callback_data": "soporte"}]]}
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje_faq, teclado_faq)
        else:
            enviar_mensaje_callback(chat_id, mensaje_faq, teclado_faq)
        return

    elif accion == "ver_terminos":
        mensaje_terminos = (
            "📜 *TÉRMINOS Y CONDICIONES DEL SERVICIO* 📜\n\n"
            "1️⃣ *1 Pantalla = 1 Dispositivo a la vez:* Tu suscripción te da derecho a reproducir en un solo dispositivo.\n"
            "2️⃣ *Respeto a los Perfiles:* Ingresa únicamente a tu perfil asignado usando tu PIN.\n"
            "3️⃣ *Garantía Total:* Cuentas con soporte activo durante los **30 días** de tu suscripción."
        )
        teclado_term = {"inline_keyboard": [[{"text": "🔙 Volver al Soporte", "callback_data": "soporte"}]]}
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje_terminos, teclado_term)
        else:
            enviar_mensaje_callback(chat_id, mensaje_terminos, teclado_term)
        return

    else:
        mensaje = "¡Hola! Selecciona una opción del menú de abajo:"
        teclado = get_main_menu_keyboard()
        enviar_mensaje_callback(chat_id, mensaje, teclado)
