"""Pruebas de la app completa con streamlit.testing (sin navegador). Corren en «modo local» (sin Google Sheets).

La prueba con el PDF real usa la variable de entorno GIO_PDF_PRUEBA (reporte del 1 al 15 de septiembre de 2026).
Los PDF de ventas tienen datos de clientes: no se guardan en el repositorio.
"""
import os

import pytest
from streamlit.testing.v1 import AppTest

from nucleo import seguridad as seg

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app.py")
PDF_PRUEBA = os.environ.get("GIO_PDF_PRUEBA", "")
PAGINAS = ["Planillas", "Ecommerce", "Dashboard", "PanelAdmin", "Expediente", "Pagos", "Anticipos", "Asistencia", "Finanzas",
           "Proveedores", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("GIO_DIR_DATOS", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def correr(at):
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def ir(at, pagina):
    at.session_state["pagina"] = pagina
    correr(at)


def boton(at, texto):
    return next(b for b in at.button if texto in b.label)


def textos(at):
    return " ".join(str(m.value) for m in list(at.markdown) + list(at.warning) + list(at.error) + list(at.info) + list(at.success))


def cargar_pdf(at):
    with open(PDF_PRUEBA, "rb") as fh:
        at.session_state["pdf_bytes"] = fh.read()
    at.session_state["pdf_hash"] = "prueba"
    at.session_state["pdf_nombre"] = "reporte.pdf"
    ir(at, "Planillas")
    boton(at, "Recalcular").click()
    correr(at)
    assert at.session_state["pdf_ok"]


# 14 -------------------------------------------------------------------
def test_14_todas_las_paginas_abren_sin_errores(app):
    for pagina in PAGINAS:
        ir(app, pagina)


@pytest.mark.skipif(not os.path.exists(PDF_PRUEBA), reason="Define GIO_PDF_PRUEBA con el PDF del 1 al 15 de septiembre de 2026")
def test_14_planilla_desde_pdf_conserva_los_calculos(app):
    cargar_pdf(app)
    assert "1.ª quincena de septiembre 2026" in app.session_state["periodo_texto"]
    filas = next(iter(app.session_state["historial_local"].values()))  # se guardó sola (en modo local, en la sesión)
    totales = {f["Colaborador"]: f["Total"] for f in filas}
    assert totales["Maydely Hernández"] == 536.46
    assert totales["Luis Violante"] == 273.96
    assert totales["Jessica Lemus"] == 194.0
    assert totales["Dr. Gio Molina"] == 300.0
    assert totales["Mario de Paz"] == 183.96


def test_14_proveedor_nuevo_sigue_funcionando(app):
    ir(app, "Proveedores")
    boton(app, "Nuevo proveedor").click()
    correr(app)
    app.text_input(key="form_prov_nuevo_Nombre_Proveedor").input("Proveedor de prueba")
    boton(app, "Guardar proveedor").click()
    correr(app)
    assert any(p.get("Nombre_Proveedor") == "Proveedor de prueba" for p in app.session_state["proveedores"])


# 11 y 12 en la interfaz --------------------------------------------------
def test_12_sin_google_sheets_la_operacion_queda_pendiente_y_no_se_dice_guardada(app):
    ir(app, "Anticipos")
    app.selectbox(key="ant_f_colab").select("Mario de Paz")
    app.number_input(key="ant_f_monto").set_value(20.0)
    boton(app, "Registrar anticipo").click()
    correr(app)
    pendientes = app.session_state["_almacen"].pendientes("Anticipos")
    assert len(pendientes) == 1 and pendientes[0]["registro"]["Monto"] == 20.0
    avisos = " ".join(w.value for w in app.warning)
    assert "PENDIENTE" in avisos or "pendiente" in avisos
    assert "Guardado en Google Sheets" not in textos(app)


# 2, 5 e integración con la planilla y el archivo del banco -----------------
@pytest.mark.skipif(not os.path.exists(PDF_PRUEBA), reason="Define GIO_PDF_PRUEBA")
def test_anticipo_se_descuenta_en_la_planilla_y_en_el_archivo_del_banco(app):
    cargar_pdf(app)
    ir(app, "Anticipos")
    app.selectbox(key="ant_f_colab").select("Mario de Paz")
    app.number_input(key="ant_f_monto").set_value(20.0)
    boton(app, "Registrar anticipo").click()
    correr(app)
    ir(app, "Planillas")
    boton(app, "Descontar en esta planilla").click()
    correr(app)
    tabla = next(d.value for d in app.dataframe if "Neto a entregar" in getattr(d.value, "columns", []))
    mario = tabla[tabla["Colaborador"] == "Mario de Paz"].iloc[0]
    assert mario["Total planilla"] == 183.96 and mario["Anticipos aplicados"] == 20.0 and mario["Neto a entregar"] == 163.96
    # recalcular la planilla no vuelve a descontar
    boton(app, "Recalcular").click()
    correr(app)
    tabla = next(d.value for d in app.dataframe if "Neto a entregar" in getattr(d.value, "columns", []))
    assert tabla[tabla["Colaborador"] == "Mario de Paz"].iloc[0]["Anticipos aplicados"] == 20.0
    descuentos = [i for i in app.session_state["_almacen"].pendientes("Anticipos") if i["registro"].get("Movimiento") == "DESCUENTO"]
    assert len(descuentos) == 1


@pytest.mark.skipif(not os.path.exists(PDF_PRUEBA), reason="Define GIO_PDF_PRUEBA")
def test_06_planilla_pagada_no_cambia_en_silencio_se_registra_ajuste(app):
    empleados = app.session_state["empleados"]
    for i, nombre in enumerate(empleados):
        empleados[nombre]["cuenta"] = f"55400000{i:02d}"
    app.session_state["empleados"] = empleados
    cargar_pdf(app)
    # 1) El banco procesó el archivo → se registra como pagado (una sola vez)
    app.checkbox(key="conf_lote_banco").check()
    correr(app)
    boton(app, "Registrar como pagado").click()
    correr(app)
    pagos = [i["registro"] for i in app.session_state["_almacen"].pendientes("Pagos_Personal")]
    assert len(pagos) == len(empleados)  # en este PDF todos tienen monto por entregar
    assert {p["Clave_Unica"].split("|")[0] for p in pagos} == {"BANCO"}
    tabla = next(d.value for d in app.dataframe if "Neto a entregar" in getattr(d.value, "columns", []))
    assert all("Completado" in e for e in tabla["Estado"])
    assert not any("Registrar como pagado" in b.label for b in app.button)  # ya no queda nada pendiente: no se puede pagar dos veces
    # 2) Un bono después de pagar NO reemplaza la planilla guardada: aparece la diferencia para registrarla como ajuste
    app.number_input(key="ui_h_Mario de Paz").set_value(10.0)
    correr(app)
    assert app.session_state["autoguardado_estado"].get("bloqueado")
    assert any("ya se pagó" in w.value for w in app.warning)
    app.text_input(key="aj_pl_motivo").input("Bono aprobado después del pago")
    boton(app, "Registrar ajuste").click()
    correr(app)
    ajustes = [i["registro"] for i in app.session_state["_almacen"].pendientes("Ajustes_Planilla")]
    assert len(ajustes) == 1 and ajustes[0]["Colaborador"] == "Mario de Paz" and ajustes[0]["Diferencia"] == 10.0
    tabla = next(d.value for d in app.dataframe if "Neto a entregar" in getattr(d.value, "columns", []))
    mario = tabla[tabla["Colaborador"] == "Mario de Paz"].iloc[0]
    assert mario["Ajustes"] == 10.0 and mario["Pendiente"] == 10.0  # queda pendiente entregar solo la diferencia


def test_11_sheets_configurado_pero_caido_no_sobrescribe_la_hoja_real(tmp_path, monkeypatch):
    """Si al abrir la app no se pudo leer la hoja «Personal», guardar NO debe reemplazarla con los datos de arranque."""
    monkeypatch.setenv("GIO_DIR_DATOS", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["gsheets"] = {"url": "https://docs.google.com/spreadsheets/d/no-existe/edit"}
    at.secrets["gcp_service_account"] = {"type": "service_account", "project_id": "x", "private_key": "invalida", "client_email": "x@x.iam.gserviceaccount.com"}
    correr(at)
    assert at.session_state["carga_hojas"]["Personal"] == "error"
    assert "solo lectura" in at.session_state["fuente_personal"]
    ir(at, "Configuración")
    at.selectbox(key="fe_sel").select("Luis Violante")
    correr(at)
    boton(at, "Guardar colaborador").click()
    correr(at)
    assert any("No se guardó «Personal»" in e.value for e in at.error)
    # y una operación nueva queda pendiente, nunca «guardada»
    ir(at, "Anticipos")
    at.selectbox(key="ant_f_colab").select("Mario de Paz")
    at.number_input(key="ant_f_monto").set_value(5.0)
    boton(at, "Registrar anticipo").click()
    correr(at)
    assert at.session_state["_almacen"].pendientes("Anticipos")
    assert "Guardado en Google Sheets" not in textos(at)


# 15 en la interfaz ------------------------------------------------------
@pytest.fixture
def app_con_usuarios(tmp_path, monkeypatch):
    monkeypatch.setenv("GIO_DIR_DATOS", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["usuarios"] = {
        "gerencia": {"nombre": "Gerencia", "rol": "admin", "clave": seg.hash_clave("ClaveGerencia1", iteraciones=1000)},
        "luis": {"nombre": "Luis Violante", "rol": "operativo", "colaborador": "Luis Violante", "clave": seg.hash_clave("ClaveLuis123", iteraciones=1000)},
    }
    at.run()
    assert not at.exception
    return at


def entrar(at, usuario, clave):
    at.text_input(key="login_usuario").input(usuario)
    at.text_input(key="login_clave").input(clave)
    boton(at, "Entrar").click()
    correr(at)


def test_15_sin_sesion_no_se_ve_nada(app_con_usuarios):
    at = app_con_usuarios
    assert "Iniciar sesión" in textos(at)
    assert not any("Planillas" in b.label for b in at.button)
    entrar(at, "luis", "incorrecta")
    assert "incorrectos" in " ".join(e.value for e in at.error)
    assert not at.session_state["usuario_sesion"] if "usuario_sesion" in at.session_state else True


def test_15_operativo_solo_ve_su_asistencia(app_con_usuarios):
    at = app_con_usuarios
    entrar(at, "luis", "ClaveLuis123")
    assert at.session_state["pagina"] == "MiAsistencia"
    for restringida in ("Planillas", "Pagos", "Anticipos", "Configuración", "PanelAdmin"):
        ir(at, restringida)
        assert at.session_state["pagina"] == "MiAsistencia"  # redirigido: no puede ver salarios, bancos ni préstamos
    contenido = textos(at)
    assert "Planilla consolidada" not in contenido and "Cuenta" not in " ".join(b.label for b in at.button)
    boton(at, "Marcar entrada").click()
    correr(at)
    marcas = at.session_state["_almacen"].pendientes("Asistencia")
    assert len(marcas) == 1 and marcas[0]["registro"]["Colaborador"] == "Luis Violante" and marcas[0]["registro"]["Usuario"] == "Luis Violante"


def test_15_administracion_ve_todo(app_con_usuarios):
    at = app_con_usuarios
    entrar(at, "gerencia", "ClaveGerencia1")
    assert at.session_state["pagina"] == "Planillas"
    for pagina in ("Pagos", "Anticipos", "Configuración"):
        ir(at, pagina)
        assert at.session_state["pagina"] == pagina
