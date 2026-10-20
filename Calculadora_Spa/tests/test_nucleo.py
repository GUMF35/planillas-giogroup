"""Pruebas obligatorias de la lógica (sin Streamlit). Numeración según el plan: 1–13 y 15."""
from datetime import date, datetime

import pytest

from nucleo import asistencia as asi
from nucleo import finanzas as fin
from nucleo import personal as per
from nucleo import seguridad as seg
from nucleo.almacen import GUARDADO, PENDIENTE, YA_EXISTIA, Almacen, BackendMemoria, ColaPendientes
from nucleo.util import clave_periodo, dinero, quincenas_cercanas

PERIODO = clave_periodo("2026-10-01", "2026-10-15")


@pytest.fixture
def almacen(tmp_path):
    return Almacen(BackendMemoria(), ColaPendientes(str(tmp_path / "pendientes.jsonl")), usuario="prueba")


def registrar_ok(alm, tabla, registro):
    r = alm.registrar(tabla, registro)
    assert r.ok, r.mensaje
    return r.registro


# 1 -------------------------------------------------------------------
def test_01_registrar_y_consultar_pago(almacen):
    reg = fin.nuevo_pago("Luis Violante", "2026-10-15", "Sueldo / planilla", 273.96, "Transferencia bancaria", periodo=PERIODO, referencia="DAV-001")
    guardado = registrar_ok(almacen, "Pagos_Personal", reg)
    pagos = fin.estado_pagos(almacen.leer("Pagos_Personal", forzar=True))
    assert len(pagos) == 1
    p = pagos[0]
    assert p["ID"] == guardado["ID"] and p["Estado"] == "Completado"
    assert p["Monto"] == 273.96 and p["Usuario"] == "prueba" and p["Registrado"]
    assert fin.entregado_periodo(almacen.leer("Pagos_Personal"), PERIODO) == {"Luis Violante": 273.96}


def test_01b_pago_invalido_se_rechaza():
    with pytest.raises(fin.ErrorNegocio):
        fin.nuevo_pago("Luis Violante", "2026-10-15", "Sueldo / planilla", 0, "Efectivo")
    with pytest.raises(fin.ErrorNegocio):
        fin.nuevo_pago("", "2026-10-15", "Bono", 10, "Efectivo")


# 2 -------------------------------------------------------------------
def test_02_anticipo_20_se_descuenta_una_sola_vez(almacen):
    entrega = registrar_ok(almacen, "Anticipos", fin.nuevo_anticipo("Mario de Paz", 20, "2026-10-08 10:30", "Efectivo", "Gerencia", periodo=PERIODO))
    movs = almacen.leer("Anticipos")
    assert fin.estado_anticipos(movs)[0]["Saldo"] == 20.0
    registrar_ok(almacen, "Anticipos", fin.preparar_descuento_anticipo(movs, entrega["ID"], PERIODO))
    movs = almacen.leer("Anticipos", forzar=True)
    a = fin.estado_anticipos(movs)[0]
    assert a["Saldo"] == 0.0 and a["Estado"] == "Liquidado" and a["Descontado"] == 20.0
    resumen = fin.resumen_pagos_periodo(PERIODO, {"Mario de Paz": 183.96}, anticipos_movs=movs)
    assert resumen[0]["Anticipos"] == 20.0 and resumen[0]["Neto"] == 163.96
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_descuento_anticipo(movs, entrega["ID"], PERIODO)


def test_02b_devolucion_baja_saldo_sin_descuento_salarial(almacen):
    entrega = registrar_ok(almacen, "Anticipos", fin.nuevo_anticipo("Mario de Paz", 20, "2026-10-08 10:30", "Efectivo", "Gerencia"))
    registrar_ok(almacen, "Anticipos", fin.preparar_devolucion_anticipo(almacen.leer("Anticipos"), entrega["ID"], 20, "Efectivo"))
    movs = almacen.leer("Anticipos", forzar=True)
    assert fin.estado_anticipos(movs)[0]["Saldo"] == 0.0
    assert fin.anticipos_aplicados(movs, PERIODO) == {}  # la devolución no es un descuento en planilla
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_devolucion_anticipo(movs, entrega["ID"], 1, "Efectivo")


