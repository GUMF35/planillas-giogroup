"""Recorrido completo por la interfaz: llena los formularios de cada módulo nuevo y abre todas las páginas con datos.
Detecta errores que solo aparecen cuando hay información (tablas, gráficos, exportaciones a Excel y PDF)."""
import os

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app.py")


def correr(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def ir(at, pagina):
    at.session_state["pagina"] = pagina
    correr(at)


def boton(at, texto):
    return next(b for b in at.button if texto in b.label)


def pendientes(at, tabla):
    return [i["registro"] for i in at.session_state["_almacen"].pendientes(tabla)]


@pytest.fixture(scope="module")
def at(tmp_path_factory):
    os.environ["GIO_DIR_DATOS"] = str(tmp_path_factory.mktemp("datos"))
    app = AppTest.from_file(APP, default_timeout=120)
    correr(app)
    return app


def test_pago_manual(at):
    ir(at, "Pagos")
    at.selectbox(key="pg_f_colab").select("Luis Violante")
    at.selectbox(key="pg_f_concepto").select("Bono")
    at.number_input(key="pg_f_monto").set_value(15.0)
    at.text_input(key="pg_f_ref").input("REF-001")
    boton(at, "💾 Registrar pago").click()
    correr(at)
    assert any(p["Monto"] == 15.0 and p["Concepto"] == "Bono" for p in pendientes(at, "Pagos_Personal"))
    # mismo pago otra vez → la app avisa del posible duplicado y no lo guarda sin confirmación
    at.selectbox(key="pg_f_colab").select("Luis Violante")
    at.selectbox(key="pg_f_concepto").select("Bono")
    at.number_input(key="pg_f_monto").set_value(15.0)
    boton(at, "💾 Registrar pago").click()
    correr(at)
    assert len([p for p in pendientes(at, "Pagos_Personal") if p["Concepto"] == "Bono"]) == 1
    assert any("iguales" in w.value for w in at.warning)


def test_corregir_y_anular_pago(at):
    ir(at, "Pagos")
    at.radio(key="pg_c_accion").set_value("Corregir")
    correr(at)
    at.text_area(key="pg_c_motivo").input("Monto mal digitado")
    pid = at.selectbox(key="pg_c_id").value
    at.number_input(key=f"pg_c_monto_{pid}").set_value(12.0)
    boton(at, "Registrar corrección").click()
    correr(at)
    nuevos = [p for p in pendientes(at, "Pagos_Personal") if p.get("Corrige_ID") == pid]
    assert nuevos and nuevos[0]["Monto"] == 12.0 and nuevos[0]["Motivo"] == "Monto mal digitado"


def test_prestamo_y_abono(at):
    ir(at, "Anticipos")
    at.selectbox(key="pre_f_colab").select("Luis Violante")
    at.number_input(key="pre_f_cap").set_value(100.0)
    at.number_input(key="pre_f_cuotas").set_value(4)
    at.text_area(key="pre_f_cond").input("4 cuotas quincenales de $25")
    boton(at, "Registrar préstamo").click()
    correr(at)
    otorgado = [p for p in pendientes(at, "Prestamos") if p["Movimiento"] == "OTORGAMIENTO"]
    assert otorgado and otorgado[0]["Cuota_Monto"] == 25.0
    pid = otorgado[0]["ID"]
    at.number_input(key=f"pre_a_monto_{pid}").set_value(25.0)
    boton(at, "Registrar abono").click()
    correr(at)
    assert any(p["Movimiento"] == "ABONO" and p["Monto"] == 25.0 for p in pendientes(at, "Prestamos"))


def test_caja_y_cuentas_por_pagar(at):
    ir(at, "Finanzas")
    at.text_input(key="caja_f_concepto").input("Compra de toallas")
    at.number_input(key="caja_f_monto").set_value(45.5)
    boton(at, "Registrar movimiento").click()
    correr(at)
    assert any(m["Concepto"] == "Compra de toallas" for m in pendientes(at, "Caja"))
    at.text_input(key="cxp_f_otro").input("JG Suministros")
    at.text_input(key="cxp_f_doc").input("CCF-120")
    at.number_input(key="cxp_f_monto").set_value(300.0)
    at.text_input(key="cxp_f_concepto").input("Insumos de octubre")
    boton(at, "Registrar cuenta por pagar").click()
    correr(at)
    factura = next(f for f in pendientes(at, "Cuentas_por_Pagar") if f["Movimiento"] == "FACTURA")
    at.radio(key="cxp_a_accion").set_value("Registrar pago")
    correr(at)
    at.number_input(key=f"cxp_p_monto_{factura['ID']}").set_value(120.0)
    boton(at, "💵 Registrar pago").click()
    correr(at)
    assert any(p["Movimiento"] == "PAGO" and p["Monto"] == 120.0 for p in pendientes(at, "Cuentas_por_Pagar"))


def test_expediente_registro_y_estado(at):
    ir(at, "Expediente")
    at.selectbox(key="exp_colab").select("Maydely Hernández")
    correr(at)
    at.selectbox(key="exp_n_tipo").select("DOCUMENTO")
    correr(at)
    at.text_input(key="exp_n_titulo").input("Copia de DUI")
    boton(at, "Guardar en el expediente").click()
    correr(at)
    assert any(r["Titulo"] == "Copia de DUI" for r in pendientes(at, "Expediente"))


def test_horario_y_marcaciones(at):
    ir(at, "Asistencia")
    at.selectbox(key="hor_f_tipo").select("Colaborador")
    correr(at)
    boton(at, "Guardar horario").click()
    correr(at)
    assert pendientes(at, "Horarios")
    at.selectbox(key="asi_m_colab").select("Mario de Paz")
    correr(at)
    boton(at, "Marcar entrada").click()
    correr(at)
    assert any(m["Tipo"] == "ENTRADA" and m["Colaborador"] == "Mario de Paz" for m in pendientes(at, "Asistencia"))
    assert not any("Marcar entrada" in b.label and "Mario" in b.key for b in at.button if b.key)  # ya no se ofrece otra entrada


def test_importar_cuentas_y_generar_usuario(at):
    ir(at, "Configuración")
    at.text_area(key="imp_cuentas_texto").input("5540496530,185.49,Mario Antonio De Paz Velasquez\n5540496680,300,Marvin Giovanni Molina Flores")
    correr(at)
    boton(at, "Guardar 2 cuenta(s)").click()
    correr(at)
    empleados = at.session_state["empleados"]
    assert empleados["Mario de Paz"]["cuenta"] == "5540496530"
    assert empleados["Dr. Gio Molina"]["titular"] == "Marvin Giovanni Molina Flores"
    at.text_input(key="seg_u").input("gerencia")
    at.text_input(key="seg_p1").input("ClaveSegura123")
    at.text_input(key="seg_p2").input("ClaveSegura123")
    boton(at, "Generar bloque para Secrets").click()
    correr(at)
    bloque = " ".join(c.value for c in at.code)
    assert "[usuarios.gerencia]" in bloque and "pbkdf2_sha256$" in bloque and "ClaveSegura123" not in bloque


def test_todas_las_paginas_con_datos(at):
    for pagina in ["PanelAdmin", "Expediente", "Pagos", "Anticipos", "Asistencia", "Finanzas", "Planillas", "Auditoría", "Configuración", "Dashboard"]:
        ir(at, pagina)
    ir(at, "Finanzas")
    at.radio(key="rep_agrupar").set_value("Mes")
    correr(at)
