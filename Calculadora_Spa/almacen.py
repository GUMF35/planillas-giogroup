"""Guardado permanente de los módulos administrativos.

Principios:
- Cada operación es una FILA NUEVA en su pestaña de Google Sheets: nunca se borra ni se reescribe una hoja.
  Las anulaciones y correcciones también son filas nuevas que apuntan a la original (Ref_ID / Corrige_ID).
- Idempotencia: cada operación lleva un ID único (y, si aplica, una Clave_Unica). Si ya existe, no se duplica.
- Si Google Sheets falla, la operación queda en una COLA DE PENDIENTES (archivo local + memoria) y se informa
  como pendiente; nunca como guardada. «Sincronizar» la envía después sin duplicar.
"""
import json
import math
import os
import threading
import time
from datetime import date, datetime

from .util import marca_tiempo, nuevo_id, texto

COMUNES = ["ID", "Registrado", "Usuario", "Movimiento", "Ref_ID"]

TABLAS = {
    "Pagos_Personal": COMUNES + ["Colaborador", "Fecha", "Concepto", "Periodo", "Monto", "Metodo", "Referencia", "Negocio",
                                 "Comprobante", "Observaciones", "Motivo", "Corrige_ID", "Clave_Unica"],
    "Anticipos": COMUNES + ["Colaborador", "Fecha", "Monto", "Metodo", "Responsable", "Periodo", "Referencia", "Comprobante",
                            "Observaciones", "Motivo", "Clave_Unica"],
    "Prestamos": COMUNES + ["Colaborador", "Fecha", "Monto", "Metodo", "Cuotas", "Cuota_Monto", "Frecuencia", "Primer_Vencimiento",
                            "Condiciones", "Autorizado_Por", "Periodo", "Referencia", "Documento", "Observaciones", "Motivo", "Clave_Unica"],
    "Ajustes_Planilla": COMUNES + ["Periodo", "Colaborador", "Calculado_Anterior", "Calculado_Nuevo", "Diferencia", "Motivo", "Clave_Unica"],
    "Asistencia": COMUNES + ["Colaborador", "Tipo", "Fecha_Hora", "Origen", "Motivo", "Observaciones", "Clave_Unica"],
    "Horarios": COMUNES + ["Alcance_Tipo", "Alcance", "Nombre_Turno", "Vigente_Desde", "Vigente_Hasta", "Lun", "Mar", "Mie", "Jue",
                           "Vie", "Sab", "Dom", "Almuerzo_Min", "Tolerancia_Min", "Observaciones", "Motivo"],
    "Incidencias": COMUNES + ["Colaborador", "Fecha", "Tipo", "Minutos", "Decision", "Comentario", "Clave_Unica"],
    "Expediente": COMUNES + ["Colaborador", "Tipo", "Titulo", "Fecha_Inicio", "Fecha_Fin", "Estado", "Detalle", "Valor_Anterior",
                             "Valor_Nuevo", "Documento", "Motivo"],
    "Caja": COMUNES + ["Fecha", "Tipo", "Categoria", "Concepto", "Monto", "Metodo", "Negocio", "Responsable", "Referencia",
                       "Comprobante", "Observaciones", "Motivo", "Clave_Unica"],
    "Cuentas_por_Pagar": COMUNES + ["Proveedor", "Documento", "Fecha", "Vencimiento", "Monto", "Concepto", "Categoria", "Negocio",
                                    "Metodo", "Referencia", "Comprobante", "Observaciones", "Motivo", "Clave_Unica"],
    "Ventas_Periodo": COMUNES + ["Periodo", "Negocio", "Servicios", "Ventas", "Efectivo", "Transferencia", "POS", "Archivo", "Version", "Clave_Unica"],
    "Auditoria": ["Fecha", "Tipo Documento", "Destinatario", "Usuario", "ID"],
}

