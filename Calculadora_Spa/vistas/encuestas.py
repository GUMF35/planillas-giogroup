"""Visitas, encuestas por QR y cupones: pantalla pública del cliente (teléfono) y pantalla de recepción."""
import html
from urllib.parse import quote

import pandas as pd
import streamlit as st

from nucleo import visitas as vis
from nucleo.finanzas import ErrorNegocio
from nucleo.util import texto, usd

from . import comun as cm

USUARIO_CLIENTE = "Cliente (encuesta)"


def url_base(ctx):
    return (texto(ctx.secreto("app_url")) or texto(ctx.aj("url_app"))).rstrip("/")


def url_encuesta(ctx, codigo):
    base = url_base(ctx)
    return f"{base}/?encuesta={quote(codigo)}" if base else ""


def qr_uri(url):
    """QR como imagen incrustada, generado aquí mismo (no se envía el enlace a ningún servicio externo)."""
    import segno
    return segno.make(url, error="m").png_data_uri(scale=8, border=2)


def tarjeta_cupon(ctx, cupon):
    t = ctx.tema()
    ctx.md(f"<div style='background:linear-gradient(135deg,{t['p']} 0%,{t['acc']} 100%);padding:25px;border-radius:16px;color:#fff;text-align:center;"
           f"margin-top:18px;box-shadow:0 10px 25px rgba(0,0,0,.12)'><div style='font-weight:800;font-size:26px'>TU CUPÓN: {html.escape(texto(cupon.get('Descuento')))}</div>"
           f"<div style='margin:8px 0 14px;opacity:.92;font-size:14px'>Muéstralo en caja en tu próxima visita · válido hasta el {html.escape(texto(cupon.get('Vencimiento')))}</div>"
           f"<div style='background:rgba(255,255,255,.25);padding:12px;border-radius:8px;font-family:monospace;font-size:24px;font-weight:bold;letter-spacing:3px'>"
           f"{html.escape(texto(cupon.get('Codigo_Cupon')))}</div></div>")


# =====================================================================
# Pantalla pública (cliente, sin inicio de sesión)
# =====================================================================
def pantalla_publica(ctx, codigo):
    codigo = texto(codigo).upper()
    st.image(ctx.img_logo(), width=96)
    alm = ctx.almacen()
    if not vis.codigo_valido(codigo):
        ctx.md(ctx.titulo_seccion("Código no válido", "Revisa el código o vuelve a escanear el QR."))
        return
    visitas = ctx.leer("Visitas")
    if alm.errores_lectura.get("Visitas") and not visitas:
        ctx.md(ctx.titulo_seccion("Estamos teniendo un problema", "No pudimos cargar la encuesta. Inténtalo de nuevo en unos minutos."))
        return
    visita = vis.buscar_visita(visitas, codigo)
    if not visita or texto(visita.get("Estado")) == "Cancelada":
        ctx.md(ctx.titulo_seccion("Código no válido", "Este código no existe o ya no está disponible."))
        return

    if vis.encuesta_de(ctx.leer("Encuestas"), codigo):
        cupon = vis.cupon_de_visita(ctx.leer("Cupones"), codigo)
        if cupon is None:  # la encuesta se guardó pero el cupón no llegó a emitirse: se emite ahora (una sola vez)
            alm.registrar("Cupones", vis.nuevo_cupon(codigo, ctx.aj("cupon_pct"), ctx.aj("cupon_dias")), usuario=USUARIO_CLIENTE)
            cupon = vis.cupon_de_visita(ctx.leer("Cupones", forzar=True), codigo)
        ctx.md(ctx.titulo_seccion("¡Gracias por tu visita!", "Ya recibimos tu evaluación."))
        if cupon:
            tarjeta_cupon(ctx, cupon)
        return

    ctx.md(ctx.titulo_seccion("Tu opinión nos ayuda a mejorar", f"Te atendió: {html.escape(texto(visita.get('Colaborador')) or 'nuestro equipo')}"))
    with st.form("form_encuesta"):
        sat = st.radio("¿Qué tan satisfecho quedaste con tu experiencia?", vis.RESPUESTAS_SATISFACCION, index=None)
        aten = st.radio("¿Cómo fue la atención que recibiste?", vis.RESPUESTAS_ATENCION, index=None)
        pagos = st.radio("Sobre tu pago, ¿alguien te pidió dinero fuera de los precios oficiales?", vis.RESPUESTAS_PAGOS, index=None)
        comentario = st.text_area("Comentario adicional (opcional)", max_chars=500)
        enviado = st.form_submit_button(f"Enviar y obtener {int(ctx.aj('cupon_pct') or 5)}% de descuento", type="primary", **ctx.ancho(st.form_submit_button))
    if enviado:
        try:
            encuesta = vis.nueva_encuesta(codigo, sat, aten, pagos, comentario)
        except ErrorNegocio as ex:
            st.error(str(ex))
            return
        r1 = alm.registrar("Encuestas", encuesta, usuario=USUARIO_CLIENTE)
        if r1.estado == "rechazado":
            st.error("No pudimos guardar tu respuesta. Inténtalo de nuevo.")
            return
        alm.registrar("Cupones", vis.nuevo_cupon(codigo, ctx.aj("cupon_pct"), ctx.aj("cupon_dias")), usuario=USUARIO_CLIENTE)
        st.rerun()


