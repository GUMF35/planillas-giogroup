"""Expediente del colaborador (permisos, vacaciones, incapacidades, contratos, documentos, observaciones,
historial de cambios) y alertas de fechas importantes."""
from datetime import timedelta

from .finanzas import ErrorNegocio, anulados
from .util import dinero, fecha, numero, texto, usd

TIPOS_EXPEDIENTE = {
    "PERMISO": ("Permiso", ("Solicitado", "Aprobado", "Rechazado", "Cancelado")),
    "VACACIONES": ("Vacaciones", ("Solicitado", "Aprobado", "Rechazado", "Gozadas", "Cancelado")),
    "INCAPACIDAD": ("Incapacidad", ("Registrada", "Validada", "Cerrada")),
    "CONTRATO": ("Contrato", ("Vigente", "Por renovar", "Vencido", "Finalizado")),
    "DOCUMENTO": ("Documento", ("Pendiente", "Entregado", "Vencido", "No aplica")),
    "OBSERVACION": ("Observación administrativa", ("Registrada",)),
    "INCIDENCIA": ("Incidencia administrativa", ("Abierta", "En seguimiento", "Cerrada")),
    "FECHA_IMPORTANTE": ("Fecha importante", ("Programada", "Cumplida")),
    "CAMBIO_CARGO": ("Cambio de cargo", ("Registrado",)),
    "CAMBIO_SALARIO": ("Cambio de salario", ("Registrado",)),
    "CAMBIO_FORMA_PAGO": ("Cambio de forma de pago", ("Registrado",)),
    "ALTA": ("Alta de colaborador", ("Registrado",)),
    "BAJA": ("Baja de colaborador", ("Registrado",)),
}
TIPOS_MANUALES = ("PERMISO", "VACACIONES", "INCAPACIDAD", "CONTRATO", "DOCUMENTO", "OBSERVACION", "INCIDENCIA", "FECHA_IMPORTANTE")
TIPOS_SOLICITUD = ("PERMISO", "VACACIONES")


def _mov(m):
    return texto(m.get("Movimiento")).upper()


def nuevo_registro(colaborador, tipo, titulo, fecha_inicio="", fecha_fin="", estado="", detalle="", documento="",
                   valor_anterior="", valor_nuevo="", id_operacion=""):
    if not texto(colaborador):
        raise ErrorNegocio("Elige el colaborador.")
    if tipo not in TIPOS_EXPEDIENTE:
        raise ErrorNegocio("Tipo de registro inválido.")
    estados = TIPOS_EXPEDIENTE[tipo][1]
    estado = texto(estado) or estados[0]
    if estado not in estados:
        raise ErrorNegocio(f"Estado «{estado}» inválido para {TIPOS_EXPEDIENTE[tipo][0].lower()}.")
    if not texto(titulo):
        raise ErrorNegocio("Escribe un título o descripción corta.")
    ini = fecha(fecha_inicio) if texto(fecha_inicio) else None
    fin = fecha(fecha_fin) if texto(fecha_fin) else None
    if texto(fecha_inicio) and ini is None or texto(fecha_fin) and fin is None:
        raise ErrorNegocio("Fecha inválida (usa AAAA-MM-DD).")
    if ini and fin and fin < ini:
        raise ErrorNegocio("La fecha final no puede ser anterior a la inicial.")
    if tipo in ("PERMISO", "VACACIONES", "INCAPACIDAD") and not ini:
        raise ErrorNegocio("Indica la fecha de inicio.")
    reg = {"Movimiento": "REGISTRO", "Colaborador": texto(colaborador), "Tipo": tipo, "Titulo": texto(titulo),
           "Fecha_Inicio": ini.strftime("%Y-%m-%d") if ini else "", "Fecha_Fin": fin.strftime("%Y-%m-%d") if fin else "",
           "Estado": estado, "Detalle": texto(detalle), "Documento": texto(documento),
           "Valor_Anterior": texto(valor_anterior), "Valor_Nuevo": texto(valor_nuevo)}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_expediente(movs):
    nulos = anulados(movs)
    cambios = {}
    for m in sorted((m for m in movs if _mov(m) == "ESTADO" and texto(m.get("ID")) not in nulos),
                    key=lambda m: (texto(m.get("Registrado")), texto(m.get("ID")))):
        cambios.setdefault(texto(m.get("Ref_ID")), []).append(m)
    salida = []
    for r in sorted((m for m in movs if _mov(m) == "REGISTRO"), key=lambda m: (texto(m.get("Registrado")), texto(m.get("ID")))):
        rid = texto(r.get("ID"))
        historial = cambios.get(rid, [])
        estado = texto(historial[-1].get("Estado")) if historial else texto(r.get("Estado"))
        tipo = texto(r.get("Tipo"))
        salida.append(dict(r, Estado_Actual="Anulado" if rid in nulos else estado, Historial_Estados=historial,
                           Tipo_Texto=TIPOS_EXPEDIENTE.get(tipo, (tipo,))[0], Anulado=rid in nulos))
    return salida


