"""Pagos al personal, anticipos, préstamos, ajustes de planilla, caja, cuentas por pagar y reportes.

Todo se calcula a partir de MOVIMIENTOS (filas que nunca se editan). Ejemplos:
- Anticipo: ENTREGA de $20 → DESCUENTO en la planilla (una sola vez por período) o DEVOLUCION → saldo $0.
- Préstamo: OTORGAMIENTO de $100 → ABONO de $25 → saldo $75.
- Pago: PAGO → si estaba mal, ANULACION (con motivo) o un PAGO nuevo que lo corrige (Corrige_ID).
"""
import calendar
import re
from datetime import date, timedelta

from .util import CENTAVO, clave_periodo, dinero, fecha, fecha_hora, marca_tiempo, normalizar, numero, rango_de_clave, texto, usd

CONCEPTOS_PLANILLA = ("Sueldo / planilla", "Comisión", "Bono")  # forman parte del total calculado de la planilla
CONCEPTOS_PAGO_DEFECTO = list(CONCEPTOS_PLANILLA) + ["Pago extraordinario", "Reembolso", "Otro"]
METODOS_DEFECTO = ["Efectivo", "Transferencia bancaria", "POS", "Cheque", "Otro"]
FRECUENCIAS = ("Quincenal", "Mensual", "Semanal", "Pago único")
CATEGORIAS_GASTO_DEFECTO = ["Insumos y materiales", "Servicios básicos (luz, agua, internet)", "Alquiler", "Publicidad y pauta",
                            "Mantenimiento", "Transporte", "Papelería y oficina", "Impuestos y trámites",
                            "Comisiones bancarias y POS", "Otros gastos"]
CATEGORIAS_INGRESO_DEFECTO = ["Ventas en efectivo", "Aporte de socios", "Reintegro", "Otros ingresos"]
CAT_PLANILLA = "Planilla y pagos al personal"
CAT_ANTICIPO = "Anticipos a colaboradores (por cobrar)"
CAT_PRESTAMO = "Préstamos a colaboradores (por cobrar)"
CAT_DEV_ANTICIPO = "Devolución de anticipo"
CAT_ABONO = "Abono de préstamo"
CAT_PROVEEDOR = "Pagos a proveedores"
CATEGORIAS_RESERVADAS = (CAT_PLANILLA, CAT_ANTICIPO, CAT_PRESTAMO, CAT_DEV_ANTICIPO, CAT_ABONO, CAT_PROVEEDOR)
MOTIVO_MINIMO = 5


class ErrorNegocio(ValueError):
    """Operación inválida (monto, saldo, duplicado, falta de motivo o de autorización)."""


# ---------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------
def _mov(m):
    return texto(m.get("Movimiento")).upper()


def anulados(movs):
    """IDs anulados por una fila ANULACION (Ref_ID)."""
    return {texto(m.get("Ref_ID")) for m in movs if _mov(m) == "ANULACION" and texto(m.get("Ref_ID"))}


def _orden(m):
    return (texto(m.get("Registrado")), texto(m.get("ID")))


def _exigir_motivo(motivo, que="la operación"):
    if len(texto(motivo)) < MOTIVO_MINIMO:
        raise ErrorNegocio(f"Escribe el motivo de {que} (mínimo {MOTIVO_MINIMO} caracteres): queda registrado en la auditoría.")
    return texto(motivo)


def _exigir_monto(monto, que="El monto"):
    m = dinero(monto)
    if m <= 0:
        raise ErrorNegocio(f"{que} debe ser mayor que $0.00.")
    return m


def _exigir_fecha(v, que="la fecha"):
    f = fecha(v)
    if f is None:
        raise ErrorNegocio(f"Indica {que} con el formato AAAA-MM-DD.")
    return f.strftime("%Y-%m-%d")


def _base_clave(clave):
    return re.sub(r"\|R\d+$", "", texto(clave))


def _clave_libre(movs, base):
    """Clave_Unica para una operación que solo puede existir una vez (salvo que la anterior se haya anulado)."""
    nulos = anulados(movs)
    activas = [m for m in movs if _base_clave(m.get("Clave_Unica")) == base and texto(m.get("ID")) not in nulos]
    if activas:
        return None, activas[0]
    previas = [m for m in movs if _base_clave(m.get("Clave_Unica")) == base]
    return (base if not previas else f"{base}|R{len(previas)}"), None


def anulacion(ref_id, motivo, **extra):
    """Fila ANULACION genérica (válida para cualquier tabla de movimientos)."""
    reg = {"Movimiento": "ANULACION", "Ref_ID": texto(ref_id), "Motivo": _exigir_motivo(motivo, "la anulación")}
    reg.update({k: v for k, v in extra.items() if v not in (None, "")})
    return reg


def _buscar(movs, mov_id, tipo=None):
    for m in movs:
        if texto(m.get("ID")) == texto(mov_id) and (tipo is None or _mov(m) == tipo):
            return m
    return None


