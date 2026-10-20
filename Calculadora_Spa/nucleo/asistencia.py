"""Control de asistencia y horarios.

- Cada marcación guarda la HORA REAL del servidor (Registrado) y la HORA EFECTIVA (Fecha_Hora).
  Si un administrador corrige una hora, se agrega una fila CORRECCION con motivo: la original no se borra.
- No puede haber dos entradas abiertas ni una salida sin entrada.
- Los horarios son VERSIONES con vigencia: cambiar un horario no altera los días anteriores.
- Las incidencias (tardanzas, ausencias, horas extra) se informan para revisión: NUNCA generan descuentos automáticos.
- La marcación desde el teléfono NO verifica identidad biométrica ni ubicación.
"""
from datetime import date, datetime, time, timedelta

from .finanzas import ErrorNegocio, anulados
from .util import fecha, fecha_hora, numero, texto

TIPOS = ("ENTRADA", "SALIDA", "INICIO_PAUSA", "FIN_PAUSA")
ETIQUETAS_TIPO = {"ENTRADA": "Entrada", "SALIDA": "Salida", "INICIO_PAUSA": "Inicio de pausa", "FIN_PAUSA": "Fin de pausa"}
DIAS_CLAVE = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
DIAS_NOMBRE = {"Lun": "Lunes", "Mar": "Martes", "Mie": "Miércoles", "Jue": "Jueves", "Vie": "Viernes", "Sab": "Sábado", "Dom": "Domingo"}
ALCANCES = ("Colaborador", "Cargo", "Negocio")
PRIORIDAD_ALCANCE = {"Colaborador": 3, "Cargo": 2, "Negocio": 1}
ESTADO_FUERA, ESTADO_TRABAJANDO, ESTADO_PAUSA = "fuera", "trabajando", "en_pausa"
TIPOS_INCIDENCIA = {
    "TARDANZA": "Tardanza", "SALIDA_ANTICIPADA": "Salida anticipada", "AUSENCIA": "Ausencia",
    "MARCACION_INCOMPLETA": "Marcación incompleta", "HORAS_EXTRA": "Posibles horas extra", "DIA_NO_PROGRAMADO": "Trabajó en día no programado",
}
DECISIONES = ("Justificada", "Aprobada", "Rechazada", "Solo observación")
MINUTOS_MIN_MOTIVO = 5


def _mov(m):
    return texto(m.get("Movimiento")).upper()


# ---------------------------------------------------------------------
# Marcaciones
# ---------------------------------------------------------------------
def nueva_marca(colaborador, tipo, momento, origen="Autoservicio", motivo="", observaciones="", id_operacion=""):
    if not texto(colaborador):
        raise ErrorNegocio("Elige el colaborador.")
    tipo = texto(tipo).upper()
    if tipo not in TIPOS:
        raise ErrorNegocio("Tipo de marcación inválido.")
    dt = fecha_hora(momento)
    if dt is None:
        raise ErrorNegocio("Fecha y hora inválidas.")
    reg = {"Movimiento": "MARCA", "Colaborador": texto(colaborador), "Tipo": tipo, "Fecha_Hora": dt.strftime("%Y-%m-%d %H:%M:%S"),
           "Origen": texto(origen) or "Autoservicio", "Motivo": texto(motivo), "Observaciones": texto(observaciones)}
    if texto(id_operacion):
        reg["ID"] = texto(id_operacion)
    return reg


