"""Piezas compartidas por las páginas administrativas: guardar con confirmación real, períodos, tablas y exportaciones."""
import io
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from fpdf import FPDF

from nucleo.almacen import ErrorConexion
from nucleo.finanzas import ErrorNegocio
from nucleo.util import dinero, nuevo_id, quincenas_cercanas, rango_de_clave, texto

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
ICONOS_ESTADO = {
    "Completado": "✅", "Pagado": "✅", "Pagada": "✅", "Liquidado": "✅", "Aprobado": "✅", "Entregado": "✅", "Vigente": "🟢",
    "Registrado": "🟢", "Registrada": "🟢", "Validada": "✅", "Cumplida": "✅", "Gozadas": "✅",
    "Pendiente": "⏳", "Calculado": "🧮", "Solicitado": "⏳", "Programada": "📅", "Abierta": "🟠", "En seguimiento": "🟠", "Por renovar": "🟠",
    "Parcial": "🟡", "Atrasado": "🔴", "Vencida": "🔴", "Vencido": "🔴", "Revisar: entregado de más": "⚠️",
    "Anulado": "⛔", "Anulada": "⛔", "Corregido": "✏️", "Cancelado": "⚪", "Rechazado": "⛔", "Cerrada": "⚪", "Finalizado": "⚪",
    "No aplica": "⚪", "Sin saldo por entregar": "⚪",
}


def con_icono(estado):
    return f"{ICONOS_ESTADO.get(estado, '•')} {estado}"


# ---------------------------------------------------------------------
# Operaciones (idempotencia + mensajes honestos)
# ---------------------------------------------------------------------
def id_operacion(clave, prefijo="OP"):
    """ID estable mientras el formulario no se envíe con éxito: repetir el envío no duplica la operación."""
    k = f"_op_{clave}"
    if k not in st.session_state:
        st.session_state[k] = nuevo_id(prefijo)
    return st.session_state[k]


def rotar_operacion(clave):
    st.session_state.pop(f"_op_{clave}", None)


def mostrar_resultado(ctx, resultado, exito):
    """Solo dice «guardado» si de verdad quedó en Google Sheets."""
    if resultado.estado == "guardado":
        ctx.notificar(exito, "✅")
    elif resultado.estado == "ya_existia":
        ctx.notificar(resultado.mensaje, "ℹ️")
    elif resultado.estado == "pendiente":
        ctx.notificar_aviso(f"⏳ {exito.rstrip('.')}, pero: {resultado.mensaje}")
    else:
        ctx.notificar_error(resultado.mensaje)


def ejecutar(ctx, tabla, construir, exito, auditoria=None, rotar=None, recargar=True):
    """Construye la operación (puede lanzar ErrorNegocio/ErrorConexion), la guarda y muestra el resultado.

    construir: función sin argumentos que devuelve un registro o una lista de registros.
    Devuelve el Resultado, o None si la operación no pasó las validaciones (el formulario conserva los datos).
    """
    try:
        registro = construir()
    except (ErrorNegocio, ErrorConexion) as ex:
        st.error(f"⚠️ {ex}")
        return None
    alm = ctx.almacen()
    resultado = alm.registrar_varios(tabla, registro) if isinstance(registro, list) else alm.registrar(tabla, registro)
    if resultado.estado in ("guardado", "ya_existia", "pendiente") and rotar:
        rotar_operacion(rotar)
    mostrar_resultado(ctx, resultado, exito)
    if auditoria and resultado.estado in ("guardado", "pendiente"):
        ctx.registrar_auditoria(*auditoria)
    if recargar and resultado.estado != "rechazado":
        st.rerun()
    return resultado


def lectura_fresca(ctx, tabla):
    """Lectura obligatoria para validar saldos. Si falla, lanza ErrorConexion (la operación no se hace)."""
    return ctx.almacen().leer_para_validar(tabla)