# 3 -------------------------------------------------------------------
def test_03_prestamo_100_abono_25_saldo_75(almacen):
    pre = registrar_ok(almacen, "Prestamos", fin.nuevo_prestamo("Luis Violante", 100, "2026-10-01", 4, 25, "Quincenal", "2026-10-15",
                                                                 "4 cuotas quincenales de $25", "Gerencia", "Efectivo"))
    registrar_ok(almacen, "Prestamos", fin.preparar_abono(almacen.leer("Prestamos"), pre["ID"], 25, "Efectivo", "2026-10-15", hoy="2026-10-15"))
    p = fin.estado_prestamos(almacen.leer("Prestamos", forzar=True), hoy="2026-10-15")[0]
    assert p["Saldo"] == 75.0 and p["Pagado"] == 25.0 and p["Estado"] == "Vigente"
    with pytest.raises(fin.ErrorNegocio):  # no se permiten saldos negativos
        fin.preparar_abono(almacen.leer("Prestamos"), pre["ID"], 80, "Efectivo", "2026-10-16", hoy="2026-10-16")


def test_03b_cuota_en_planilla_requiere_autorizacion_y_no_se_duplica(almacen):
    pre = registrar_ok(almacen, "Prestamos", fin.nuevo_prestamo("Luis Violante", 100, "2026-10-01", 4, 25, "Quincenal", "2026-10-15",
                                                                 "Cuotas en planilla", "Gerencia", "Efectivo"))
    movs = almacen.leer("Prestamos")
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_cuota_planilla(movs, pre["ID"], PERIODO, 25, autorizado_por="")
    registrar_ok(almacen, "Prestamos", fin.preparar_cuota_planilla(movs, pre["ID"], PERIODO, 25, "Gerencia"))
    movs = almacen.leer("Prestamos", forzar=True)
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_cuota_planilla(movs, pre["ID"], PERIODO, 25, "Gerencia")
    assert fin.cuotas_aplicadas(movs, PERIODO) == {"Luis Violante": 25.0}
    assert fin.estado_prestamos(movs, hoy="2026-10-15")[0]["Saldo"] == 75.0


def test_03c_prestamo_atrasado_y_cancelacion_justificada(almacen):
    pre = registrar_ok(almacen, "Prestamos", fin.nuevo_prestamo("Luis Violante", 100, "2026-09-01", 2, 50, "Mensual", "2026-09-30",
                                                                 "2 cuotas mensuales", "Gerencia", "Efectivo"))
    p = fin.estado_prestamos(almacen.leer("Prestamos"), hoy="2026-10-20")[0]
    assert p["Estado"] == "Atrasado" and p["Atraso"] == 50.0
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_cancelacion(almacen.leer("Prestamos"), pre["ID"], "", "Gerencia", hoy="2026-10-20")
    registrar_ok(almacen, "Prestamos", fin.preparar_cancelacion(almacen.leer("Prestamos"), pre["ID"], "Condonado por gerencia", "Gerencia", hoy="2026-10-20"))
    p = fin.estado_prestamos(almacen.leer("Prestamos", forzar=True), hoy="2026-10-20")[0]
    assert p["Estado"] == "Cancelado" and p["Saldo"] == 0.0 and p["Condonado"] == 100.0