# ---------------------------------------------------------------------
# Pagos al personal
# ---------------------------------------------------------------------
def nuevo_pago(colaborador, fecha_pago, concepto, monto, metodo, periodo="", referencia="", negocio="", comprobante="",
               observaciones="", corrige_id="", motivo="", clave_unica="", id_operacion=""):
    if not texto(colaborador):
        raise ErrorNegocio("Elige el colaborador.")
    if not texto(concepto):
        raise ErrorNegocio("Elige el concepto del pago.")
    if not texto(metodo):
        raise ErrorNegocio("Elige el método de pago.")
    reg = {"Movimiento": "PAGO", "Colaborador": texto(colaborador), "Fecha": _exigir_fecha(fecha_pago, "la fecha del pago"),
           "Concepto": texto(concepto), "Periodo": texto(periodo), "Monto": _exigir_monto(monto), "Metodo": texto(metodo),
           "Referencia": texto(referencia), "Negocio": texto(negocio), "Comprobante": texto(comprobante),
           "Observaciones": texto(observaciones), "Clave_Unica": texto(clave_unica)}
    if texto(corrige_id):
        reg["Corrige_ID"] = texto(corrige_id)
        reg["Ref_ID"] = texto(corrige_id)
        reg["Motivo"] = _exigir_motivo(motivo, "la corrección")
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_pagos(movs):
    """Cada PAGO con su estado: Completado, Anulado o Corregido (reemplazado por otro pago)."""
    nulos = anulados(movs)
    pagos = [m for m in movs if _mov(m) == "PAGO"]
    corregido_por = {}
    for p in pagos:
        ref = texto(p.get("Corrige_ID"))
        if ref and texto(p.get("ID")) not in nulos:
            corregido_por[ref] = texto(p.get("ID"))
    salida = []
    for p in sorted(pagos, key=_orden):
        pid = texto(p.get("ID"))
        estado = "Anulado" if pid in nulos else "Corregido" if pid in corregido_por else "Completado"
        motivo_anul = next((texto(a.get("Motivo")) for a in movs if _mov(a) == "ANULACION" and texto(a.get("Ref_ID")) == pid), "")
        salida.append(dict(p, Monto=dinero(p.get("Monto")), Estado=estado, Corregido_Por=corregido_por.get(pid, ""),
                           Motivo_Anulacion=motivo_anul, Sincronizado="⏳ Pendiente" if p.get("_pendiente") else "✅ En la nube"))
    return salida


def pagos_vigentes(movs):
    return [p for p in estado_pagos(movs) if p["Estado"] == "Completado"]


def posibles_duplicados(movs, nuevo):
    """Pagos vigentes iguales (colaborador, fecha, concepto, período y monto): probable doble registro."""
    return [p for p in pagos_vigentes(movs)
            if texto(p.get("Colaborador")) == texto(nuevo.get("Colaborador")) and texto(p.get("Fecha")) == texto(nuevo.get("Fecha"))
            and texto(p.get("Concepto")) == texto(nuevo.get("Concepto")) and texto(p.get("Periodo")) == texto(nuevo.get("Periodo"))
            and abs(dinero(p.get("Monto")) - dinero(nuevo.get("Monto"))) < CENTAVO]


def validar_modificable(movs, pago_id):
    """Solo un pago vigente puede anularse o corregirse (los cambios siempre dejan rastro)."""
    for p in estado_pagos(movs):
        if texto(p.get("ID")) == texto(pago_id):
            if p["Estado"] != "Completado":
                raise ErrorNegocio(f"El pago {pago_id} ya está {p['Estado'].lower()}: no se puede volver a modificar.")
            return p
    raise ErrorNegocio(f"No existe el pago {pago_id}.")


def preparar_anulacion_pago(movs, pago_id, motivo):
    p = validar_modificable(movs, pago_id)
    return anulacion(pago_id, motivo, Colaborador=p.get("Colaborador"), Periodo=p.get("Periodo"), Monto=p.get("Monto"))


def preparar_correccion_pago(movs, pago_id, motivo, **cambios):
    """Pago nuevo que reemplaza al original (el original queda en el historial como «Corregido»)."""
    p = validar_modificable(movs, pago_id)
    datos = {"colaborador": p.get("Colaborador"), "fecha_pago": p.get("Fecha"), "concepto": p.get("Concepto"), "monto": p.get("Monto"),
             "metodo": p.get("Metodo"), "periodo": p.get("Periodo"), "referencia": p.get("Referencia"), "negocio": p.get("Negocio"),
             "comprobante": p.get("Comprobante"), "observaciones": p.get("Observaciones")}
    datos.update({k: v for k, v in cambios.items() if v is not None})
    return nuevo_pago(corrige_id=pago_id, motivo=motivo, **datos)


# ---------------------------------------------------------------------
# Anticipos de sueldo
# ---------------------------------------------------------------------
def nuevo_anticipo(colaborador, monto, momento, metodo, responsable, periodo="", referencia="", comprobante="", observaciones="", id_operacion=""):
    if not texto(colaborador):
        raise ErrorNegocio("Elige el colaborador que recibe el anticipo.")
    if not texto(metodo):
        raise ErrorNegocio("Indica la forma de entrega.")
    if not texto(responsable):
        raise ErrorNegocio("Indica quién entrega el dinero (responsable).")
    momento_dt = fecha_hora(momento) or (fecha_hora(f"{texto(momento)} 00:00") if fecha(momento) else None)
    if momento_dt is None:
        raise ErrorNegocio("Indica la fecha y hora de la entrega.")
    reg = {"Movimiento": "ENTREGA", "Colaborador": texto(colaborador), "Fecha": momento_dt.strftime("%Y-%m-%d %H:%M"),
           "Monto": _exigir_monto(monto, "El anticipo"), "Metodo": texto(metodo), "Responsable": texto(responsable),
           "Periodo": texto(periodo), "Referencia": texto(referencia), "Comprobante": texto(comprobante), "Observaciones": texto(observaciones)}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_anticipos(movs):
    nulos = anulados(movs)
    salida = []
    for e in sorted((m for m in movs if _mov(m) == "ENTREGA"), key=_orden):
        aid = texto(e.get("ID"))
        hijos = [m for m in movs if texto(m.get("Ref_ID")) == aid and _mov(m) in ("DESCUENTO", "DEVOLUCION") and texto(m.get("ID")) not in nulos]
        descuentos = [h for h in hijos if _mov(h) == "DESCUENTO"]
        devoluciones = [h for h in hijos if _mov(h) == "DEVOLUCION"]
        monto = dinero(e.get("Monto"))
        desc = dinero(sum(dinero(h.get("Monto")) for h in descuentos))
        dev = dinero(sum(dinero(h.get("Monto")) for h in devoluciones))
        if aid in nulos:
            estado, saldo = "Anulado", 0.0
        else:
            saldo = dinero(monto - desc - dev)
            estado = "Liquidado" if saldo < CENTAVO else "Parcial" if desc + dev > 0 else "Pendiente"
        salida.append({"ID": aid, "Colaborador": texto(e.get("Colaborador")), "Fecha": texto(e.get("Fecha")), "Monto": monto,
                       "Metodo": texto(e.get("Metodo")), "Responsable": texto(e.get("Responsable")), "Periodo": texto(e.get("Periodo")),
                       "Referencia": texto(e.get("Referencia")), "Observaciones": texto(e.get("Observaciones")),
                       "Descontado": desc, "Devuelto": dev, "Saldo": saldo, "Estado": estado,
                       "Descuentos": descuentos, "Devoluciones": devoluciones, "Pendiente_Sync": bool(e.get("_pendiente"))})
    return salida