def marcas_efectivas(movs, colaborador=None):
    """Marcaciones vigentes con su hora efectiva (aplicando correcciones y sin las anuladas), ordenadas."""
    nulos = anulados(movs)
    correcciones = {}
    for m in sorted((m for m in movs if _mov(m) == "CORRECCION" and texto(m.get("ID")) not in nulos),
                    key=lambda m: (texto(m.get("Registrado")), texto(m.get("ID")))):
        correcciones[texto(m.get("Ref_ID"))] = m
    salida = []
    for m in movs:
        if _mov(m) != "MARCA" or texto(m.get("ID")) in nulos:
            continue
        if colaborador and texto(m.get("Colaborador")) != texto(colaborador):
            continue
        original = fecha_hora(m.get("Fecha_Hora"))
        corr = correcciones.get(texto(m.get("ID")))
        efectiva = fecha_hora(corr.get("Fecha_Hora")) if corr else original
        if efectiva is None:
            continue
        salida.append({"ID": texto(m.get("ID")), "Colaborador": texto(m.get("Colaborador")), "Tipo": texto(m.get("Tipo")).upper(),
                       "Fecha_Hora": efectiva, "Hora_Original": original, "Registrado": fecha_hora(m.get("Registrado")),
                       "Origen": texto(m.get("Origen")), "Corregida": corr is not None,
                       "Motivo": texto(corr.get("Motivo")) if corr else texto(m.get("Motivo")),
                       "Usuario": texto(m.get("Usuario")), "Pendiente": bool(m.get("_pendiente"))})
    return sorted(salida, key=lambda x: (x["Colaborador"], x["Fecha_Hora"], x["ID"]))


def _transicion(estado, tipo):
    """Nuevo estado tras una marcación, o None si la secuencia es inválida."""
    reglas = {(ESTADO_FUERA, "ENTRADA"): ESTADO_TRABAJANDO, (ESTADO_TRABAJANDO, "SALIDA"): ESTADO_FUERA,
              (ESTADO_TRABAJANDO, "INICIO_PAUSA"): ESTADO_PAUSA, (ESTADO_PAUSA, "FIN_PAUSA"): ESTADO_TRABAJANDO}
    return reglas.get((estado, tipo))


def secuencia_valida(marcas):
    estado = ESTADO_FUERA
    for m in sorted(marcas, key=lambda x: (x["Fecha_Hora"], x["ID"])):
        estado = _transicion(estado, m["Tipo"])
        if estado is None:
            return False
    return True


def estado_colaborador(marcas_colab):
    estado, desde, ultima = ESTADO_FUERA, None, None
    for m in sorted(marcas_colab, key=lambda x: (x["Fecha_Hora"], x["ID"])):
        nuevo = _transicion(estado, m["Tipo"])
        if nuevo is None:
            continue  # secuencia rota (se reporta como incidencia); no bloquea el cálculo
        estado, ultima = nuevo, m
        if m["Tipo"] == "ENTRADA":
            desde = m["Fecha_Hora"]
        elif m["Tipo"] == "SALIDA":
            desde = None
    return {"estado": estado, "desde": desde, "ultima": ultima}


def validar_marca(movs, colaborador, tipo, momento, pausas_habilitadas=True):
    tipo = texto(tipo).upper()
    momento = fecha_hora(momento)
    marcas = marcas_efectivas(movs, colaborador)
    est = estado_colaborador(marcas)
    if marcas and momento is not None and momento <= marcas[-1]["Fecha_Hora"]:
        raise ErrorNegocio(f"Ya existe una marcación posterior ({marcas[-1]['Fecha_Hora']:%d/%m/%Y %H:%M}). "
                           "Para cambiar una hora pasada, corrige la marcación existente con su justificación.")
    if tipo in ("INICIO_PAUSA", "FIN_PAUSA") and not pausas_habilitadas:
        raise ErrorNegocio("Las pausas no están habilitadas en la configuración.")
    if tipo == "ENTRADA" and est["estado"] != ESTADO_FUERA:
        desde = est["desde"]
        dia = f" del {desde:%d/%m/%Y} a las {desde:%H:%M}" if desde else ""
        extra = " Pide al administrador registrar la salida pendiente con su justificación." if desde and momento and desde.date() < momento.date() else ""
        raise ErrorNegocio(f"Ya tiene una entrada abierta{dia}: no puede marcar otra entrada.{extra}")
    if tipo == "SALIDA" and est["estado"] == ESTADO_PAUSA:
        raise ErrorNegocio("Está en pausa: primero marca el fin de la pausa y luego la salida.")
    if tipo == "SALIDA" and est["estado"] == ESTADO_FUERA:
        raise ErrorNegocio("No hay una entrada abierta: no se puede marcar la salida.")
    if tipo == "INICIO_PAUSA" and est["estado"] != ESTADO_TRABAJANDO:
        raise ErrorNegocio("Solo se puede iniciar una pausa después de marcar la entrada.")
    if tipo == "FIN_PAUSA" and est["estado"] != ESTADO_PAUSA:
        raise ErrorNegocio("No hay una pausa abierta.")
    return est


