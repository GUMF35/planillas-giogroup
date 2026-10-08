# =====================================================================
# GIO GROUP · Suite Administrativa
# Planillas · E-commerce · Panel · Proveedores · Documentos · Configuración
# =====================================================================
import base64
import calendar
import hashlib
import html
import inspect
import io
import json
import os
import re
import smtplib
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import gspread
import pandas as pd
import pdfplumber
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from fpdf import FPDF
from google.oauth2.service_account import Credentials
from PIL import Image


# =====================================================================
# 0. CONSTANTES
# =====================================================================
ZONA_SV = timezone(timedelta(hours=-6))  # El Salvador (sin horario de verano)

MOD_ESTANDAR = "Estándar (Con retención 25% Pub)"
MOD_PORCENTAJE = "Porcentaje Directo (%)"
MOD_FIJO = "Fijo"
MODALIDADES = [MOD_ESTANDAR, MOD_PORCENTAJE, MOD_FIJO]
MOD_ETIQUETAS = {MOD_ESTANDAR: "💵 Sueldo base + extras", MOD_PORCENTAJE: "📈 Porcentaje de ventas", MOD_FIJO: "🔒 Sueldo fijo"}
MOD_AYUDA = {
    MOD_ESTANDAR: "Recibe su sueldo base y, por cada servicio mayor al precio mínimo, el excedente menos la retención de pauta.",
    MOD_PORCENTAJE: "No tiene sueldo base ni renta: gana el porcentaje que definas (de 1% a 100%) sobre todo lo que vende.",
    MOD_FIJO: "Solo recibe su sueldo base (ideal para administración). A un operativo se le puede sumar una comisión opcional.",
}
ROLES = ["Operativo", "Administrativo"]

# Salario mínimo de comercio y servicios (Decreto Ejecutivo N.° 11, Diario Oficial del 23/05/2025)
SALARIO_MINIMO_REF = 408.80
FUENTE_SALARIO_MINIMO = "Comercio y servicios · Decreto Ejecutivo N.° 11 (Diario Oficial, 23/05/2025)"
SUELDO_NETO_POR_DEFECTO = {"Operativo": 183.96, "Administrativo": 300.00}

AJUSTES_POR_DEFECTO = {
    "empresa_nombre": "GIO GROUP SAS DE CV",
    "empresa_corto": "Gio Group",
    "firma_correo": "Administración GIO GROUP SAS DE CV",
    "tema": "Índigo",
    "mostrar_hero": True,
    "salario_minimo": SALARIO_MINIMO_REF,
    "umbral_extra": 60.0,
    "retencion_pub_pct": 25.0,
    "renta_pct": 10.0,
    "logo_b64": "",
}
AJUSTES_NUMERICOS = ("salario_minimo", "umbral_extra", "retencion_pub_pct", "renta_pct")
REGLAS_OFICIALES = {"umbral_extra": 60.0, "retencion_pub_pct": 25.0, "renta_pct": 10.0}

TEMAS = {
    "Índigo":    {"p": "#4F46E5", "p400": "#6366F1", "p600": "#4338CA", "p50": "#EEF2FF", "p100": "#E0E7FF", "acc": "#0EA5E9", "h1": "#0B1B3F", "h2": "#172554", "h3": "#3730A3", "glow": "129,140,248"},
    "Esmeralda": {"p": "#059669", "p400": "#10B981", "p600": "#047857", "p50": "#ECFDF5", "p100": "#D1FAE5", "acc": "#14B8A6", "h1": "#022C22", "h2": "#064E3B", "h3": "#047857", "glow": "52,211,153"},
    "Océano":    {"p": "#0284C7", "p400": "#0EA5E9", "p600": "#0369A1", "p50": "#F0F9FF", "p100": "#E0F2FE", "acc": "#06B6D4", "h1": "#082F49", "h2": "#0C4A6E", "h3": "#0369A1", "glow": "56,189,248"},
    "Violeta":   {"p": "#7C3AED", "p400": "#8B5CF6", "p600": "#6D28D9", "p50": "#F5F3FF", "p100": "#EDE9FE", "acc": "#EC4899", "h1": "#1E0B3B", "h2": "#2E1065", "h3": "#5B21B6", "glow": "167,139,250"},
    "Vino":      {"p": "#BE123C", "p400": "#E11D48", "p600": "#9F1239", "p50": "#FFF1F2", "p100": "#FFE4E6", "acc": "#F97316", "h1": "#2A0A12", "h2": "#4C0519", "h3": "#9F1239", "glow": "251,113,133"},
    "Dorado":    {"p": "#B45309", "p400": "#D97706", "p600": "#92400E", "p50": "#FFFBEB", "p100": "#FEF3C7", "acc": "#EAB308", "h1": "#1C1003", "h2": "#451A03", "h3": "#92400E", "glow": "251,191,36"},
    "Grafito":   {"p": "#334155", "p400": "#475569", "p600": "#1E293B", "p50": "#F1F5F9", "p100": "#E2E8F0", "acc": "#64748B", "h1": "#020617", "h2": "#0F172A", "h3": "#334155", "glow": "148,163,184"},
}

MENU = [
    ("Principal", [("Planillas", "💼", "Planillas"), ("Ecommerce", "🏪", "E-commerce"), ("Dashboard", "📊", "Panel general")]),
    ("Gestión", [("Proveedores", "📇", "Proveedores"), ("Memorándums", "📝", "Memorándums"), ("Amonestaciones", "⚠️", "Amonestaciones")]),
    ("Sistema", [("Auditoría", "🗂️", "Historial"), ("Configuración", "⚙️", "Configuración")]),
]
PAGINAS_VALIDAS = [p for _, items in MENU for p, _, _ in items]
ETIQUETAS_PAGINA = {p: f"{icono} {etiqueta}" for _, items in MENU for p, icono, etiqueta in items}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Columnas del reporte de ventas (sin tildes y en mayúsculas)
CLAVES_PROFESIONAL = ("PROFESIONAL", "COLABORADOR", "EMPLEADO", "ESTILISTA", "TERAPEUTA",
                      "ESPECIALISTA", "ATENDIDO", "BARBERO", "MASAJISTA")
CLAVES_PRECIO = ("PRECIO", "TOTAL", "MONTO", "IMPORTE", "VALOR", "COBRADO", "PAGADO")
CLAVES_CLIENTE = ("CLIENTE", "PACIENTE")
CLAVES_SERVICIO = ("SERVICIO", "TRATAMIENTO", "PROCEDIMIENTO", "PRODUCTO", "DESCRIPCION", "CONCEPTO")
CLAVES_FECHA = ("FECHA",)
CLAVES_MARCA = ("ECOMER", "E-COMER", "E COMER", "COMERCIO", "MARCA", "SUCURSAL", "NEGOCIO", "UNIDAD")
CLAVES_CORRELATIVO = ("CORRELATIVO", "FOLIO", "TICKET", "FACTURA", "CODIGO")
CLAVES_EFECTIVO = ("EFECTIVO", "CONTADO", "CASH")
CLAVES_TRANSFER = ("TRANSFER", "DEPOSITO")
CLAVES_POS = ("POS", "TARJETA")
PATRON_TOTAL = re.compile(r"^(SUB\s*-?\s*TOTAL|GRAN\s+TOTAL|TOTALES|TOTAL|SUMA)\b")
PATRON_FIN_TABLA = re.compile(r"^(TOTALES|GRAN\s+TOTAL|TOTAL\s+GENERAL|RESUMEN|REGISTRO\s+DE)")
PATRON_FECHA = r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})"
RANGO_RE = re.compile(r"\b(?:DESDE|DEL|PERIODO|RANGO|FECHAS?)\s*:?\s*" + PATRON_FECHA + r"[^0-9]{1,25}?" + PATRON_FECHA)
AJUSTES_TABLA_TEXTO = {"vertical_strategy": "text", "horizontal_strategy": "text",
                       "snap_tolerance": 3, "join_tolerance": 3, "intersection_tolerance": 5}

AUTO = "(automático)"
CLAVES_MAPEO = ("map_prof", "map_precio", "map_cliente", "map_servicio", "map_marca", "map_quincenas")

ORDEN_MARCAS = ["Papi Spa", "Relájate Man", "Dr. Gio Molina", "Relájate Clinic"]
COLORES_MARCA = {"Papi Spa": "#2a78d6", "Relájate Man": "#eb6834", "Dr. Gio Molina": "#1baf7a", "Relájate Clinic": "#eda100"}
COLORES_PAGO = {"Efectivo": "#0D9488", "Transferencia": "#7C3AED", "POS": "#E11D48"}
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}

NUEVO_EMP = "➕ Nuevo colaborador"
MODO_NETO_Q = "Neto quincenal"
MODO_BRUTO_M = "Bruto mensual"

ENCABEZADOS_HISTORIAL = ["Guardado", "Periodo", "Desde", "Hasta", "Quincenas", "Colaborador", "Forma_Pago", "Servicios",
                         "Ventas", "Sueldo_Neto", "Comision", "Bonos", "Descuentos", "Renta", "Total"]


# =====================================================================
# 1. UTILIDADES GENERALES
# =====================================================================
def ahora_sv():
    return datetime.now(ZONA_SV)


