"""Visitas, encuestas de satisfacción y cupones de descuento.

- Visita: la registra recepción y genera un código (que va en el QR).
- Encuesta: la responde el cliente desde su teléfono; solo una por visita.
- Cupón: se emite al responder (una sola vez por visita) y se canjea una sola vez, sin pasar de su vencimiento.
Todo se guarda como filas nuevas (nunca se edita ni se borra una fila).
"""
import re
import secrets
from datetime import timedelta

from .finanzas import ErrorNegocio, anulados
from .util import ahora_sv, fecha, numero, texto

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para que sea fácil de leer
FORMATO_CODIGO = re.compile(r"^[A-Z0-9]{6,16}$")
RESPUESTAS_SATISFACCION = ["5 - Muy satisfecho", "4 - Satisfecho", "3 - Regular", "2 - Insatisfecho", "1 - Muy insatisfecho"]
RESPUESTAS_ATENCION = ["Muy amable y profesional", "Buena, sin inconvenientes", "Poco amable o incómoda", "Me sentí mal atendido/a"]
RESPUESTAS_PAGOS = ["No, todo estuvo claro", "Sí, me solicitaron un extra", "Pagué directamente a la persona", "No estoy seguro/a"]
ATENCION_BUENA = RESPUESTAS_ATENCION[:2]
PAGO_LIMPIO = RESPUESTAS_PAGOS[0]


def _mov(m):
    return texto(m.get("Movimiento")).upper()


def codigo_nuevo(prefijo="", largo=8):
    return prefijo + "".join(secrets.choice(ALFABETO) for _ in range(largo))


def codigo_valido(codigo):
    return bool(FORMATO_CODIGO.match(texto(codigo).upper()))


def nueva_visita(colaborador, marca, servicio, precio, codigo=None):
    if not texto(colaborador):
        raise ErrorNegocio("Elige al colaborador que atendió.")
    if not texto(servicio):
        raise ErrorNegocio("Escribe el servicio realizado.")
    if numero(precio) <= 0:
        raise ErrorNegocio("El precio debe ser mayor que $0.00.")
    codigo = texto(codigo).upper() or codigo_nuevo()
    return {"Movimiento": "VISITA", "Codigo": codigo, "Fecha": ahora_sv().strftime("%Y-%m-%d %H:%M"), "Marca": texto(marca),
            "Colaborador": texto(colaborador), "Servicio": texto(servicio), "Precio": round(numero(precio), 2), "Estado": "Completada",
            "Clave_Unica": f"VIS|{codigo}"}


def buscar_visita(visitas, codigo):
    """La visita vigente de ese código (None si no existe o fue cancelada)."""
    codigo = texto(codigo).upper()
    if not codigo_valido(codigo):
        return None
    nulos = anulados(visitas)
    for v in visitas:
        if _mov(v) == "VISITA" and texto(v.get("Codigo")).upper() == codigo:
            return None if texto(v.get("ID")) in nulos else v
    return None


def encuesta_de(encuestas, codigo):
    return next((e for e in encuestas if _mov(e) == "ENCUESTA" and texto(e.get("Codigo_Visita")).upper() == texto(codigo).upper()), None)


def cupon_de_visita(cupones, codigo):
    nulos = anulados(cupones)
    for c in cupones:
        if _mov(c) == "EMISION" and texto(c.get("Codigo_Visita")).upper() == texto(codigo).upper() and texto(c.get("ID")) not in nulos:
            return c
    return None


def nueva_encuesta(codigo, satisfaccion, atencion, pagos, comentario=""):
    if satisfaccion not in RESPUESTAS_SATISFACCION or atencion not in RESPUESTAS_ATENCION or pagos not in RESPUESTAS_PAGOS:
        raise ErrorNegocio("Responde las tres preguntas.")
    codigo = texto(codigo).upper()
    return {"Movimiento": "ENCUESTA", "Codigo_Visita": codigo, "P1_Satisfaccion": int(satisfaccion[0]), "P2_Atencion": atencion,
            "P3_Pagos": pagos, "Comentario": texto(comentario)[:500], "Fecha": ahora_sv().strftime("%Y-%m-%d %H:%M"),
            "Clave_Unica": f"ENC|{codigo}"}


