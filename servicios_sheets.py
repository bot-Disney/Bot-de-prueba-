import datetime
import time
from sheets_db import conectar_sheets
from config_y_estado import (
    candado_operaciones,
    ADMIN_ID,
    PRECIO_DISNEY_USD,
    PRECIO_NETFLIX_USD,
    safe_get,
    obtener_hora_venezuela
)
from teclados import get_main_menu_keyboard, get_back_keyboard


def normalizar_id(valor):
    """Limpia IDs de Telegram o números de WhatsApp (quita espacios, '+', y '.0' de Sheets)."""
    s = str(valor or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.lstrip("+").strip()


def existen_cupones_activos():
    """Verifica si hay al menos un cupón activo y vigente en Google Sheets."""
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cupones = spreadsheet.worksheet("Cupones")
        registros = sheet_cupones.get_all_records()
        
        ahora = obtener_hora_venezuela().replace(tzinfo=None)
        for row in registros:
            estado = safe_get(row, "Estado", "Activo").lower()
            if estado == "activo":
                fecha_creacion_str = safe_get(row, "Fecha de Creacion", "")
                duracion_horas_str = safe_get(row, "Duracion (Horas)", "0")
                
                expirado = False
                if fecha_creacion_str and str(duracion_horas_str).strip().isdigit():
                    duracion_horas = int(str(duracion_horas_str).strip())
                    if duracion_horas > 0:
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                fecha_creacion = datetime.datetime.strptime(fecha_creacion_str, fmt)
                                if ahora > (fecha_creacion + datetime.timedelta(hours=duracion_horas)):
                                    expirado = True
                                break
                            except ValueError:
                                continue
                if expirado:
                    continue
                
                usos_max = int(safe_get(row, "Usos Maximos", "999999"))
                veces_usado = int(safe_get(row, "Veces Usado", "0"))
                if veces_usado < usos_max:
                    return True
        return False
    except Exception:
        return False


def validar_y_consumir_cupon(codigo_ingresado):
    with candado_operaciones:
        try:
            sheet_principal = conectar_sheets()
            spreadsheet = sheet_principal.spreadsheet
            
            try:
                sheet_cupones = spreadsheet.worksheet("Cupones")
            except Exception:
                return False, "❌ El cupón ingresado no existe."

            registros = sheet_cupones.get_all_records()
            ahora = obtener_hora_venezuela().replace(tzinfo=None)

            for idx, row in enumerate(registros, start=2):
                codigo_db = safe_get(row, "Codigo", "").upper()
                
                if codigo_db == codigo_ingresado.upper():
                    estado = safe_get(row, "Estado", "Activo").lower()
                    if estado != "activo":
                        return False, "❌ Este cupón ya expiró o no está disponible."

                    fecha_creacion_str = safe_get(row, "Fecha de Creacion", "")
                    duracion_horas_str = str(safe_get(row, "Duracion (Horas)", "0")).strip()
                    duracion_horas = int(duracion_horas_str) if duracion_horas_str.isdigit() else 0
                    
                    if fecha_creacion_str and duracion_horas > 0:
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                            try:
                                fecha_creacion = datetime.datetime.strptime(fecha_creacion_str, fmt)
                                fecha_expiracion = fecha_creacion + datetime.timedelta(hours=duracion_horas)
                                
                                if ahora > fecha_expiracion:
                                    sheet_cupones.update_cell(idx, 8, "Expirado")
                                    return False, "⏳ ¡Este cupón relámpago ya expiró!"
                                break
                            except ValueError:
                                continue

                    usos_max = int(safe_get(row, "Usos Maximos", "999999"))
                    veces_usado = int(safe_get(row, "Veces Usado", "0"))

                    if veces_usado >= usos_max:
                        sheet_cupones.update_cell(idx, 8, "Agotado")
                        return False, "❌ Este cupón ya alcanzó su límite máximo de usos."

                    tipo_desc = safe_get(row, "Tipo", "Fijo").strip()
                    valor_raw = str(safe_get(row, "Valor", "0")).replace("$", "").replace("%", "").replace(",", ".").strip()
                    try:
                        valor_desc = float(valor_raw)
                    except ValueError:
                        valor_desc = 0.0

                    if valor_desc <= 0:
                        return False, "❌ El cupón tiene un valor de descuento inválido (0)."

                    sheet_cupones.update_cell(idx, 7, veces_usado + 1)
                    if (veces_usado + 1) >= usos_max and duracion_horas == 0:
                        sheet_cupones.update_cell(idx, 8, "Agotado")

                    return True, {"tipo": tipo_desc, "valor": valor_desc, "codigo": codigo_db}

            return False, "❌ El código de cupón ingresado es inválido."
        except Exception as e:
            print(f"Error validando cupón: {e}")
            return False, "❌ Ocurrió un error al validar el cupón."


def guardar_nuevo_cupon_sheet(chat_id, sesion_c, enviar_msg_cb):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            sheet_cupones = spreadsheet.worksheet("Cupones")
        except Exception:
            sheet_cupones = spreadsheet.add_worksheet(title="Cupones", rows="1000", cols="8")
            sheet_cupones.append_row(["Codigo", "Tipo", "Valor", "Fecha de Creacion", "Duracion (Horas)", "Usos Maximos", "Veces Usado", "Estado"])

        try:
            fila_1 = sheet_cupones.row_values(1)
            if len(fila_1) < 8:
                sheet_cupones.update("A1:H1", [["Codigo", "Tipo", "Valor", "Fecha de Creacion", "Duracion (Horas)", "Usos Maximos", "Veces Usado", "Estado"]])
        except Exception:
            pass

        codigo = sesion_c["codigo"]
        tipo = sesion_c["tipo"]
        valor = sesion_c["valor"]
        fecha_creacion = obtener_hora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
        duracion_horas = sesion_c["duracion_horas"]
        usos_maximos = sesion_c["usos_maximos"]
        veces_usado = 0
        estado = "Activo"

        sheet_cupones.append_row([
            codigo,
            tipo,
            str(valor),
            fecha_creacion,
            str(duracion_horas),
            str(usos_maximos),
            str(veces_usado),
            estado
        ])

        detalle_limite = f"{duracion_horas} horas" if duracion_horas > 0 else f"{usos_maximos} usos máximos"
        simbolo = "$" if tipo == "Fijo" else "%"

        enviar_msg_cb(
            chat_id,
            f"✅ *¡CUPÓN CREADO CON ÉXITO!*\n\n"
            f"• *Código:* `{codigo}`\n"
            f"• *Descuento:* {valor}{simbolo} ({tipo})\n"
            f"• *Límite:* {detalle_limite}\n"
            f"• *Estado:* Activo y listo para usar.",
            {
                "inline_keyboard": [
                    [{"text": "🎟️ Ver Lista de Cupones", "callback_data": "admin_ver_cupones"}],
                    [{"text": "🔙 Volver a Gestión de Cupones", "callback_data": "admin_gestionar_cupones"}]
                ]
            }
        )
    except Exception as e:
        print(f"Error guardando cupón: {e}")
        enviar_msg_cb(chat_id, f"❌ Ocurrió un error al guardar el cupón en Google Sheets: {e}", {
            "inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_gestionar_cupones"}]]
        })