def _texto(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    t = str(v).strip()
    return "" if t.lower() in ("nan", "none", "nat") else t


def _esc(v):
    return html.escape(_texto(v))


def _normalizar(v):
    t = unicodedata.normalize("NFKD", _texto(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().upper()


def _clave_nombre(v):
    """'MARVIN\\nMOLINA', 'Marvin Molina' y 'MARVINMOLINA' → 'MARVINMOLINA' (para comparar nombres)."""
    return re.sub(r"[^A-Z0-9]", "", _normalizar(v))


def nombre_bonito(v):
    return re.sub(r"\s+", " ", _texto(v)).title()


def _a_numero(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip()
    if not s:
        return None
    for linea in s.splitlines():
        if re.search(r"\d", linea):
            s = linea.strip()
            break
    else:
        return None
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    token = m.group().rstrip(".,")
    prefijo = s[:m.start()]
    negativo = "-" in prefijo or "(" in prefijo
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        partes = token.split(",")
        token = token.replace(",", ".") if (len(partes) == 2 and len(partes[1]) in (1, 2)) else token.replace(",", "")
    elif token.count(".") > 1:
        partes = token.split(".")
        token = "".join(partes[:-1]) + "." + partes[-1]
    try:
        n = float(token)
    except ValueError:
        return None
    return -n if negativo else n


def _a_porcentaje(v, defecto=0.0):
    n = _a_numero(v)
    if n is None:
        return defecto
    if 0 < n < 1 and "%" not in _texto(v):
        n = n * 100.0
    return n


def normalizar_modalidad(v):
    n = _normalizar(v)
    if "ESTANDAR" in n or "RETENCION" in n or "EXTRAS" in n:
        return MOD_ESTANDAR
    if "PORCENTAJE" in n or "%" in n or "COMISION" in n:
        return MOD_PORCENTAJE
    return MOD_FIJO


def normalizar_rol(v):
    n = _normalizar(v)
    if not n or n.startswith("OPERA"):
        return "Operativo"
    if n.startswith("ADMIN") or n.startswith("DIRECT") or n.startswith("GEREN"):
        return "Administrativo"
    return _texto(v)


def modalidad_corta(mod):
    return "Estándar" if "Estándar" in mod else "Porcentaje" if "Porcentaje" in mod else "Fijo"


def forma_pago_texto(info):
    mod = info.get("mod", MOD_FIJO)
    porc = float(_a_numero(info.get("porc")) or 0.0)
    if "Porcentaje" in mod:
        return f"{porc:g}% de ventas"
    if "Estándar" in mod:
        return "Sueldo + extras"
    if info.get("rol") == "Operativo" and porc > 0:
        return f"Sueldo fijo + {porc:g}%"
    return "Sueldo fijo"


def alias_efectivo(nombre, info):
    alias = _texto(info.get("alias"))
    if alias:
        return alias
    for parte in _texto(nombre).split():
        if len(parte) >= 3 and "." not in parte:
            return parte
    return ""


def patron_alias(alias):
    partes = [p.strip() for p in _normalizar(alias).split("|") if p.strip()]
    return "|".join(partes)


def coincide_alias(nombre_norm, patron):
    if not patron:
        return False
    try:
        return re.search(patron, nombre_norm) is not None
    except re.error:
        return any(p in nombre_norm for p in patron.split("|"))


def _parse_fecha_texto(s):
    s = _texto(s)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _fecha_de_celda(v):
    m = re.search(PATRON_FECHA, _texto(v))
    return _parse_fecha_texto(m.group(1)) if m else None


def _fecha_de_correlativo(v):
    """'20260901-001' → 1/09/2026 (los correlativos del sistema de ventas empiezan con la fecha)."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", _texto(v))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_fecha(v):
    t = _texto(v)
    if not t:
        return None
    fecha = pd.to_datetime(t, dayfirst=not re.match(r"^\d{4}-", t), errors="coerce")
    return None if pd.isna(fecha) else fecha


def usd(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _iniciales(nombre):
    partes = [p for p in re.split(r"\s+", _texto(nombre)) if p and p[0].isalnum()]
    return ("".join(p[0] for p in partes[:2]) or "?").upper()


def nombre_archivo(prefijo, nombre):
    limpio = unicodedata.normalize("NFKD", _texto(nombre)).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", limpio).strip("_") or "Colaborador"
    return f"{prefijo}_{limpio}.pdf"


def limpiar_texto_pdf(txt):
    if txt is None:
        return ""
    return str(txt).encode('latin-1', 'replace').decode('latin-1')


def generar_pdf_bytes(pdf_obj):
    return bytes(pdf_obj.output())


def correo_valido(correo):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _texto(correo)))


_CACHE_WIDTH = {}


def _api_width_nueva(fn):
    nombre = getattr(fn, "__name__", repr(fn))
    if nombre not in _CACHE_WIDTH:
        try:
            p = inspect.signature(fn).parameters.get("width")
            _CACHE_WIDTH[nombre] = p is not None and isinstance(p.default, str)
        except (TypeError, ValueError):
            _CACHE_WIDTH[nombre] = False
    return _CACHE_WIDTH[nombre]


def ancho(fn):
    """Ancho completo compatible con Streamlit nuevo (width='stretch') y anterior (use_container_width)."""
    return {"width": "stretch"} if _api_width_nueva(fn) else {"use_container_width": True}


def columnas(spec, alinear=None):
    """st.columns con alineación vertical (evita espacios fijos que se desacomodan en el teléfono)."""
    if alinear:
        try:
            return st.columns(spec, vertical_alignment=alinear)
        except TypeError:
            pass
    return st.columns(spec)


def secreto(*ruta):
    try:
        valor = st.secrets
        for parte in ruta:
            valor = valor[parte]
        return valor
    except Exception:
        return None


# =====================================================================
# 2. GOOGLE SHEETS
# =====================================================================
@st.cache_resource(show_spinner=False)
def _abrir_documento():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    skey = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(skey, scopes=scopes)
    gc = gspread.authorize(credentials)
    return gc.open_by_url(st.secrets["gsheets"]["url"])


def _documento():
    try:
        return _abrir_documento()
    except Exception:
        return None


def error_conexion():
    try:
        _abrir_documento()
        return ""
    except Exception as ex:
        return f"{type(ex).__name__}: {ex}"


def conectar_gsheets(nombre_hoja="Personal", crear=False):
    doc = _documento()
    if doc is None:
        return None
    try:
        return doc.worksheet(nombre_hoja)
    except gspread.exceptions.WorksheetNotFound:
        if nombre_hoja == "Personal":
            return doc.sheet1
        if crear:
            try:
                return doc.add_worksheet(title=nombre_hoja, rows=500, cols=30)
            except Exception:
                return None
        return None
    except Exception:
        return None


def _leer_registros(worksheet):
    try:
        return worksheet.get_all_records(numericise_ignore=["all"])
    except TypeError:
        return worksheet.get_all_records()


def _valor_para_sheets(v):
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except Exception:
            pass
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.strftime("%Y-%m-%d")
    return v


def _registros_validos(datos_list):
    if not datos_list:
        return []
    return [r for r in datos_list if any(_valor_para_sheets(v) != "" for v in r.values())]


def _escribir_hoja(nombre_hoja, filas):
    worksheet = conectar_gsheets(nombre_hoja, crear=True)
    if not worksheet:
        return False
    try:
        worksheet.clear()
        worksheet.update(values=filas, range_name="A1")
        return True
    except Exception:
        return False


EMPLEADOS_POR_DEFECTO = {
    "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96},
    "Luis Violante": {"rol": "Operativo", "alias": "LUIS", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96},
    "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA", "mod": MOD_PORCENTAJE, "porc": 20, "sueldo_base_neto": 0.0},
    "Mario de Paz": {"rol": "Operativo", "alias": "MARIO", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96},
    "Dr. Gio Molina": {"rol": "Administrativo", "alias": "GIO|MARVIN|DOCTOR", "mod": MOD_FIJO, "porc": 0, "sueldo_base_neto": 300.00},
    "Gerson Ulises Molina Flores": {"rol": "Administrativo", "alias": "GERSON", "mod": MOD_FIJO, "porc": 0, "sueldo_base_neto": 300.00},
}
CAMPOS_EXTRA_EMPLEADO = ("cargo", "correo", "telefono", "dui", "banco", "cuenta", "fecha_ingreso")


def sueldo_neto_por_defecto(rol):
    return SUELDO_NETO_POR_DEFECTO.get(rol, SUELDO_NETO_POR_DEFECTO["Administrativo"])


def _leer_sueldo_neto(registro, rol):
    for clave, valor in registro.items():
        n = _normalizar(clave)
        if "SUELDO" in n or "SALARIO" in n:
            numero = _a_numero(valor)
            if numero is not None:
                return numero
    return sueldo_neto_por_defecto(rol)


def _empleado_normalizado(info):
    mod = normalizar_modalidad(info.get("mod", "Fijo"))
    rol = normalizar_rol(info.get("rol", "Operativo"))
    sueldo = _a_numero(info.get("sueldo_base_neto"))
    porc = _a_porcentaje(info.get("porc", 0), 20.0 if mod == MOD_PORCENTAJE else 0.0)
    limpio = {
        "rol": rol, "alias": _texto(info.get("alias")), "mod": mod,
        "porc": min(max(porc, 0.0), 100.0),
        "sueldo_base_neto": sueldo if sueldo is not None else sueldo_neto_por_defecto(rol),
    }
    for campo in CAMPOS_EXTRA_EMPLEADO:
        limpio[campo] = _texto(info.get(campo))
    return limpio


def cargar_empleados():
    worksheet = conectar_gsheets("Personal")
    if worksheet:
        try:
            emp_dict = {}
            for r in _leer_registros(worksheet):
                nombre = _texto(r.get("Nombre"))
                if not nombre:
                    continue
                rol = normalizar_rol(r.get("Rol", "Operativo"))
                emp_dict[nombre] = _empleado_normalizado({
                    "rol": rol, "alias": r.get("Alias", ""), "mod": r.get("Modalidad", "Fijo"),
                    "porc": r.get("Porcentaje", 0), "sueldo_base_neto": _leer_sueldo_neto(r, rol),
                    "cargo": r.get("Cargo", ""), "correo": r.get("Correo", ""), "telefono": r.get("Telefono", ""),
                    "dui": r.get("DUI", ""), "banco": r.get("Banco", ""), "cuenta": r.get("Cuenta", ""),
                    "fecha_ingreso": r.get("Fecha_Ingreso", ""),
                })
            if emp_dict:
                return emp_dict, "Google Sheets"
        except Exception:
            pass
    return {k: _empleado_normalizado(v) for k, v in EMPLEADOS_POR_DEFECTO.items()}, "Datos locales"


def guardar_empleados(datos):
    if not datos:
        return False
    filas = [["Nombre", "Cargo", "Rol", "Alias", "Modalidad", "Porcentaje", "Sueldo_Base_Neto", "Correo", "Telefono", "DUI", "Banco", "Cuenta", "Fecha_Ingreso"]]
    for nombre, info in datos.items():
        filas.append([_valor_para_sheets(x) for x in [
            nombre, info.get("cargo", ""), info.get("rol", ""), info.get("alias", ""), info.get("mod", ""),
            info.get("porc", 0), sueldo_neto_de(info), info.get("correo", ""), info.get("telefono", ""),
            info.get("dui", ""), info.get("banco", ""), info.get("cuenta", ""), info.get("fecha_ingreso", "")]])
    return _escribir_hoja("Personal", filas)


PROVEEDOR_EJEMPLO = {
    "ID_Proveedor": "1", "Nombre_Proveedor": "JG SUMINISTROS", "Nombre_Contacto": "JULIO CESAR HERNANDEZ",
    "Telefono_1": "7398 4751", "Telefono_2": "", "Correo": "jgsuministrossv@gmail.com",
    "Banco": "Banco Cuscatlan", "Cuenta": "325-301-000002077", "Direccion_1": "",
    "Direccion_2": "San Salvador", "Pais": "El Salvador", "Patrocinador": "",
    "Valoracion": "50%", "Fecha_Ultima_Rev": "", "Fecha_Prox_Rev": "", "Fecha_Contrato": "", "Fecha_Vencimiento": "",
    "Fecha_Calif_Riesgo": "", "Fecha_Diligencia": "", "Fecha_Rev_Contrato": "", "Fecha_Aprobacion": "",
    "Descripcion": "suministros medicos", "Notas": ""
}
CAMPOS_PROVEEDOR = list(PROVEEDOR_EJEMPLO.keys())


def cargar_proveedores():
    worksheet = conectar_gsheets("Proveedores")
    if worksheet:
        try:
            records = _leer_registros(worksheet)
            if records:
                return records
        except Exception:
            pass
    return [dict(PROVEEDOR_EJEMPLO)]


def guardar_proveedores(datos_list, encabezados_si_vacio=None):
    datos_list = _registros_validos(datos_list)
    if not datos_list:
        return _escribir_hoja("Proveedores", [list(encabezados_si_vacio)]) if encabezados_si_vacio else False
    encabezados = []
    for item in datos_list:
        for k in item.keys():
            if k not in encabezados:
                encabezados.append(k)
    filas = [encabezados] + [[_valor_para_sheets(item.get(c, "")) for c in encabezados] for item in datos_list]
    return _escribir_hoja("Proveedores", filas)


def cargar_ajustes():
    ajustes = dict(AJUSTES_POR_DEFECTO)
    worksheet = conectar_gsheets("Ajustes")
    if worksheet:
        try:
            for r in _leer_registros(worksheet):
                clave, valor = _texto(r.get("Clave")), r.get("Valor")
                if clave not in ajustes:
                    continue
                if clave in AJUSTES_NUMERICOS:
                    n = _a_numero(valor)
                    if n is not None:
                        ajustes[clave] = n
                elif isinstance(AJUSTES_POR_DEFECTO[clave], bool):
                    ajustes[clave] = _normalizar(valor) in ("TRUE", "SI", "1", "VERDADERO")
                elif _texto(valor):
                    ajustes[clave] = _texto(valor)
        except Exception:
            pass
    if ajustes["tema"] not in TEMAS:
        ajustes["tema"] = "Índigo"
    return ajustes


def guardar_ajustes(ajustes):
    filas = [["Clave", "Valor"]] + [[k, _valor_para_sheets(ajustes.get(k, v))] for k, v in AJUSTES_POR_DEFECTO.items()]
    return _escribir_hoja("Ajustes", filas)


def cargar_auditoria():
    worksheet = conectar_gsheets("Auditoria")
    if worksheet:
        try:
            return [{"Fecha": _texto(r.get("Fecha")), "Tipo Documento": _texto(r.get("Tipo Documento")),
                     "Destinatario": _texto(r.get("Destinatario"))} for r in _leer_registros(worksheet)]
        except Exception:
            pass
    return []


def _auditoria_a_sheets(registro):
    worksheet = conectar_gsheets("Auditoria", crear=True)
    if not worksheet:
        return
    try:
        if not st.session_state.get("_aud_encabezado"):
            if not worksheet.row_values(1):
                worksheet.update(values=[["Fecha", "Tipo Documento", "Destinatario"]], range_name="A1")
            st.session_state["_aud_encabezado"] = True
        worksheet.append_row([registro["Fecha"], registro["Tipo Documento"], registro["Destinatario"]])
    except Exception:
        pass


def cargar_historial_planillas():
    """Planillas guardadas en la hoja 'Historial_Planillas'. None si no hay conexión."""
    worksheet = conectar_gsheets("Historial_Planillas")
    if worksheet is None:
        return None
    try:
        if not worksheet.row_values(1):
            return []
        return _leer_registros(worksheet)
    except Exception:
        return None


def guardar_historial_planilla(filas_nuevas, periodo):
    """Guarda la planilla del período (si el período ya existía, se reemplaza para no duplicar)."""
    worksheet = conectar_gsheets("Historial_Planillas", crear=True)
    if worksheet is None:
        return False
    try:
        existentes = _leer_registros(worksheet) if worksheet.row_values(1) else []
        conservar = [r for r in existentes if _texto(r.get("Periodo")) != periodo]
        filas = [ENCABEZADOS_HISTORIAL]
        filas += [[_valor_para_sheets(r.get(c, "")) for c in ENCABEZADOS_HISTORIAL] for r in conservar]
        filas += [[_valor_para_sheets(f.get(c, "")) for c in ENCABEZADOS_HISTORIAL] for f in filas_nuevas]
        worksheet.clear()
        worksheet.update(values=filas, range_name="A1")
        return True
    except Exception:
        return False


def preparar_hoja_calculo():
    """Crea (o actualiza) todas las pestañas que usa la app con sus encabezados."""
    ss = st.session_state
    doc = _documento()
    if doc is None:
        return None
    try:
        doc.worksheet("Personal")
    except gspread.exceptions.WorksheetNotFound:
        try:
            primera = doc.sheet1
            if not primera.row_values(1):
                primera.update_title("Personal")
            else:
                doc.add_worksheet(title="Personal", rows=200, cols=20)
        except Exception:
            pass
    except Exception:
        pass
    resultados = {
        "Personal": guardar_empleados(ss["empleados"]),
        "Proveedores": guardar_proveedores(ss["proveedores"], encabezados_si_vacio=CAMPOS_PROVEEDOR),
        "Ajustes": guardar_ajustes(ss["ajustes"]),
    }
    for hoja, encabezados in (("Auditoria", ["Fecha", "Tipo Documento", "Destinatario"]), ("Historial_Planillas", ENCABEZADOS_HISTORIAL)):
        ok = False
        worksheet = conectar_gsheets(hoja, crear=True)
        if worksheet is not None:
            try:
                if not worksheet.row_values(1):
                    worksheet.update(values=[encabezados], range_name="A1")
                ok = True
            except Exception:
                ok = False
        resultados[hoja] = ok
    return resultados



# =====================================================================
# 3. CONFIGURACIÓN DE PÁGINA
# =====================================================================
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
try:
    if os.path.exists(logo_path):
        st.set_page_config(page_title="Gio Group · Gerencia", page_icon=Image.open(logo_path), layout="wide", initial_sidebar_state="auto")
    else:
        st.set_page_config(page_title="Gio Group · Gerencia", page_icon="🏢", layout="wide", initial_sidebar_state="auto")
except Exception:
    st.set_page_config(page_title="Gio Group · Gerencia", page_icon="🏢", layout="wide")


# =====================================================================
# 4. ESTADO DE MEMORIA
# =====================================================================
DEFAULTS_GLOBALES = {
    "pagina": "Planillas",
    "quincenas_multiplicador": 1.0,
    "quincenas_manual": None,
    "periodo_texto": "1 Quincena (Por defecto)",
    "periodo_info": None,
    "detalle_extras": [],
    "total_ingresos_pdf": 0.0,
    "ingresos_por_marca": {},
    "extras_por_marca": {},
    "pdf_hash": None,
    "pdf_nombre": "",
    "pdf_bytes": None,
    "pdf_ok": False,
    "pdf_error": "",
    "pdf_meta": {},
    "pdf_resumen": {},
    "pagos_ok": False,
    "reporte_df": None,
    "resumen_pdf": {},
    "indices_por_colab": {},
    "historial_local": {},
    "uploader_nonce": 0,
    "nonce_editor_personal": 0,
    "prov_modo": "ver",
    "prov_idx": None,
    "_toasts": [],
    "_errores": [],
}
for _k, _v in DEFAULTS_GLOBALES.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v

if "ajustes" not in st.session_state:
    st.session_state["ajustes"] = cargar_ajustes()
if "empleados" not in st.session_state:
    st.session_state["empleados"], st.session_state["fuente_personal"] = cargar_empleados()
if "proveedores" not in st.session_state:
    st.session_state["proveedores"] = cargar_proveedores()
if "historial_auditoria" not in st.session_state:
    st.session_state["historial_auditoria"] = cargar_auditoria()
if st.session_state["pagina"] not in PAGINAS_VALIDAS:
    st.session_state["pagina"] = "Planillas"


def aj(clave):
    return st.session_state.get("ajustes", {}).get(clave, AJUSTES_POR_DEFECTO.get(clave))


def tema():
    return TEMAS.get(aj("tema"), TEMAS["Índigo"])


# --- Reglas de cálculo (valores oficiales por defecto: $60, 25% y 10%) ---
def tasa_renta():
    return min(max(float(aj("renta_pct") or 0.0), 0.0), 90.0) / 100.0


def factor_neto():
    return 1.0 - tasa_renta()  # 0.90 con renta del 10%


def umbral_extra():
    return float(aj("umbral_extra") or 0.0)


def tasa_pauta():
    return min(max(float(aj("retencion_pub_pct") or 0.0), 0.0), 100.0) / 100.0


def sueldo_neto_de(info):
    """Sueldo neto QUINCENAL de la persona (lo que recibe libre de renta)."""
    n = _a_numero(info.get("sueldo_base_neto"))
    return n if n is not None else sueldo_neto_por_defecto(info.get("rol", "Operativo"))


def neto_q_desde_bruto_mensual(bruto_mensual):
    return round(float(bruto_mensual or 0.0) / 2.0 * factor_neto(), 2)


def desglose_sueldo(neto_q):
    """Bruto, renta y neto por quincena y por mes a partir del neto quincenal."""
    neto_q = float(neto_q or 0.0)
    bruto_q = round(neto_q / factor_neto(), 2) if neto_q > 0 else 0.0
    renta_q = round(bruto_q * tasa_renta(), 2)
    return {"neto_q": neto_q, "bruto_q": bruto_q, "renta_q": renta_q,
            "neto_m": round(neto_q * 2, 2), "bruto_m": round(bruto_q * 2, 2), "renta_m": round(renta_q * 2, 2)}


def base_neta_periodo(info):
    return 0.0 if "Porcentaje" in info.get("mod", "Fijo") else round(sueldo_neto_de(info) * st.session_state["quincenas_multiplicador"], 2)


def inicializar_empleados():
    ss = st.session_state
    for emp, info in ss["empleados"].items():
        for pref in ("com_", "extra_bruto_", "ret_pub_", "serv_tot_", "hex_", "desc_"):
            if f"{pref}{emp}" not in ss:
                ss[f"{pref}{emp}"] = 0.0
        if f"email_{emp}" not in ss:
            ss[f"email_{emp}"] = _texto(info.get("correo"))
        if f"notas_{emp}" not in ss:
            ss[f"notas_{emp}"] = "Ninguno"
        if f"base_net_{emp}" not in ss:
            ss[f"base_net_{emp}"] = base_neta_periodo(info)


inicializar_empleados()


def recalcular_bases():
    for emp, info in st.session_state["empleados"].items():
        st.session_state[f"base_net_{emp}"] = base_neta_periodo(info)


def correo_de(emp):
    ss = st.session_state
    return _texto(ss.get(f"email_{emp}")) or _texto(ss["empleados"].get(emp, {}).get("correo"))


def notificar(msg, icon="✅"):
    st.session_state["_toasts"].append((msg, icon))


def notificar_error(msg):
    st.session_state["_errores"].append(msg)


def mostrar_notificaciones():
    pendientes = st.session_state.get("_toasts", [])
    st.session_state["_toasts"] = []
    for msg, icon in pendientes:
        st.toast(msg, icon=icon)
    errores = st.session_state.get("_errores", [])
    st.session_state["_errores"] = []
    for msg in errores:
        st.error(msg)


def campo_persistente(widget_fn, label, state_key, ui_key, conv=None, **kwargs):
    if ui_key not in st.session_state:
        valor_inicial = st.session_state[state_key]
        st.session_state[ui_key] = conv(valor_inicial) if conv else valor_inicial
    valor = widget_fn(label, key=ui_key, **kwargs)
    st.session_state[state_key] = valor
    return valor


def sembrar(clave, valor):
    if clave not in st.session_state:
        st.session_state[clave] = valor


def reiniciar_widgets_planilla(prefijos=("ui_b_net_", "ui_c_")):
    for emp in st.session_state["empleados"].keys():
        for p in prefijos:
            st.session_state.pop(f"{p}{emp}", None)


def registrar_auditoria(tipo, destinatario):
    registro = {"Fecha": ahora_sv().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": tipo, "Destinatario": destinatario}
    st.session_state["historial_auditoria"].append(registro)
    _auditoria_a_sheets(registro)


# =====================================================================
# 5. LOGO E IMÁGENES (SVG con los colores del tema)
# =====================================================================
def _svg_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def logo_bytes():
    """Logo subido en Configuración; si no hay, el archivo logo.png del proyecto."""
    b64 = _texto(aj("logo_b64"))
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            pass
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as fh:
                return fh.read()
        except Exception:
            pass
    return None


def img_logo():
    contenido = logo_bytes()
    if contenido:
        return "data:image/png;base64," + base64.b64encode(contenido).decode("ascii")
    t = tema()
    letras = html.escape(_iniciales(aj("empresa_corto")))
    return _svg_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'>"
        f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='{t['p']}'/><stop offset='1' stop-color='{t['acc']}'/></linearGradient></defs>"
        "<rect width='48' height='48' rx='14' fill='url(#g)'/>"
        f"<text x='24' y='31' font-family='Arial, sans-serif' font-size='18' font-weight='800' fill='#FFFFFF' text-anchor='middle'>{letras}</text></svg>"
    )


def img_hero():
    t = tema()
    return _svg_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 340 220'><defs>"
        f"<linearGradient id='p' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#FFFFFF'/><stop offset='1' stop-color='{t['p50']}'/></linearGradient>"
        f"<linearGradient id='b' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{t['p400']}'/><stop offset='1' stop-color='{t['p']}'/></linearGradient>"
        f"<linearGradient id='l' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#34D399'/><stop offset='1' stop-color='{t['acc']}'/></linearGradient>"
        "<linearGradient id='c' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#FDE68A'/><stop offset='1' stop-color='#F59E0B'/></linearGradient></defs>"
        "<rect x='34' y='26' width='236' height='160' rx='18' fill='url(#p)'/>"
        f"<rect x='54' y='46' width='84' height='9' rx='4.5' fill='{t['p100']}'/><rect x='54' y='62' width='52' height='7' rx='3.5' fill='{t['p50']}'/>"
        "<rect x='60' y='132' width='18' height='36' rx='5' fill='url(#b)' opacity='.45'/><rect x='90' y='118' width='18' height='50' rx='5' fill='url(#b)' opacity='.6'/>"
        "<rect x='120' y='124' width='18' height='44' rx='5' fill='url(#b)' opacity='.5'/><rect x='150' y='100' width='18' height='68' rx='5' fill='url(#b)' opacity='.75'/>"
        "<rect x='180' y='92' width='18' height='76' rx='5' fill='url(#b)' opacity='.85'/><rect x='210' y='72' width='18' height='96' rx='5' fill='url(#b)'/>"
        "<polyline points='69,118 99,104 129,110 159,86 189,78 219,56' fill='none' stroke='url(#l)' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'/>"
        f"<circle cx='219' cy='56' r='7' fill='#FFFFFF' stroke='{t['acc']}' stroke-width='3'/><rect x='222' y='112' width='100' height='70' rx='14' fill='#FFFFFF'/>"
        f"<circle cx='252' cy='147' r='17' fill='none' stroke='{t['p100']}' stroke-width='7'/>"
        f"<circle cx='252' cy='147' r='17' fill='none' stroke='{t['p']}' stroke-width='7' stroke-dasharray='70 107' stroke-linecap='round' transform='rotate(-90 252 147)'/>"
        f"<rect x='278' y='136' width='32' height='7' rx='3.5' fill='{t['p100']}'/><rect x='278' y='150' width='22' height='7' rx='3.5' fill='{t['p50']}'/>"
        "<circle cx='40' cy='170' r='24' fill='url(#c)'/>"
        "<text x='40' y='179' font-family='Arial, sans-serif' font-size='24' font-weight='700' fill='#FFFFFF' text-anchor='middle'>$</text></svg>"
    )


def img_reporte():
    t = tema()
    return _svg_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 150'>"
        f"<defs><linearGradient id='u' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='{t['p400']}'/><stop offset='1' stop-color='{t['acc']}'/></linearGradient></defs>"
        "<ellipse cx='100' cy='136' rx='70' ry='8' fill='#E2E8F0'/>"
        f"<rect x='56' y='14' width='86' height='112' rx='12' fill='#FFFFFF' stroke='{t['p100']}' stroke-width='2'/>"
        f"<rect x='70' y='34' width='42' height='7' rx='3.5' fill='{t['p100']}'/><rect x='70' y='48' width='58' height='6' rx='3' fill='{t['p50']}'/>"
        f"<rect x='70' y='60' width='50' height='6' rx='3' fill='{t['p50']}'/><rect x='70' y='72' width='56' height='6' rx='3' fill='{t['p50']}'/>"
        "<rect x='70' y='90' width='30' height='16' rx='4' fill='#EF4444'/>"
        "<text x='85' y='101.5' font-family='Arial, sans-serif' font-size='9' font-weight='700' fill='#FFFFFF' text-anchor='middle'>PDF</text>"
        "<circle cx='146' cy='104' r='22' fill='url(#u)'/>"
        "<path d='M146 115v-20m-8 8l8-8 8 8' fill='none' stroke='#FFFFFF' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'/></svg>"
    )


def img_directorio():
    t = tema()
    return _svg_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 150'><ellipse cx='100' cy='136' rx='70' ry='8' fill='#E2E8F0'/>"
        f"<rect x='50' y='18' width='100' height='108' rx='14' fill='#FFFFFF' stroke='{t['p100']}' stroke-width='2'/>"
        f"<circle cx='100' cy='54' r='17' fill='{t['p50']}'/><circle cx='100' cy='49' r='7' fill='{t['p400']}'/><path d='M87 66c3-8 23-8 26 0' fill='{t['p400']}'/>"
        f"<rect x='70' y='84' width='60' height='7' rx='3.5' fill='{t['p100']}'/><rect x='78' y='98' width='44' height='6' rx='3' fill='{t['p50']}'/>"
        "<circle cx='150' cy='108' r='18' fill='#10B981'/>"
        "<path d='M141 108l6 6 12-12' fill='none' stroke='#FFFFFF' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'/></svg>"
    )


# =====================================================================
# 6. ESTILOS CSS (los colores del tema llegan como variables)
# =====================================================================
def css_tema():
    t = tema()
    return ("<style>:root{"
            f"--primary:{t['p']};--primary-400:{t['p400']};--primary-600:{t['p600']};--primary-50:{t['p50']};"
            f"--primary-100:{t['p100']};--accent:{t['acc']};--hero1:{t['h1']};--hero2:{t['h2']};--hero3:{t['h3']};--glow:{t['glow']};"
            "}</style>")


CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap');
:root { --bg: #F4F6FA; --surface: #FFFFFF; --ink: #0B1220; --ink-2: #334155; --muted: #64748B; --soft: #94A3B8; --line: #E5E9F0; --line-2: #EEF1F6; --radius: 16px;
  --shadow-sm: 0 1px 2px rgba(16,24,40,.04), 0 2px 8px rgba(16,24,40,.04); --shadow-md: 0 14px 34px rgba(16,24,40,.09), 0 3px 8px rgba(16,24,40,.04);
  --display: 'Plus Jakarta Sans', 'Inter', -apple-system, 'Segoe UI', sans-serif; }
.stApp { background: radial-gradient(1100px 520px at 100% -10%, rgba(var(--glow),.12), transparent 60%), radial-gradient(900px 500px at -15% 105%, rgba(var(--glow),.07), transparent 60%), var(--bg) !important; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stMarkdown { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important; }
#MainMenu, footer, [data-testid="stDecoration"], .stAppDeployButton { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding: 2.4rem 2.2rem 2.5rem 2.2rem !important; max-width: 1360px; }
h1, h2, h3, h4 { color: var(--ink) !important; letter-spacing: -0.02em; font-family: var(--display) !important; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* ---------- Menú lateral ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%) !important; border-right: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 12px; padding: 4px 6px 18px 6px; border-bottom: 1px solid var(--line-2); margin-bottom: 2px; }
.brand img { width: 46px; height: 46px; border-radius: 14px; object-fit: contain; background: #FFFFFF; box-shadow: 0 8px 18px rgba(15,23,42,.14); flex-shrink: 0; }
.brand-name { font-family: var(--display); font-weight: 800; font-size: 1.1rem; color: var(--ink); letter-spacing: -0.01em; line-height: 1.2; }
.brand-sub { font-size: .74rem; color: var(--muted); margin-top: 1px; }
.nav-sec { font-size: .64rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: var(--soft); margin: 18px 10px 6px 10px; }
[class*="st-key-nav_"] { gap: .15rem !important; }
[class*="st-key-nav_"] .stButton button {
  justify-content: flex-start !important; text-align: left !important; background: transparent !important; border: 1px solid transparent !important;
  box-shadow: none !important; color: var(--ink-2) !important; font-weight: 500 !important; padding: .55rem .8rem !important; border-radius: 11px !important;
  transform: none !important; min-height: 2.6rem; }
[class*="st-key-nav_"] .stButton button > div, [class*="st-key-nav_"] .stButton button p { justify-content: flex-start !important; text-align: left !important; }
[class*="st-key-nav_"] .stButton button:hover { background: var(--primary-50) !important; color: var(--primary-600) !important; transform: none !important; box-shadow: none !important; }
[class*="st-key-nav_"] .stButton button[kind="primary"], [class*="st-key-nav_"] .stButton button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(90deg, var(--primary-50), rgba(255,255,255,0)) !important; color: var(--primary-600) !important; font-weight: 700 !important;
  box-shadow: inset 3px 0 0 var(--primary) !important; filter: none !important; }
[class*="st-key-nav_"] .stButton button[kind="primary"] p, [class*="st-key-nav_"] .stButton button[data-testid="stBaseButton-primary"] p { color: var(--primary-600) !important; }
.side-card { background: #F8FAFC; border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; margin-top: 18px; font-size: .8rem; color: var(--ink-2); }
.side-title { font-size: .64rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--soft); margin-bottom: 6px; }
.side-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 4px 0; }
.side-row b { color: var(--ink); font-weight: 600; text-align: right; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.dot.on { background: #10B981; box-shadow: 0 0 0 3px rgba(16,185,129,.18); }
.dot.off { background: #F59E0B; box-shadow: 0 0 0 3px rgba(245,158,11,.18); }
.profile { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding: 10px 12px; border-radius: 14px; border: 1px solid var(--line); background: #FFFFFF; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--accent)); color: #FFFFFF; font-weight: 700; display: flex; align-items: center; justify-content: center; font-size: .78rem; flex-shrink: 0; }
.profile-name { font-weight: 700; color: var(--ink); font-size: .85rem; }
.profile-role { color: var(--muted); font-size: .74rem; }
.version { text-align: center; color: var(--soft); font-size: .7rem; margin-top: 14px; }

/* ---------- Encabezados ---------- */
.hero { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 30px 34px; border-radius: 22px; margin-bottom: 18px; background: radial-gradient(900px 260px at 85% -30%, rgba(var(--glow),.55), transparent 60%), linear-gradient(135deg, var(--hero1) 0%, var(--hero2) 45%, var(--hero3) 100%); box-shadow: 0 18px 40px rgba(15,23,42,.22); animation: fadeUp .5s ease both; }
.hero::after { content: ""; position: absolute; inset: 0; pointer-events: none; background-image: radial-gradient(rgba(255,255,255,.07) 1px, transparent 1px); background-size: 18px 18px; }
.hero-body { position: relative; z-index: 1; min-width: 0; }
.hero-kicker { font-size: .76rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: rgba(255,255,255,.72) !important; }
.hero-title { font-family: var(--display); font-size: 2.1rem; font-weight: 800; letter-spacing: -0.03em; margin-top: 6px; color: #FFFFFF !important; line-height: 1.15; }
.hero-sub { color: rgba(255,255,255,.8) !important; margin-top: 8px; font-size: .98rem; max-width: 600px; line-height: 1.5; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.hero-chip { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); color: #FFFFFF !important; padding: 6px 12px; border-radius: 999px; font-size: .8rem; font-weight: 600; }
.hero-img { width: 300px; max-width: 36%; flex-shrink: 0; position: relative; z-index: 1; filter: drop-shadow(0 14px 26px rgba(0,0,0,.28)); }
.page-head { display: flex; align-items: center; gap: 14px; margin: 0 0 18px 0; animation: fadeUp .4s ease both; }
.page-ico { width: 50px; height: 50px; border-radius: 15px; background: linear-gradient(135deg, var(--primary-50), var(--primary-100)); border: 1px solid var(--primary-100); display: flex; align-items: center; justify-content: center; font-size: 1.4rem; flex-shrink: 0; }
.page-kicker { font-size: .7rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--primary); }
.page-title { font-family: var(--display); font-size: 1.7rem; font-weight: 800; color: var(--ink); letter-spacing: -0.025em; line-height: 1.2; }
.page-sub { font-size: .92rem; color: var(--muted); margin-top: 3px; line-height: 1.45; }

/* ---------- Tarjetas ---------- */
[class*="st-key-card_"] { background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: var(--radius) !important; padding: 20px 22px !important; box-shadow: var(--shadow-sm) !important; transition: box-shadow .2s ease, border-color .2s ease; animation: fadeUp .45s ease both; }
[class*="st-key-card_"]:hover { box-shadow: var(--shadow-md) !important; border-color: #DCE1EA !important; }
.sec-title { font-family: var(--display); font-size: 1.04rem; font-weight: 700; color: var(--ink); letter-spacing: -0.01em; }
.sec-sub { font-size: .84rem; color: var(--muted); margin: 3px 0 8px 0; line-height: 1.45; }
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow-sm); transition: transform .2s ease, box-shadow .2s ease; min-height: 132px; display: flex; flex-direction: column; animation: fadeUp .45s ease both; }
.kpi:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
.kpi-top { display: flex; align-items: center; gap: 10px; }
.kpi-ico { width: 38px; height: 38px; border-radius: 11px; display: flex; align-items: center; justify-content: center; font-size: 1.05rem; flex-shrink: 0; }
.kpi-ico.indigo { background: var(--primary-50); } .kpi-ico.sky { background: #E0F2FE; } .kpi-ico.green { background: #ECFDF5; } .kpi-ico.amber { background: #FFFBEB; } .kpi-ico.red { background: #FEF2F2; } .kpi-ico.violet { background: #F5F3FF; }
.kpi-label { font-size: .72rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; line-height: 1.3; }
.kpi-value { font-family: var(--display); font-size: 1.75rem; font-weight: 800; color: var(--ink); letter-spacing: -0.03em; margin-top: 12px; font-variant-numeric: tabular-nums; line-height: 1.1; overflow-wrap: anywhere; }
.kpi-value.pos { color: #047857; } .kpi-value.neg { color: #B91C1C; } .kpi-value.prim { color: var(--primary-600); }
.kpi-note { font-size: .8rem; color: var(--muted); margin-top: auto; padding-top: 6px; line-height: 1.4; }
.bar { height: 6px; border-radius: 999px; background: #F1F5F9; overflow: hidden; margin-top: 8px; }
.bar span { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #F59E0B, #FBBF24); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px 0; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 999px; font-size: .78rem; font-weight: 600; background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0; line-height: 1.35; max-width: 100%; }
.chip.indigo { background: var(--primary-50); color: var(--primary-600); border-color: var(--primary-100); } .chip.green { background: #ECFDF5; color: #047857; border-color: #A7F3D0; } .chip.amber { background: #FFFBEB; color: #B45309; border-color: #FDE68A; } .chip.red { background: #FEF2F2; color: #B91C1C; border-color: #FECACA; } .chip.sky { background: #F0F9FF; color: #0369A1; border-color: #BAE6FD; } .chip.violet { background: #F5F3FF; color: #6D28D9; border-color: #DDD6FE; }
[class*="st-key-peligro"] .stButton button { background: linear-gradient(135deg, #DC2626 0%, #EF4444 100%) !important; color: #FFFFFF !important; border: none !important; box-shadow: 0 6px 16px rgba(220,38,38,.25) !important; }
[class*="st-key-peligro"] .stButton button p { color: #FFFFFF !important; }
[class*="st-key-peligro"] .stButton button:hover { filter: brightness(1.06); box-shadow: 0 10px 24px rgba(220,38,38,.34) !important; color: #FFFFFF !important; }
.confirmar-borrado { background: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; border-radius: 12px; padding: 12px 14px; font-size: .9rem; margin: 6px 0 8px 0; }
.empty { display: flex; align-items: center; gap: 30px; background: var(--surface); border: 1px solid var(--line); border-radius: 20px; padding: 28px 34px; box-shadow: var(--shadow-sm); animation: fadeUp .45s ease both; }
.empty img { width: 210px; flex-shrink: 0; }
.empty-title { font-family: var(--display); font-size: 1.25rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em; }
.empty-text { color: var(--muted); margin-top: 4px; }
.steps { margin-top: 14px; display: grid; gap: 9px; }
.step { display: flex; gap: 10px; align-items: center; font-size: .9rem; color: var(--ink-2); }
.step b { width: 24px; height: 24px; border-radius: 50%; background: var(--primary-50); color: var(--primary-600); display: flex; align-items: center; justify-content: center; font-size: .75rem; flex-shrink: 0; }
.footer { text-align: center; color: var(--soft); font-size: .76rem; margin-top: 36px; padding-top: 16px; border-top: 1px solid var(--line); }

/* ---------- Planilla ---------- */
.periodo { display: flex; align-items: center; gap: 16px; padding: 16px 18px; border-radius: 14px; background: linear-gradient(135deg, var(--primary-50), #FFFFFF 70%); border: 1px solid var(--primary-100); margin: 2px 0 4px 0; animation: fadeUp .4s ease both; }
.periodo-ico { width: 46px; height: 46px; border-radius: 12px; background: linear-gradient(135deg, var(--primary), var(--accent)); color: #FFFFFF; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; flex-shrink: 0; }
.periodo-t { font-family: var(--display); font-weight: 800; color: var(--ink); font-size: 1.12rem; letter-spacing: -0.01em; }
.periodo-s { color: var(--muted); font-size: .84rem; margin-top: 2px; line-height: 1.4; }
.periodo-q { margin-left: auto; text-align: right; flex-shrink: 0; }
.periodo-q b { font-family: var(--display); font-size: 1.95rem; color: var(--primary-600); display: block; line-height: 1; font-weight: 800; }
.periodo-q span { font-size: .66rem; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; font-weight: 700; }
.pago { background: var(--surface); border: 1px solid var(--line); border-radius: 18px; padding: 18px 18px 14px 18px; box-shadow: var(--shadow-sm); transition: transform .2s ease, box-shadow .2s ease; min-height: 270px; display: flex; flex-direction: column; animation: fadeUp .45s ease both; position: relative; overflow: hidden; margin-bottom: 14px; }
.pago::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 4px; background: linear-gradient(90deg, var(--primary), var(--accent)); }
.pago:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
.pago-top { display: flex; gap: 12px; align-items: center; }
.pago-av { width: 42px; height: 42px; border-radius: 12px; background: var(--primary-50); color: var(--primary-600); font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.pago-nom { font-weight: 700; color: var(--ink); line-height: 1.25; }
.pago-sub { font-size: .76rem; color: var(--muted); margin-top: 2px; }
.pago-total { font-family: var(--display); font-size: 1.95rem; font-weight: 800; color: var(--ink); letter-spacing: -0.03em; margin-top: 14px; font-variant-numeric: tabular-nums; line-height: 1.1; }
.pago-lbl { font-size: .68rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--primary-600); margin-top: 3px; }
.pago-lines { margin-top: 12px; border-top: 1px dashed var(--line); padding-top: 8px; }
.pl { display: flex; justify-content: space-between; gap: 10px; font-size: .84rem; color: var(--ink-2); padding: 3px 0; }
.pl b { font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 700; white-space: nowrap; }
.pl.info { color: var(--soft); font-size: .76rem; } .pl.info b { color: var(--soft); font-weight: 600; }
.pl.neg b { color: #B91C1C; } .pl.pos b { color: #047857; }
.neto { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: linear-gradient(135deg, #FFFFFF, var(--primary-50)); border: 1px solid var(--primary-100); border-radius: 12px; padding: 12px 16px; margin-top: 8px; }
.neto-label { font-size: .7rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--primary-600); }
.neto-formula { font-size: .8rem; color: var(--muted); font-variant-numeric: tabular-nums; margin-top: 2px; line-height: 1.45; }
.neto-valor { font-family: var(--display); font-size: 1.45rem; font-weight: 800; color: var(--primary-600); font-variant-numeric: tabular-nums; white-space: nowrap; }
table.sal { width: 100%; border-collapse: collapse; font-size: .88rem; margin-top: 6px; }
table.sal th { text-align: right; font-size: .68rem; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); padding: 6px 8px; border-bottom: 1px solid var(--line); }
table.sal td { padding: 8px; text-align: right; font-variant-numeric: tabular-nums; color: var(--ink); border-bottom: 1px solid var(--line-2); }
table.sal td:first-child, table.sal th:first-child { text-align: left; color: var(--ink-2); }
table.sal tr.neg td { color: #B91C1C; }
table.sal tr.tot td { font-weight: 800; color: var(--primary-600); background: var(--primary-50); border-bottom: none; }
.formula { background: #F8FAFC; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; font-size: .84rem; color: var(--ink-2); line-height: 1.7; }
.formula b { color: var(--primary-600); }
.swatches { display: flex; flex-wrap: wrap; gap: 10px; margin: 6px 0 10px 0; }
.sw { display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border: 1px solid var(--line); border-radius: 12px; background: #FFFFFF; font-size: .82rem; font-weight: 600; color: var(--ink-2); }
.sw i { width: 18px; height: 18px; border-radius: 6px; display: inline-block; }
.sw.on { border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-100); color: var(--primary-600); }

/* ---------- E-commerce ---------- */
.marca { background: var(--surface); border: 1px solid var(--line); border-radius: 18px; padding: 16px 18px 16px 22px; box-shadow: var(--shadow-sm); position: relative; overflow: hidden; min-height: 160px; display: flex; flex-direction: column; margin-bottom: 14px; animation: fadeUp .45s ease both; transition: transform .2s ease, box-shadow .2s ease; }
.marca:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
.marca::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--c); }
.marca-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.marca-nom { font-weight: 700; color: var(--ink); display: flex; align-items: center; gap: 8px; }
.marca-nom i { width: 10px; height: 10px; border-radius: 50%; background: var(--c); display: inline-block; }
.marca-pct { font-size: .74rem; font-weight: 700; padding: 3px 9px; border-radius: 999px; background: #F1F5F9; color: var(--ink-2); }
.marca-val { font-family: var(--display); font-size: 1.7rem; font-weight: 800; color: var(--ink); letter-spacing: -0.03em; margin-top: 10px; font-variant-numeric: tabular-nums; }
.marca-sub { font-size: .8rem; color: var(--muted); margin-top: 2px; }
.marca-bar { height: 6px; background: #F1F5F9; border-radius: 999px; margin-top: auto; overflow: hidden; }
.marca-bar span { display: block; height: 100%; background: var(--c); border-radius: 999px; }

/* ---------- Controles ---------- */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button { border-radius: 11px !important; font-weight: 600 !important; padding: .55rem 1.1rem !important; min-height: 2.6rem; border: 1px solid var(--line) !important; background: #FFFFFF !important; color: var(--ink) !important; box-shadow: var(--shadow-sm) !important; transition: all .18s ease !important; }
.stButton button:hover, .stDownloadButton button:hover, [data-testid="stFormSubmitButton"] button:hover { border-color: var(--primary-100) !important; color: var(--primary-600) !important; background: var(--primary-50) !important; transform: translateY(-1px); box-shadow: var(--shadow-md) !important; }
.stButton button:active, .stDownloadButton button:active { transform: scale(.98); }
.stButton button p, .stDownloadButton button p, [data-testid="stFormSubmitButton"] button p { color: inherit !important; font-weight: 600 !important; }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] { background: linear-gradient(135deg, var(--primary) 0%, var(--primary-400) 55%, var(--accent) 140%) !important; color: #FFFFFF !important; border: none !important; box-shadow: 0 6px 16px rgba(15,23,42,.18) !important; }
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover, [data-testid="stFormSubmitButton"] button[kind="primary"]:hover { filter: brightness(1.07); box-shadow: 0 10px 24px rgba(15,23,42,.24) !important; color: #FFFFFF !important; }
.stButton button:disabled, .stDownloadButton button:disabled { opacity: .45 !important; transform: none !important; box-shadow: none !important; }
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { border-radius: 11px !important; border-color: var(--line) !important; background: #FFFFFF !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within { border-color: var(--primary) !important; box-shadow: 0 0 0 3px var(--primary-100) !important; }
.stApp label p { color: var(--ink-2) !important; font-weight: 500 !important; font-size: .86rem !important; }
[data-testid="stFileUploaderDropzone"] { background: linear-gradient(180deg, #FFFFFF, var(--primary-50)) !important; border: 1.5px dashed var(--primary-100) !important; border-radius: 14px !important; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--primary) !important; }
[data-testid="stExpander"] { background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: var(--radius) !important; box-shadow: var(--shadow-sm) !important; }
[data-testid="stExpander"]:hover { box-shadow: var(--shadow-md) !important; }
[data-testid="stExpander"] details { border: none !important; }
[data-testid="stExpander"] summary p { font-weight: 600 !important; color: var(--ink) !important; }
[data-testid="stForm"] { border: none !important; padding: 0 !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
[data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); overflow-x: auto; scrollbar-width: none; }
[data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
[data-baseweb="tab"] { padding: 8px 14px !important; font-weight: 600 !important; white-space: nowrap; }
[data-baseweb="tab"][aria-selected="true"] p { color: var(--primary) !important; }
[data-baseweb="tab-highlight"] { background-color: var(--primary) !important; height: 3px !important; border-radius: 3px; }
[data-testid="stToast"] { border-radius: 14px !important; border: 1px solid var(--line) !important; box-shadow: 0 14px 34px rgba(16,24,40,.14) !important; background: #FFFFFF !important; }
[class*="st-key-navmovil"] { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 10px 12px; box-shadow: var(--shadow-sm); margin-bottom: 4px; }

/* ---------- Proveedores (CRM) ---------- */
.crm-head { display: flex; gap: 18px; align-items: center; }
.crm-avatar { width: 68px; height: 68px; border-radius: 18px; flex-shrink: 0; background: linear-gradient(135deg, var(--primary) 0%, var(--primary-400) 55%, var(--accent) 100%); color: #FFFFFF; font-family: var(--display); font-weight: 800; font-size: 1.45rem; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 20px rgba(15,23,42,.18); }
.crm-kicker { font-size: .68rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--soft); }
.crm-name { font-family: var(--display); font-size: 1.5rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em; line-height: 1.2; margin-top: 2px; overflow-wrap: anywhere; }
.crm-desc { color: var(--muted); font-size: .92rem; margin-top: 4px; }
.crm-section-title { display: flex; align-items: center; gap: 8px; font-size: .72rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #475569; margin: 4px 0 6px 0; padding-bottom: 10px; border-bottom: 1px solid #F1F5F9; }
.crm-section-title .sdot { width: 8px; height: 8px; border-radius: 50%; }
.crm-field { display: flex; gap: 12px; align-items: flex-start; padding: 9px 0; }
.crm-ico { width: 36px; height: 36px; border-radius: 10px; background: #F1F5F9; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; transition: background .2s ease, transform .2s ease; }
.crm-field:hover .crm-ico { background: var(--primary-100); transform: scale(1.06); }
.crm-label { font-size: .66rem; color: var(--soft); font-weight: 700; text-transform: uppercase; letter-spacing: .07em; }
.crm-value { font-size: .92rem; color: var(--ink); font-weight: 600; overflow-wrap: anywhere; margin-top: 1px; }
.crm-value.mono { font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.crm-value.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-value a { color: var(--primary); text-decoration: none; }
.crm-date { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px dashed #EEF2F7; }
.crm-date:last-child { border-bottom: none; }
.crm-date .l { display: flex; align-items: center; gap: 10px; font-size: .86rem; color: var(--ink-2); font-weight: 500; }
.crm-date .r { display: flex; align-items: center; gap: 8px; font-size: .86rem; color: var(--ink); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.crm-date .r.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-text { color: var(--ink-2); font-size: .92rem; line-height: 1.6; white-space: pre-wrap; }
.crm-text.empty { color: #CBD5E1; font-style: italic; }
.tips { display: grid; gap: 10px; margin-top: 6px; }
.tip { display: flex; gap: 10px; font-size: .86rem; color: var(--ink-2); line-height: 1.45; }
.tip span { flex-shrink: 0; }
.guia { font-size: .9rem; color: var(--ink-2); line-height: 1.65; }
.guia ol { padding-left: 1.2rem; margin: 6px 0; } .guia li { margin-bottom: 8px; } .guia b { color: var(--ink); }
.guia code { background: var(--primary-50); color: var(--primary-600); padding: 1px 6px; border-radius: 6px; font-size: .82rem; }

/* ---------- Teléfono y tablet ---------- */
@media (min-width: 769px) { [class*="st-key-navmovil"] { display: none !important; } }
@media (max-width: 1100px) { .hero-img { width: 230px; } .kpi-value { font-size: 1.5rem; } }
@media (max-width: 768px) {
  .block-container { padding: 3.6rem 1rem 2rem 1rem !important; }
  [data-testid="stHeader"] { background: rgba(244,246,250,.88) !important; backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); }
  .hero { flex-direction: column; align-items: flex-start; padding: 22px 20px; border-radius: 18px; }
  .hero-img { display: none; } .hero-title { font-size: 1.55rem; } .hero-sub { font-size: .9rem; }
  .page-head { gap: 12px; margin-bottom: 14px; } .page-ico { width: 42px; height: 42px; font-size: 1.2rem; border-radius: 12px; }
  .page-title { font-size: 1.35rem; } .page-sub { font-size: .85rem; }
  [class*="st-key-card_"] { padding: 16px !important; border-radius: 14px !important; }
  .kpi { min-height: 0; padding: 14px 16px; } .kpi-value { font-size: 1.45rem; margin-top: 8px; }
  .periodo { flex-wrap: wrap; gap: 12px; } .periodo-q { margin-left: 0; text-align: left; width: 100%; display: flex; align-items: baseline; gap: 8px; }
  .periodo-q b { display: inline; font-size: 1.6rem; }
  .neto { flex-wrap: wrap; } .neto-valor { font-size: 1.3rem; }
  .pago, .marca { min-height: 0; } .pago-total { font-size: 1.7rem; }
  .empty { flex-direction: column; text-align: center; padding: 22px 18px; gap: 14px; } .empty img { width: 150px; } .step { justify-content: flex-start; text-align: left; }
  .crm-head { gap: 12px; } .crm-avatar { width: 54px; height: 54px; font-size: 1.15rem; border-radius: 15px; } .crm-name { font-size: 1.2rem; }
  .crm-date .r { white-space: normal; text-align: right; }
  .stApp input, .stApp textarea { font-size: 16px !important; }
  .footer { margin-top: 24px; }
}
</style>
"""



# =====================================================================
# 7. COMPONENTES DE INTERFAZ
# =====================================================================
def md(contenido, destino=None):
    # '$' se escapa para que Streamlit no lo interprete como fórmula matemática.
    (destino or st).markdown(contenido.replace("$", "&#36;"), unsafe_allow_html=True)


def tarjeta(nombre):
    try:
        return st.container(key=f"card_{nombre}")
    except TypeError:
        return st.container(border=True)


def zona(clave):
    try:
        return st.container(key=clave)
    except TypeError:
        return st.container()


def encabezado_pagina(icono, titulo, subtitulo=""):
    md(f"<div class='page-head'><div class='page-ico'>{icono}</div><div><div class='page-kicker'>{html.escape(aj('empresa_corto'))} · Gerencia</div>"
       f"<div class='page-title'>{titulo}</div><div class='page-sub'>{subtitulo}</div></div></div>")


def titulo_seccion(titulo, sub=""):
    sub_html = f"<div class='sec-sub'>{sub}</div>" if sub else ""
    return f"<div class='sec-title'>{titulo}</div>{sub_html}"


def chip(texto, tono=""):
    return f"<span class='chip {tono}'>{texto}</span>"


def kpi_html(icono, etiqueta, valor, nota="", tono="indigo", valor_cls=""):
    return (f"<div class='kpi'><div class='kpi-top'><span class='kpi-ico {tono}'>{icono}</span><span class='kpi-label'>{etiqueta}</span></div>"
            f"<div class='kpi-value {valor_cls}'>{valor}</div><div class='kpi-note'>{nota}</div></div>")


def fila_kpis(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        md(item, col)


def estado_vacio(imagen, titulo, texto, pasos=()):
    pasos_html = ""
    if pasos:
        pasos_html = "<div class='steps'>" + "".join(f"<div class='step'><b>{i}</b>{p}</div>" for i, p in enumerate(pasos, 1)) + "</div>"
    md(f"<div class='empty'><img src='{imagen}' alt=''/><div><div class='empty-title'>{titulo}</div><div class='empty-text'>{texto}</div>{pasos_html}</div></div>")


def espacio(px_alto=10):
    md(f"<div style='height:{px_alto}px'></div>")


def pie_pagina():
    md(f"<div class='footer'>{html.escape(aj('empresa_nombre'))} · Suite administrativa · {ahora_sv().strftime('%d/%m/%Y')}</div>")


def tabla_sueldo_html(d):
    filas = [("Sueldo bruto", d["bruto_q"], d["bruto_m"], ""),
             (f"(−) Renta {aj('renta_pct'):g}%", d["renta_q"], d["renta_m"], "neg"),
             ("Neto a pagar", d["neto_q"], d["neto_m"], "tot")]
    cuerpo = "".join(f"<tr class='{c}'><td>{e}</td><td>{usd(q)}</td><td>{usd(m)}</td></tr>" for e, q, m, c in filas)
    return f"<table class='sal'><thead><tr><th></th><th>Quincenal</th><th>Mensual</th></tr></thead><tbody>{cuerpo}</tbody></table>"


# =====================================================================
# 8. MOTOR DE LECTURA DEL PDF
# =====================================================================
def _fila_norm(fila):
    return [_normalizar(c) for c in fila]


def _es_encabezado(fila_norm):
    tiene_prof = any(any(k in c for k in CLAVES_PROFESIONAL) for c in fila_norm)
    tiene_precio = any(any(k in c for k in CLAVES_PRECIO) for c in fila_norm)
    return tiene_prof and tiene_precio


def _ubicar_encabezado(tablas):
    for ti, tabla in enumerate(tablas):
        for fi, fila in enumerate(tabla):
            if _es_encabezado(_fila_norm(fila)):
                return ti, fi
    for ti, tabla in enumerate(tablas):
        for fi, fila in enumerate(tabla):
            if any("PROFESIONAL" in c for c in _fila_norm(fila)):
                return ti, fi
    return None


def _buscar_columna(columnas_tabla, claves, excluir=()):
    for clave in claves:
        for c in columnas_tabla:
            if clave in c and c not in excluir:
                return c
    return None


def _tablas_pagina(page, ajustes=None):
    try:
        tablas = page.extract_tables(ajustes) if ajustes else page.extract_tables()
    except Exception:
        return []
    salida = []
    for t in tablas or []:
        filas = [["" if c is None else str(c) for c in fila] for fila in (t or []) if fila and any(c not in (None, "") for c in fila)]
        if filas:
            salida.append(filas)
    return salida


def _filas_con_precio(tablas):
    pos = _ubicar_encabezado(tablas)
    if pos is None:
        return 0
    ti, fi = pos
    enc = _fila_norm(tablas[ti][fi])
    idx_precio = next((i for k in CLAVES_PRECIO for i, c in enumerate(enc) if k in c), None)
    if idx_precio is None:
        return 0
    total = 0
    for j, tabla in enumerate(tablas[ti:]):
        for fila in (tabla[fi + 1:] if j == 0 else tabla):
            if idx_precio < len(fila) and _a_numero(fila[idx_precio]) is not None:
                total += 1
    return total


def _resumenes_tablas(tablas):
    """Tablas de resumen que imprime el reporte (por e-commerce, por profesional y por servicio)."""
    res, actual = {}, None
    for tabla in tablas:
        if not tabla:
            continue
        if len(tabla[0]) > 4:
            actual = None
            continue
        encabezado = " ".join(_fila_norm(tabla[0]))
        inicio = 0
        if "CANTIDAD" in encabezado:
            if "COMER" in encabezado:
                actual = "ecomer"
            elif "PROFESIONAL" in encabezado:
                actual = "profesional"
            elif "SERVICIO" in encabezado:
                actual = "servicio"
            else:
                actual = None
            inicio = 1
            if actual:
                res[actual] = {"filas": [], "total": None}
        if actual is None:
            continue
        for fila in tabla[inicio:]:
            celdas = [_texto(c) for c in fila if _texto(c)]
            if len(celdas) < 3:
                continue
            nombre, cantidad, total = celdas[0], _a_numero(celdas[-2]), _a_numero(celdas[-1])
            if cantidad is None or total is None:
                continue
            if _normalizar(nombre).startswith("TOTAL"):
                res[actual]["total"] = {"cantidad": int(cantidad), "total": float(total)}
            else:
                res[actual]["filas"].append({"nombre": re.sub(r"\s+", " ", nombre), "cantidad": int(cantidad), "total": float(total)})
    return res


def _resumen_general(texto):
    """'RESUMEN INGRESO GENERAL': total neto, efectivo, transferencia, POS y total con recargo POS."""
    t = _normalizar(texto)
    i = t.find("RESUMEN INGRESO GENERAL")
    if i < 0:
        i = t.find("TOTAL NETO")
    if i < 0:
        return None
    j = t.find("RESUMEN POR", i + 5)
    segmento = t[i:(j if j > i else i + 800)]
    montos = [m for m in (_a_numero(x) for x in re.findall(r"\$\s?\d[\d,]*(?:\.\d+)?", segmento)) if m is not None]
    if len(montos) < 4:
        return None
    general = dict(zip(["total_neto", "efectivo", "transferencia", "pos", "total_con_pos"], montos))
    if abs(general["efectivo"] + general["transferencia"] + general["pos"] - general["total_neto"]) > 0.05:
        return None  # orden inesperado: mejor no comparar que comparar mal
    return general


@st.cache_data(show_spinner=False, max_entries=16)
def extraer_contenido_pdf(pdf_bytes):
    textos, tablas_lineas, tablas_texto = [], [], []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        n_paginas = len(pdf.pages)
        for page in pdf.pages:
            textos.append(page.extract_text() or "")
            tablas_lineas.extend(_tablas_pagina(page))
            tablas_texto.extend(_tablas_pagina(page, AJUSTES_TABLA_TEXTO))
    texto = "\n".join(textos)
    # Las tablas con bordes son las más confiables; la alineación de texto solo se usa si las primeras fallan.
    usar_texto = _filas_con_precio(tablas_lineas) == 0 and _filas_con_precio(tablas_texto) > 0
    resumen = _resumenes_tablas(tablas_lineas)
    resumen["general"] = _resumen_general(texto)
    return {"texto": texto, "tablas": tablas_texto if usar_texto else tablas_lineas, "paginas": n_paginas,
            "estrategia": "texto" if usar_texto else "lineas", "resumen": resumen}


def detectar_rango(texto):
    """Rango del encabezado del reporte, p. ej. 'Desde: 2026-09-01 | Hasta: 2026-09-15'."""
    m = RANGO_RE.search(_normalizar(texto))
    if m:
        f1, f2 = _parse_fecha_texto(m.group(1)), _parse_fecha_texto(m.group(2))
        if f1 and f2:
            return min(f1, f2), max(f1, f2)
    return None


def fechas_del_texto(texto):
    """Respaldo: fechas sueltas del documento, ignorando la fecha de impresión o de firma."""
    t = _normalizar(texto)
    fechas = []
    for m in re.finditer(PATRON_FECHA, t):
        contexto = t[max(0, m.start() - 30):m.start()]
        if re.search(r"GENERAD|IMPRES|EMISION|EMITID|CREAD|FIRMA|FECHA\s*:", contexto):
            continue
        f = _parse_fecha_texto(m.group(1))
        if f:
            fechas.append(f)
    return (min(fechas), max(fechas)) if len(fechas) >= 2 else None


def analizar_periodo(ini, fin, fuente):
    """1 al 15 → 1 quincena · 1 al 30/31 → mes (2 quincenas) · rangos mayores → quincenas equivalentes."""
    if fin < ini:
        ini, fin = fin, ini
    dias = (fin - ini).days + 1
    quincenas = 1 if dias <= 16 else 2 if dias <= 31 else max(2, int(round(dias / 15.2)))
    ultimo = calendar.monthrange(ini.year, ini.month)[1]
    mismo_mes = (ini.year, ini.month) == (fin.year, fin.month)
    mes = f"{MESES[ini.month - 1]} {ini.year}"
    if mismo_mes and ini.day == 1 and fin.day == ultimo:
        etiqueta = f"Mes completo de {mes}"
    elif mismo_mes and ini.day == 1 and fin.day == 15:
        etiqueta = f"1.ª quincena de {mes}"
    elif mismo_mes and ini.day == 16 and fin.day == ultimo:
        etiqueta = f"2.ª quincena de {mes}"
    elif quincenas == 1:
        etiqueta = f"Quincena del {ini.day} al {fin.day} de {mes}" if mismo_mes else "Período de una quincena"
    elif quincenas == 2:
        etiqueta = f"Período mensual ({dias} días)"
    else:
        etiqueta = f"Período de {quincenas} quincenas ({dias} días)"
    return {"inicio": ini.strftime("%d/%m/%Y"), "fin": fin.strftime("%d/%m/%Y"), "dias": dias,
            "quincenas": quincenas, "etiqueta": etiqueta, "fuente": fuente}


def marca_desde_texto(t):
    n = _normalizar(t)
    if not n:
        return ""
    if "PAPI" in n:
        return "Papi Spa"
    if "CLINIC" in n:
        return "Relájate Clinic"
    if "RELAJATE" in n:
        return "Relájate Man"
    if "GIO" in n or n.startswith("DR"):
        return "Dr. Gio Molina"
    return nombre_bonito(t)


def construir_reporte(texto, tablas, estrategia, mapeo):
    meta = {"estrategia": "Tablas con bordes" if estrategia == "lineas" else "Alineación de texto",
            "columnas": [], "filas_leidas": 0, "servicios": 0, "excluidas_total": 0, "sin_precio": 0,
            "sin_profesional": 0, "monto_sin_profesional": 0.0, "rellenadas": 0, "muestra_texto": texto[:1500]}
    if not texto.strip() and not tablas:
        return {"ok": False, "meta": meta, "error": "El PDF no tiene texto legible (parece escaneado como imagen). Expórtalo desde el sistema de ventas como PDF normal."}

    pos = _ubicar_encabezado(tablas)
    if pos is None:
        return {"ok": False, "meta": meta, "error": "No se encontró la tabla de servicios: falta un encabezado con las columnas PROFESIONAL y PRECIO."}
    ti, fi = pos

    cols = []
    for i, c in enumerate(tablas[ti][fi]):
        nombre = _normalizar(c) or f"COLUMNA {i + 1}"
        base, k = nombre, 2
        while nombre in cols:
            nombre = f"{base} ({k})"
            k += 1
        cols.append(nombre)
    ancho_tabla = len(cols)
    meta["columnas"] = cols

    filas, fin_tabla = [], False
    for j, tabla in enumerate(tablas[ti:]):
        if fin_tabla:
            break
        if j == 0:
            cuerpo = tabla[fi + 1:]
        elif not tabla or (estrategia == "lineas" and abs(len(tabla[0]) - ancho_tabla) > 1):
            continue  # tablas de resumen (por e-comer, por profesional...) u otras secciones
        else:
            cuerpo = tabla
        for fila in cuerpo:
            fila = list(fila)[:ancho_tabla] + [""] * max(0, ancho_tabla - len(fila))
            fn = _fila_norm(fila)
            if _es_encabezado(fn):
                continue  # encabezado repetido en cada página
            primera = next((c for c in fn if c), "")
            if PATRON_FIN_TABLA.match(primera):
                fin_tabla = True  # fila TOTALES o inicio de los resúmenes: la lista de servicios terminó
                break
            filas.append(fila)
    meta["filas_leidas"] = len(filas)
    if not filas:
        return {"ok": False, "meta": meta, "error": "Se encontró el encabezado, pero ninguna fila de servicios debajo."}

    df = pd.DataFrame(filas, columns=cols)

    def elegir(clave, claves, excluir=()):
        v = mapeo.get(clave)
        if v and v in cols:
            return v
        return _buscar_columna(cols, claves, excluir)

    c_prof = elegir("prof", CLAVES_PROFESIONAL)
    c_pre = elegir("precio", CLAVES_PRECIO, (c_prof,))
    c_cli = elegir("cliente", CLAVES_CLIENTE, (c_prof, c_pre))
    c_ser = elegir("servicio", CLAVES_SERVICIO, (c_prof, c_pre, c_cli))
    c_marca = elegir("marca", CLAVES_MARCA, (c_prof, c_pre, c_cli, c_ser))
    usadas = (c_prof, c_pre, c_cli, c_ser, c_marca)
    c_fecha = _buscar_columna(cols, CLAVES_FECHA, usadas)
    c_corr = _buscar_columna(cols, CLAVES_CORRELATIVO, usadas)
    c_efe = _buscar_columna(cols, CLAVES_EFECTIVO, usadas)
    c_tra = _buscar_columna(cols, CLAVES_TRANSFER, usadas)
    meta.update({"c_prof": c_prof, "c_pre": c_pre, "c_cli": c_cli, "c_ser": c_ser, "c_marca": c_marca,
                 "c_fecha": c_fecha, "c_corr": c_corr, "c_efe": c_efe, "c_tra": c_tra})
    if not c_prof or not c_pre:
        return {"ok": False, "meta": meta, "error": "No se pudo identificar la columna del profesional o la del precio. Elígelas en el diagnóstico."}

    df["_PROF"] = df[c_prof].map(_texto)
    df["_PRECIO"] = df[c_pre].map(_a_numero)
    prof_norm = df["_PROF"].map(_normalizar)
    encabezado_repetido = prof_norm.str.contains("PROFESIONAL", na=False) | (prof_norm == c_prof)

    es_total = pd.Series(False, index=df.index)
    for c in [c for c in dict.fromkeys([c_prof, c_cli, cols[0]]) if c]:
        es_total = es_total | df[c].map(lambda v: bool(PATRON_TOTAL.match(_normalizar(v))))
    meta["excluidas_total"] = int((es_total & ~encabezado_repetido).sum())
    df = df[~encabezado_repetido & ~es_total].copy()

    if mapeo.get("ffill", True):
        ultimo, nuevos, rellenadas = "", [], 0
        for prof, precio in zip(df["_PROF"], df["_PRECIO"]):
            if prof:
                ultimo = prof
            elif pd.notna(precio) and ultimo:
                prof = ultimo
                rellenadas += 1
            nuevos.append(prof)
        df["_PROF"] = nuevos
        meta["rellenadas"] = rellenadas

    sin_precio = df["_PRECIO"].isna()
    sin_prof = df["_PROF"] == ""
    meta["sin_precio"] = int((sin_precio & ~sin_prof).sum())
    meta["sin_profesional"] = int((sin_prof & ~sin_precio).sum())
    meta["monto_sin_profesional"] = float(df.loc[sin_prof & ~sin_precio, "_PRECIO"].sum())
    df = df[~sin_precio & ~sin_prof].copy()
    if df.empty:
        return {"ok": False, "meta": meta, "error": f"Ninguna fila tiene un precio legible en la columna «{c_pre}». Elige la columna correcta en el diagnóstico."}

    df[c_prof] = df["_PROF"]
    df[c_pre] = df["_PRECIO"].astype(float)
    df["_PROF_N"] = df["_PROF"].map(_normalizar)

    # Formas de pago: el POS se calcula como precio − efectivo − transferencia (la columna POS sale cortada en el PDF)
    pagos = bool(c_efe and c_tra)
    if pagos:
        df["_EFE"] = df[c_efe].map(_a_numero).fillna(0.0).astype(float)
        df["_TRA"] = df[c_tra].map(_a_numero).fillna(0.0).astype(float)
        df["_POS"] = (df[c_pre] - df["_EFE"] - df["_TRA"]).clip(lower=0.0).round(2)

    meta["servicios"] = int(len(df))
    return {"ok": True, "df": df, "meta": meta, "c_prof": c_prof, "c_pre": c_pre, "c_cli": c_cli, "c_ser": c_ser,
            "c_marca": c_marca, "c_fecha": c_fecha, "c_corr": c_corr, "pagos": pagos,
            "rango": detectar_rango(texto), "fechas_texto": fechas_del_texto(texto)}


def aplicar_reporte(rep, quincenas_manual=None):
    ss = st.session_state
    df_reporte = rep["df"]
    c_prof, c_pre, c_cli, c_ser = rep["c_prof"], rep["c_pre"], rep["c_cli"], rep["c_ser"]
    c_marca, c_fecha, c_corr = rep["c_marca"], rep["c_fecha"], rep["c_corr"]
    meta = rep["meta"]

    # --- Fecha de cada servicio (columna FECHA o el correlativo AAAAMMDD-NNN) ---
    fechas_col = None
    if c_fecha:
        fechas_col = pd.to_datetime(df_reporte[c_fecha].map(_fecha_de_celda), errors="coerce")
    elif c_corr:
        fechas_col = pd.to_datetime(df_reporte[c_corr].map(_fecha_de_correlativo), errors="coerce")

    # --- Período del reporte → quincenas a pagar ---
    if rep["rango"]:
        ini, fin = rep["rango"]
        fuente = "encabezado del reporte (Desde / Hasta)"
    elif fechas_col is not None and fechas_col.notna().any():
        ini, fin = fechas_col.min().to_pydatetime(), fechas_col.max().to_pydatetime()
        fuente = "fechas de los servicios"
    elif rep["fechas_texto"]:
        ini, fin = rep["fechas_texto"]
        fuente = "fechas encontradas en el documento"
    else:
        ini = fin = fuente = None
    if fuente:
        info_p = analizar_periodo(ini, fin, fuente)
        factor = float(info_p["quincenas"])
        texto_periodo = f"{info_p['etiqueta']} (del {info_p['inicio']} al {info_p['fin']})"
    else:
        info_p, factor, texto_periodo = None, 1.0, "1 Quincena (el reporte no trae fechas)"
    meta["periodo_fuente"] = fuente or "sin fechas: se asume 1 quincena"
    if quincenas_manual:
        factor = float(quincenas_manual)
        texto_periodo += f" · {factor:g} quincena(s) por ajuste manual"
    ss["quincenas_multiplicador"] = factor
    ss["periodo_texto"] = texto_periodo
    ss["periodo_info"] = info_p

    # --- Ingresos y e-commerce (la columna ECOMER del reporte manda; si no existe, se deduce del profesional) ---
    ss["total_ingresos_pdf"] = float(df_reporte[c_pre].sum())

    def asignar_marca(p):
        p = _normalizar(p)
        if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
        if "LUIS" in p: return "Relájate Man"
        if "GIO" in p or "MARVIN" in p: return "Dr. Gio Molina"
        return "Relájate Clinic"

    if c_marca:
        marcas_pdf = df_reporte[c_marca].map(marca_desde_texto)
        df_reporte['MARCA'] = [m if m else asignar_marca(p) for m, p in zip(marcas_pdf, df_reporte[c_prof])]
    else:
        df_reporte['MARCA'] = df_reporte[c_prof].apply(asignar_marca)
    umbral, pauta = umbral_extra(), tasa_pauta()
    ss["ingresos_por_marca"] = {k: float(v) for k, v in df_reporte.groupby('MARCA')[c_pre].sum().to_dict().items()}
    df_reporte['EXTRA'] = df_reporte.apply(lambda r: 0.0 if r['MARCA'] == "Dr. Gio Molina" else max(0.0, float(r[c_pre]) - umbral), axis=1)
    ss["extras_por_marca"] = {k: float(v) for k, v in df_reporte.groupby('MARCA')['EXTRA'].sum().to_dict().items()}

    # --- Cálculo por colaborador ---
    df_reporte["_COLAB"] = ""
    df_reporte["_N_COINC"] = 0
    lista_ex, resumen, indices_por_colab = [], {}, {}
    for emp, info in ss["empleados"].items():
        mod = info.get("mod", "Fijo")
        ss[f"com_{emp}"] = 0.0
        ss[f"extra_bruto_{emp}"] = 0.0
        ss[f"ret_pub_{emp}"] = 0.0
        ss[f"base_net_{emp}"] = base_neta_periodo(info)  # sueldo neto quincenal × quincenas del período

        patron = patron_alias(alias_efectivo(emp, info))
        mascara = df_reporte["_PROF_N"].map(lambda n: coincide_alias(n, patron)).astype(bool)
        df_reporte.loc[mascara, "_N_COINC"] += 1
        df_reporte.loc[mascara & (df_reporte["_COLAB"] == ""), "_COLAB"] = emp
        df_p = df_reporte[mascara]
        indices_por_colab[emp] = [i for i, m in enumerate(mascara.tolist()) if m]
        tot_s = float(df_p[c_pre].sum())
        ss[f"serv_tot_{emp}"] = tot_s

        n_extra = 0
        if info.get("rol", "") == "Operativo":
            if "Estándar" in mod:
                df_ex = df_p[df_p[c_pre] > umbral]
                ex_tot = 0.0; ret_tot = 0.0
                for _, rx in df_ex.iterrows():
                    pr = float(rx[c_pre]); ex = pr - umbral; ret = ex * pauta; com = ex - ret
                    ex_tot += ex; ret_tot += ret
                    lista_ex.append({"Colaborador": emp, "Cliente": _texto(rx[c_cli]) if c_cli else "N/A", "Servicio": _texto(rx[c_ser]) if c_ser else "N/A",
                                     "Precio Final": pr, "Extra Generado": ex, "Retención pauta": ret, "Comisión Neta": com})
                n_extra = int(len(df_ex))
                ss[f"extra_bruto_{emp}"] = ex_tot
                ss[f"ret_pub_{emp}"] = ret_tot
                ss[f"com_{emp}"] = max(0.0, ex_tot - ret_tot)
            else:
                ss[f"com_{emp}"] = tot_s * (float(info.get("porc", 20) or 0) / 100.0)
        resumen[emp] = {"Alias buscado": patron or "—", "Servicios": int(mascara.sum()), "Ventas": tot_s, "Servicios con extra": n_extra}

    ss["detalle_extras"] = lista_ex
    ss["resumen_pdf"] = resumen
    ss["indices_por_colab"] = indices_por_colab

    sin_asignar = df_reporte[df_reporte["_COLAB"] == ""]
    meta["sin_asignar"] = [{"Profesional en el PDF": k, "Servicios": int(len(g)), "Ventas": float(g[c_pre].sum())} for k, g in sin_asignar.groupby("_PROF")]
    meta["multiples"] = int((df_reporte["_N_COINC"] > 1).sum())

    vacio = pd.Series("", index=df_reporte.index)
    datos = {
        "Profesional": df_reporte[c_prof].values,
        "Colaborador": df_reporte["_COLAB"].replace("", "Sin asignar").values,
        "Marca": df_reporte["MARCA"].values,
        "Precio": df_reporte[c_pre].astype(float).values,
        "Extra": df_reporte["EXTRA"].astype(float).values,
        "Servicio": (df_reporte[c_ser].map(_texto) if c_ser else vacio).values,
        "Cliente": (df_reporte[c_cli].map(_texto) if c_cli else vacio).values,
        "Fecha": (fechas_col if fechas_col is not None else pd.Series(pd.NaT, index=df_reporte.index)).values,
    }
    if rep.get("pagos"):
        datos.update({"Efectivo": df_reporte["_EFE"].values, "Transferencia": df_reporte["_TRA"].values, "POS": df_reporte["_POS"].values})
    ss["reporte_df"] = pd.DataFrame(datos)
    ss["pagos_ok"] = bool(rep.get("pagos"))


def mapeo_actual():
    ss = st.session_state

    def valor(clave):
        v = ss.get(clave)
        return None if v in (None, AUTO) else v

    return {"prof": valor("map_prof"), "precio": valor("map_precio"), "cliente": valor("map_cliente"),
            "servicio": valor("map_servicio"), "marca": valor("map_marca"), "quincenas": ss.get("quincenas_manual"),
            "ffill": bool(ss.get("map_ffill", True))}


def _reiniciar_datos_pdf():
    ss = st.session_state
    ss["total_ingresos_pdf"] = 0.0
    ss["detalle_extras"] = []
    ss["ingresos_por_marca"] = {}
    ss["extras_por_marca"] = {}
    ss["reporte_df"] = None
    ss["resumen_pdf"] = {}
    ss["indices_por_colab"] = {}
    ss["pdf_resumen"] = {}
    ss["pagos_ok"] = False
    for emp in ss["empleados"].keys():
        ss[f"com_{emp}"] = 0.0
        ss[f"extra_bruto_{emp}"] = 0.0
        ss[f"ret_pub_{emp}"] = 0.0
        ss[f"serv_tot_{emp}"] = 0.0


def ejecutar_procesamiento():
    ss = st.session_state
    pdf_bytes = ss.get("pdf_bytes")
    if not pdf_bytes:
        return False, "No hay ningún reporte cargado."
    resumen_pdf = {}
    try:
        datos = extraer_contenido_pdf(pdf_bytes)
        mapeo = mapeo_actual()
        rep = construir_reporte(datos["texto"], datos["tablas"], datos["estrategia"], mapeo)
        rep["meta"]["paginas"] = datos["paginas"]
        resumen_pdf = datos.get("resumen") or {}
        if rep["ok"]:
            aplicar_reporte(rep, mapeo.get("quincenas"))
    except Exception as e:
        rep = {"ok": False, "meta": {}, "error": f"Error inesperado leyendo el PDF: {e}"}
    if not rep["ok"]:
        _reiniciar_datos_pdf()
        ss["pdf_meta"], ss["pdf_ok"], ss["pdf_error"] = rep["meta"], False, rep["error"]
        reiniciar_widgets_planilla()
        return False, rep["error"]
    ss["pdf_meta"], ss["pdf_ok"], ss["pdf_error"] = rep["meta"], True, ""
    ss["pdf_resumen"] = resumen_pdf
    reiniciar_widgets_planilla()
    return True, f"Reporte leído: {rep['meta']['servicios']} servicios · {ss['periodo_texto']}"


def reprocesar_pdf():
    ok, msg = ejecutar_procesamiento()
    notificar(msg, "🔄" if ok else "⚠️")


def cambiar_quincenas():
    v = st.session_state.get("map_quincenas")
    st.session_state["quincenas_manual"] = None if v in (None, AUTO) else float(v)
    reprocesar_pdf()


def recalcular_todo():
    if st.session_state.get("pdf_bytes"):
        ejecutar_procesamiento()
    else:
        recalcular_bases()
        reiniciar_widgets_planilla()


def limpiar_reporte_pdf():
    ss = st.session_state
    _reiniciar_datos_pdf()
    ss["quincenas_multiplicador"] = 1.0
    ss["periodo_texto"] = "1 Quincena (Por defecto)"
    ss["periodo_info"] = None
    recalcular_bases()
    ss["pdf_hash"], ss["pdf_nombre"], ss["pdf_bytes"] = None, "", None
    ss["pdf_ok"], ss["pdf_error"], ss["pdf_meta"] = False, "", {}
    ss["quincenas_manual"] = None
    for k in CLAVES_MAPEO:
        ss.pop(k, None)
    ss["uploader_nonce"] += 1
    reiniciar_widgets_planilla()
    notificar("Reporte limpiado. La planilla volvió a los valores base.", "🧹")


# =====================================================================
# 9. PLANILLA Y VERIFICACIÓN CONTRA EL PDF
# =====================================================================
def calcular_fila_planilla(emp, info):
    ss = st.session_state
    neto_base = float(ss.get(f"base_net_{emp}", 0.0) or 0.0)
    bruto_base = round(neto_base / factor_neto(), 2) if neto_base > 0 else 0.0
    com = float(ss.get(f"com_{emp}", 0.0) or 0.0)
    bonos = float(ss.get(f"hex_{emp}", 0.0) or 0.0)
    desc = float(ss.get(f"desc_{emp}", 0.0) or 0.0)
    renta_calculada = 0.0 if "Porcentaje" in info.get("mod", "") and info.get("rol", "") == "Operativo" else round(bruto_base * tasa_renta(), 2)
    t_net = round(bruto_base + com + bonos - renta_calculada - desc, 2)
    return {
        "Colaborador": emp, "Rol": info.get("rol", ""), "Modalidad": forma_pago_texto(info),
        "Servicios": int(ss.get("resumen_pdf", {}).get(emp, {}).get("Servicios", 0)),
        "Ventas PDF": float(ss.get(f"serv_tot_{emp}", 0.0) or 0.0),
        "Base Bruta": bruto_base, "Base Neta": neto_base,
        "Extra": float(ss.get(f"extra_bruto_{emp}", 0.0) or 0.0),
        "Ret Pub": float(ss.get(f"ret_pub_{emp}", 0.0) or 0.0),
        "Com Neta": com, "Bonos": bonos, "Desc": desc, "Renta": renta_calculada, "Total": t_net,
        "Notas": ss.get(f"notas_{emp}", "Ninguno"), "Email": correo_de(emp),
        "DUI": info.get("dui", ""), "Cuenta": info.get("cuenta", ""),
    }


def calcular_planilla():
    return [calcular_fila_planilla(emp, info) for emp, info in st.session_state["empleados"].items()]


def servicios_colaborador(emp, info):
    ss = st.session_state
    rep = ss.get("reporte_df")
    indices = ss.get("indices_por_colab", {}).get(emp)
    if rep is None or not indices:
        return None
    d = rep.iloc[indices]
    umbral, pauta = umbral_extra(), tasa_pauta()
    extra = (d["Precio"] - umbral).clip(lower=0.0)
    base = {
        "Fecha": d["Fecha"].dt.strftime("%d/%m/%Y").fillna("—"),
        "E-commerce": d["Marca"],
        "Cliente": d["Cliente"].replace("", "—"),
        "Servicio": d["Servicio"].replace("", "—"),
        "Precio": d["Precio"].astype(float),
    }
    if info.get("rol", "") == "Operativo" and "Estándar" in info.get("mod", ""):
        base.update({"Extra bruto": extra.astype(float), "Retención pauta": (extra * pauta).astype(float), "Comisión neta": (extra - extra * pauta).astype(float)})
    elif info.get("rol", "") == "Operativo" and float(info.get("porc", 0) or 0) > 0:
        base["Comisión neta"] = (d["Precio"] * (float(info.get("porc", 20) or 0) / 100.0)).astype(float)
    return pd.DataFrame(base).reset_index(drop=True)


def tarjeta_pago_html(f, info):
    ss = st.session_state
    q = ss["quincenas_multiplicador"]
    mod = info.get("mod", MOD_FIJO)
    sub = f"{forma_pago_texto(info)} · {f['Servicios']} servicio(s)" if ss.get("pdf_ok") else f"{forma_pago_texto(info)} · {info.get('rol', '')}"
    lineas = []
    if "Porcentaje" in mod:
        lineas.append((f"Comisión {float(info.get('porc', 0) or 0):g}% de {usd(f['Ventas PDF'])}", usd(f["Com Neta"]), "pos"))
    else:
        lineas.append((f"Sueldo neto ({q:g} quincena{'s' if q != 1 else ''})", usd(f["Base Neta"]), ""))
        if "Estándar" in mod and info.get("rol") == "Operativo":
            lineas.append(("Comisión por extras", usd(f["Com Neta"]), "pos"))
        elif f["Com Neta"]:
            lineas.append(("Comisión", usd(f["Com Neta"]), "pos"))
    if f["Bonos"]:
        lineas.append(("Bonos", "+" + usd(f["Bonos"]), "pos"))
    if f["Desc"]:
        lineas.append(("Descuentos", "−" + usd(f["Desc"]), "neg"))
    if f["Extra"]:
        lineas.append((f"Extra bruto {usd(f['Extra'])} − {aj('retencion_pub_pct'):g}% pauta", "−" + usd(f["Ret Pub"]), "info"))
    if f["Renta"]:
        lineas.append((f"Renta {aj('renta_pct'):g}% sobre bruto {usd(f['Base Bruta'])}", usd(f["Renta"]), "info"))
    lineas_html = "".join(f"<div class='pl {cls}'><span>{etq}</span><b>{val}</b></div>" for etq, val, cls in lineas)
    return (f"<div class='pago'><div class='pago-top'><div class='pago-av'>{html.escape(_iniciales(f['Colaborador']))}</div>"
            f"<div><div class='pago-nom'>{html.escape(f['Colaborador'])}</div><div class='pago-sub'>{html.escape(sub)}</div></div></div>"
            f"<div class='pago-total'>{usd(f['Total'])}</div><div class='pago-lbl'>Total a pagar</div>"
            f"<div class='pago-lines'>{lineas_html}</div></div>")


def calcular_cuadre():
    """Compara lo que suma la app con los totales que imprime el propio PDF."""
    ss = st.session_state
    rep = ss.get("reporte_df")
    res = ss.get("pdf_resumen") or {}
    if rep is None or rep.empty:
        return None
    filas = []

    def agregar(grupo, concepto, app, pdf, tipo="dinero"):
        if pdf is None:
            return
        app, pdf = float(app), float(pdf)
        dif = round(app - pdf, 2)
        ok = abs(dif) < 0.015 if tipo == "dinero" else int(round(app)) == int(round(pdf))
        filas.append({"grupo": grupo, "concepto": concepto, "app": app, "pdf": pdf, "dif": dif, "tipo": tipo, "ok": ok})

    gen = res.get("general") or {}
    agregar("General", "Total de ventas", rep["Precio"].sum(), gen.get("total_neto"))
    total_resumen = (res.get("ecomer") or {}).get("total") or (res.get("profesional") or {}).get("total") or {}
    agregar("General", "Cantidad de servicios", len(rep), total_resumen.get("cantidad"), "cantidad")
    if ss.get("pagos_ok") and gen:
        agregar("Formas de pago", "Efectivo", rep["Efectivo"].sum(), gen.get("efectivo"))
        agregar("Formas de pago", "Transferencia", rep["Transferencia"].sum(), gen.get("transferencia"))
        agregar("Formas de pago", "POS (tarjeta)", rep["POS"].sum(), gen.get("pos"))
    for f in (res.get("ecomer") or {}).get("filas", []):
        marca = marca_desde_texto(f["nombre"]) or f["nombre"]
        sub = rep[rep["Marca"] == marca]
        agregar("E-commerce", f"{marca} · ventas", sub["Precio"].sum(), f["total"])
        agregar("E-commerce", f"{marca} · servicios", len(sub), f["cantidad"], "cantidad")
    claves_prof = rep["Profesional"].map(_clave_nombre)
    for f in (res.get("profesional") or {}).get("filas", []):
        sub = rep[claves_prof == _clave_nombre(f["nombre"])]
        nombre = nombre_bonito(f["nombre"])
        agregar("Profesional", f"{nombre} · ventas", sub["Precio"].sum(), f["total"])
        agregar("Profesional", f"{nombre} · servicios", len(sub), f["cantidad"], "cantidad")
    recargo = None
    if gen.get("total_con_pos") is not None and gen.get("total_neto") is not None:
        recargo = round(gen["total_con_pos"] - gen["total_neto"], 2)
    return {"filas": filas, "ok": sum(1 for f in filas if f["ok"]), "total": len(filas), "recargo_pos": recargo}


def render_cuadre(expandido=False):
    c = calcular_cuadre()
    if not c:
        return
    if not c["total"]:
        md("<div class='chips'>" + chip("ℹ️ Este PDF no trae resúmenes para comparar; se usan solo los servicios leídos.") + "</div>")
        return
    if c["ok"] == c["total"]:
        estado = chip(f"✅ Todo cuadra con el PDF · {c['ok']} de {c['total']} verificaciones", "green")
    else:
        estado = chip(f"⚠️ {c['total'] - c['ok']} diferencia(s) con el PDF · revisa el detalle", "amber")
    extra = chip(f"💳 Recargo POS según el PDF: {usd(c['recargo_pos'])}", "sky") if c["recargo_pos"] else ""
    md(f"<div class='chips'>{estado}{extra}</div>")
    with st.expander("🔎 Verificación detallada contra el PDF", expanded=expandido):
        def formato(valor, tipo):
            return usd(valor) if tipo == "dinero" else f"{int(round(valor))}"

        tabla = pd.DataFrame([{
            "Grupo": f["grupo"], "Concepto": f["concepto"],
            "Según la app": formato(f["app"], f["tipo"]), "Según el PDF": formato(f["pdf"], f["tipo"]),
            "Diferencia": "" if f["ok"] else (usd(f["dif"]) if f["tipo"] == "dinero" else f"{int(round(f['dif'])):+d}"),
            "Estado": "✅ Cuadra" if f["ok"] else "⚠️ Revisar",
        } for f in c["filas"]])
        st.dataframe(tabla, hide_index=True, **ancho(st.dataframe))
        st.caption("La app suma cada servicio leído y lo compara con los totales que imprime el propio reporte. Si algo no cuadra, revisa el diagnóstico de lectura.")



# =====================================================================
# 10. GRÁFICOS
# =====================================================================
def estilo_plotly(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, sans-serif", color="#334155", size=13),
                      hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E2E8F0", font=dict(family="Inter, sans-serif", color="#0B1220", size=13)),
                      legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5, title=None, font=dict(color="#334155")))
    try:
        fig.update_layout(barcornerradius=5)
    except ValueError:
        pass
    return fig


def _ejes_dinero_h(fig):
    fig.update_xaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(color="#0B1220"))


def marcas_ordenadas(dic):
    return [m for m in ORDEN_MARCAS if m in dic] + [m for m in dic if m not in ORDEN_MARCAS]


def grafico_donut_marcas(ingresos_marca):
    marcas = [m for m in marcas_ordenadas(ingresos_marca) if ingresos_marca.get(m, 0) > 0]
    valores = [float(ingresos_marca[m]) for m in marcas]
    fig = go.Figure(go.Pie(labels=marcas, values=valores, hole=0.66, sort=False, direction="clockwise",
                           marker=dict(colors=[COLORES_MARCA.get(m, "#94A3B8") for m in marcas], line=dict(color="#FFFFFF", width=2)),
                           textinfo="percent", textposition="outside", textfont=dict(color="#334155", size=12),
                           hovertemplate="<b>%{label}</b><br>$%{value:,.2f} · %{percent}<extra></extra>"))
    fig.add_annotation(text=f"<span style='font-size:12px;color:#64748B'>TOTAL</span><br><b style='font-size:22px;color:#0B1220'>${sum(valores):,.0f}</b>", showarrow=False, x=0.5, y=0.5)
    return estilo_plotly(fig, 360)


def grafico_barras_marcas(ingresos_marca, extras_marca):
    marcas = marcas_ordenadas(ingresos_marca)
    filas = [{"Marca": m, "Concepto": "Ingresos", "Monto": float(ingresos_marca.get(m, 0.0))} for m in marcas]
    filas += [{"Marca": m, "Concepto": "Extras", "Monto": float(extras_marca.get(m, 0.0))} for m in marcas]
    fig = px.bar(pd.DataFrame(filas), y="Marca", x="Monto", color="Concepto", barmode="group", orientation="h",
                 color_discrete_map={"Ingresos": "#2a78d6", "Extras": "#eb6834"}, category_orders={"Marca": marcas, "Concepto": ["Ingresos", "Extras"]})
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{fullData.name}: $%{x:,.2f}<extra></extra>", marker_line_width=0, texttemplate="$%{x:,.0f}",
                      textposition="outside", textfont=dict(color="#334155", size=11), cliponaxis=False)
    fig.update_layout(bargap=0.28, bargroupgap=0.08)
    _ejes_dinero_h(fig)
    fig.update_yaxes(autorange="reversed")
    return estilo_plotly(fig, max(300, 92 * len(marcas) + 80))


def grafico_colaboradores(ventas):
    df = pd.DataFrame([{"Colaborador": k, "Ventas": float(v)} for k, v in ventas.items() if v > 0]).sort_values("Ventas")
    fig = px.bar(df, x="Ventas", y="Colaborador", orientation="h")
    fig.update_traces(marker_color=tema()["p"], marker_line_width=0, texttemplate="$%{x:,.0f}", textposition="outside", textfont=dict(color="#334155"),
                      cliponaxis=False, hovertemplate="<b>%{y}</b><br>Servicios: $%{x:,.2f}<extra></extra>")
    fig.update_layout(bargap=0.38, showlegend=False)
    _ejes_dinero_h(fig)
    return estilo_plotly(fig, max(260, 50 * len(df) + 60))


def grafico_top_servicios(df, color=None):
    d = df[df["Servicio"].str.strip() != ""]
    top = (d.groupby("Servicio").agg(Ingresos=("Precio", "sum"), Cantidad=("Precio", "size")).sort_values("Ingresos", ascending=False).head(8).sort_values("Ingresos").reset_index())
    top["Etiqueta"] = top["Servicio"].map(lambda s: s if len(s) <= 28 else s[:27] + "…")
    fig = px.bar(top, x="Ingresos", y="Etiqueta", orientation="h", custom_data=["Servicio", "Cantidad"])
    fig.update_traces(marker_color=color or tema()["p"], marker_line_width=0, texttemplate="$%{x:,.0f}", textposition="outside", textfont=dict(color="#334155"),
                      cliponaxis=False, hovertemplate="<b>%{customdata[0]}</b><br>Ingresos: $%{x:,.2f}<br>Servicios: %{customdata[1]}<extra></extra>")
    fig.update_layout(bargap=0.38, showlegend=False)
    _ejes_dinero_h(fig)
    return estilo_plotly(fig, max(240, 46 * len(top) + 60))


def grafico_tendencia(df):
    p = tema()["p"]
    d = df.dropna(subset=["Fecha"]).groupby("Fecha")["Precio"].sum().reset_index().sort_values("Fecha")
    fig = go.Figure(go.Scatter(x=d["Fecha"], y=d["Precio"], mode="lines+markers", line=dict(color=p, width=2.5, shape="spline", smoothing=0.6),
                               marker=dict(size=8, color=p, line=dict(color="#FFFFFF", width=2)), fill="tozeroy", fillcolor="rgba(" + tema()["glow"] + ",0.14)",
                               hovertemplate="%{x|%d/%m/%Y}<br><b>$%{y:,.2f}</b><extra></extra>"))
    fig.update_xaxes(title=None, showgrid=False, tickformat="%d/%m", tickfont=dict(color="#64748B"), linecolor="#CBD5E1")
    fig.update_yaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    return estilo_plotly(fig, 300)


def grafico_pagos_marcas(rep, marcas):
    filas = []
    for m in marcas:
        sub = rep[rep["Marca"] == m]
        for metodo in COLORES_PAGO:
            filas.append({"E-commerce": m, "Forma de pago": metodo, "Monto": float(sub[metodo].sum())})
    fig = px.bar(pd.DataFrame(filas), y="E-commerce", x="Monto", color="Forma de pago", orientation="h", barmode="stack",
                 color_discrete_map=COLORES_PAGO, category_orders={"E-commerce": marcas, "Forma de pago": list(COLORES_PAGO)})
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{fullData.name}: $%{x:,.2f}<extra></extra>", marker_line_width=2, marker_line_color="#FFFFFF")
    fig.update_layout(bargap=0.35)
    _ejes_dinero_h(fig)
    fig.update_yaxes(autorange="reversed")
    return estilo_plotly(fig, max(260, 74 * len(marcas) + 90))


def grafico_tendencia_marcas(rep, marcas):
    d = rep.dropna(subset=["Fecha"]).groupby(["Fecha", "Marca"])["Precio"].sum().reset_index()
    fig = go.Figure()
    for m in marcas:
        s = d[d["Marca"] == m].sort_values("Fecha")
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=s["Fecha"], y=s["Precio"], name=m, mode="lines+markers",
                                 line=dict(color=COLORES_MARCA.get(m, "#94A3B8"), width=2),
                                 marker=dict(size=7, color=COLORES_MARCA.get(m, "#94A3B8"), line=dict(color="#FFFFFF", width=1.5)),
                                 hovertemplate="%{fullData.name}: $%{y:,.2f}<extra></extra>"))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title=None, showgrid=False, tickformat="%d/%m", tickfont=dict(color="#64748B"), linecolor="#CBD5E1")
    fig.update_yaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    return estilo_plotly(fig, 320)