# 4 -------------------------------------------------------------------
def test_04_repetir_la_operacion_no_duplica_el_pago(almacen):
    reg = fin.nuevo_pago("Jessica Lemus", "2026-10-15", "Comisión", 194, "Efectivo", periodo=PERIODO, id_operacion="PAG-OP-1")
    assert almacen.registrar("Pagos_Personal", reg).estado == GUARDADO
    assert almacen.registrar("Pagos_Personal", dict(reg)).estado == YA_EXISTIA
    assert len(almacen.leer("Pagos_Personal", forzar=True)) == 1
    similar = fin.nuevo_pago("Jessica Lemus", "2026-10-15", "Comisión", 194, "Efectivo", periodo=PERIODO)
    assert fin.posibles_duplicados(almacen.leer("Pagos_Personal"), similar)


# 5 -------------------------------------------------------------------
def test_05_recalcular_planilla_no_descuenta_dos_veces_el_anticipo(almacen):
    entrega = registrar_ok(almacen, "Anticipos", fin.nuevo_anticipo("Mario de Paz", 20, "2026-10-08 10:30", "Efectivo", "Gerencia"))
    desc = fin.preparar_descuento_anticipo(almacen.leer("Anticipos"), entrega["ID"], PERIODO)
    assert almacen.registrar("Anticipos", desc).estado == GUARDADO
    otro_intento = dict(desc, ID="")  # mismo descuento con otro ID (p. ej. doble clic)
    assert almacen.registrar("Anticipos", otro_intento).estado == YA_EXISTIA
    movs = almacen.leer("Anticipos", forzar=True)
    calculado = {"Mario de Paz": 183.96}
    r1 = fin.resumen_pagos_periodo(PERIODO, calculado, anticipos_movs=movs)
    r2 = fin.resumen_pagos_periodo(PERIODO, calculado, anticipos_movs=movs)
    assert r1 == r2 and r1[0]["Anticipos"] == 20.0 and r1[0]["Neto"] == 163.96


# 6 -------------------------------------------------------------------
def test_06_pago_completado_no_se_modifica_sin_ajuste(almacen):
    original = registrar_ok(almacen, "Pagos_Personal", fin.nuevo_pago("Luis Violante", "2026-10-15", "Sueldo / planilla", 273.96, "Efectivo", periodo=PERIODO))
    movs = almacen.leer("Pagos_Personal")
    with pytest.raises(fin.ErrorNegocio):  # sin motivo no hay corrección
        fin.preparar_correccion_pago(movs, original["ID"], motivo="", monto=270.0)
    registrar_ok(almacen, "Pagos_Personal", fin.preparar_correccion_pago(movs, original["ID"], "Se digitó mal el monto", monto=270.0))
    filas = almacen.backend.tablas["Pagos_Personal"]
    assert filas[0]["Monto"] == 273.96 and len(filas) == 2  # la fila original sigue intacta
    estados = {p["ID"]: p for p in fin.estado_pagos(almacen.leer("Pagos_Personal", forzar=True))}
    assert estados[original["ID"]]["Estado"] == "Corregido"
    assert sum(p["Monto"] for p in estados.values() if p["Estado"] == "Completado") == 270.0
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_correccion_pago(almacen.leer("Pagos_Personal"), original["ID"], "Otra vez", monto=1)
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_ajuste_planilla(PERIODO, "Luis Violante", 273.96, 280.0, motivo="")
    ajuste = fin.preparar_ajuste_planilla(PERIODO, "Luis Violante", 273.96, 280.0, "Bono aprobado después del pago")
    assert ajuste["Diferencia"] == 6.04


# 7 -------------------------------------------------------------------
def test_07_entrada_y_salida(almacen):
    asi.validar_marca(almacen.leer("Asistencia"), "Luis Violante", "ENTRADA", "2026-10-19 08:02:00")
    registrar_ok(almacen, "Asistencia", asi.nueva_marca("Luis Violante", "ENTRADA", "2026-10-19 08:02:00"))
    asi.validar_marca(almacen.leer("Asistencia", forzar=True), "Luis Violante", "SALIDA", "2026-10-19 17:05:00")
    registrar_ok(almacen, "Asistencia", asi.nueva_marca("Luis Violante", "SALIDA", "2026-10-19 17:05:00"))
    marcas = asi.marcas_efectivas(almacen.leer("Asistencia", forzar=True))
    j = asi.jornadas(marcas)
    assert len(j) == 1 and j[0]["Completa"] and j[0]["Trabajado_Min"] == 543.0
    with pytest.raises(fin.ErrorNegocio):  # salida sin entrada abierta
        asi.validar_marca(almacen.leer("Asistencia"), "Luis Violante", "SALIDA", "2026-10-19 18:00:00")