def preparar_cambio_estado(movs, registro_id, nuevo_estado, comentario=""):
    reg = next((r for r in estado_expediente(movs) if texto(r.get("ID")) == texto(registro_id)), None)
    if reg is None:
        raise ErrorNegocio("No existe ese registro del expediente.")
    if reg["Anulado"]:
        raise ErrorNegocio("Ese registro está anulado.")
    estados = TIPOS_EXPEDIENTE.get(texto(reg.get("Tipo")), ("", ()))[1]
    if nuevo_estado not in estados:
        raise ErrorNegocio("Estado inválido.")
    if nuevo_estado == reg["Estado_Actual"]:
        raise ErrorNegocio("El registro ya tiene ese estado.")
    return {"Movimiento": "ESTADO", "Ref_ID": texto(registro_id), "Colaborador": texto(reg.get("Colaborador")), "Tipo": texto(reg.get("Tipo")),
            "Titulo": texto(reg.get("Titulo")), "Estado": nuevo_estado, "Motivo": texto(comentario)}


def cambios_personal(anteriores, nuevos, sueldo_de):
    """Registros automáticos del historial cuando cambian cargo, sueldo o forma de pago (o hay altas y bajas)."""
    registros = []
    for nombre, info in nuevos.items():
        previo = anteriores.get(nombre)
        if previo is None:
            registros.append(nuevo_registro(nombre, "ALTA", "Alta en el personal", valor_nuevo=f"{info.get('cargo') or info.get('rol', '')}"))
            continue
        if texto(previo.get("cargo")) != texto(info.get("cargo")):
            registros.append(nuevo_registro(nombre, "CAMBIO_CARGO", "Cambio de cargo", valor_anterior=texto(previo.get("cargo")) or "—",
                                            valor_nuevo=texto(info.get("cargo")) or "—"))
        if abs(dinero(sueldo_de(previo)) - dinero(sueldo_de(info))) >= 0.005:
            registros.append(nuevo_registro(nombre, "CAMBIO_SALARIO", "Cambio de sueldo neto quincenal",
                                            valor_anterior=usd(sueldo_de(previo)), valor_nuevo=usd(sueldo_de(info))))
        forma_prev = f"{texto(previo.get('mod'))} {numero(previo.get('porc')):g}%"
        forma_nueva = f"{texto(info.get('mod'))} {numero(info.get('porc')):g}%"
        if forma_prev != forma_nueva:
            registros.append(nuevo_registro(nombre, "CAMBIO_FORMA_PAGO", "Cambio de forma de pago", valor_anterior=forma_prev, valor_nuevo=forma_nueva))
    for nombre in anteriores:
        if nombre not in nuevos:
            registros.append(nuevo_registro(nombre, "BAJA", "Baja del personal", valor_anterior=texto(anteriores[nombre].get("cargo"))))
    return registros