# =====================================================================
# 11. DOCUMENTOS PDF
# =====================================================================
def _encabezado_pdf(pdf, subtitulo, color=(10, 25, 47), linea_extra=None):
    con_logo = False
    logo = logo_bytes()
    if logo:
        try:
            pdf.image(io.BytesIO(logo), 10, 8, 25)
            con_logo = True
        except Exception:
            con_logo = False
    if con_logo: pdf.set_x(40)
    pdf.set_font('helvetica', 'B', 16); pdf.set_text_color(*color); pdf.cell(0, 10, limpiar_texto_pdf(aj("empresa_nombre")), 0, 1, 'L')
    if con_logo: pdf.set_x(40)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(100, 100, 100); pdf.cell(0, 5, limpiar_texto_pdf(subtitulo), 0, 1, 'L')
    if linea_extra:
        if con_logo: pdf.set_x(40)
        pdf.cell(0, 5, limpiar_texto_pdf(linea_extra), 0, 1, 'L')
    pdf.ln(5)


def generar_recibo_pdf(e_dat, periodo_texto):
    class PDF(FPDF):
        def header(self):
            _encabezado_pdf(self, 'Comprobante Oficial de Pago', linea_extra=f"Periodo Liquidado: {periodo_texto}")

    pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
    pdf.cell(0, 10, limpiar_texto_pdf(f" Colaborador: {e_dat['Colaborador']}  ·  {e_dat['Modalidad']}"), 0, 1, 'L', fill=True); pdf.ln(5)

    pdf.set_font('helvetica', '', 9); pdf.set_text_color(80, 80, 80)
    txt_banco = f"DUI: {e_dat['DUI']} | Cuenta a Depositar: {e_dat['Cuenta']}" if e_dat['DUI'] or e_dat['Cuenta'] else "Datos bancarios no registrados"
    pdf.cell(0, 5, limpiar_texto_pdf(txt_banco), 0, 1, 'L'); pdf.ln(3)

    pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
    pdf.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)

    for d, v in [("Sueldo Base Acumulado (Bruto)", e_dat['Base Bruta']), ("Extra Bruto Generado", e_dat['Extra']), ("Comisiones Netas a Pagar", e_dat['Com Neta']), ("Bonos Extras", e_dat['Bonos'])]:
        if v > 0 or "Sueldo" in d or "Comisiones" in d:
            pdf.cell(130, 8, limpiar_texto_pdf(f"  {d}"), 1, 0, 'L'); pdf.cell(60, 8, f"${v:,.2f}", 1, 1, 'R')

    pdf.set_text_color(201, 42, 42)
    if e_dat['Desc'] > 0:
        pdf.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Desc']:,.2f}", 1, 1, 'R')
    if e_dat['Ret Pub'] > 0:
        pdf.cell(130, 8, limpiar_texto_pdf(f"  (Informativo) Retención {aj('retencion_pub_pct'):g}% Publicidad"), 1, 0, 'L'); pdf.cell(60, 8, f"${e_dat['Ret Pub']:,.2f}", 1, 1, 'R')
    if e_dat['Renta'] > 0:
        pdf.cell(130, 8, limpiar_texto_pdf(f"  (-) {aj('renta_pct'):g}% Retención de Renta"), 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Renta']:,.2f}", 1, 1, 'R')

    pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
    pdf.cell(130, 10, limpiar_texto_pdf("  TOTAL LÍQUIDO A RECIBIR"), 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total']:,.2f}", 1, 1, 'R', fill=True)

    notas_val = str(e_dat.get('Notas', 'Ninguno')).strip()
    if not notas_val or notas_val.lower() == 'ninguno': notas_val = "Sin notas adicionales"
    pdf.ln(6)
    pdf.set_font('helvetica', 'B', 10); pdf.set_text_color(10, 25, 47); pdf.set_fill_color(243, 244, 246)
    pdf.cell(0, 7, "  Notas del Registro:", 0, 1, 'L', fill=True)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 6, limpiar_texto_pdf(f"  {notas_val}"), 0, 'L')
    return generar_pdf_bytes(pdf)


def generar_planilla_pdf(filas, periodo_texto):
    class PDFPlanilla(FPDF):
        def header(self):
            _encabezado_pdf(self, 'Planilla de pago', linea_extra=f"Periodo: {periodo_texto}")

        def footer(self):
            self.set_y(-12); self.set_font('helvetica', '', 8); self.set_text_color(130, 130, 130)
            self.cell(0, 8, limpiar_texto_pdf(f"Generado el {ahora_sv().strftime('%d/%m/%Y %H:%M')} · Página {self.page_no()}"), 0, 0, 'C')

    pdf = PDFPlanilla(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, 16)
    pdf.add_page()
    especificacion = [("Colaborador", 56, "L", "Colaborador"), ("Forma de pago", 32, "L", "Modalidad"), ("Serv.", 12, "R", "Servicios"),
                      ("Ventas", 26, "R", "Ventas PDF"), ("Sueldo neto", 26, "R", "Base Neta"), ("Comisión", 26, "R", "Com Neta"),
                      ("Bonos", 20, "R", "Bonos"), ("Desc.", 20, "R", "Desc"), ("Renta", 22, "R", "Renta"), ("Total a pagar", 32, "R", "Total")]
    pdf.set_font('helvetica', 'B', 9); pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
    for titulo, w, al, _ in especificacion:
        pdf.cell(w, 8, limpiar_texto_pdf(f" {titulo} "), 1, 0, al, fill=True)
    pdf.ln()
    pdf.set_font('helvetica', '', 9); pdf.set_text_color(40, 40, 40)

    def celda(valor, clave):
        if clave in ("Colaborador", "Modalidad"):
            return limpiar_texto_pdf(f" {valor}")
        if clave == "Servicios":
            return f"{int(valor)} "
        return f"${float(valor):,.2f} "

    for i, f in enumerate(filas):
        if i % 2:
            pdf.set_fill_color(248, 250, 252)
        else:
            pdf.set_fill_color(255, 255, 255)
        for _, w, al, clave in especificacion:
            pdf.cell(w, 7, celda(f[clave], clave), 1, 0, al, fill=True)
        pdf.ln()
    pdf.set_font('helvetica', 'B', 9); pdf.set_fill_color(238, 242, 255)
    for _, w, al, clave in especificacion:
        if clave == "Colaborador":
            texto = " TOTAL"
        elif clave == "Modalidad":
            texto = ""
        else:
            texto = celda(sum(f[clave] for f in filas), clave)
        pdf.cell(w, 8, texto, 1, 0, al, fill=True)
    pdf.ln()
    return generar_pdf_bytes(pdf)


def _firmas_pdf(pdf, izquierda, derecha):
    pdf.ln(28)
    y = pdf.get_y()
    pdf.set_draw_color(120, 120, 120)
    pdf.line(20, y, 90, y); pdf.line(120, y, 190, y)
    pdf.set_font('helvetica', '', 9); pdf.set_text_color(80, 80, 80)
    pdf.set_xy(20, y + 2); pdf.cell(70, 5, limpiar_texto_pdf(izquierda), 0, 0, 'C')
    pdf.set_xy(120, y + 2); pdf.cell(70, 5, limpiar_texto_pdf(derecha), 0, 1, 'C')


def generar_memo_pdf(destinatario, asunto, texto):
    class PDFMemo(FPDF):
        def header(self): _encabezado_pdf(self, 'Memorándum Interno')
    pdf_m = PDFMemo(); pdf_m.add_page()
    pdf_m.set_font('helvetica', '', 10); pdf_m.set_text_color(80, 80, 80)
    pdf_m.cell(0, 6, limpiar_texto_pdf(f" Fecha: {ahora_sv().strftime('%d/%m/%Y')}"), 0, 1, 'L')
    pdf_m.set_font('helvetica', 'B', 11); pdf_m.set_text_color(10, 25, 47)
    pdf_m.cell(0, 10, limpiar_texto_pdf(f" Entregado a: {destinatario}"), 0, 1, 'L'); pdf_m.cell(0, 10, limpiar_texto_pdf(f" Asunto Central: {asunto}"), 0, 1, 'L')
    y = pdf_m.get_y() + 1; pdf_m.set_draw_color(200, 200, 200); pdf_m.line(10, y, 200, y); pdf_m.ln(5)
    pdf_m.set_font('helvetica', '', 11); pdf_m.set_text_color(40, 40, 40); pdf_m.multi_cell(0, 7, limpiar_texto_pdf(texto), 0, 'L')
    _firmas_pdf(pdf_m, "Administración / Gerencia General", f"Recibido: {destinatario}")
    return generar_pdf_bytes(pdf_m)


def generar_acta_pdf(destinatario, tipo_falta, motivo):
    class PDFAmon(FPDF):
        def header(self): _encabezado_pdf(self, 'Acta de Amonestación', color=(201, 42, 42))
    pdf_a = PDFAmon(); pdf_a.add_page()
    pdf_a.set_font('helvetica', '', 10); pdf_a.set_text_color(80, 80, 80)
    pdf_a.cell(0, 6, limpiar_texto_pdf(f" Fecha: {ahora_sv().strftime('%d/%m/%Y')}"), 0, 1, 'L')
    pdf_a.set_font('helvetica', 'B', 11); pdf_a.set_text_color(10, 25, 47)
    pdf_a.cell(0, 10, limpiar_texto_pdf(f" Dirigido a: {destinatario}"), 0, 1, 'L'); pdf_a.cell(0, 10, limpiar_texto_pdf(f" Tipo de Falta: {tipo_falta}"), 0, 1, 'L')
    pdf_a.set_font('helvetica', '', 11); pdf_a.set_text_color(40, 40, 40); pdf_a.multi_cell(0, 7, limpiar_texto_pdf(motivo), 1, 'L')
    _firmas_pdf(pdf_a, "Gerencia General", f"Colaborador: {destinatario}")
    return generar_pdf_bytes(pdf_a)


# =====================================================================
# 12. CORREO (Gmail)
# =====================================================================
def abrir_smtp():
    remitente = st.secrets["EMAIL_USER"]
    password = st.secrets["EMAIL_PASS"]
    servidor_smtp = smtplib.SMTP('smtp.gmail.com', 587, timeout=30)
    servidor_smtp.starttls()
    servidor_smtp.login(remitente, password)
    return servidor_smtp, remitente


def construir_mensaje(remitente, destinatario, asunto, cuerpo, pdf_bytes, nombre_adjunto):
    msg = MIMEMultipart()
    msg['From'] = remitente; msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo, 'plain'))
    parte_adjunta = MIMEApplication(pdf_bytes, Name=nombre_adjunto)
    parte_adjunta.add_header('Content-Disposition', 'attachment', filename=nombre_adjunto)
    msg.attach(parte_adjunta)
    return msg