def _anticipo(movs, anticipo_id):
    for a in estado_anticipos(movs):
        if a["ID"] == texto(anticipo_id):
            return a
    raise ErrorNegocio(f"No existe el anticipo {anticipo_id}.")


def preparar_descuento_anticipo(movs, anticipo_id, periodo, monto=None, observaciones=""):
    """Descuento del anticipo en la planilla del período. Solo una vez por anticipo y período."""
    a = _anticipo(movs, anticipo_id)
    if a["Estado"] == "Anulado":
        raise ErrorNegocio("Ese anticipo está anulado.")
    if not texto(periodo):
        raise ErrorNegocio("Indica el período de planilla en el que se descuenta.")
    if a["Saldo"] < CENTAVO:
        raise ErrorNegocio("Ese anticipo ya no tiene saldo pendiente.")
    m = a["Saldo"] if monto is None else _exigir_monto(monto, "El descuento")
    if m > a["Saldo"] + CENTAVO:
        raise ErrorNegocio(f"El descuento ({usd(m)}) supera el saldo del anticipo ({usd(a['Saldo'])}).")
    clave, existente = _clave_libre(movs, f"DESC|{a['ID']}|{texto(periodo)}")
    if existente is not None:
        raise ErrorNegocio(f"Este anticipo ya se descontó en la planilla de {periodo} ({usd(existente.get('Monto'))}). No se descuenta dos veces.")
    return {"Movimiento": "DESCUENTO", "Ref_ID": a["ID"], "Colaborador": a["Colaborador"], "Monto": m, "Periodo": texto(periodo),
            "Fecha": marca_tiempo()[:16], "Observaciones": texto(observaciones), "Clave_Unica": clave}


def preparar_devolucion_anticipo(movs, anticipo_id, monto, metodo, momento="", referencia="", observaciones=""):
    """El colaborador devuelve el dinero: baja el saldo sin descontarle de su sueldo."""
    a = _anticipo(movs, anticipo_id)
    if a["Estado"] == "Anulado":
        raise ErrorNegocio("Ese anticipo está anulado.")
    m = _exigir_monto(monto, "La devolución")
    if m > a["Saldo"] + CENTAVO:
        raise ErrorNegocio(f"La devolución ({usd(m)}) supera el saldo del anticipo ({usd(a['Saldo'])}).")
    if not texto(metodo):
        raise ErrorNegocio("Indica cómo se recibió la devolución.")
    return {"Movimiento": "DEVOLUCION", "Ref_ID": a["ID"], "Colaborador": a["Colaborador"], "Monto": m, "Metodo": texto(metodo),
            "Fecha": texto(momento) or marca_tiempo()[:16], "Referencia": texto(referencia), "Observaciones": texto(observaciones)}


def preparar_anulacion_anticipo(movs, anticipo_id, motivo):
    a = _anticipo(movs, anticipo_id)
    if a["Estado"] == "Anulado":
        raise ErrorNegocio("Ese anticipo ya está anulado.")
    if a["Descuentos"] or a["Devoluciones"]:
        raise ErrorNegocio("El anticipo tiene descuentos o devoluciones registrados: anúlalos primero (cada uno con su motivo).")
    return anulacion(a["ID"], motivo, Colaborador=a["Colaborador"], Monto=a["Monto"])


def preparar_anulacion_movimiento(movs, mov_id, motivo, tipos=("DESCUENTO", "DEVOLUCION", "ABONO", "CUOTA_PLANILLA", "PAGO", "MOVIMIENTO")):
    m = _buscar(movs, mov_id)
    if m is None or _mov(m) not in tipos:
        raise ErrorNegocio(f"No existe el movimiento {mov_id}.")
    if texto(mov_id) in anulados(movs):
        raise ErrorNegocio("Ese movimiento ya está anulado.")
    return anulacion(mov_id, motivo, Colaborador=m.get("Colaborador"), Monto=m.get("Monto"), Periodo=m.get("Periodo"))


def anticipos_aplicados(movs, periodo):
    """{colaborador: total descontado de anticipos en la planilla del período}."""
    nulos = anulados(movs)
    total = {}
    for m in movs:
        if _mov(m) == "DESCUENTO" and texto(m.get("Periodo")) == texto(periodo) and texto(m.get("ID")) not in nulos:
            c = texto(m.get("Colaborador"))
            total[c] = dinero(total.get(c, 0.0) + dinero(m.get("Monto")))
    return total