def preparar_correccion_marca(movs, marca_id, nuevo_momento, motivo):
    if len(texto(motivo)) < MINUTOS_MIN_MOTIVO:
        raise ErrorNegocio("Escribe la justificación de la corrección (mínimo 5 caracteres).")
    nuevo = fecha_hora(nuevo_momento)
    if nuevo is None:
        raise ErrorNegocio("Fecha y hora inválidas.")
    todas = marcas_efectivas(movs)
    marca = next((m for m in todas if m["ID"] == texto(marca_id)), None)
    if marca is None:
        raise ErrorNegocio("No existe esa marcación (o está anulada).")
    otras = [dict(m) for m in todas if m["Colaborador"] == marca["Colaborador"] and m["ID"] != marca["ID"]]
    if not secuencia_valida(otras + [dict(marca, Fecha_Hora=nuevo)]):
        raise ErrorNegocio("Con esa hora la secuencia de entradas y salidas quedaría inválida (por ejemplo, una salida antes de su entrada).")
    return {"Movimiento": "CORRECCION", "Ref_ID": marca["ID"], "Colaborador": marca["Colaborador"], "Tipo": marca["Tipo"],
            "Fecha_Hora": nuevo.strftime("%Y-%m-%d %H:%M:%S"), "Origen": "Administrador", "Motivo": texto(motivo)}


def preparar_anulacion_marca(movs, marca_id, motivo):
    if len(texto(motivo)) < MINUTOS_MIN_MOTIVO:
        raise ErrorNegocio("Escribe la justificación de la anulación (mínimo 5 caracteres).")
    todas = marcas_efectivas(movs)
    marca = next((m for m in todas if m["ID"] == texto(marca_id)), None)
    if marca is None:
        raise ErrorNegocio("No existe esa marcación (o ya está anulada).")
    otras = [m for m in todas if m["Colaborador"] == marca["Colaborador"] and m["ID"] != marca["ID"]]
    if not secuencia_valida(otras):
        raise ErrorNegocio("Anular esta marcación dejaría la secuencia inválida: corrige su hora o anula también la marcación que le sigue.")
    return {"Movimiento": "ANULACION", "Ref_ID": marca["ID"], "Colaborador": marca["Colaborador"], "Tipo": marca["Tipo"],
            "Motivo": texto(motivo), "Origen": "Administrador"}


def jornadas(marcas):
    """Agrupa marcaciones en jornadas (entrada → salida, restando pausas). La jornada pertenece al día de su entrada."""
    salida = []
    por_colab = {}
    for m in marcas:
        por_colab.setdefault(m["Colaborador"], []).append(m)
    for colab, lista in por_colab.items():
        actual = None
        for m in sorted(lista, key=lambda x: (x["Fecha_Hora"], x["ID"])):
            if m["Tipo"] == "ENTRADA":
                if actual:
                    salida.append(actual)
                actual = {"Colaborador": colab, "Fecha": m["Fecha_Hora"].date(), "Entrada": m["Fecha_Hora"], "Salida": None,
                          "Pausa_Min": 0.0, "_pausa_desde": None, "Corregida": m["Corregida"], "Marcas": [m["ID"]]}
            elif actual is None:
                continue
            else:
                actual["Marcas"].append(m["ID"])
                actual["Corregida"] = actual["Corregida"] or m["Corregida"]
                if m["Tipo"] == "INICIO_PAUSA":
                    actual["_pausa_desde"] = m["Fecha_Hora"]
                elif m["Tipo"] == "FIN_PAUSA" and actual["_pausa_desde"]:
                    actual["Pausa_Min"] += (m["Fecha_Hora"] - actual["_pausa_desde"]).total_seconds() / 60
                    actual["_pausa_desde"] = None
                elif m["Tipo"] == "SALIDA":
                    actual["Salida"] = m["Fecha_Hora"]
                    salida.append(actual)
                    actual = None
        if actual:
            salida.append(actual)
    for j in salida:
        j.pop("_pausa_desde", None)
        j["Completa"] = j["Salida"] is not None
        bruto = ((j["Salida"] - j["Entrada"]).total_seconds() / 60) if j["Salida"] else 0.0
        j["Trabajado_Min"] = max(0.0, round(bruto - j["Pausa_Min"], 1))
    return sorted(salida, key=lambda j: (j["Fecha"], j["Colaborador"], j["Entrada"]))


