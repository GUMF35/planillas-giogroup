"""Página «Pagos al personal»: calculado vs. entregado, registro de pagos, historial, anulaciones y correcciones."""
import pandas as pd
import streamlit as st

from nucleo import finanzas as fin
from nucleo.util import dinero, texto, usd

from . import comun as cm

COLUMNAS_HISTORIAL = ["Fecha", "Colaborador", "Concepto", "Periodo", "Monto", "Metodo", "Referencia", "Negocio", "Estado", "Sincronizado",
                      "Observaciones", "Usuario", "Registrado", "ID"]


def pagina(ctx):
    ctx.encabezado_pagina("💸", "Pagos al personal",
                          "Registra cada pago entregado y compáralo con lo calculado. Generar una planilla o un recibo NO marca nada como pagado.")
    movs = ctx.leer("Pagos_Personal")
    cm.aviso_lectura(ctx, "Pagos_Personal")
    t1, t2, t3 = st.tabs(["📋 Estado por período", "➕ Registrar pago", "🗂️ Historial y búsqueda"])
    with t1:
        estado_periodo(ctx, movs)
    with t2:
        formulario_pago(ctx, movs)
    with t3:
        historial(ctx, movs)


def resumen_periodo(ctx, clave, movs=None):
    calculado, guardado = ctx.calculado_periodo(clave)
    movs = ctx.leer("Pagos_Personal") if movs is None else movs
    filas = fin.resumen_pagos_periodo(clave, calculado, movs, ctx.leer("Anticipos"), ctx.leer("Prestamos"), ctx.leer("Ajustes_Planilla"), guardado)
    return filas, guardado


def estado_periodo(ctx, movs):
    with ctx.tarjeta("pg_estado"):
        ctx.md(ctx.titulo_seccion("Calculado vs. entregado", "Neto a entregar = total de la planilla + ajustes − anticipos aplicados − cuotas de préstamo aplicadas."))
        clave = cm.selector_periodo(ctx, "Período de planilla", "pg_periodo")
        filas, guardado = resumen_periodo(ctx, clave, movs)
        if not filas:
            st.info("No hay una planilla calculada ni pagos para este período. Sube el PDF de ventas en Planillas: la planilla se guarda sola.")
            return
        df = pd.DataFrame(filas)
        ctx.fila_kpis([
            ctx.kpi_html("🧮", "Total calculado", ctx.usd(df["Calculado"].sum()), "Planilla guardada" if guardado else "Cálculo actual (sin guardar)", "indigo"),
            ctx.kpi_html("💵", "Neto a entregar", ctx.usd(df["Neto"].sum()), f"Anticipos {ctx.usd(df['Anticipos'].sum())} · cuotas {ctx.usd(df['Cuotas_Prestamo'].sum())}", "sky"),
            ctx.kpi_html("✅", "Entregado", ctx.usd(df["Entregado"].sum()), f"{int((df['Estado'] == 'Completado').sum())} colaborador(es) completos", "green", "pos"),
            ctx.kpi_html("⏳", "Pendiente", ctx.usd(df["Pendiente"].sum()), f"{int(df['Pendiente'].gt(0.004).sum())} por pagar", "amber"),
        ])
        if (df["Estado"] == "Revisar: entregado de más").any():
            st.warning("Hay colaboradores con más dinero entregado que lo calculado: revisa si falta un ajuste o si un pago se registró dos veces.")
        vista = df.assign(Estado=df["Estado"].map(cm.con_icono)).rename(columns={"Cuotas_Prestamo": "Cuotas préstamo", "Neto": "Neto a entregar"})
        cm.tabla(ctx, vista, ("Calculado", "Ajustes", "Anticipos", "Cuotas préstamo", "Neto a entregar", "Entregado", "Pendiente"))
        cm.descargas(ctx, vista, f"Estado_pagos_{clave.replace(' ', '_')}", "Estado de pagos de planilla", f"Período {cm.etiqueta_periodo(clave)} ({clave})",
                     ("Calculado", "Ajustes", "Anticipos", "Cuotas préstamo", "Neto a entregar", "Entregado", "Pendiente"), key="dl_pg_estado")

    pendientes = [f for f in filas if f["Pendiente"] > 0.004]
    if pendientes:
        with ctx.tarjeta("pg_rapido"):
            ctx.md(ctx.titulo_seccion("⚡ Registrar el pago de lo pendiente", "Úsalo cuando ya entregaste el dinero (efectivo o transferencia)."))
            nombres = [f["Colaborador"] for f in pendientes]
            c1, c2, c3 = ctx.columnas([1.4, 1, 1], "bottom")
            colab = c1.selectbox("Colaborador", nombres, key="pg_r_colab")
            fila = next(f for f in pendientes if f["Colaborador"] == colab)
            monto = c2.number_input("Monto entregado ($)", min_value=0.0, value=float(fila["Pendiente"]), step=0.01, format="%.2f", key=f"pg_r_monto_{colab}")
            metodo = c3.selectbox("Método", ctx.lista("metodos_pago"), key="pg_r_metodo")
            d1, d2, d3 = ctx.columnas([1, 1.4, 1], "bottom")
            fecha_pago = d1.date_input("Fecha", value=ctx.hoy(), format="DD/MM/YYYY", key="pg_r_fecha")
            referencia = d2.text_input("Referencia bancaria (opcional)", key="pg_r_ref")
            if d3.button("✅ Registrar pago", type="primary", key="pg_r_btn", **ctx.ancho(st.button)):
                op = f"pago_rapido_{clave}_{colab}"
                cm.ejecutar(ctx, "Pagos_Personal",
                            lambda: fin.nuevo_pago(colab, fecha_pago, "Sueldo / planilla", monto, metodo, periodo=clave, referencia=referencia,
                                                   negocio=ctx.negocio_de().get(colab, ""), id_operacion=cm.id_operacion(op, "PAG")),
                            f"Pago de {usd(monto)} a {colab} registrado.", auditoria=("Pago al personal", f"{colab} · {usd(monto)} · {clave}"), rotar=op)