def obtener_pin_asignado_cliente(correo_cuenta, nombre_perfil):
    if not correo_cuenta or "pendiente" in correo_cuenta.lower() or "asignar" in correo_cuenta.lower():
        return "N/A"
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
        registros = sheet_cuentas.get_all_records()

        num_perfil_limpio = "Perfil 1"
        for n in range(1, 10):
            if f"perfil {n}" in str(nombre_perfil).lower():
                num_perfil_limpio = f"Perfil {n}"
                break

        for c in registros:
            correo_c = safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", ""))
            if correo_c.lower() == correo_cuenta.lower():
                pins_texto = safe_get(c, "PINs de Perfiles", "")
                for parte in pins_texto.split("|"):
                    if num_perfil_limpio.lower() in parte.lower():
                        if ":" in parte:
                            return parte.split(":")[-1].strip()
                return pins_texto if pins_texto else "Sin PIN"
        return "No registrado"
    except Exception as e:
        print(f"Error consultando PIN: {e}")
        return "S/N"


def limpiar_fila_cancelada_o_renovacion(row_idx):
    try:
        sheet_principal = conectar_sheets()
        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 6:
            return

        estado_actual = safe_get({"Estado": fila_datos[5]}, "Estado", "").lower()
        vencimiento_actual = safe_get({"Vencimiento": fila_datos[4]}, "Vencimiento", "").strip()

        if "pendiente" in estado_actual:
            if vencimiento_actual and vencimiento_actual.lower() not in ("", "sin fecha") and len(vencimiento_actual) == 10 and ("-" in vencimiento_actual or "/" in vencimiento_actual):
                sheet_principal.update_cell(row_idx, 6, "Activo")
                print(f"Renovación cancelada en fila {row_idx}. Estado restaurado a Activo.")
            else:
                correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
                if correo_a_liberar and "pendiente de stock" not in correo_a_liberar.lower():
                    try:
                        spreadsheet = sheet_principal.spreadsheet
                        sheet_cuentas = spreadsheet.worksheet("Cuentas")
                        registros_cuentas = sheet_cuentas.get_all_records()
                        for idx_c, c_row in enumerate(registros_cuentas, start=2):
                            correo_cta = safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", ""))
                            if correo_cta.lower() == correo_a_liberar.lower():
                                ocupados = int(safe_get(c_row, "Perfiles Ocupados", "1"))
                                nuevos_ocupados = max(0, ocupados - 1)
                                sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)
                                if safe_get(c_row, "Estado", "").lower() == "llena":
                                    sheet_cuentas.update_cell(idx_c, 6, "Activa")
                                break
                    except Exception as e:
                        print(f"Aviso al liberar stock en cancelación: {e}")
                sheet_principal.delete_rows(row_idx)
                print(f"Fila nueva {row_idx} eliminada por cancelación.")
    except Exception as e:
        print(f"Error en limpieza segura de fila: {e}")


