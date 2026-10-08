# =====================================================================
# GIO GROUP · Suite Administrativa (Planillas, Dashboard y Proveedores)
# =====================================================================
import base64
import hashlib
import html
import inspect
import io
import os
import re
import smtplib
import unicodedata
from datetime import datetime, timedelta, timezone
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
from streamlit_option_menu import option_menu


# =====================================================================
# 0. CONSTANTES
# =====================================================================
ZONA_SV = timezone(timedelta(hours=-6))  # El Salvador (sin horario de verano)

MOD_ESTANDAR = "Estándar (Con retención 25% Pub)"
MOD_PORCENTAJE = "Porcentaje Directo (%)"
MOD_FIJO = "Fijo"
MODALIDADES = [MOD_ESTANDAR, MOD_PORCENTAJE, MOD_FIJO]
ROLES = ["Operativo", "Administrativo"]
# Solo se usa para rellenar un sueldo que venga vacío en Google Sheets; cada persona tiene el suyo.
SUELDO_NETO_POR_DEFECTO = {"Operativo": 183.96, "Administrativo": 300.00}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Palabras clave para reconocer las columnas del reporte de ventas (sin tildes, en mayúsculas)
CLAVES_PROFESIONAL = ("PROFESIONAL", "COLABORADOR", "EMPLEADO", "ESTILISTA", "TERAPEUTA",
                      "ESPECIALISTA", "ATENDIDO", "BARBERO", "MASAJISTA")
CLAVES_PRECIO = ("PRECIO", "TOTAL", "MONTO", "IMPORTE", "VALOR", "COBRADO", "PAGADO")
CLAVES_CLIENTE = ("CLIENTE", "PACIENTE")
CLAVES_SERVICIO = ("SERVICIO", "TRATAMIENTO", "PROCEDIMIENTO", "PRODUCTO", "DESCRIPCION", "CONCEPTO")
CLAVES_FECHA = ("FECHA",)
PATRON_TOTAL = re.compile(r"^(SUB\s*-?\s*TOTAL|GRAN\s+TOTAL|TOTALES|TOTAL|SUMA)\b")
PATRON_FECHA = r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2})"
AJUSTES_TABLA_TEXTO = {"vertical_strategy": "text", "horizontal_strategy": "text",
                       "snap_tolerance": 3, "join_tolerance": 3, "intersection_tolerance": 5}

AUTO = "(automático)"
CLAVES_MAPEO = ("map_prof", "map_precio", "map_cliente", "map_servicio", "map_fecha", "map_quincenas")

ORDEN_MARCAS = ["Papi Spa", "Relájate Man", "Dr. Gio Molina", "Relájate Clinic"]
COLORES_MARCA = {"Papi Spa": "#2a78d6", "Relájate Man": "#eb6834", "Dr. Gio Molina": "#1baf7a", "Relájate Clinic": "#eda100"}
COLOR_PRIMARIO = "#4F46E5"
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


# =====================================================================
# 1. UTILIDADES GENERALES
# =====================================================================
def ahora_sv():
    return datetime.now(ZONA_SV)