# 8 -------------------------------------------------------------------
def test_08_marcacion_incompleta(almacen):
    registrar_ok(almacen, "Asistencia", asi.nueva_marca("Maydely Hernández", "ENTRADA", "2026-10-19 08:00:00"))
    movs = almacen.leer("Asistencia", forzar=True)
    with pytest.raises(fin.ErrorNegocio):  # no puede tener dos entradas abiertas
        asi.validar_marca(movs, "Maydely Hernández", "ENTRADA", "2026-10-20 08:00:00")
    marcas = asi.marcas_efectivas(movs)
    incs = asi.incidencias(asi.jornadas(marcas), [], {"Maydely Hernández": {}}, "2026-10-19", "2026-10-20", datetime(2026, 10, 20, 9, 0))
    assert any(i["Tipo"] == "MARCACION_INCOMPLETA" and i["Fecha"] == date(2026, 10, 19) for i in incs)
    # corrección con justificación (la hora original se conserva)
    correccion = asi.preparar_correccion_marca(movs, marcas[0]["ID"], "2026-10-19 08:10:00", "Marcó tarde por falla de internet")
    registrar_ok(almacen, "Asistencia", correccion)
    m = asi.marcas_efectivas(almacen.leer("Asistencia", forzar=True))[0]
    assert m["Corregida"] and m["Fecha_Hora"] == datetime(2026, 10, 19, 8, 10) and m["Hora_Original"] == datetime(2026, 10, 19, 8, 0)


# 9 -------------------------------------------------------------------
def test_09_tardanza_sin_descuento_automatico(almacen):
    horario = asi.nueva_version_horario("Colaborador", "Luis Violante", "Turno día", "2026-10-01", "",
                                        {d: "08:00-17:00" for d in ("Lun", "Mar", "Mie", "Jue", "Vie")}, 60, 10)
    registrar_ok(almacen, "Horarios", horario)
    registrar_ok(almacen, "Asistencia", asi.nueva_marca("Luis Violante", "ENTRADA", "2026-10-19 08:25:00"))
    registrar_ok(almacen, "Asistencia", asi.nueva_marca("Luis Violante", "SALIDA", "2026-10-19 17:00:00"))
    marcas = asi.marcas_efectivas(almacen.leer("Asistencia", forzar=True))
    incs = asi.incidencias(asi.jornadas(marcas), almacen.leer("Horarios", forzar=True), {"Luis Violante": {}},
                           "2026-10-19", "2026-10-19", datetime(2026, 10, 19, 20, 0))
    tardanzas = [i for i in incs if i["Tipo"] == "TARDANZA"]
    assert len(tardanzas) == 1 and tardanzas[0]["Minutos"] == 25
    # la planilla no cambia: ninguna incidencia genera movimientos de dinero
    for tabla in ("Pagos_Personal", "Anticipos", "Prestamos", "Ajustes_Planilla"):
        assert almacen.leer(tabla, forzar=True) == []
    resumen = fin.resumen_pagos_periodo(PERIODO, {"Luis Violante": 273.96})
    assert resumen[0]["Neto"] == 273.96


