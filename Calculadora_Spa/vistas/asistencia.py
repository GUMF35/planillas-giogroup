"""Páginas «Asistencia y horarios» (administración) y «Mi asistencia» (personal operativo)."""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from nucleo import asistencia as asi
from nucleo import personal as per
from nucleo.finanzas import ErrorNegocio

from . import comun as cm

AVISO_VERIFICACION = ("ℹ️ La marcación registra la hora del servidor (El Salvador). No verifica identidad biométrica ni ubicación: "
                      "si alguien marca por otra persona, solo se detecta revisando el historial.")


def _empleados_info(ctx):
    return {n: {"cargo": i.get("cargo", ""), "negocio": i.get("negocio", "")} for n, i in ctx.empleados().items()}


def _marcar(ctx, colab, tipo, momento=None, origen="Autoservicio", motivo=""):
    ahora = ctx.ahora()
    momento = momento or ahora
    manual = abs((momento - ahora).total_seconds()) > 300
    if manual and len((motivo or "").strip()) < 5:
        st.error("⚠️ Para registrar una hora distinta de la actual escribe la justificación (mínimo 5 caracteres).")
        return

    def construir():
        movs = ctx.almacen().leer("Asistencia", forzar=True)
        asi.validar_marca(movs, colab, tipo, momento, bool(ctx.aj("pausas_habilitadas")))
        return asi.nueva_marca(colab, tipo, momento, origen=origen if not manual else "Administrador (hora manual)", motivo=motivo,
                               id_operacion=cm.id_operacion(f"marca_{colab}", "ASI"))

    cm.ejecutar(ctx, "Asistencia", construir, f"{asi.ETIQUETAS_TIPO[tipo]} de {colab} registrada a las {momento:%H:%M}.", rotar=f"marca_{colab}",
                auditoria=("Marcación con hora manual", f"{colab} · {asi.ETIQUETAS_TIPO[tipo]} {momento:%d/%m %H:%M} · {motivo}") if manual else None)


def botones_marcacion(ctx, colab, marcas, admin=False):
    est = asi.estado_colaborador([m for m in marcas if m["Colaborador"] == colab])
    texto_estado = {"fuera": "⚪ Fuera de turno", "trabajando": "🟢 Trabajando", "en_pausa": "🟡 En pausa"}[est["estado"]]
    desde = f" desde {est['desde']:%d/%m %H:%M}" if est["desde"] else ""
    ctx.md(f"<div class='chips'>{ctx.chip(texto_estado + desde, 'indigo')}</div>")
    if est["desde"] and est["desde"].date() < ctx.hoy() and est["estado"] != "fuera":
        st.warning("Hay una entrada abierta de un día anterior: falta registrar la salida. El administrador debe registrarla con su justificación.")
    momento, motivo = None, ""
    if admin:
        with st.expander("🕰️ Registrar con otra hora (requiere justificación)"):
            a, b = st.columns(2)
            dia = a.date_input("Fecha", value=ctx.hoy(), format="DD/MM/YYYY", key=f"asi_m_dia_{colab}")
            hora = b.time_input("Hora", value=ctx.ahora().time().replace(second=0, microsecond=0), step=timedelta(minutes=1), key=f"asi_m_hora_{colab}")
            motivo = st.text_input("Justificación", key=f"asi_m_motivo_{colab}")
            if st.checkbox("Usar esta fecha y hora", key=f"asi_m_usar_{colab}"):
                momento = datetime.combine(dia, hora)
    pausas = bool(ctx.aj("pausas_habilitadas"))
    disponibles = {"fuera": ["ENTRADA"], "trabajando": ["SALIDA"] + (["INICIO_PAUSA"] if pausas else []), "en_pausa": ["FIN_PAUSA"] if pausas else []}
    iconos = {"ENTRADA": "🟢", "SALIDA": "🔴", "INICIO_PAUSA": "☕", "FIN_PAUSA": "▶️"}
    tipos = disponibles[est["estado"]]
    cols = st.columns(max(1, len(tipos)))
    for col, tipo in zip(cols, tipos):
        if col.button(f"{iconos[tipo]} Marcar {asi.ETIQUETAS_TIPO[tipo].lower()}", key=f"asi_btn_{colab}_{tipo}", type="primary" if tipo in ("ENTRADA", "SALIDA") else "secondary",
                      **ctx.ancho(st.button)):
            _marcar(ctx, colab, tipo, momento, "Administrador" if admin else "Autoservicio", motivo)
    st.caption(AVISO_VERIFICACION)