def formulario_pago(ctx, movs):
    conceptos = [c for c in ctx.lista("conceptos_pago") if c] or fin.CONCEPTOS_PAGO_DEFECTO
    with ctx.tarjeta("pg_form"):
        ctx.md(ctx.titulo_seccion("➕ Registrar un pago entregado", "Sueldo, comisión o bono cuentan contra la planilla del período; pagos extraordinarios, reembolsos y otros se suman aparte."))
        st.caption("¿Es un anticipo de sueldo? Regístralo en «Anticipos y préstamos» para que se pueda descontar después una sola vez.")
        empleados = list(ctx.empleados())
        with st.form("form_pago", clear_on_submit=False):
            a, b, c = st.columns([1.4, 1, 1])
            colab = a.selectbox("Colaborador *", empleados, key="pg_f_colab")
            fecha_pago = b.date_input("Fecha del pago *", value=ctx.hoy(), format="DD/MM/YYYY", key="pg_f_fecha")
            concepto = c.selectbox("Concepto *", conceptos, key="pg_f_concepto")
            a, b, c = st.columns([1.6, 1, 1])
            periodo = cm.selector_periodo(ctx, "Período de planilla", "pg_f_periodo", vacio="Sin período (no es de planilla)", destino=a)
            monto = b.number_input("Monto ($) *", min_value=0.0, step=0.01, format="%.2f", key="pg_f_monto")
            metodo = c.selectbox("Método de pago *", ctx.lista("metodos_pago"), key="pg_f_metodo")
            a, b, c = st.columns(3)
            referencia = a.text_input("Referencia bancaria", key="pg_f_ref")
            negocios = [""] + ctx.lista("negocios")
            negocio = b.selectbox("Sucursal / negocio", negocios, key="pg_f_negocio", format_func=lambda n: n or "Según el colaborador")
            comprobante = c.text_input("Comprobante (número o enlace)", key="pg_f_comp")
            observaciones = st.text_area("Observaciones", key="pg_f_obs", height=80)
            confirmar = st.checkbox("Confirmo que es un pago distinto aunque la app avise que parece duplicado", key="pg_f_confirmar")
            enviado = st.form_submit_button("💾 Registrar pago", type="primary")
        if enviado:
            try:
                reg = fin.nuevo_pago(colab, fecha_pago, concepto, monto, metodo, periodo=periodo, referencia=referencia,
                                     negocio=negocio or ctx.negocio_de().get(colab, ""), comprobante=comprobante, observaciones=observaciones,
                                     id_operacion=cm.id_operacion("pago", "PAG"))
            except fin.ErrorNegocio as ex:
                st.error(f"⚠️ {ex}")
                return
            duplicados = fin.posibles_duplicados(movs, reg)
            if duplicados and not confirmar:
                st.warning(f"Ya hay {len(duplicados)} pago(s) iguales (mismo colaborador, fecha, concepto, período y monto): "
                           + ", ".join(d["ID"] for d in duplicados) + ". Si de verdad es otro pago, marca la confirmación y vuelve a enviarlo.")
                return
            cm.ejecutar(ctx, "Pagos_Personal", lambda: reg, f"Pago de {usd(reg['Monto'])} a {colab} registrado.",
                        auditoria=("Pago al personal", f"{colab} · {concepto} · {usd(reg['Monto'])}"), rotar="pago")


