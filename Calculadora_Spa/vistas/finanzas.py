"""Página «Caja y cuentas»: caja administrativa, gastos, cuentas por pagar a proveedores y reportes."""
import pandas as pd
import plotly.express as px
import streamlit as st

from nucleo import finanzas as fin
from nucleo.util import dinero, fecha, usd

from . import comun as cm


def pagina(ctx):
    ctx.encabezado_pagina("🏦", "Caja y cuentas", "Entradas y salidas de dinero, gastos por categoría, cuentas por pagar a proveedores y reportes por negocio.")
    t1, t2, t3 = st.tabs(["💵 Caja", "🧾 Cuentas por pagar", "📊 Reportes"])
    with t1:
        caja(ctx)
    with t2:
        cuentas_por_pagar(ctx)
    with t3:
        reportes(ctx)


def _unificados(ctx):
    return fin.movimientos_caja_unificados(ctx.leer("Caja"), ctx.leer("Pagos_Personal"), ctx.leer("Anticipos"), ctx.leer("Prestamos"),
                                           ctx.leer("Cuentas_por_Pagar"), ctx.negocio_de())


def caja(ctx):
    cm.aviso_lectura(ctx, "Caja")
    c_form, c_tabla = st.columns([1, 1.7])
    with c_form:
        with ctx.tarjeta("caja_form"):
            ctx.md(ctx.titulo_seccion("➕ Registrar movimiento", "Gastos, compras e ingresos de caja. Pagos al personal, anticipos, préstamos y proveedores se registran en su módulo y aparecen aquí solos."))
            tipo = st.radio("Tipo", ["SALIDA", "ENTRADA"], horizontal=True, key="caja_f_tipo", format_func=lambda t: "📤 Salida (gasto)" if t == "SALIDA" else "📥 Entrada")
            categorias = ctx.lista("categorias_gasto") if tipo == "SALIDA" else ctx.lista("categorias_ingreso")
            with st.form("form_caja"):
                a, b = st.columns(2)
                fecha_mov = a.date_input("Fecha *", value=ctx.hoy(), format="DD/MM/YYYY", key="caja_f_fecha")
                categoria = b.selectbox("Categoría *", categorias, key=f"caja_f_cat_{tipo}")
                concepto = st.text_input("Concepto *", key="caja_f_concepto", placeholder="Ej.: Compra de toallas")
                a, b = st.columns(2)
                monto = a.number_input("Monto ($) *", min_value=0.0, step=0.01, format="%.2f", key="caja_f_monto")
                metodo = b.selectbox("Método *", ctx.lista("metodos_pago"), key="caja_f_metodo")
                a, b = st.columns(2)
                negocio = a.selectbox("Negocio / sucursal", [""] + ctx.lista("negocios"), key="caja_f_negocio", format_func=lambda n: n or "Sin asignar")
                responsable = b.text_input("Responsable *", value=ctx.usuario()["nombre"], key="caja_f_resp")
                a, b = st.columns(2)
                referencia = a.text_input("Referencia", key="caja_f_ref")
                comprobante = b.text_input("Comprobante (número o enlace)", key="caja_f_comp")
                observaciones = st.text_area("Observaciones", key="caja_f_obs", height=60)
                enviado = st.form_submit_button("💾 Registrar movimiento", type="primary")
            if enviado:
                cm.ejecutar(ctx, "Caja", lambda: fin.nuevo_movimiento_caja(fecha_mov, tipo, categoria, concepto, monto, metodo, negocio, responsable, referencia,
                                                                            comprobante, observaciones, id_operacion=cm.id_operacion("caja", "CAJ")),
                            f"Movimiento de {usd(monto)} registrado.", rotar="caja")
    with c_tabla:
        with ctx.tarjeta("caja_tabla"):
            ctx.md(ctx.titulo_seccion("📒 Movimientos de dinero", "Incluye lo registrado en pagos, anticipos, préstamos y proveedores (cada movimiento aparece una sola vez)."))
            desde, hasta = cm.filtro_fechas(ctx, "caja_fechas", 30)
            filas = fin.filtrar_fechas(_unificados(ctx), desde, hasta)
            if not filas:
                st.caption("Sin movimientos en el rango.")
            else:
                df = pd.DataFrame(filas)
                entradas = df.loc[df["Tipo"] == "ENTRADA", "Monto"].sum()
                salidas = df.loc[df["Tipo"] == "SALIDA", "Monto"].sum()
                ctx.md("<div class='chips'>" + ctx.chip(f"📥 Entradas {ctx.usd(entradas)}", "green") + ctx.chip(f"📤 Salidas {ctx.usd(salidas)}", "red")
                       + ctx.chip(f"⚖️ Neto {ctx.usd(entradas - salidas)}", "indigo") + "</div>")
                vista = df.assign(Fecha=df["Fecha"].map(lambda d: d.strftime("%Y-%m-%d") if d else ""),
                                  Pendiente=df["Pendiente"].map(lambda p: "⏳" if p else ""))[
                    ["Fecha", "Tipo", "Categoria", "Concepto", "Monto", "Metodo", "Negocio", "Origen", "Pendiente", "Ref_ID"]]
                cm.tabla(ctx, vista, ("Monto",), alto=min(460, 40 + 35 * len(vista)))
                por_metodo = df.assign(Signo=df.apply(lambda r: r["Monto"] if r["Tipo"] == "ENTRADA" else -r["Monto"], axis=1)).groupby("Metodo")["Signo"].sum()
                st.caption("Neto por método: " + " · ".join(f"{m or 'Sin método'} {usd(v)}" for m, v in por_metodo.items()))
                cm.descargas(ctx, vista, f"Caja_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Movimientos de caja", f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", ("Monto",), key="dl_caja")
    manuales = [m for m in fin.estado_caja(ctx.leer("Caja")) if m["Estado"] == "Registrado"]
    if manuales:
        with st.expander("⛔ Anular un movimiento de caja registrado a mano"):
            etiquetas = {m["ID"]: f"{m.get('Fecha')} · {m.get('Tipo')} · {m.get('Concepto')} · {usd(m.get('Monto'))} · {m['ID']}" for m in reversed(manuales)}
            mid = st.selectbox("Movimiento", list(etiquetas), format_func=etiquetas.get, key="caja_n_id")
            motivo = st.text_input("Motivo (obligatorio)", key="caja_n_motivo")
            if st.button("⛔ Anular", key="caja_n_btn"):
                cm.ejecutar(ctx, "Caja", lambda: fin.preparar_anulacion_movimiento(cm.lectura_fresca(ctx, "Caja"), mid, motivo, tipos=("MOVIMIENTO",)),
                            "Movimiento anulado.", auditoria=("Movimiento de caja anulado", f"{mid} · {motivo}"))


def cuentas_por_pagar(ctx):
    movs = ctx.leer("Cuentas_por_Pagar")
    cm.aviso_lectura(ctx, "Cuentas_por_Pagar")
    estado = fin.estado_cxp(movs, ctx.hoy())
    abiertas = [f for f in estado if f["Estado"] in ("Pendiente", "Parcial", "Vencida")]
    ctx.fila_kpis([
        ctx.kpi_html("🧾", "Saldo por pagar", ctx.usd(sum(f["Saldo"] for f in abiertas)), f"{len(abiertas)} documento(s) abiertos", "amber"),
        ctx.kpi_html("🔴", "Vencido", ctx.usd(sum(f["Saldo"] for f in abiertas if f["Estado"] == "Vencida")),
                     f"{sum(1 for f in abiertas if f['Estado'] == 'Vencida')} documento(s)", "red"),
        ctx.kpi_html("📅", "Vence en 7 días", ctx.usd(sum(f["Saldo"] for f in abiertas if f["Dias"] is not None and 0 <= f["Dias"] <= 7)), "Programa estos pagos", "sky"),
        ctx.kpi_html("✅", "Pagado (histórico)", ctx.usd(sum(f["Pagado"] for f in estado)), "Pagos parciales y completos", "green"),
    ])
    c_form, c_tabla = st.columns([1, 1.7])
    with c_form:
        with ctx.tarjeta("cxp_form"):
            ctx.md(ctx.titulo_seccion("➕ Nueva cuenta por pagar", "Factura, crédito fiscal o compromiso con un proveedor."))
            proveedores = [p.get("Nombre_Proveedor") for p in ctx.proveedores() if p.get("Nombre_Proveedor")]
            with st.form("form_cxp"):
                proveedor = st.selectbox("Proveedor *", proveedores + ["Otro (escribir abajo)"], key="cxp_f_prov") if proveedores else "Otro (escribir abajo)"
                otro = st.text_input("Proveedor (si no está en el directorio)", key="cxp_f_otro")
                a, b = st.columns(2)
                documento = a.text_input("N.° de documento", key="cxp_f_doc", placeholder="CCF-0001")
                monto = b.number_input("Monto ($) *", min_value=0.0, step=0.01, format="%.2f", key="cxp_f_monto")
                a, b = st.columns(2)
                fecha_doc = a.date_input("Fecha del documento *", value=ctx.hoy(), format="DD/MM/YYYY", key="cxp_f_fecha")
                vencimiento = b.date_input("Vencimiento *", value=ctx.hoy(), format="DD/MM/YYYY", key="cxp_f_venc")
                concepto = st.text_input("Concepto *", key="cxp_f_concepto")
                a, b = st.columns(2)
                categoria = a.selectbox("Categoría de gasto", ctx.lista("categorias_gasto"), key="cxp_f_cat")
                negocio = b.selectbox("Negocio", [""] + ctx.lista("negocios"), key="cxp_f_neg", format_func=lambda n: n or "Sin asignar")
                observaciones = st.text_input("Observaciones", key="cxp_f_obs")
                enviado = st.form_submit_button("💾 Registrar cuenta por pagar", type="primary")
            if enviado:
                nombre = otro.strip() if proveedor == "Otro (escribir abajo)" else proveedor
                cm.ejecutar(ctx, "Cuentas_por_Pagar",
                            lambda: fin.nueva_factura(cm.lectura_fresca(ctx, "Cuentas_por_Pagar"), nombre, documento, fecha_doc, vencimiento, monto, concepto,
                                                      categoria, negocio, observaciones, id_operacion=cm.id_operacion("cxp", "CXP")),
                            f"Cuenta por pagar a {nombre} registrada.", rotar="cxp")
    with c_tabla:
        with ctx.tarjeta("cxp_tabla"):
            ctx.md(ctx.titulo_seccion("📋 Cuentas por pagar", "Saldo = monto − pagos registrados."))
            ver = st.radio("Mostrar", ["Abiertas", "Todas"], horizontal=True, key="cxp_ver", label_visibility="collapsed")
            lista = abiertas if ver == "Abiertas" else estado
            if not lista:
                st.caption("No hay cuentas " + ("abiertas." if ver == "Abiertas" else "registradas."))
            else:
                df = pd.DataFrame([{"Proveedor": f["Proveedor"], "Documento": f["Documento"], "Fecha": f["Fecha"], "Vencimiento": f["Vencimiento"],
                                    "Monto": f["Monto"], "Pagado": f["Pagado"], "Saldo": f["Saldo"], "Días": f["Dias"], "Estado": cm.con_icono(f["Estado"]),
                                    "ID": f["ID"]} for f in sorted(lista, key=lambda x: x["Vencimiento"])])
                cm.tabla(ctx, df, ("Monto", "Pagado", "Saldo"))
                cm.descargas(ctx, df, "Cuentas_por_pagar", "Cuentas por pagar", f"Al {ctx.hoy():%d/%m/%Y}", ("Monto", "Pagado", "Saldo"), key="dl_cxp")
    pagables = [f for f in estado if f["Estado"] in ("Pendiente", "Parcial", "Vencida")]
    anulables = [f for f in estado if f["Estado"] != "Anulada"]
    if not anulables:
        return
    with st.expander("💵 Registrar pago (parcial o total) o anular"):
        accion = st.radio("Acción", ["Registrar pago", "Anular documento o pago"], horizontal=True, key="cxp_a_accion")
        if accion == "Registrar pago":
            if not pagables:
                st.caption("No hay cuentas con saldo.")
                return
            etiquetas = {f["ID"]: f"{f['Proveedor']} · {f['Documento'] or f['Concepto']} · saldo {usd(f['Saldo'])} · vence {f['Vencimiento']}" for f in pagables}
            fid = st.selectbox("Cuenta", list(etiquetas), format_func=etiquetas.get, key="cxp_p_id")
            f = next(x for x in pagables if x["ID"] == fid)
            a, b, c, d = st.columns(4)
            monto = a.number_input("Monto ($)", min_value=0.0, max_value=float(f["Saldo"]), value=float(f["Saldo"]), step=0.01, format="%.2f", key=f"cxp_p_monto_{fid}")
            fecha_pago = b.date_input("Fecha", value=ctx.hoy(), format="DD/MM/YYYY", key="cxp_p_fecha")
            metodo = c.selectbox("Método", ctx.lista("metodos_pago"), key="cxp_p_met")
            ref = d.text_input("Referencia", key="cxp_p_ref")
            if st.button("💵 Registrar pago", type="primary", key="cxp_p_btn"):
                op = f"pago_cxp_{fid}"
                cm.ejecutar(ctx, "Cuentas_por_Pagar",
                            lambda: dict(fin.preparar_pago_cxp(cm.lectura_fresca(ctx, "Cuentas_por_Pagar"), fid, monto, fecha_pago, metodo, ref, hoy=ctx.hoy()),
                                         ID=cm.id_operacion(op, "CXP")),
                            f"Pago de {usd(monto)} a {f['Proveedor']} registrado.", auditoria=("Pago a proveedor", f"{f['Proveedor']} · {usd(monto)}"), rotar=op)
        else:
            opciones = {f["ID"]: f"Documento: {f['Proveedor']} · {f['Documento'] or f['Concepto']} · {usd(f['Monto'])}" for f in anulables}
            for f in anulables:
                opciones.update({p["ID"]: f"Pago: {f['Proveedor']} · {usd(p.get('Monto'))} · {p.get('Fecha')}" for p in f["Pagos"]})
            objetivo = st.selectbox("¿Qué anulas?", list(opciones), format_func=opciones.get, key="cxp_n_id")
            motivo = st.text_input("Motivo (obligatorio)", key="cxp_n_motivo")
            if st.button("⛔ Anular", key="cxp_n_btn"):
                if any(f["ID"] == objetivo for f in anulables):
                    construir = lambda: fin.preparar_anulacion_factura(cm.lectura_fresca(ctx, "Cuentas_por_Pagar"), objetivo, motivo, hoy=ctx.hoy())  # noqa: E731
                else:
                    construir = lambda: fin.preparar_anulacion_movimiento(cm.lectura_fresca(ctx, "Cuentas_por_Pagar"), objetivo, motivo, tipos=("PAGO",))  # noqa: E731
                cm.ejecutar(ctx, "Cuentas_por_Pagar", construir, "Anulación registrada.", auditoria=("Anulación en cuentas por pagar", f"{objetivo} · {motivo}"))


def reportes(ctx):
    desde, hasta = cm.filtro_fechas(ctx, "rep_fechas", 30)
    negocios = st.multiselect("Negocios", ["Sin asignar"] + ctx.lista("negocios"), key="rep_negocios", placeholder="Todos")
    flujo = [m for m in fin.filtrar_fechas(_unificados(ctx), desde, hasta) if not negocios or m["Negocio"] in negocios]
    planilla = [r for r in ctx.historial() if fin.periodo_en_rango(ctx.clave_de_fila(r), desde, hasta)]
    gastos = [g for g in fin.filtrar_fechas(fin.gastos_devengados(ctx.leer("Caja"), ctx.leer("Cuentas_por_Pagar"), planilla, ctx.negocio_de(), ctx.hoy()),
                                            desde, hasta) if not negocios or g["Negocio"] in negocios]
    cobrar_ant = sum(a["Saldo"] for a in fin.estado_anticipos(ctx.leer("Anticipos")))
    cobrar_pre = sum(p["Saldo"] for p in fin.estado_prestamos(ctx.leer("Prestamos"), ctx.hoy()))
    entradas = sum(m["Monto"] for m in flujo if m["Tipo"] == "ENTRADA")
    salidas = sum(m["Monto"] for m in flujo if m["Tipo"] == "SALIDA")
    ctx.fila_kpis([
        ctx.kpi_html("🧾", "Gastos del período", ctx.usd(sum(g["Monto"] for g in gastos)), "Caja + proveedores + planilla calculada", "red"),
        ctx.kpi_html("📥", "Entradas de dinero", ctx.usd(entradas), "Flujo real de caja", "green"),
        ctx.kpi_html("📤", "Salidas de dinero", ctx.usd(salidas), f"Neto {ctx.usd(entradas - salidas)}", "amber"),
        ctx.kpi_html("🤝", "Por cobrar al personal", ctx.usd(cobrar_ant + cobrar_pre), f"Anticipos {ctx.usd(cobrar_ant)} · préstamos {ctx.usd(cobrar_pre)}", "violet"),
    ])
    st.caption("«Gastos» = lo que cuesta operar (incluye la planilla calculada y las facturas aunque aún no se paguen). «Flujo» = el dinero que realmente entró o salió. "
               "Los anticipos y préstamos no son gasto: son cuentas por cobrar.")
    if not gastos and not flujo:
        st.info("Sin datos en el rango elegido.")
        return
    c1, c2 = st.columns(2)
    if gastos:
        df_g = pd.DataFrame(gastos)
        with c1:
            with ctx.tarjeta("rep_cat"):
                ctx.md(ctx.titulo_seccion("Gastos por categoría"))
                por_cat = df_g.groupby("Categoria", as_index=False)["Monto"].sum().sort_values("Monto")
                fig = px.bar(por_cat, x="Monto", y="Categoria", orientation="h")
                fig.update_traces(marker_color=ctx.tema()["p"], texttemplate="$%{x:,.2f}", textposition="outside", cliponaxis=False)
                fig.update_xaxes(title=None, tickprefix="$")
                fig.update_yaxes(title=None)
                st.plotly_chart(ctx.estilo_plotly(fig, max(260, 44 * len(por_cat) + 60)), config=ctx.PLOTLY_CONFIG, key="rep_ch_cat", **ctx.ancho(st.plotly_chart))
        with c2:
            with ctx.tarjeta("rep_neg"):
                ctx.md(ctx.titulo_seccion("Costos por negocio"))
                por_neg = df_g.groupby(["Negocio", "Origen"], as_index=False)["Monto"].sum()
                fig = px.bar(por_neg, x="Monto", y="Negocio", color="Origen", orientation="h", barmode="stack")
                fig.update_xaxes(title=None, tickprefix="$")
                fig.update_yaxes(title=None)
                st.plotly_chart(ctx.estilo_plotly(fig, max(260, 60 * por_neg["Negocio"].nunique() + 80)), config=ctx.PLOTLY_CONFIG, key="rep_ch_neg", **ctx.ancho(st.plotly_chart))
    with ctx.tarjeta("rep_resumen"):
        ctx.md(ctx.titulo_seccion("📅 Resumen quincenal y mensual", "Gastos y flujo de caja agrupados."))
        agrupar = st.radio("Agrupar por", ["Quincena", "Mes"], horizontal=True, key="rep_agrupar")

        def grupo(d):
            if d is None:
                return "Sin fecha"
            return f"{d:%Y-%m} · {'1.ª' if d.day <= 15 else '2.ª'} quincena" if agrupar == "Quincena" else f"{d:%Y-%m}"

        filas = {}
        for g in gastos:
            filas.setdefault(grupo(fecha(g["Fecha"])), {"Gastos": 0.0, "Entradas": 0.0, "Salidas": 0.0})["Gastos"] += g["Monto"]
        for m in flujo:
            filas.setdefault(grupo(m["Fecha"]), {"Gastos": 0.0, "Entradas": 0.0, "Salidas": 0.0})["Entradas" if m["Tipo"] == "ENTRADA" else "Salidas"] += m["Monto"]
        df_r = pd.DataFrame([{"Período": k, **{c: dinero(v) for c, v in vals.items()}} for k, vals in sorted(filas.items())])
        df_r["Neto de caja"] = df_r["Entradas"] - df_r["Salidas"]
        cm.tabla(ctx, df_r, ("Gastos", "Entradas", "Salidas", "Neto de caja"))
        cm.descargas(ctx, df_r, f"Resumen_{agrupar}_{desde:%Y%m%d}_{hasta:%Y%m%d}", f"Resumen {agrupar.lower()} de gastos y caja",
                     f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", ("Gastos", "Entradas", "Salidas", "Neto de caja"), key="dl_rep_res")
    if gastos:
        with st.expander("📋 Detalle de gastos"):
            df_d = pd.DataFrame(gastos).assign(Fecha=lambda d: d["Fecha"].map(lambda x: x.strftime("%Y-%m-%d") if x else ""))
            cm.tabla(ctx, df_d, ("Monto",))
            cm.descargas(ctx, df_d, f"Gastos_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Detalle de gastos", f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", ("Monto",), key="dl_rep_det")