def test_09b_horario_versionado_no_altera_el_pasado(almacen):
    dias = {d: "08:00-17:00" for d in ("Lun", "Mar", "Mie", "Jue", "Vie")}
    registrar_ok(almacen, "Horarios", asi.nueva_version_horario("Colaborador", "Luis Violante", "Antes", "2026-09-01", "", dias, 60, 10))
    nuevos = {d: "09:00-18:00" for d in ("Lun", "Mar", "Mie", "Jue", "Vie")}
    registrar_ok(almacen, "Horarios", asi.nueva_version_horario("Colaborador", "Luis Violante", "Después", "2026-10-15", "", nuevos, 60, 10))
    movs = almacen.leer("Horarios", forzar=True)
    assert asi.resolver_horario(movs, "Luis Violante", "", "", "2026-10-13")["Tramo"] == "08:00-17:00"
    assert asi.resolver_horario(movs, "Luis Violante", "", "", "2026-10-19")["Tramo"] == "09:00-18:00"


# 10 ------------------------------------------------------------------
def test_10_gasto_se_refleja_en_reportes(almacen):
    gasto = fin.nuevo_movimiento_caja("2026-10-10", "SALIDA", "Insumos y materiales", "Aceites para masaje", 45.5, "Efectivo", negocio="Papi Spa")
    registrar_ok(almacen, "Caja", gasto)
    caja = almacen.leer("Caja", forzar=True)
    flujo = fin.movimientos_caja_unificados(caja=caja)
    gastos = fin.filtrar_fechas(fin.gastos_devengados(caja=caja), "2026-10-01", "2026-10-15")
    assert flujo[0]["Monto"] == 45.5 and flujo[0]["Tipo"] == "SALIDA"
    assert gastos[0]["Categoria"] == "Insumos y materiales" and gastos[0]["Negocio"] == "Papi Spa"
    with pytest.raises(fin.ErrorNegocio):  # categorías de otros módulos no se registran a mano (evita contar dos veces)
        fin.nuevo_movimiento_caja("2026-10-10", "SALIDA", fin.CAT_PLANILLA, "Sueldo", 100, "Efectivo")


def test_10b_prestamo_es_cuenta_por_cobrar_no_gasto(almacen):
    registrar_ok(almacen, "Prestamos", fin.nuevo_prestamo("Luis Violante", 100, "2026-10-01", 4, 25, "Quincenal", "2026-10-15", "Cuotas", "Gerencia", "Efectivo"))
    prestamos = almacen.leer("Prestamos", forzar=True)
    flujo = fin.movimientos_caja_unificados(prestamos=prestamos)
    assert flujo[0]["Categoria"] == fin.CAT_PRESTAMO  # sale dinero de caja...
    assert fin.gastos_devengados() == []  # ...pero no es un gasto


# 11 y 12 -------------------------------------------------------------
def test_11_y_12_caida_de_google_sheets(almacen):
    almacen.backend.fallar = True
    reg = fin.nuevo_pago("Luis Violante", "2026-10-15", "Bono", 15, "Efectivo", periodo=PERIODO)
    r = almacen.registrar("Pagos_Personal", reg)
    assert r.estado == PENDIENTE and not r.ok  # 12: un guardado fallido NUNCA se informa como exitoso
    assert "PENDIENTE" in r.mensaje and "Guardado en Google Sheets" not in r.mensaje
    assert len(almacen.pendientes()) == 1
    assert almacen.leer("Pagos_Personal")[0]["_pendiente"] is True  # se ve como pendiente
    almacen.backend.fallar = False
    resumen = almacen.sincronizar()
    assert resumen["enviados"] == 1 and not almacen.pendientes()
    assert almacen.sincronizar()["enviados"] == 0
    assert len(almacen.backend.tablas["Pagos_Personal"]) == 1


def test_11b_sincronizar_no_duplica_si_la_escritura_si_habia_llegado(almacen):
    reg = almacen._completar("Pagos_Personal", fin.nuevo_pago("Luis Violante", "2026-10-15", "Bono", 15, "Efectivo"))
    almacen.backend.agregar("Pagos_Personal", ["ID"], [reg])  # llegó a la nube...
    almacen.cola.agregar("Pagos_Personal", reg, "timeout")      # ...pero la app no recibió la confirmación
    resumen = almacen.sincronizar()
    assert resumen["descartados"] == 1 and resumen["enviados"] == 0


