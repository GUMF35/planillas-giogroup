"""Visitas, encuestas por QR y cupones."""
import os
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from nucleo import seguridad as seg
from nucleo import visitas as vis
from nucleo.almacen import Almacen, BackendMemoria, ColaPendientes
from nucleo.finanzas import ErrorNegocio

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(RAIZ, "app.py")


@pytest.fixture
def alm(tmp_path):
    return Almacen(BackendMemoria(), ColaPendientes(str(tmp_path / "p.jsonl")), usuario="Recepción")


def test_ciclo_completo_visita_encuesta_cupon_canje(alm):
    visita = alm.registrar("Visitas", vis.nueva_visita("Luis Violante", "Relájate Man", "Masaje", 40)).registro
    codigo = visita["Codigo"]
    assert vis.codigo_valido(codigo) and len(codigo) == 8
    assert vis.buscar_visita(alm.leer("Visitas"), codigo)["Colaborador"] == "Luis Violante"
    assert vis.buscar_visita(alm.leer("Visitas"), "NOEXISTE1") is None
    enc = vis.nueva_encuesta(codigo, vis.RESPUESTAS_SATISFACCION[0], vis.RESPUESTAS_ATENCION[0], vis.RESPUESTAS_PAGOS[0])
    assert alm.registrar("Encuestas", enc).estado == "guardado"
    assert alm.registrar("Encuestas", vis.nueva_encuesta(codigo, vis.RESPUESTAS_SATISFACCION[4], vis.RESPUESTAS_ATENCION[3], vis.RESPUESTAS_PAGOS[1])).estado == "ya_existia"
    assert alm.registrar("Cupones", vis.nuevo_cupon(codigo, 5, 60)).estado == "guardado"
    assert alm.registrar("Cupones", vis.nuevo_cupon(codigo, 5, 60)).estado == "ya_existia"  # un solo cupón por visita
    assert len([c for c in alm.leer("Cupones", forzar=True)]) == 1
    cupon = vis.cupon_de_visita(alm.leer("Cupones"), codigo)
    assert cupon["Descuento"] == "5% OFF" and cupon["Codigo_Cupon"].startswith("GIO-")
    assert vis.estado_cupon(alm.leer("Cupones"), cupon["Codigo_Cupon"])[1] == "Disponible"
    assert alm.registrar("Cupones", vis.preparar_canje(alm.leer("Cupones"), cupon["Codigo_Cupon"])).estado == "guardado"
    with pytest.raises(ErrorNegocio, match="YA FUE UTILIZADO"):
        vis.preparar_canje(alm.leer("Cupones", forzar=True), cupon["Codigo_Cupon"].lower())


def test_cupon_vencido_y_inexistente(alm):
    c = alm.registrar("Cupones", dict(vis.nuevo_cupon("ABCD2345", 5, 60), Vencimiento="2026-01-01")).registro
    assert vis.estado_cupon(alm.leer("Cupones"), c["Codigo_Cupon"], date(2026, 10, 24))[1] == "Vencido"
    with pytest.raises(ErrorNegocio, match="venció"):
        vis.preparar_canje(alm.leer("Cupones"), c["Codigo_Cupon"], date(2026, 10, 24))
    with pytest.raises(ErrorNegocio, match="no existe"):
        vis.preparar_canje(alm.leer("Cupones"), "GIO-XXXXXX")


def test_validaciones_y_visita_cancelada(alm):
    for args in (("", "M", "x", 10), ("A", "M", "", 10), ("A", "M", "x", 0)):
        with pytest.raises(ErrorNegocio):
            vis.nueva_visita(*args)
    with pytest.raises(ErrorNegocio):
        vis.nueva_encuesta("ABCD2345", None, vis.RESPUESTAS_ATENCION[0], vis.RESPUESTAS_PAGOS[0])
    v = alm.registrar("Visitas", vis.nueva_visita("Luis", "M", "Masaje", 40)).registro
    from nucleo.finanzas import anulacion
    alm.registrar("Visitas", anulacion(v["ID"], "Registrada por error"))
    assert vis.buscar_visita(alm.leer("Visitas", forzar=True), v["Codigo"]) is None