def rechazar_pago_seguro(row_idx):
    try:
        sheet_principal = conectar_sheets()
        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 6:
            return "Fila no encontrada."

        vencimiento_actual = safe_get({"Vencimiento": fila_datos[4]}, "Vencimiento", "").strip()

        if vencimiento_actual and vencimiento_actual.lower() not in ("", "sin fecha") and len(vencimiento_actual) == 10 and ("-" in vencimiento_actual or "/" in vencimiento_actual):
            sheet_principal.update_cell(row_idx, 6, "Activo")
            return f"Pago de la fila {row_idx} rechazado. Como era una renovación, la suscripción se ha restaurado a Estado Activo sin perder sus días."
        else:
            resultado = liberar_y_eliminar_fila_suscripcion(row_idx)
            return f"Pago de la fila {row_idx} rechazado. Fila eliminada y cupo liberado con éxito."
    except Exception as e:
        print(f"Error en rechazo seguro: {e}")
        return f"Error al procesar el rechazo: {e}"


def obtener_primer_perfil_disponible(sheet, servicio_solicitado, correo_asignado):
    try:
        es_netflix = "netflix" in servicio_solicitado.lower()
        limite_maximo = 5 if es_netflix else 7

        registros = sheet.get_all_records()
        perfiles_ocupados_en_cuenta = set()

        for r in registros:
            srv = safe_get(r, "Servicio", "").lower()
            cta = safe_get(r, "Cuenta", "").lower()
            pnt = safe_get(r, "Pantalla", "").lower()
            
            if servicio_solicitado.lower() in srv and cta == correo_asignado.lower():
                for num in range(1, limite_maximo + 1):
                    if f"perfil {num}" in pnt:
                        perfiles_ocupados_en_cuenta.add(num)

        for num in range(1, limite_maximo + 1):
            if num not in perfiles_ocupados_en_cuenta:
                return f"Perfil {num}"

        return f"Perfil {limite_maximo + 1}"
    except Exception as e:
        print(f"Error buscando perfil disponible: {e}")
        return "Perfil 1"