# ---------------------------------------------------------------------
# Préstamos
# ---------------------------------------------------------------------
def _sumar_meses(d, n):
    mes = d.month - 1 + n
    anio, mes = d.year + mes // 12, mes % 12 + 1
    return date(anio, mes, min(d.day, calendar.monthrange(anio, mes)[1]))


def fechas_vencimiento(primer, frecuencia, cuotas):
    primer = fecha(primer)
    if primer is None:
        return []
    n = max(1, int(numero(cuotas, 1)))
    if frecuencia == "Pago único":
        return [primer]
    salida = []
    for i in range(n):
        if frecuencia == "Mensual":
            salida.append(_sumar_meses(primer, i))
        elif frecuencia == "Semanal":
            salida.append(primer + timedelta(days=7 * i))
        else:  # Quincenal: cada 15 días calendario
            salida.append(primer + timedelta(days=15 * i))
    return salida


def nuevo_prestamo(colaborador, capital, fecha_prestamo, cuotas, cuota_monto, frecuencia, primer_vencimiento, condiciones,
                   autorizado_por, metodo, documento="", observaciones="", id_operacion=""):
    if not texto(colaborador):
        raise ErrorNegocio("Elige el colaborador.")
    cap = _exigir_monto(capital, "El capital")
    n = int(numero(cuotas, 0))
    if n < 1:
        raise ErrorNegocio("El número de cuotas debe ser 1 o más.")
    cuota = _exigir_monto(cuota_monto, "La cuota")
    if cuota * n + CENTAVO < cap:
        raise ErrorNegocio(f"{n} cuota(s) de {usd(cuota)} no cubren el capital de {usd(cap)}.")
    if cuota > cap + CENTAVO:
        raise ErrorNegocio("La cuota no puede ser mayor que el capital.")
    if frecuencia not in FRECUENCIAS:
        raise ErrorNegocio("Elige la frecuencia de las cuotas.")
    if not texto(condiciones):
        raise ErrorNegocio("Describe las condiciones acordadas (cómo y cuándo se devolverá).")
    if not texto(autorizado_por):
        raise ErrorNegocio("Indica quién autorizó el préstamo.")
    if not texto(metodo):
        raise ErrorNegocio("Indica cómo se entregó el dinero.")
    reg = {"Movimiento": "OTORGAMIENTO", "Colaborador": texto(colaborador), "Fecha": _exigir_fecha(fecha_prestamo, "la fecha del préstamo"),
           "Monto": cap, "Metodo": texto(metodo), "Cuotas": n, "Cuota_Monto": cuota, "Frecuencia": frecuencia,
           "Primer_Vencimiento": _exigir_fecha(primer_vencimiento, "el primer vencimiento"), "Condiciones": texto(condiciones),
           "Autorizado_Por": texto(autorizado_por), "Documento": texto(documento), "Observaciones": texto(observaciones)}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_prestamos(movs, hoy=None):
    hoy = fecha(hoy) or date.today()
    nulos = anulados(movs)
    salida = []
    for o in sorted((m for m in movs if _mov(m) == "OTORGAMIENTO"), key=_orden):
        pid = texto(o.get("ID"))
        hijos = sorted((m for m in movs if texto(m.get("Ref_ID")) == pid and texto(m.get("ID")) not in nulos
                        and _mov(m) in ("ABONO", "CUOTA_PLANILLA", "REESTRUCTURACION", "CANCELACION")), key=_orden)
        pagos = [h for h in hijos if _mov(h) in ("ABONO", "CUOTA_PLANILLA")]
        cancel = [h for h in hijos if _mov(h) == "CANCELACION"]
        reestr = [h for h in hijos if _mov(h) == "REESTRUCTURACION"]
        capital = dinero(o.get("Monto"))
        pagado = dinero(sum(dinero(p.get("Monto")) for p in pagos))
        condonado = dinero(sum(dinero(c.get("Monto")) for c in cancel))
        saldo = max(0.0, dinero(capital - pagado - condonado))
        base = reestr[-1] if reestr else o
        cuota = dinero(base.get("Cuota_Monto"))
        frecuencia = texto(base.get("Frecuencia")) or "Quincenal"
        n_cuotas = int(numero(base.get("Cuotas"), 1))
        vencimientos = fechas_vencimiento(base.get("Primer_Vencimiento"), frecuencia, n_cuotas)
        pagado_antes = 0.0
        if reestr:
            corte = texto(base.get("Registrado"))
            pagado_antes = dinero(sum(dinero(p.get("Monto")) for p in pagos if texto(p.get("Registrado")) <= corte))
        objetivo = dinero(capital - condonado)
        vencidas = sum(1 for v in vencimientos if v <= hoy)
        esperado = min(objetivo, dinero(pagado_antes + vencidas * cuota))
        atraso = max(0.0, dinero(esperado - pagado))
        proximo = None
        acumulado = pagado_antes
        for v in vencimientos:
            acumulado = min(objetivo, acumulado + cuota)
            if acumulado > pagado + CENTAVO:
                proximo = v
                break
        if pid in nulos:
            estado, saldo, atraso, proximo = "Anulado", 0.0, 0.0, None
        elif cancel and saldo < CENTAVO:
            estado = "Cancelado"
        elif saldo < CENTAVO:
            estado = "Pagado"
        elif atraso > CENTAVO:
            estado = "Atrasado"
        else:
            estado = "Vigente"
        salida.append({"ID": pid, "Colaborador": texto(o.get("Colaborador")), "Fecha": texto(o.get("Fecha")), "Capital": capital,
                       "Pagado": pagado, "Condonado": condonado, "Saldo": saldo, "Cuota": cuota, "Cuotas": n_cuotas,
                       "Frecuencia": frecuencia, "Proximo_Vencimiento": proximo.strftime("%Y-%m-%d") if proximo else "",
                       "Atraso": atraso, "Estado": estado, "Condiciones": texto(o.get("Condiciones")),
                       "Autorizado_Por": texto(o.get("Autorizado_Por")), "Documento": texto(o.get("Documento")),
                       "Movimientos": hijos, "Pendiente_Sync": bool(o.get("_pendiente"))})
    return salida


