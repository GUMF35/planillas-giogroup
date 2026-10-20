"""Página «Anticipos y préstamos». Son módulos independientes:
- Anticipo: dinero adelantado del sueldo; se descuenta UNA vez en la planilla o se devuelve.
- Préstamo: cuenta por cobrar con cuotas, abonos, reestructuraciones y cancelaciones justificadas.
"""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from nucleo import finanzas as fin
from nucleo.util import usd

from . import comun as cm


def pagina(ctx):
    ctx.encabezado_pagina("🤝", "Anticipos y préstamos",
                          "Entrega dinero antes del día de pago o presta con cuotas. Nada se descuenta solo: cada descuento se aplica una vez y con tu confirmación.")
    t1, t2 = st.tabs(["💵 Anticipos de sueldo", "🏦 Préstamos"])
    with t1:
        anticipos(ctx)
    with t2:
        prestamos(ctx)


# ---------------------------------------------------------------------
# Anticipos
# ---------------------------------------------------------------------
def anticipos(ctx):
    movs = ctx.leer("Anticipos")
    cm.aviso_lectura(ctx, "Anticipos")
    estado = fin.estado_anticipos(movs)
    activos = [a for a in estado if a["Estado"] in ("Pendiente", "Parcial")]
    ctx.fila_kpis([
        ctx.kpi_html("💵", "Saldo por descontar", ctx.usd(sum(a["Saldo"] for a in activos)), f"{len(activos)} anticipo(s) activo(s)", "amber"),
        ctx.kpi_html("📤", "Entregado (vigentes)", ctx.usd(sum(a["Monto"] for a in estado if a["Estado"] != "Anulado")), "Desde el inicio", "sky"),
        ctx.kpi_html("✂️", "Descontado en planillas", ctx.usd(sum(a["Descontado"] for a in estado)), "Una sola vez por anticipo y período", "green"),
        ctx.kpi_html("↩️", "Devuelto", ctx.usd(sum(a["Devuelto"] for a in estado)), "Sin descuento salarial", "violet"),
    ])
    c_form, c_tabla = st.columns([1, 1.6])
    with c_form:
        with ctx.tarjeta("ant_form"):
            ctx.md(ctx.titulo_seccion("➕ Entregar un anticipo", "Ejemplo: hoy entregas $20. Queda registrado al instante y asociado a la persona."))
            with st.form("form_anticipo"):
                colab = st.selectbox("Colaborador *", list(ctx.empleados()), key="ant_f_colab")
                a, b = st.columns(2)
                monto = a.number_input("Monto entregado ($) *", min_value=0.0, step=1.0, format="%.2f", key="ant_f_monto")
                metodo = b.selectbox("Forma de entrega *", ctx.lista("metodos_pago"), key="ant_f_metodo")
                a, b = st.columns(2)
                dia = a.date_input("Fecha *", value=ctx.hoy(), format="DD/MM/YYYY", key="ant_f_dia")
                hora = b.time_input("Hora *", value=ctx.ahora().time().replace(second=0, microsecond=0), step=timedelta(minutes=1), key="ant_f_hora")
                responsable = st.text_input("Responsable que entrega *", value=ctx.usuario()["nombre"], key="ant_f_resp")
                periodo = cm.selector_periodo(ctx, "Planilla en la que se descontará", "ant_f_periodo", vacio="Por definir")
                referencia = st.text_input("Referencia / comprobante", key="ant_f_ref")
                observaciones = st.text_area("Observaciones", key="ant_f_obs", height=70)
                enviado = st.form_submit_button("💾 Registrar anticipo", type="primary")
            if enviado:
                cm.ejecutar(ctx, "Anticipos",
                            lambda: fin.nuevo_anticipo(colab, monto, datetime.combine(dia, hora), metodo, responsable, periodo, referencia,
                                                       observaciones=observaciones, id_operacion=cm.id_operacion("anticipo", "ANT")),
                            f"Anticipo de {usd(monto)} a {colab} registrado.", auditoria=("Anticipo entregado", f"{colab} · {usd(monto)}"), rotar="anticipo")
    with c_tabla:
        with ctx.tarjeta("ant_tabla"):
            ctx.md(ctx.titulo_seccion("📋 Anticipos", "Saldo = entregado − descontado en planilla − devuelto."))
            ver = st.radio("Mostrar", ["Activos", "Todos"], horizontal=True, key="ant_ver", label_visibility="collapsed")
            lista = activos if ver == "Activos" else estado
            if not lista:
                st.caption("No hay anticipos " + ("activos." if ver == "Activos" else "registrados."))
            else:
                df = pd.DataFrame([{k: a[k] for k in ("Fecha", "Colaborador", "Monto", "Descontado", "Devuelto", "Saldo", "Estado", "Periodo", "Metodo",
                                                     "Responsable", "ID")} for a in reversed(lista)])
                df["Estado"] = df["Estado"].map(cm.con_icono)
                cm.tabla(ctx, df, ("Monto", "Descontado", "Devuelto", "Saldo"))
                cm.descargas(ctx, df, "Anticipos", "Anticipos de sueldo", f"Al {ctx.hoy():%d/%m/%Y}", ("Monto", "Descontado", "Devuelto", "Saldo"), key="dl_ant")

    if not estado:
        return
    with st.expander("⚙️ Descontar, registrar devolución o anular un anticipo"):
        disponibles = [a for a in estado if a["Estado"] != "Anulado"]
        if not disponibles:
            st.caption("No hay anticipos vigentes.")
            return
        etiquetas = {a["ID"]: f"{a['Fecha']} · {a['Colaborador']} · {usd(a['Monto'])} · saldo {usd(a['Saldo'])} · {a['ID']}" for a in reversed(disponibles)}
        aid = st.selectbox("Anticipo", list(etiquetas), format_func=etiquetas.get, key="ant_a_id")
        a = next(x for x in disponibles if x["ID"] == aid)
        accion = st.radio("Acción", ["Descontar en una planilla", "Registrar devolución", "Anular movimiento"], horizontal=True, key="ant_a_accion")
        if accion == "Descontar en una planilla":
            c1, c2 = st.columns([1.6, 1])
            periodo = cm.selector_periodo(ctx, "Período de planilla", "ant_a_periodo", destino=c1)
            monto = c2.number_input("Monto a descontar ($)", min_value=0.0, max_value=float(max(a["Saldo"], 0.0)), value=float(a["Saldo"]), step=0.01,
                                    format="%.2f", key=f"ant_a_monto_{aid}")
            st.caption("El descuento aparece en la planilla de ese período como «Anticipos aplicados». Si vuelves a calcular la planilla, no se descuenta otra vez.")
            if st.button("✂️ Aplicar descuento", type="primary", key="ant_a_desc", disabled=a["Saldo"] < 0.005):
                cm.ejecutar(ctx, "Anticipos", lambda: fin.preparar_descuento_anticipo(cm.lectura_fresca(ctx, "Anticipos"), aid, periodo, monto),
                            f"Anticipo descontado en la planilla {periodo}.", auditoria=("Anticipo descontado en planilla", f"{a['Colaborador']} · {usd(monto)} · {periodo}"))
        elif accion == "Registrar devolución":
            c1, c2, c3 = st.columns(3)
            monto = c1.number_input("Monto devuelto ($)", min_value=0.0, max_value=float(max(a["Saldo"], 0.0)), value=float(a["Saldo"]), step=0.01,
                                    format="%.2f", key=f"ant_a_dev_{aid}")
            metodo = c2.selectbox("Recibido en", ctx.lista("metodos_pago"), key="ant_a_dev_met")
            ref = c3.text_input("Referencia", key="ant_a_dev_ref")
            st.caption("La devolución baja el saldo SIN descontarle del sueldo.")
            if st.button("↩️ Registrar devolución", type="primary", key="ant_a_dev_btn", disabled=a["Saldo"] < 0.005):
                cm.ejecutar(ctx, "Anticipos", lambda: fin.preparar_devolucion_anticipo(cm.lectura_fresca(ctx, "Anticipos"), aid, monto, metodo,
                                                                                        ctx.ahora().strftime("%Y-%m-%d %H:%M"), ref),
                            "Devolución registrada.", auditoria=("Devolución de anticipo", f"{a['Colaborador']} · {usd(monto)}"))
        else:
            hijos = {m["ID"]: f"{m.get('Movimiento')} · {usd(m.get('Monto'))} · {m.get('Periodo') or m.get('Fecha')} · {m['ID']}"
                     for m in a["Descuentos"] + a["Devoluciones"]}
            opciones = {aid: f"El anticipo completo ({usd(a['Monto'])})"}
            opciones.update(hijos)
            objetivo = st.selectbox("¿Qué anulas?", list(opciones), format_func=opciones.get, key=f"ant_a_obj_{aid}")
            motivo = st.text_area("Motivo (obligatorio)", key="ant_a_motivo", height=70)
            st.caption("Anular un descuento devuelve el saldo al anticipo. Un anticipo con descuentos o devoluciones vigentes no se puede anular hasta anular esos movimientos.")
            if st.button("⛔ Anular", key="ant_a_anular"):
                if objetivo == aid:
                    construir = lambda: fin.preparar_anulacion_anticipo(cm.lectura_fresca(ctx, "Anticipos"), aid, motivo)  # noqa: E731
                else:
                    construir = lambda: fin.preparar_anulacion_movimiento(cm.lectura_fresca(ctx, "Anticipos"), objetivo, motivo)  # noqa: E731
                cm.ejecutar(ctx, "Anticipos", construir, "Anulación registrada.", auditoria=("Anulación en anticipos", f"{a['Colaborador']} · {objetivo} · {motivo}"))