def aviso_lectura(ctx, *tablas):
    errores = {t: ctx.almacen().errores_lectura.get(t) for t in tablas if ctx.almacen().errores_lectura.get(t)}
    if errores:
        st.warning("No se pudo leer Google Sheets en este momento: se muestran los últimos datos conocidos y las operaciones pendientes de esta sesión. "
                   + " · ".join(f"{t}: {e[:120]}" for t, e in errores.items()))


# ---------------------------------------------------------------------
# Períodos de planilla
# ---------------------------------------------------------------------
def etiqueta_periodo(clave):
    r = rango_de_clave(clave)
    if not r:
        return texto(clave) or "Sin período"
    a, b = r
    mes = f"{MESES[a.month - 1]} {a.year}"
    fin_mes = date(a.year + (a.month == 12), a.month % 12 + 1, 1) - timedelta(days=1)
    if (a.year, a.month) == (b.year, b.month):
        if a.day == 1 and b.day == 15:
            return f"1.ª quincena de {mes}"
        if a.day == 16 and b == fin_mes:
            return f"2.ª quincena de {mes}"
        if a.day == 1 and b == fin_mes:
            return f"Mes de {mes}"
    return f"Del {a:%d/%m/%Y} al {b:%d/%m/%Y}"


def opciones_periodo(ctx, incluir=()):
    claves = list(incluir) + [ctx.periodo_actual()[0]] + ctx.periodos_historial() + quincenas_cercanas(ctx.hoy(), antes=2, despues=2)
    vistas = []
    for c in claves:
        if c and c not in vistas:
            vistas.append(c)
    return vistas


def selector_periodo(ctx, etiqueta, key, incluir=(), vacio=None, ayuda=None, destino=None):
    opciones = opciones_periodo(ctx, incluir)
    if vacio is not None:
        opciones = [""] + opciones
    actual = ctx.periodo_actual()[0]
    if key not in st.session_state and actual in opciones:
        st.session_state[key] = actual
    return (destino or st).selectbox(etiqueta, opciones, key=key, help=ayuda,
                                     format_func=lambda c: (vacio or "—") if c == "" else f"{etiqueta_periodo(c)} · {c}")


# ---------------------------------------------------------------------
# Tablas y exportaciones
# ---------------------------------------------------------------------
def tabla(ctx, df, dinero_cols=(), alto=None, key=None):
    if df is None or df.empty:
        st.caption("Sin registros.")
        return
    cols = [c for c in dinero_cols if c in df.columns]
    estilo = df.style.format("${:,.2f}", subset=cols) if cols else df
    kwargs = {"hide_index": True}
    if alto:
        kwargs["height"] = alto
    if key:
        kwargs["key"] = key
    st.dataframe(estilo, **kwargs, **ctx.ancho(st.dataframe))


def excel_bytes(df, hoja="Datos"):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        df.to_excel(escritor, index=False, sheet_name=hoja[:31])
        ws = escritor.sheets[hoja[:31]]
        for i, col in enumerate(df.columns, 1):
            largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(200).tolist()])
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(48, max(10, largo + 2))
    return buffer.getvalue()


