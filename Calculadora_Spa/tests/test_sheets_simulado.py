"""Google Sheets SIMULADO (sin internet): verifica la lógica que habla con gspread.
No reemplaza una prueba contra la hoja real: confirma columnas, orden de escritura y que nunca se borren datos."""
import re

import gspread
import pytest

from nucleo import finanzas as fin
from nucleo.almacen import Almacen, BackendSheets, ColaPendientes
from nucleo.hojas import a1, reemplazar_contenido


def _celda(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    return int(m.group(2)), col


class HojaFalsa:
    def __init__(self, titulo, valores=None, filas=1000, cols=26):
        self.title, self.row_count, self.col_count = titulo, filas, cols
        self.celdas, self.llamadas, self.fallar = {}, [], set()
        if valores:
            self.update(values=valores, range_name="A1")
            self.llamadas.clear()

    def _usado(self):
        if not self.celdas:
            return 0, 0
        return max(r for r, _ in self.celdas), max(c for _, c in self.celdas)

    def get_all_values(self, value_render_option=None):
        filas, cols = self._usado()
        return [[self.celdas.get((r, c), "") for c in range(1, cols + 1)] for r in range(1, filas + 1)]

    def row_values(self, n):
        fila = [self.celdas.get((n, c), "") for c in range(1, self._usado()[1] + 1)]
        while fila and fila[-1] == "":
            fila.pop()
        return fila

    def update(self, values=None, range_name="A1"):
        if "update" in self.fallar:
            raise ConnectionError("falla simulada en update")
        self.llamadas.append("update")
        r0, c0 = _celda(range_name)
        for i, fila in enumerate(values):
            for j, v in enumerate(fila):
                if v == "":
                    self.celdas.pop((r0 + i, c0 + j), None)
                else:
                    self.celdas[(r0 + i, c0 + j)] = v

    def add_cols(self, n):
        self.col_count += n

    def add_rows(self, n):
        self.row_count += n

    def batch_clear(self, rangos):
        if "batch_clear" in self.fallar:
            raise ConnectionError("falla simulada en batch_clear")
        self.llamadas.append("batch_clear")
        for rango in rangos:
            a, b = rango.split(":")
            (r1, c1), (r2, c2) = _celda(a), _celda(b)
            for k in [k for k in self.celdas if r1 <= k[0] <= r2 and c1 <= k[1] <= c2]:
                del self.celdas[k]

    def append_rows(self, values, value_input_option=None, insert_data_option=None, table_range=None):
        if "append" in self.fallar:
            raise ConnectionError("falla simulada en append")
        self.llamadas.append("append")
        inicio = self._usado()[0] + 1
        self.update(values=values, range_name=f"A{inicio}")
        self.llamadas.pop()


class DocFalso:
    def __init__(self):
        self.hojas = {}

    def worksheet(self, nombre):
        if nombre not in self.hojas:
            raise gspread.exceptions.WorksheetNotFound(nombre)
        return self.hojas[nombre]

    def add_worksheet(self, title, rows, cols):
        self.hojas[title] = HojaFalsa(title, filas=rows, cols=cols)
        return self.hojas[title]


@pytest.fixture
def doc():
    return DocFalso()


def test_crea_la_pestana_con_encabezados_y_guarda_numeros(doc, tmp_path):
    alm = Almacen(BackendSheets(lambda: doc), ColaPendientes(str(tmp_path / "p.jsonl")), usuario="Gerencia")
    r = alm.registrar("Pagos_Personal", fin.nuevo_pago("Luis Violante", "2026-10-15", "Sueldo / planilla", 273.96, "Efectivo", periodo="2026-10-01 al 2026-10-15"))
    assert r.estado == "guardado"
    hoja = doc.hojas["Pagos_Personal"]
    encabezados = hoja.get_all_values()[0]
    assert encabezados[:5] == ["ID", "Registrado", "Usuario", "Movimiento", "Ref_ID"]
    fila = dict(zip(encabezados, hoja.get_all_values()[1]))
    assert fila["Monto"] == 273.96 and fila["Usuario"] == "Gerencia" and fila["Colaborador"] == "Luis Violante"
    assert fin.estado_pagos(alm.leer("Pagos_Personal", forzar=True))[0]["Estado"] == "Completado"


def test_migracion_agrega_columnas_sin_tocar_datos_existentes(doc, tmp_path):
    doc.hojas["Auditoria"] = HojaFalsa("Auditoria", [["Fecha", "Tipo Documento", "Destinatario"],
                                                     ["2026-09-01 10:00:00", "Memorándum", "Luis Violante"]])
    alm = Almacen(BackendSheets(lambda: doc), ColaPendientes(str(tmp_path / "p.jsonl")), usuario="Gerencia")
    assert alm.registrar("Auditoria", {"Fecha": "2026-10-20 09:00:00", "Tipo Documento": "Pago al personal", "Destinatario": "Mario de Paz"}).ok
    valores = doc.hojas["Auditoria"].get_all_values()
    assert valores[0] == ["Fecha", "Tipo Documento", "Destinatario", "Usuario", "ID"]
    assert valores[1][:3] == ["2026-09-01 10:00:00", "Memorándum", "Luis Violante"]  # el dato viejo sigue intacto
    nueva = dict(zip(valores[0], valores[2]))
    assert nueva["Usuario"] == "Gerencia" and nueva["Destinatario"] == "Mario de Paz" and nueva["ID"].startswith("AUD-")


def test_append_que_falla_queda_pendiente_y_luego_se_sincroniza(doc, tmp_path):
    alm = Almacen(BackendSheets(lambda: doc), ColaPendientes(str(tmp_path / "p.jsonl")))
    alm.leer("Caja")  # crea la pestaña
    doc.hojas["Caja"].fallar.add("append")
    r = alm.registrar("Caja", fin.nuevo_movimiento_caja("2026-10-10", "SALIDA", "Transporte", "Taxi", 5, "Efectivo"))
    assert r.estado == "pendiente" and len(doc.hojas["Caja"].get_all_values()) == 1  # solo encabezados
    doc.hojas["Caja"].fallar.clear()
    assert alm.sincronizar()["enviados"] == 1
    assert len(doc.hojas["Caja"].get_all_values()) == 2


def test_reemplazo_seguro_no_borra_si_falla_la_escritura():
    hoja = HojaFalsa("Personal", [["Nombre", "Sueldo"], ["A", 1], ["B", 2], ["C", 3], ["D", 4]], filas=10, cols=5)
    hoja.fallar.add("update")
    with pytest.raises(ConnectionError):
        reemplazar_contenido(hoja, [["Nombre", "Sueldo"], ["A", 10]])
    assert len(hoja.get_all_values()) == 5 and "batch_clear" not in hoja.llamadas  # nada se borró
    hoja.fallar.clear()
    reemplazar_contenido(hoja, [["Nombre", "Sueldo"], ["A", 10], ["B", 20]])
    assert hoja.get_all_values() == [["Nombre", "Sueldo"], ["A", 10], ["B", 20]]
    assert hoja.llamadas == ["update", "batch_clear"]  # primero escribe, después limpia lo sobrante


def test_reemplazo_seguro_si_falla_la_limpieza_los_datos_nuevos_ya_estan():
    hoja = HojaFalsa("Personal", [["Nombre"], ["A"], ["B"], ["C"]], filas=10, cols=3)
    hoja.fallar.add("batch_clear")
    with pytest.raises(ConnectionError):
        reemplazar_contenido(hoja, [["Nombre"], ["X"]])
    assert hoja.get_all_values()[:2] == [["Nombre"], ["X"]]  # lo nuevo quedó escrito; solo sobran filas viejas al final


def test_a1():
    assert a1(1, 1) == "A1" and a1(10, 26) == "Z10" and a1(3, 28) == "AB3"