# =====================================================================
# Pantalla de recepción (administración)
# =====================================================================
def pagina_admin(ctx):
    ctx.encabezado_pagina("🛎️", "Visitas y recepción", "Registra visitas, entrega el QR de la encuesta, canjea cupones y revisa lo que opinan los clientes.")
    cm.aviso_lectura(ctx, "Visitas", "Encuestas", "Cupones")
    t1, t2, t3 = st.tabs(["📝 Registrar visita", "🎟️ Canjear cupón", "📊 Resultados de encuestas"])
    with t1:
        registrar_visita(ctx)
    with t2:
        canjear(ctx)
    with t3:
        resultados(ctx)


def registrar_visita(ctx):
    ss = st.session_state
    c1, c2 = st.columns([1.4, 1])
    with c1:
        with ctx.tarjeta("nueva_visita"):
            ctx.md(ctx.titulo_seccion("Nueva visita", "Se guarda en Google Sheets y se genera el QR para el cliente."))
            if not url_base(ctx):
                st.warning("Falta la dirección pública de tu app (la que aparece en el navegador, como https://tu-app.streamlit.app). Escríbela para que el QR funcione.")
                dir_app = st.text_input("Dirección de la app", key="vis_url", placeholder="https://tu-app.streamlit.app")
                if st.button("💾 Guardar dirección", key="vis_url_btn") and dir_app.strip().startswith("https://"):
                    ctx.aj_set("url_app", dir_app.strip())
                    ctx.notificar("Dirección guardada.")
                    st.rerun()
            colab = st.selectbox("Colaborador que atendió", list(ctx.empleados()), key="vis_colab")
            negocios = ctx.lista("negocios")
            marca = st.selectbox("Marca / negocio", negocios, key="vis_marca") if negocios else ""
            servicio = st.text_input("Servicio realizado", key="vis_servicio")
            precio = st.number_input("Precio cobrado ($)", min_value=0.0, step=0.5, format="%.2f", key="vis_precio")
            if st.button("➕ Registrar visita y generar QR", type="primary", key="vis_btn", **ctx.ancho(st.button)):
                codigo = ss.setdefault("_cod_visita_pend", vis.codigo_nuevo())  # el mismo código si se repite el clic
                try:
                    reg = vis.nueva_visita(colab, marca, servicio, precio, codigo)
                except ErrorNegocio as ex:
                    st.error(f"⚠️ {ex}")
                else:
                    r = ctx.almacen().registrar("Visitas", reg)
                    if r.estado != "rechazado":
                        ss.pop("_cod_visita_pend", None)
                        ss["ultimo_codigo"] = codigo
                    cm.mostrar_resultado(ctx, r, f"Visita registrada ({usd(precio)}).")
                    st.rerun()
    with c2:
        codigo = ss.get("ultimo_codigo")
        with ctx.tarjeta("qr_visita"):
            if not codigo:
                ctx.md("<div style='text-align:center;padding:36px 0;color:#94A3B8'>Registra una visita para generar el QR.</div>")
                return
            ctx.md(ctx.titulo_seccion("Código de la visita", "Muéstraselo al cliente o dile que escanee el QR."))
            enlace = url_encuesta(ctx, codigo)
            if enlace:
                st.image(qr_uri(enlace), width=240)
                st.caption("Enlace de la encuesta")
                st.code(enlace, language=None)
            else:
                st.info("Configura la dirección de la app para ver el QR.")
            st.code(codigo, language=None)