def _union_con_anticipos(ctx, pagos):
    filas = [dict(p) for p in pagos]
    for a in cm_estado_anticipos(ctx):
        filas.append({"Fecha": texto(a["Fecha"])[:10], "Colaborador": a["Colaborador"], "Concepto": "Anticipo (módulo Anticipos)",
                      "Periodo": a["Periodo"], "Monto": a["Monto"], "Metodo": a["Metodo"], "Referencia": a["Referencia"],
                      "Negocio": ctx.negocio_de().get(a["Colaborador"], ""), "Estado": "Anulado" if a["Estado"] == "Anulado" else "Completado",
                      "Sincronizado": "⏳ Pendiente" if a["Pendiente_Sync"] else "✅ En la nube", "Observaciones": a["Observaciones"],
                      "Usuario": a.get("Responsable", ""), "Registrado": "", "ID": a["ID"]})
    return filas


def cm_estado_anticipos(ctx):
    return fin.estado_anticipos(ctx.leer("Anticipos"))


def historial(ctx, movs):
    pagos = fin.estado_pagos(movs)
    with ctx.tarjeta("pg_hist"):
        ctx.md(ctx.titulo_seccion("🗂️ Historial de pagos", "Busca por colaborador, fechas, período, negocio, concepto, método o estado. Exporta o imprime."))
        incluir_ant = st.toggle("Incluir anticipos entregados", value=True, key="pg_h_ant")
        filas = _union_con_anticipos(ctx, pagos) if incluir_ant else [dict(p) for p in pagos]
        if not filas:
            st.info("Todavía no hay pagos registrados.")
            return
        df = pd.DataFrame(filas)
        for c in COLUMNAS_HISTORIAL:
            if c not in df.columns:
                df[c] = ""
        df = df[COLUMNAS_HISTORIAL]
        df["Monto"] = df["Monto"].map(dinero)
        desde, hasta = cm.filtro_fechas(ctx, "pg_h_fechas", 90)
        f1, f2, f3 = st.columns(3)
        sel_colab = f1.multiselect("Colaboradores", sorted(df["Colaborador"].unique()), key="pg_h_colab", placeholder="Todos")
        sel_periodo = f2.multiselect("Períodos", sorted([p for p in df["Periodo"].unique() if p]), key="pg_h_periodo", placeholder="Todos")
        sel_estado = f3.multiselect("Estado", ["Completado", "Anulado", "Corregido"], default=["Completado"], key="pg_h_estado")
        f4, f5, f6 = st.columns(3)
        sel_concepto = f4.multiselect("Concepto", sorted(df["Concepto"].unique()), key="pg_h_concepto", placeholder="Todos")
        sel_metodo = f5.multiselect("Método", sorted([m for m in df["Metodo"].unique() if m]), key="pg_h_metodo", placeholder="Todos")
        sel_negocio = f6.multiselect("Negocio", sorted([n for n in df["Negocio"].unique() if n]), key="pg_h_negocio", placeholder="Todos")
        fechas = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
        mascara = fechas.between(desde, hasta)
        for col, sel in (("Colaborador", sel_colab), ("Periodo", sel_periodo), ("Estado", sel_estado), ("Concepto", sel_concepto),
                         ("Metodo", sel_metodo), ("Negocio", sel_negocio)):
            if sel:
                mascara &= df[col].isin(sel)
        vista = df[mascara].sort_values(["Fecha", "Registrado"], ascending=False)
        vigentes = vista[vista["Estado"] == "Completado"]
        ctx.md("<div class='chips'>" + ctx.chip(f"🧾 {len(vista)} registro(s)", "indigo") + ctx.chip(f"💵 Vigente {ctx.usd(vigentes['Monto'].sum())}", "green")
               + (ctx.chip(f"⏳ {int((vista['Sincronizado'] == '⏳ Pendiente').sum())} pendiente(s) de sincronizar", "amber")
                  if (vista["Sincronizado"] == "⏳ Pendiente").any() else "") + "</div>")
        mostrar = vista.assign(Estado=vista["Estado"].map(cm.con_icono))
        cm.tabla(ctx, mostrar, ("Monto",), alto=min(520, 40 + 35 * len(mostrar)))
        cm.descargas(ctx, mostrar.drop(columns=["Registrado"]), f"Pagos_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Historial de pagos al personal",
                     f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}", ("Monto",), key="dl_pg_hist")

    corregibles = [p for p in pagos if p["Estado"] == "Completado"]
    if not corregibles:
        return
    with st.expander("✏️ Anular o corregir un pago (queda registrado con motivo; el original nunca se borra)"):
        etiquetas = {p["ID"]: f"{p['Fecha']} · {p['Colaborador']} · {p['Concepto']} · {usd(p['Monto'])} · {p['ID']}" for p in reversed(corregibles)}
        pid = st.selectbox("Pago", list(etiquetas), format_func=etiquetas.get, key="pg_c_id")
        original = next(p for p in corregibles if p["ID"] == pid)
        accion = st.radio("Acción", ["Anular", "Corregir"], horizontal=True, key="pg_c_accion")
        motivo = st.text_area("Motivo (obligatorio)", key="pg_c_motivo", height=70)
        if accion == "Anular":
            if st.button("⛔ Anular pago", key="pg_c_anular", type="primary"):
                cm.ejecutar(ctx, "Pagos_Personal", lambda: fin.preparar_anulacion_pago(cm.lectura_fresca(ctx, "Pagos_Personal"), pid, motivo),
                            "Pago anulado.", auditoria=("Pago anulado", f"{original['Colaborador']} · {usd(original['Monto'])} · {motivo}"))
        else:
            a, b, c = st.columns(3)
            nuevo_monto = a.number_input("Monto correcto ($)", min_value=0.0, value=float(original["Monto"]), step=0.01, format="%.2f", key=f"pg_c_monto_{pid}")
            metodos = ctx.lista("metodos_pago")
            nuevo_metodo = b.selectbox("Método", metodos, index=metodos.index(original["Metodo"]) if original["Metodo"] in metodos else 0, key=f"pg_c_met_{pid}")
            nueva_ref = c.text_input("Referencia", value=texto(original.get("Referencia")), key=f"pg_c_ref_{pid}")
            if st.button("✏️ Registrar corrección", key="pg_c_corregir", type="primary"):
                op = f"correccion_{pid}"
                cm.ejecutar(ctx, "Pagos_Personal",
                            lambda: dict(fin.preparar_correccion_pago(cm.lectura_fresca(ctx, "Pagos_Personal"), pid, motivo, monto=nuevo_monto,
                                                                      metodo=nuevo_metodo, referencia=nueva_ref), ID=cm.id_operacion(op, "PAG")),
                            "Corrección registrada: el pago original queda como «Corregido».",
                            auditoria=("Pago corregido", f"{original['Colaborador']} · {usd(original['Monto'])} → {usd(nuevo_monto)} · {motivo}"), rotar=op)