PREFIJOS = {"Pagos_Personal": "PAG", "Anticipos": "ANT", "Prestamos": "PRE", "Ajustes_Planilla": "AJU", "Asistencia": "ASI",
            "Horarios": "HOR", "Incidencias": "INC", "Expediente": "EXP", "Caja": "CAJ", "Cuentas_por_Pagar": "CXP",
            "Ventas_Periodo": "VEN", "Auditoria": "AUD"}

GUARDADO, YA_EXISTIA, PENDIENTE, RECHAZADO = "guardado", "ya_existia", "pendiente", "rechazado"


class ErrorConexion(Exception):
    """No se pudo leer Google Sheets para validar una operación."""


class Resultado:
    def __init__(self, estado, mensaje, registro=None, detalle=""):
        self.estado, self.mensaje, self.registro, self.detalle = estado, mensaje, registro, detalle

    @property
    def ok(self):
        """True solo si la operación quedó en el almacenamiento permanente (o ya estaba)."""
        return self.estado in (GUARDADO, YA_EXISTIA)

    @property
    def pendiente(self):
        return self.estado == PENDIENTE

    def __repr__(self):
        return f"Resultado({self.estado!r}, {self.mensaje!r})"


def rechazo(mensaje):
    return Resultado(RECHAZADO, mensaje)


