"""Página «Expediente»: todo lo de una persona en un solo lugar + alertas de fechas importantes de toda la empresa."""
import html
from datetime import timedelta

import pandas as pd
import streamlit as st

from nucleo import asistencia as asi
from nucleo import finanzas as fin
from nucleo import personal as per

from . import comun as cm


def alertas_generales(ctx):
    hoy = ctx.hoy()
    return per.alertas(hoy, per.estado_expediente(ctx.leer("Expediente")), fin.estado_prestamos(ctx.leer("Prestamos"), hoy),
                       fin.estado_anticipos(ctx.leer("Anticipos")), fin.estado_cxp(ctx.leer("Cuentas_por_Pagar"), hoy), ctx.proveedores(),
                       int(ctx.aj("dias_alerta") or 30))


def bloque_alertas(ctx, alertas, clave="exp"):
    altas = sum(1 for a in alertas if a["Nivel"] == "Alta")
    medias = sum(1 for a in alertas if a["Nivel"] == "Media")
    with st.expander(f"🔔 Alertas · {altas} urgentes · {medias} por atender · {len(alertas) - altas - medias} informativas", expanded=altas > 0):
        if not alertas:
            st.success("Sin alertas: no hay vencimientos ni pendientes próximos.")
            return
        icono = {"Alta": "🔴", "Media": "🟠", "Info": "🔵"}
        cm.tabla(ctx, pd.DataFrame([{"Nivel": f"{icono[a['Nivel']]} {a['Nivel']}", "Tipo": a["Tipo"], "Quién": a["Quien"], "Fecha": a["Fecha"],
                                     "Detalle": a["Mensaje"]} for a in alertas]), key=f"tabla_alertas_{clave}")