# ---------------------------------------------------------------------
# Préstamos
# ---------------------------------------------------------------------
def prestamos(ctx):
    movs = ctx.leer("Prestamos")
    cm.aviso_lectura(ctx, "Prestamos")
    estado = fin.estado_prestamos(movs, ctx.hoy())
    vigentes = [p for p in estado if p["Estado"] in ("Vigente", "Atrasado")]
    ctx.fila_kpis([
        ctx.kpi_html("🏦", "Saldo por recuperar", ctx.usd(sum(p["Saldo"] for p in vigentes)), f"{len(vigentes)} préstamo(s) vigente(s)", "amber"),
        ctx.kpi_html("🔴", "Atrasados", str(sum(1 for p in estado if p["Estado"] == "Atrasado")),
                     f"Atraso total {ctx.usd(sum(p['Atraso'] for p in estado))}", "red"),
        ctx.kpi_html("💵", "Recuperado", ctx.usd(sum(p["Pagado"] for p in estado)), "Abonos + cuotas en planilla", "green"),
        ctx.kpi_html("⚪", "Cancelado / condonado", ctx.usd(sum(p["Condonado"] for p in estado)), "Con motivo y autorización", "violet"),
    ])
    c_form, c_tabla = st.columns([1, 1.6])
    with c_form:
        with ctx.tarjeta("pre_form"):
            ctx.md(ctx.titulo_seccion("➕ Nuevo préstamo", "Queda como cuenta por cobrar (no es un gasto de planilla) hasta que se recupere."))
            with st.form("form_prestamo"):
                colab = st.selectbox("Colaborador *", list(ctx.empleados()), key="pre_f_colab")
                a, b = st.columns(2)
                capital = a.number_input("Capital entregado ($) *", min_value=0.0, step=5.0, format="%.2f", key="pre_f_cap")
                fecha_pre = b.date_input("Fecha *", value=ctx.hoy(), format="DD/MM/YYYY", key="pre_f_fecha")
                a, b, c = st.columns(3)
                cuotas = a.number_input("Cuotas *", min_value=1, max_value=60, value=4, step=1, key="pre_f_cuotas")
                frecuencia = b.selectbox("Frecuencia *", list(fin.FRECUENCIAS), key="pre_f_frec")
                cuota = c.number_input("Cuota ($) *", min_value=0.0, step=1.0, format="%.2f", key="pre_f_cuota",
                                       help="Déjala en 0 para calcularla: capital ÷ cuotas.")
                primer = st.date_input("Primer vencimiento *", value=ctx.hoy() + timedelta(days=15), format="DD/MM/YYYY", key="pre_f_primer")
                condiciones = st.text_area("Condiciones acordadas *", key="pre_f_cond", height=70,
                                           placeholder="Ej.: 4 cuotas quincenales de $25 descontadas en planilla, autorizadas por escrito por el colaborador.")
                a, b = st.columns(2)
                autorizado = a.text_input("Autorizado por *", value=ctx.usuario()["nombre"], key="pre_f_aut")
                metodo = b.selectbox("Entregado en *", ctx.lista("metodos_pago"), key="pre_f_met")
                documento = st.text_input("Documento de respaldo (número o enlace)", key="pre_f_doc")
                enviado = st.form_submit_button("💾 Registrar préstamo", type="primary")
            if enviado:
                monto_cuota = cuota if cuota > 0 else round(capital / max(int(cuotas), 1) + 0.004, 2)
                cm.ejecutar(ctx, "Prestamos",
                            lambda: fin.nuevo_prestamo(colab, capital, fecha_pre, cuotas, monto_cuota, frecuencia, primer, condiciones, autorizado, metodo,
                                                       documento, id_operacion=cm.id_operacion("prestamo", "PRE")),
                            f"Préstamo de {usd(capital)} a {colab} registrado.", auditoria=("Préstamo otorgado", f"{colab} · {usd(capital)}"), rotar="prestamo")
    with c_tabla:
        with ctx.tarjeta("pre_tabla"):
            ctx.md(ctx.titulo_seccion("📋 Préstamos", "Saldo = capital − abonos − cuotas en planilla − cancelaciones justificadas."))
            ver = st.radio("Mostrar", ["Vigentes", "Todos"], horizontal=True, key="pre_ver", label_visibility="collapsed")
            lista = vigentes if ver == "Vigentes" else estado
            if not lista:
                st.caption("No hay préstamos " + ("vigentes." if ver == "Vigentes" else "registrados."))
            else:
                df = pd.DataFrame([{"Fecha": p["Fecha"], "Colaborador": p["Colaborador"], "Capital": p["Capital"], "Pagado": p["Pagado"], "Saldo": p["Saldo"],
                                    "Cuota": p["Cuota"], "Frecuencia": p["Frecuencia"], "Próximo vencimiento": p["Proximo_Vencimiento"],
                                    "Atraso": p["Atraso"], "Estado": cm.con_icono(p["Estado"]), "ID": p["ID"]} for p in reversed(lista)])
                cm.tabla(ctx, df, ("Capital", "Pagado", "Saldo", "Cuota", "Atraso"))
                cm.descargas(ctx, df, "Prestamos", "Préstamos a colaboradores", f"Al {ctx.hoy():%d/%m/%Y}", ("Capital", "Pagado", "Saldo", "Cuota", "Atraso"), key="dl_pre")

    if not estado:
        return
    with st.expander("⚙️ Abonos, reestructuración, cancelación o anulación"):
        etiquetas = {p["ID"]: f"{p['Fecha']} · {p['Colaborador']} · capital {usd(p['Capital'])} · saldo {usd(p['Saldo'])} · {p['Estado']} · {p['ID']}"
                     for p in reversed(estado) if p["Estado"] != "Anulado"}
        if not etiquetas:
            st.caption("No hay préstamos vigentes.")
            return
        pid = st.selectbox("Préstamo", list(etiquetas), format_func=etiquetas.get, key="pre_a_id")
        p = next(x for x in estado if x["ID"] == pid)
        ctx.md("<div class='chips'>" + ctx.chip(f"Condiciones: {p['Condiciones']}") + ctx.chip(f"Autorizó: {p['Autorizado_Por']}", "indigo") + "</div>")
        if p["Movimientos"]:
            with st.container():
                hist = pd.DataFrame([{"Movimiento": m.get("Movimiento"), "Fecha": m.get("Fecha") or str(m.get("Registrado", ""))[:10], "Monto": m.get("Monto"),
                                      "Período": m.get("Periodo", ""), "Detalle": m.get("Motivo") or m.get("Observaciones") or "", "ID": m.get("ID")}
                                     for m in p["Movimientos"]])
                cm.tabla(ctx, hist, ("Monto",))
        accion = st.radio("Acción", ["Registrar abono", "Reestructurar", "Cancelar saldo (justificado)", "Anular préstamo o movimiento"], horizontal=True, key="pre_a_accion")
        if accion == "Registrar abono":
            c1, c2, c3, c4 = st.columns(4)
            monto = c1.number_input("Abono ($)", min_value=0.0, max_value=float(max(p["Saldo"], 0.0)), value=float(min(p["Cuota"], p["Saldo"])), step=0.01,
                                    format="%.2f", key=f"pre_a_monto_{pid}")
            metodo = c2.selectbox("Recibido en", ctx.lista("metodos_pago"), key="pre_a_met")
            fecha_ab = c3.date_input("Fecha", value=ctx.hoy(), format="DD/MM/YYYY", key="pre_a_fecha")
            ref = c4.text_input("Referencia", key="pre_a_ref")
            st.caption(f"Saldo actual {usd(p['Saldo'])} → nuevo saldo {usd(max(0.0, p['Saldo'] - monto))}.")
            if st.button("💵 Registrar abono", type="primary", key="pre_a_abono", disabled=p["Saldo"] < 0.005):
                op = f"abono_{pid}"
                cm.ejecutar(ctx, "Prestamos",
                            lambda: dict(fin.preparar_abono(cm.lectura_fresca(ctx, "Prestamos"), pid, monto, metodo, fecha_ab, ref, hoy=ctx.hoy()),
                                         ID=cm.id_operacion(op, "PRE")),
                            f"Abono de {usd(monto)} registrado.", auditoria=("Abono de préstamo", f"{p['Colaborador']} · {usd(monto)}"), rotar=op)
        elif accion == "Reestructurar":
            c1, c2, c3, c4 = st.columns(4)
            cuota = c1.number_input("Nueva cuota ($)", min_value=0.0, value=float(p["Cuota"]), step=1.0, format="%.2f", key=f"pre_r_cuota_{pid}")
            cuotas = c2.number_input("Cuotas restantes", min_value=1, max_value=60, value=max(1, int(round(p["Saldo"] / p["Cuota"] + 0.49)) if p["Cuota"] else 1),
                                     key=f"pre_r_n_{pid}")
            frecuencia = c3.selectbox("Frecuencia", list(fin.FRECUENCIAS), key="pre_r_frec")
            proximo = c4.date_input("Próximo vencimiento", value=ctx.hoy() + timedelta(days=15), format="DD/MM/YYYY", key="pre_r_prox")
            a, b = st.columns(2)
            motivo = a.text_area("Motivo (obligatorio)", key="pre_r_motivo", height=70)
            autorizado = b.text_input("Autorizado por", value=ctx.usuario()["nombre"], key="pre_r_aut")
            if st.button("🔁 Reestructurar", type="primary", key="pre_r_btn"):
                cm.ejecutar(ctx, "Prestamos", lambda: fin.preparar_reestructuracion(cm.lectura_fresca(ctx, "Prestamos"), pid, cuota, cuotas, frecuencia, proximo,
                                                                                     motivo, autorizado, hoy=ctx.hoy()),
                            "Reestructuración registrada.", auditoria=("Préstamo reestructurado", f"{p['Colaborador']} · {motivo}"))
        elif accion == "Cancelar saldo (justificado)":
            st.warning(f"Se cancelará el saldo pendiente de {usd(p['Saldo'])}. Queda registrado como condonación con motivo y autorización.")
            a, b = st.columns(2)
            motivo = a.text_area("Motivo (obligatorio)", key="pre_c_motivo", height=70)
            autorizado = b.text_input("Autorizado por", value=ctx.usuario()["nombre"], key="pre_c_aut")
            confirmar = st.checkbox("Confirmo la cancelación del saldo", key=f"pre_c_conf_{pid}")
            if st.button("⚪ Cancelar saldo", key="pre_c_btn", disabled=not confirmar):
                cm.ejecutar(ctx, "Prestamos", lambda: fin.preparar_cancelacion(cm.lectura_fresca(ctx, "Prestamos"), pid, motivo, autorizado, hoy=ctx.hoy()),
                            "Saldo cancelado.", auditoria=("Préstamo cancelado", f"{p['Colaborador']} · {usd(p['Saldo'])} · {motivo}"))
        else:
            opciones = {pid: "El préstamo completo (solo si no tiene abonos ni cuotas)"}
            opciones.update({m["ID"]: f"{m.get('Movimiento')} · {usd(m.get('Monto'))} · {m['ID']}" for m in p["Movimientos"]
                             if str(m.get("Movimiento")).upper() in ("ABONO", "CUOTA_PLANILLA")})
            objetivo = st.selectbox("¿Qué anulas?", list(opciones), format_func=opciones.get, key=f"pre_n_obj_{pid}")
            motivo = st.text_area("Motivo (obligatorio)", key="pre_n_motivo", height=70)
            if st.button("⛔ Anular", key="pre_n_btn"):
                if objetivo == pid:
                    construir = lambda: fin.preparar_anulacion_prestamo(cm.lectura_fresca(ctx, "Prestamos"), pid, motivo, hoy=ctx.hoy())  # noqa: E731
                else:
                    construir = lambda: fin.preparar_anulacion_movimiento(cm.lectura_fresca(ctx, "Prestamos"), objetivo, motivo)  # noqa: E731
                cm.ejecutar(ctx, "Prestamos", construir, "Anulación registrada.", auditoria=("Anulación en préstamos", f"{p['Colaborador']} · {objetivo} · {motivo}"))