def test_12b_saldos_exigen_lectura_fresca(almacen):
    almacen.backend.fallar = True
    with pytest.raises(Exception):
        almacen.leer_para_validar("Anticipos")


# 13 ------------------------------------------------------------------
def test_13_datos_disponibles_tras_reiniciar(tmp_path):
    backend = BackendMemoria()
    ruta = str(tmp_path / "pendientes.jsonl")
    primera = Almacen(backend, ColaPendientes(ruta), usuario="admin")
    registrar_ok(primera, "Anticipos", fin.nuevo_anticipo("Mario de Paz", 20, "2026-10-08 10:30", "Efectivo", "Gerencia"))
    backend.fallar = True
    assert primera.registrar("Caja", fin.nuevo_movimiento_caja("2026-10-10", "SALIDA", "Transporte", "Taxi", 5, "Efectivo")).pendiente
    # «reinicio»: objetos nuevos, mismo almacenamiento y mismo archivo de pendientes
    backend.fallar = False
    segunda = Almacen(backend, ColaPendientes(ruta), usuario="admin")
    assert len(segunda.leer("Anticipos")) == 1
    assert len(segunda.pendientes("Caja")) == 1
    assert segunda.sincronizar()["enviados"] == 1
    assert len(Almacen(backend, ColaPendientes(ruta)).leer("Caja")) == 1


# 15 ------------------------------------------------------------------
def test_15_permisos_y_contrasenas():
    assert seg.puede("admin", "ver_salarios")
    assert not seg.puede("operativo", "ver_salarios")
    assert not seg.puede("operativo", "gestionar_pagos")
    assert seg.puede("operativo", "marcar_propia")
    assert not seg.puede("desconocido", "marcar_propia")
    h = seg.hash_clave("Secreta123", iteraciones=1000)
    assert "Secreta123" not in h and seg.verificar_clave("Secreta123", h) and not seg.verificar_clave("otra", h)
    usuarios = seg.cargar_usuarios({"gerencia": {"rol": "admin", "clave": h, "nombre": "Gerencia"},
                                    "luis": {"rol": "operativo", "clave": h, "colaborador": "Luis Violante"},
                                    "malo": {"rol": "admin", "clave": "texto-plano"}})
    assert set(usuarios) == {"gerencia", "luis"}
    assert seg.autenticar(usuarios, "luis", "Secreta123")["rol"] == "operativo"
    assert seg.autenticar(usuarios, "luis", "mala") is None
    assert "clave" not in seg.autenticar(usuarios, "gerencia", "Secreta123")
    lim = seg.Limitador(maximo=2, bloqueo=60, reloj=lambda: 100.0)
    lim.fallo()
    lim.fallo()
    assert lim.bloqueado()


# Extras ----------------------------------------------------------------
def test_estado_por_periodo_parcial_completado_y_exceso(almacen):
    registrar_ok(almacen, "Pagos_Personal", fin.nuevo_pago("Luis Violante", "2026-10-15", "Sueldo / planilla", 100, "Efectivo", periodo=PERIODO))
    registrar_ok(almacen, "Pagos_Personal", fin.nuevo_pago("Jessica Lemus", "2026-10-15", "Comisión", 194, "Efectivo", periodo=PERIODO))
    registrar_ok(almacen, "Pagos_Personal", fin.nuevo_pago("Mario de Paz", "2026-10-15", "Sueldo / planilla", 200, "Efectivo", periodo=PERIODO))
    registrar_ok(almacen, "Pagos_Personal", fin.nuevo_pago("Mario de Paz", "2026-10-15", "Reembolso", 50, "Efectivo", periodo=PERIODO))
    filas = {f["Colaborador"]: f for f in fin.resumen_pagos_periodo(PERIODO, {"Luis Violante": 273.96, "Jessica Lemus": 194.0, "Mario de Paz": 183.96,
                                                                               "Gerson Ulises Molina Flores": 300.0},
                                                                     pagos_movs=almacen.leer("Pagos_Personal"))}
    assert filas["Luis Violante"]["Estado"] == "Parcial" and filas["Luis Violante"]["Pendiente"] == 173.96
    assert filas["Jessica Lemus"]["Estado"] == "Completado"
    assert filas["Mario de Paz"]["Estado"] == "Revisar: entregado de más"  # el reembolso no cuenta contra la planilla
    assert filas["Gerson Ulises Molina Flores"]["Estado"] == "Pendiente"