def pagina(ctx):
    ctx.encabezado_pagina("🪪", "Expediente del colaborador", "Pagos, anticipos, préstamos, horario, asistencia, permisos, contratos, documentos e historial de cada persona.")
    bloque_alertas(ctx, alertas_generales(ctx))
    empleados = ctx.empleados()
    if not empleados:
        st.info("No hay colaboradores registrados.")
        return
    colab = st.selectbox("🔎 Colaborador", list(empleados), key="exp_colab")
    info = empleados[colab]
    expediente = [r for r in per.estado_expediente(ctx.leer("Expediente")) if r.get("Colaborador") == colab]
    pagos = [p for p in fin.estado_pagos(ctx.leer("Pagos_Personal")) if p.get("Colaborador") == colab]
    anticipos = [a for a in fin.estado_anticipos(ctx.leer("Anticipos")) if a["Colaborador"] == colab]
    prestamos = [p for p in fin.estado_prestamos(ctx.leer("Prestamos"), ctx.hoy()) if p["Colaborador"] == colab]
    marcas = asi.marcas_efectivas(ctx.leer("Asistencia"), colab)
    horarios = ctx.leer("Horarios")
    cuenta = info.get("cuenta", "")
    cuenta_oculta = f"•••• {cuenta[-4:]}" if len(cuenta) >= 4 else (cuenta or "Sin registrar")

    with ctx.tarjeta("exp_head"):
        e = html.escape
        chips = "".join(ctx.chip(e(t), c) for t, c in [
            (f"💼 {info.get('cargo') or info.get('rol')}", "indigo"), (f"🏪 {info.get('negocio') or 'Negocio sin asignar'}", ""),
            (f"📅 Ingreso: {info.get('fecha_ingreso') or '—'}", ""), (f"🪪 DUI: {info.get('dui') or '—'}", ""),
            (f"🏦 {info.get('banco') or 'Banco'} {cuenta_oculta}", "sky"), (f"📧 {info.get('correo') or 'Sin correo'}", "")])
        iniciales = "".join(p[0] for p in colab.split()[:2] if p).upper()
        ctx.md(f"<div class='crm-head'><div class='crm-avatar'>{e(iniciales)}</div><div>"
               f"<div class='crm-kicker'>Colaborador</div><div class='crm-name'>{e(colab)}</div>"
               f"<div class='crm-desc'>{e(info.get('rol', ''))} · {e(info.get('mod', ''))}</div><div class='chips' style='margin-top:10px'>{chips}</div></div></div>")
    anio = ctx.hoy().year
    vigentes = [p for p in pagos if p["Estado"] == "Completado" and str(p.get("Fecha", "")).startswith(str(anio))]
    hace30 = ctx.hoy() - timedelta(days=30)
    jornadas = [j for j in asi.jornadas(marcas) if j["Fecha"] >= hace30]
    pendientes_doc = [r for r in expediente if r.get("Tipo") == "DOCUMENTO" and r["Estado_Actual"] == "Pendiente"]
    ctx.fila_kpis([
        ctx.kpi_html("💸", f"Pagado en {anio}", ctx.usd(sum(p["Monto"] for p in vigentes)), f"{len(vigentes)} pago(s)", "green"),
        ctx.kpi_html("🤝", "Anticipos por descontar", ctx.usd(sum(a["Saldo"] for a in anticipos)), f"Préstamos: saldo {ctx.usd(sum(p['Saldo'] for p in prestamos))}", "amber"),
        ctx.kpi_html("🕒", "Asistencia (30 días)", f"{len(jornadas)} días", f"{sum(j['Trabajado_Min'] for j in jornadas) / 60:.1f} horas trabajadas", "sky"),
        ctx.kpi_html("📄", "Documentos pendientes", str(len(pendientes_doc)), f"{len(expediente)} registro(s) en el expediente", "violet"),
    ])

    t1, t2, t3, t4, t5, t6 = st.tabs(["📋 Resumen", "🏖️ Permisos y ausencias", "📑 Contratos y documentos", "🗒️ Observaciones", "🕓 Historial", "➕ Nuevo registro"])
    with t1:
        resumen(ctx, colab, info, pagos, anticipos, prestamos, marcas, horarios)
    with t2:
        lista_registros(ctx, expediente, ("PERMISO", "VACACIONES", "INCAPACIDAD"), "exp_aus")
    with t3:
        lista_registros(ctx, expediente, ("CONTRATO", "DOCUMENTO", "FECHA_IMPORTANTE"), "exp_doc")
    with t4:
        lista_registros(ctx, expediente, ("OBSERVACION", "INCIDENCIA"), "exp_obs")
    with t5:
        historial(ctx, colab, expediente)
    with t6:
        nuevo_registro(ctx, colab)


