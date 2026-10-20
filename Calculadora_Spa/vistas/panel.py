"""Panel administrativo: indicadores calculados SOLO con registros guardados (Google Sheets o pendientes de sincronizar)."""
import pandas as pd
import plotly.express as px
import streamlit as st

from nucleo import asistencia as asi
from nucleo import finanzas as fin
from nucleo.util import dinero

from . import comun as cm
from .expediente import alertas_generales, bloque_alertas


def pagina(ctx):
    ctx.encabezado_pagina("📈", "Panel administrativo", "Planilla calculada vs. pagada, anticipos, préstamos, gastos, caja, asistencia y vencimientos, con datos guardados.")
    f1, f2, f3 = st.columns([1.6, 1, 1])
    with f1:
        desde, hasta = cm.filtro_fechas(ctx, "pa_fechas", 30)
    sel_colab = f2.multiselect("Colaboradores", list(ctx.empleados()), key="pa_colab", placeholder="Todos")
    sel_neg = f3.multiselect("Negocios", ["Sin asignar"] + ctx.lista("negocios"), key="pa_neg", placeholder="Todos")
    negocio_de = ctx.negocio_de()

    def pasa(colab=None, negocio=None):
        if sel_colab and colab not in sel_colab:
            return False
        neg = negocio if negocio is not None else (negocio_de.get(colab, "") or "Sin asignar")
        return not sel_neg or (neg or "Sin asignar") in sel_neg

    # Planilla calculada y pagos (por períodos que terminan en el rango)
    historial = [r for r in ctx.historial() if fin.periodo_en_rango(ctx.clave_de_fila(r), desde, hasta) and pasa(r.get("Colaborador"))]
    claves = sorted({ctx.clave_de_fila(r) for r in historial})
    calculada = sum(dinero(r.get("Total")) for r in historial)
    pagos_movs, ant_movs, pre_movs, aju_movs = ctx.leer("Pagos_Personal"), ctx.leer("Anticipos"), ctx.leer("Prestamos"), ctx.leer("Ajustes_Planilla")
    resumenes = []
    for clave in claves:
        calc = {}
        for r in historial:
            if ctx.clave_de_fila(r) == clave:
                calc[r.get("Colaborador")] = dinero(calc.get(r.get("Colaborador"), 0) + dinero(r.get("Total")))
        resumenes += [dict(f, Periodo=clave) for f in fin.resumen_pagos_periodo(clave, calc, pagos_movs, ant_movs, pre_movs, aju_movs) if pasa(f["Colaborador"])]
    pendiente = sum(f["Pendiente"] for f in resumenes)
    pagos_rango = [p for p in fin.filtrar_fechas(fin.pagos_vigentes(pagos_movs), desde, hasta) if pasa(p.get("Colaborador"), p.get("Negocio") or None)]
    entregado = sum(p["Monto"] for p in pagos_rango)
    anticipos = [a for a in fin.estado_anticipos(ant_movs) if pasa(a["Colaborador"])]
    prestamos = [p for p in fin.estado_prestamos(pre_movs, ctx.hoy()) if pasa(p["Colaborador"])]
    flujo = [m for m in fin.filtrar_fechas(fin.movimientos_caja_unificados(ctx.leer("Caja"), pagos_movs, ant_movs, pre_movs, ctx.leer("Cuentas_por_Pagar"), negocio_de),
                                           desde, hasta) if not sel_neg or m["Negocio"] in sel_neg]
    gastos = [g for g in fin.filtrar_fechas(fin.gastos_devengados(ctx.leer("Caja"), ctx.leer("Cuentas_por_Pagar"), historial, negocio_de, ctx.hoy()), desde, hasta)
              if not sel_neg or g["Negocio"] in sel_neg]
    cxp = [f for f in fin.estado_cxp(ctx.leer("Cuentas_por_Pagar"), ctx.hoy()) if f["Estado"] in ("Pendiente", "Parcial", "Vencida")
           and (not sel_neg or (f["Negocio"] or "Sin asignar") in sel_neg)]
    marcas = asi.marcas_efectivas(ctx.leer("Asistencia"))
    horarios = ctx.leer("Horarios")
    empleados_info = {n: {"cargo": i.get("cargo", ""), "negocio": i.get("negocio", "")} for n, i in ctx.empleados().items() if pasa(n)}
    hoy_tab = asi.tablero_hoy(empleados_info, marcas, horarios, ctx.ahora())
    incs = asi.incidencias(asi.jornadas(marcas), horarios, empleados_info, desde, min(hasta, ctx.hoy()), ctx.ahora(),
                           umbral_extra_min=float(ctx.aj("umbral_horas_extra_min") or 15))

    sincronizado = not ctx.almacen().pendientes()
    st.caption(("✅ Todos los datos están en Google Sheets." if sincronizado else
                f"⏳ Hay {len(ctx.almacen().pendientes())} operación(es) pendientes de sincronizar: se incluyen en los indicadores marcadas como pendientes.")
               + f" Período: {desde:%d/%m/%Y} – {hasta:%d/%m/%Y}.")
    ctx.fila_kpis([
        ctx.kpi_html("🧮", "Planilla calculada", ctx.usd(calculada), f"{len(claves)} período(s) guardado(s)", "indigo"),
        ctx.kpi_html("✅", "Pagos entregados", ctx.usd(entregado), f"{len(pagos_rango)} pago(s) en el rango", "green", "pos"),
        ctx.kpi_html("⏳", "Pendiente por entregar", ctx.usd(pendiente), "De las planillas del rango", "amber"),
        ctx.kpi_html("🤝", "Anticipos por descontar", ctx.usd(sum(a["Saldo"] for a in anticipos)), f"{sum(1 for a in anticipos if a['Saldo'] > 0.004)} activo(s)", "violet"),
    ])
    ctx.espacio(10)
    ctx.fila_kpis([
        ctx.kpi_html("🏦", "Préstamos por recuperar", ctx.usd(sum(p["Saldo"] for p in prestamos)), f"{sum(1 for p in prestamos if p['Estado'] == 'Atrasado')} atrasado(s)", "sky"),
        ctx.kpi_html("🧾", "Gastos del período", ctx.usd(sum(g["Monto"] for g in gastos)), "Caja + proveedores + planilla", "red"),
        ctx.kpi_html("📑", "Cuentas por pagar", ctx.usd(sum(f["Saldo"] for f in cxp)), f"{sum(1 for f in cxp if f['Estado'] == 'Vencida')} vencida(s)", "amber"),
        ctx.kpi_html("💵", "Caja: entradas / salidas", f"{ctx.usd(sum(m['Monto'] for m in flujo if m['Tipo'] == 'ENTRADA'))}",
                     f"Salidas {ctx.usd(sum(m['Monto'] for m in flujo if m['Tipo'] == 'SALIDA'))}", "green"),
    ])
    ctx.espacio(10)
    presentes = sum(1 for f in hoy_tab if "Trabajando" in f["Estado"] or "En pausa" in f["Estado"])
    ctx.fila_kpis([
        ctx.kpi_html("👥", "Personal activo", str(len(empleados_info)), "Colaboradores registrados", "indigo"),
        ctx.kpi_html("🕒", "Asistencia de hoy", f"{presentes} / {len(empleados_info)}", f"{sum(1 for f in hoy_tab if 'Sin marcar' in f['Estado'])} sin marcar", "sky"),
        ctx.kpi_html("⏰", "Tardanzas", str(sum(1 for i in incs if i["Tipo"] == "TARDANZA")), f"{sum(i['Minutos'] for i in incs if i['Tipo'] == 'TARDANZA'):.0f} min en el rango", "amber"),
        ctx.kpi_html("🚫", "Ausencias", str(sum(1 for i in incs if i["Tipo"] == "AUSENCIA")), f"{sum(1 for i in incs if i['Tipo'] == 'MARCACION_INCOMPLETA')} marcación(es) incompleta(s)", "red"),
    ])
    ctx.espacio(10)
    bloque_alertas(ctx, alertas_generales(ctx), "panel")

    c1, c2 = st.columns(2)
    with c1:
        with ctx.tarjeta("pa_planilla"):
            ctx.md(ctx.titulo_seccion("🧮 Calculado vs. entregado por colaborador", "Planillas de los períodos del rango."))
            if resumenes:
                df = pd.DataFrame(resumenes).groupby("Colaborador", as_index=False)[["Calculado", "Anticipos", "Cuotas_Prestamo", "Neto", "Entregado", "Pendiente"]].sum()
                largo = df.melt(id_vars="Colaborador", value_vars=["Neto", "Entregado"], var_name="Concepto", value_name="Monto")
                fig = px.bar(largo, x="Monto", y="Colaborador", color="Concepto", barmode="group", orientation="h",
                             color_discrete_map={"Neto": ctx.tema()["p"], "Entregado": "#10B981"})
                fig.update_xaxes(title=None, tickprefix="$")
                fig.update_yaxes(title=None)
                st.plotly_chart(ctx.estilo_plotly(fig, max(260, 46 * len(df) + 80)), config=ctx.PLOTLY_CONFIG, key="pa_ch_plan", **ctx.ancho(st.plotly_chart))
                cm.tabla(ctx, df.rename(columns={"Cuotas_Prestamo": "Cuotas préstamo", "Neto": "Neto a entregar"}),
                         ("Calculado", "Anticipos", "Cuotas préstamo", "Neto a entregar", "Entregado", "Pendiente"))
            else:
                st.caption("No hay planillas guardadas cuyo período termine en el rango.")
    with c2:
        with ctx.tarjeta("pa_negocio"):
            ctx.md(ctx.titulo_seccion("🏪 Resumen por negocio", "Ventas guardadas de los PDF, planilla calculada y otros gastos."))
            ventas = {}
            for v in ultimas_ventas(ctx.leer("Ventas_Periodo")):
                if fin.periodo_en_rango(v.get("Periodo"), desde, hasta) and (not sel_neg or v.get("Negocio") in sel_neg):
                    ventas[v.get("Negocio")] = ventas.get(v.get("Negocio"), 0.0) + dinero(v.get("Ventas"))
            costos = {}
            for g in gastos:
                costos.setdefault(g["Negocio"], {"Planilla": 0.0, "Otros gastos": 0.0})["Planilla" if g["Origen"] == "Planilla" else "Otros gastos"] += g["Monto"]
            nombres = sorted(set(ventas) | set(costos))
            if nombres:
                df_n = pd.DataFrame([{"Negocio": n, "Ventas": dinero(ventas.get(n, 0)), "Planilla": dinero(costos.get(n, {}).get("Planilla", 0)),
                                      "Otros gastos": dinero(costos.get(n, {}).get("Otros gastos", 0))} for n in nombres])
                df_n["Resultado"] = df_n["Ventas"] - df_n["Planilla"] - df_n["Otros gastos"]
                cm.tabla(ctx, df_n, ("Ventas", "Planilla", "Otros gastos", "Resultado"))
                st.caption("La planilla se asigna al negocio de cada colaborador (Configuración → Personal y sueldos → Negocio). Lo no asignado aparece como «Sin asignar».")
                cm.descargas(ctx, df_n, f"Resumen_negocios_{desde:%Y%m%d}_{hasta:%Y%m%d}", "Resumen por negocio", f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}",
                             ("Ventas", "Planilla", "Otros gastos", "Resultado"), key="dl_pa_neg")
            else:
                st.caption("Sin ventas ni gastos guardados en el rango.")
        with ctx.tarjeta("pa_hoy"):
            ctx.md(ctx.titulo_seccion("🕒 Asistencia de hoy"))
            cm.tabla(ctx, pd.DataFrame(hoy_tab)) if hoy_tab else st.caption("Sin colaboradores.")


def ultimas_ventas(movs):
    """Solo la versión más reciente de las ventas de cada período (al reprocesar un PDF se agrega una versión nueva)."""
    ultima = {}
    for m in movs:
        clave = m.get("Periodo")
        version = str(m.get("Version", ""))
        if clave not in ultima or version > ultima[clave]:
            ultima[clave] = version
    return [m for m in movs if str(m.get("Version", "")) == ultima.get(m.get("Periodo"))]