# ---------------------------------------------------------------------
# Horarios versionados
# ---------------------------------------------------------------------
def tramo(v):
    """'08:00-17:00' → (time(8,0), time(17,0)). Vacío → None. Formato inválido → ErrorNegocio."""
    t = texto(v).replace(" ", "")
    if not t:
        return None
    try:
        ini, fin = t.split("-")
        h1, m1 = (int(x) for x in ini.split(":"))
        h2, m2 = (int(x) for x in fin.split(":"))
        a, b = time(h1, m1), time(h2, m2)
    except (ValueError, TypeError):
        raise ErrorNegocio(f"Horario «{v}» inválido: usa el formato 08:00-17:00.")
    if a == b:
        raise ErrorNegocio(f"Horario «{v}»: la entrada y la salida no pueden ser iguales.")
    return a, b


def minutos_tramo(a, b, almuerzo_min=0):
    inicio = datetime.combine(date(2000, 1, 1), a)
    fin = datetime.combine(date(2000, 1, 1) + timedelta(days=1 if b <= a else 0), b)
    return max(0.0, (fin - inicio).total_seconds() / 60 - float(almuerzo_min or 0))


def nueva_version_horario(alcance_tipo, alcance, nombre_turno, vigente_desde, vigente_hasta, dias, almuerzo_min=60,
                          tolerancia_min=10, observaciones=""):
    if alcance_tipo not in ALCANCES:
        raise ErrorNegocio("Elige a quién aplica el horario.")
    if not texto(alcance):
        raise ErrorNegocio("Elige el colaborador, cargo o negocio.")
    desde = fecha(vigente_desde)
    if desde is None:
        raise ErrorNegocio("Indica desde qué fecha rige el horario.")
    hasta = fecha(vigente_hasta) if texto(vigente_hasta) else None
    if hasta and hasta < desde:
        raise ErrorNegocio("La fecha final no puede ser anterior a la inicial.")
    reg = {"Movimiento": "VERSION", "Alcance_Tipo": alcance_tipo, "Alcance": texto(alcance), "Nombre_Turno": texto(nombre_turno) or "Horario",
           "Vigente_Desde": desde.strftime("%Y-%m-%d"), "Vigente_Hasta": hasta.strftime("%Y-%m-%d") if hasta else "",
           "Almuerzo_Min": int(numero(almuerzo_min, 0)), "Tolerancia_Min": int(numero(tolerancia_min, 0)), "Observaciones": texto(observaciones)}
    laborales = 0
    for d in DIAS_CLAVE:
        valor = texto((dias or {}).get(d))
        if tramo(valor):
            laborales += 1
        reg[d] = valor.replace(" ", "")
    if not laborales:
        raise ErrorNegocio("Indica al menos un día laboral (por ejemplo 08:00-17:00).")
    if reg["Almuerzo_Min"] < 0 or reg["Tolerancia_Min"] < 0:
        raise ErrorNegocio("El almuerzo y la tolerancia no pueden ser negativos.")
    return reg


def versiones_vigentes(horarios_movs):
    nulos = anulados(horarios_movs)
    return [h for h in horarios_movs if _mov(h) == "VERSION" and texto(h.get("ID")) not in nulos]