def asignar_correo_desde_stock(sheet_principal, servicio_solicitado, chat_id="", nombre_cliente="", enviar_mensaje_callback=None):
    with candado_operaciones:
        try:
            spreadsheet = sheet_principal.spreadsheet
            try:
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
            except Exception:
                return "Por Asignar"

            registros_cuentas = sheet_cuentas.get_all_records()
            
            for idx_c, cuenta_row in enumerate(registros_cuentas, start=2):
                srv_cuenta = safe_get(cuenta_row, "Servicio", "").lower()
                estado_cuenta = safe_get(cuenta_row, "Estado", "").lower()
                
                if servicio_solicitado.lower() in srv_cuenta and estado_cuenta == "activa":
                    try:
                        limite_defecto = 5 if "netflix" in servicio_solicitado.lower() else 7
                        capacidad = int(safe_get(cuenta_row, "Capacidad Total", str(limite_defecto)))
                        ocupados = int(safe_get(cuenta_row, "Perfiles Ocupados", "0"))
                    except ValueError:
                        capacidad = 5 if "netflix" in servicio_solicitado.lower() else 7
                        ocupados = 0

                    if ocupados < capacidad:
                        correo_encontrado = safe_get(cuenta_row, "Correo (Usuario)", safe_get(cuenta_row, "Correo", ""))
                        
                        nuevos_ocupados = ocupados + 1
                        sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)
                        
                        if nuevos_ocupados >= capacidad:
                            sheet_cuentas.update_cell(idx_c, 6, "Llena")
                            if ADMIN_ID and enviar_mensaje_callback:
                                alerta_stock = (
                                    f"⚠️ *¡ALERTA DE STOCK AGOTADO!* ⚠️\n\n"
                                    f"La cuenta de *{servicio_solicitado}* (`{correo_encontrado}`) ha llegado al 100% de su capacidad y está *Llena*.\n\n"
                                    f"💡 *Acción recomendada:* Carga una nueva cuenta en la pestaña 'Cuentas' lo antes posible."
                                )
                                try:
                                    enviar_mensaje_callback(int(ADMIN_ID), alerta_stock)
                                except Exception:
                                    pass
                            
                        return correo_encontrado
                        
            if ADMIN_ID and enviar_mensaje_callback:
                alerta_sin_stock = (
                    f"🚨 *¡COMPRA CON STOCK AGOTADO (LISTA DE ESPERA)!* 🚨\n\n"
                    f"• *Cliente:* {nombre_cliente}\n"
                    f"• *Telegram ID:* `{chat_id}`\n"
                    f"• *Servicio:* {servicio_solicitado}\n\n"
                    f"💡 El cliente avanzó a pagar pero no había cuentas activas. Quedó marcado como *Pendiente de Stock*. ¡Carga una cuenta nueva y usa el botón *Asignar Stock Pendiente* en `/admin`!"
                )
                try:
                    enviar_mensaje_callback(int(ADMIN_ID), alerta_sin_stock)
                except Exception:
                    pass

            return "⚠️ Pendiente de Stock"
        except Exception as e:
            print(f"Error asignando correo desde stock: {e}")
            return "Por Asignar"