def alertas(hoy, expediente=(), prestamos=(), anticipos=(), cuentas_pagar=(), proveedores=(), dias=30):
    """Alertas ordenadas por urgencia. Cada una: Nivel (Alta/Media/Info), Tipo, Quien, Fecha, Mensaje."""
    hoy = fecha(hoy)
    limite = hoy + timedelta(days=int(dias))
    salida = []

    def agregar(nivel, tipo, quien, cuando, mensaje):
        salida.append({"Nivel": nivel, "Tipo": tipo, "Quien": quien, "Fecha": cuando.strftime("%Y-%m-%d") if cuando else "", "Mensaje": mensaje})

    for r in expediente:
        if r.get("Anulado"):
            continue
        tipo, estado, quien = texto(r.get("Tipo")), texto(r.get("Estado_Actual")), texto(r.get("Colaborador"))
        fin = fecha(r.get("Fecha_Fin"))
        ini = fecha(r.get("Fecha_Inicio"))
        if tipo == "CONTRATO" and estado in ("Vigente", "Por renovar") and fin:
            if fin < hoy:
                agregar("Alta", "Contrato vencido", quien, fin, f"Contrato «{r.get('Titulo')}» venció el {fin:%d/%m/%Y}")
            elif fin <= limite:
                agregar("Media", "Contrato por vencer", quien, fin, f"Contrato «{r.get('Titulo')}» vence en {(fin - hoy).days} días")
        elif tipo == "DOCUMENTO" and estado == "Pendiente":
            nivel = "Alta" if fin and fin < hoy else "Media"
            agregar(nivel, "Documento pendiente", quien, fin, f"Falta entregar «{r.get('Titulo')}»" + (f" (límite {fin:%d/%m/%Y})" if fin else ""))
        elif tipo in ("PERMISO", "VACACIONES") and estado == "Solicitado":
            agregar("Media", "Solicitud por aprobar", quien, ini, f"{r.get('Tipo_Texto')}: {r.get('Titulo')}")
        elif tipo == "INCAPACIDAD" and estado != "Cerrada" and fin and hoy <= fin <= hoy + timedelta(days=3):
            agregar("Info", "Incapacidad por terminar", quien, fin, f"Termina el {fin:%d/%m/%Y}")
        elif tipo == "FECHA_IMPORTANTE" and estado == "Programada" and ini and hoy <= ini <= limite:
            agregar("Info", "Fecha importante", quien, ini, f"{r.get('Titulo')} ({(ini - hoy).days} días)")
    for p in prestamos:
        if p.get("Estado") == "Atrasado":
            agregar("Alta", "Préstamo atrasado", p["Colaborador"], fecha(p.get("Proximo_Vencimiento")), f"Atraso de {usd(p['Atraso'])} · saldo {usd(p['Saldo'])}")
        elif p.get("Estado") == "Vigente" and fecha(p.get("Proximo_Vencimiento")) and fecha(p["Proximo_Vencimiento"]) <= hoy + timedelta(days=7):
            agregar("Info", "Cuota de préstamo próxima", p["Colaborador"], fecha(p["Proximo_Vencimiento"]), f"Cuota de {usd(p['Cuota'])} · saldo {usd(p['Saldo'])}")
    for a in anticipos:
        f = fecha(a.get("Fecha"))
        if a.get("Estado") in ("Pendiente", "Parcial") and f and (hoy - f).days > 30:
            agregar("Media", "Anticipo sin descontar", a["Colaborador"], f, f"Saldo {usd(a['Saldo'])} desde hace {(hoy - f).days} días")
    for c in cuentas_pagar:
        v = fecha(c.get("Vencimiento"))
        if c.get("Estado") == "Vencida":
            agregar("Alta", "Cuenta por pagar vencida", c["Proveedor"], v, f"{c.get('Documento') or c.get('Concepto')} · saldo {usd(c['Saldo'])}")
        elif c.get("Estado") in ("Pendiente", "Parcial") and v and v <= hoy + timedelta(days=7):
            agregar("Media", "Cuenta por pagar próxima", c["Proveedor"], v, f"Vence en {(v - hoy).days} días · saldo {usd(c['Saldo'])}")
    for p in proveedores:
        v = fecha(p.get("Fecha_Vencimiento"))
        nombre = texto(p.get("Nombre_Proveedor")) or "Proveedor"
        if v and v < hoy:
            agregar("Media", "Contrato de proveedor vencido", nombre, v, f"Venció el {v:%d/%m/%Y}")
        elif v and v <= limite:
            agregar("Info", "Contrato de proveedor por vencer", nombre, v, f"Vence en {(v - hoy).days} días")
    orden = {"Alta": 0, "Media": 1, "Info": 2}
    return sorted(salida, key=lambda a: (orden[a["Nivel"]], a["Fecha"] or "9999"))