def canjear(ctx):
    with ctx.tarjeta("canje"):
        ctx.md(ctx.titulo_seccion("Canjear cupón", "Se canjea una sola vez y solo si no ha vencido."))
        codigo = st.text_input("Código del cupón", key="canje_codigo", placeholder="GIO-ABC123")
        cupones = ctx.leer("Cupones", forzar=True)
        cupon, estado = vis.estado_cupon(cupones, codigo, ctx.hoy()) if texto(codigo) else (None, "")
        if estado == "Disponible":
            st.success(f"Cupón válido: {cupon.get('Descuento')} · vence el {cupon.get('Vencimiento')}.")
        elif estado:
            st.error({"No existe": "El cupón no existe.", "Canjeado": "Este cupón YA FUE UTILIZADO.", "Vencido": f"El cupón venció el {cupon.get('Vencimiento') if cupon else ''}.",
                      "Anulado": "El cupón está anulado."}[estado])
        obs = st.text_input("Observaciones (ticket o factura donde se aplicó)", key="canje_obs")
        if st.button("✅ Canjear ahora", type="primary", disabled=estado != "Disponible", key="canje_btn"):
            cm.ejecutar(ctx, "Cupones", lambda: vis.preparar_canje(cm.lectura_fresca(ctx, "Cupones"), codigo, ctx.hoy(), obs),
                        f"Cupón {codigo.strip().upper()} canjeado.", auditoria=("Cupón canjeado", codigo.strip().upper()))


def resultados(ctx):
    visitas, encuestas = ctx.leer("Visitas"), ctx.leer("Encuestas")
    resumen, revisar = vis.resultados(visitas, encuestas)
    n_vis = sum(1 for v in visitas if str(v.get("Movimiento")).upper() == "VISITA")
    ctx.fila_kpis([
        ctx.kpi_html("🛎️", "Visitas registradas", str(n_vis), "Con código QR", "indigo"),
        ctx.kpi_html("📝", "Encuestas respondidas", str(sum(r["Encuestas"] for r in resumen)),
                     f"{(sum(r['Encuestas'] for r in resumen) / n_vis * 100 if n_vis else 0):.0f}% de las visitas", "green"),
        ctx.kpi_html("⭐", "Satisfacción promedio",
                     f"{(sum(r['Satisfacción promedio'] * r['Encuestas'] for r in resumen) / max(1, sum(r['Encuestas'] for r in resumen))):.2f} / 5" if resumen else "—",
                     "Pregunta 1", "amber"),
        ctx.kpi_html("🚩", "Para revisar", str(len(revisar)), "Satisfacción baja, mala atención o cobros fuera de precio", "red"),
    ])
    with ctx.tarjeta("enc_resumen"):
        ctx.md(ctx.titulo_seccion("Por colaborador"))
        if resumen:
            cm.tabla(ctx, pd.DataFrame(resumen))
        else:
            st.caption("Aún no hay encuestas respondidas.")
    if revisar:
        with ctx.tarjeta("enc_alertas"):
            ctx.md(ctx.titulo_seccion("🚩 Respuestas que merecen revisión", "Una alerta no prueba nada: es un aviso para conversar con el cliente y el colaborador."))
            df = pd.DataFrame(revisar)
            cm.tabla(ctx, df)
            cm.descargas(ctx, df, "Encuestas_para_revisar", "Encuestas para revisar", f"Al {ctx.hoy():%d/%m/%Y}", key="dl_enc")