def procesar_asignacion_stock_masivo(enviar_msg_cb):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
        except Exception:
            return "❌ No se encontró la pestaña 'Cuentas' en el Google Sheets."

        registros_clientes = sheet_principal.get_all_records()
        registros_cuentas = sheet_cuentas.get_all_records()
        
        asignados_count = 0

        for idx_cli, cli_row in enumerate(registros_clientes, start=2):
            cuenta_actual = safe_get(cli_row, "Cuenta", "")
            
            if "pendiente de stock" in cuenta_actual.lower():
                servicio_cli = safe_get(cli_row, "Servicio", "Disney+")
                tid_cliente = safe_get(cli_row, "Telegram_ID", "")
                nombre_cliente = safe_get(cli_row, "Nombre", "Cliente")
                estado_cli = safe_get(cli_row, "Estado", "").lower()
                
                cuenta_encontrada = None
                idx_cuenta_encontrada = None
                
                for idx_c, cuenta_row in enumerate(registros_cuentas, start=2):
                    srv_cuenta = safe_get(cuenta_row, "Servicio", "").lower()
                    estado_cuenta = safe_get(cuenta_row, "Estado", "").lower()
                    
                    if servicio_cli.lower() in srv_cuenta and estado_cuenta == "activa":
                        try:
                            limite_defecto = 5 if "netflix" in servicio_cli.lower() else 7
                            capacidad = int(safe_get(cuenta_row, "Capacidad Total", str(limite_defecto)))
                            ocupados = int(safe_get(cuenta_row, "Perfiles Ocupados", "0"))
                        except ValueError:
                            capacidad = 5 if "netflix" in servicio_cli.lower() else 7
                            ocupados = 0

                        if ocupados < capacidad:
                            cuenta_encontrada = safe_get(cuenta_row, "Correo (Usuario)", safe_get(cuenta_row, "Correo", ""))
                            idx_cuenta_encontrada = idx_c
                            break
                
                if cuenta_encontrada and idx_cuenta_encontrada:
                    perfil_correcto = obtener_primer_perfil_disponible(sheet_principal, servicio_cli, cuenta_encontrada)
                    
                    sheet_principal.update_cell(idx_cli, 3, cuenta_encontrada)
                    sheet_principal.update_cell(idx_cli, 4, perfil_correcto)
                    
                    fila_c_actual = sheet_cuentas.row_values(idx_cuenta_encontrada)
                    try:
                        ocupados_actuales = int(fila_c_actual[4])
                    except (IndexError, ValueError):
                        ocupados_actuales = 0
                        
                    nuevos_ocupados = ocupados_actuales + 1
                    sheet_cuentas.update_cell(idx_cuenta_encontrada, 5, nuevos_ocupados)
                    
                    limite_defecto = 5 if "netflix" in servicio_cli.lower() else 7
                    capacidad_total = int(fila_c_actual[3]) if len(fila_c_actual) > 3 and fila_c_actual[3].isdigit() else limite_defecto
                    if nuevos_ocupados >= capacidad_total:
                        sheet_cuentas.update_cell(idx_cuenta_encontrada, 6, "Llena")

                    if tid_cliente and enviar_msg_cb and estado_cli == "activo":
                        try:
                            primer_nombre = nombre_cliente.split()[0] if nombre_cliente else "Cliente"
                            pin_asignado = obtener_pin_asignado_cliente(cuenta_encontrada, perfil_correcto)
                            aviso_tv_especial = (
                                "\n\n📺 *Nota para Smart TVs (como Damasco u otros):*\n"
                                "Si tu televisor no muestra código numérico de 4 dígitos y te pide aprobar por correo, "
                                "avísanos por soporte para ayudarte a confirmarlo de inmediato."
                            )
                            mensaje_notif = (
                                f"🎉 *¡EXCELENTE NOTICIA, {primer_nombre}!*\n\n"
                                f"Tu cuenta de *{servicio_cli}* ya ha sido asignada y se encuentra 100% **Activa**.\n\n"
                                f"• *Correo asignado:* `{cuenta_encontrada}`\n"
                                f"• *Perfil:* `{perfil_correcto}`\n"
                                f"• *PIN de seguridad:* `{pin_asignado}` 🔒"
                                f"{aviso_tv_especial}\n\n"
                                "Puedes ingresar al bot y presionar **📲 Ver mis datos / pantallas** para consultar los detalles completos de tu acceso."
                            )
                            enviar_msg_cb(normalizar_id(tid_cliente), mensaje_notif, get_main_menu_keyboard())
                        except Exception as e:
                            print(f"No se pudo notificar al cliente {tid_cliente}: {e}")

                    asignados_count += 1
                    registros_cuentas = sheet_cuentas.get_all_records()

        if asignados_count > 0:
            return f"✅ ¡Proceso exitoso! Se han asignado cuentas nuevas a **{asignados_count}** cliente(s) que estaban en lista de espera."
        else:
            return "ℹ️ No hay clientes pendientes de stock o no hay suficientes cuentas activas con cupo en la pestaña 'Cuentas'."

    except Exception as e:
        print(f"Error en asignación masiva de stock: {e}")
        return f"❌ Ocurrió un error al procesar la asignación: {e}"


def obtener_suscripciones_por_id(chat_id):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        id_buscado = normalizar_id(chat_id)
        resultados = []
        for idx, r in enumerate(registros, start=2):
            tid = normalizar_id(safe_get(r, "Telegram_ID", ""))
            if tid and tid == id_buscado:
                r["_row_index"] = idx
                resultados.append(r)
        return resultados
    except Exception as e:
        print(f"Error: {e}")
        return []


def crear_nueva_fila_pendiente(str_chat_id, nombre, username="", servicio="Disney", enviar_mensaje_cb=None):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        id_limpio = normalizar_id(str_chat_id)

        for idx, r in enumerate(registros, start=2):
            tid = normalizar_id(safe_get(r, "Telegram_ID", ""))
            estado = safe_get(r, "Estado", "").lower()
            srv = safe_get(r, "Servicio", "").lower()
            
            if tid == id_limpio and "pendiente" in estado and servicio.lower() in srv:
                return idx

        correo_asignado = asignar_correo_desde_stock(sheet, servicio, id_limpio, nombre_completo, enviar_mensaje_cb)
        perfil_asignado = obtener_primer_perfil_disponible(sheet, servicio, correo_asignado)
        
        sheet.append_row([id_limpio, nombre_completo, correo_asignado, perfil_asignado, "", "Pendiente Pago", servicio])
        return len(sheet.get_all_records()) + 1
    except Exception as e:
        print(f"Error creando fila nueva: {e}")
        return 2


def verificar_cliente_activo(chat_id):
    for sub in obtener_suscripciones_por_id(chat_id):
        estado = safe_get(sub, "Estado", "").lower()
        cuenta = safe_get(sub, "Cuenta", "").lower()
        if estado == "activo" and cuenta not in ("", "por asignar") and "pendiente" not in cuenta:
            return True
    return False