def test_cuentas_por_pagar_pago_parcial_y_saldo(almacen):
    fac = registrar_ok(almacen, "Cuentas_por_Pagar", fin.nueva_factura([], "JG Suministros", "CCF-120", "2026-10-01", "2026-10-31", 300, "Insumos"))
    movs = almacen.leer("Cuentas_por_Pagar")
    with pytest.raises(fin.ErrorNegocio):
        fin.nueva_factura(movs, "JG Suministros", "CCF-120", "2026-10-01", "2026-10-31", 300, "Insumos")
    registrar_ok(almacen, "Cuentas_por_Pagar", fin.preparar_pago_cxp(movs, fac["ID"], 120, "2026-10-10", "Transferencia bancaria", hoy="2026-10-10"))
    estado = fin.estado_cxp(almacen.leer("Cuentas_por_Pagar", forzar=True), hoy="2026-10-10")[0]
    assert estado["Saldo"] == 180.0 and estado["Estado"] == "Parcial"
    with pytest.raises(fin.ErrorNegocio):
        fin.preparar_pago_cxp(almacen.leer("Cuentas_por_Pagar"), fac["ID"], 200, "2026-10-11", "Efectivo", hoy="2026-10-11")
    assert fin.estado_cxp(almacen.leer("Cuentas_por_Pagar"), hoy="2026-11-05")[0]["Estado"] == "Vencida"


def test_expediente_estados_y_alertas(almacen):
    reg = registrar_ok(almacen, "Expediente", per.nuevo_registro("Luis Violante", "PERMISO", "Cita médica", "2026-10-22", "2026-10-22", "Solicitado"))
    alertas = per.alertas("2026-10-20", per.estado_expediente(almacen.leer("Expediente", forzar=True)))
    assert alertas and alertas[0]["Tipo"] == "Solicitud por aprobar"
    registrar_ok(almacen, "Expediente", per.preparar_cambio_estado(almacen.leer("Expediente"), reg["ID"], "Aprobado", "Presentó constancia"))
    estado = per.estado_expediente(almacen.leer("Expediente", forzar=True))[0]
    assert estado["Estado_Actual"] == "Aprobado" and len(estado["Historial_Estados"]) == 1
    cambios = per.cambios_personal({"Luis Violante": {"cargo": "Barbero", "sueldo_base_neto": 183.96, "mod": "Fijo", "porc": 0}},
                                   {"Luis Violante": {"cargo": "Barbero senior", "sueldo_base_neto": 200.0, "mod": "Fijo", "porc": 0}},
                                   lambda i: i["sueldo_base_neto"])
    assert {c["Tipo"] for c in cambios} == {"CAMBIO_CARGO", "CAMBIO_SALARIO"}


def test_utilidades():
    assert dinero(0.125) == 0.13 and dinero(2.675) == 2.68
    assert len(quincenas_cercanas(date(2026, 10, 20))) == 4
    assert quincenas_cercanas(date(2026, 12, 20), antes=0, despues=1) == ["2026-12-16 al 2026-12-31", "2027-01-01 al 2027-01-15"]