def _prestamo(movs, prestamo_id, hoy=None):
    for p in estado_prestamos(movs, hoy):
        if p["ID"] == texto(prestamo_id):
            return p
    raise ErrorNegocio(f"No existe el préstamo {prestamo_id}.")


def _prestamo_activo(movs, prestamo_id, hoy=None):
    p = _prestamo(movs, prestamo_id, hoy)
    if p["Estado"] in ("Anulado", "Cancelado", "Pagado"):
        raise ErrorNegocio(f"El préstamo está {p['Estado'].lower()}: no admite más movimientos.")
    return p


def preparar_abono(movs, prestamo_id, monto, metodo, fecha_abono, referencia="", observaciones="", hoy=None):
    p = _prestamo_activo(movs, prestamo_id, hoy)
    m = _exigir_monto(monto, "El abono")
    if m > p["Saldo"] + CENTAVO:
        raise ErrorNegocio(f"El abono ({usd(m)}) supera el saldo pendiente ({usd(p['Saldo'])}). No se permiten saldos negativos.")
    if not texto(metodo):
        raise ErrorNegocio("Indica cómo se recibió el abono.")
    return {"Movimiento": "ABONO", "Ref_ID": p["ID"], "Colaborador": p["Colaborador"], "Monto": m, "Metodo": texto(metodo),
            "Fecha": _exigir_fecha(fecha_abono, "la fecha del abono"), "Referencia": texto(referencia), "Observaciones": texto(observaciones)}


def preparar_cuota_planilla(movs, prestamo_id, periodo, monto, autorizado_por, hoy=None):
    """Cuota descontada en la planilla: requiere autorización y solo una vez por préstamo y período."""
    p = _prestamo_activo(movs, prestamo_id, hoy)
    if not texto(periodo):
        raise ErrorNegocio("Indica el período de planilla.")
    if not texto(autorizado_por):
        raise ErrorNegocio("Indica quién autoriza descontar la cuota en la planilla.")
    m = _exigir_monto(monto, "La cuota")
    if m > p["Saldo"] + CENTAVO:
        raise ErrorNegocio(f"La cuota ({usd(m)}) supera el saldo pendiente ({usd(p['Saldo'])}).")
    clave, existente = _clave_libre(movs, f"CUOTA|{p['ID']}|{texto(periodo)}")
    if existente is not None:
        raise ErrorNegocio(f"Ya se descontó una cuota de este préstamo en la planilla de {periodo}. No se cobra dos veces.")
    return {"Movimiento": "CUOTA_PLANILLA", "Ref_ID": p["ID"], "Colaborador": p["Colaborador"], "Monto": m, "Periodo": texto(periodo),
            "Autorizado_Por": texto(autorizado_por), "Fecha": marca_tiempo()[:10], "Clave_Unica": clave,
            "Observaciones": f"Saldo anterior {usd(p['Saldo'])} → nuevo saldo {usd(p['Saldo'] - m)}"}


def preparar_reestructuracion(movs, prestamo_id, cuota_monto, cuotas, frecuencia, primer_vencimiento, motivo, autorizado_por, hoy=None):
    p = _prestamo_activo(movs, prestamo_id, hoy)
    cuota = _exigir_monto(cuota_monto, "La nueva cuota")
    n = int(numero(cuotas, 0))
    if n < 1:
        raise ErrorNegocio("Indica cuántas cuotas quedan.")
    if cuota * n + CENTAVO < p["Saldo"]:
        raise ErrorNegocio(f"{n} cuota(s) de {usd(cuota)} no cubren el saldo pendiente de {usd(p['Saldo'])}.")
    if frecuencia not in FRECUENCIAS:
        raise ErrorNegocio("Elige la frecuencia.")
    if not texto(autorizado_por):
        raise ErrorNegocio("Indica quién autorizó la reestructuración.")
    return {"Movimiento": "REESTRUCTURACION", "Ref_ID": p["ID"], "Colaborador": p["Colaborador"], "Cuota_Monto": cuota, "Cuotas": n,
            "Frecuencia": frecuencia, "Primer_Vencimiento": _exigir_fecha(primer_vencimiento, "el próximo vencimiento"),
            "Motivo": _exigir_motivo(motivo, "la reestructuración"), "Autorizado_Por": texto(autorizado_por), "Monto": p["Saldo"]}


def preparar_cancelacion(movs, prestamo_id, motivo, autorizado_por, hoy=None):
    """Cancelación justificada del saldo (condonación): el saldo queda en $0 y se conserva todo el historial."""
    p = _prestamo_activo(movs, prestamo_id, hoy)
    if not texto(autorizado_por):
        raise ErrorNegocio("Indica quién autorizó cancelar el saldo.")
    return {"Movimiento": "CANCELACION", "Ref_ID": p["ID"], "Colaborador": p["Colaborador"], "Monto": p["Saldo"],
            "Motivo": _exigir_motivo(motivo, "la cancelación"), "Autorizado_Por": texto(autorizado_por), "Fecha": marca_tiempo()[:10]}