def _celda(v):
    """Valor apto para Sheets: números como números, fechas como texto ISO, vacíos como ''."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "SI" if v else "NO"
    if isinstance(v, float):
        return "" if math.isnan(v) else round(v, 2) if abs(v - round(v, 2)) < 1e-9 else v
    if isinstance(v, int):
        return v
    if isinstance(v, datetime):
        return marca_tiempo(v)
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        try:
            return _celda(v.item())
        except Exception:
            pass
    return str(v)


# ---------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------
class BackendMemoria:
    """Almacenamiento en memoria (pruebas). Con fallar=True simula una caída de Google Sheets."""

    def __init__(self):
        self.tablas = {}
        self.fallar = False
        self.escrituras = 0

    def leer(self, tabla, encabezados):
        if self.fallar:
            raise ConnectionError("Google Sheets no responde (simulado)")
        return [dict(r) for r in self.tablas.get(tabla, [])]

    def agregar(self, tabla, encabezados, registros):
        if self.fallar:
            raise ConnectionError("Google Sheets no responde (simulado)")
        self.escrituras += 1
        self.tablas.setdefault(tabla, []).extend({h: _celda(r.get(h, "")) for h in encabezados} for r in registros)


class BackendSheets:
    """Google Sheets mediante gspread. abrir_documento() devuelve el Spreadsheet (o lanza una excepción)."""

    def __init__(self, abrir_documento):
        self._abrir = abrir_documento
        self._hojas = {}
        self._cabeceras = {}

    def _hoja(self, tabla, encabezados):
        if tabla in self._hojas:
            return self._hojas[tabla]
        import gspread
        doc = self._abrir()
        try:
            ws = doc.worksheet(tabla)
        except gspread.exceptions.WorksheetNotFound:
            ws = doc.add_worksheet(title=tabla, rows=1000, cols=max(26, len(encabezados) + 4))
        self._hojas[tabla] = ws
        return ws

    def _asegurar_encabezados(self, ws, tabla, primera_fila, encabezados):
        """Agrega al final las columnas que falten (migración sin tocar los datos existentes)."""
        actuales = [texto(c) for c in primera_fila]
        while actuales and not actuales[-1]:
            actuales.pop()
        faltan = [h for h in encabezados if h not in actuales]
        if faltan:
            nuevos = actuales + faltan
            if ws.col_count < len(nuevos):
                ws.add_cols(len(nuevos) - ws.col_count)
            ws.update(values=[nuevos], range_name="A1")
            actuales = nuevos
        self._cabeceras[tabla] = actuales
        return actuales

    def leer(self, tabla, encabezados):
        try:
            ws = self._hoja(tabla, encabezados)
            valores = ws.get_all_values(value_render_option="UNFORMATTED_VALUE")
        except Exception:
            self._hojas.pop(tabla, None)
            raise
        cab = self._asegurar_encabezados(ws, tabla, valores[0] if valores else [], encabezados)
        filas = []
        for fila in valores[1:]:
            if not any(texto(c) for c in fila):
                continue
            filas.append({cab[i]: (fila[i] if i < len(fila) else "") for i in range(len(cab))})
        return filas

    def agregar(self, tabla, encabezados, registros):
        try:
            ws = self._hoja(tabla, encabezados)
            cab = self._cabeceras.get(tabla)
            if not cab:
                cab = self._asegurar_encabezados(ws, tabla, ws.row_values(1), encabezados)
            filas = [[_celda(r.get(h, "")) for h in cab] for r in registros]
            ws.append_rows(filas, value_input_option="RAW", insert_data_option="INSERT_ROWS", table_range="A1")
        except Exception:
            self._hojas.pop(tabla, None)
            self._cabeceras.pop(tabla, None)
            raise


# ---------------------------------------------------------------------
# Cola de pendientes (archivo local + memoria, compartida por todas las sesiones del proceso)
# ---------------------------------------------------------------------
_COLAS = {}
_COLAS_LOCK = threading.Lock()


class ColaPendientes:
    def __init__(self, ruta=None):
        self.ruta = ruta
        self._lock = threading.Lock()
        self._items = []
        self.persistente = False
        self.error_archivo = ""
        if ruta:
            try:
                os.makedirs(os.path.dirname(ruta), exist_ok=True)
                if os.path.exists(ruta):
                    with open(ruta, "r", encoding="utf-8") as fh:
                        for linea in fh:
                            linea = linea.strip()
                            if linea:
                                self._items.append(json.loads(linea))
                self.persistente = True
            except Exception as ex:  # disco de solo lectura, archivo dañado, etc.
                self.error_archivo = f"{type(ex).__name__}: {ex}"
                self.persistente = False

    @classmethod
    def compartida(cls, ruta):
        with _COLAS_LOCK:
            if ruta not in _COLAS:
                _COLAS[ruta] = cls(ruta)
            return _COLAS[ruta]

    def _escribir(self):
        if not self.ruta:
            return
        try:
            temporal = self.ruta + ".tmp"
            with open(temporal, "w", encoding="utf-8") as fh:
                for item in self._items:
                    fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            os.replace(temporal, self.ruta)
            self.persistente = True
        except Exception as ex:
            self.error_archivo = f"{type(ex).__name__}: {ex}"
            self.persistente = False

    def agregar(self, tabla, registro, error=""):
        with self._lock:
            self._items = [i for i in self._items if not (i["tabla"] == tabla and i["registro"].get("ID") == registro.get("ID"))]
            self._items.append({"tabla": tabla, "registro": dict(registro), "encolado": marca_tiempo(), "error": error})
            self._escribir()

    def quitar(self, tabla, ids):
        ids = set(ids)
        with self._lock:
            self._items = [i for i in self._items if not (i["tabla"] == tabla and i["registro"].get("ID") in ids)]
            self._escribir()

    def listar(self, tabla=None):
        with self._lock:
            return [dict(i) for i in self._items if tabla is None or i["tabla"] == tabla]

    def __len__(self):
        return len(self._items)


# ---------------------------------------------------------------------
# Almacén
# ---------------------------------------------------------------------
class Almacen:
    def __init__(self, backend=None, cola=None, usuario="", ttl=45.0, reloj=time.monotonic):
        self.backend = backend          # None = Google Sheets no configurado (modo local)
        self.cola = cola if cola is not None else ColaPendientes()
        self.usuario = usuario
        self.ttl = ttl
        self._reloj = reloj
        self._cache = {}
        self.errores_lectura = {}

    @property
    def conectado(self):
        return self.backend is not None

    def invalidar(self, tabla=None):
        if tabla is None:
            self._cache.clear()
        else:
            self._cache.pop(tabla, None)

    def _leer_backend(self, tabla, forzar=False):
        """Filas confirmadas en Google Sheets. Devuelve (filas, ok)."""
        if self.backend is None:
            return [], True
        ahora = self._reloj()
        cache = self._cache.get(tabla)
        if cache and not forzar and ahora - cache[0] < self.ttl:
            return cache[1], True
        try:
            filas = self.backend.leer(tabla, TABLAS.get(tabla, ["ID"]))
        except Exception as ex:
            self.errores_lectura[tabla] = f"{type(ex).__name__}: {ex}"
            return (cache[1] if cache else []), False
        self.errores_lectura.pop(tabla, None)
        self._cache[tabla] = (ahora, filas)
        return filas, True

    def leer(self, tabla, forzar=False):
        """Filas confirmadas + operaciones pendientes de sincronizar (marcadas con _pendiente=True)."""
        filas, _ = self._leer_backend(tabla, forzar)
        ids = {texto(f.get("ID")) for f in filas}
        salida = [dict(f) for f in filas]
        for item in self.cola.listar(tabla):
            reg = item["registro"]
            if texto(reg.get("ID")) not in ids:
                salida.append(dict(reg, _pendiente=True))
        return salida

    def leer_para_validar(self, tabla):
        """Lectura fresca obligatoria antes de operaciones que dependen de saldos o del estado actual."""
        filas, ok = self._leer_backend(tabla, forzar=True)
        if not ok:
            raise ErrorConexion(f"No se pudo leer «{tabla}» en Google Sheets para validar la operación: "
                                f"{self.errores_lectura.get(tabla, '')}. Intenta de nuevo en unos minutos.")
        return self.leer(tabla)

    def _completar(self, tabla, registro, usuario=None):
        encabezados = TABLAS.get(tabla, list(registro.keys()))
        reg = {k: v for k, v in registro.items() if not str(k).startswith("_")}
        if "ID" in encabezados and not texto(reg.get("ID")):
            reg["ID"] = nuevo_id(PREFIJOS.get(tabla, "REG"))
        if "Registrado" in encabezados and not texto(reg.get("Registrado")):
            reg["Registrado"] = marca_tiempo()
        if "Usuario" in encabezados and not texto(reg.get("Usuario")):
            reg["Usuario"] = usuario or self.usuario
        return reg

    def _existentes(self, tabla, filas):
        ids = {texto(f.get("ID")) for f in filas if texto(f.get("ID"))}
        claves = {texto(f.get("Clave_Unica")) for f in filas if texto(f.get("Clave_Unica"))}
        return ids, claves

    def registrar(self, tabla, registro, usuario=None, verificar=True):
        return self.registrar_varios(tabla, [registro], usuario, verificar)

    def registrar_varios(self, tabla, registros, usuario=None, verificar=True):
        """Guarda una o varias filas en una sola operación. Devuelve un Resultado (registro = lista si son varias).

        verificar=False omite la lectura previa (solo para bitácoras con ID nuevo, donde un duplicado es imposible)."""
        if tabla not in TABLAS:
            return rechazo(f"Tabla desconocida: {tabla}")
        regs = [self._completar(tabla, r, usuario) for r in registros]
        if not regs:
            return rechazo("No hay nada que guardar.")
        unico = regs[0] if len(regs) == 1 else regs

        # 1) ¿Ya existe? (en la nube o en la cola) → no se duplica
        if verificar:
            filas_nube, lectura_ok = self._leer_backend(tabla, forzar=True)
        else:
            filas_nube, lectura_ok = [], True
        ids_nube, claves_nube = self._existentes(tabla, filas_nube)
        pend = [i["registro"] for i in self.cola.listar(tabla)]
        ids_pend, claves_pend = self._existentes(tabla, pend)
        nuevos, repetidos_pend = [], 0
        for r in regs:
            rid, clave = texto(r.get("ID")), texto(r.get("Clave_Unica"))
            if rid in ids_nube or (clave and clave in claves_nube):
                continue
            if rid in ids_pend or (clave and clave in claves_pend):
                repetidos_pend += 1
                continue
            nuevos.append(r)
        if not nuevos:
            if repetidos_pend:
                return Resultado(PENDIENTE, "Esta operación ya está en la cola de pendientes; se enviará al sincronizar.", unico)
            return Resultado(YA_EXISTIA, "Esta operación ya estaba registrada: no se duplicó.", unico)

        # 2) Sin Google Sheets configurado → solo cola local
        if self.backend is None:
            for r in nuevos:
                self.cola.agregar(tabla, r, "Google Sheets no configurado")
            donde = "el archivo local de este equipo" if self.cola.persistente else "la memoria de esta sesión"
            return Resultado(PENDIENTE, f"Google Sheets no está configurado: la operación quedó guardada solo en {donde}, "
                                        "pendiente de sincronizar. No está respaldada en la nube.", unico)

        # 3) Si no se pudo leer la hoja, no arriesgamos duplicados: va a la cola
        if not lectura_ok:
            error = self.errores_lectura.get(tabla, "sin conexión")
            for r in nuevos:
                self.cola.agregar(tabla, r, error)
            return Resultado(PENDIENTE, self._mensaje_pendiente(error), unico, error)

        # 4) Guardar en Google Sheets
        try:
            self.backend.agregar(tabla, TABLAS[tabla], nuevos)
        except Exception as ex:
            error = f"{type(ex).__name__}: {ex}"
            for r in nuevos:
                self.cola.agregar(tabla, r, error)
            self.invalidar(tabla)
            return Resultado(PENDIENTE, self._mensaje_pendiente(error), unico, error)
        self.invalidar(tabla)
        return Resultado(GUARDADO, "Guardado en Google Sheets.", unico)

    def _mensaje_pendiente(self, error):
        donde = "en este equipo" if self.cola.persistente else "solo en la memoria de esta sesión"
        return (f"No se pudo guardar en Google Sheets ({error[:160]}). La operación quedó PENDIENTE de sincronización {donde}: "
                "todavía no está respaldada en la nube.")

    def pendientes(self, tabla=None):
        return self.cola.listar(tabla)

    def sincronizar(self):
        """Envía la cola a Google Sheets sin duplicar. Devuelve {'enviados', 'descartados', 'fallidos', 'errores'}."""
        resumen = {"enviados": 0, "descartados": 0, "fallidos": 0, "errores": []}
        if self.backend is None:
            resumen["errores"].append("Google Sheets no está configurado.")
            resumen["fallidos"] = len(self.cola)
            return resumen
        por_tabla = {}
        for item in self.cola.listar():
            por_tabla.setdefault(item["tabla"], []).append(item["registro"])
        for tabla, registros in por_tabla.items():
            filas, ok = self._leer_backend(tabla, forzar=True)
            if not ok:
                resumen["fallidos"] += len(registros)
                resumen["errores"].append(f"{tabla}: {self.errores_lectura.get(tabla, '')}")
                continue
            ids, claves = self._existentes(tabla, filas)
            ya = [r for r in registros if texto(r.get("ID")) in ids or (texto(r.get("Clave_Unica")) and texto(r.get("Clave_Unica")) in claves)]
            nuevos = [r for r in registros if r not in ya]
            if ya:
                self.cola.quitar(tabla, [r.get("ID") for r in ya])
                resumen["descartados"] += len(ya)
            if not nuevos:
                continue
            try:
                self.backend.agregar(tabla, TABLAS.get(tabla, list(nuevos[0].keys())), nuevos)
            except Exception as ex:
                resumen["fallidos"] += len(nuevos)
                resumen["errores"].append(f"{tabla}: {type(ex).__name__}: {ex}")
                continue
            self.cola.quitar(tabla, [r.get("ID") for r in nuevos])
            resumen["enviados"] += len(nuevos)
            self.invalidar(tabla)
        return resumen