def obtener_clientes_pendientes():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        pendientes = []
        for idx, row in enumerate(registros, start=2):
            estado = safe_get(row, "Estado", "").lower()
            if "pendiente" in estado:
                pendientes.append((len(pendientes)+1, idx, row))
        return pendientes
    except Exception as e:
        print(f"Error obteniendo pendientes: {e}")
        return []


def obtener_clientes_activos_general():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        activos = []
        for idx, row in enumerate(registros, start=2):
            estado = safe_get(row, "Estado", "").lower()
            cuenta = safe_get(row, "Cuenta", "")
            if estado == "activo" and cuenta and cuenta.lower() not in ("por asignar", "pendiente de stock"):
                activos.append((len(activos)+1, idx, row))
        return activos
    except Exception as e:
        print(f"Error obteniendo clientes activos: {e}")
        return []


def obtener_suscripciones_vencidas():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        vencidos = []
        hoy = obtener_hora_venezuela().date()

        for idx, row in enumerate(registros, start=2):
            vencimiento_str = safe_get(row, "Vencimiento", "")
            estado = safe_get(row, "Estado", "").lower()
            cuenta = safe_get(row, "Cuenta", "")

            if cuenta and cuenta.lower() not in ("por asignar", "pendiente de stock"):
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
                        if fecha_venc < hoy or estado == "vencido":
                            vencidos.append((len(vencidos)+1, idx, row))
                        break
                    except ValueError:
                        continue
        return vencidos
    except Exception as e:
        print(f"Error obteniendo vencidos: {e}")
        return []


def liberar_y_eliminar_fila_suscripcion(row_idx):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
        except Exception:
            return "❌ No se encontró la pestaña 'Cuentas'."

        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 3:
            return "❌ La fila seleccionada no es válida o está vacía."

        correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
        
        registros_cuentas = sheet_cuentas.get_all_records()
        cuenta_encontrada = False

        for idx_c, c_row in enumerate(registros_cuentas, start=2):
            correo_cta = safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", ""))
            if correo_cta.lower() == correo_a_liberar.lower():
                try:
                    ocupados = int(safe_get(c_row, "Perfiles Ocupados", "1"))
                except ValueError:
                    ocupados = 1

                nuevos_ocupados = max(0, ocupados - 1)
                sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)

                estado_actual = safe_get(c_row, "Estado", "").lower()
                if estado_actual == "llena":
                    sheet_cuentas.update_cell(idx_c, 6, "Activa")

                cuenta_encontrada = True
                break

        sheet_principal.delete_rows(row_idx)

        msg_extra = " y se liberó un cupo en la cuenta maestra" if cuenta_encontrada else ""
        return f"✅ ¡Suscripción de la fila {row_idx} eliminada con éxito{msg_extra}!"

    except Exception as e:
        print(f"Error liberando suscripción: {e}")
        return f"❌ Ocurrió un error al liberar la suscripción: {e}"