def preparar_anulacion_prestamo(movs, prestamo_id, motivo, hoy=None):
    p = _prestamo(movs, prestamo_id, hoy)
    if p["Estado"] == "Anulado":
        raise ErrorNegocio("Ese préstamo ya está anulado.")
    if any(_mov(m) in ("ABONO", "CUOTA_PLANILLA") for m in p["Movimientos"]):
        raise ErrorNegocio("El préstamo tiene abonos o cuotas registrados: no se anula. Usa «Cancelar saldo» si corresponde.")
    return anulacion(p["ID"], motivo, Colaborador=p["Colaborador"], Monto=p["Capital"])


def cuotas_aplicadas(movs, periodo):
    nulos = anulados(movs)
    total = {}
    for m in movs:
        if _mov(m) == "CUOTA_PLANILLA" and texto(m.get("Periodo")) == texto(periodo) and texto(m.get("ID")) not in nulos:
            c = texto(m.get("Colaborador"))
            total[c] = dinero(total.get(c, 0.0) + dinero(m.get("Monto")))
    return total


# ---------------------------------------------------------------------
# Ajustes de una planilla ya pagada e integración con la planilla
# ---------------------------------------------------------------------
def preparar_ajuste_planilla(periodo, colaborador, anterior, nuevo, motivo):
    anterior, nuevo = dinero(anterior), dinero(nuevo)
    if abs(nuevo - anterior) < CENTAVO:
        raise ErrorNegocio("No hay diferencia que ajustar.")
    return {"Movimiento": "AJUSTE", "Periodo": texto(periodo), "Colaborador": texto(colaborador), "Calculado_Anterior": anterior,
            "Calculado_Nuevo": nuevo, "Diferencia": dinero(nuevo - anterior), "Motivo": _exigir_motivo(motivo, "el ajuste"),
            "Clave_Unica": f"AJU|{texto(periodo)}|{texto(colaborador)}|{anterior:.2f}>{nuevo:.2f}"}


def ajustes_periodo(movs, periodo):
    nulos = anulados(movs)
    total = {}
    for m in movs:
        if _mov(m) == "AJUSTE" and texto(m.get("Periodo")) == texto(periodo) and texto(m.get("ID")) not in nulos:
            c = texto(m.get("Colaborador"))
            total[c] = dinero(total.get(c, 0.0) + dinero(m.get("Diferencia")))
    return total


def entregado_periodo(pagos_movs, periodo):
    """{colaborador: lo entregado como sueldo/comisión/bono de ese período} (sin pagos anulados ni corregidos)."""
    total = {}
    for p in pagos_vigentes(pagos_movs):
        if texto(p.get("Periodo")) == texto(periodo) and texto(p.get("Concepto")) in CONCEPTOS_PLANILLA:
            c = texto(p.get("Colaborador"))
            total[c] = dinero(total.get(c, 0.0) + dinero(p.get("Monto")))
    return total


def resumen_pagos_periodo(periodo, calculado, pagos_movs=(), anticipos_movs=(), prestamos_movs=(), ajustes_movs=(), guardado=True):
    """Calculado vs. entregado por colaborador para un período de planilla.

    calculado: {colaborador: total de la planilla (fórmula original, sin tocar)}.
    Neto a entregar = calculado + ajustes − anticipos aplicados − cuotas de préstamo aplicadas.
    """
    ajustes = ajustes_periodo(list(ajustes_movs), periodo)
    anticipos = anticipos_aplicados(list(anticipos_movs), periodo)
    cuotas = cuotas_aplicadas(list(prestamos_movs), periodo)
    entregado = entregado_periodo(list(pagos_movs), periodo)
    nombres = list(dict.fromkeys(list(calculado) + list(entregado) + list(anticipos) + list(cuotas) + list(ajustes)))
    filas = []
    for c in nombres:
        calc = dinero(calculado.get(c, 0.0))
        aj = ajustes.get(c, 0.0)
        ant = anticipos.get(c, 0.0)
        cuo = cuotas.get(c, 0.0)
        neto = dinero(calc + aj - ant - cuo)
        ent = entregado.get(c, 0.0)
        pend = dinero(neto - ent)
        if ent > neto + CENTAVO:
            estado = "Revisar: entregado de más"
        elif neto < CENTAVO and ent < CENTAVO:
            estado = "Sin saldo por entregar"
        elif pend < CENTAVO:
            estado = "Completado"
        elif ent >= CENTAVO:
            estado = "Parcial"
        elif not guardado:
            estado = "Calculado"
        else:
            estado = "Pendiente"
        filas.append({"Colaborador": c, "Calculado": calc, "Ajustes": aj, "Anticipos": ant, "Cuotas_Prestamo": cuo, "Neto": neto,
                      "Entregado": ent, "Pendiente": max(0.0, pend), "Estado": estado})
    return filas


# ---------------------------------------------------------------------
# Caja y cuentas por pagar
# ---------------------------------------------------------------------
def nuevo_movimiento_caja(fecha_mov, tipo, categoria, concepto, monto, metodo, negocio="", responsable="", referencia="",
                          comprobante="", observaciones="", id_operacion=""):
    tipo = texto(tipo).upper()
    if tipo not in ("ENTRADA", "SALIDA"):
        raise ErrorNegocio("Indica si es una entrada o una salida de dinero.")
    if texto(categoria) in CATEGORIAS_RESERVADAS:
        raise ErrorNegocio(f"«{categoria}» se registra desde su propio módulo (pagos, anticipos, préstamos o proveedores) para no contarlo dos veces.")
    if not texto(categoria):
        raise ErrorNegocio("Elige la categoría.")
    if not texto(concepto):
        raise ErrorNegocio("Describe el concepto.")
    if not texto(metodo):
        raise ErrorNegocio("Elige el método de pago.")
    reg = {"Movimiento": "MOVIMIENTO", "Fecha": _exigir_fecha(fecha_mov), "Tipo": tipo, "Categoria": texto(categoria),
           "Concepto": texto(concepto), "Monto": _exigir_monto(monto), "Metodo": texto(metodo), "Negocio": texto(negocio),
           "Responsable": texto(responsable), "Referencia": texto(referencia), "Comprobante": texto(comprobante),
           "Observaciones": texto(observaciones)}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_caja(movs):
    nulos = anulados(movs)
    return [dict(m, Monto=dinero(m.get("Monto")), Estado="Anulado" if texto(m.get("ID")) in nulos else "Registrado")
            for m in sorted((m for m in movs if _mov(m) == "MOVIMIENTO"), key=_orden)]