def pagina_admin(ctx):
    ctx.encabezado_pagina("🕒", "Asistencia y horarios", "Entradas, salidas y pausas con hora de El Salvador, horarios con vigencia e incidencias para revisar.")
    movs = ctx.leer("Asistencia")
    horarios = ctx.leer("Horarios")
    cm.aviso_lectura(ctx, "Asistencia", "Horarios")
    marcas = asi.marcas_efectivas(movs)
    t1, t2, t3, t4, t5 = st.tabs(["👥 Hoy", "🕒 Marcar", "📜 Marcaciones y correcciones", "⚠️ Incidencias", "🗓️ Horarios y turnos"])
    with t1:
        tablero(ctx, marcas, horarios)
    with t2:
        with ctx.tarjeta("asi_marcar"):
            ctx.md(ctx.titulo_seccion("Registrar una marcación", "Elige al colaborador. Para una hora distinta de la actual se pide justificación y queda auditada."))
            colab = st.selectbox("Colaborador", list(ctx.empleados()), key="asi_m_colab")
            botones_marcacion(ctx, colab, marcas, admin=True)
    with t3:
        marcaciones(ctx, movs, marcas)
    with t4:
        incidencias(ctx, marcas, horarios)
    with t5:
        pagina_horarios(ctx, horarios)


def tablero(ctx, marcas, horarios):
    filas = asi.tablero_hoy(_empleados_info(ctx), marcas, horarios, ctx.ahora())
    df = pd.DataFrame(filas)
    if df.empty:
        st.info("No hay colaboradores registrados.")
        return
    cuenta = lambda texto: int(df["Estado"].str.contains(texto, regex=False).sum())  # noqa: E731
    ctx.fila_kpis([
        ctx.kpi_html("🟢", "Trabajando", str(cuenta("Trabajando")), f"Hoy {ctx.hoy():%d/%m/%Y}", "green"),
        ctx.kpi_html("🟡", "En pausa", str(cuenta("En pausa")), "Pausas o almuerzo", "amber"),
        ctx.kpi_html("🔴", "Sin marcar", str(cuenta("Sin marcar")), "Ya pasó su hora de entrada", "red"),
        ctx.kpi_html("⚪", "Ya salieron", str(cuenta("Ya salió")), f"{cuenta('Libre')} libres · {cuenta('Sin horario')} sin horario", "sky"),
    ])
    with ctx.tarjeta("asi_hoy"):
        ctx.md(ctx.titulo_seccion("👥 Quién está trabajando", "Se actualiza con cada marcación."))
        cm.tabla(ctx, df)
        if (df["Entrada abierta desde"] != "").any():
            st.warning("Hay entradas abiertas de días anteriores: registra la salida en «Marcar» con la hora correcta y su justificación.")