def resumen(ctx, colab, info, pagos, anticipos, prestamos, marcas, horarios):
    c1, c2 = st.columns(2)
    with c1:
        with ctx.tarjeta("exp_pagos"):
            ctx.md(ctx.titulo_seccion("💸 Últimos pagos"))
            if pagos:
                cm.tabla(ctx, pd.DataFrame([{"Fecha": p["Fecha"], "Concepto": p["Concepto"], "Período": p["Periodo"], "Monto": p["Monto"],
                                             "Estado": cm.con_icono(p["Estado"])} for p in reversed(pagos[-10:])]), ("Monto",))
            else:
                st.caption("Sin pagos registrados.")
        with ctx.tarjeta("exp_deudas"):
            ctx.md(ctx.titulo_seccion("🤝 Anticipos y préstamos activos"))
            activos = [{"Tipo": "Anticipo", "Fecha": a["Fecha"], "Monto": a["Monto"], "Saldo": a["Saldo"], "Estado": cm.con_icono(a["Estado"])}
                       for a in anticipos if a["Estado"] in ("Pendiente", "Parcial")]
            activos += [{"Tipo": "Préstamo", "Fecha": p["Fecha"], "Monto": p["Capital"], "Saldo": p["Saldo"], "Estado": cm.con_icono(p["Estado"])}
                        for p in prestamos if p["Estado"] in ("Vigente", "Atrasado")]
            cm.tabla(ctx, pd.DataFrame(activos), ("Monto", "Saldo")) if activos else st.caption("Sin saldos pendientes.")
    with c2:
        with ctx.tarjeta("exp_horario"):
            ctx.md(ctx.titulo_seccion("🗓️ Horario vigente"))
            h = asi.resolver_horario(horarios, colab, info.get("cargo"), info.get("negocio"), ctx.hoy())
            if not h:
                st.caption("Sin horario asignado (Asistencia y horarios → Horarios y turnos).")
            else:
                version = next((v for v in horarios if v.get("ID") == h["ID"]), {})
                cm.tabla(ctx, pd.DataFrame([{asi.DIAS_NOMBRE[d]: version.get(d) or "Libre" for d in asi.DIAS_CLAVE}]))
                st.caption(f"{h['Nombre_Turno']} · {h['Alcance']} · almuerzo {h['Almuerzo_Min']:g} min · tolerancia {h['Tolerancia_Min']:g} min")
        with ctx.tarjeta("exp_marcas"):
            ctx.md(ctx.titulo_seccion("🕒 Últimas marcaciones"))
            if marcas:
                cm.tabla(ctx, pd.DataFrame([{"Fecha y hora": m["Fecha_Hora"].strftime("%d/%m/%Y %H:%M"), "Tipo": asi.ETIQUETAS_TIPO.get(m["Tipo"]),
                                             "Corregida": "✏️" if m["Corregida"] else ""} for m in reversed(marcas[-10:])]))
            else:
                st.caption("Sin marcaciones.")


def lista_registros(ctx, expediente, tipos, clave):
    regs = [r for r in expediente if r.get("Tipo") in tipos]
    if not regs:
        st.caption("Sin registros. Usa la pestaña «➕ Nuevo registro».")
        return
    df = pd.DataFrame([{"Tipo": r["Tipo_Texto"], "Título": r.get("Titulo"), "Desde": r.get("Fecha_Inicio"), "Hasta / vence": r.get("Fecha_Fin"),
                        "Estado": cm.con_icono(r["Estado_Actual"]), "Detalle": r.get("Detalle"), "Documento": r.get("Documento"),
                        "Registrado por": r.get("Usuario"), "ID": r.get("ID")} for r in reversed(regs)])
    cm.tabla(ctx, df, key=f"tabla_{clave}")
    activos = [r for r in regs if not r["Anulado"]]
    if not activos:
        return
    with st.expander("🔁 Cambiar el estado de un registro (aprobar, rechazar, entregar…)"):
        etiquetas = {r["ID"]: f"{r['Tipo_Texto']} · {r.get('Titulo')} · {r['Estado_Actual']} · {r['ID']}" for r in reversed(activos)}
        rid = st.selectbox("Registro", list(etiquetas), format_func=etiquetas.get, key=f"{clave}_sel")
        reg = next(r for r in activos if r["ID"] == rid)
        estados = [e for e in per.TIPOS_EXPEDIENTE[reg["Tipo"]][1] if e != reg["Estado_Actual"]]
        if not estados:
            st.caption("Este tipo de registro no tiene otros estados.")
            return
        a, b = st.columns([1, 2])
        nuevo = a.selectbox("Nuevo estado", estados, key=f"{clave}_estado")
        comentario = b.text_input("Comentario", key=f"{clave}_coment")
        if st.button("💾 Guardar estado", type="primary", key=f"{clave}_btn"):
            cm.ejecutar(ctx, "Expediente", lambda: per.preparar_cambio_estado(ctx.almacen().leer("Expediente", forzar=True), rid, nuevo, comentario),
                        f"Estado actualizado a «{nuevo}».", auditoria=(f"Expediente: {reg['Tipo_Texto']} → {nuevo}", reg.get("Colaborador")))