def nueva_factura(movs, proveedor, documento, fecha_doc, vencimiento, monto, concepto, categoria="", negocio="", observaciones="",
                  comprobante="", id_operacion=""):
    if not texto(proveedor):
        raise ErrorNegocio("Indica el proveedor.")
    f = _exigir_fecha(fecha_doc, "la fecha del documento")
    v = _exigir_fecha(vencimiento, "el vencimiento")
    if v < f:
        raise ErrorNegocio("El vencimiento no puede ser anterior a la fecha del documento.")
    if not texto(concepto):
        raise ErrorNegocio("Describe el concepto de la cuenta por pagar.")
    clave = ""
    if texto(documento):
        clave, existente = _clave_libre(movs, f"FAC|{normalizar(proveedor)}|{normalizar(documento)}")
        if existente is not None:
            raise ErrorNegocio(f"El documento {documento} de {proveedor} ya está registrado ({existente.get('ID')}).")
    reg = {"Movimiento": "FACTURA", "Proveedor": texto(proveedor), "Documento": texto(documento), "Fecha": f, "Vencimiento": v,
           "Monto": _exigir_monto(monto), "Concepto": texto(concepto), "Categoria": texto(categoria), "Negocio": texto(negocio),
           "Observaciones": texto(observaciones), "Comprobante": texto(comprobante), "Clave_Unica": clave}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def estado_cxp(movs, hoy=None):
    hoy = fecha(hoy) or date.today()
    nulos = anulados(movs)
    salida = []
    for f in sorted((m for m in movs if _mov(m) == "FACTURA"), key=_orden):
        fid = texto(f.get("ID"))
        pagos = [m for m in movs if _mov(m) == "PAGO" and texto(m.get("Ref_ID")) == fid and texto(m.get("ID")) not in nulos]
        monto = dinero(f.get("Monto"))
        pagado = dinero(sum(dinero(p.get("Monto")) for p in pagos))
        venc = fecha(f.get("Vencimiento"))
        dias = (venc - hoy).days if venc else None
        if fid in nulos:
            estado, saldo = "Anulada", 0.0
        else:
            saldo = max(0.0, dinero(monto - pagado))
            if saldo < CENTAVO:
                estado = "Pagada"
            elif dias is not None and dias < 0:
                estado = "Vencida"
            elif pagado >= CENTAVO:
                estado = "Parcial"
            else:
                estado = "Pendiente"
        salida.append({"ID": fid, "Proveedor": texto(f.get("Proveedor")), "Documento": texto(f.get("Documento")), "Fecha": texto(f.get("Fecha")),
                       "Vencimiento": texto(f.get("Vencimiento")), "Monto": monto, "Pagado": pagado, "Saldo": saldo, "Estado": estado,
                       "Dias": dias, "Concepto": texto(f.get("Concepto")), "Categoria": texto(f.get("Categoria")),
                       "Negocio": texto(f.get("Negocio")), "Pagos": pagos, "Pendiente_Sync": bool(f.get("_pendiente"))})
    return salida


def preparar_pago_cxp(movs, factura_id, monto, fecha_pago, metodo, referencia="", observaciones="", hoy=None):
    fac = next((f for f in estado_cxp(movs, hoy) if f["ID"] == texto(factura_id)), None)
    if fac is None:
        raise ErrorNegocio(f"No existe la cuenta por pagar {factura_id}.")
    if fac["Estado"] in ("Anulada", "Pagada"):
        raise ErrorNegocio(f"La cuenta está {fac['Estado'].lower()}.")
    m = _exigir_monto(monto, "El pago")
    if m > fac["Saldo"] + CENTAVO:
        raise ErrorNegocio(f"El pago ({usd(m)}) supera el saldo pendiente ({usd(fac['Saldo'])}).")
    if not texto(metodo):
        raise ErrorNegocio("Elige el método de pago.")
    return {"Movimiento": "PAGO", "Ref_ID": fac["ID"], "Proveedor": fac["Proveedor"], "Documento": fac["Documento"], "Monto": m,
            "Fecha": _exigir_fecha(fecha_pago, "la fecha del pago"), "Metodo": texto(metodo), "Referencia": texto(referencia),
            "Categoria": fac["Categoria"], "Negocio": fac["Negocio"], "Observaciones": texto(observaciones)}


def preparar_anulacion_factura(movs, factura_id, motivo, hoy=None):
    fac = next((f for f in estado_cxp(movs, hoy) if f["ID"] == texto(factura_id)), None)
    if fac is None:
        raise ErrorNegocio(f"No existe la cuenta por pagar {factura_id}.")
    if fac["Estado"] == "Anulada":
        raise ErrorNegocio("Ya está anulada.")
    if fac["Pagos"]:
        raise ErrorNegocio("Tiene pagos registrados: anula primero cada pago (con su motivo).")
    return anulacion(fac["ID"], motivo, Proveedor=fac["Proveedor"], Monto=fac["Monto"])