def mensaje_recibo(remitente, e_dat, pdf_bytes, nombre_adjunto, periodo_texto):
    asunto = f"Comprobante de Pago - Período: {periodo_texto} | {aj('empresa_corto')}"
    cuerpo = (f"Estimado/a {e_dat['Colaborador']},\n\nAdjunto a este correo electrónico encontrará su Comprobante Oficial de Pago detallado."
              f"\n\nAtentamente,\n{aj('firma_correo')}")
    return construir_mensaje(remitente, e_dat["Email"], asunto, cuerpo, pdf_bytes, nombre_adjunto)


def enviar_documento(destinatario, asunto, cuerpo, pdf_bytes, nombre_adjunto):
    servidor_smtp, remitente = abrir_smtp()
    try:
        msg = construir_mensaje(remitente, destinatario, asunto, cuerpo, pdf_bytes, nombre_adjunto)
        servidor_smtp.sendmail(remitente, destinatario, msg.as_string())
    finally:
        try:
            servidor_smtp.quit()
        except Exception:
            pass


def bloque_envio_documento(prefijo, emp, pdf_bytes, nombre_pdf, asunto, cuerpo, tipo_auditoria):
    """Descargar el PDF o enviarlo al correo del colaborador (editable)."""
    b1, b2, b3 = columnas([1, 1.6, 1], "bottom")
    with b1:
        st.download_button("⬇️ Descargar PDF", data=pdf_bytes, file_name=nombre_pdf, mime="application/pdf", key=f"{prefijo}_dl", **ancho(st.download_button))
    with b2:
        correo = st.text_input("Enviar al correo", value=correo_de(emp), key=f"{prefijo}_correo_{nombre_archivo('', emp)}", placeholder="nombre@correo.com")
    with b3:
        enviar = st.button("📨 Enviar por correo", key=f"{prefijo}_enviar", type="primary", disabled=not correo_valido(correo), **ancho(st.button))
    if not correo_valido(correo):
        st.caption("Escribe un correo válido para habilitar el envío. Puedes guardar el correo del colaborador en Configuración → Personal y sueldos.")
    if enviar:
        with st.spinner("Enviando por Gmail..."):
            try:
                enviar_documento(correo, asunto, cuerpo, pdf_bytes, nombre_pdf)
                registrar_auditoria(f"{tipo_auditoria} (enviado por correo)", emp)
                st.toast(f"Enviado a {correo}", icon="📨")
            except Exception as ex:
                st.error(f"No se pudo enviar el correo. Verifique los secretos `EMAIL_USER` y `EMAIL_PASS`: {ex}")