def resolver_horario(horarios_movs, colaborador, cargo, negocio, dia):
    """Horario que rige ese día: primero el del colaborador, luego el de su cargo y luego el de su negocio.
    Entre versiones del mismo nivel gana la de vigencia más reciente (así funcionan los turnos especiales)."""
    dia = fecha(dia)
    candidatos = []
    for h in versiones_vigentes(horarios_movs):
        tipo, alcance = texto(h.get("Alcance_Tipo")), texto(h.get("Alcance"))
        objetivo = {"Colaborador": colaborador, "Cargo": cargo, "Negocio": negocio}.get(tipo)
        if not objetivo or alcance.lower() != texto(objetivo).lower():
            continue
        desde, hasta = fecha(h.get("Vigente_Desde")), fecha(h.get("Vigente_Hasta"))
        if desde is None or desde > dia or (hasta and hasta < dia):
            continue
        candidatos.append((PRIORIDAD_ALCANCE[tipo], desde, texto(h.get("Registrado")), h))
    if not candidatos:
        return None
    h = max(candidatos, key=lambda c: c[:3])[3]
    clave = DIAS_CLAVE[dia.weekday()]
    t = tramo(h.get(clave))
    almuerzo = numero(h.get("Almuerzo_Min"), 0)
    return {"ID": texto(h.get("ID")), "Nombre_Turno": texto(h.get("Nombre_Turno")), "Alcance": f"{h.get('Alcance_Tipo')}: {h.get('Alcance')}",
            "Tramo": texto(h.get(clave)), "Inicio": t[0] if t else None, "Fin": t[1] if t else None,
            "Cruza_Medianoche": bool(t and t[1] <= t[0]), "Almuerzo_Min": almuerzo, "Tolerancia_Min": numero(h.get("Tolerancia_Min"), 0),
            "Programado_Min": minutos_tramo(t[0], t[1], almuerzo) if t else 0.0, "Laboral": bool(t)}


# ---------------------------------------------------------------------
# Incidencias y tablero del día
# ---------------------------------------------------------------------
def _rango_dias(desde, hasta):
    d = fecha(desde)
    hasta = fecha(hasta)
    while d and hasta and d <= hasta:
        yield d
        d += timedelta(days=1)


def incidencias(jornadas_lista, horarios_movs, empleados, desde, hasta, ahora, umbral_extra_min=15):
    """Comparación marcaciones vs. horario. Solo informa: ninguna incidencia descuenta dinero automáticamente.

    empleados: {nombre: {"cargo": ..., "negocio": ...}}
    """
    ahora = fecha_hora(ahora) or datetime.now()
    salida = []
    por_dia = {}
    for j in jornadas_lista:
        por_dia.setdefault((j["Colaborador"], j["Fecha"]), []).append(j)

    def agregar(colab, dia, tipo, minutos, detalle):
        salida.append({"Colaborador": colab, "Fecha": dia, "Tipo": tipo, "Tipo_Texto": TIPOS_INCIDENCIA[tipo],
                       "Minutos": round(float(minutos), 0), "Detalle": detalle, "Clave": f"INC|{colab}|{dia:%Y-%m-%d}|{tipo}"})

    for colab, info in empleados.items():
        for dia in _rango_dias(desde, hasta):
            if dia > ahora.date():
                break
            h = resolver_horario(horarios_movs, colab, texto(info.get("cargo")), texto(info.get("negocio")), dia)
            js = por_dia.get((colab, dia), [])
            for j in js:
                if not j["Completa"] and (dia < ahora.date()):
                    agregar(colab, dia, "MARCACION_INCOMPLETA", 0, f"Entrada {j['Entrada']:%H:%M} sin salida registrada")
            if not h or not h["Laboral"]:
                if js:
                    agregar(colab, dia, "DIA_NO_PROGRAMADO", sum(j["Trabajado_Min"] for j in js), "Marcó en un día sin horario asignado")
                continue
            inicio = datetime.combine(dia, h["Inicio"])
            fin = datetime.combine(dia + timedelta(days=1 if h["Cruza_Medianoche"] else 0), h["Fin"])
            if not js:
                if ahora > fin:
                    agregar(colab, dia, "AUSENCIA", h["Programado_Min"], f"Sin marcaciones · horario {h['Tramo']}")
                continue
            entrada = min(j["Entrada"] for j in js)
            tarde = (entrada - inicio).total_seconds() / 60
            if tarde > h["Tolerancia_Min"]:
                agregar(colab, dia, "TARDANZA", tarde, f"Entró {entrada:%H:%M} · horario {h['Inicio']:%H:%M} (tolerancia {h['Tolerancia_Min']:g} min)")
            completas = [j for j in js if j["Completa"]]
            if completas and len(completas) == len(js):
                salida_real = max(j["Salida"] for j in completas)
                antes = (fin - salida_real).total_seconds() / 60
                if antes > 1:
                    agregar(colab, dia, "SALIDA_ANTICIPADA", antes, f"Salió {salida_real:%H:%M} · horario hasta {h['Fin']:%H:%M}")
                trabajado = sum(j["Trabajado_Min"] for j in completas)
                extra = trabajado - h["Programado_Min"]
                if extra > umbral_extra_min:
                    agregar(colab, dia, "HORAS_EXTRA", extra, f"Trabajó {trabajado / 60:.2f} h · programado {h['Programado_Min'] / 60:.2f} h")
    return sorted(salida, key=lambda i: (i["Fecha"], i["Colaborador"], i["Tipo"]))