# ---------------------------------------------------------------------
# Reportes (cada movimiento de dinero aparece UNA sola vez)
# ---------------------------------------------------------------------
def movimientos_caja_unificados(caja=(), pagos=(), anticipos=(), prestamos=(), cxp=(), negocio_de=None):
    """Flujo real de dinero: caja manual + módulos. Los descuentos en planilla no son dinero: no aparecen aquí."""
    negocio_de = negocio_de or {}
    filas = []

    def agregar(origen, m, tipo, categoria, concepto, negocio=""):
        filas.append({"Fecha": fecha(m.get("Fecha")), "Tipo": tipo, "Categoria": categoria, "Concepto": concepto,
                      "Monto": dinero(m.get("Monto")), "Metodo": texto(m.get("Metodo")), "Negocio": negocio or "Sin asignar",
                      "Origen": origen, "Ref_ID": texto(m.get("ID")), "Pendiente": bool(m.get("_pendiente"))})

    for m in estado_caja(list(caja)):
        if m["Estado"] == "Registrado":
            agregar("Caja", m, texto(m.get("Tipo")), texto(m.get("Categoria")), texto(m.get("Concepto")), texto(m.get("Negocio")))
    for p in pagos_vigentes(list(pagos)):
        c = texto(p.get("Colaborador"))
        agregar("Pagos al personal", p, "SALIDA", CAT_PLANILLA, f"{p.get('Concepto')} · {c}", texto(p.get("Negocio")) or negocio_de.get(c, ""))
    ant = list(anticipos)
    nulos_ant = anulados(ant)
    for m in ant:
        if texto(m.get("ID")) in nulos_ant:
            continue
        c = texto(m.get("Colaborador"))
        if _mov(m) == "ENTREGA":
            agregar("Anticipos", m, "SALIDA", CAT_ANTICIPO, f"Anticipo · {c}", negocio_de.get(c, ""))
        elif _mov(m) == "DEVOLUCION":
            agregar("Anticipos", m, "ENTRADA", CAT_DEV_ANTICIPO, f"Devolución de anticipo · {c}", negocio_de.get(c, ""))
    pre = list(prestamos)
    nulos_pre = anulados(pre)
    for m in pre:
        if texto(m.get("ID")) in nulos_pre:
            continue
        c = texto(m.get("Colaborador"))
        if _mov(m) == "OTORGAMIENTO":
            agregar("Préstamos", m, "SALIDA", CAT_PRESTAMO, f"Préstamo · {c}", negocio_de.get(c, ""))
        elif _mov(m) == "ABONO":
            agregar("Préstamos", m, "ENTRADA", CAT_ABONO, f"Abono de préstamo · {c}", negocio_de.get(c, ""))
    cx = list(cxp)
    nulos_cx = anulados(cx)
    for m in cx:
        if _mov(m) == "PAGO" and texto(m.get("ID")) not in nulos_cx and texto(m.get("Ref_ID")) not in nulos_cx:
            agregar("Cuentas por pagar", m, "SALIDA", CAT_PROVEEDOR, f"{m.get('Proveedor')} · {m.get('Documento') or 'sin documento'}", texto(m.get("Negocio")))
    return sorted(filas, key=lambda f: (f["Fecha"] or date.min, f["Ref_ID"]))


def gastos_devengados(caja=(), cxp=(), planilla=(), negocio_de=None, hoy=None):
    """Gastos del negocio (no flujo de caja): salidas de caja + documentos de proveedores + costo de planilla calculado.

    planilla: filas de Historial_Planillas (Colaborador, Hasta, Total).
    Los anticipos y préstamos NO son gasto: son cuentas por cobrar.
    """
    negocio_de = negocio_de or {}
    filas = []
    for m in estado_caja(list(caja)):
        if m["Estado"] == "Registrado" and texto(m.get("Tipo")) == "SALIDA":
            filas.append({"Fecha": fecha(m.get("Fecha")), "Categoria": texto(m.get("Categoria")), "Concepto": texto(m.get("Concepto")),
                          "Monto": dinero(m.get("Monto")), "Negocio": texto(m.get("Negocio")) or "Sin asignar", "Origen": "Caja"})
    for f in estado_cxp(list(cxp), hoy):
        if f["Estado"] != "Anulada":
            filas.append({"Fecha": fecha(f["Fecha"]), "Categoria": f["Categoria"] or "Proveedores", "Concepto": f"{f['Proveedor']} · {f['Concepto']}",
                          "Monto": f["Monto"], "Negocio": f["Negocio"] or "Sin asignar", "Origen": "Cuentas por pagar"})
    for r in planilla:
        c = texto(r.get("Colaborador"))
        filas.append({"Fecha": fecha(r.get("Hasta")), "Categoria": "Planilla (calculada)", "Concepto": f"Planilla · {c}",
                      "Monto": dinero(r.get("Total")), "Negocio": negocio_de.get(c, "") or "Sin asignar", "Origen": "Planilla"})
    return filas


def filtrar_fechas(filas, desde=None, hasta=None, campo="Fecha"):
    desde, hasta = fecha(desde), fecha(hasta)
    salida = []
    for f in filas:
        d = fecha(f.get(campo))
        if d is None:
            continue
        if desde and d < desde:
            continue
        if hasta and d > hasta:
            continue
        salida.append(f)
    return salida


def periodo_en_rango(clave, desde, hasta):
    """True si el período de planilla termina dentro del rango."""
    r = rango_de_clave(clave)
    if not r:
        return False
    fin = r[1]
    return (not desde or fin >= fecha(desde)) and (not hasta or fin <= fecha(hasta))


def periodo_de_fechas(inicio, fin):
    return clave_periodo(inicio, fin)