def _texto(v):
    """Valor como texto limpio ('' si viene vacío, None o NaN)."""
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
    """Mayúsculas, sin tildes y con espacios simples: 'Jéssica  López' -> 'JESSICA LOPEZ'."""
    t = unicodedata.normalize("NFKD", _texto(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().upper()


def _a_numero(v):
    """Convierte '$1,234.50', 'US$ 60', '60,00', '(15.00)' o 60 a float. None si no hay número."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip()
    if not s:
        return None
    # Celdas de varias líneas: se usa la primera línea que tenga un número
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
    """'20%', '20', 20 o 0.2 -> 20.0"""
    n = _a_numero(v)
    if n is None:
        return defecto
    if 0 < n < 1 and "%" not in _texto(v):
        n = n * 100.0
    return n


def normalizar_modalidad(v):
    n = _normalizar(v)
    if "ESTANDAR" in n or "RETENCION" in n:
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


def alias_efectivo(nombre, info):
    """Alias configurado; si está vacío se usa el primer nombre (evita que un alias vacío capture todo el reporte)."""
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


def usd(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


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
    # Los errores no se guardan en caché: si la conexión falla, se reintenta después.
    try:
        return _abrir_documento()
    except Exception:
        return None


def conectar_gsheets(nombre_hoja="Personal", crear=False):
    doc = _documento()
    if doc is None:
        return None
    try:
        return doc.worksheet(nombre_hoja)
    except gspread.exceptions.WorksheetNotFound:
        if nombre_hoja == "Personal":
            return doc.sheet1
        # Nunca se usa sheet1 como reemplazo de otra hoja: al guardar borraría al personal.
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
        return worksheet.get_all_records(numericise_ignore=["all"])  # conserva ceros a la izquierda (DUI, cuentas)
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
    if isinstance(v, (pd.Timestamp, datetime)):
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
    "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96, "correo": "", "dui": "", "cuenta": ""},
    "Luis Violante": {"rol": "Operativo", "alias": "LUIS", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96, "correo": "", "dui": "", "cuenta": ""},
    "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA", "mod": MOD_PORCENTAJE, "porc": 20, "sueldo_base_neto": 0.0, "correo": "", "dui": "", "cuenta": ""},
    "Mario de Paz": {"rol": "Operativo", "alias": "MARIO", "mod": MOD_ESTANDAR, "porc": 20, "sueldo_base_neto": 183.96, "correo": "", "dui": "", "cuenta": ""},
    "Dr. Gio Molina": {"rol": "Administrativo", "alias": "GIO|MARVIN|DOCTOR", "mod": MOD_FIJO, "porc": 0, "sueldo_base_neto": 300.00, "correo": "", "dui": "", "cuenta": ""},
    "Gerson Ulises Molina Flores": {"rol": "Administrativo", "alias": "GERSON", "mod": MOD_FIJO, "porc": 0, "sueldo_base_neto": 300.00, "correo": "", "dui": "", "cuenta": ""},
    "Edwin Ponce": {"rol": "Administrativo", "alias": "EDWIN", "mod": MOD_FIJO, "porc": 0, "sueldo_base_neto": 300.00, "correo": "", "dui": "", "cuenta": ""},
}


def sueldo_neto_por_defecto(rol):
    return SUELDO_NETO_POR_DEFECTO.get(rol, SUELDO_NETO_POR_DEFECTO["Administrativo"])


def _leer_sueldo_neto(registro, rol):
    """Busca la columna de sueldo en la fila de Sheets (Sueldo_Base_Neto, 'Sueldo base neto', 'Salario'...)."""
    for clave, valor in registro.items():
        n = _normalizar(clave)
        if "SUELDO" in n or "SALARIO" in n:
            numero = _a_numero(valor)
            if numero is not None:
                return numero
    return sueldo_neto_por_defecto(rol)


def cargar_empleados():
    """Devuelve (empleados, fuente). Normaliza rol, modalidad y porcentaje para que los cálculos no fallen por tildes o formatos."""
    worksheet = conectar_gsheets("Personal")
    if worksheet:
        try:
            emp_dict = {}
            for r in _leer_registros(worksheet):
                nombre = _texto(r.get("Nombre"))
                if not nombre:
                    continue
                mod = normalizar_modalidad(r.get("Modalidad", "Fijo"))
                rol = normalizar_rol(r.get("Rol", "Operativo"))
                emp_dict[nombre] = {
                    "rol": rol,
                    "alias": _texto(r.get("Alias", "")),
                    "mod": mod,
                    "porc": _a_porcentaje(r.get("Porcentaje", 0), 20.0 if mod == MOD_PORCENTAJE else 0.0),
                    "sueldo_base_neto": _leer_sueldo_neto(r, rol),
                    "correo": _texto(r.get("Correo", "")),
                    "dui": _texto(r.get("DUI", "")),
                    "cuenta": _texto(r.get("Cuenta", "")),
                }
            if emp_dict:
                return emp_dict, "Google Sheets"
        except Exception:
            pass
    return {k: dict(v) for k, v in EMPLEADOS_POR_DEFECTO.items()}, "Datos locales"


def guardar_empleados(datos):
    if not datos:
        return False
    filas = [["Nombre", "Rol", "Alias", "Modalidad", "Porcentaje", "Sueldo_Base_Neto", "Correo", "DUI", "Cuenta"]]
    for nombre, info in datos.items():
        filas.append([_valor_para_sheets(x) for x in [nombre, info.get("rol", ""), info.get("alias", ""), info.get("mod", ""), info.get("porc", 0), sueldo_neto_de(info), info.get("correo", ""), info.get("dui", ""), info.get("cuenta", "")]])
    return _escribir_hoja("Personal", filas)


PROVEEDOR_EJEMPLO = {
    "ID_Proveedor": "1", "Nombre_Proveedor": "JG SUMINISTROS", "Nombre_Contacto": "JULIO CESAR HERNANDEZ POSADA",
    "Telefono_1": "7398 4751", "Telefono_2": "73984751", "Correo": "jgsuministrossv@gmail.com",
    "Banco": "Banco Cuscatlan", "Cuenta": "325-301-000002077", "Direccion_1": "Plaza comercial San Antonio, P°. El Carmen",
    "Direccion_2": "San Salvador", "Pais": "El Salvador", "Patrocinador": "JULIO CESAR HERNANDEZ POSADA",
    "Valoracion": "50%", "Fecha_Ultima_Rev": "", "Fecha_Prox_Rev": "", "Fecha_Contrato": "", "Fecha_Vencimiento": "",
    "Fecha_Calif_Riesgo": "", "Fecha_Diligencia": "", "Fecha_Rev_Contrato": "", "Fecha_Aprobacion": "",
    "Descripcion": "suministros medicos", "Notas": ""
}


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
        # Solo al eliminar el último proveedor: la hoja queda con los encabezados, sin filas
        return _escribir_hoja("Proveedores", [list(encabezados_si_vacio)]) if encabezados_si_vacio else False
    encabezados = list(datos_list[0].keys())
    filas = [encabezados] + [[_valor_para_sheets(item.get(c, "")) for c in encabezados] for item in datos_list]
    return _escribir_hoja("Proveedores", filas)


# =====================================================================
# 3. CONFIGURACIÓN DE PÁGINA
# =====================================================================
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
try:
    if os.path.exists(logo_path):
        st.set_page_config(page_title="Gio Group · Gerencia", page_icon=Image.open(logo_path), layout="wide", initial_sidebar_state="expanded")
    else:
        st.set_page_config(page_title="Gio Group · Gerencia", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")
except Exception:
    st.set_page_config(page_title="Gio Group · Gerencia", page_icon="🏢", layout="wide")


# =====================================================================
# 4. ESTADO DE MEMORIA (se inicializa una sola vez; nunca se pisa al navegar)
# =====================================================================
DEFAULTS_GLOBALES = {
    "quincenas_multiplicador": 1.0,
    "periodo_texto": "1 Quincena (Por defecto)",
    "detalle_extras": [],
    "historial_auditoria": [],
    "total_ingresos_pdf": 0.0,
    "ingresos_por_marca": {},
    "extras_por_marca": {},
    "pdf_hash": None,
    "pdf_nombre": "",
    "pdf_bytes": None,
    "pdf_ok": False,
    "pdf_error": "",
    "pdf_meta": {},
    "reporte_df": None,
    "resumen_pdf": {},
    "indices_por_colab": {},
    "uploader_nonce": 0,
    "nonce_editor_prov": 0,
    "nonce_editor_personal": 0,
    "_toasts": [],
    "_errores": [],
}
for _k, _v in DEFAULTS_GLOBALES.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v

if "empleados" not in st.session_state:
    st.session_state["empleados"], st.session_state["fuente_personal"] = cargar_empleados()
if "proveedores" not in st.session_state:
    st.session_state["proveedores"] = cargar_proveedores()


def sueldo_neto_de(info):
    """Sueldo neto quincenal individual de la persona (columna sueldo_base_neto de Configuración → Personal)."""
    n = _a_numero(info.get("sueldo_base_neto"))
    return n if n is not None else sueldo_neto_por_defecto(info.get("rol", "Operativo"))


def calcular_bruto_acumulado(info, quincenas=None):
    neto_quincenal = sueldo_neto_de(info)
    mult = quincenas if quincenas is not None else st.session_state["quincenas_multiplicador"]
    return round((neto_quincenal * mult) / 0.90, 2)


def inicializar_empleados():
    ss = st.session_state
    for emp, info in ss["empleados"].items():
        for pref in ("com_", "extra_bruto_", "ret_pub_", "serv_tot_", "hex_", "desc_"):
            if f"{pref}{emp}" not in ss:
                ss[f"{pref}{emp}"] = 0.0
        if f"email_{emp}" not in ss:
            ss[f"email_{emp}"] = info.get("correo", "")
        if f"notas_{emp}" not in ss:
            ss[f"notas_{emp}"] = "Ninguno"
        if f"base_{emp}" not in ss:
            ss[f"base_{emp}"] = 0.0 if "Porcentaje" in info.get("mod", "Fijo") else calcular_bruto_acumulado(info)


inicializar_empleados()


def recalcular_bases():
    for emp, info in st.session_state["empleados"].items():
        st.session_state[f"base_{emp}"] = 0.0 if "Porcentaje" in info.get("mod", "Fijo") else calcular_bruto_acumulado(info)


# --- Notificaciones flotantes (sobreviven a st.rerun) ---
def notificar(msg, icon="✅"):
    st.session_state["_toasts"].append((msg, icon))


def notificar_error(msg):
    """Errores críticos: se muestran fijos en pantalla (no como toast) aunque haya un rerun."""
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


# --- Widgets persistentes: el valor canónico vive en session_state y el widget se re-siembra al volver ---
def campo_persistente(widget_fn, label, state_key, ui_key, conv=None, **kwargs):
    if ui_key not in st.session_state:
        valor_inicial = st.session_state[state_key]
        st.session_state[ui_key] = conv(valor_inicial) if conv else valor_inicial
    valor = widget_fn(label, key=ui_key, **kwargs)
    st.session_state[state_key] = valor
    return valor


def reiniciar_widgets_planilla(prefijos=("ui_b_", "ui_c_")):
    for emp in st.session_state["empleados"].keys():
        for p in prefijos:
            st.session_state.pop(f"{p}{emp}", None)


# =====================================================================
# 5. IMÁGENES (ilustraciones SVG embebidas: no dependen de internet)
# =====================================================================
def _svg_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


IMG_LOGO = _svg_uri(
    "<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'>"
    "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#4F46E5'/><stop offset='1' stop-color='#0EA5E9'/></linearGradient></defs>"
    "<rect width='48' height='48' rx='14' fill='url(#g)'/>"
    "<text x='24' y='31' font-family='Arial, sans-serif' font-size='18' font-weight='800' fill='#FFFFFF' text-anchor='middle'>GG</text></svg>"
)

IMG_HERO = _svg_uri(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 340 220'>"
    "<defs>"
    "<linearGradient id='p' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#FFFFFF'/><stop offset='1' stop-color='#EEF2FF'/></linearGradient>"
    "<linearGradient id='b' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#818CF8'/><stop offset='1' stop-color='#4F46E5'/></linearGradient>"
    "<linearGradient id='l' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#34D399'/><stop offset='1' stop-color='#22D3EE'/></linearGradient>"
    "<linearGradient id='c' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#FDE68A'/><stop offset='1' stop-color='#F59E0B'/></linearGradient>"
    "</defs>"
    "<rect x='34' y='26' width='236' height='160' rx='18' fill='url(#p)'/>"
    "<rect x='54' y='46' width='84' height='9' rx='4.5' fill='#C7D2FE'/>"
    "<rect x='54' y='62' width='52' height='7' rx='3.5' fill='#E0E7FF'/>"
    "<rect x='60' y='132' width='18' height='36' rx='5' fill='url(#b)' opacity='.45'/>"
    "<rect x='90' y='118' width='18' height='50' rx='5' fill='url(#b)' opacity='.6'/>"
    "<rect x='120' y='124' width='18' height='44' rx='5' fill='url(#b)' opacity='.5'/>"
    "<rect x='150' y='100' width='18' height='68' rx='5' fill='url(#b)' opacity='.75'/>"
    "<rect x='180' y='92' width='18' height='76' rx='5' fill='url(#b)' opacity='.85'/>"
    "<rect x='210' y='72' width='18' height='96' rx='5' fill='url(#b)'/>"
    "<polyline points='69,118 99,104 129,110 159,86 189,78 219,56' fill='none' stroke='url(#l)' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'/>"
    "<circle cx='219' cy='56' r='7' fill='#FFFFFF' stroke='#22D3EE' stroke-width='3'/>"
    "<rect x='222' y='112' width='100' height='70' rx='14' fill='#FFFFFF'/>"
    "<circle cx='252' cy='147' r='17' fill='none' stroke='#E0E7FF' stroke-width='7'/>"
    "<circle cx='252' cy='147' r='17' fill='none' stroke='#4F46E5' stroke-width='7' stroke-dasharray='70 107' stroke-linecap='round' transform='rotate(-90 252 147)'/>"
    "<rect x='278' y='136' width='32' height='7' rx='3.5' fill='#C7D2FE'/>"
    "<rect x='278' y='150' width='22' height='7' rx='3.5' fill='#E0E7FF'/>"
    "<circle cx='40' cy='170' r='24' fill='url(#c)'/>"
    "<text x='40' y='179' font-family='Arial, sans-serif' font-size='24' font-weight='700' fill='#FFFFFF' text-anchor='middle'>$</text>"
    "</svg>"
)

IMG_REPORTE = _svg_uri(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 150'>"
    "<defs><linearGradient id='u' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#6366F1'/><stop offset='1' stop-color='#0EA5E9'/></linearGradient></defs>"
    "<ellipse cx='100' cy='136' rx='70' ry='8' fill='#E2E8F0'/>"
    "<rect x='56' y='14' width='86' height='112' rx='12' fill='#FFFFFF' stroke='#C7D2FE' stroke-width='2'/>"
    "<rect x='70' y='34' width='42' height='7' rx='3.5' fill='#C7D2FE'/>"
    "<rect x='70' y='48' width='58' height='6' rx='3' fill='#E0E7FF'/>"
    "<rect x='70' y='60' width='50' height='6' rx='3' fill='#E0E7FF'/>"
    "<rect x='70' y='72' width='56' height='6' rx='3' fill='#E0E7FF'/>"
    "<rect x='70' y='90' width='30' height='16' rx='4' fill='#EF4444'/>"
    "<text x='85' y='101.5' font-family='Arial, sans-serif' font-size='9' font-weight='700' fill='#FFFFFF' text-anchor='middle'>PDF</text>"
    "<circle cx='146' cy='104' r='22' fill='url(#u)'/>"
    "<path d='M146 115v-20m-8 8l8-8 8 8' fill='none' stroke='#FFFFFF' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'/>"
    "</svg>"
)

IMG_DIRECTORIO = _svg_uri(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 150'>"
    "<ellipse cx='100' cy='136' rx='70' ry='8' fill='#E2E8F0'/>"
    "<rect x='50' y='18' width='100' height='108' rx='14' fill='#FFFFFF' stroke='#C7D2FE' stroke-width='2'/>"
    "<circle cx='100' cy='54' r='17' fill='#EEF2FF'/>"
    "<circle cx='100' cy='49' r='7' fill='#818CF8'/>"
    "<path d='M87 66c3-8 23-8 26 0' fill='#818CF8'/>"
    "<rect x='70' y='84' width='60' height='7' rx='3.5' fill='#C7D2FE'/>"
    "<rect x='78' y='98' width='44' height='6' rx='3' fill='#E0E7FF'/>"
    "<circle cx='150' cy='108' r='18' fill='#10B981'/>"
    "<path d='M141 108l6 6 12-12' fill='none' stroke='#FFFFFF' stroke-width='3.5' stroke-linecap='round' stroke-linejoin='round'/>"
    "</svg>"
)


# =====================================================================
# 6. ESTILOS (CSS PREMIUM)
# =====================================================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #F5F7FB; --surface: #FFFFFF; --ink: #0B1220; --ink-2: #334155; --muted: #64748B; --soft: #94A3B8;
    --line: #E6EAF1; --line-2: #EEF1F6;
    --primary: #4F46E5; --primary-600: #4338CA; --primary-50: #EEF2FF;
    --radius: 14px;
    --shadow-sm: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06);
    --shadow-md: 0 10px 28px rgba(16,24,40,.08), 0 2px 6px rgba(16,24,40,.04);
}

/* Base */
.stApp { background: var(--bg) !important; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button, .stMarkdown {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
#MainMenu, footer, [data-testid="stDecoration"], .stAppDeployButton { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }
.block-container { padding-top: 1.6rem !important; padding-bottom: 3rem !important; max-width: 1360px; }
h1, h2, h3, h4 { color: var(--ink) !important; letter-spacing: -0.02em; }
@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* Sidebar */
[data-testid="stSidebar"] { background: #FFFFFF !important; border-right: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 12px; padding: 4px 4px 16px 4px; border-bottom: 1px solid var(--line-2); margin-bottom: 12px; }
.brand img { width: 44px; height: 44px; border-radius: 14px; box-shadow: 0 6px 16px rgba(79,70,229,.25); }
.brand-name { font-weight: 800; font-size: 1.08rem; color: var(--ink); letter-spacing: -0.01em; }
.brand-sub { font-size: .75rem; color: var(--muted); }
.side-card { background: #F8FAFC; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin-top: 14px; font-size: .8rem; color: var(--ink-2); }
.side-title { font-size: .68rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--soft); margin-bottom: 6px; }
.side-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 0; }
.side-row b { color: var(--ink); font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.dot.on { background: #10B981; box-shadow: 0 0 0 3px rgba(16,185,129,.18); }
.dot.off { background: #F59E0B; box-shadow: 0 0 0 3px rgba(245,158,11,.18); }
.profile { display: flex; align-items: center; gap: 10px; margin-top: 14px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: #FFFFFF; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #4F46E5, #0EA5E9); color: #FFFFFF; font-weight: 700; display: flex; align-items: center; justify-content: center; font-size: .8rem; flex-shrink: 0; }
.profile-name { font-weight: 700; color: var(--ink); font-size: .85rem; }
.profile-role { color: var(--muted); font-size: .75rem; }

/* Hero */
.hero {
    position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; gap: 24px;
    padding: 30px 34px; border-radius: 20px; margin-bottom: 18px;
    background: radial-gradient(900px 260px at 85% -30%, rgba(129,140,248,.55), transparent 60%),
                linear-gradient(135deg, #0B1B3F 0%, #172554 45%, #3730A3 100%);
    box-shadow: 0 18px 40px rgba(30,27,75,.22); animation: fadeUp .5s ease both;
}
.hero::after {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(rgba(255,255,255,.07) 1px, transparent 1px); background-size: 18px 18px;
}
.hero-body { position: relative; z-index: 1; }
.hero-kicker { font-size: .78rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #C7D2FE !important; }
.hero-title { font-size: 2.05rem; font-weight: 800; letter-spacing: -0.03em; margin-top: 6px; color: #FFFFFF !important; line-height: 1.15; }
.hero-sub { color: #CBD5E1 !important; margin-top: 8px; font-size: .98rem; max-width: 600px; line-height: 1.5; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.hero-chip { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); color: #FFFFFF !important; padding: 6px 12px; border-radius: 999px; font-size: .8rem; font-weight: 600; }
.hero-img { width: 300px; max-width: 36%; flex-shrink: 0; position: relative; z-index: 1; filter: drop-shadow(0 14px 26px rgba(0,0,0,.28)); }
@media (max-width: 900px) { .hero { flex-direction: column; align-items: flex-start; } .hero-img { display: none; } .hero-title { font-size: 1.6rem; } }

/* Encabezado de página */
.page-head { display: flex; align-items: center; gap: 14px; margin: 2px 0 18px 0; animation: fadeUp .4s ease both; }
.page-ico { width: 48px; height: 48px; border-radius: 14px; background: linear-gradient(135deg, #EEF2FF, #E0E7FF); border: 1px solid #E0E7FF; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; flex-shrink: 0; }
.page-kicker { font-size: .72rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--primary); }
.page-title { font-size: 1.65rem; font-weight: 800; color: var(--ink); letter-spacing: -0.025em; line-height: 1.2; }
.page-sub { font-size: .92rem; color: var(--muted); margin-top: 2px; }

/* Tarjetas (contenedores con key="card_*") */
[class*="st-key-card_"] {
    background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: var(--radius) !important;
    padding: 20px 22px !important; box-shadow: var(--shadow-sm) !important; transition: box-shadow .2s ease, border-color .2s ease;
    animation: fadeUp .45s ease both;
}
[class*="st-key-card_"]:hover { box-shadow: var(--shadow-md) !important; border-color: #DCE1EA !important; }
.sec-title { font-size: 1.02rem; font-weight: 700; color: var(--ink); }
.sec-sub { font-size: .83rem; color: var(--muted); margin: 2px 0 6px 0; }

/* KPIs */
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; box-shadow: var(--shadow-sm); transition: transform .2s ease, box-shadow .2s ease; height: 100%; animation: fadeUp .45s ease both; }
.kpi:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
.kpi-top { display: flex; align-items: center; gap: 10px; }
.kpi-ico { width: 38px; height: 38px; border-radius: 11px; display: flex; align-items: center; justify-content: center; font-size: 1.05rem; flex-shrink: 0; }
.kpi-ico.indigo { background: #EEF2FF; } .kpi-ico.sky { background: #E0F2FE; } .kpi-ico.green { background: #ECFDF5; }
.kpi-ico.amber { background: #FFFBEB; } .kpi-ico.red { background: #FEF2F2; } .kpi-ico.violet { background: #F5F3FF; }
.kpi-label { font-size: .74rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.kpi-value { font-size: 1.7rem; font-weight: 800; color: var(--ink); letter-spacing: -0.03em; margin-top: 12px; font-variant-numeric: tabular-nums; }
.kpi-value.pos { color: #047857; } .kpi-value.neg { color: #B91C1C; }
.kpi-note { font-size: .8rem; color: var(--muted); margin-top: 4px; }
.bar { height: 6px; border-radius: 999px; background: #F1F5F9; overflow: hidden; margin-top: 8px; }
.bar span { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, #F59E0B, #FBBF24); }

/* Chips */
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 8px 0; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 11px; border-radius: 999px; font-size: .78rem; font-weight: 600; background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0; white-space: nowrap; }
.chip.indigo { background: #EEF2FF; color: #4338CA; border-color: #E0E7FF; }
.chip.green { background: #ECFDF5; color: #047857; border-color: #A7F3D0; }
.chip.amber { background: #FFFBEB; color: #B45309; border-color: #FDE68A; }
.chip.red { background: #FEF2F2; color: #B91C1C; border-color: #FECACA; }
.chip.sky { background: #F0F9FF; color: #0369A1; border-color: #BAE6FD; }
.chip.violet { background: #F5F3FF; color: #6D28D9; border-color: #DDD6FE; }

/* Acciones destructivas (contenedores con key="peligro_*") */
[class*="st-key-peligro"] .stButton button {
    background: linear-gradient(135deg, #DC2626 0%, #EF4444 100%) !important; color: #FFFFFF !important;
    border: none !important; box-shadow: 0 6px 16px rgba(220,38,38,.25) !important;
}
[class*="st-key-peligro"] .stButton button:hover {
    color: #FFFFFF !important; filter: brightness(1.06); box-shadow: 0 10px 24px rgba(220,38,38,.34) !important;
}
.confirmar-borrado { background: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; border-radius: 12px; padding: 12px 14px; font-size: .9rem; margin: 6px 0 8px 0; }

/* Estado vacío */
.empty { display: flex; align-items: center; gap: 30px; background: var(--surface); border: 1px solid var(--line); border-radius: 18px; padding: 28px 34px; box-shadow: var(--shadow-sm); animation: fadeUp .45s ease both; }
.empty img { width: 210px; flex-shrink: 0; }
.empty-title { font-size: 1.25rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em; }
.empty-text { color: var(--muted); margin-top: 4px; }
.steps { margin-top: 14px; display: grid; gap: 9px; }
.step { display: flex; gap: 10px; align-items: center; font-size: .9rem; color: var(--ink-2); }
.step b { width: 24px; height: 24px; border-radius: 50%; background: var(--primary-50); color: var(--primary-600); display: flex; align-items: center; justify-content: center; font-size: .75rem; flex-shrink: 0; }
@media (max-width: 700px) { .empty { flex-direction: column; text-align: center; } .step { justify-content: center; } }

/* Neto por colaborador */
.neto { display: flex; align-items: center; justify-content: space-between; gap: 12px; background: linear-gradient(135deg, #F8FAFF, #EEF2FF); border: 1px solid #E0E7FF; border-radius: 12px; padding: 12px 16px; margin-top: 8px; }
.neto-label { font-size: .72rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--primary-600); }
.neto-formula { font-size: .8rem; color: var(--muted); font-variant-numeric: tabular-nums; margin-top: 2px; }
.neto-valor { font-size: 1.4rem; font-weight: 800; color: var(--primary-600); font-variant-numeric: tabular-nums; white-space: nowrap; }

/* Botones */
.stButton button, .stDownloadButton button {
    border-radius: 10px !important; font-weight: 600 !important; padding: .55rem 1.1rem !important;
    border: 1px solid var(--line) !important; background: #FFFFFF !important; color: var(--ink) !important;
    box-shadow: var(--shadow-sm) !important; transition: all .18s ease !important;
}
.stButton button:hover, .stDownloadButton button:hover {
    border-color: #C7D2FE !important; color: var(--primary-600) !important; background: #F8FAFF !important;
    transform: translateY(-1px); box-shadow: var(--shadow-md) !important;
}
.stButton button:active, .stDownloadButton button:active { transform: scale(.98); }
.stButton button p, .stDownloadButton button p { color: inherit !important; font-weight: 600 !important; }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"],
[data-testid="stBaseButton-primary"], [data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #4F46E5 0%, #6366F1 55%, #0EA5E9 140%) !important;
    color: #FFFFFF !important; border: none !important; box-shadow: 0 6px 16px rgba(79,70,229,.28) !important;
}
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover, [data-testid="baseButton-primary"]:hover {
    color: #FFFFFF !important; filter: brightness(1.07); box-shadow: 0 10px 24px rgba(79,70,229,.36) !important;
}
.stButton button:disabled, .stDownloadButton button:disabled { opacity: .45 !important; transform: none !important; box-shadow: none !important; }

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { border-radius: 10px !important; border-color: var(--line) !important; background: #FFFFFF !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within { border-color: var(--primary) !important; box-shadow: 0 0 0 3px rgba(79,70,229,.15) !important; }
.stApp label p { color: var(--ink-2) !important; font-weight: 500 !important; font-size: .86rem !important; }
[data-testid="stFileUploaderDropzone"] { background: linear-gradient(180deg, #FAFBFF, #F4F6FF) !important; border: 1.5px dashed #C7D2FE !important; border-radius: 12px !important; transition: border-color .2s ease; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--primary) !important; }

/* Expanders, tablas, tabs, toasts */
[data-testid="stExpander"] { background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: var(--radius) !important; box-shadow: var(--shadow-sm) !important; transition: box-shadow .2s ease; }
[data-testid="stExpander"]:hover { box-shadow: var(--shadow-md) !important; }
[data-testid="stExpander"] details { border: none !important; }
[data-testid="stExpander"] summary p { font-weight: 600 !important; color: var(--ink) !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
[data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] { padding: 8px 14px !important; font-weight: 600 !important; }
[data-baseweb="tab"][aria-selected="true"] p { color: var(--primary) !important; }
[data-baseweb="tab-highlight"] { background-color: var(--primary) !important; height: 3px !important; border-radius: 3px; }
[data-testid="stToast"] { border-radius: 12px !important; border: 1px solid var(--line) !important; box-shadow: 0 14px 34px rgba(16,24,40,.14) !important; background: #FFFFFF !important; }

/* Perfil de proveedor (CRM) */
.crm-head { display: flex; gap: 18px; align-items: center; }
.crm-avatar { width: 68px; height: 68px; border-radius: 18px; flex-shrink: 0; background: linear-gradient(135deg, #4F46E5 0%, #6366F1 55%, #0EA5E9 100%); color: #FFFFFF; font-weight: 800; font-size: 1.45rem; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 20px rgba(79,70,229,.28); }
.crm-kicker { font-size: .7rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--soft); }
.crm-name { font-size: 1.5rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em; line-height: 1.2; margin-top: 2px; }
.crm-desc { color: var(--muted); font-size: .92rem; margin-top: 4px; }
.crm-section-title { display: flex; align-items: center; gap: 8px; font-size: .74rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; color: #475569; margin-bottom: 6px; padding-bottom: 10px; border-bottom: 1px solid #F1F5F9; }
.crm-section-title .sdot { width: 8px; height: 8px; border-radius: 50%; }
.crm-field { display: flex; gap: 12px; align-items: flex-start; padding: 9px 0; }
.crm-ico { width: 36px; height: 36px; border-radius: 10px; background: #F1F5F9; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; transition: background .2s ease, transform .2s ease; }
.crm-field:hover .crm-ico { background: #E0E7FF; transform: scale(1.06); }
.crm-label { font-size: .68rem; color: var(--soft); font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.crm-value { font-size: .92rem; color: var(--ink); font-weight: 600; word-break: break-word; margin-top: 1px; }
.crm-value.mono { font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.crm-value.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-value a { color: var(--primary); text-decoration: none; }
.crm-value a:hover { text-decoration: underline; }
.crm-date { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px dashed #EEF2F7; }
.crm-date:last-child { border-bottom: none; }
.crm-date .l { display: flex; align-items: center; gap: 10px; font-size: .86rem; color: var(--ink-2); font-weight: 500; }
.crm-date .r { display: flex; align-items: center; gap: 8px; font-size: .86rem; color: var(--ink); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.crm-date .r.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-text { color: var(--ink-2); font-size: .92rem; line-height: 1.6; white-space: pre-wrap; }
.crm-text.empty { color: #CBD5E1; font-style: italic; }

/* Lista de consejos */
.tips { display: grid; gap: 10px; margin-top: 6px; }
.tip { display: flex; gap: 10px; font-size: .86rem; color: var(--ink-2); line-height: 1.45; }
.tip span { flex-shrink: 0; }
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
    except TypeError:  # Streamlit antiguo sin 'key' en contenedores
        return st.container(border=True)


def zona(clave):
    """Contenedor sin estilo propio, solo para aplicar CSS por key (p. ej. botones rojos 'peligro_*')."""
    try:
        return st.container(key=clave)
    except TypeError:
        return st.container()


def encabezado_pagina(icono, titulo, subtitulo="", kicker="Gio Group · Gerencia"):
    md(f"<div class='page-head'><div class='page-ico'>{icono}</div><div><div class='page-kicker'>{kicker}</div>"
       f"<div class='page-title'>{titulo}</div><div class='page-sub'>{subtitulo}</div></div></div>")


def titulo_seccion(titulo, sub=""):
    sub_html = f"<div class='sec-sub'>{sub}</div>" if sub else ""
    return f"<div class='sec-title'>{titulo}</div>{sub_html}"


def chip(texto, tono=""):
    return f"<span class='chip {tono}'>{texto}</span>"


def kpi_html(icono, etiqueta, valor, nota="", tono="indigo", valor_cls=""):
    return (f"<div class='kpi'><div class='kpi-top'><span class='kpi-ico {tono}'>{icono}</span>"
            f"<span class='kpi-label'>{etiqueta}</span></div>"
            f"<div class='kpi-value {valor_cls}'>{valor}</div><div class='kpi-note'>{nota}</div></div>")


def fila_kpis(items):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        md(item, col)


def estado_vacio(imagen, titulo, texto, pasos=()):
    pasos_html = ""
    if pasos:
        pasos_html = "<div class='steps'>" + "".join(f"<div class='step'><b>{i}</b>{p}</div>" for i, p in enumerate(pasos, 1)) + "</div>"
    md(f"<div class='empty'><img src='{imagen}' alt=''/><div><div class='empty-title'>{titulo}</div>"
       f"<div class='empty-text'>{texto}</div>{pasos_html}</div></div>")


def espacio(px_alto=10):
    md(f"<div style='height:{px_alto}px'></div>")


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
    """(tabla, fila) del encabezado. Primero exige profesional + precio; luego la regla original (solo 'PROFESIONAL')."""
    for ti, tabla in enumerate(tablas):
        for fi, fila in enumerate(tabla):
            if _es_encabezado(_fila_norm(fila)):
                return ti, fi
    for ti, tabla in enumerate(tablas):
        for fi, fila in enumerate(tabla):
            if any("PROFESIONAL" in c for c in _fila_norm(fila)):
                return ti, fi
    return None


def _buscar_columna(columnas, claves, excluir=()):
    for clave in claves:
        for c in columnas:
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
    """Calidad de una extracción: filas bajo el encabezado con un precio legible."""
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


@st.cache_data(show_spinner=False, max_entries=16)
def extraer_contenido_pdf(pdf_bytes):
    """Lectura pesada (una sola vez por archivo). Prueba tablas con bordes y, como respaldo, tablas alineadas por texto."""
    textos, tablas_lineas, tablas_texto = [], [], []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        n_paginas = len(pdf.pages)
        for page in pdf.pages:
            textos.append(page.extract_text() or "")
            tablas_lineas.extend(_tablas_pagina(page))
            tablas_texto.extend(_tablas_pagina(page, AJUSTES_TABLA_TEXTO))
    calidad_lineas = _filas_con_precio(tablas_lineas)
    calidad_texto = _filas_con_precio(tablas_texto)
    if calidad_lineas == 0 and calidad_texto > 0 or calidad_texto > calidad_lineas * 1.3:
        return "\n".join(textos), tablas_texto, n_paginas, "texto"
    return "\n".join(textos), tablas_lineas, n_paginas, "lineas"


def detectar_periodo(texto):
    """Rango de fechas del reporte: primero un rango explícito ('Del ... al ...'); si no, el mínimo y máximo de las fechas del documento."""
    t = _normalizar(texto)
    rango = re.search(r"(?:DESDE|DEL|DE|PERIODO|RANGO|FECHAS?)\s*:?\s*" + PATRON_FECHA + r"\s*(?:HASTA|AL|A|-)\s*:?\s*" + PATRON_FECHA, t)
    if rango:
        f1, f2 = _parse_fecha_texto(rango.group(1)), _parse_fecha_texto(rango.group(2))
        if f1 and f2:
            return min(f1, f2), max(f1, f2), "rango indicado en el reporte"
    fechas = []
    for m in re.finditer(PATRON_FECHA, t):
        contexto = t[max(0, m.start() - 30):m.start()]
        if re.search(r"GENERAD|IMPRES|EMISION|EMITID|CREAD", contexto):
            continue  # fecha de impresión del reporte, no del período
        f = _parse_fecha_texto(m.group(1))
        if f:
            fechas.append(f)
    if len(fechas) >= 2:
        return min(fechas), max(fechas), f"{len(fechas)} fechas encontradas en el reporte"
    return None


def construir_reporte(texto, tablas, estrategia, mapeo):
    meta = {"estrategia": "Tablas con bordes" if estrategia == "lineas" else "Alineación de texto",
            "columnas": [], "filas_leidas": 0, "servicios": 0, "excluidas_total": 0, "sin_precio": 0,
            "sin_profesional": 0, "monto_sin_profesional": 0.0, "rellenadas": 0, "muestra_texto": texto[:1500]}
    if not texto.strip() and not tablas:
        return {"ok": False, "meta": meta, "error": "El PDF no tiene texto legible (parece escaneado como imagen). Exporta el reporte desde el sistema de ventas como PDF normal."}

    pos = _ubicar_encabezado(tablas)
    if pos is None:
        return {"ok": False, "meta": meta, "error": "No se encontró la tabla de servicios: falta un encabezado con la columna PROFESIONAL (o COLABORADOR / EMPLEADO) y PRECIO (o TOTAL / MONTO)."}
    ti, fi = pos

    columnas = []
    for i, c in enumerate(tablas[ti][fi]):
        nombre = _normalizar(c) or f"COLUMNA {i + 1}"
        base, k = nombre, 2
        while nombre in columnas:
            nombre = f"{base} ({k})"
            k += 1
        columnas.append(nombre)
    ancho_tabla = len(columnas)
    meta["columnas"] = columnas

    filas = []
    for j, tabla in enumerate(tablas[ti:]):
        if j == 0:
            cuerpo = tabla[fi + 1:]
        elif estrategia == "lineas" and tabla and len(tabla[0]) != ancho_tabla:
            continue  # tablas de resumen u otras secciones: no son servicios
        else:
            cuerpo = tabla
        for fila in cuerpo:
            fila = list(fila)[:ancho_tabla] + [""] * max(0, ancho_tabla - len(fila))
            if _es_encabezado(_fila_norm(fila)):
                continue  # encabezado repetido en cada página
            filas.append(fila)
    meta["filas_leidas"] = len(filas)
    if not filas:
        return {"ok": False, "meta": meta, "error": "Se encontró el encabezado, pero ninguna fila de servicios debajo."}

    df = pd.DataFrame(filas, columns=columnas)

    def elegir(clave, claves, excluir=()):
        v = mapeo.get(clave)
        if v and v in columnas:
            return v
        return _buscar_columna(columnas, claves, excluir)

    c_prof = elegir("prof", CLAVES_PROFESIONAL)
    c_pre = elegir("precio", CLAVES_PRECIO, (c_prof,))
    c_cli = elegir("cliente", CLAVES_CLIENTE, (c_prof, c_pre))
    c_ser = elegir("servicio", CLAVES_SERVICIO, (c_prof, c_pre, c_cli))
    c_fecha = elegir("fecha", CLAVES_FECHA, (c_prof, c_pre))
    meta.update({"c_prof": c_prof, "c_pre": c_pre, "c_cli": c_cli, "c_ser": c_ser, "c_fecha": c_fecha})
    if not c_prof or not c_pre:
        return {"ok": False, "meta": meta, "error": "No se pudo identificar la columna del profesional o la del precio. Selecciónalas manualmente en el diagnóstico."}

    df["_PROF"] = df[c_prof].map(_texto)
    df["_PRECIO"] = df[c_pre].map(_a_numero)
    prof_norm = df["_PROF"].map(_normalizar)
    encabezado_repetido = prof_norm.str.contains("PROFESIONAL", na=False) | (prof_norm == c_prof)

    # Filas de TOTAL / SUBTOTAL: se excluyen para no duplicar los ingresos
    es_total = pd.Series(False, index=df.index)
    for c in [c for c in dict.fromkeys([c_prof, c_cli, columnas[0]]) if c]:
        es_total = es_total | df[c].map(lambda v: bool(PATRON_TOTAL.match(_normalizar(v))))
    meta["excluidas_total"] = int((es_total & ~encabezado_repetido).sum())
    df = df[~encabezado_repetido & ~es_total].copy()

    # Reportes agrupados: el nombre del profesional solo aparece en la primera fila del grupo
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
    meta["servicios"] = int(len(df))
    return {"ok": True, "df": df, "meta": meta, "c_prof": c_prof, "c_pre": c_pre, "c_cli": c_cli,
            "c_ser": c_ser, "c_fecha": c_fecha, "periodo": detectar_periodo(texto)}


def aplicar_reporte(rep, quincenas_manual=None):
    """Aplica el reporte a la planilla. Las fórmulas de pago son exactamente las originales."""
    ss = st.session_state
    df_reporte = rep["df"]
    c_prof, c_pre, c_cli, c_ser, c_fecha = rep["c_prof"], rep["c_pre"], rep["c_cli"], rep["c_ser"], rep["c_fecha"]
    meta = rep["meta"]

    fechas_col = None
    if c_fecha:
        fechas_col = pd.to_datetime(df_reporte[c_fecha].map(_fecha_de_celda), errors="coerce")

    # --- Período y quincenas ---
    periodo = rep["periodo"]
    if periodo is None and fechas_col is not None and fechas_col.notna().sum() >= 1:
        periodo = (fechas_col.min().to_pydatetime(), fechas_col.max().to_pydatetime(), "columna de fechas del reporte")
    factor, texto_periodo = 1.0, "1 Quincena (Por defecto)"
    if periodo:
        min_f, max_f, fuente = periodo
        dias_diff = (max_f - min_f).days + 1
        factor = 1.0 if dias_diff <= 16 else 2.0 if dias_diff <= 31 else float(max(2, round(dias_diff / 30.0)) * 2.0)
        texto_periodo = f"Del {min_f.strftime('%d/%m/%Y')} al {max_f.strftime('%d/%m/%Y')} ({factor} Quincenas)"
        meta["periodo_fuente"] = fuente
    else:
        meta["periodo_fuente"] = "no se encontraron fechas (se asume 1 quincena)"
    if quincenas_manual:
        factor = float(quincenas_manual)
        prefijo = texto_periodo.split(" (")[0] if periodo else "Período"
        texto_periodo = f"{prefijo} ({factor} Quincenas · ajuste manual)"
    ss["quincenas_multiplicador"] = factor
    ss["periodo_texto"] = texto_periodo

    # --- Ingresos y marcas ---
    ss["total_ingresos_pdf"] = float(df_reporte[c_pre].sum())

    def asignar_marca(p):
        p = _normalizar(p)
        if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
        if "LUIS" in p: return "Relájate Man"
        if "GIO" in p or "MARVIN" in p: return "Dr. Gio Molina"
        return "Relájate Clinic"

    df_reporte['MARCA'] = df_reporte[c_prof].apply(asignar_marca)
    ss["ingresos_por_marca"] = {k: float(v) for k, v in df_reporte.groupby('MARCA')[c_pre].sum().to_dict().items()}
    df_reporte['EXTRA'] = df_reporte.apply(lambda r: 0.0 if r['MARCA'] == "Dr. Gio Molina" else max(0.0, float(r[c_pre]) - 60.0), axis=1)
    ss["extras_por_marca"] = {k: float(v) for k, v in df_reporte.groupby('MARCA')['EXTRA'].sum().to_dict().items()}

    # --- Cálculo por colaborador (lógica de negocio intacta) ---
    df_reporte["_COLAB"] = ""
    df_reporte["_N_COINC"] = 0
    lista_ex = []
    resumen = {}
    indices_por_colab = {}
    for emp, info in ss["empleados"].items():
        mod = info.get("mod", "Fijo")
        ss[f"com_{emp}"] = 0.0
        ss[f"extra_bruto_{emp}"] = 0.0
        ss[f"ret_pub_{emp}"] = 0.0
        ss[f"base_{emp}"] = 0.0 if "Porcentaje" in mod else calcular_bruto_acumulado(info, ss["quincenas_multiplicador"])

        patron = patron_alias(alias_efectivo(emp, info))
        mascara = df_reporte["_PROF_N"].map(lambda n: coincide_alias(n, patron)).astype(bool)
        df_reporte.loc[mascara, "_N_COINC"] += 1
        df_reporte.loc[mascara & (df_reporte["_COLAB"] == ""), "_COLAB"] = emp
        df_p = df_reporte[mascara]
        # Posiciones (en reporte_df) de los servicios de esta persona: exactamente las filas que suman a su pago
        indices_por_colab[emp] = [i for i, m in enumerate(mascara.tolist()) if m]
        tot_s = float(df_p[c_pre].sum())
        ss[f"serv_tot_{emp}"] = tot_s

        n_extra = 0
        if info.get("rol", "") == "Operativo":
            if "Estándar" in mod:
                df_ex = df_p[df_p[c_pre] > 60.0]
                ex_tot = 0.0; ret_tot = 0.0
                for _, rx in df_ex.iterrows():
                    pr = float(rx[c_pre]); ex = pr - 60.0; ret = ex * 0.25; com = ex - ret
                    ex_tot += ex; ret_tot += ret
                    lista_ex.append({"Colaborador": emp, "Cliente": _texto(rx[c_cli]) if c_cli else "N/A", "Servicio": _texto(rx[c_ser]) if c_ser else "N/A", "Precio Final": pr, "Extra Generado": ex, "Retención (25%)": ret, "Comisión Neta": com})
                n_extra = int(len(df_ex))
                ss[f"extra_bruto_{emp}"] = ex_tot
                ss[f"ret_pub_{emp}"] = ret_tot
                ss[f"com_{emp}"] = max(0.0, ex_tot - ret_tot)
            else:
                ss[f"com_{emp}"] = tot_s * (float(info.get("porc", 20) or 0) / 100.0)
        resumen[emp] = {"Alias buscado": patron or "—", "Servicios": int(mascara.sum()), "Ventas": tot_s, "Servicios > $60": n_extra}

    ss["detalle_extras"] = lista_ex
    ss["resumen_pdf"] = resumen
    ss["indices_por_colab"] = indices_por_colab

    sin_asignar = df_reporte[df_reporte["_COLAB"] == ""]
    meta["sin_asignar"] = [
        {"Profesional en el PDF": k, "Servicios": int(len(g)), "Ventas": float(g[c_pre].sum())}
        for k, g in sin_asignar.groupby("_PROF")
    ]
    meta["multiples"] = int((df_reporte["_N_COINC"] > 1).sum())

    vacio = pd.Series("", index=df_reporte.index)
    ss["reporte_df"] = pd.DataFrame({
        "Profesional": df_reporte[c_prof].values,
        "Colaborador": df_reporte["_COLAB"].replace("", "Sin asignar").values,
        "Marca": df_reporte["MARCA"].values,
        "Precio": df_reporte[c_pre].astype(float).values,
        "Extra": df_reporte["EXTRA"].astype(float).values,
        "Servicio": (df_reporte[c_ser].map(_texto) if c_ser else vacio).values,
        "Cliente": (df_reporte[c_cli].map(_texto) if c_cli else vacio).values,
        "Fecha": (fechas_col if fechas_col is not None else pd.Series(pd.NaT, index=df_reporte.index)).values,
    })


def mapeo_actual():
    ss = st.session_state

    def valor(clave):
        v = ss.get(clave)
        return None if v in (None, AUTO) else v

    return {"prof": valor("map_prof"), "precio": valor("map_precio"), "cliente": valor("map_cliente"),
            "servicio": valor("map_servicio"), "fecha": valor("map_fecha"), "quincenas": valor("map_quincenas"),
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
    try:
        texto, tablas, n_paginas, estrategia = extraer_contenido_pdf(pdf_bytes)
        mapeo = mapeo_actual()
        rep = construir_reporte(texto, tablas, estrategia, mapeo)
        rep["meta"]["paginas"] = n_paginas
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
    reiniciar_widgets_planilla()
    return True, f"Reporte leído: {rep['meta']['servicios']} servicios procesados."


def reprocesar_pdf():
    ok, msg = ejecutar_procesamiento()
    notificar(msg, "🔄" if ok else "⚠️")


def limpiar_reporte_pdf():
    ss = st.session_state
    _reiniciar_datos_pdf()
    ss["quincenas_multiplicador"] = 1.0
    ss["periodo_texto"] = "1 Quincena (Por defecto)"
    recalcular_bases()
    ss["pdf_hash"], ss["pdf_nombre"], ss["pdf_bytes"] = None, "", None
    ss["pdf_ok"], ss["pdf_error"], ss["pdf_meta"] = False, "", {}
    for k in CLAVES_MAPEO:
        ss.pop(k, None)
    ss["uploader_nonce"] += 1  # vacía el cargador de archivos
    reiniciar_widgets_planilla()
    notificar("Reporte limpiado. La planilla volvió a los valores base.", "🧹")


# =====================================================================
# 9. PLANILLA (fórmulas originales, una sola fuente de verdad)
# =====================================================================
def calcular_fila_planilla(emp, info):
    ss = st.session_state
    base = float(ss.get(f"base_{emp}", 0.0) or 0.0)
    com = float(ss.get(f"com_{emp}", 0.0) or 0.0)
    bonos = float(ss.get(f"hex_{emp}", 0.0) or 0.0)
    desc = float(ss.get(f"desc_{emp}", 0.0) or 0.0)
    renta_calculada = 0.0 if "Porcentaje" in info.get("mod", "") and info.get("rol", "") == "Operativo" else round(base * 0.10, 2)
    t_net = round(base + com + bonos - renta_calculada - desc, 2)
    mod = info.get("mod", MOD_FIJO)
    return {
        "Colaborador": emp, "Rol": info.get("rol", ""),
        "Modalidad": "Estándar" if "Estándar" in mod else "Porcentaje" if "Porcentaje" in mod else "Fijo",
        "Ventas PDF": float(ss.get(f"serv_tot_{emp}", 0.0) or 0.0), "Base": base,
        "Extra": float(ss.get(f"extra_bruto_{emp}", 0.0) or 0.0), "Ret Pub": float(ss.get(f"ret_pub_{emp}", 0.0) or 0.0),
        "Com Neta": com, "Bonos": bonos, "Desc": desc, "Renta": renta_calculada, "Total": t_net,
        "Notas": ss.get(f"notas_{emp}", "Ninguno"), "Email": _texto(ss.get(f"email_{emp}", "")),
        "DUI": info.get("dui", ""), "Cuenta": info.get("cuenta", ""),
    }


def calcular_planilla():
    return [calcular_fila_planilla(emp, info) for emp, info in st.session_state["empleados"].items()]


def servicios_colaborador(emp, info):
    """Todos los servicios del PDF asignados a la persona, con el extra y la comisión de cada uno (mismas fórmulas del pago)."""
    ss = st.session_state
    rep = ss.get("reporte_df")
    indices = ss.get("indices_por_colab", {}).get(emp)
    if rep is None or not indices:
        return None
    d = rep.iloc[indices]
    extra = (d["Precio"] - 60.0).clip(lower=0.0)
    tabla = pd.DataFrame({
        "Fecha": d["Fecha"].dt.strftime("%d/%m/%Y").fillna("—"),
        "Cliente": d["Cliente"].replace("", "—"),
        "Servicio": d["Servicio"].replace("", "—"),
        "Precio": d["Precio"].astype(float),
        "Extra generado": extra.astype(float),
    }).reset_index(drop=True)
    if info.get("rol", "") == "Operativo":
        if "Estándar" in info.get("mod", ""):
            tabla["Comisión"] = (extra - extra * 0.25).values  # extra menos 25% de retención publicitaria
        else:
            tabla["Comisión"] = (d["Precio"] * (float(info.get("porc", 20) or 0) / 100.0)).values
    return tabla


# =====================================================================
# 10. GRÁFICOS (Plotly)
# =====================================================================
def estilo_plotly(fig, height=360):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color="#334155", size=13),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E2E8F0", font=dict(family="Inter, sans-serif", color="#0B1220", size=13)),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5, title=None, font=dict(color="#334155")),
    )
    try:
        fig.update_layout(barcornerradius=5)
    except ValueError:
        pass  # Plotly < 5.19
    return fig


def _ejes_dinero_h(fig):
    fig.update_xaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(color="#0B1220"))


def marcas_ordenadas(dic):
    return [m for m in ORDEN_MARCAS if m in dic] + [m for m in dic if m not in ORDEN_MARCAS]


def grafico_donut_marcas(ingresos_marca):
    marcas = [m for m in marcas_ordenadas(ingresos_marca) if ingresos_marca.get(m, 0) > 0]
    valores = [float(ingresos_marca[m]) for m in marcas]
    fig = go.Figure(go.Pie(
        labels=marcas, values=valores, hole=0.66, sort=False, direction="clockwise",
        marker=dict(colors=[COLORES_MARCA.get(m, "#94A3B8") for m in marcas], line=dict(color="#FFFFFF", width=2)),
        textinfo="percent", textposition="outside", textfont=dict(color="#334155", size=12),
        hovertemplate="<b>%{label}</b><br>$%{value:,.2f} · %{percent}<extra></extra>",
    ))
    fig.add_annotation(text=f"<span style='font-size:12px;color:#64748B'>TOTAL</span><br><b style='font-size:22px;color:#0B1220'>${sum(valores):,.0f}</b>", showarrow=False, x=0.5, y=0.5)
    return estilo_plotly(fig, 360)


def grafico_barras_marcas(ingresos_marca, extras_marca):
    marcas = marcas_ordenadas(ingresos_marca)
    filas = []
    for m in marcas:
        filas.append({"Marca": m, "Concepto": "Ingresos", "Monto": float(ingresos_marca.get(m, 0.0))})
        filas.append({"Marca": m, "Concepto": "Extras (> $60)", "Monto": float(extras_marca.get(m, 0.0))})
    fig = px.bar(pd.DataFrame(filas), y="Marca", x="Monto", color="Concepto", barmode="group", orientation="h",
                 color_discrete_map={"Ingresos": "#2a78d6", "Extras (> $60)": "#eb6834"},
                 category_orders={"Marca": marcas, "Concepto": ["Ingresos", "Extras (> $60)"]})
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{fullData.name}: $%{x:,.2f}<extra></extra>", marker_line_width=0,
                      texttemplate="$%{x:,.0f}", textposition="outside", textfont=dict(color="#334155", size=11), cliponaxis=False)
    fig.update_layout(bargap=0.28, bargroupgap=0.08)
    _ejes_dinero_h(fig)
    fig.update_yaxes(autorange="reversed")
    return estilo_plotly(fig, max(300, 92 * len(marcas) + 80))


def grafico_colaboradores(ventas):
    df = pd.DataFrame([{"Colaborador": k, "Ventas": float(v)} for k, v in ventas.items() if v > 0]).sort_values("Ventas")
    fig = px.bar(df, x="Ventas", y="Colaborador", orientation="h")
    fig.update_traces(marker_color="#2a78d6", marker_line_width=0, texttemplate="$%{x:,.0f}", textposition="outside",
                      textfont=dict(color="#334155"), cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>Servicios: $%{x:,.2f}<extra></extra>")
    fig.update_layout(bargap=0.38, showlegend=False)
    _ejes_dinero_h(fig)
    return estilo_plotly(fig, max(260, 50 * len(df) + 60))


def grafico_top_servicios(df):
    d = df[df["Servicio"].str.strip() != ""]
    top = (d.groupby("Servicio").agg(Ingresos=("Precio", "sum"), Cantidad=("Precio", "size"))
           .sort_values("Ingresos", ascending=False).head(8).sort_values("Ingresos").reset_index())
    top["Etiqueta"] = top["Servicio"].map(lambda s: s if len(s) <= 30 else s[:29] + "…")
    fig = px.bar(top, x="Ingresos", y="Etiqueta", orientation="h", custom_data=["Servicio", "Cantidad"])
    fig.update_traces(marker_color=COLOR_PRIMARIO, marker_line_width=0, texttemplate="$%{x:,.0f}", textposition="outside",
                      textfont=dict(color="#334155"), cliponaxis=False,
                      hovertemplate="<b>%{customdata[0]}</b><br>Ingresos: $%{x:,.2f}<br>Servicios: %{customdata[1]}<extra></extra>")
    fig.update_layout(bargap=0.38, showlegend=False)
    _ejes_dinero_h(fig)
    return estilo_plotly(fig, max(260, 46 * len(top) + 60))


def grafico_tendencia(df):
    d = df.dropna(subset=["Fecha"]).groupby("Fecha")["Precio"].sum().reset_index().sort_values("Fecha")
    fig = go.Figure(go.Scatter(
        x=d["Fecha"], y=d["Precio"], mode="lines+markers",
        line=dict(color=COLOR_PRIMARIO, width=2.5, shape="spline", smoothing=0.6),
        marker=dict(size=8, color=COLOR_PRIMARIO, line=dict(color="#FFFFFF", width=2)),
        fill="tozeroy", fillcolor="rgba(79,70,229,0.10)",
        hovertemplate="%{x|%d/%m/%Y}<br><b>$%{y:,.2f}</b><extra></extra>",
    ))
    fig.update_xaxes(title=None, showgrid=False, tickformat="%d/%m", tickfont=dict(color="#64748B"), linecolor="#CBD5E1")
    fig.update_yaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    return estilo_plotly(fig, 300)


# =====================================================================
# 11. DOCUMENTOS PDF (recibo, memorándum y acta)
# =====================================================================
def _encabezado_pdf(pdf, subtitulo, color=(10, 25, 47), linea_extra=None):
    if os.path.exists(logo_path): pdf.image(logo_path, 10, 8, 25); pdf.set_x(40)
    pdf.set_font('helvetica', 'B', 16); pdf.set_text_color(*color); pdf.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
    if os.path.exists(logo_path): pdf.set_x(40)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(100, 100, 100); pdf.cell(0, 5, limpiar_texto_pdf(subtitulo), 0, 1, 'L')
    if linea_extra:
        if os.path.exists(logo_path): pdf.set_x(40)
        pdf.cell(0, 5, limpiar_texto_pdf(linea_extra), 0, 1, 'L')
    pdf.ln(5)


def generar_recibo_pdf(e_dat, periodo_texto):
    class PDF(FPDF):
        def header(self):
            _encabezado_pdf(self, 'Comprobante Oficial de Pago', linea_extra=f"Periodo Liquidado: {periodo_texto}")

    pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
    pdf.cell(0, 10, limpiar_texto_pdf(f" Colaborador: {e_dat['Colaborador']}"), 0, 1, 'L', fill=True); pdf.ln(5)

    pdf.set_font('helvetica', '', 9); pdf.set_text_color(80, 80, 80)
    txt_banco = f"DUI: {e_dat['DUI']} | Cuenta a Depositar: {e_dat['Cuenta']}" if e_dat['DUI'] or e_dat['Cuenta'] else "Datos bancarios no registrados"
    pdf.cell(0, 5, limpiar_texto_pdf(txt_banco), 0, 1, 'L'); pdf.ln(3)

    pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
    pdf.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)

    for d, v in [("Sueldo Base Acumulado (Bruto)", e_dat['Base']), ("Extra Bruto Generado", e_dat['Extra']), ("Comisiones Netas a Pagar", e_dat['Com Neta']), ("Bonos Extras", e_dat['Bonos'])]:
        if v > 0 or "Sueldo" in d or "Comisiones" in d:
            pdf.cell(130, 8, limpiar_texto_pdf(f"  {d}"), 1, 0, 'L'); pdf.cell(60, 8, f"${v:,.2f}", 1, 1, 'R')

    pdf.set_text_color(201, 42, 42)
    if e_dat['Desc'] > 0:
        pdf.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Desc']:,.2f}", 1, 1, 'R')
    if e_dat['Ret Pub'] > 0:
        pdf.cell(130, 8, limpiar_texto_pdf("  (Informativo) Retención 25% Publicidad"), 1, 0, 'L'); pdf.cell(60, 8, f"${e_dat['Ret Pub']:,.2f}", 1, 1, 'R')
    if e_dat['Renta'] > 0:
        pdf.cell(130, 8, limpiar_texto_pdf("  (-) 10% Retención de Renta"), 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Renta']:,.2f}", 1, 1, 'R')

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
        def header(self):
            _encabezado_pdf(self, 'Memorándum Interno')

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
        def header(self):
            _encabezado_pdf(self, 'Acta de Amonestación', color=(201, 42, 42))

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


def mensaje_recibo(remitente, e_dat, pdf_bytes, nombre_adjunto, periodo_texto):
    msg = MIMEMultipart()
    msg['From'] = remitente; msg['To'] = e_dat["Email"]
    msg['Subject'] = f"Comprobante de Pago - Período: {periodo_texto} | GIO GROUP"
    cuerpo_correo = f"Estimado/a {e_dat['Colaborador']},\n\nAdjunto a este correo electrónico encontrará su Comprobante Oficial de Pago detallado.\n\nAtentamente,\nAdministración GIO GROUP SAS DE CV"
    msg.attach(MIMEText(cuerpo_correo, 'plain'))
    parte_adjunta = MIMEApplication(pdf_bytes, Name=nombre_adjunto)
    parte_adjunta.add_header('Content-Disposition', 'attachment', filename=nombre_adjunto)
    msg.attach(parte_adjunta)
    return msg


def correo_valido(correo):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _texto(correo)))


def registrar_auditoria(tipo, destinatario):
    st.session_state["historial_auditoria"].append({"Fecha": ahora_sv().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": tipo, "Destinatario": destinatario})


# =====================================================================
# 13. PERFIL DE PROVEEDOR (CRM)
# =====================================================================
def _iniciales(nombre):
    partes = [p for p in re.split(r"\s+", _texto(nombre)) if p]
    return ("".join(p[0] for p in partes[:2]) or "?").upper()


def _parse_fecha(v):
    t = _texto(v)
    if not t:
        return None
    fecha = pd.to_datetime(t, dayfirst=not re.match(r"^\d{4}-", t), errors="coerce")
    return None if pd.isna(fecha) else fecha


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


FECHAS_PROVEEDOR = [
    ("📝", "Contrato firmado", "Fecha_Contrato"),
    ("⏳", "Vencimiento del contrato", "Fecha_Vencimiento"),
    ("🔁", "Revisión del contrato", "Fecha_Rev_Contrato"),
    ("✅", "Aprobación", "Fecha_Aprobacion"),
    ("🔍", "Última revisión", "Fecha_Ultima_Rev"),
    ("📆", "Próxima revisión", "Fecha_Prox_Rev"),
    ("🛡️", "Calificación de riesgo", "Fecha_Calif_Riesgo"),
    ("📑", "Diligencia debida", "Fecha_Diligencia"),
]


def nombre_proveedor(p):
    return _texto(p.get("Nombre_Proveedor")) or f"Prov {_texto(p.get('ID_Proveedor'))}"


# --- Eliminación de proveedores (callbacks: se ejecutan antes del rerun automático) ---
def pedir_borrado_proveedor(idx, nombre):
    st.session_state["prov_a_eliminar"] = (idx, nombre)


def cancelar_borrado_proveedor():
    st.session_state.pop("prov_a_eliminar", None)


def confirmar_borrado_proveedor(idx, nombre):
    ss = st.session_state
    ss.pop("prov_a_eliminar", None)
    provs = ss["proveedores"]
    if idx >= len(provs) or nombre_proveedor(provs[idx]) != nombre:
        notificar_error("No se pudo eliminar: la lista de proveedores cambió mientras confirmabas. Inténtalo de nuevo.")
        return
    encabezados = list(provs[idx].keys())
    ss["proveedores"] = provs[:idx] + provs[idx + 1:]
    ss.pop("prov_seleccionado", None)  # la búsqueda vuelve al primer proveedor de la lista
    ss["nonce_editor_prov"] += 1       # la tabla de edición se recarga con la lista nueva
    if guardar_proveedores(ss["proveedores"], encabezados_si_vacio=encabezados):
        notificar(f"Proveedor «{nombre}» eliminado.", "🗑️")
    else:
        notificar_error(f"«{nombre}» se eliminó de esta sesión, pero no se pudo actualizar Google Sheets. Si recargas la app volverá a aparecer.")


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
        h1, h2 = st.columns([5, 1.35])
        with h1:
            md(f"<div class='crm-head'><div class='crm-avatar'>{html.escape(_iniciales(nombre))}</div>"
               f"<div><div class='crm-kicker'>Proveedor</div><div class='crm-name'>{html.escape(nombre)}</div>"
               f"<div class='crm-desc'>{desc}</div><div class='chips' style='margin-top:10px'>{chips}</div></div></div>")
        with h2:
            espacio(14)
            with zona("peligro_eliminar"):
                st.button("🗑️ Eliminar Proveedor", key="btn_eliminar_prov", on_click=pedir_borrado_proveedor, args=(idx, clave), **ancho(st.button))

        if st.session_state.get("prov_a_eliminar") == (idx, clave):
            md(f"<div class='confirmar-borrado'>⚠️ ¿Eliminar definitivamente a <b>{html.escape(nombre)}</b>? "
               f"También se borrará de Google Sheets y no se puede deshacer.</div>")
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
        kpi_html("📆", "Próxima revisión", prox.strftime("%d/%m/%Y") if prox is not None else "—", "Revisión atrasada" if prox_atrasada else "Programada" if prox is not None else "Sin programar", "red" if prox_atrasada else "sky"),
    ])
    espacio(6)

    c1, c2, c3 = st.columns(3)
    with c1:
        with tarjeta("prov_contacto"):
            md(crm_seccion("Información de contacto", "#4F46E5")
               + crm_campo("👤", "Contacto", p.get("Nombre_Contacto"))
               + crm_campo("📞", "Teléfono", p.get("Telefono_1"), "telefono")
               + crm_campo("📧", "Correo electrónico", p.get("Correo"), "correo")
               + crm_campo("📍", "Dirección", p.get("Direccion_1"))
               + crm_campo("🏙️", "Ciudad / Dirección 2", p.get("Direccion_2"))
               + crm_campo("🌎", "País", p.get("Pais")))
    with c2:
        with tarjeta("prov_finanzas"):
            md(crm_seccion("Datos financieros", "#059669")
               + crm_campo("🏦", "Banco", p.get("Banco"))
               + crm_campo("💳", "Número de cuenta", p.get("Cuenta"), "mono")
               + crm_campo("🤝", "Patrocinador", p.get("Patrocinador"))
               + crm_campo("☎️", "Teléfono del patrocinador", p.get("Telefono_2"), "telefono"))
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
# 14. ESTILOS + MENÚ LATERAL
# =====================================================================
md(CSS)
mostrar_notificaciones()

with st.sidebar:
    if os.path.exists(logo_path):
        st.image(logo_path, **ancho(st.image))
    else:
        md(f"<div class='brand'><img src='{IMG_LOGO}' alt=''/><div><div class='brand-name'>Gio Group</div><div class='brand-sub'>Suite administrativa</div></div></div>")

    menu_seleccionado = option_menu(
        None,
        ["Dashboard", "Planillas", "Directorio de Proveedores", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "journal-bookmark-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        default_index=0, key="menu_principal",
        styles={
            "container": {"padding": "0", "background-color": "transparent"},
            "icon": {"font-size": "15px"},
            "nav-link": {"font-family": "Inter, -apple-system, Segoe UI, sans-serif", "font-size": "14px", "font-weight": "500",
                         "color": "#475569", "border-radius": "10px", "margin": "2px 0", "padding": "10px 12px", "--hover-color": "#F1F5F9"},
            "nav-link-selected": {"background-color": "#EEF2FF", "color": "#4338CA", "font-weight": "600"},
        },
    )

    if "sheets_ok" not in st.session_state:
        st.session_state["sheets_ok"] = _documento() is not None
    estado_sheets = "<span class='dot on'></span><b>Conectado</b>" if st.session_state["sheets_ok"] else "<span class='dot off'></span><b>Modo local</b>"
    estado_pdf = "<span class='dot on'></span><b>Sincronizado</b>" if st.session_state["pdf_ok"] else "<span class='dot off'></span><b>Pendiente</b>"
    md(f"<div class='side-card'><div class='side-title'>Estado del sistema</div>"
       f"<div class='side-row'><span>Google Sheets</span><span>{estado_sheets}</span></div>"
       f"<div class='side-row'><span>Reporte de ventas</span><span>{estado_pdf}</span></div>"
       f"<div class='side-row'><span>Quincenas</span><b>{st.session_state['quincenas_multiplicador']:g}</b></div>"
       f"<div class='side-row'><span>Colaboradores</span><b>{len(st.session_state['empleados'])}</b></div></div>")
    md("<div class='profile'><div class='avatar'>GG</div><div><div class='profile-name'>Administración</div><div class='profile-role'>Gerencia General</div></div></div>")


# =====================================================================
# 15. PANEL DE SINCRONIZACIÓN DEL PDF (Dashboard y Planillas)
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
    md(f"<div class='hero'><div class='hero-body'><div class='hero-kicker'>{fecha}</div>"
       f"<div class='hero-title'>{saludo}, Gerencia</div>"
       f"<div class='hero-sub'>El pulso de Gio Group en una sola vista: ingresos, planilla y rentabilidad del período, calculados directamente desde el reporte de ventas.</div>"
       f"<div class='hero-chips'>{chips}</div></div><img class='hero-img' src='{IMG_HERO}' alt=''/></div>")


def panel_diagnostico():
    ss = st.session_state
    if not ss.get("pdf_bytes"):
        return
    meta = ss.get("pdf_meta") or {}
    with st.expander("🔬 Diagnóstico de lectura y ajustes del reporte", expanded=not ss.get("pdf_ok", False)):
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
            chips += chip(f"📅 Período: {meta['periodo_fuente']}", "indigo")
        md(f"<div class='chips'>{chips}</div>")

        columnas = meta.get("columnas") or []
        if columnas:
            md(titulo_seccion("Columnas del reporte", "Se detectan solas. Si alguna no es la correcta, elígela aquí y todo se recalcula."))
            opciones = [AUTO] + columnas
            a, b, c, d, e = st.columns(5)
            a.selectbox("👤 Profesional", opciones, key="map_prof", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_prof') or '—'}")
            b.selectbox("💲 Precio", opciones, key="map_precio", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_pre') or '—'}")
            c.selectbox("🙍 Cliente", opciones, key="map_cliente", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_cli') or '—'}")
            d.selectbox("💆 Servicio", opciones, key="map_servicio", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_ser') or '—'}")
            e.selectbox("📅 Fecha", opciones, key="map_fecha", on_change=reprocesar_pdf, help=f"Detectada: {meta.get('c_fecha') or '—'}")
            f, g = st.columns([1, 2])
            f.selectbox("🗓️ Quincenas a liquidar", [AUTO, 1.0, 2.0, 3.0, 4.0, 6.0], key="map_quincenas", on_change=reprocesar_pdf,
                        format_func=lambda v: f"Automático ({st.session_state['quincenas_multiplicador']:g})" if v == AUTO else f"{v:g} quincena(s)")
            with g:
                espacio(28)
                st.checkbox("Asignar filas sin nombre al profesional de arriba (reportes agrupados)", value=True, key="map_ffill", on_change=reprocesar_pdf)

        if ss.get("resumen_pdf"):
            md(titulo_seccion("Coincidencias por colaborador", "Cuántos servicios del PDF se asignaron a cada persona según su alias."))
            df_res = pd.DataFrame.from_dict(ss["resumen_pdf"], orient="index").reset_index().rename(columns={"index": "Colaborador"})
            st.dataframe(df_res.style.format({"Ventas": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
        if meta.get("sin_asignar"):
            st.warning(f"Hay {len(meta['sin_asignar'])} nombre(s) en el PDF que no coinciden con ningún colaborador. Sus ventas cuentan en los ingresos, pero no generan comisión. Agrega el nombre como alias en Configuración → Personal.")
            st.dataframe(pd.DataFrame(meta["sin_asignar"]).style.format({"Ventas": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
        if meta.get("multiples"):
            st.warning(f"{meta['multiples']} servicio(s) coinciden con más de un colaborador: revisa que los alias no se repitan.")
        if ss.get("reporte_df") is not None:
            md(titulo_seccion("Vista previa de servicios leídos"))
            st.dataframe(ss["reporte_df"].head(25).style.format({"Precio": "${:,.2f}", "Extra": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
        elif meta.get("muestra_texto"):
            md(titulo_seccion("Texto extraído del PDF", "Útil para revisar el formato si no se reconoce la tabla."))
            st.code(meta["muestra_texto"], language=None)


def panel_sincronizacion():
    ss = st.session_state
    with tarjeta("sync"):
        md(titulo_seccion("📥 Reporte de ventas", "Sube el PDF del período y la planilla completa se calcula de una sola vez."))
        c1, c2 = st.columns([3, 1])
        with c1:
            archivo_subido = st.file_uploader("Reporte de ventas (PDF)", type=["pdf"], key=f"pdf_uploader_{ss['uploader_nonce']}", label_visibility="collapsed")
        with c2:
            st.button("🔄 Recalcular", on_click=reprocesar_pdf, disabled=not ss.get("pdf_bytes"), **ancho(st.button))
            st.button("🧹 Limpiar reporte", on_click=limpiar_reporte_pdf, **ancho(st.button))

        if archivo_subido is not None:
            pdf_bytes = archivo_subido.getvalue()
            pdf_hash = hashlib.md5(pdf_bytes).hexdigest()
            # Solo se procesa un archivo NUEVO: navegar o editar no vuelve a leer ni pisa los cambios manuales
            if pdf_hash != ss["pdf_hash"]:
                ss["pdf_hash"], ss["pdf_nombre"], ss["pdf_bytes"] = pdf_hash, archivo_subido.name, pdf_bytes
                for k in CLAVES_MAPEO:
                    ss.pop(k, None)
                with st.spinner("Analizando el reporte de ventas..."):
                    ok, msg = ejecutar_procesamiento()
                st.toast(msg, icon="✅" if ok else "⚠️")

        chips = chip(f"📅 {html.escape(ss['periodo_texto'])}", "indigo")
        if ss.get("pdf_nombre"):
            chips += chip(f"📄 {html.escape(ss['pdf_nombre'])}", "green" if ss.get("pdf_ok") else "red")
        if ss.get("pdf_ok"):
            chips += chip(f"🧾 {ss['pdf_meta'].get('servicios', 0)} servicios · {usd(ss['total_ingresos_pdf'])}", "green")
        md(f"<div class='chips'>{chips}</div>")
        panel_diagnostico()
    espacio(6)


# =====================================================================
# 16. PÁGINAS
# =====================================================================
ss = st.session_state

if menu_seleccionado == "Dashboard":
    hero_dashboard()
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
            kpi_html("👥", "Planilla neta", usd(costo_planilla), f"{(costo_planilla / ingresos * 100 if ingresos else 0):.1f}% de los ingresos", "sky"),
            kpi_html("🏦", "Utilidad estimada", usd(utilidad), "Ingresos − planilla neta", "green" if utilidad >= 0 else "red", "pos" if utilidad >= 0 else "neg"),
            kpi_html("📈", "Margen neto", f"{margen:,.1f}%", "Sobre ingresos brutos", "violet", "pos" if margen >= 0 else "neg"),
        ])
        espacio(12)
        fila_kpis([
            kpi_html("✨", "Extras generados", usd(extras_total), "Excedente sobre $60 por servicio", "amber"),
            kpi_html("💼", "Comisiones netas", usd(comisiones_total), "A pagar a colaboradores", "indigo"),
            kpi_html("🏛️", "Renta retenida", usd(renta_total), "10% sobre sueldos base", "sky"),
            kpi_html("🗓️", "Quincenas", f"{ss['quincenas_multiplicador']:g}", html.escape(ss["periodo_texto"]), "violet"),
        ])
        espacio(14)

        if ss["ingresos_por_marca"]:
            g1, g2 = st.columns([1, 1.35])
            with g1:
                with tarjeta("donut"):
                    md(titulo_seccion("Ingresos por marca", "Participación de cada unidad de negocio"))
                    st.plotly_chart(grafico_donut_marcas(ss["ingresos_por_marca"]), config=PLOTLY_CONFIG, **ancho(st.plotly_chart))
            with g2:
                with tarjeta("barras"):
                    md(titulo_seccion("Ingresos vs. extras por marca", "Extra = excedente sobre $60 por servicio"))
                    st.plotly_chart(grafico_barras_marcas(ss["ingresos_por_marca"], ss["extras_por_marca"]), config=PLOTLY_CONFIG, **ancho(st.plotly_chart))

        ventas_colab = {emp: ss.get(f"serv_tot_{emp}", 0.0) for emp in ss["empleados"].keys()}
        hay_servicios = rep_df is not None and (rep_df["Servicio"].str.strip() != "").any()
        h1, h2 = st.columns(2) if hay_servicios else (st.container(), None)
        if any(v > 0 for v in ventas_colab.values()):
            with h1:
                with tarjeta("colaboradores"):
                    md(titulo_seccion("Ventas por colaborador", "Servicios facturados en el período"))
                    st.plotly_chart(grafico_colaboradores(ventas_colab), config=PLOTLY_CONFIG, **ancho(st.plotly_chart))
        if hay_servicios and h2 is not None:
            with h2:
                with tarjeta("top_servicios"):
                    md(titulo_seccion("Servicios más rentables", "Top 8 por ingresos"))
                    st.plotly_chart(grafico_top_servicios(rep_df), config=PLOTLY_CONFIG, **ancho(st.plotly_chart))

        if rep_df is not None and rep_df["Fecha"].notna().any() and rep_df["Fecha"].nunique() >= 2:
            with tarjeta("tendencia"):
                md(titulo_seccion("Tendencia de ingresos diarios", "Suma de servicios por día"))
                st.plotly_chart(grafico_tendencia(rep_df), config=PLOTLY_CONFIG, **ancho(st.plotly_chart))

        with tarjeta("resumen_colab"):
            md(titulo_seccion("Resumen ejecutivo por colaborador", "Ventas, comisión y neto a pagar del período"))
            df_res = pd.DataFrame([{
                "Colaborador": f["Colaborador"], "Modalidad": f["Modalidad"],
                "Servicios": ss["resumen_pdf"].get(f["Colaborador"], {}).get("Servicios", 0),
                "Ventas": f["Ventas PDF"], "Comisión neta": f["Com Neta"], "Neto a pagar": f["Total"],
            } for f in filas]).sort_values("Ventas", ascending=False)
            st.dataframe(df_res.style.format({"Ventas": "${:,.2f}", "Comisión neta": "${:,.2f}", "Neto a pagar": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))
    else:
        estado_vacio(IMG_REPORTE, "Tu tablero está listo para el primer reporte",
                     "Sube el PDF de ventas en el panel de arriba y la app calculará todo de una sola vez.",
                     ["Exporta el reporte de ventas del período en PDF.",
                      "Arrástralo al panel «Reporte de ventas».",
                      "Revisa el diagnóstico: servicios leídos, extras y comisiones por colaborador."])

elif menu_seleccionado == "Planillas":
    encabezado_pagina("💼", "Planillas", "Sueldos, extras sobre $60, comisiones del 20% y recibos de pago.")
    panel_sincronizacion()

    resumen_planilla = st.container()

    if ss.get("detalle_extras"):
        with st.expander(f"🔍 Desglose de servicios con extra · {len(ss['detalle_extras'])} servicios sobre $60"):
            st.dataframe(pd.DataFrame(ss["detalle_extras"]).style.format({"Precio Final": "${:,.2f}", "Extra Generado": "${:,.2f}", "Retención (25%)": "${:,.2f}", "Comisión Neta": "${:,.2f}"}), hide_index=True, **ancho(st.dataframe))

    md(titulo_seccion("👥 Colaboradores", "Abre cada colaborador para ajustar bonos, descuentos o notas. El neto se recalcula al instante."))
    datos_emp = []
    for emp, info in ss["empleados"].items():
        mod = info.get("mod", MOD_FIJO)
        if "Estándar" in mod:
            etiqueta_mod = "Estándar · extras sobre $60"
        elif "Porcentaje" in mod:
            etiqueta_mod = f"Porcentaje · {float(info.get('porc', 0) or 0):g}% de ventas"
        else:
            etiqueta_mod = "Salario fijo"
        with st.expander(f"👤 {emp}  ·  {info.get('rol', '')}  ·  {etiqueta_mod}"):
            r = ss.get("resumen_pdf", {}).get(emp)
            if r:
                chips = chip(f"🧾 {r['Servicios']} servicios", "indigo") + chip(f"💰 Ventas {usd(r['Ventas'])}", "green")
                if "Estándar" in mod:
                    chips += chip(f"✨ {r['Servicios > $60']} sobre $60 · extra {usd(ss.get(f'extra_bruto_{emp}', 0))}", "amber")
                    chips += chip(f"📣 Retención 25% {usd(ss.get(f'ret_pub_{emp}', 0))}", "sky")
            else:
                chips = chip("Sin datos del reporte de ventas")
            if "Porcentaje" in mod:
                chips = chip("🪙 Sin sueldo base · gana solo su %", "violet") + chips
            else:
                chips = chip(f"🪙 Sueldo neto {usd(sueldo_neto_de(info))} / quincena", "violet") + chips
            md(f"<div class='chips'>{chips}</div>")

            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                campo_persistente(st.number_input, "Sueldo Base ($)", f"base_{emp}", f"ui_b_{emp}", conv=float, step=0.01, format="%.2f",
                                  help="Sueldo neto quincenal de la persona (Configuración → Personal) ÷ 0.90 × quincenas del período. Modalidad Porcentaje: $0.")
                campo_persistente(st.number_input, "Comisiones ($)", f"com_{emp}", f"ui_c_{emp}", conv=float, step=0.01, format="%.2f",
                                  help="Estándar: (precio − 60) × 75% por cada servicio mayor a $60. Porcentaje: ventas × %.")
            with c2:
                campo_persistente(st.number_input, "Bonos ($)", f"hex_{emp}", f"ui_h_{emp}", conv=float, step=0.01, format="%.2f")
                campo_persistente(st.number_input, "Descuentos ($)", f"desc_{emp}", f"ui_d_{emp}", conv=float, step=0.01, format="%.2f")
            with c3:
                campo_persistente(st.text_input, "Notas", f"notas_{emp}", f"n_{emp}", conv=str)
                campo_persistente(st.text_input, "Correo", f"email_{emp}", f"ui_e_{emp}", conv=str)

            fila = calcular_fila_planilla(emp, info)
            md(f"<div class='neto'><div><div class='neto-label'>Neto a pagar</div>"
               f"<div class='neto-formula'>Base {usd(fila['Base'])} + Comisión {usd(fila['Com Neta'])} + Bonos {usd(fila['Bonos'])} − Renta {usd(fila['Renta'])} − Descuentos {usd(fila['Desc'])}</div></div>"
               f"<div class='neto-valor'>{usd(fila['Total'])}</div></div>")

            # Historial completo de servicios del período (transparencia total del pago)
            servicios = servicios_colaborador(emp, info)
            espacio(6)
            if servicios is not None and not servicios.empty:
                md(titulo_seccion(f"🧾 Servicios del período · {len(servicios)}", "Cada servicio del PDF asignado a esta persona."))
                cols_dinero = [c for c in ("Precio", "Extra generado", "Comisión") if c in servicios.columns]
                resumen_serv = chip(f"Ventas {usd(servicios['Precio'].sum())}", "green") + chip(f"Extra {usd(servicios['Extra generado'].sum())}", "amber")
                if "Comisión" in servicios.columns:
                    resumen_serv += chip(f"Comisión {usd(servicios['Comisión'].sum())}", "indigo")
                md(f"<div class='chips'>{resumen_serv}</div>")
                st.dataframe(servicios.style.format("${:,.2f}", subset=cols_dinero), hide_index=True,
                             height=min(420, 38 + 35 * len(servicios)), **ancho(st.dataframe))
            elif ss.get("pdf_ok"):
                md(f"<div class='chips'>{chip('No se encontraron servicios de esta persona en el reporte. Revisa su alias en Configuración.', 'amber')}</div>")
            else:
                md(f"<div class='chips'>{chip('Sube el reporte de ventas para ver el detalle de servicios.')}</div>")
        datos_emp.append(fila)

    if datos_emp:
        with resumen_planilla:
            fila_kpis([
                kpi_html("🧾", "Planilla neta a pagar", usd(sum(d["Total"] for d in datos_emp)), f"{len(datos_emp)} colaboradores", "indigo"),
                kpi_html("🪙", "Sueldos base", usd(sum(d["Base"] for d in datos_emp)), f"{ss['quincenas_multiplicador']:g} quincena(s)", "sky"),
                kpi_html("💼", "Comisiones netas", usd(sum(d["Com Neta"] for d in datos_emp)), "Extras y porcentajes", "green"),
                kpi_html("🏛️", "Renta retenida", usd(sum(d["Renta"] for d in datos_emp)), "10% sobre sueldo base", "amber"),
            ])
            espacio(14)

        espacio(8)
        with tarjeta("tabla_planilla"):
            md(titulo_seccion("📊 Planilla consolidada", "Incluye la fila de TOTAL general."))
            cols_num = ["Ventas PDF", "Base", "Extra", "Ret Pub", "Com Neta", "Bonos", "Desc", "Renta", "Total"]
            df_pl = pd.DataFrame(datos_emp)
            df_tabla = df_pl[["Colaborador", "Modalidad"] + cols_num].copy()
            totales = {c: float(df_tabla[c].sum()) for c in cols_num}
            totales.update({"Colaborador": "TOTAL", "Modalidad": ""})
            df_tabla = pd.concat([df_tabla, pd.DataFrame([totales])], ignore_index=True)

            def _resaltar_total(fila_tabla):
                estilo = "font-weight:700;background-color:#EEF2FF;color:#3730A3" if fila_tabla["Colaborador"] == "TOTAL" else ""
                return [estilo] * len(fila_tabla)

            st.dataframe(df_tabla.style.format("${:,.2f}", subset=cols_num).apply(_resaltar_total, axis=1), hide_index=True, **ancho(st.dataframe))
            csv = df_pl.drop(columns=["Email", "DUI", "Cuenta"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Exportar planilla (Excel / CSV)", data=csv, file_name=f"Planilla_{ahora_sv().strftime('%Y-%m-%d')}.csv", mime="text/csv")

        espacio(8)
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

                # El recibo solo se muestra/envía si corresponde al colaborador seleccionado
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

# --- MÓDULO: DIRECTORIO DE PROVEEDORES ---
elif menu_seleccionado == "Directorio de Proveedores":
    encabezado_pagina("📇", "Directorio de Proveedores", "Perfil 360° de cada proveedor: contacto, datos financieros y control de contratos.")
    proveedores = ss["proveedores"]
    nombres_provs = [nombre_proveedor(p) for p in proveedores]

    col_sel, col_info = st.columns([2.2, 1])
    with col_sel:
        prov_seleccionado = st.selectbox("🔎 Buscar proveedor", nombres_provs, key="prov_seleccionado", placeholder="Escribe para buscar...")
    with col_info:
        alertas = sum(1 for p in proveedores if estado_contrato(p)[1] in ("red", "amber"))
        chips = chip(f"📇 {len(proveedores)} proveedores", "indigo")
        if alertas:
            chips += chip(f"⚠️ {alertas} contrato(s) por atender", "amber")
        espacio(26)
        md(f"<div class='chips'>{chips}</div>")

    if prov_seleccionado:
        idx = nombres_provs.index(prov_seleccionado)
        render_perfil_proveedor(proveedores[idx], idx)
    else:
        estado_vacio(IMG_DIRECTORIO, "Aún no hay proveedores", "Agrega el primero desde el editor de abajo.")

    espacio(8)
    with st.expander("✏️ Agregar / editar proveedores (base de datos)", expanded=not proveedores):
        df_prov = pd.DataFrame(proveedores) if proveedores else pd.DataFrame(columns=list(PROVEEDOR_EJEMPLO.keys()))
        # El nonce reinicia el editor tras guardar o eliminar (evita filas duplicadas o ediciones aplicadas a otra fila)
        df_prov_edited = st.data_editor(df_prov, num_rows="dynamic", key=f"editor_proveedores_{ss['nonce_editor_prov']}", **ancho(st.data_editor))
        if st.button("💾 Guardar cambios de proveedores", type="primary"):
            registros = _registros_validos(df_prov_edited.to_dict("records"))
            if not registros:
                st.toast("La lista de proveedores está vacía; no se guardó nada.", icon="⚠️")
            else:
                ss["proveedores"] = registros
                ss["nonce_editor_prov"] += 1
                if guardar_proveedores(registros):
                    notificar("Base de proveedores actualizada.", "✅")
                else:
                    notificar_error("No se pudo sincronizar con Google Sheets. Los cambios de proveedores quedaron solo en esta sesión.")
                st.rerun()

elif menu_seleccionado == "Memorándums":
    encabezado_pagina("📝", "Memorándums internos", "Comunicaciones oficiales en PDF con la identidad de Gio Group.")
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
                    registrar_auditoria("Memorándum", emp_memo)
                    st.toast("Memorándum generado.", icon="📝")
                else:
                    st.toast("Escribe el contenido del memorándum.", icon="ℹ️")
            if 'temp_memo_pdf' in ss:
                st.download_button("⬇️ Descargar memorándum", data=ss['temp_memo_pdf'], file_name=ss['temp_memo_path'], mime="application/pdf")
    with c_tips:
        with tarjeta("memo_tips"):
            md(titulo_seccion("Buenas prácticas")
               + "<div class='tips'>"
               + "<div class='tip'><span>🎯</span>Un solo tema por memorándum; el asunto debe resumirlo.</div>"
               + "<div class='tip'><span>📅</span>Indica fechas y plazos concretos cuando haya una instrucción.</div>"
               + "<div class='tip'><span>✍️</span>Imprime y pide la firma de recibido del colaborador.</div>"
               + "<div class='tip'><span>🗂️</span>Cada documento queda registrado en Auditoría.</div></div>")

elif menu_seleccionado == "Amonestaciones":
    encabezado_pagina("⚠️", "Faltas y amonestaciones", "Documenta incidentes y genera actas formales con espacio para firmas.")
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
                    registrar_auditoria(f"Acta: {tipo_falta}", emp_amon)
                    st.toast("Acta redactada.", icon="⚖️")
                else:
                    st.toast("Describe el incidente para poder redactar el acta.", icon="ℹ️")
            if 'temp_amon_pdf' in ss:
                st.download_button("⬇️ Descargar acta", data=ss['temp_amon_pdf'], file_name=ss['temp_amon_path'], mime="application/pdf")
    with c_hist:
        with tarjeta("amon_hist"):
            actas = [h for h in ss["historial_auditoria"] if str(h.get("Tipo Documento", "")).startswith("Acta")]
            md(titulo_seccion("Historial de la sesión", f"{len(actas)} acta(s) generadas"))
            if actas:
                conteo = pd.Series([a["Destinatario"] for a in actas]).value_counts()
                md("<div class='tips'>" + "".join(f"<div class='tip'><span>👤</span><b>{html.escape(n)}</b>&nbsp;· {c} acta(s)</div>" for n, c in conteo.items()) + "</div>")
            else:
                md("<div class='tips'><div class='tip'><span>✅</span>Sin actas registradas en esta sesión.</div></div>")

elif menu_seleccionado == "Auditoría":
    encabezado_pagina("🗂️", "Registro de auditoría", "Trazabilidad de los documentos generados y enviados en esta sesión.")
    historial = ss["historial_auditoria"]
    if historial:
        df_aud = pd.DataFrame(historial)
        recibos = int(df_aud["Tipo Documento"].str.startswith("Recibo").sum())
        fila_kpis([
            kpi_html("🗂️", "Documentos", str(len(df_aud)), "Total de la sesión", "indigo"),
            kpi_html("📨", "Recibos enviados", str(recibos), "Por Gmail", "green"),
            kpi_html("📝", "Memos y actas", str(len(df_aud) - recibos), "Generados en PDF", "amber"),
        ])
        espacio(12)
        with tarjeta("auditoria"):
            st.dataframe(df_aud.iloc[::-1], hide_index=True, **ancho(st.dataframe))
            st.download_button("⬇️ Exportar registro (CSV)", data=df_aud.to_csv(index=False).encode("utf-8-sig"), file_name="Auditoria.csv", mime="text/csv")
        st.caption("El registro se guarda durante la sesión: descárgalo antes de cerrar la app.")
    else:
        estado_vacio(IMG_REPORTE, "El registro está limpio", "Los recibos enviados, memorándums y actas aparecerán aquí.")

elif menu_seleccionado == "Configuración":
    encabezado_pagina("⚙️", "Configuración", "Personal, sueldos individuales y conexión con Google Sheets.")
    tab_personal, tab_conexion = st.tabs(["👥 Personal y sueldos", "☁️ Conexión"])

    with tab_personal:
        st.caption("**Sueldo base neto**: lo que recibe cada persona por quincena. El bruto se calcula como neto ÷ 0.90 × quincenas del período. "
                   "En modalidad Porcentaje el sueldo no se usa (base en cero y sin renta). "
                   "**Alias**: el nombre con el que la persona aparece en el PDF de ventas (varios separados con |, por ejemplo GIO|MARVIN); si se deja vacío se usa su primer nombre.")
        df_emp = pd.DataFrame([{"Nombre": n, "rol": i.get("rol", ""), "mod": i.get("mod", MOD_FIJO),
                                "sueldo_base_neto": float(sueldo_neto_de(i)), "porc": float(i.get("porc", 0) or 0),
                                "alias": i.get("alias", ""), "correo": i.get("correo", ""), "dui": i.get("dui", ""), "cuenta": i.get("cuenta", "")}
                               for n, i in ss["empleados"].items()])
        df_editado = st.data_editor(
            df_emp, num_rows="dynamic", hide_index=True, key=f"editor_personal_{ss['nonce_editor_personal']}",
            column_config={
                "Nombre": st.column_config.TextColumn("Nombre", required=True),
                "rol": st.column_config.SelectboxColumn("Rol", options=ROLES, required=True),
                "mod": st.column_config.SelectboxColumn("Modalidad", options=MODALIDADES, required=True, width="medium"),
                "sueldo_base_neto": st.column_config.NumberColumn("Sueldo base neto (quincenal)", min_value=0.0, step=0.01, format="$%.2f",
                                                                  help="Neto que recibe la persona por quincena. Se ignora en modalidad Porcentaje."),
                "porc": st.column_config.NumberColumn("% Comisión", min_value=0, max_value=100, step=1, format="%.0f"),
                "alias": st.column_config.TextColumn("Alias en el PDF"),
                "correo": st.column_config.TextColumn("Correo"),
                "dui": st.column_config.TextColumn("DUI"),
                "cuenta": st.column_config.TextColumn("Cuenta bancaria"),
            },
            **ancho(st.data_editor),
        )
        if st.button("💾 Guardar cambios de personal", type="primary"):
            nuevos = {}
            for r in df_editado.to_dict("records"):
                nombre = _texto(r.get("Nombre"))
                if not nombre:
                    continue
                mod = normalizar_modalidad(r.get("mod"))
                rol = normalizar_rol(r.get("rol"))
                sueldo = _a_numero(r.get("sueldo_base_neto"))
                nuevos[nombre] = {"rol": rol, "alias": _texto(r.get("alias")), "mod": mod,
                                  "porc": _a_porcentaje(r.get("porc"), 20.0 if mod == MOD_PORCENTAJE else 0.0),
                                  "sueldo_base_neto": sueldo if sueldo is not None else sueldo_neto_por_defecto(rol),
                                  "correo": _texto(r.get("correo")), "dui": _texto(r.get("dui")), "cuenta": _texto(r.get("cuenta"))}
            if not nuevos:
                st.error("Debe existir al menos un colaborador con nombre.")
            else:
                anteriores = ss["empleados"]
                ss["empleados"] = nuevos
                inicializar_empleados()
                for emp, info in nuevos.items():
                    ss[f"email_{emp}"] = info["correo"]
                    ss.pop(f"ui_e_{emp}", None)
                    previo = anteriores.get(emp)
                    if (previo is None or previo.get("rol") != info["rol"] or previo.get("mod") != info["mod"]
                            or sueldo_neto_de(previo) != info["sueldo_base_neto"]):
                        ss[f"base_{emp}"] = 0.0 if "Porcentaje" in info["mod"] else calcular_bruto_acumulado(info)
                reiniciar_widgets_planilla()
                if ss.get("pdf_bytes"):
                    ejecutar_procesamiento()  # alias, modalidades y sueldos nuevos se aplican al reporte cargado
                ss["nonce_editor_personal"] += 1  # el editor se recarga con los datos guardados
                if guardar_empleados(nuevos):
                    notificar("Personal y sueldos actualizados. Planilla recalculada.", "✅")
                else:
                    notificar_error("No se pudo sincronizar con Google Sheets. Los cambios de personal quedaron solo en esta sesión.")
                st.rerun()

    with tab_conexion:
        with tarjeta("conexion"):
            conectado = _documento() is not None
            ss["sheets_ok"] = conectado
            fuente = html.escape(ss.get("fuente_personal", "—"))
            if conectado:
                md("<div class='chips'>" + chip("✅ Conectado a Google Sheets", "green") + chip(f"Personal cargado desde: {fuente}", "indigo") + "</div>")
            else:
                st.warning("⚠️ **MODO LOCAL ACTIVADO:** no se detectan credenciales de Google Cloud o no hay conexión. Los cambios no se guardan en la nube.")
            k1, k2 = st.columns(2)
            if k1.button("🔌 Reintentar conexión", **ancho(st.button)):
                _abrir_documento.clear()
                ss.pop("sheets_ok", None)
                notificar("Conexión reintentada.", "🔌")
                st.rerun()
            if k2.button("⬇️ Recargar datos desde Google Sheets", **ancho(st.button)):
                ss["empleados"], ss["fuente_personal"] = cargar_empleados()
                ss["proveedores"] = cargar_proveedores()
                inicializar_empleados()
                if ss.get("pdf_bytes"):
                    ejecutar_procesamiento()
                notificar(f"Datos recargados ({ss['fuente_personal']}).", "☁️")
                st.rerun()