# =====================================================================
# 13. PROVEEDORES (CRM)
# =====================================================================
SECCIONES_PROVEEDOR = [
    ("Información de contacto", "#4F46E5", 2, [
        ("Nombre_Proveedor", "Nombre de la empresa / proveedor *", "texto"), ("Nombre_Contacto", "Nombre del contacto", "texto"),
        ("Telefono_1", "Teléfono", "texto"), ("Correo", "Correo electrónico", "texto"),
        ("Direccion_1", "Dirección", "texto"), ("Direccion_2", "Ciudad / Dirección 2", "texto"), ("Pais", "País", "texto")]),
    ("Datos financieros", "#059669", 2, [
        ("Banco", "Banco", "texto"), ("Cuenta", "Número de cuenta", "texto"),
        ("Patrocinador", "Patrocinador", "texto"), ("Telefono_2", "Teléfono del patrocinador", "texto")]),
    ("Contratos y auditoría", "#7C3AED", 4, [
        ("Fecha_Contrato", "Contrato firmado", "fecha"), ("Fecha_Vencimiento", "Vencimiento del contrato", "fecha"),
        ("Fecha_Rev_Contrato", "Revisión del contrato", "fecha"), ("Fecha_Aprobacion", "Aprobación", "fecha"),
        ("Fecha_Ultima_Rev", "Última revisión", "fecha"), ("Fecha_Prox_Rev", "Próxima revisión", "fecha"),
        ("Fecha_Calif_Riesgo", "Calificación de riesgo", "fecha"), ("Fecha_Diligencia", "Diligencia debida", "fecha")]),
]
FECHAS_PROVEEDOR = [
    ("📝", "Contrato firmado", "Fecha_Contrato"), ("⏳", "Vencimiento del contrato", "Fecha_Vencimiento"), ("🔁", "Revisión del contrato", "Fecha_Rev_Contrato"),
    ("✅", "Aprobación", "Fecha_Aprobacion"), ("🔍", "Última revisión", "Fecha_Ultima_Rev"), ("📆", "Próxima revisión", "Fecha_Prox_Rev"),
    ("🛡️", "Calificación de riesgo", "Fecha_Calif_Riesgo"), ("📑", "Diligencia debida", "Fecha_Diligencia"),
]


def _valoracion_pct(v):
    n = _a_numero(v)
    return None if n is None else max(0.0, min(100.0, n))


def estado_contrato(p):
    venc = _parse_fecha(p.get("Fecha_Vencimiento"))
    if venc is None:
        return ("Sin fecha de vencimiento", "")
    dias = (venc.normalize() - pd.Timestamp(ahora_sv().date())).days
    if dias < 0:
        return (f"Vencido hace {abs(dias)} días", "red")
    if dias <= 30:
        return (f"Vence en {dias} días", "amber")
    return ("Contrato vigente", "green")


def crm_seccion(titulo, color):
    return f"<div class='crm-section-title'><span class='sdot' style='background:{color};box-shadow:0 0 0 3px {color}26'></span>{titulo}</div>"


def crm_campo(icono, etiqueta, valor, tipo="texto"):
    t = _texto(valor)
    e = html.escape(t)
    if not t:
        contenido = "<div class='crm-value empty'>Sin registrar</div>"
    elif tipo == "correo":
        contenido = f"<div class='crm-value'><a href='mailto:{e}'>{e}</a></div>"
    elif tipo == "telefono":
        tel = re.sub(r"[^\d+]", "", t)
        contenido = f"<div class='crm-value mono'><a href='tel:{tel}'>{e}</a></div>"
    elif tipo == "mono":
        contenido = f"<div class='crm-value mono'>{e}</div>"
    else:
        contenido = f"<div class='crm-value'>{e}</div>"
    return f"<div class='crm-field'><div class='crm-ico'>{icono}</div><div><div class='crm-label'>{etiqueta}</div>{contenido}</div></div>"


def crm_fecha(icono, etiqueta, valor, extra=""):
    f = _parse_fecha(valor)
    mostrar = f.strftime("%d/%m/%Y") if f is not None else _texto(valor)
    derecha = f"<div class='r'>{extra}{html.escape(mostrar)}</div>" if mostrar else "<div class='r empty'>Pendiente</div>"
    return f"<div class='crm-date'><div class='l'><span>{icono}</span>{etiqueta}</div>{derecha}</div>"


def nombre_proveedor(p):
    return _texto(p.get("Nombre_Proveedor")) or f"Prov {_texto(p.get('ID_Proveedor'))}"


def siguiente_id_proveedor(provs):
    ids = [n for n in (_a_numero(p.get("ID_Proveedor")) for p in provs) if n is not None]
    return str(int(max(ids)) + 1 if ids else 1)


def abrir_nuevo_proveedor():
    st.session_state["prov_modo"] = "nuevo"
    st.session_state["prov_idx"] = None


def abrir_edicion_proveedor(idx):
    st.session_state["prov_modo"] = "editar"
    st.session_state["prov_idx"] = idx


def volver_directorio():
    st.session_state["prov_modo"] = "ver"
    st.session_state["prov_idx"] = None


def pedir_borrado_proveedor(idx, nombre):
    st.session_state["prov_a_eliminar"] = (idx, nombre)


def cancelar_borrado_proveedor():
    st.session_state.pop("prov_a_eliminar", None)


def confirmar_borrado_proveedor(idx, nombre):
    ss = st.session_state
    ss.pop("prov_a_eliminar", None)
    provs = ss["proveedores"]
    if idx >= len(provs) or nombre_proveedor(provs[idx]) != nombre:
        notificar_error("No se pudo eliminar: la lista cambió mientras confirmabas.")
        return
    encabezados = list(provs[idx].keys())
    ss["proveedores"] = provs[:idx] + provs[idx + 1:]
    ss.pop("prov_seleccionado", None)
    if guardar_proveedores(ss["proveedores"], encabezados_si_vacio=encabezados):
        notificar(f"Proveedor «{nombre}» eliminado.", "🗑️")
    else:
        notificar_error(f"«{nombre}» se eliminó de la sesión, pero no se pudo actualizar Google Sheets.")


def formulario_proveedor(base, clave_form, texto_boton):
    """Formulario completo (contacto, financieros, contratos y auditoría). Devuelve el registro al guardar."""
    with st.form(clave_form, clear_on_submit=False):
        valores = {}
        for titulo, color, n_cols, campos in SECCIONES_PROVEEDOR:
            md(crm_seccion(titulo, color))
            cols = st.columns(n_cols)
            for i, (campo, etiqueta, tipo) in enumerate(campos):
                col = cols[i % n_cols]
                if tipo == "fecha":
                    f = _parse_fecha(base.get(campo))
                    valores[campo] = col.date_input(etiqueta, value=f.date() if f is not None else None, format="DD/MM/YYYY",
                                                    min_value=date(2000, 1, 1), max_value=date(2100, 12, 31), key=f"{clave_form}_{campo}")
                else:
                    valores[campo] = col.text_input(etiqueta, value=_texto(base.get(campo)), key=f"{clave_form}_{campo}")
        md(crm_seccion("Descripción, valoración y notas", "#F59E0B"))
        c1, c2 = st.columns([2, 1])
        valores["Descripcion"] = c1.text_input("Descripción / ¿Qué productos o servicios provee?", value=_texto(base.get("Descripcion")), key=f"{clave_form}_Descripcion")
        pct = _valoracion_pct(base.get("Valoracion"))
        valoracion = c2.slider("Valoración general (%)", 0, 100, int(pct) if pct is not None else 50, step=5, key=f"{clave_form}_Valoracion")
        valores["Notas"] = st.text_area("Notas internas", value=_texto(base.get("Notas")), height=110, key=f"{clave_form}_Notas")
        enviado = st.form_submit_button(texto_boton, type="primary", **ancho(st.form_submit_button))
    if not enviado:
        return None
    registro = {}
    for campo, valor in valores.items():
        if isinstance(valor, (date, datetime)):
            registro[campo] = valor.strftime("%Y-%m-%d")
        elif valor is None:
            registro[campo] = ""
        else:
            registro[campo] = _texto(valor)
    registro["Valoracion"] = f"{int(valoracion)}%"
    return registro


def render_perfil_proveedor(p, idx):
    nombre = _texto(p.get("Nombre_Proveedor")) or "Proveedor sin nombre"
    clave = nombre_proveedor(p)
    estado_txt, estado_cls = estado_contrato(p)
    hoy = pd.Timestamp(ahora_sv().date())
    venc = _parse_fecha(p.get("Fecha_Vencimiento"))
    prox = _parse_fecha(p.get("Fecha_Prox_Rev"))
    prox_atrasada = prox is not None and prox.normalize() < hoy

    with tarjeta("prov_header"):
        chips = chip(f"● {estado_txt}", estado_cls)
        if _texto(p.get("Pais")):
            chips += chip(f"🌎 {_esc(p.get('Pais'))}")
        if _texto(p.get("ID_Proveedor")):
            chips += chip(f"# ID {_esc(p.get('ID_Proveedor'))}", "indigo")
        desc = _esc(p.get("Descripcion")) or "Sin descripción registrada"
        h1, h2 = columnas([4.2, 1.4], "center")
        with h1:
            md(f"<div class='crm-head'><div class='crm-avatar'>{html.escape(_iniciales(nombre))}</div><div><div class='crm-kicker'>Proveedor</div>"
               f"<div class='crm-name'>{html.escape(nombre)}</div><div class='crm-desc'>{desc}</div><div class='chips' style='margin-top:10px'>{chips}</div></div></div>")
        with h2:
            st.button("✏️ Editar datos", key="btn_editar_prov", on_click=abrir_edicion_proveedor, args=(idx,), **ancho(st.button))
            with zona("peligro_eliminar"):
                st.button("🗑️ Eliminar", key="btn_eliminar_prov", on_click=pedir_borrado_proveedor, args=(idx, clave), **ancho(st.button))

        if st.session_state.get("prov_a_eliminar") == (idx, clave):
            md(f"<div class='confirmar-borrado'>⚠️ ¿Eliminar definitivamente a <b>{html.escape(nombre)}</b>? También se borrará de Google Sheets.</div>")
            k1, k2, _ = st.columns([1.2, 1, 3])
            with k1:
                with zona("peligro_confirmar"):
                    st.button("Sí, eliminar", key="btn_confirmar_borrado", on_click=confirmar_borrado_proveedor, args=(idx, clave), **ancho(st.button))
            with k2:
                st.button("Cancelar", key="btn_cancelar_borrado", on_click=cancelar_borrado_proveedor, **ancho(st.button))

    pct = _valoracion_pct(p.get("Valoracion"))
    barra = f"<div class='bar'><span style='width:{pct:.0f}%'></span></div>" if pct is not None else "Sin calificación"
    fila_kpis([
        kpi_html("⭐", "Valoración general", _esc(p.get("Valoracion")) or "—", barra, "amber"),
        kpi_html("⏳", "Vencimiento de contrato", venc.strftime("%d/%m/%Y") if venc is not None else "—", estado_txt, "violet"),
        kpi_html("📆", "Próxima revisión", prox.strftime("%d/%m/%Y") if prox is not None else "—",
                 "Revisión atrasada" if prox_atrasada else "Programada" if prox is not None else "Sin programar", "red" if prox_atrasada else "sky"),
    ])
    espacio(6)

    c1, c2, c3 = st.columns(3)
    with c1:
        with tarjeta("prov_contacto"):
            md(crm_seccion("Información de contacto", tema()["p"]) + crm_campo("👤", "Contacto", p.get("Nombre_Contacto"))
               + crm_campo("📞", "Teléfono", p.get("Telefono_1"), "telefono") + crm_campo("📧", "Correo electrónico", p.get("Correo"), "correo")
               + crm_campo("📍", "Dirección", p.get("Direccion_1")) + crm_campo("🏙️", "Ciudad / Dirección 2", p.get("Direccion_2")) + crm_campo("🌎", "País", p.get("Pais")))
    with c2:
        with tarjeta("prov_finanzas"):
            md(crm_seccion("Datos financieros", "#059669") + crm_campo("🏦", "Banco", p.get("Banco")) + crm_campo("💳", "Número de cuenta", p.get("Cuenta"), "mono")
               + crm_campo("🤝", "Patrocinador", p.get("Patrocinador")) + crm_campo("☎️", "Teléfono del patrocinador", p.get("Telefono_2"), "telefono"))
            if _texto(p.get("Cuenta")):
                st.caption("Copiar número de cuenta")
                st.code(_texto(p.get("Cuenta")), language=None)
    with c3:
        with tarjeta("prov_fechas"):
            filas = ""
            for icono, etiqueta, campo in FECHAS_PROVEEDOR:
                extra = ""
                if campo == "Fecha_Vencimiento" and estado_cls:
                    extra = chip("Vencido" if estado_cls == "red" else "Por vencer" if estado_cls == "amber" else "Vigente", estado_cls)
                elif campo == "Fecha_Prox_Rev" and prox_atrasada:
                    extra = chip("Atrasada", "red")
                filas += crm_fecha(icono, etiqueta, p.get(campo), extra)
            md(crm_seccion("Contratos y auditoría", "#7C3AED") + filas)

    with tarjeta("prov_notas"):
        notas = _esc(p.get("Notas"))
        cuerpo = f"<div class='crm-text'>{notas}</div>" if notas else "<div class='crm-text empty'>Sin notas registradas para este proveedor.</div>"
        md(crm_seccion("Notas internas", "#F59E0B") + cuerpo)


# =====================================================================
# 14. PERSONAL, FORMA DE PAGO Y AJUSTES (callbacks)
# =====================================================================
def actualizar_ajuste(clave, widget_key, recalcular=False):
    ss = st.session_state
    ss["ajustes"][clave] = ss[widget_key]
    if recalcular:
        recalcular_todo()


def restaurar_reglas():
    ss = st.session_state
    for clave, valor in REGLAS_OFICIALES.items():
        ss["ajustes"][clave] = valor
        ss.pop(f"aj_{clave}", None)
    recalcular_todo()
    notificar("Reglas oficiales restauradas: extra sobre $60, pauta 25% y renta 10%.", "↩️")


def quitar_logo():
    st.session_state["ajustes"]["logo_b64"] = ""
    notificar("Logo quitado. Recuerda guardar los ajustes en Google Sheets.", "🖼️")


def _aplicar_cambios_personal(nuevos, recalcular=(), guardar=True):
    ss = st.session_state
    ss["empleados"] = nuevos
    for emp in recalcular:
        ss.pop(f"base_net_{emp}", None)
    inicializar_empleados()
    for emp, info in nuevos.items():
        ss[f"email_{emp}"] = _texto(info.get("correo"))
        for clave in (f"ui_e_{emp}", f"fp_mod_{emp}", f"fp_porc_{emp}"):
            ss.pop(clave, None)
    reiniciar_widgets_planilla()
    if ss.get("pdf_bytes"):
        ejecutar_procesamiento()
    ss["nonce_editor_personal"] += 1
    return guardar_empleados(nuevos) if guardar else True


def aplicar_forma_pago(emp):
    """Cambio rápido de forma de pago y porcentaje desde Planillas (se guarda en el personal)."""
    ss = st.session_state
    info = dict(ss["empleados"].get(emp) or {})
    if not info:
        return
    mod = ss.get(f"fp_mod_{emp}", info.get("mod"))
    if mod not in MODALIDADES:
        return
    info["mod"] = mod
    if mod == MOD_PORCENTAJE or (mod == MOD_FIJO and info.get("rol") == "Operativo"):
        porc = float(ss.get(f"fp_porc_{emp}", info.get("porc", 0)) or 0.0)
        if mod == MOD_PORCENTAJE and porc <= 0:
            notificar_error(f"Indica un porcentaje mayor a 0% para {emp}.")
            return
        info["porc"] = min(max(porc, 0.0), 100.0)
    elif mod == MOD_FIJO:
        info["porc"] = 0.0
    aviso = ""
    if mod != MOD_PORCENTAJE and sueldo_neto_de(info) <= 0:
        info["sueldo_base_neto"] = neto_q_desde_bruto_mensual(aj("salario_minimo"))
        aviso = " Se le asignó el salario mínimo como sueldo base; ajústalo en Configuración si es otro."
    nuevos = {k: (info if k == emp else v) for k, v in ss["empleados"].items()}
    ok = _aplicar_cambios_personal(nuevos, recalcular=(emp,))
    ss["fe_recargar"] = True
    if ok:
        notificar(f"{emp}: ahora cobra {forma_pago_texto(info)}. Planilla recalculada.{aviso}", "✅")
    else:
        notificar_error(f"El cambio de {emp} quedó en esta sesión, pero no se pudo guardar en Google Sheets.{aviso}")


def cargar_form_empleado():
    ss = st.session_state
    sel = ss.get("fe_sel", NUEVO_EMP)
    nuevo = sel not in ss["empleados"]
    info = {} if nuevo else ss["empleados"][sel]
    ss["fe_nombre"] = "" if nuevo else sel
    ss["fe_cargo"] = _texto(info.get("cargo"))
    ss["fe_rol"] = info.get("rol") if info.get("rol") in ROLES else "Operativo"
    ss["fe_mod"] = info.get("mod") if info.get("mod") in MODALIDADES else MOD_ESTANDAR
    porc = _a_numero(info.get("porc"))
    ss["fe_porc"] = float(min(100.0, max(0.0, 20.0 if porc is None else porc)))
    ss["fe_modo_sueldo"] = MODO_NETO_Q
    ss["fe_modo_prev"] = MODO_NETO_Q
    ss["fe_sueldo"] = float(max(0.0, neto_q_desde_bruto_mensual(aj("salario_minimo")) if nuevo or sueldo_neto_de(info) <= 0 else sueldo_neto_de(info)))
    for campo in ("alias",) + CAMPOS_EXTRA_EMPLEADO:
        ss[f"fe_{campo}"] = _texto(info.get(campo))
    ss["fe_confirmar_borrar"] = False


def cambio_forma_pago_form():
    ss = st.session_state
    mod = ss.get("fe_mod")
    if mod == MOD_PORCENTAJE and float(ss.get("fe_porc") or 0) <= 0:
        ss["fe_porc"] = 20.0
    elif mod == MOD_FIJO:
        ss["fe_porc"] = 0.0


def convertir_modo_sueldo():
    ss = st.session_state
    nuevo_modo, previo = ss.get("fe_modo_sueldo"), ss.get("fe_modo_prev", MODO_NETO_Q)
    if nuevo_modo == previo:
        return
    valor = float(ss.get("fe_sueldo") or 0.0)
    if nuevo_modo == MODO_BRUTO_M:
        ss["fe_sueldo"] = round(valor / factor_neto() * 2, 2)
    else:
        ss["fe_sueldo"] = neto_q_desde_bruto_mensual(valor)
    ss["fe_modo_prev"] = nuevo_modo


def usar_salario_minimo():
    ss = st.session_state
    ss["fe_modo_sueldo"] = MODO_BRUTO_M
    ss["fe_modo_prev"] = MODO_BRUTO_M
    ss["fe_sueldo"] = float(aj("salario_minimo"))


def neto_q_formulario():
    ss = st.session_state
    valor = float(ss.get("fe_sueldo") or 0.0)
    return round(valor, 2) if ss.get("fe_modo_sueldo", MODO_NETO_Q) == MODO_NETO_Q else neto_q_desde_bruto_mensual(valor)


def guardar_form_empleado():
    ss = st.session_state
    nombre = _texto(ss.get("fe_nombre"))
    sel = ss.get("fe_sel", NUEVO_EMP)
    es_nuevo = sel not in ss["empleados"]
    previo = {} if es_nuevo else ss["empleados"][sel]
    if not nombre:
        notificar_error("Escribe el nombre del colaborador antes de guardar.")
        return
    if nombre in ss["empleados"] and (es_nuevo or nombre != sel):
        notificar_error(f"Ya existe un colaborador llamado «{nombre}».")
        return
    correo = _texto(ss.get("fe_correo"))
    if correo and not correo_valido(correo):
        notificar_error(f"El correo «{correo}» no es válido.")
        return
    mod = ss.get("fe_mod") if ss.get("fe_mod") in MODALIDADES else MOD_ESTANDAR
    rol = ss.get("fe_rol") if ss.get("fe_rol") in ROLES else "Operativo"
    if mod == MOD_PORCENTAJE or (mod == MOD_FIJO and rol == "Operativo"):
        porc = float(ss.get("fe_porc") or 0.0)
    elif mod == MOD_FIJO:
        porc = 0.0
    else:
        porc_previo = _a_numero(previo.get("porc"))
        porc = 20.0 if porc_previo is None else porc_previo
    if mod == MOD_PORCENTAJE and porc <= 0:
        notificar_error("Indica el porcentaje de comisión (entre 1% y 100%).")
        return
    if mod == MOD_PORCENTAJE:
        sueldo = sueldo_neto_de(previo) if previo else 0.0  # se conserva por si vuelve a tener sueldo base
    else:
        sueldo = neto_q_formulario() if "fe_sueldo" in ss else sueldo_neto_de(previo)
    info = _empleado_normalizado({
        "rol": rol, "mod": mod, "porc": porc, "alias": ss.get("fe_alias"), "sueldo_base_neto": sueldo,
        "cargo": ss.get("fe_cargo"), "correo": correo, "telefono": ss.get("fe_telefono"), "dui": ss.get("fe_dui"),
        "banco": ss.get("fe_banco"), "cuenta": ss.get("fe_cuenta"), "fecha_ingreso": ss.get("fe_fecha_ingreso"),
    })
    if es_nuevo:
        nuevos = dict(ss["empleados"])
        nuevos[nombre] = info
    else:
        nuevos = {}
        for k, v in ss["empleados"].items():
            nuevos[nombre if k == sel else k] = info if k == sel else v
        if nombre != sel:
            for pref in ("hex_", "desc_", "notas_"):
                if f"{pref}{sel}" in ss:
                    ss[f"{pref}{nombre}"] = ss[f"{pref}{sel}"]
    ok = _aplicar_cambios_personal(nuevos, recalcular=(nombre,))
    ss["fe_sel"] = nombre
    cargar_form_empleado()
    if ok:
        notificar(f"«{nombre}» guardado: {forma_pago_texto(info)}. Planilla recalculada.", "✅")
    else:
        notificar_error("Los cambios del colaborador quedaron en esta sesión, pero no se pudieron guardar en Google Sheets.")


def pedir_borrar_empleado():
    st.session_state["fe_confirmar_borrar"] = True


def cancelar_borrar_empleado():
    st.session_state["fe_confirmar_borrar"] = False


def eliminar_empleado():
    ss = st.session_state
    sel = ss.get("fe_sel")
    if sel not in ss["empleados"]:
        return
    if len(ss["empleados"]) <= 1:
        notificar_error("Debe quedar al menos un colaborador registrado.")
        return
    nuevos = {k: v for k, v in ss["empleados"].items() if k != sel}
    ok = _aplicar_cambios_personal(nuevos)
    ss["fe_sel"] = NUEVO_EMP
    cargar_form_empleado()
    if ok:
        notificar(f"Colaborador «{sel}» eliminado.", "🗑️")
    else:
        notificar_error(f"«{sel}» se eliminó de la sesión, pero no se pudo actualizar Google Sheets.")


def ir_a(pagina):
    st.session_state["pagina"] = pagina


def ir_a_movil():
    v = st.session_state.get("nav_movil_sel")
    if v in PAGINAS_VALIDAS:
        st.session_state["pagina"] = v