def pdf_tabla(ctx, titulo, subtitulo, df, dinero_cols=()):
    """Listado imprimible en PDF horizontal con el encabezado de la empresa."""

    class PDFListado(FPDF):
        def header(self):
            ctx.encabezado_pdf(self, titulo, linea_extra=subtitulo)

        def footer(self):
            self.set_y(-12)
            self.set_font("helvetica", "", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 8, ctx.limpiar_texto_pdf(f"Generado el {ctx.ahora():%d/%m/%Y %H:%M} por {ctx.usuario()['nombre']} · Página {self.page_no()}"), 0, 0, "C")

    pdf = PDFListado(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, 16)
    pdf.add_page()
    columnas = list(df.columns)
    if not columnas:
        return bytes(pdf.output())
    largos = [max([len(str(c))] + [len(str(v)) for v in df[c].head(300).tolist()]) for c in columnas]
    total = sum(min(l, 40) for l in largos) or 1
    anchos = [max(14.0, 277.0 * min(l, 40) / total) for l in largos]
    escala = 277.0 / sum(anchos)
    anchos = [a * escala for a in anchos]
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(10, 25, 47)
    pdf.set_text_color(255, 255, 255)
    for c, w in zip(columnas, anchos):
        pdf.cell(w, 7, ctx.limpiar_texto_pdf(str(c))[:int(w / 1.6)], 1, 0, "C", fill=True)
    pdf.ln()
    pdf.set_font("helvetica", "", 7.5)
    pdf.set_text_color(40, 40, 40)
    for i, fila in enumerate(df.itertuples(index=False)):
        pdf.set_fill_color(248, 250, 252) if i % 2 else pdf.set_fill_color(255, 255, 255)
        for c, w, v in zip(columnas, anchos, fila):
            es_dinero = c in dinero_cols
            txt = f"${dinero(v):,.2f}" if es_dinero else texto(v)
            pdf.cell(w, 6, ctx.limpiar_texto_pdf(txt)[:int(w / 1.45)], 1, 0, "R" if es_dinero else "L", fill=True)
        pdf.ln()
    if dinero_cols:
        pdf.set_font("helvetica", "B", 8)
        pdf.set_fill_color(238, 242, 255)
        for j, (c, w) in enumerate(zip(columnas, anchos)):
            if c in dinero_cols:
                txt = f"${sum(dinero(v) for v in df[c].tolist()):,.2f}"
            else:
                txt = "TOTAL" if j == 0 else ""
            pdf.cell(w, 7, txt, 1, 0, "R" if c in dinero_cols else "L", fill=True)
        pdf.ln()
    return bytes(pdf.output())


def descargas(ctx, df, nombre, titulo_pdf=None, subtitulo_pdf="", dinero_cols=(), key="dl"):
    """Botones para exportar: CSV (Excel en español), Excel (.xlsx) y PDF imprimible."""
    if df is None or df.empty:
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("⬇️ CSV", data=df.to_csv(index=False).encode("utf-8-sig"), file_name=f"{nombre}.csv", mime="text/csv",
                           key=f"{key}_csv", **ctx.ancho(st.download_button))
    with c2:
        st.download_button("⬇️ Excel", data=excel_bytes(df), file_name=f"{nombre}.xlsx", key=f"{key}_xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **ctx.ancho(st.download_button))
    with c3:
        st.download_button("🖨️ PDF para imprimir", data=pdf_tabla(ctx, titulo_pdf or nombre, subtitulo_pdf, df, dinero_cols),
                           file_name=f"{nombre}.pdf", mime="application/pdf", key=f"{key}_pdf", **ctx.ancho(st.download_button))


def filtro_fechas(ctx, key, defecto_dias=30, destino=None):
    """Rango de fechas con atajos (quincena actual, mes actual, mes anterior, últimos N días)."""
    hoy = ctx.hoy()
    inicio_q = date(hoy.year, hoy.month, 1 if hoy.day <= 15 else 16)
    inicio_mes = date(hoy.year, hoy.month, 1)
    fin_mes_ant = inicio_mes - timedelta(days=1)
    opciones = {"Quincena actual": (inicio_q, hoy), "Mes actual": (inicio_mes, hoy),
                "Mes anterior": (date(fin_mes_ant.year, fin_mes_ant.month, 1), fin_mes_ant),
                f"Últimos {defecto_dias} días": (hoy - timedelta(days=defecto_dias), hoy),
                "Este año": (date(hoy.year, 1, 1), hoy), "Personalizado": None}
    zona = destino or st
    a, b = zona.columns([1.2, 1.6]) if destino is None else (zona, zona)
    atajo = a.selectbox("Período", list(opciones), index=1, key=f"{key}_atajo")
    if opciones[atajo] is None:
        rango = b.date_input("Desde – hasta", value=(hoy - timedelta(days=defecto_dias), hoy), format="DD/MM/YYYY", key=f"{key}_rango")
        if isinstance(rango, (list, tuple)) and len(rango) == 2:
            return rango[0], rango[1]
        return hoy, hoy
    desde, hasta = opciones[atajo]
    b.caption(f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}")
    return desde, hasta