def nuevo_cupon(codigo_visita, descuento_pct=5, vigencia_dias=60):
    codigo_visita = texto(codigo_visita).upper()
    pct = int(numero(descuento_pct, 5))
    return {"Movimiento": "EMISION", "Codigo_Cupon": codigo_nuevo("GIO-", 6), "Codigo_Visita": codigo_visita, "Descuento": f"{pct}% OFF",
            "Vencimiento": (ahora_sv().date() + timedelta(days=int(numero(vigencia_dias, 60)))).strftime("%Y-%m-%d"),
            "Clave_Unica": f"CUP|{codigo_visita}"}


def estado_cupon(cupones, codigo_cupon, hoy=None):
    """(cupón, estado): 'Disponible', 'Canjeado', 'Vencido' o 'Anulado'. (None, 'No existe') si no hay tal código."""
    hoy = fecha(hoy) or ahora_sv().date()
    codigo = texto(codigo_cupon).upper()
    cupon = next((c for c in cupones if _mov(c) == "EMISION" and texto(c.get("Codigo_Cupon")).upper() == codigo), None)
    if cupon is None:
        return None, "No existe"
    nulos = anulados(cupones)
    if texto(cupon.get("ID")) in nulos:
        return cupon, "Anulado"
    if any(_mov(c) == "CANJE" and texto(c.get("Ref_ID")) == texto(cupon.get("ID")) and texto(c.get("ID")) not in nulos for c in cupones):
        return cupon, "Canjeado"
    venc = fecha(cupon.get("Vencimiento"))
    return cupon, ("Vencido" if venc and venc < hoy else "Disponible")


def preparar_canje(cupones, codigo_cupon, hoy=None, observaciones=""):
    cupon, estado = estado_cupon(cupones, codigo_cupon, hoy)
    if estado != "Disponible":
        raise ErrorNegocio({"No existe": "El cupón no existe.", "Canjeado": "Este cupón YA FUE UTILIZADO.",
                            "Vencido": f"El cupón venció el {cupon.get('Vencimiento') if cupon else ''}.", "Anulado": "El cupón está anulado."}[estado])
    return {"Movimiento": "CANJE", "Ref_ID": texto(cupon.get("ID")), "Codigo_Cupon": texto(cupon.get("Codigo_Cupon")),
            "Codigo_Visita": texto(cupon.get("Codigo_Visita")), "Descuento": texto(cupon.get("Descuento")),
            "Observaciones": texto(observaciones), "Clave_Unica": f"CANJE|{texto(cupon.get('Codigo_Cupon')).upper()}"}


def resultados(visitas, encuestas):
    """Resumen por colaborador y lista de respuestas que merecen revisión."""
    nulos = anulados(visitas)
    por_codigo = {texto(v.get("Codigo")).upper(): v for v in visitas if _mov(v) == "VISITA" and texto(v.get("ID")) not in nulos}
    filas, revisar = {}, []
    for e in (x for x in encuestas if _mov(x) == "ENCUESTA"):
        codigo = texto(e.get("Codigo_Visita")).upper()
        visita = por_codigo.get(codigo, {})
        colab = texto(visita.get("Colaborador")) or "(visita no encontrada)"
        p1 = int(numero(e.get("P1_Satisfaccion"), 0))
        f = filas.setdefault(colab, {"Colaborador": colab, "Encuestas": 0, "_suma": 0, "Con alerta": 0})
        f["Encuestas"] += 1
        f["_suma"] += p1
        motivos = []
        if p1 and p1 <= 2:
            motivos.append("Satisfacción baja")
        if texto(e.get("P2_Atencion")) not in ATENCION_BUENA:
            motivos.append("Mala atención")
        if texto(e.get("P3_Pagos")) != PAGO_LIMPIO:
            motivos.append("Posible cobro fuera de precio" if texto(e.get("P3_Pagos")) != RESPUESTAS_PAGOS[3] else "Duda sobre el cobro")
        if motivos:
            f["Con alerta"] += 1
            revisar.append({"Fecha": texto(e.get("Fecha")), "Colaborador": colab, "Servicio": texto(visita.get("Servicio")), "Visita": codigo,
                            "Satisfacción": p1, "Atención": texto(e.get("P2_Atencion")), "Pagos": texto(e.get("P3_Pagos")),
                            "Comentario": texto(e.get("Comentario")), "Motivo": ", ".join(motivos)})
    resumen = [{"Colaborador": f["Colaborador"], "Encuestas": f["Encuestas"], "Satisfacción promedio": round(f["_suma"] / f["Encuestas"], 2),
                "Con alerta": f["Con alerta"]} for f in filas.values()]
    return sorted(resumen, key=lambda r: r["Colaborador"]), sorted(revisar, key=lambda r: r["Fecha"], reverse=True)