PLANTILLA_SECRETS = """# Streamlit Cloud → tu app → ⋮ → Settings → Secrets  (o el archivo .streamlit/secrets.toml en tu PC)
EMAIL_USER = "tucorreo@gmail.com"
EMAIL_PASS = "abcd efgh ijkl mnop"   # contraseña de aplicación de Gmail (16 letras)

[gsheets]
url = "https://docs.google.com/spreadsheets/d/TU_ID_DE_HOJA/edit"

[gcp_service_account]   # copia aquí los datos del archivo JSON de la cuenta de servicio
type = "service_account"
project_id = "tu-proyecto"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "gio-group@tu-proyecto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
"""

GUIA_CONEXION_HTML = (
    "<div class='guia'><ol>"
    "<li><b>Crea la hoja de cálculo.</b> En Google Sheets crea un archivo nuevo (por ejemplo «Gio Group · Base de datos») y copia su enlace.</li>"
    "<li><b>Crea un proyecto en Google Cloud.</b> Entra a <code>console.cloud.google.com</code>, crea un proyecto y en «APIs y servicios → Biblioteca» habilita <b>Google Sheets API</b> y <b>Google Drive API</b>.</li>"
    "<li><b>Crea la cuenta de servicio.</b> En «IAM y administración → Cuentas de servicio» crea una cuenta, entra en ella, abre «Claves → Agregar clave → JSON» y guarda el archivo que se descarga (no lo compartas).</li>"
    "<li><b>Comparte la hoja.</b> En tu hoja de cálculo pulsa «Compartir» y agrega el correo de la cuenta de servicio (termina en <code>iam.gserviceaccount.com</code>) como <b>Editor</b>.</li>"
    "<li><b>Prepara Gmail.</b> Activa la verificación en dos pasos de tu cuenta y crea una «Contraseña de aplicación»: esas 16 letras van en <code>EMAIL_PASS</code>.</li>"
    "<li><b>Pega los secretos.</b> En Streamlit Cloud abre tu app → ⋮ → <b>Settings → Secrets</b>, pega la plantilla de abajo con tus datos y guarda. Nunca subas estos datos a GitHub.</li>"
    "<li><b>Conecta y prepara.</b> Vuelve aquí, pulsa «Reintentar conexión» y luego «Preparar hoja de cálculo»: la app crea las pestañas Personal, Proveedores, Ajustes, Auditoria e Historial_Planillas.</li>"
    "</ol></div>"
)



# =====================================================================
# 15. ESTILOS + MENÚ LATERAL + NAVEGACIÓN EN TELÉFONO
# =====================================================================
md(css_tema() + CSS_BASE)
mostrar_notificaciones()

with st.sidebar:
    md(f"<div class='brand'><img src='{img_logo()}' alt=''/><div><div class='brand-name'>{html.escape(aj('empresa_corto'))}</div>"
       "<div class='brand-sub'>Suite administrativa</div></div></div>")
    for seccion, items in MENU:
        md(f"<div class='nav-sec'>{seccion}</div>")
        with zona(f"nav_{_normalizar(seccion).lower()}"):
            for clave_pag, icono, etiqueta in items:
                st.button(f"{icono}  {etiqueta}", key=f"navbtn_{clave_pag}", on_click=ir_a, args=(clave_pag,),
                          type="primary" if st.session_state["pagina"] == clave_pag else "secondary", **ancho(st.button))

    if "sheets_ok" not in st.session_state:
        st.session_state["sheets_ok"] = _documento() is not None
    estado_sheets = "<span class='dot on'></span><b>Conectado</b>" if st.session_state["sheets_ok"] else "<span class='dot off'></span><b>Modo local</b>"
    estado_pdf = "<span class='dot on'></span><b>Sincronizado</b>" if st.session_state["pdf_ok"] else "<span class='dot off'></span><b>Pendiente</b>"
    pi_side = st.session_state.get("periodo_info")
    periodo_side = html.escape(pi_side["etiqueta"]) if pi_side else "Sin reporte"
    md(f"<div class='side-card'><div class='side-title'>Estado del sistema</div>"
       f"<div class='side-row'><span>Google Sheets</span><span>{estado_sheets}</span></div>"
       f"<div class='side-row'><span>Reporte de ventas</span><span>{estado_pdf}</span></div>"
       f"<div class='side-row'><span>Período</span><b>{periodo_side}</b></div>"
       f"<div class='side-row'><span>Quincenas a pagar</span><b>{st.session_state['quincenas_multiplicador']:g}</b></div>"
       f"<div class='side-row'><span>Colaboradores</span><b>{len(st.session_state['empleados'])}</b></div></div>")
    md("<div class='profile'><div class='avatar'>AD</div><div><div class='profile-name'>Administración</div><div class='profile-role'>Gerencia General</div></div></div>"
       "<div class='version'>Suite administrativa · v4</div>")


def nav_movil():
    """En el teléfono el menú lateral queda oculto: esta barra permite cambiar de sección sin abrirlo."""
    ss = st.session_state
    with zona("navmovil"):
        ss["nav_movil_sel"] = ss["pagina"]
        if hasattr(st, "pills"):
            st.pills("Ir a", PAGINAS_VALIDAS, key="nav_movil_sel", format_func=lambda p: ETIQUETAS_PAGINA.get(p, p),
                     on_change=ir_a_movil, label_visibility="collapsed")
        else:
            st.selectbox("Ir a", PAGINAS_VALIDAS, key="nav_movil_sel", format_func=lambda p: ETIQUETAS_PAGINA.get(p, p),
                         on_change=ir_a_movil, label_visibility="collapsed")


nav_movil()


# =====================================================================
# 16. PANEL DE SINCRONIZACIÓN DEL PDF
# =====================================================================
def hero_dashboard():
    ss = st.session_state
    ahora = ahora_sv()
    saludo = "Buenos días" if ahora.hour < 12 else "Buenas tardes" if ahora.hour < 19 else "Buenas noches"
    fecha = f"{DIAS[ahora.weekday()].capitalize()}, {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}"
    chips = f"<span class='hero-chip'>📅 {html.escape(ss['periodo_texto'])}</span>"
    if ss.get("pdf_ok"):
        chips += f"<span class='hero-chip'>✅ {html.escape(ss['pdf_nombre'])}</span>"
    else:
        chips += "<span class='hero-chip'>⏳ Esperando reporte de ventas</span>"
    chips += f"<span class='hero-chip'>👥 {len(ss['empleados'])} colaboradores</span>"
    md(f"<div class='hero'><div class='hero-body'><div class='hero-kicker'>{fecha}</div><div class='hero-title'>{saludo}, Gerencia</div>"
       f"<div class='hero-sub'>El pulso de {html.escape(aj('empresa_corto'))} en una sola vista: ingresos, planilla y rentabilidad del período, calculados directamente desde el reporte de ventas.</div>"
       f"<div class='hero-chips'>{chips}</div></div><img class='hero-img' src='{img_hero()}' alt=''/></div>")