def historial(ctx, colab, expediente):
    cambios = [r for r in expediente if r.get("Tipo") in ("CAMBIO_CARGO", "CAMBIO_SALARIO", "CAMBIO_FORMA_PAGO", "ALTA", "BAJA")]
    with ctx.tarjeta("exp_cambios"):
        ctx.md(ctx.titulo_seccion("🕓 Cambios de cargo, salario y forma de pago", "Se registran solos cada vez que se guarda el personal."))
        if cambios:
            cm.tabla(ctx, pd.DataFrame([{"Fecha": str(r.get("Registrado", ""))[:16], "Cambio": r["Tipo_Texto"], "Antes": r.get("Valor_Anterior"),
                                         "Después": r.get("Valor_Nuevo"), "Por": r.get("Usuario")} for r in reversed(cambios)]))
        else:
            st.caption("Sin cambios registrados desde que se activó el expediente.")
    with ctx.tarjeta("exp_docs_emitidos"):
        ctx.md(ctx.titulo_seccion("⚠️ Amonestaciones, memorándums y recibos", "Desde el historial de documentos."))
        docs = [d for d in ctx.auditoria() if d.get("Destinatario") == colab]
        if docs:
            cm.tabla(ctx, pd.DataFrame([{"Fecha": d.get("Fecha"), "Documento": d.get("Tipo Documento"), "Por": d.get("Usuario", "")} for d in reversed(docs)]))
        else:
            st.caption("Sin documentos emitidos.")
    horarios = [v for v in asi.versiones_vigentes(ctx.leer("Horarios")) if v.get("Alcance_Tipo") == "Colaborador" and v.get("Alcance") == colab]
    if horarios:
        with ctx.tarjeta("exp_hist_hor"):
            ctx.md(ctx.titulo_seccion("🗓️ Historial de horarios"))
            cm.tabla(ctx, pd.DataFrame([{"Turno": v.get("Nombre_Turno"), "Desde": v.get("Vigente_Desde"), "Hasta": v.get("Vigente_Hasta") or "—",
                                         **{asi.DIAS_NOMBRE[d][:3]: v.get(d) or "Libre" for d in asi.DIAS_CLAVE}} for v in reversed(horarios)]))


def nuevo_registro(ctx, colab):
    with ctx.tarjeta("exp_nuevo"):
        ctx.md(ctx.titulo_seccion(f"➕ Nuevo registro para {colab}", "Permisos, vacaciones, incapacidades, contratos, documentos pendientes, observaciones o fechas importantes."))
        tipo = st.selectbox("Tipo", list(per.TIPOS_MANUALES), format_func=lambda t: per.TIPOS_EXPEDIENTE[t][0], key="exp_n_tipo")
        with st.form("form_expediente"):
            titulo = st.text_input("Título *", key="exp_n_titulo",
                                   placeholder={"CONTRATO": "Contrato por servicios 2026", "DOCUMENTO": "Copia de DUI", "PERMISO": "Cita médica"}.get(tipo, ""))
            a, b, c = st.columns(3)
            ini = a.date_input("Fecha de inicio", value=ctx.hoy(), format="DD/MM/YYYY", key="exp_n_ini")
            fin_d = b.date_input("Fecha final / vencimiento / límite", value=None, format="DD/MM/YYYY", key="exp_n_fin")
            estado = c.selectbox("Estado", list(per.TIPOS_EXPEDIENTE[tipo][1]), key=f"exp_n_estado_{tipo}")
            detalle = st.text_area("Detalle", key="exp_n_detalle", height=80)
            documento = st.text_input("Documento de respaldo (número o enlace a Drive)", key="exp_n_doc")
            enviado = st.form_submit_button("💾 Guardar en el expediente", type="primary")
        if enviado:
            cm.ejecutar(ctx, "Expediente", lambda: dict(per.nuevo_registro(colab, tipo, titulo, ini, fin_d or "", estado, detalle, documento),
                                                         ID=cm.id_operacion("expediente", "EXP")),
                        "Registro guardado en el expediente.", auditoria=(f"Expediente: {per.TIPOS_EXPEDIENTE[tipo][0]}", colab), rotar="expediente")