def ultimas_decisiones(incidencias_movs):
    """{Clave_Unica base: última decisión registrada}."""
    nulos = anulados(incidencias_movs)
    salida = {}
    for m in sorted((m for m in incidencias_movs if _mov(m) == "DECISION" and texto(m.get("ID")) not in nulos),
                    key=lambda m: (texto(m.get("Registrado")), texto(m.get("ID")))):
        salida[texto(m.get("Clave_Unica")).split("#")[0]] = m
    return salida


def preparar_decision(incidencia, decision, comentario, numero_revision=0):
    if decision not in DECISIONES:
        raise ErrorNegocio("Elige una decisión válida.")
    if len(texto(comentario)) < 3:
        raise ErrorNegocio("Escribe un comentario para la decisión.")
    return {"Movimiento": "DECISION", "Colaborador": incidencia["Colaborador"], "Fecha": incidencia["Fecha"].strftime("%Y-%m-%d"),
            "Tipo": incidencia["Tipo"], "Minutos": incidencia["Minutos"], "Decision": decision, "Comentario": texto(comentario),
            "Clave_Unica": f"{incidencia['Clave']}#{numero_revision}"}


def tablero_hoy(empleados, marcas, horarios_movs, ahora):
    """Quién está trabajando, en pausa, ya salió, no ha marcado o descansa hoy."""
    ahora = fecha_hora(ahora) or datetime.now()
    hoy = ahora.date()
    filas = []
    for colab, info in empleados.items():
        propias = [m for m in marcas if m["Colaborador"] == colab]
        est = estado_colaborador(propias)
        h = resolver_horario(horarios_movs, colab, texto(info.get("cargo")), texto(info.get("negocio")), hoy)
        hoy_marcas = [m for m in propias if m["Fecha_Hora"].date() == hoy]
        entrada = next((m["Fecha_Hora"] for m in hoy_marcas if m["Tipo"] == "ENTRADA"), None)
        if est["estado"] == ESTADO_TRABAJANDO:
            estado = "🟢 Trabajando"
        elif est["estado"] == ESTADO_PAUSA:
            estado = "🟡 En pausa"
        elif hoy_marcas:
            estado = "⚪ Ya salió"
        elif h and h["Laboral"]:
            inicio = datetime.combine(hoy, h["Inicio"])
            estado = "🔴 Sin marcar (tarde)" if ahora > inicio + timedelta(minutes=h["Tolerancia_Min"]) else "⏳ Aún no entra"
        else:
            estado = "💤 Libre hoy" if h else "— Sin horario asignado"
        abierta = est["desde"] if est["estado"] != ESTADO_FUERA else None
        filas.append({"Colaborador": colab, "Estado": estado, "Horario hoy": h["Tramo"] if h and h["Laboral"] else ("Libre" if h else "Sin horario"),
                      "Entrada": entrada.strftime("%H:%M") if entrada else "",
                      "Entrada abierta desde": abierta.strftime("%d/%m %H:%M") if abierta and abierta.date() < hoy else ""})
    return filas