def panel_diagnostico():
    ss = st.session_state
    if not ss.get("pdf_bytes"):
        return
    meta = ss.get("pdf_meta") or {}
    with st.expander("🔬 Diagnóstico de lectura del reporte", expanded=not ss.get("pdf_ok", False)):
        if ss.get("pdf_error"):
            st.error(ss["pdf_error"])
        chips = (chip(f"📄 {meta.get('paginas', '—')} página(s)") + chip(f"🧭 {meta.get('estrategia', '—')}")
                 + chip(f"📋 {meta.get('filas_leidas', 0)} filas leídas") + chip(f"✅ {meta.get('servicios', 0)} servicios válidos", "green"))
        if meta.get("excluidas_total"):
            chips += chip(f"➖ {meta['excluidas_total']} filas de total excluidas", "sky")
        if meta.get("rellenadas"):
            chips += chip(f"↪️ {meta['rellenadas']} filas asignadas al profesional anterior", "indigo")
        if meta.get("sin_precio"):
            chips += chip(f"⚠️ {meta['sin_precio']} filas sin precio legible", "amber")
        if meta.get("sin_profesional"):
            chips += chip(f"⚠️ {meta['sin_profesional']} filas sin profesional ({usd(meta.get('monto_sin_profesional', 0))})", "amber")
        if meta.get("periodo_fuente"):
            chips += chip(f"📅 Período tomado de: {meta['periodo_fuente']}", "indigo")
        chips += chip("💳 Formas de pago leídas" if ss.get("pagos_ok") else "💳 Sin columnas de forma de pago", "green" if ss.get("pagos_ok") else "")
        md(f"<div class='chips'>{chips}</div>")

        cols_pdf = meta.get("columnas") or []
        if cols_pdf:
            md(titulo_seccion("Columnas del reporte", "Se detectan solas. Si alguna no es la correcta, elígela aquí y todo se recalcula."))
            opciones = [AUTO] + cols_pdf
            a, b, c, d, e = st.columns(5)
            a.selectbox("👤 Profesional", opciones, key="map_prof", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_prof') or '—'}")
            b.selectbox("💲 Precio", opciones, key="map_precio", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_pre') or '—'}")
            c.selectbox("🙍 Cliente", opciones, key="map_cliente", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_cli') or '—'}")
            d.selectbox("💆 Servicio", opciones, key="map_servicio", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_ser') or '—'}")
            e.selectbox("🏪 E-commerce", opciones, key="map_marca", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_marca') or '—'}")
            st.checkbox("Asignar filas sin nombre al profesional de arriba (reportes agrupados)", value=True, key="map_ffill", on_change=reprocesar_pdf)

        if ss.get("resumen_pdf"):
            md(titulo_seccion("Coincidencias por colaborador", "Cuántos servicios del PDF se asignaron a cada persona según su alias."))
            df_res = pd.DataFrame.from_dict(ss["resumen_pdf"], orient="index").reset_index().rename(columns={"index": "Colaborador"})
            st.dataframe(df_res.style.format({"Ventas": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
        if meta.get("sin_asignar"):
            st.warning(f"Hay {len(meta['sin_asignar'])} nombre(s) en el PDF que no coinciden con ningún colaborador: sus ventas cuentan en los ingresos, pero no generan pago. "
                       "Agrégalos como alias en Configuración → Personal y sueldos (por ejemplo MAYDELY|MEY).")
            st.dataframe(pd.DataFrame(meta["sin_asignar"]).style.format({"Ventas": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
        if meta.get("multiples"):
            st.warning(f"{meta['multiples']} servicio(s) coinciden con más de un colaborador: revisa que los alias no se repitan.")
        if ss.get("reporte_df") is not None:
            md(titulo_seccion("Vista previa de servicios leídos"))
            formatos = {c: "${:,.2f}" for c in ("Precio", "Extra", "Efectivo", "Transferencia", "POS") if c in ss["reporte_df"].columns}
            st.dataframe(ss["reporte_df"].head(25).style.format(formatos), hide_index=True, **ancho(st.dataframe))
        elif meta.get("muestra_texto"):
            md(titulo_seccion("Texto extraído del PDF", "Útil para revisar el formato si no se reconoce la tabla."))
            st.code(meta["muestra_texto"], language=None)


def panel_sincronizacion():
    ss = st.session_state
    with tarjeta("sync"):
        md(titulo_seccion("📥 Reporte de ventas", "Sube el PDF del período: la app detecta si es quincena o mes y calcula la planilla de una sola vez."))
        c1, c2 = columnas([3, 1], "center")
        with c1:
            archivo_subido = st.file_uploader("Reporte de ventas (PDF)", type=["pdf"], key=f"pdf_uploader_{ss['uploader_nonce']}", label_visibility="collapsed")
        with c2:
            st.button("🔄 Recalcular", on_click=reprocesar_pdf, disabled=not ss.get("pdf_bytes"), **ancho(st.button))
            st.button("🧹 Limpiar reporte", on_click=limpiar_reporte_pdf, **ancho(st.button))

        if archivo_subido is not None:
            pdf_bytes = archivo_subido.getvalue()
            pdf_hash = hashlib.md5(pdf_bytes).hexdigest()
            if pdf_hash != ss["pdf_hash"]:
                ss["pdf_hash"], ss["pdf_nombre"], ss["pdf_bytes"] = pdf_hash, archivo_subido.name, pdf_bytes
                ss["quincenas_manual"] = None
                for k in CLAVES_MAPEO:
                    ss.pop(k, None)
                with st.spinner("Analizando el reporte de ventas..."):
                    ok, msg = ejecutar_procesamiento()
                st.toast(msg, icon="✅" if ok else "⚠️")

        if ss.get("pdf_bytes"):
            pi = ss.get("periodo_info")
            q = ss["quincenas_multiplicador"]
            if pi:
                p1, p2 = columnas([3, 1], "center")
                with p1:
                    md(f"<div class='periodo'><div class='periodo-ico'>📅</div><div><div class='periodo-t'>{html.escape(pi['etiqueta'])}</div>"
                       f"<div class='periodo-s'>Del {pi['inicio']} al {pi['fin']} · {pi['dias']} días · detectado en el {html.escape(pi['fuente'])}</div></div>"
                       f"<div class='periodo-q'><b>{q:g}</b><span>{'quincena' if q == 1 else 'quincenas'} a pagar</span></div></div>")
                with p2:
                    sembrar("map_quincenas", ss.get("quincenas_manual") or AUTO)
                    st.selectbox("¿Ajustar quincenas?", [AUTO, 1.0, 2.0, 3.0, 4.0], key="map_quincenas", on_change=cambiar_quincenas,
                                 format_func=lambda v: f"Automático ({pi['quincenas']})" if v == AUTO else f"{v:g} quincena(s)")
            chips = ""
            if ss.get("pdf_nombre"):
                chips += chip(f"📄 {html.escape(ss['pdf_nombre'])}", "green" if ss.get("pdf_ok") else "red")
            if ss.get("pdf_ok"):
                chips += chip(f"🧾 {ss['pdf_meta'].get('servicios', 0)} servicios · {usd(ss['total_ingresos_pdf'])} en ventas", "green")
                asignados = sum(1 for r in ss["resumen_pdf"].values() if r.get("Servicios"))
                chips += chip(f"👥 {asignados} colaborador(es) con servicios", "indigo")
                if ss["pdf_meta"].get("sin_asignar"):
                    chips += chip(f"⚠️ {len(ss['pdf_meta']['sin_asignar'])} nombre(s) sin asignar · ver diagnóstico", "amber")
            md(f"<div class='chips'>{chips}</div>")
        panel_diagnostico()
    espacio(6)


def filas_historial(datos_emp):
    ss = st.session_state
    pi = ss.get("periodo_info") or {}
    guardado = ahora_sv().strftime("%Y-%m-%d %H:%M")
    return [{"Guardado": guardado, "Periodo": ss["periodo_texto"], "Desde": pi.get("inicio", ""), "Hasta": pi.get("fin", ""),
             "Quincenas": ss["quincenas_multiplicador"], "Colaborador": d["Colaborador"], "Forma_Pago": d["Modalidad"],
             "Servicios": d["Servicios"], "Ventas": round(d["Ventas PDF"], 2), "Sueldo_Neto": round(d["Base Neta"], 2),
             "Comision": round(d["Com Neta"], 2), "Bonos": round(d["Bonos"], 2), "Descuentos": round(d["Desc"], 2),
             "Renta": round(d["Renta"], 2), "Total": round(d["Total"], 2)} for d in datos_emp]


# =====================================================================
# 17. PÁGINAS
# =====================================================================
ss = st.session_state
pagina = ss["pagina"]

if pagina == "Planillas":
    encabezado_pagina("💼", "Planillas", f"Sube el reporte de ventas y la planilla del período se calcula sola: sueldos, extras sobre {usd(umbral_extra())}, porcentajes y renta.")
    panel_sincronizacion()

    contenedor_pago = st.container()

    espacio(4)
    md(titulo_seccion("✏️ Ajustes y detalle por colaborador", "Cambia la forma de pago o el porcentaje, agrega bonos o descuentos y revisa cada servicio del PDF."))
    datos_emp = []
    for emp, info in ss["empleados"].items():
        mod = info.get("mod", MOD_FIJO)
        with st.expander(f"👤 {emp}  ·  {forma_pago_texto(info)}"):
            r = ss.get("resumen_pdf", {}).get(emp)
            if r:
                chips = chip(f"🧾 {r['Servicios']} servicios", "indigo") + chip(f"💰 Ventas {usd(r['Ventas'])}", "green")
                if "Estándar" in mod:
                    chips += chip(f"✨ {r['Servicios con extra']} con extra · {usd(ss.get(f'extra_bruto_{emp}', 0))}", "amber")
                    chips += chip(f"📣 Pauta {aj('retencion_pub_pct'):g}% {usd(ss.get(f'ret_pub_{emp}', 0))}", "sky")
            else:
                chips = chip("Sin datos del reporte de ventas")
            if "Porcentaje" in mod:
                chips = chip(f"📈 Gana el {float(info.get('porc', 0) or 0):g}% de lo que vende", "violet") + chips
            else:
                chips = chip(f"🪙 Sueldo neto {usd(sueldo_neto_de(info))} por quincena", "violet") + chips
            md(f"<div class='chips'>{chips}</div>")

            # --- Forma de pago (cambio rápido; se guarda en el personal) ---
            k_mod, k_porc = f"fp_mod_{emp}", f"fp_porc_{emp}"
            sembrar(k_mod, mod if mod in MODALIDADES else MOD_FIJO)
            f1, f2, f3 = columnas([1.5, 1, 1], "bottom")
            f1.selectbox("Forma de pago", MODALIDADES, key=k_mod, format_func=lambda m: MOD_ETIQUETAS.get(m, m))
            mod_sel = ss[k_mod]
            usa_porc = mod_sel == MOD_PORCENTAJE or (mod_sel == MOD_FIJO and info.get("rol") == "Operativo")
            porc_actual = float(info.get("porc", 0) or 0)
            if usa_porc:
                sembrar(k_porc, porc_actual if porc_actual > 0 else (20.0 if mod_sel == MOD_PORCENTAJE else 0.0))
                f2.number_input("% de comisión" if mod_sel == MOD_PORCENTAJE else "Comisión adicional (%)", min_value=0.0, max_value=100.0,
                                step=1.0, format="%.0f", key=k_porc)
            hay_cambio = mod_sel != mod or (usa_porc and abs(float(ss.get(k_porc, porc_actual) or 0) - porc_actual) > 1e-9)
            f3.button("Aplicar cambio", key=f"fp_btn_{emp}", on_click=aplicar_forma_pago, args=(emp,),
                      type="primary" if hay_cambio else "secondary", disabled=not hay_cambio, **ancho(st.button))
            st.caption(MOD_AYUDA.get(mod_sel, ""))

            # --- Montos del período ---
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                campo_persistente(st.number_input, "Sueldo neto del período ($)", f"base_net_{emp}", f"ui_b_net_{emp}", conv=float, step=0.01, format="%.2f",
                                  help="Sueldo neto quincenal (Configuración) × quincenas del período. La app calcula el bruto y la renta.")
                campo_persistente(st.number_input, "Comisiones ($)", f"com_{emp}", f"ui_c_{emp}", conv=float, step=0.01, format="%.2f",
                                  help="Sueldo + extras: (precio − precio mínimo) menos la pauta, por servicio. Porcentaje: ventas × %.")
            with c2:
                campo_persistente(st.number_input, "Bonos ($)", f"hex_{emp}", f"ui_h_{emp}", conv=float, step=0.01, format="%.2f")
                campo_persistente(st.number_input, "Descuentos ($)", f"desc_{emp}", f"ui_d_{emp}", conv=float, step=0.01, format="%.2f")
            with c3:
                campo_persistente(st.text_input, "Notas", f"notas_{emp}", f"n_{emp}", conv=str)
                campo_persistente(st.text_input, "Correo", f"email_{emp}", f"ui_e_{emp}", conv=str)

            fila = calcular_fila_planilla(emp, info)
            md(f"<div class='neto'><div><div class='neto-label'>Total a pagar</div>"
               f"<div class='neto-formula'>Sueldo neto {usd(fila['Base Neta'])} + Comisión {usd(fila['Com Neta'])} + Bonos {usd(fila['Bonos'])} − Descuentos {usd(fila['Desc'])}</div></div>"
               f"<div class='neto-valor'>{usd(fila['Total'])}</div></div>")

            servicios = servicios_colaborador(emp, info)
            espacio(6)
            if servicios is not None and not servicios.empty:
                md(titulo_seccion(f"🧾 Servicios del período ({len(servicios)})", "Cada servicio del PDF asignado a esta persona."))
                cols_dinero = [c for c in ("Precio", "Extra bruto", "Retención pauta", "Comisión neta") if c in servicios.columns]
                resumen_serv = chip(f"Ventas {usd(servicios['Precio'].sum())}", "green")
                if "Extra bruto" in servicios.columns:
                    resumen_serv += chip(f"Extra {usd(servicios['Extra bruto'].sum())}", "amber")
                    resumen_serv += chip(f"Pauta {usd(servicios['Retención pauta'].sum())}", "sky")
                if "Comisión neta" in servicios.columns:
                    resumen_serv += chip(f"Comisión {usd(servicios['Comisión neta'].sum())}", "indigo")
                md(f"<div class='chips'>{resumen_serv}</div>")
                st.dataframe(servicios.style.format("${:,.2f}", subset=cols_dinero), hide_index=True, height=min(420, 38 + 35 * len(servicios)), **ancho(st.dataframe))
            elif ss.get("pdf_ok"):
                md(f"<div class='chips'>{chip('No se encontraron servicios de esta persona en el reporte. Revisa su alias en Configuración.', 'amber')}</div>")
            else:
                md(f"<div class='chips'>{chip('Sube el reporte de ventas para ver el detalle de servicios.')}</div>")
        datos_emp.append(fila)

    if datos_emp:
        with contenedor_pago:
            total_pagar = sum(d["Total"] for d in datos_emp)
            fila_kpis([
                kpi_html("🧾", "Total a pagar", usd(total_pagar), f"{len(datos_emp)} colaboradores · {ss['quincenas_multiplicador']:g} quincena(s)", "indigo", "prim"),
                kpi_html("🪙", "Sueldos netos", usd(sum(d["Base Neta"] for d in datos_emp)), f"Bruto {usd(sum(d['Base Bruta'] for d in datos_emp))}", "sky"),
                kpi_html("💼", "Comisiones netas", usd(sum(d["Com Neta"] for d in datos_emp)), f"Pauta retenida {usd(sum(d['Ret Pub'] for d in datos_emp))}", "green"),
                kpi_html("🏛️", f"Renta ({aj('renta_pct'):g}%)", usd(sum(d["Renta"] for d in datos_emp)), "Retenida sobre los sueldos brutos", "amber"),
            ])
            if ss.get("pdf_ok"):
                espacio(4)
                render_cuadre()
            espacio(10)
            md(titulo_seccion("💵 Pago por colaborador", "Lo que debes pagarle a cada persona en este período, con el detalle del cálculo."))
            for i in range(0, len(datos_emp), 3):
                cols = st.columns(3)
                for col, f in zip(cols, datos_emp[i:i + 3]):
                    md(tarjeta_pago_html(f, ss["empleados"][f["Colaborador"]]), col)

            with tarjeta("tabla_planilla"):
                md(titulo_seccion("📊 Planilla consolidada", "Con fila de TOTAL. Descárgala o guárdala en el historial de Google Sheets como respaldo."))
                df_pl = pd.DataFrame(datos_emp)
                vista = df_pl[["Colaborador", "Modalidad", "Servicios", "Ventas PDF", "Base Bruta", "Renta", "Base Neta", "Extra", "Ret Pub", "Com Neta", "Bonos", "Desc", "Total"]].rename(columns={
                    "Modalidad": "Forma de pago", "Ventas PDF": "Ventas", "Base Bruta": "Sueldo bruto", "Base Neta": "Sueldo neto", "Extra": "Extra bruto",
                    "Ret Pub": "Pauta", "Com Neta": "Comisión neta", "Desc": "Descuentos", "Total": "Total a pagar"})
                cols_num = [c for c in vista.columns if c not in ("Colaborador", "Forma de pago", "Servicios")]
                totales = {c: float(vista[c].sum()) for c in cols_num}
                totales.update({"Colaborador": "TOTAL", "Forma de pago": "", "Servicios": int(vista["Servicios"].sum())})
                vista = pd.concat([vista, pd.DataFrame([totales])], ignore_index=True)
                estilo_total = f"font-weight:700;background-color:{tema()['p50']};color:{tema()['p600']}"

                def _resaltar_total(fila_tabla):
                    return [estilo_total if fila_tabla["Colaborador"] == "TOTAL" else ""] * len(fila_tabla)

                st.dataframe(vista.style.format("${:,.2f}", subset=cols_num).apply(_resaltar_total, axis=1), hide_index=True, **ancho(st.dataframe))
                d1, d2, d3 = st.columns(3)
                with d1:
                    csv = df_pl.drop(columns=["Email", "DUI", "Cuenta"]).to_csv(index=False).encode("utf-8-sig")
                    st.download_button("⬇️ Excel / CSV", data=csv, file_name=f"Planilla_{ahora_sv().strftime('%Y-%m-%d')}.csv", mime="text/csv", **ancho(st.download_button))
                with d2:
                    st.download_button("⬇️ Planilla en PDF", data=generar_planilla_pdf(datos_emp, ss["periodo_texto"]),
                                       file_name=f"Planilla_{ahora_sv().strftime('%Y-%m-%d')}.pdf", mime="application/pdf", **ancho(st.download_button))
                with d3:
                    guardar_hist = st.button("☁️ Guardar en historial", type="primary", disabled=not ss.get("pdf_ok"), **ancho(st.button),
                                             help="Guarda el resultado de esta planilla en la hoja «Historial_Planillas». Si el período ya existía, se reemplaza.")
                if guardar_hist:
                    filas_h = filas_historial(datos_emp)
                    ss["historial_local"][ss["periodo_texto"]] = filas_h
                    ss.pop("hist_cache", None)
                    if guardar_historial_planilla(filas_h, ss["periodo_texto"]):
                        registrar_auditoria("Planilla guardada en historial", ss["periodo_texto"])
                        st.toast("Planilla guardada en el historial de Google Sheets.", icon="☁️")
                    else:
                        st.error("No se pudo guardar en Google Sheets (quedó guardada solo en esta sesión). Revisa la conexión en Configuración → Respaldo y conexión.")

        espacio(10)
        c_ind, c_mas = st.columns([1.25, 1])
        with c_ind:
            with tarjeta("recibos"):
                md(titulo_seccion("🧾 Recibo individual", "Genera, descarga o envía por Gmail el comprobante de un colaborador."))
                e_sel = st.selectbox("Seleccionar colaborador", list(ss["empleados"].keys()), key="recibo_colaborador")
                e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)
                if st.button("👁️ Generar recibo PDF", type="primary"):
                    with st.spinner("Generando comprobante..."):
                        ss['t_pdf'] = generar_recibo_pdf(e_dat, ss['periodo_texto'])
                        ss['t_path'] = nombre_archivo("Recibo", e_sel)
                        ss['t_emp'] = e_sel
                    st.toast(f"Recibo de {e_sel} generado.", icon="📄")
                if 't_pdf' in ss and ss.get('t_emp') == e_sel:
                    b1, b2 = st.columns(2)
                    with b1:
                        st.download_button("📄 Descargar PDF", data=ss['t_pdf'], file_name=ss['t_path'], mime="application/pdf", **ancho(st.download_button))
                    correo_ok = correo_valido(e_dat["Email"])
                    with b2:
                        enviar = st.button("🚀 Enviar por Gmail", disabled=not correo_ok, **ancho(st.button))
                    if not correo_ok:
                        st.warning("⚠️ Este colaborador no tiene un correo válido configurado.")
                    if enviar:
                        with st.spinner("Enviando comprobante por Gmail..."):
                            try:
                                servidor_smtp, remitente = abrir_smtp()
                                msg = mensaje_recibo(remitente, e_dat, ss['t_pdf'], ss['t_path'], ss['periodo_texto'])
                                servidor_smtp.sendmail(remitente, e_dat["Email"], msg.as_string())
                                servidor_smtp.quit()
                                registrar_auditoria("Recibo de Pago", e_sel)
                                st.toast(f"Comprobante enviado a {e_dat['Email']}", icon="📨")
                                st.balloons()
                            except Exception as ex:
                                st.error(f"Error al enviar correo. Verifique los secretos `EMAIL_USER` y `EMAIL_PASS`: {ex}")

        with c_mas:
            with tarjeta("masivo"):
                destinatarios = [d for d in datos_emp if correo_valido(d["Email"])]
                md(titulo_seccion("📨 Envío masivo", "Envía su recibo a todos los colaboradores con correo válido."))
                md(f"<div class='chips'>{chip(f'✅ {len(destinatarios)} con correo', 'green')}{chip(f'⚠️ {len(datos_emp) - len(destinatarios)} sin correo', 'amber')}</div>")
                confirmar = st.checkbox(f"Confirmo el envío de {len(destinatarios)} recibos", key="confirmar_masivo")
                if st.button("📨 Enviar todos los recibos", type="primary", disabled=not (confirmar and destinatarios), **ancho(st.button)):
                    progreso = st.progress(0.0, text="Conectando con Gmail...")
                    enviados, errores = 0, []
                    try:
                        servidor_smtp, remitente = abrir_smtp()
                        for i, d in enumerate(destinatarios, 1):
                            try:
                                adjunto = nombre_archivo("Recibo", d["Colaborador"])
                                msg = mensaje_recibo(remitente, d, generar_recibo_pdf(d, ss['periodo_texto']), adjunto, ss['periodo_texto'])
                                servidor_smtp.sendmail(remitente, d["Email"], msg.as_string())
                                registrar_auditoria("Recibo de Pago (envío masivo)", d["Colaborador"])
                                enviados += 1
                            except Exception as ex:
                                errores.append(f"{d['Colaborador']}: {ex}")
                            progreso.progress(i / len(destinatarios), text=f"Enviando {i} de {len(destinatarios)}...")
                        servidor_smtp.quit()
                    except Exception as ex:
                        errores.append(f"Conexión con Gmail: {ex}")
                    progreso.empty()
                    if enviados:
                        st.toast(f"{enviados} recibos enviados correctamente.", icon="📨")
                        st.balloons()
                    if errores:
                        st.error("No se pudieron enviar algunos recibos:\n\n" + "\n".join(f"- {e}" for e in errores))

elif pagina == "Ecommerce":
    encabezado_pagina("🏪", "E-commerce", "Lo que generó cada e-commerce en el período: ventas, servicios, formas de pago, profesionales y clientes, verificado contra el PDF.")
    rep = ss.get("reporte_df")
    if rep is None or rep.empty:
        estado_vacio(img_reporte(), "Sube un reporte para ver los e-commerce", "El reporte se carga desde Planillas o desde el Panel general.",
                     ["Ve a Planillas y sube el PDF de ventas.", "Vuelve aquí para ver cada e-commerce por separado.", "Revisa la verificación contra el PDF."])
    else:
        marcas = marcas_ordenadas(dict.fromkeys(rep["Marca"].tolist()))
        total = float(rep["Precio"].sum())
        md("<div class='chips'>" + chip(f"📅 {html.escape(ss['periodo_texto'])}", "indigo") + chip(f"🧾 {len(rep)} servicios · {usd(total)}", "green") + "</div>")
        for i in range(0, len(marcas), 4):
            cols = st.columns(4)
            for col, marca in zip(cols, marcas[i:i + 4]):
                sub = rep[rep["Marca"] == marca]
                ventas = float(sub["Precio"].sum())
                pct = ventas / total * 100 if total else 0.0
                color = COLORES_MARCA.get(marca, "#64748B")
                ticket = ventas / len(sub) if len(sub) else 0.0
                md(f"<div class='marca' style='--c:{color}'><div class='marca-top'><div class='marca-nom'><i></i>{html.escape(marca)}</div>"
                   f"<span class='marca-pct'>{pct:.1f}%</span></div><div class='marca-val'>{usd(ventas)}</div>"
                   f"<div class='marca-sub'>{len(sub)} servicios · ticket promedio {usd(ticket)}</div>"
                   f"<div class='marca-bar'><span style='width:{pct:.1f}%'></span></div></div>", col)

        with tarjeta("cuadre_ecom"):
            md(titulo_seccion("🔎 Verificación contra el PDF", "Compara lo que suma la app con los totales que imprime el reporte (general, por e-commerce y por profesional)."))
            render_cuadre(expandido=True)

        g1, g2 = st.columns([1, 1.25])
        with g1:
            with tarjeta("ecom_donut"):
                md(titulo_seccion("Participación en ventas", "Peso de cada e-commerce en el total"))
                st.plotly_chart(grafico_donut_marcas({m: float(rep[rep["Marca"] == m]["Precio"].sum()) for m in marcas}), config=PLOTLY_CONFIG, key="ch_ecom_donut", **ancho(st.plotly_chart))
        with g2:
            with tarjeta("ecom_pagos"):
                if ss.get("pagos_ok"):
                    md(titulo_seccion("Formas de pago por e-commerce", "Efectivo, transferencia y POS (tarjeta)"))
                    st.plotly_chart(grafico_pagos_marcas(rep, marcas), config=PLOTLY_CONFIG, key="ch_ecom_pagos", **ancho(st.plotly_chart))
                else:
                    md(titulo_seccion("Formas de pago por e-commerce", "Este reporte no trae columnas de efectivo y transferencia."))

        if rep["Fecha"].notna().any() and rep["Fecha"].nunique() >= 2:
            with tarjeta("ecom_tendencia"):
                md(titulo_seccion("Ventas diarias por e-commerce", "Pasa el cursor (o toca) un día para comparar"))
                st.plotly_chart(grafico_tendencia_marcas(rep, marcas), config=PLOTLY_CONFIG, key="ch_ecom_tend", **ancho(st.plotly_chart))

        with tarjeta("ecom_matriz"):
            md(titulo_seccion("👥 ¿Quién generó qué en cada e-commerce?", "Ventas o cantidad de servicios de cada profesional del PDF, por e-commerce."))
            modo_matriz = st.radio("Ver", ["Ventas", "Servicios"], horizontal=True, key="matriz_modo", label_visibility="collapsed")
            base = rep.assign(Profesional=rep["Profesional"].map(nombre_bonito))
            if modo_matriz == "Ventas":
                matriz = base.pivot_table(index="Profesional", columns="Marca", values="Precio", aggfunc="sum", fill_value=0.0)
            else:
                matriz = base.pivot_table(index="Profesional", columns="Marca", values="Precio", aggfunc="count", fill_value=0)
            matriz = matriz[[m for m in marcas if m in matriz.columns]]
            matriz["Total"] = matriz.sum(axis=1)
            matriz = matriz.sort_values("Total", ascending=False)
            matriz.loc["TOTAL"] = matriz.sum()
            if modo_matriz == "Ventas":
                st.dataframe(matriz.style.format("${:,.2f}"), **ancho(st.dataframe))
            else:
                st.dataframe(matriz.astype(int), **ancho(st.dataframe))

        md(titulo_seccion("🏪 Detalle por e-commerce", "Elige un e-commerce para ver sus servicios, profesionales, clientes y formas de pago."))
        pestanas = st.tabs(marcas)
        for pestana, marca in zip(pestanas, marcas):
            with pestana:
                sub = rep[rep["Marca"] == marca]
                ventas = float(sub["Precio"].sum())
                clientes = sub["Cliente"].map(_clave_nombre)
                clientes = clientes[clientes != ""]
                recurrentes = int((clientes.value_counts() > 1).sum())
                fila_kpis([
                    kpi_html("💰", "Ventas", usd(ventas), f"{(ventas / total * 100 if total else 0):.1f}% del total", "indigo"),
                    kpi_html("🧾", "Servicios", str(len(sub)), f"Ticket promedio {usd(ventas / len(sub) if len(sub) else 0)}", "sky"),
                    kpi_html("🙋", "Clientes únicos", str(int(clientes.nunique())), f"{recurrentes} volvieron más de una vez", "green"),
                    kpi_html("✨", "Extras generados", usd(float(sub["Extra"].sum())), f"Excedente sobre {usd(umbral_extra())}", "amber"),
                ])
                if ss.get("pagos_ok"):
                    md("<div class='chips'>" + chip(f"💵 Efectivo {usd(sub['Efectivo'].sum())}") + chip(f"🏦 Transferencia {usd(sub['Transferencia'].sum())}")
                       + chip(f"💳 POS {usd(sub['POS'].sum())}") + "</div>")
                espacio(6)
                t1, t2 = st.columns([1.15, 1])
                with t1:
                    with tarjeta(f"ecom_top_{_clave_nombre(marca).lower()}"):
                        md(titulo_seccion("Servicios más vendidos", "Top 8 por ingresos"))
                        if (sub["Servicio"].str.strip() != "").any():
                            st.plotly_chart(grafico_top_servicios(sub, COLORES_MARCA.get(marca)), config=PLOTLY_CONFIG, key=f"ch_top_{_clave_nombre(marca)}", **ancho(st.plotly_chart))
                with t2:
                    with tarjeta(f"ecom_prof_{_clave_nombre(marca).lower()}"):
                        md(titulo_seccion("Profesionales", "Quién atendió en este e-commerce"))
                        profs = (sub.assign(Profesional=sub["Profesional"].map(nombre_bonito))
                                 .groupby("Profesional").agg(Servicios=("Precio", "size"), Ventas=("Precio", "sum")).sort_values("Ventas", ascending=False).reset_index())
                        profs["Ticket"] = profs["Ventas"] / profs["Servicios"]
                        st.dataframe(profs.style.format({"Ventas": "${:,.2f}", "Ticket": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
                with st.expander(f"📋 Todos los servicios de {marca} ({len(sub)})"):
                    detalle = sub.assign(Fecha=sub["Fecha"].dt.strftime("%d/%m/%Y").fillna("—"), Profesional=sub["Profesional"].map(nombre_bonito))
                    columnas_det = [c for c in ("Fecha", "Cliente", "Servicio", "Profesional", "Precio", "Efectivo", "Transferencia", "POS") if c in detalle.columns]
                    detalle = detalle[columnas_det]
                    formatos = {c: "${:,.2f}" for c in ("Precio", "Efectivo", "Transferencia", "POS") if c in detalle.columns}
                    st.dataframe(detalle.style.format(formatos), hide_index=True, **ancho(st.dataframe))
                    st.download_button(f"⬇️ Descargar servicios de {marca} (CSV)", data=detalle.to_csv(index=False).encode("utf-8-sig"),
                                       file_name=f"Servicios_{nombre_archivo('', marca).strip('_').replace('.pdf', '')}.csv", mime="text/csv",
                                       key=f"dl_ecom_{_clave_nombre(marca)}")

elif pagina == "Dashboard":
    if aj("mostrar_hero"):
        hero_dashboard()
    else:
        encabezado_pagina("📊", "Panel general", "Ingresos, planilla y rentabilidad del período.")
    panel_sincronizacion()

    if ss["total_ingresos_pdf"] > 0:
        filas = calcular_planilla()
        costo_planilla = sum(f["Total"] for f in filas)
        ingresos = float(ss["total_ingresos_pdf"])
        utilidad = ingresos - costo_planilla
        margen = (utilidad / ingresos * 100.0) if ingresos else 0.0
        rep_df = ss.get("reporte_df")
        n_serv = int(len(rep_df)) if rep_df is not None else 0
        ticket = ingresos / n_serv if n_serv else 0.0
        extras_total = sum(ss["extras_por_marca"].values())
        renta_total = sum(f["Renta"] for f in filas)
        comisiones_total = sum(f["Com Neta"] for f in filas)

        fila_kpis([
            kpi_html("💰", "Ingresos brutos", usd(ingresos), f"{n_serv} servicios · ticket promedio {usd(ticket)}", "indigo"),
            kpi_html("👥", "Planilla a pagar", usd(costo_planilla), f"{(costo_planilla / ingresos * 100 if ingresos else 0):.1f}% de los ingresos", "sky"),
            kpi_html("🏦", "Utilidad estimada", usd(utilidad), "Ingresos − planilla", "green" if utilidad >= 0 else "red", "pos" if utilidad >= 0 else "neg"),
            kpi_html("📈", "Margen neto", f"{margen:,.1f}%", "Sobre ingresos brutos", "violet", "pos" if margen >= 0 else "neg"),
        ])
        espacio(12)
        if ss.get("pagos_ok") and rep_df is not None:
            fila_kpis([
                kpi_html("💵", "Efectivo", usd(rep_df["Efectivo"].sum()), f"{(rep_df['Efectivo'].sum() / ingresos * 100 if ingresos else 0):.1f}% de las ventas", "green"),
                kpi_html("🏦", "Transferencias", usd(rep_df["Transferencia"].sum()), f"{(rep_df['Transferencia'].sum() / ingresos * 100 if ingresos else 0):.1f}% de las ventas", "violet"),
                kpi_html("💳", "POS (tarjeta)", usd(rep_df["POS"].sum()), f"{(rep_df['POS'].sum() / ingresos * 100 if ingresos else 0):.1f}% de las ventas", "red"),
                kpi_html("✨", "Extras generados", usd(extras_total), f"Excedente sobre {usd(umbral_extra())} por servicio", "amber"),
            ])
        else:
            fila_kpis([
                kpi_html("✨", "Extras generados", usd(extras_total), f"Excedente sobre {usd(umbral_extra())} por servicio", "amber"),
                kpi_html("💼", "Comisiones netas", usd(comisiones_total), "A pagar a colaboradores", "indigo"),
                kpi_html("🏛️", "Renta retenida", usd(renta_total), f"{aj('renta_pct'):g}% sobre sueldos brutos", "sky"),
                kpi_html("🗓️", "Quincenas", f"{ss['quincenas_multiplicador']:g}", html.escape(ss["periodo_texto"]), "violet"),
            ])
        espacio(6)
        render_cuadre()
        espacio(8)

        if ss["ingresos_por_marca"]:
            g1, g2 = st.columns([1, 1.35])
            with g1:
                with tarjeta("donut"):
                    md(titulo_seccion("Ingresos por e-commerce", "Según la columna e-comer del reporte"))
                    st.plotly_chart(grafico_donut_marcas(ss["ingresos_por_marca"]), config=PLOTLY_CONFIG, key="ch_dash_donut", **ancho(st.plotly_chart))
            with g2:
                with tarjeta("barras"):
                    md(titulo_seccion("Ingresos vs. extras por e-commerce", f"Extra = excedente sobre {usd(umbral_extra())} por servicio"))
                    st.plotly_chart(grafico_barras_marcas(ss["ingresos_por_marca"], ss["extras_por_marca"]), config=PLOTLY_CONFIG, key="ch_dash_barras", **ancho(st.plotly_chart))

        ventas_colab = {emp: ss.get(f"serv_tot_{emp}", 0.0) for emp in ss["empleados"].keys()}
        hay_servicios = rep_df is not None and (rep_df["Servicio"].str.strip() != "").any()
        h1, h2 = st.columns(2) if hay_servicios else (st.container(), None)
        if any(v > 0 for v in ventas_colab.values()):
            with h1:
                with tarjeta("colaboradores"):
                    md(titulo_seccion("Ventas por colaborador", "Servicios facturados en el período"))
                    st.plotly_chart(grafico_colaboradores(ventas_colab), config=PLOTLY_CONFIG, key="ch_dash_colab", **ancho(st.plotly_chart))
        if hay_servicios and h2 is not None:
            with h2:
                with tarjeta("top_servicios"):
                    md(titulo_seccion("Servicios más rentables", "Top 8 por ingresos"))
                    st.plotly_chart(grafico_top_servicios(rep_df), config=PLOTLY_CONFIG, key="ch_dash_top", **ancho(st.plotly_chart))

        if rep_df is not None and rep_df["Fecha"].notna().any() and rep_df["Fecha"].nunique() >= 2:
            with tarjeta("tendencia"):
                md(titulo_seccion("Tendencia de ingresos diarios", "Suma de servicios por día"))
                st.plotly_chart(grafico_tendencia(rep_df), config=PLOTLY_CONFIG, key="ch_dash_tend", **ancho(st.plotly_chart))

        with tarjeta("resumen_colab"):
            md(titulo_seccion("Resumen ejecutivo por colaborador", "Ventas, comisión y total a pagar del período"))
            df_res = pd.DataFrame([{"Colaborador": f["Colaborador"], "Forma de pago": f["Modalidad"], "Servicios": f["Servicios"], "Ventas": f["Ventas PDF"],
                                    "Comisión neta": f["Com Neta"], "Total a pagar": f["Total"]} for f in filas]).sort_values("Ventas", ascending=False)
            st.dataframe(df_res.style.format({"Ventas": "${:,.2f}", "Comisión neta": "${:,.2f}", "Total a pagar": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
    else:
        estado_vacio(img_reporte(), "Tu tablero está listo para el primer reporte", "Sube el PDF de ventas en el panel de arriba y la app calculará todo de una sola vez.",
                     ["Exporta el reporte de ventas del período en PDF.", "Arrástralo al panel «Reporte de ventas».", "Revisa la planilla: la app detecta si es quincena o mes."])


elif pagina == "Proveedores":
    encabezado_pagina("📇", "Directorio de Proveedores", "Perfil 360° de cada proveedor: contacto, datos financieros y control de contratos y auditoría.")
    proveedores = ss["proveedores"]
    nombres_provs = [nombre_proveedor(p) for p in proveedores]
    modo = ss.get("prov_modo", "ver")
    idx_edit = ss.get("prov_idx")
    if modo == "editar" and (idx_edit is None or idx_edit >= len(proveedores)):
        modo = "ver"

    if modo in ("nuevo", "editar"):
        st.button("⬅️ Volver al directorio", on_click=volver_directorio)
        es_nuevo = modo == "nuevo"
        base = {} if es_nuevo else proveedores[idx_edit]
        with tarjeta("form_prov"):
            md(titulo_seccion("➕ Nuevo proveedor" if es_nuevo else f"✏️ Editar · {html.escape(nombre_proveedor(base))}",
                              "Completa las tres secciones: contacto, datos financieros y fechas de contratos y auditoría."))
            registro = formulario_proveedor(base, "form_prov_nuevo" if es_nuevo else f"form_prov_edit_{idx_edit}",
                                            "💾 Guardar proveedor" if es_nuevo else "💾 Guardar cambios")
        if registro is not None:
            nombre_nuevo = _texto(registro.get("Nombre_Proveedor"))
            otros = [nombre_proveedor(p) for i, p in enumerate(proveedores) if es_nuevo or i != idx_edit]
            if not nombre_nuevo:
                st.error("⚠️ El nombre del proveedor es obligatorio.")
            elif nombre_nuevo in otros:
                st.error(f"⚠️ Ya existe un proveedor llamado «{nombre_nuevo}».")
            else:
                if es_nuevo:
                    nuevo = {campo: "" for campo in CAMPOS_PROVEEDOR}
                    nuevo.update(registro)
                    nuevo["ID_Proveedor"] = siguiente_id_proveedor(proveedores)
                    ss["proveedores"] = proveedores + [nuevo]
                else:
                    actualizado = dict(proveedores[idx_edit])
                    actualizado.update(registro)
                    ss["proveedores"] = proveedores[:idx_edit] + [actualizado] + proveedores[idx_edit + 1:]
                if guardar_proveedores(ss["proveedores"]):
                    notificar(f"Proveedor «{nombre_nuevo}» {'agregado' if es_nuevo else 'actualizado'}.", "✅")
                else:
                    notificar_error("El proveedor se guardó en esta sesión, pero no se pudo subir a Google Sheets.")
                ss["prov_modo"], ss["prov_idx"] = "ver", None
                ss["prov_seleccionado"] = nombre_nuevo
                st.rerun()
    else:
        col_sel, col_info, col_btn = columnas([2.2, 1.3, 1], "bottom")
        with col_sel:
            prov_seleccionado = st.selectbox("🔎 Buscar proveedor", nombres_provs, key="prov_seleccionado", placeholder="Escribe para buscar...")
        with col_info:
            alertas = sum(1 for p in proveedores if estado_contrato(p)[1] in ("red", "amber"))
            chips = chip(f"📇 {len(proveedores)} proveedores", "indigo")
            if alertas:
                chips += chip(f"⚠️ {alertas} contrato(s) por atender", "amber")
            md(f"<div class='chips'>{chips}</div>")
        with col_btn:
            st.button("➕ Nuevo proveedor", type="primary", on_click=abrir_nuevo_proveedor, **ancho(st.button))

        if prov_seleccionado:
            idx = nombres_provs.index(prov_seleccionado)
            render_perfil_proveedor(proveedores[idx], idx)
            with st.expander("📋 Ver todos los proveedores en lista"):
                lista = pd.DataFrame([{"Proveedor": nombre_proveedor(p), "Contacto": _texto(p.get("Nombre_Contacto")), "Teléfono": _texto(p.get("Telefono_1")),
                                       "Correo": _texto(p.get("Correo")), "Banco": _texto(p.get("Banco")), "Vencimiento": _texto(p.get("Fecha_Vencimiento")),
                                       "Estado": estado_contrato(p)[0]} for p in proveedores])
                st.dataframe(lista, hide_index=True, **ancho(st.dataframe))
        else:
            estado_vacio(img_directorio(), "Aún no hay proveedores", "Agrega el primero con el botón «Nuevo proveedor».")

elif pagina == "Memorándums":
    encabezado_pagina("📝", "Memorándums internos", "Genera comunicaciones oficiales en PDF, descárgalas o envíalas al correo del colaborador.")
    c_form, c_tips = st.columns([2, 1])
    with c_form:
        with tarjeta("memo"):
            emp_memo = st.selectbox("Destinatario del memorándum", list(ss["empleados"].keys()), key="memo_emp")
            asunto_memo = st.text_input("Asunto", value="Aviso Administrativo Oficial", key="memo_asunto")
            texto_memo = st.text_area("Cuerpo del memorándum", key="memo_texto", height=220)
            if st.button("📄 Generar PDF oficial", type="primary"):
                if texto_memo.strip():
                    ss['temp_memo_pdf'] = generar_memo_pdf(emp_memo, asunto_memo, texto_memo)
                    ss['temp_memo_path'] = nombre_archivo("Memorandum", emp_memo)
                    ss['temp_memo_emp'] = emp_memo
                    ss['temp_memo_asunto'] = asunto_memo
                    registrar_auditoria("Memorándum", emp_memo)
                    st.toast("Memorándum generado.", icon="📝")
                else:
                    st.toast("Escribe el contenido del memorándum.", icon="ℹ️")
            if 'temp_memo_pdf' in ss and ss.get('temp_memo_emp') == emp_memo:
                md(titulo_seccion("📤 Descargar o enviar", f"Memorándum para {html.escape(emp_memo)}"))
                bloque_envio_documento("memo", emp_memo, ss['temp_memo_pdf'], ss['temp_memo_path'],
                                       f"Memorándum: {ss.get('temp_memo_asunto', '')} | {aj('empresa_corto')}",
                                       f"Estimado/a {emp_memo},\n\nAdjunto encontrará el memorándum «{ss.get('temp_memo_asunto', '')}». Por favor, léalo con atención.\n\nAtentamente,\n{aj('firma_correo')}",
                                       "Memorándum")
    with c_tips:
        with tarjeta("memo_tips"):
            md(titulo_seccion("Buenas prácticas") + "<div class='tips'><div class='tip'><span>🎯</span>Un solo tema por memorándum; el asunto debe resumirlo.</div>"
               "<div class='tip'><span>📅</span>Indica fechas y plazos concretos cuando haya una instrucción.</div>"
               "<div class='tip'><span>📨</span>Envíalo por correo: la constancia queda en el Historial.</div>"
               "<div class='tip'><span>✍️</span>Para el expediente, imprímelo y pide la firma de recibido.</div></div>")

elif pagina == "Amonestaciones":
    encabezado_pagina("⚠️", "Faltas y amonestaciones", "Documenta incidentes, genera actas formales con firmas y envíalas por correo.")
    c_form, c_hist = st.columns([2, 1])
    with c_form:
        with tarjeta("amon"):
            emp_amon = st.selectbox("Colaborador involucrado", list(ss["empleados"].keys()), key="amon_emp")
            tipo_falta = st.selectbox("Gravedad de la falta", ["Llamada de Atención Verbal", "Amonestación Escrita Leve", "Amonestación Escrita Grave"], key="amon_tipo")
            motivo_amon = st.text_area("Detalles completos del incidente", key="amon_motivo", height=220)
            if st.button("📄 Redactar acta PDF", type="primary"):
                if motivo_amon.strip():
                    ss['temp_amon_pdf'] = generar_acta_pdf(emp_amon, tipo_falta, motivo_amon)
                    ss['temp_amon_path'] = nombre_archivo("Acta_Amonestacion", emp_amon)
                    ss['temp_amon_emp'] = emp_amon
                    ss['temp_amon_tipo'] = tipo_falta
                    registrar_auditoria(f"Acta: {tipo_falta}", emp_amon)
                    st.toast("Acta redactada.", icon="⚖️")
                else:
                    st.toast("Describe el incidente para poder redactar el acta.", icon="ℹ️")
            if 'temp_amon_pdf' in ss and ss.get('temp_amon_emp') == emp_amon:
                md(titulo_seccion("📤 Descargar o enviar", f"Acta para {html.escape(emp_amon)}"))
                bloque_envio_documento("acta", emp_amon, ss['temp_amon_pdf'], ss['temp_amon_path'],
                                       f"{ss.get('temp_amon_tipo', 'Acta de amonestación')} | {aj('empresa_corto')}",
                                       f"Estimado/a {emp_amon},\n\nAdjunto encontrará el acta de {ss.get('temp_amon_tipo', 'amonestación').lower()} levantada por la gerencia.\n\nAtentamente,\n{aj('firma_correo')}",
                                       "Acta")
    with c_hist:
        with tarjeta("amon_hist"):
            actas = [h for h in ss["historial_auditoria"] if str(h.get("Tipo Documento", "")).startswith("Acta")]
            md(titulo_seccion("Historial de actas", f"{len(actas)} registro(s)"))
            if actas:
                conteo = pd.Series([a["Destinatario"] for a in actas]).value_counts()
                md("<div class='tips'>" + "".join(f"<div class='tip'><span>👤</span><b>{html.escape(n)}</b>&nbsp;· {c} registro(s)</div>" for n, c in conteo.items()) + "</div>")
            else:
                md("<div class='tips'><div class='tip'><span>✅</span>Sin actas registradas.</div></div>")

elif pagina == "Auditoría":
    encabezado_pagina("🗂️", "Historial", "Planillas guardadas como respaldo y registro de recibos, memorándums y actas.")
    tab_planillas, tab_docs = st.tabs(["💾 Planillas guardadas", "🗂️ Documentos y envíos"])

    with tab_planillas:
        if "hist_cache" not in ss:
            ss["hist_cache"] = cargar_historial_planillas()
        registros = ss["hist_cache"]
        if registros is None:
            registros = [f for filas_h in ss["historial_local"].values() for f in filas_h]
            st.info("Sin conexión con Google Sheets: se muestran solo las planillas guardadas en esta sesión.")
        r1, _ = columnas([1, 3], "center")
        r1.button("🔄 Actualizar historial", on_click=lambda: st.session_state.pop("hist_cache", None), **ancho(st.button))
        if registros:
            df_h = pd.DataFrame(registros)
            for c in ("Ventas", "Sueldo_Neto", "Comision", "Bonos", "Descuentos", "Renta", "Total", "Servicios"):
                if c in df_h.columns:
                    df_h[c] = df_h[c].map(_a_numero).fillna(0.0)
            periodos = list(dict.fromkeys(df_h["Periodo"].tolist()))[::-1]
            periodo_sel = st.selectbox("Período", periodos, key="hist_periodo")
            sub = df_h[df_h["Periodo"] == periodo_sel]
            fila_kpis([
                kpi_html("🧾", "Total pagado", usd(sub["Total"].sum()), f"{len(sub)} colaboradores", "indigo", "prim"),
                kpi_html("💰", "Ventas del período", usd(sub["Ventas"].sum()), f"{int(sub['Servicios'].sum())} servicios", "green"),
                kpi_html("💼", "Comisiones", usd(sub["Comision"].sum()), f"Sueldos netos {usd(sub['Sueldo_Neto'].sum())}", "sky"),
                kpi_html("💾", "Guardado", html.escape(_texto(sub["Guardado"].iloc[0]) if "Guardado" in sub.columns and len(sub) else "—"), "Fecha del respaldo", "violet"),
            ])
            espacio(8)
            with tarjeta("historial_planillas"):
                vista_h = sub.drop(columns=[c for c in ("Periodo", "Guardado") if c in sub.columns]).rename(columns={
                    "Forma_Pago": "Forma de pago", "Sueldo_Neto": "Sueldo neto", "Comision": "Comisión"})
                formatos = {c: "${:,.2f}" for c in ("Ventas", "Sueldo neto", "Comisión", "Bonos", "Descuentos", "Renta", "Total") if c in vista_h.columns}
                st.dataframe(vista_h.style.format(formatos), hide_index=True, **ancho(st.dataframe))
                st.download_button("⬇️ Descargar este período (CSV)", data=sub.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"Historial_{nombre_archivo('', periodo_sel).strip('_').replace('.pdf', '')}.csv", mime="text/csv")
            if len(periodos) > 1:
                with tarjeta("historial_resumen"):
                    md(titulo_seccion("📈 Comparativo entre períodos", "Total pagado y ventas de cada planilla guardada"))
                    comp = (df_h.groupby("Periodo", sort=False).agg(Ventas=("Ventas", "sum"), Pagado=("Total", "sum"), Colaboradores=("Colaborador", "count"))
                            .reset_index().iloc[::-1])
                    comp["% de ventas"] = (comp["Pagado"] / comp["Ventas"].where(comp["Ventas"] > 0) * 100).fillna(0.0)
                    st.dataframe(comp.style.format({"Ventas": "${:,.2f}", "Pagado": "${:,.2f}", "% de ventas": "{:.1f}%"}), hide_index=True, **ancho(st.dataframe))
        else:
            estado_vacio(img_reporte(), "Todavía no hay planillas guardadas",
                         "En Planillas, después de revisar los montos, pulsa «☁️ Guardar en historial». Así queda un respaldo de cada quincena o mes.")

    with tab_docs:
        historial = ss["historial_auditoria"]
        if historial:
            df_aud = pd.DataFrame(historial)
            recibos = int(df_aud["Tipo Documento"].str.startswith("Recibo").sum())
            enviados_correo = int(df_aud["Tipo Documento"].str.contains("enviado|Recibo", case=False, regex=True).sum())
            fila_kpis([
                kpi_html("🗂️", "Registros", str(len(df_aud)), "Total registrado", "indigo"),
                kpi_html("📨", "Recibos enviados", str(recibos), "Por Gmail", "green"),
                kpi_html("📝", "Memos, actas y planillas", str(len(df_aud) - recibos), "Generados o guardados", "amber"),
                kpi_html("✉️", "Envíos por correo", str(enviados_correo), "Recibos, memos y actas", "sky"),
            ])
            espacio(12)
            with tarjeta("auditoria"):
                st.dataframe(df_aud.iloc[::-1], hide_index=True, **ancho(st.dataframe))
                st.download_button("⬇️ Exportar registro (CSV)", data=df_aud.to_csv(index=False).encode("utf-8-sig"), file_name="Auditoria.csv", mime="text/csv")
            st.caption("Con Google Sheets conectado, cada registro se guarda también en la hoja «Auditoria».")
        else:
            estado_vacio(img_reporte(), "El registro está limpio", "Los recibos enviados, memorándums, actas y planillas guardadas aparecerán aquí.")

elif pagina == "Configuración":
    encabezado_pagina("⚙️", "Configuración", "Personal y forma de pago, salario mínimo y reglas, apariencia de la app, respaldo y conexión con Google Sheets.")
    tab_p, tab_s, tab_a, tab_r = st.tabs(["👥 Personal y sueldos", "💵 Salario mínimo y reglas", "🎨 Apariencia y empresa", "☁️ Respaldo y conexión"])

    # ---------------- Personal y sueldos ----------------
    with tab_p:
        filas_p = []
        for n, i in ss["empleados"].items():
            es_porc = "Porcentaje" in i.get("mod", "")
            d = desglose_sueldo(0.0 if es_porc else sueldo_neto_de(i))
            filas_p.append({"Colaborador": n, "Cargo": i.get("cargo", ""), "Rol": i.get("rol", ""), "Forma de pago": forma_pago_texto(i),
                            "Neto quincenal": d["neto_q"], "Neto mensual": d["neto_m"], "Bruto mensual": d["bruto_m"], "Renta mensual": d["renta_m"],
                            "Correo": i.get("correo", "")})
        df_p = pd.DataFrame(filas_p)
        fila_kpis([
            kpi_html("👥", "Colaboradores", str(len(df_p)), f"{int((df_p['Rol'] == 'Operativo').sum())} operativos", "indigo"),
            kpi_html("💵", "Sueldos por quincena", usd(df_p["Neto quincenal"].sum()), "Neto, sin comisiones", "sky"),
            kpi_html("📅", "Sueldos por mes", usd(df_p["Neto mensual"].sum()), f"Bruto {usd(df_p['Bruto mensual'].sum())}", "green"),
            kpi_html("🏛️", "Renta mensual", usd(df_p["Renta mensual"].sum()), f"{aj('renta_pct'):g}% · sin AFP ni ISSS", "amber"),
        ])
        espacio(10)
        with tarjeta("personal_tabla"):
            md(titulo_seccion("Sueldos y forma de pago del personal", "Lo que se le paga a cada persona por quincena y por mes. Las comisiones y porcentajes se suman aparte en la planilla."))
            st.dataframe(df_p.style.format({"Neto quincenal": "${:,.2f}", "Neto mensual": "${:,.2f}", "Bruto mensual": "${:,.2f}", "Renta mensual": "${:,.2f}"}),
                         hide_index=True, **ancho(st.dataframe))

        espacio(10)
        opciones_emp = [NUEVO_EMP] + list(ss["empleados"].keys())
        if "fe_sel" not in ss or ss.get("fe_recargar") or ss.get("fe_sel") not in opciones_emp:
            if ss.get("fe_sel") not in opciones_emp:
                ss["fe_sel"] = NUEVO_EMP
            cargar_form_empleado()
            ss["fe_recargar"] = False
        info_sel = ss["empleados"].get(ss.get("fe_sel"), {})
        c_form, c_prev = st.columns([1.7, 1])
        with c_form:
            with tarjeta("form_emp"):
                md(titulo_seccion("➕ Agregar o ✏️ editar colaborador", "Elige una persona para editarla, o «Nuevo colaborador» para registrar a alguien."))
                st.selectbox("Colaborador", opciones_emp, key="fe_sel", on_change=cargar_form_empleado)
                a, b, c = st.columns([1.4, 1.2, 1])
                a.text_input("Nombre completo *", key="fe_nombre")
                b.text_input("Cargo / puesto", key="fe_cargo", placeholder="Ej. Masajista, Cosmetóloga")
                c.selectbox("Rol", ROLES, key="fe_rol")

                md(titulo_seccion("Forma de pago", "Elige si la persona cobra con sueldo base o con un porcentaje de lo que vende."))
                st.radio("Forma de pago", MODALIDADES, key="fe_mod", horizontal=True, format_func=lambda m: MOD_ETIQUETAS.get(m, m),
                         on_change=cambio_forma_pago_form, label_visibility="collapsed")
                mod_form = ss.get("fe_mod", MOD_ESTANDAR)
                st.caption(MOD_AYUDA.get(mod_form, ""))
                usa_porc_form = mod_form == MOD_PORCENTAJE or (mod_form == MOD_FIJO and ss.get("fe_rol") == "Operativo")
                if usa_porc_form:
                    porc_guardado = _a_numero(info_sel.get("porc"))
                    sembrar("fe_porc", float(porc_guardado) if porc_guardado else (20.0 if mod_form == MOD_PORCENTAJE else 0.0))
                    p1, p2 = columnas([1, 2], "center")
                    p1.number_input("Porcentaje de comisión (%)" if mod_form == MOD_PORCENTAJE else "Comisión adicional sobre ventas (%)",
                                    min_value=0.0, max_value=100.0, step=1.0, format="%.0f", key="fe_porc")
                    porc_ej = float(ss.get("fe_porc") or 0)
                    md("<div class='chips'>" + chip(f"Ejemplo: si vende {usd(1000)} en el período, gana {usd(1000 * porc_ej / 100)}", "violet") + "</div>", p2)
                if mod_form != MOD_PORCENTAJE:
                    md(titulo_seccion("Sueldo base", "Escríbelo como neto por quincena o como bruto mensual (igual que el salario mínimo)."))
                    sembrar("fe_modo_sueldo", MODO_NETO_Q)
                    sembrar("fe_modo_prev", ss["fe_modo_sueldo"])
                    neto_guardado = sueldo_neto_de(info_sel) if info_sel and sueldo_neto_de(info_sel) > 0 else neto_q_desde_bruto_mensual(aj("salario_minimo"))
                    sembrar("fe_sueldo", float(neto_guardado if ss["fe_modo_sueldo"] == MODO_NETO_Q else round(neto_guardado / factor_neto() * 2, 2)))
                    a, b = columnas([1.3, 1], "bottom")
                    a.radio("Ingresar el sueldo como", [MODO_NETO_Q, MODO_BRUTO_M], key="fe_modo_sueldo", horizontal=True, on_change=convertir_modo_sueldo)
                    b.number_input("Monto", min_value=0.0, step=0.01, format="%.2f", key="fe_sueldo")
                    st.button(f"🇸🇻 Usar el salario mínimo vigente ({usd(aj('salario_minimo'))} al mes)", on_click=usar_salario_minimo)

                md(titulo_seccion("Datos de contacto y pago"))
                a, b, c = st.columns(3)
                a.text_input("Correo electrónico", key="fe_correo", placeholder="nombre@correo.com")
                b.text_input("Teléfono", key="fe_telefono")
                c.text_input("DUI", key="fe_dui", placeholder="00000000-0")
                a, b, c = st.columns(3)
                a.text_input("Banco", key="fe_banco")
                b.text_input("Cuenta bancaria", key="fe_cuenta")
                c.text_input("Fecha de ingreso", key="fe_fecha_ingreso", placeholder="dd/mm/aaaa")
                st.text_input("Alias en el reporte PDF", key="fe_alias",
                              help="Nombre con el que aparece en la columna PROFESIONAL del reporte. Varios separados con | (ej. MAYDELY|MEY). Vacío = primer nombre.")
                g1, g2, _ = st.columns([1.3, 1, 1.6])
                g1.button("💾 Guardar colaborador", type="primary", on_click=guardar_form_empleado, **ancho(st.button))
                if ss.get("fe_sel") in ss["empleados"]:
                    with g2:
                        with zona("peligro_emp"):
                            st.button("🗑️ Eliminar", on_click=pedir_borrar_empleado, key="btn_borrar_emp", **ancho(st.button))
                    if ss.get("fe_confirmar_borrar"):
                        md(f"<div class='confirmar-borrado'>⚠️ ¿Eliminar a <b>{html.escape(ss['fe_sel'])}</b> del personal? También se quitará de Google Sheets.</div>")
                        k1, k2, _ = st.columns([1.2, 1, 3])
                        with k1:
                            with zona("peligro_emp_confirmar"):
                                st.button("Sí, eliminar", on_click=eliminar_empleado, key="btn_borrar_emp_ok", **ancho(st.button))
                        with k2:
                            st.button("Cancelar", on_click=cancelar_borrar_empleado, key="btn_borrar_emp_no", **ancho(st.button))
        with c_prev:
            with tarjeta("prev_sueldo"):
                md(titulo_seccion("🧮 Vista previa del pago", "Así quedará el pago fijo de esta persona."))
                mod_form = ss.get("fe_mod", MOD_ESTANDAR)
                if mod_form == MOD_PORCENTAJE:
                    porc_prev = float(ss.get("fe_porc") or 0)
                    md(f"<div class='formula'>En <b>porcentaje de ventas</b> no hay sueldo base ni renta: la persona gana el <b>{porc_prev:g}%</b> de lo que vende en el período.<br>"
                       f"Ventas de {usd(500)} → {usd(500 * porc_prev / 100)} · Ventas de {usd(2000)} → {usd(2000 * porc_prev / 100)}</div>")
                else:
                    d = desglose_sueldo(neto_q_formulario())
                    md(tabla_sueldo_html(d))
                    minimo_q = neto_q_desde_bruto_mensual(aj("salario_minimo"))
                    minimo_txt = usd(aj("salario_minimo"))
                    if d["neto_q"] + 0.005 < minimo_q:
                        md("<div class='chips'>" + chip(f"⚠️ Por debajo del mínimo neto quincenal ({usd(minimo_q)})", "amber") + "</div>")
                    else:
                        md("<div class='chips'>" + chip(f"✅ Cumple el salario mínimo ({minimo_txt} al mes)", "green") + "</div>")
                    extra_txt = (f"Además cobra el {float(ss.get('fe_porc') or 0):g}% de lo que vende." if mod_form == MOD_FIJO and float(ss.get("fe_porc") or 0) > 0
                                 else ("Además cobra los extras de cada servicio mayor a " + usd(umbral_extra()) + "." if mod_form == MOD_ESTANDAR else "Sin comisiones."))
                    md(f"<div class='formula'>Bruto = neto ÷ {factor_neto():.2f} · Renta = bruto × {aj('renta_pct'):g}%.<br>{extra_txt}<br>"
                       f"<b>En la planilla:</b> neto quincenal × quincenas del reporte + comisiones + bonos − descuentos.</div>")

        espacio(10)
        with st.expander("📋 Edición rápida en tabla (varias personas a la vez)"):
            df_emp = pd.DataFrame([{"Nombre": n, "rol": i.get("rol", ""), "mod": i.get("mod", MOD_FIJO), "sueldo_base_neto": float(sueldo_neto_de(i)),
                                    "porc": float(i.get("porc", 0) or 0), "alias": i.get("alias", ""), "correo": i.get("correo", ""),
                                    "dui": i.get("dui", ""), "cuenta": i.get("cuenta", "")} for n, i in ss["empleados"].items()])
            df_editado = st.data_editor(
                df_emp, num_rows="dynamic", hide_index=True, key=f"editor_personal_{ss['nonce_editor_personal']}",
                column_config={
                    "Nombre": st.column_config.TextColumn("Nombre", required=True),
                    "rol": st.column_config.SelectboxColumn("Rol", options=ROLES, required=True),
                    "mod": st.column_config.SelectboxColumn("Forma de pago", options=MODALIDADES, required=True, width="medium"),
                    "sueldo_base_neto": st.column_config.NumberColumn("Sueldo neto quincenal", min_value=0.0, step=0.01, format="$%.2f"),
                    "porc": st.column_config.NumberColumn("% Comisión", min_value=0, max_value=100, step=1, format="%.0f"),
                    "alias": st.column_config.TextColumn("Alias en el PDF"),
                    "correo": st.column_config.TextColumn("Correo"),
                    "dui": st.column_config.TextColumn("DUI"),
                    "cuenta": st.column_config.TextColumn("Cuenta bancaria"),
                },
                **ancho(st.data_editor),
            )
            if st.button("💾 Guardar tabla de personal", type="primary"):
                anteriores = ss["empleados"]
                nuevos, cambiados = {}, []
                for r in df_editado.to_dict("records"):
                    nombre = _texto(r.get("Nombre"))
                    if not nombre:
                        continue
                    previo = anteriores.get(nombre, {})
                    datos_emp_tabla = dict(previo)
                    datos_emp_tabla.update({"rol": r.get("rol"), "mod": r.get("mod"), "porc": r.get("porc"), "sueldo_base_neto": r.get("sueldo_base_neto"),
                                            "alias": r.get("alias"), "correo": r.get("correo"), "dui": r.get("dui"), "cuenta": r.get("cuenta")})
                    info_n = _empleado_normalizado(datos_emp_tabla)
                    nuevos[nombre] = info_n
                    if (not previo or previo.get("rol") != info_n["rol"] or previo.get("mod") != info_n["mod"]
                            or sueldo_neto_de(previo) != info_n["sueldo_base_neto"]):
                        cambiados.append(nombre)
                if not nuevos:
                    st.error("Debe existir al menos un colaborador con nombre.")
                else:
                    if _aplicar_cambios_personal(nuevos, cambiados):
                        notificar("Personal y sueldos actualizados. Planilla recalculada.", "✅")
                    else:
                        notificar_error("No se pudo sincronizar con Google Sheets. Los cambios de personal quedaron solo en esta sesión.")
                    ss["fe_recargar"] = True
                    st.rerun()

    # ---------------- Salario mínimo y reglas ----------------
    with tab_s:
        c1, c2 = st.columns([1.25, 1])
        with c1:
            with tarjeta("salmin"):
                md(titulo_seccion("🇸🇻 Salario mínimo de referencia", FUENTE_SALARIO_MINIMO))
                st.number_input("Salario mínimo mensual (bruto)", min_value=0.0, step=0.01, format="%.2f", value=float(aj("salario_minimo")),
                                key="aj_salario_minimo", on_change=actualizar_ajuste, args=("salario_minimo", "aj_salario_minimo"))
                md(tabla_sueldo_html(desglose_sueldo(neto_q_desde_bruto_mensual(aj("salario_minimo")))))
                st.caption("Sin AFP ni ISSS: solo se retiene la renta configurada. Antes de cambiar el monto, confírmalo con el Ministerio de Trabajo (MTPS).")
                confirmar_min = st.checkbox("Confirmo actualizar el sueldo de los operativos con sueldo base al salario mínimo", key="conf_aplicar_min")
                if st.button("Aplicar salario mínimo a los operativos", type="primary", disabled=not confirmar_min):
                    neto_min = neto_q_desde_bruto_mensual(aj("salario_minimo"))
                    nuevos, cambiados = {}, []
                    for n, i in ss["empleados"].items():
                        i = dict(i)
                        if i.get("rol") == "Operativo" and "Porcentaje" not in i.get("mod", ""):
                            i["sueldo_base_neto"] = neto_min
                            cambiados.append(n)
                        nuevos[n] = i
                    if _aplicar_cambios_personal(nuevos, cambiados):
                        notificar(f"Sueldo de {len(cambiados)} operativo(s) actualizado a {usd(neto_min)} netos por quincena.", "✅")
                    else:
                        notificar_error("Los sueldos se actualizaron en la sesión, pero no se pudieron guardar en Google Sheets.")
                    ss["fe_recargar"] = True
                    st.rerun()
        with c2:
            with tarjeta("reglas"):
                md(titulo_seccion("📐 Reglas de cálculo", "Se aplican a toda la planilla. Cámbialas solo si cambia la política de la empresa."))
                st.number_input("Precio desde el cual hay extra (USD)", min_value=0.0, step=1.0, format="%.2f", value=float(aj("umbral_extra")),
                                key="aj_umbral_extra", on_change=actualizar_ajuste, args=("umbral_extra", "aj_umbral_extra", True))
                st.number_input("Retención de publicidad sobre el extra (%)", min_value=0.0, max_value=100.0, step=1.0, format="%.0f", value=float(aj("retencion_pub_pct")),
                                key="aj_retencion_pub_pct", on_change=actualizar_ajuste, args=("retencion_pub_pct", "aj_retencion_pub_pct", True))
                st.number_input("Retención de renta sobre el sueldo (%)", min_value=0.0, max_value=90.0, step=1.0, format="%.0f", value=float(aj("renta_pct")),
                                key="aj_renta_pct", on_change=actualizar_ajuste, args=("renta_pct", "aj_renta_pct", True))
                md(f"<div class='formula'><b>Sueldo + extras:</b> por cada servicio mayor a {usd(umbral_extra())} → extra = precio − {usd(umbral_extra())}; comisión = extra − {aj('retencion_pub_pct'):g}%.<br>"
                   f"<b>Porcentaje de ventas:</b> comisión = ventas × % de la persona; sin sueldo base ni renta.<br>"
                   f"<b>Sueldo:</b> bruto = neto ÷ {factor_neto():.2f}; renta = bruto × {aj('renta_pct'):g}%.</div>")
                espacio(6)
                st.button("↩️ Restaurar reglas oficiales ($60 · 25% · 10%)", on_click=restaurar_reglas)
        espacio(8)
        if st.button("☁️ Guardar salario y reglas en Google Sheets", key="guardar_aj_s"):
            if guardar_ajustes(ss["ajustes"]):
                st.toast("Ajustes guardados en la nube.", icon="☁️")
            else:
                st.error("No se pudieron guardar los ajustes en Google Sheets (quedan activos en esta sesión).")

    # ---------------- Apariencia y empresa ----------------
    with tab_a:
        c1, c2 = st.columns([1.3, 1])
        with c1:
            with tarjeta("tema"):
                md(titulo_seccion("🎨 Color de la aplicación", "Se aplica al instante en el menú, botones, tarjetas, gráficos e ilustraciones."))
                swatches = "".join(f"<span class='sw {'on' if nombre_t == aj('tema') else ''}'><i style='background:linear-gradient(135deg,{t['p']},{t['acc']})'></i>{nombre_t}</span>"
                                   for nombre_t, t in TEMAS.items())
                md(f"<div class='swatches'>{swatches}</div>")
                temas = list(TEMAS.keys())
                st.radio("Tema de color", temas, index=temas.index(aj("tema")) if aj("tema") in temas else 0, key="aj_tema", horizontal=True,
                         on_change=actualizar_ajuste, args=("tema", "aj_tema"))
                st.toggle("Mostrar el banner de bienvenida en el Panel general", value=bool(aj("mostrar_hero")), key="aj_mostrar_hero",
                          on_change=actualizar_ajuste, args=("mostrar_hero", "aj_mostrar_hero"))
            with tarjeta("logo"):
                md(titulo_seccion("🖼️ Logo de la empresa", "Aparece en el menú y en todos los PDF (recibos, planillas, memorándums y actas)."))
                l1, l2 = columnas([1, 3], "center")
                md(f"<div class='brand' style='border:none;padding:0;margin:0'><img src='{img_logo()}' alt=''/></div>", l1)
                with l2:
                    archivo_logo = st.file_uploader("Subir logo (PNG o JPG)", type=["png", "jpg", "jpeg"], key="up_logo")
                if archivo_logo is not None and st.button("Usar este logo", type="primary", key="btn_logo"):
                    try:
                        imagen = Image.open(archivo_logo).convert("RGBA")
                        logo_b64 = ""
                        for lado in (320, 240, 180, 128):
                            copia = imagen.copy()
                            copia.thumbnail((lado, lado))
                            buffer = io.BytesIO()
                            copia.save(buffer, format="PNG", optimize=True)
                            logo_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                            if len(logo_b64) <= 45000:
                                break
                        ss["ajustes"]["logo_b64"] = logo_b64
                        notificar("Logo actualizado. Pulsa «Guardar apariencia y empresa» para conservarlo en la nube.", "🖼️")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo leer la imagen: {ex}")
                if _texto(aj("logo_b64")):
                    st.button("Quitar logo", on_click=quitar_logo, key="btn_quitar_logo")
        with c2:
            with tarjeta("empresa"):
                md(titulo_seccion("🏢 Datos de la empresa", "Aparecen en recibos, planillas, memorándums, actas y correos."))
                st.text_input("Razón social", value=aj("empresa_nombre"), key="aj_empresa_nombre", on_change=actualizar_ajuste, args=("empresa_nombre", "aj_empresa_nombre"))
                st.text_input("Nombre corto (menú y encabezados)", value=aj("empresa_corto"), key="aj_empresa_corto", on_change=actualizar_ajuste, args=("empresa_corto", "aj_empresa_corto"))
                st.text_area("Firma de los correos", value=aj("firma_correo"), key="aj_firma_correo", height=90, on_change=actualizar_ajuste, args=("firma_correo", "aj_firma_correo"))
        espacio(8)
        if st.button("☁️ Guardar apariencia y empresa en Google Sheets", key="guardar_aj_a"):
            if guardar_ajustes(ss["ajustes"]):
                st.toast("Ajustes guardados en la nube.", icon="☁️")
            else:
                st.error("No se pudieron guardar los ajustes en Google Sheets (quedan activos en esta sesión).")

    # ---------------- Respaldo y conexión ----------------
    with tab_r:
        c1, c2 = st.columns([1.1, 1])
        with c1:
            with tarjeta("conexion"):
                md(titulo_seccion("☁️ Conexión con Google Sheets y Gmail", "Estado de cada pieza. Si algo falta, sigue la guía paso a paso de abajo."))
                conectado = _documento() is not None
                ss["sheets_ok"] = conectado
                correo_cuenta = _texto(secreto("gcp_service_account", "client_email"))
                estados = [
                    ("Credenciales de Google (cuenta de servicio)", bool(secreto("gcp_service_account"))),
                    ("Enlace de la hoja de cálculo", bool(_texto(secreto("gsheets", "url")))),
                    ("Conexión con Google Sheets", conectado),
                    ("Correo de Gmail para envíos", bool(_texto(secreto("EMAIL_USER"))) and bool(_texto(secreto("EMAIL_PASS")))),
                ]
                md("<div class='chips' style='flex-direction:column;align-items:flex-start'>" + "".join(
                    chip(("✅ " if ok else "❌ ") + etiqueta, "green" if ok else "red") for etiqueta, ok in estados) + "</div>")
                if correo_cuenta:
                    st.caption("Comparte tu hoja de cálculo como Editor con este correo:")
                    st.code(correo_cuenta, language=None)
                if not conectado and secreto("gcp_service_account"):
                    detalle = error_conexion()
                    if detalle:
                        st.caption(f"Detalle técnico: {detalle[:300]}")
                k1, k2 = st.columns(2)
                if k1.button("🔌 Reintentar conexión", **ancho(st.button)):
                    _abrir_documento.clear()
                    ss.pop("sheets_ok", None)
                    notificar("Conexión reintentada.", "🔌")
                    st.rerun()
                if k2.button("✉️ Probar Gmail", **ancho(st.button)):
                    try:
                        servidor_prueba, _ = abrir_smtp()
                        servidor_prueba.quit()
                        st.toast("Gmail conectado correctamente.", icon="✅")
                    except Exception as ex:
                        st.error(f"Gmail no respondió: {ex}")
                k3, k4 = st.columns(2)
                if k3.button("🧱 Preparar hoja de cálculo", type="primary", disabled=not conectado, **ancho(st.button),
                             help="Crea las pestañas Personal, Proveedores, Ajustes, Auditoria e Historial_Planillas con sus encabezados y guarda los datos actuales."):
                    resultados = preparar_hoja_calculo()
                    if resultados and all(resultados.values()):
                        st.toast("Hoja de cálculo lista: todas las pestañas creadas.", icon="🧱")
                    else:
                        fallidas = [h for h, ok in (resultados or {}).items() if not ok]
                        st.error("No se pudieron preparar estas pestañas: " + (", ".join(fallidas) if fallidas else "sin conexión"))
                if k4.button("⬇️ Recargar desde Sheets", disabled=not conectado, **ancho(st.button)):
                    ss["empleados"], ss["fuente_personal"] = cargar_empleados()
                    ss["proveedores"] = cargar_proveedores()
                    ss["ajustes"] = cargar_ajustes()
                    ss["historial_auditoria"] = cargar_auditoria()
                    ss.pop("hist_cache", None)
                    for k in AJUSTES_POR_DEFECTO:
                        ss.pop(f"aj_{k}", None)
                    inicializar_empleados()
                    recalcular_todo()
                    ss["fe_recargar"] = True
                    notificar(f"Datos recargados ({ss['fuente_personal']}).", "☁️")
                    st.rerun()
            with st.expander("📘 Guía paso a paso para conectar Google Sheets y Gmail", expanded=not conectado):
                md(GUIA_CONEXION_HTML)
                st.code(PLANTILLA_SECRETS, language="toml")
        with c2:
            with tarjeta("respaldo"):
                md(titulo_seccion("💾 Respaldo de datos", "Copia completa de personal, proveedores, ajustes, auditoría e historial de esta sesión."))
                respaldo = {"version": 4, "fecha": ahora_sv().strftime("%Y-%m-%d %H:%M"), "empleados": ss["empleados"], "proveedores": ss["proveedores"],
                            "ajustes": ss["ajustes"], "auditoria": ss["historial_auditoria"], "historial_planillas": ss["historial_local"]}
                st.download_button("⬇️ Descargar respaldo completo (JSON)", data=json.dumps(respaldo, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                                   file_name=f"Respaldo_{nombre_archivo('', aj('empresa_corto')).strip('_').replace('.pdf', '')}_{ahora_sv().strftime('%Y-%m-%d')}.json",
                                   mime="application/json", **ancho(st.download_button))
                espacio(6)
                archivo_resp = st.file_uploader("Restaurar desde un respaldo", type=["json"], key="up_respaldo")
                sincronizar = st.checkbox("Guardar también lo restaurado en Google Sheets", value=True, key="resp_sync")
                if archivo_resp is not None and st.button("♻️ Restaurar respaldo", type="primary"):
                    try:
                        datos = json.loads(archivo_resp.getvalue().decode("utf-8"))
                        emps, provs, ajs, aud = datos.get("empleados"), datos.get("proveedores"), datos.get("ajustes"), datos.get("auditoria")
                        if isinstance(ajs, dict):
                            for k in AJUSTES_POR_DEFECTO:
                                if k in ajs:
                                    ss["ajustes"][k] = ajs[k]
                            if ss["ajustes"].get("tema") not in TEMAS:
                                ss["ajustes"]["tema"] = "Índigo"
                            for k in AJUSTES_POR_DEFECTO:
                                ss.pop(f"aj_{k}", None)
                            if sincronizar:
                                guardar_ajustes(ss["ajustes"])
                        if isinstance(provs, list) and provs:
                            ss["proveedores"] = [dict(p) for p in provs if isinstance(p, dict)]
                            ss.pop("prov_seleccionado", None)
                            if sincronizar:
                                guardar_proveedores(ss["proveedores"])
                        if isinstance(aud, list):
                            ss["historial_auditoria"] = [dict(a) for a in aud if isinstance(a, dict)]
                        if isinstance(datos.get("historial_planillas"), dict):
                            ss["historial_local"] = datos["historial_planillas"]
                        if isinstance(emps, dict) and emps:
                            restaurados = {_texto(n): _empleado_normalizado(i) for n, i in emps.items() if _texto(n) and isinstance(i, dict)}
                            if restaurados:
                                _aplicar_cambios_personal(restaurados, list(restaurados.keys()), guardar=sincronizar)
                        ss["fe_recargar"] = True
                        notificar("Respaldo restaurado.", "♻️")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"No se pudo leer el respaldo: {ex}")
            with tarjeta("plan_respaldo"):
                md(titulo_seccion("🛡️ Plan de respaldo recomendado") + "<div class='tips'>"
                   "<div class='tip'><span>1️⃣</span>Cada quincena, en Planillas, pulsa «☁️ Guardar en historial» después de revisar los montos.</div>"
                   "<div class='tip'><span>2️⃣</span>Cada mes descarga aquí el respaldo completo (JSON) y guárdalo en una carpeta de Google Drive.</div>"
                   "<div class='tip'><span>3️⃣</span>En Google Sheets usa «Archivo → Historial de versiones» para volver a cualquier día, y «Archivo → Hacer una copia» al cierre de cada mes.</div>"
                   "<div class='tip'><span>4️⃣</span>Guarda también los PDF de ventas originales en Drive, por mes.</div></div>")

pie_pagina()