def marcaciones(ctx, movs, marcas):
    with ctx.tarjeta("asi_hist"):
        ctx.md(ctx.titulo_seccion("📜 Jornadas", "Hora efectiva y, si fue corregida, la hora original registrada por el sistema."))
        desde, hasta = cm.filtro_fechas(ctx, "asi_h_fechas", 15)
        sel = st.multiselect("Colaboradores", list(ctx.empleados()), key="asi_h_colab", placeholder="Todos")
        jornadas = [j for j in asi.jornadas(marcas) if desde <= j["Fecha"] <= hasta and (not sel or j["Colaborador"] in sel)]
        if not jornadas:
            st.caption("Sin marcaciones en el rango.")
        else:
            df = pd.DataFrame([{"Fecha": j["Fecha"].strftime("%Y-%m-%d"), "Colaborador": j["Colaborador"], "Entrada": j["Entrada"].strftime("%H:%M"),
                                "Salida": j["Salida"].strftime("%d/%m %H:%M") if j["Salida"] else "⚠️ Sin salida",
                                "Pausas (min)": round(j["Pausa_Min"]), "Horas trabajadas": round(j["Trabajado_Min"] / 60, 2),
                                "Corregida": "✏️ Sí" if j["Corregida"] else ""} for j in reversed(jornadas)])
            cm.tabla(ctx, df)
            ctx.md("<div class='chips'>" + ctx.chip(f"⏱️ {df['Horas trabajadas'].sum():.2f} horas", "indigo")
                   + ctx.chip(f"⚠️ {int((df['Salida'] == '⚠️ Sin salida').sum())} sin salida", "amber") + "</div>")
            cm.descargas(ctx, df, f"Asistencia_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Reporte de asistencia", f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", key="dl_asi")
    detalle = [m for m in marcas if desde <= m["Fecha_Hora"].date() <= hasta and (not sel or m["Colaborador"] in sel)]
    with st.expander("✏️ Corregir o anular una marcación (con justificación)"):
        if not detalle:
            st.caption("No hay marcaciones en el rango elegido.")
            return
        df_m = pd.DataFrame([{"Fecha y hora efectiva": m["Fecha_Hora"].strftime("%Y-%m-%d %H:%M"), "Colaborador": m["Colaborador"],
                              "Tipo": asi.ETIQUETAS_TIPO.get(m["Tipo"], m["Tipo"]),
                              "Hora real registrada": m["Registrado"].strftime("%Y-%m-%d %H:%M") if m["Registrado"] else "",
                              "Hora original": m["Hora_Original"].strftime("%Y-%m-%d %H:%M") if m["Corregida"] else "",
                              "Origen": m["Origen"], "Motivo": m["Motivo"], "Usuario": m["Usuario"], "ID": m["ID"]} for m in reversed(detalle)])
        cm.tabla(ctx, df_m, alto=min(380, 40 + 35 * len(df_m)))
        etiquetas = {m["ID"]: f"{m['Fecha_Hora']:%d/%m %H:%M} · {m['Colaborador']} · {asi.ETIQUETAS_TIPO.get(m['Tipo'])} · {m['ID']}" for m in reversed(detalle)}
        mid = st.selectbox("Marcación", list(etiquetas), format_func=etiquetas.get, key="asi_c_id")
        m = next(x for x in detalle if x["ID"] == mid)
        accion = st.radio("Acción", ["Corregir hora", "Anular"], horizontal=True, key="asi_c_accion")
        motivo = st.text_input("Justificación (obligatoria)", key="asi_c_motivo")
        if accion == "Corregir hora":
            a, b = st.columns(2)
            dia = a.date_input("Nueva fecha", value=m["Fecha_Hora"].date(), format="DD/MM/YYYY", key=f"asi_c_dia_{mid}")
            hora = b.time_input("Nueva hora", value=m["Fecha_Hora"].time().replace(second=0), step=timedelta(minutes=1), key=f"asi_c_hora_{mid}")
            if st.button("✏️ Guardar corrección", type="primary", key="asi_c_btn"):
                cm.ejecutar(ctx, "Asistencia", lambda: asi.preparar_correccion_marca(ctx.almacen().leer("Asistencia", forzar=True), mid,
                                                                                      datetime.combine(dia, hora), motivo),
                            "Corrección registrada (la hora original se conserva).", auditoria=("Corrección de marcación", f"{m['Colaborador']} · {mid} · {motivo}"))
        elif st.button("⛔ Anular marcación", key="asi_n_btn"):
            cm.ejecutar(ctx, "Asistencia", lambda: asi.preparar_anulacion_marca(ctx.almacen().leer("Asistencia", forzar=True), mid, motivo),
                        "Marcación anulada.", auditoria=("Anulación de marcación", f"{m['Colaborador']} · {mid} · {motivo}"))


def incidencias(ctx, marcas, horarios):
    decisiones_movs = ctx.leer("Incidencias")
    with ctx.tarjeta("asi_inc"):
        ctx.md(ctx.titulo_seccion("⚠️ Incidencias para revisar", "Tardanzas, salidas anticipadas, ausencias, marcaciones incompletas y posibles horas extra."))
        st.info("Ninguna incidencia descuenta dinero automáticamente. Revísala y registra tu decisión; si corresponde un descuento, aplícalo tú en la planilla con su motivo.")
        desde, hasta = cm.filtro_fechas(ctx, "asi_i_fechas", 15)
        lista = asi.incidencias(asi.jornadas(marcas), horarios, _empleados_info(ctx), desde, hasta, ctx.ahora(),
                                umbral_extra_min=float(ctx.aj("umbral_horas_extra_min") or 15))
        decisiones = asi.ultimas_decisiones(decisiones_movs)
        if not lista:
            st.success("Sin incidencias en el rango (o los colaboradores aún no tienen horario asignado).")
            return
        df = pd.DataFrame([{"Fecha": i["Fecha"].strftime("%Y-%m-%d"), "Colaborador": i["Colaborador"], "Incidencia": i["Tipo_Texto"],
                            "Minutos": int(i["Minutos"]), "Detalle": i["Detalle"],
                            "Decisión": decisiones.get(i["Clave"], {}).get("Decision", "⏳ Por revisar"),
                            "Comentario": decisiones.get(i["Clave"], {}).get("Comentario", "")} for i in lista])
        ctx.md("<div class='chips'>" + "".join(ctx.chip(f"{t}: {n}", "amber") for t, n in df["Incidencia"].value_counts().items())
               + ctx.chip(f"⏳ {int((df['Decisión'] == '⏳ Por revisar').sum())} por revisar", "red") + "</div>")
        cm.tabla(ctx, df, alto=min(460, 40 + 35 * len(df)))
        cm.descargas(ctx, df, f"Incidencias_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Incidencias de asistencia", f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", key="dl_inc")
    with st.expander("📝 Registrar la decisión sobre una incidencia"):
        etiquetas = {i["Clave"]: f"{i['Fecha']:%d/%m} · {i['Colaborador']} · {i['Tipo_Texto']} ({int(i['Minutos'])} min)" for i in lista}
        clave = st.selectbox("Incidencia", list(etiquetas), format_func=etiquetas.get, key="asi_d_clave")
        inc = next(i for i in lista if i["Clave"] == clave)
        a, b = st.columns([1, 2])
        decision = a.selectbox("Decisión", list(asi.DECISIONES), key="asi_d_decision")
        comentario = b.text_input("Comentario", key="asi_d_coment")
        if st.button("💾 Guardar decisión", type="primary", key="asi_d_btn"):
            revisiones = sum(1 for m in decisiones_movs if str(m.get("Clave_Unica", "")).split("#")[0] == clave)
            cm.ejecutar(ctx, "Incidencias", lambda: asi.preparar_decision(inc, decision, comentario, revisiones),
                        "Decisión registrada.", auditoria=("Decisión sobre incidencia", f"{inc['Colaborador']} · {inc['Tipo_Texto']} · {decision}"))


def pagina_horarios(ctx, horarios):
    with ctx.tarjeta("hor_vigentes"):
        ctx.md(ctx.titulo_seccion("🗓️ Horario de cada colaborador", "Se aplica el del colaborador; si no tiene, el de su cargo y luego el de su negocio."))
        dia = st.date_input("Ver horarios vigentes el día", value=ctx.hoy(), format="DD/MM/YYYY", key="hor_dia")
        filas = []
        for colab, info in _empleados_info(ctx).items():
            h = asi.resolver_horario(horarios, colab, info["cargo"], info["negocio"], dia)
            fila = {"Colaborador": colab, "Turno": h["Nombre_Turno"] if h else "— Sin horario", "Origen": h["Alcance"] if h else ""}
            if h:
                version = next((v for v in horarios if v.get("ID") == h["ID"]), {})
                fila.update({asi.DIAS_NOMBRE[d][:3]: version.get(d) or "Libre" for d in asi.DIAS_CLAVE})
                fila.update({"Almuerzo (min)": int(h["Almuerzo_Min"]), "Tolerancia (min)": int(h["Tolerancia_Min"])})
            filas.append(fila)
        cm.tabla(ctx, pd.DataFrame(filas))
    c1, c2 = st.columns([1.2, 1])
    with c1:
        with ctx.tarjeta("hor_form"):
            ctx.md(ctx.titulo_seccion("➕ Asignar horario o turno especial", "Cambiar un horario crea una versión nueva desde una fecha: los días anteriores no cambian."))
            a, b = st.columns(2)
            alcance_tipo = a.selectbox("Aplica a", list(asi.ALCANCES), key="hor_f_tipo")
            opciones = {"Colaborador": list(ctx.empleados()),
                        "Cargo": sorted({i.get("cargo") for i in ctx.empleados().values() if i.get("cargo")}) or ["(sin cargos registrados)"],
                        "Negocio": ctx.lista("negocios")}
            alcance = b.selectbox("¿Quién?", opciones.get(alcance_tipo, []), key=f"hor_f_alc_{alcance_tipo}")
            with st.form("form_horario"):
                nombre = st.text_input("Nombre del turno", value="Turno regular", key="hor_f_nombre")
                a, b = st.columns(2)
                desde = a.date_input("Vigente desde *", value=ctx.hoy(), format="DD/MM/YYYY", key="hor_f_desde")
                hasta = b.date_input("Vigente hasta (opcional, para turnos especiales)", value=None, format="DD/MM/YYYY", key="hor_f_hasta")
                st.caption("Escribe cada día como 08:00-17:00. Deja vacío el día de descanso. Turnos nocturnos: 22:00-06:00.")
                cols = st.columns(7)
                dias = {}
                for col, d in zip(cols, asi.DIAS_CLAVE):
                    dias[d] = col.text_input(asi.DIAS_NOMBRE[d][:3], value="" if d == "Dom" else "08:00-17:00", key=f"hor_f_{d}")
                a, b = st.columns(2)
                almuerzo = a.number_input("Almuerzo (min, no se cuenta como trabajo)", min_value=0, max_value=180, value=60, step=5, key="hor_f_alm")
                tolerancia = b.number_input("Tolerancia de entrada (min)", min_value=0, max_value=60, value=int(ctx.aj("tolerancia_min") or 10), step=1, key="hor_f_tol")
                observaciones = st.text_input("Observaciones", key="hor_f_obs")
                enviado = st.form_submit_button("💾 Guardar horario", type="primary")
            if enviado:
                cm.ejecutar(ctx, "Horarios",
                            lambda: dict(asi.nueva_version_horario(alcance_tipo, alcance, nombre, desde, hasta or "", dias, almuerzo, tolerancia, observaciones),
                                         ID=cm.id_operacion("horario", "HOR")),
                            f"Horario de {alcance} guardado desde el {desde:%d/%m/%Y}.", auditoria=("Horario asignado", f"{alcance_tipo}: {alcance} · desde {desde:%d/%m/%Y}"),
                            rotar="horario")
    with c2:
        with ctx.tarjeta("hor_hist"):
            ctx.md(ctx.titulo_seccion("📚 Historial de versiones", "Nada se borra: una versión equivocada se anula con motivo."))
            vigentes = asi.versiones_vigentes(horarios)
            if not vigentes:
                st.caption("Aún no hay horarios.")
                return
            df = pd.DataFrame([{"Aplica a": f"{v.get('Alcance_Tipo')}: {v.get('Alcance')}", "Turno": v.get("Nombre_Turno"), "Desde": v.get("Vigente_Desde"),
                                "Hasta": v.get("Vigente_Hasta") or "—", "ID": v.get("ID")} for v in reversed(vigentes)])
            cm.tabla(ctx, df)
            etiquetas = {v.get("ID"): f"{v.get('Alcance')} · {v.get('Nombre_Turno')} · desde {v.get('Vigente_Desde')}" for v in reversed(vigentes)}
            vid = st.selectbox("Anular versión", list(etiquetas), format_func=etiquetas.get, key="hor_n_id")
            motivo = st.text_input("Motivo", key="hor_n_motivo")
            if st.button("⛔ Anular versión", key="hor_n_btn"):
                def construir():
                    if len(motivo.strip()) < 5:
                        raise ErrorNegocio("Escribe el motivo (mínimo 5 caracteres).")
                    return {"Movimiento": "ANULACION", "Ref_ID": vid, "Motivo": motivo.strip()}
                cm.ejecutar(ctx, "Horarios", construir, "Versión de horario anulada.", auditoria=("Horario anulado", f"{vid} · {motivo}"))


def pagina_mi_asistencia(ctx):
    """Vista del personal operativo: solo su propia información (sin salarios ni datos bancarios)."""
    usuario = ctx.usuario()
    colab = usuario.get("colaborador")
    ctx.encabezado_pagina("🕒", "Mi asistencia", f"Hola, {usuario.get('nombre')}. Marca tu entrada y salida, revisa tu horario y solicita permisos.")
    if not colab or colab not in ctx.empleados():
        st.error("Tu usuario no está vinculado a un colaborador del personal. Pide a la administración que revise tu usuario.")
        return
    marcas = asi.marcas_efectivas(ctx.leer("Asistencia"), colab)
    horarios = ctx.leer("Horarios")
    info = _empleados_info(ctx).get(colab, {})
    h = asi.resolver_horario(horarios, colab, info.get("cargo"), info.get("negocio"), ctx.hoy())
    with ctx.tarjeta("mi_marcar"):
        ctx.md(ctx.titulo_seccion(f"Hoy, {ctx.hoy():%d/%m/%Y}", f"Tu horario de hoy: {h['Tramo'] if h and h['Laboral'] else ('Libre' if h else 'sin horario asignado')}"))
        botones_marcacion(ctx, colab, marcas, admin=False)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        with ctx.tarjeta("mi_hist"):
            ctx.md(ctx.titulo_seccion("📜 Mis últimas jornadas", "Últimos 30 días"))
            desde = ctx.hoy() - timedelta(days=30)
            js = [j for j in asi.jornadas(marcas) if j["Fecha"] >= desde]
            if js:
                cm.tabla(ctx, pd.DataFrame([{"Fecha": j["Fecha"].strftime("%d/%m/%Y"), "Entrada": j["Entrada"].strftime("%H:%M"),
                                             "Salida": j["Salida"].strftime("%H:%M") if j["Salida"] else "Sin salida",
                                             "Horas": round(j["Trabajado_Min"] / 60, 2)} for j in reversed(js)]))
            else:
                st.caption("Aún no tienes marcaciones.")
    with c2:
        with ctx.tarjeta("mi_solicitud"):
            ctx.md(ctx.titulo_seccion("📝 Solicitar permiso o vacaciones", "La administración la revisará."))
            with st.form("form_mi_solicitud"):
                tipo = st.selectbox("Tipo", list(per.TIPOS_SOLICITUD), format_func=lambda t: per.TIPOS_EXPEDIENTE[t][0], key="mi_s_tipo")
                titulo = st.text_input("Motivo breve", key="mi_s_titulo")
                a, b = st.columns(2)
                ini = a.date_input("Desde", value=ctx.hoy(), format="DD/MM/YYYY", key="mi_s_ini")
                fin = b.date_input("Hasta", value=ctx.hoy(), format="DD/MM/YYYY", key="mi_s_fin")
                detalle = st.text_area("Detalle", key="mi_s_det", height=70)
                enviado = st.form_submit_button("📨 Enviar solicitud", type="primary")
            if enviado:
                cm.ejecutar(ctx, "Expediente", lambda: dict(per.nuevo_registro(colab, tipo, titulo, ini, fin, "Solicitado", detalle),
                                                             ID=cm.id_operacion("mi_solicitud", "EXP")),
                            "Solicitud enviada.", rotar="mi_solicitud")
            propias = [r for r in per.estado_expediente(ctx.leer("Expediente")) if r.get("Colaborador") == colab and r.get("Tipo") in per.TIPOS_SOLICITUD]
            if propias:
                cm.tabla(ctx, pd.DataFrame([{"Tipo": r["Tipo_Texto"], "Motivo": r.get("Titulo"), "Desde": r.get("Fecha_Inicio"),
                                             "Estado": cm.con_icono(r["Estado_Actual"])} for r in reversed(propias)]))