def aprobar_suscripcion_sheet(row_idx):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_actual = registros[row_idx - 2] if (row_idx - 2) < len(registros) else {}
        tid_cliente = safe_get(fila_actual, "Telegram_ID", "")
        nombre_cliente = safe_get(fila_actual, "Nombre", "Cliente")
        servicio_fila = safe_get(fila_actual, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_actual, "Pantalla", "Perfil 1")
        cuenta_fila = safe_get(fila_actual, "Cuenta", "Por Asignar")
        timestamp_orden = safe_get(fila_actual, "Vencimiento", "").strip()
        estado_actual = safe_get(fila_actual, "Estado", "").lower()

        if estado_actual == "activo":
            return True, tid_cliente, True, nombre_cliente, servicio_fila, perfil_asignado, "Renovación", cuenta_fila

        fecha_previa = None
        if timestamp_orden and len(timestamp_orden) == 10:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    fecha_previa = datetime.datetime.strptime(timestamp_orden, fmt).date()
                    break
                except ValueError:
                    continue

        es_renovacion = (fecha_previa is not None)
        tipo_operacion = "Renovación" if es_renovacion else "Pantalla Nueva"

        if not es_renovacion:
            tiempo_expirado = False
            if timestamp_orden:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        hora_orden = datetime.datetime.strptime(timestamp_orden, fmt)
                        ahora_local = obtener_hora_venezuela().replace(tzinfo=None)
                        diferencia_minutos = (ahora_local - hora_orden).total_seconds() / 60
                        if diferencia_minutos > 30:
                            tiempo_expirado = True
                        break
                    except ValueError:
                        continue

            if tiempo_expirado:
                print(f"⚠️ La orden de la fila {row_idx} superó los 30 minutos. Reasignando pantalla fresca...")
                
                if cuenta_fila and "pendiente" not in cuenta_fila.lower() and "asignar" not in cuenta_fila.lower():
                    try:
                        spreadsheet = sheet.spreadsheet
                        sheet_cuentas = spreadsheet.worksheet("Cuentas")
                        registros_c = sheet_cuentas.get_all_records()
                        for idx_c, c_row in enumerate(registros_c, start=2):
                            if safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", "")).lower() == cuenta_fila.lower():
                                ocu = int(safe_get(c_row, "Perfiles Ocupados", "1"))
                                sheet_cuentas.update_cell(idx_c, 5, max(0, ocu - 1))
                                if safe_get(c_row, "Estado", "").lower() == "llena":
                                    sheet_cuentas.update_cell(idx_c, 6, "Activa")
                                break
                    except Exception as e:
                        print(f"Aviso liberando cuenta expirada de 30 min: {e}")

                correo_fresco = asignar_correo_desde_stock(sheet, servicio_fila, tid_cliente, nombre_cliente)
                if correo_fresco and "pendiente" not in correo_fresco.lower():
                    cuenta_fila = correo_fresco
                    perfil_asignado = obtener_primer_perfil_disponible(sheet, servicio_fila, cuenta_fila)
                    sheet.update_cell(row_idx, 3, cuenta_fila)
                    sheet.update_cell(row_idx, 4, perfil_asignado)
                else:
                    cuenta_fila = "⚠️ Pendiente de Stock"
                    sheet.update_cell(row_idx, 3, cuenta_fila)

        hoy = obtener_hora_venezuela().date()
        if es_renovacion and fecha_previa > hoy:
            fecha_base = fecha_previa
        else:
            fecha_base = hoy

        nueva_fecha = (fecha_base + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        
        sheet.update_cell(row_idx, 5, nueva_fecha)
        sheet.update_cell(row_idx, 6, "Activo")
        
        return True, tid_cliente, False, nombre_cliente, servicio_fila, perfil_asignado, tipo_operacion, cuenta_fila
    except Exception as e:
        print(f"Error aprobando suscripción: {e}")
        return False, None, False, "", "Disney+", "Perfil 1", "Renovación", "Por Asignar"


def registrar_venta_en_historial(nombre_cliente, tid_cliente, servicio, perfil, monto_usd, tipo_operacion, metodo_pago):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        encabezados_esperados = ["Fecha y Hora", "Cliente", "Telegram ID", "Servicio", "Perfil Asignado", "Monto USD", "Tipo", "Método Pago"]
        try:
            sheet_ventas = spreadsheet.worksheet("Ventas")
            fila_1 = sheet_ventas.row_values(1)
            if len(fila_1) < 8:
                sheet_ventas.update("A1:H1", [encabezados_esperados])
        except Exception:
            sheet_ventas = spreadsheet.add_worksheet(title="Ventas", rows="1000", cols="8")
            sheet_ventas.append_row(encabezados_esperados)

        fecha_hora = obtener_hora_venezuela().strftime("%Y-%m-%d %H:%M:%S")
        sheet_ventas.append_row([
            fecha_hora,
            str(nombre_cliente),
            str(tid_cliente),
            str(servicio),
            str(perfil),
            f"${float(monto_usd):.2f}",
            str(tipo_operacion),
            str(metodo_pago)
        ])
    except Exception as e:
        print(f"Error al registrar la venta en el historial: {e}")


def verificar_alerta_vencimiento(vencimiento_str, estado_str):
    if estado_str.lower() != "activo":
        return "🔴"
    hoy = obtener_hora_venezuela().date()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
            dias = (fecha_venc - hoy).days
            if dias < 0: return "⚠️ *(Vencida)*"
            elif dias == 0: return "🟠 *(Vence HOY)*"
            elif dias <= 3: return f"🟡 *(Vence en {dias} días)*"
            return "🟢"
        except ValueError:
            continue
    return ""


def generar_reporte_admin():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        activas = sum(1 for r in registros if safe_get(r, "Estado", "").lower() == "activo")
        pendientes = sum(1 for r in registros if "pendiente" in safe_get(r, "Estado", "").lower())
        en_espera_stock = sum(1 for r in registros if "pendiente de stock" in safe_get(r, "Cuenta", "").lower())
        vencidos_total = len(obtener_suscripciones_vencidas())
        unicos = len(set(safe_get(r, "Telegram_ID", "") for r in registros if safe_get(r, "Telegram_ID", "")))
        return (
            "📊 *PANEL DE CONTROL INDUSTRIAL*\n\n"
            f"👥 *Clientes únicos:* {unicos}\n"
            f"📺 *Total pantallas:* {len(registros)}\n"
            f"🟢 *Activas:* {activas}\n"
            f"🟡 *Pagos pendientes:* {pendientes}\n"
            f"🔴 *Vencidas por depurar:* {vencidos_total}\n"
            f"⏳ *En espera de stock:* {en_espera_stock}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


def generar_resumen_completo_negocio():
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        registros_clientes = sheet_principal.get_all_records()
        total_pantallas = len(registros_clientes)
        activas_cli = sum(1 for r in registros_clientes if safe_get(r, "Estado", "").lower() == "activo")
        pendientes_pago = sum(1 for r in registros_clientes if "pendiente" in safe_get(r, "Estado", "").lower())
        en_espera_stock = sum(1 for r in registros_clientes if "pendiente de stock" in safe_get(r, "Cuenta", "").lower())
        clientes_unicos = len(set(safe_get(r, "Telegram_ID", "") for r in registros_clientes if safe_get(r, "Telegram_ID", "")))

        netflix_cli = sum(1 for r in registros_clientes if "netflix" in safe_get(r, "Servicio", "").lower())
        disney_cli = sum(1 for r in registros_clientes if "disney" in safe_get(r, "Servicio", "").lower())

        total_cuentas_maestras = 0
        cuentas_activas_stock = 0
        cuentas_llenas_stock = 0
        capacidad_total_perfiles = 0
        perfiles_totales_ocupados = 0

        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
            registros_cuentas = sheet_cuentas.get_all_records()
            total_cuentas_maestras = len(registros_cuentas)
            for c in registros_cuentas:
                est_c = safe_get(c, "Estado", "").lower()
                if est_c == "activa":
                    cuentas_activas_stock += 1
                elif est_c == "llena":
                    cuentas_llenas_stock += 1
                
                try:
                    cap = int(safe_get(c, "Capacidad Total", "5"))
                    ocu = int(safe_get(c, "Perfiles Ocupados", "0"))
                except ValueError:
                    cap = 5
                    ocu = 0
                
                capacidad_total_perfiles += cap
                perfiles_totales_ocupados += ocu
        except Exception:
            pass

        total_ingresos_usd = 0.0
        ventas_totales_count = 0
        try:
            sheet_ventas = spreadsheet.worksheet("Ventas")
            registros_ventas = sheet_ventas.get_all_records()
            ventas_totales_count = len(registros_ventas)
            for v in registros_ventas:
                monto_str = safe_get(v, "Monto USD", "0").replace("$", "").strip()
                try:
                    total_ingresos_usd += float(monto_str)
                except ValueError:
                    pass
        except Exception:
            pass

        cupos_disponibles = max(0, capacidad_total_perfiles - perfiles_totales_ocupados)

        resumen_texto = (
            "📈 *RESUMEN GENERAL DEL NEGOCIO* 📈\n\n"
            f"👤 *Clientes y Demografía:*\n"
            f"• Clientes únicos: `{clientes_unicos}`\n"
            f"• Pantallas alquiladas: `{total_pantallas}` (🟢 Activas: `{activas_cli}`)\n"
            f"• Desglose: 📺 Netflix: `{netflix_cli}` | 📺 Disney+: `{disney_cli}`\n\n"
            f"📦 *Estado del Inventario (Cuentas Maestras):*\n"
            f"• Cuentas totales: `{total_cuentas_maestras}` (🟢 Activas: `{cuentas_activas_stock}` | 🔴 Llenas: `{cuentas_llenas_stock}`)\n"
            f"• Capacidad de perfiles: `{perfiles_totales_ocupados} / {capacidad_total_perfiles}`\n"
            f"• Cupos libres en stock: `{cupos_disponibles}`\n"
            f"• Clientes en lista de espera (Sin stock): `{en_espera_stock}`\n\n"
            f"💰 *Finanzas y Rendimiento:*\n"
            f"• Transacciones registradas: `{ventas_totales_count}`\n"
            f"• Ingresos acumulados: *`${total_ingresos_usd:.2f} USD`*\n"
            f"• Pagos pendientes por verificar: `{pendientes_pago}`"
        )
        return resumen_texto
    except Exception as e:
        return f"❌ Error al generar el resumen del negocio: {e}"