def test_resultados_marcan_alertas(alm):
    v = alm.registrar("Visitas", vis.nueva_visita("Luis Violante", "M", "Masaje", 40)).registro
    alm.registrar("Encuestas", vis.nueva_encuesta(v["Codigo"], vis.RESPUESTAS_SATISFACCION[4], vis.RESPUESTAS_ATENCION[0], vis.RESPUESTAS_PAGOS[1], "Me pidieron $5"))
    resumen, revisar = vis.resultados(alm.leer("Visitas"), alm.leer("Encuestas"))
    assert resumen[0]["Satisfacción promedio"] == 1.0 and resumen[0]["Con alerta"] == 1
    assert "Posible cobro fuera de precio" in revisar[0]["Motivo"] and revisar[0]["Comentario"] == "Me pidieron $5"




# --- Interfaz: el cliente entra por el enlace público, aunque la app tenga inicio de sesión ---
@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("GIO_DIR_DATOS", str(tmp_path))
    cola = ColaPendientes.compartida(os.path.join(str(tmp_path), "pendientes.jsonl"))  # la misma cola que usa la app en modo local
    return Almacen(None, cola, usuario="Recepción")


def app_cliente(codigo):
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["usuarios"] = {"gerencia": {"nombre": "Gerencia", "rol": "admin", "clave": seg.hash_clave("ClaveGerencia1", iteraciones=1000)}}
    at.query_params["encuesta"] = codigo
    at.run()
    return at


def todo_el_texto(at):
    return " ".join(str(m.value) for m in list(at.markdown) + list(at.error) + list(at.warning) + list(at.info))


def test_cliente_ve_encuesta_sin_login_ni_panel_y_recibe_un_solo_cupon(entorno):
    codigo = entorno.registrar("Visitas", vis.nueva_visita("Luis Violante", "Relájate Man", "Masaje", 40)).registro["Codigo"]
    at = app_cliente(codigo)
    assert not at.exception
    texto = todo_el_texto(at)
    assert "Tu opinión nos ayuda a mejorar" in texto and "Luis Violante" in texto
    assert "Iniciar sesión" not in texto and "Planillas" not in texto and "$40" not in texto  # sin login, sin panel, sin precio
    assert not any("Planillas" in b.label for b in at.button)
    at.radio[0].set_value(vis.RESPUESTAS_SATISFACCION[0])
    at.radio[1].set_value(vis.RESPUESTAS_ATENCION[0])
    at.radio[2].set_value(vis.RESPUESTAS_PAGOS[0])
    at.button[0].click()
    at.run()
    assert not at.exception and "TU CUPÓN: 5% OFF" in todo_el_texto(at)
    assert len(entorno.leer("Encuestas")) == 1 and len(entorno.leer("Cupones")) == 1
    otra = app_cliente(codigo)  # volver a abrir el enlace: mismo cupón, no se emite otro ni se repite la encuesta
    assert "¡Gracias por tu visita!" in todo_el_texto(otra) and len(entorno.leer("Cupones", forzar=True)) == 1


def test_codigo_falso_o_cancelado_no_muestra_nada(entorno):
    assert "Código no válido" in todo_el_texto(app_cliente("ZZZZZZZZ"))
    assert "Código no válido" in todo_el_texto(app_cliente("../../etc"))
    v = entorno.registrar("Visitas", vis.nueva_visita("Luis", "M", "Masaje", 40)).registro
    from nucleo.finanzas import anulacion
    entorno.registrar("Visitas", anulacion(v["ID"], "Registrada por error"))
    assert "Código no válido" in todo_el_texto(app_cliente(v["Codigo"]))


def test_recepcion_registra_visita_y_muestra_qr(tmp_path, monkeypatch):
    monkeypatch.setenv("GIO_DIR_DATOS", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["app_url"] = "https://mi-app.streamlit.app"
    at.run()
    at.session_state["pagina"] = "Visitas"
    at.run()
    assert not at.exception
    at.text_input(key="vis_servicio").input("Masaje relajante")
    at.number_input(key="vis_precio").set_value(40.0)
    next(b for b in at.button if "Registrar visita" in b.label).click()
    at.run()
    assert not at.exception
    codigo = at.session_state["ultimo_codigo"]
    assert vis.buscar_visita(at.session_state["_almacen"].leer("Visitas"), codigo)
    assert any(f"https://mi-app.streamlit.app/?encuesta={codigo}" in c.value for c in at.code)
    assert len(at.session_state["_almacen"].pendientes("Visitas")) == 1  # modo local: pendiente, no «guardado en la nube»
