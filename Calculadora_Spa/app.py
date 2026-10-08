import streamlit as st
import pandas as pd
import io
import os
import re
import html
import hashlib
from datetime import datetime
import pdfplumber
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from fpdf import FPDF
from PIL import Image
from streamlit_option_menu import option_menu
import gspread
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go


# =====================================================================
# 0. UTILIDADES DE SEGURIDAD Y GOOGLE SHEETS
# =====================================================================
def limpiar_texto_pdf(txt):
    if txt is None:
        return ""
    return str(txt).encode('latin-1', 'replace').decode('latin-1')


def generar_pdf_bytes(pdf_obj):
    return bytes(pdf_obj.output())


@st.cache_resource
def conectar_gsheets(nombre_hoja="Personal"):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        skey = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(skey, scopes=scopes)
        gc = gspread.authorize(credentials)
        sheet_url = st.secrets["gsheets"]["url"]
        doc = gc.open_by_url(sheet_url)
        try:
            return doc.worksheet(nombre_hoja)
        except Exception:
            return doc.sheet1
    except Exception:
        return None


def _valor_para_sheets(v):
    """Convierte NaN/None/numpy/fechas a tipos que la API de Sheets acepta (evita errores JSON)."""
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
    """Descarta filas totalmente vacías (p. ej. filas nuevas sin llenar del data_editor)."""
    if not datos_list:
        return []
    return [r for r in datos_list if any(_valor_para_sheets(v) != "" for v in r.values())]


def _escribir_hoja(nombre_hoja, datos_list):
    datos_list = _registros_validos(datos_list)
    if not datos_list:
        return False
    worksheet = conectar_gsheets(nombre_hoja)
    if not worksheet:
        return False
    encabezados = list(datos_list[0].keys())
    filas = [encabezados]
    for item in datos_list:
        filas.append([_valor_para_sheets(item.get(c, "")) for c in encabezados])
    try:
        worksheet.clear()
        worksheet.update(values=filas, range_name="A1")
        return True
    except Exception:
        return False


# --- CARGA Y GUARDADO DE DATOS (EMPLEADOS, PROVEEDORES) ---
def cargar_empleados():
    worksheet = conectar_gsheets("Personal")
    if worksheet:
        try:
            records = worksheet.get_all_records()
            if records:
                emp_dict = {}
                for r in records:
                    nombre = r.get("Nombre")
                    if nombre:
                        emp_dict[nombre] = {
                            "rol": str(r.get("Rol", "Operativo")), "alias": str(r.get("Alias", "")),
                            "mod": str(r.get("Modalidad", "Fijo")), "porc": float(r.get("Porcentaje", 0)),
                            "correo": str(r.get("Correo", "")), "dui": str(r.get("DUI", "")), "cuenta": str(r.get("Cuenta", ""))
                        }
                return emp_dict
        except Exception:
            pass
    return {
        "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY", "mod": "Estándar (Con retención 25% Pub)", "porc": 20, "correo": "", "dui": "", "cuenta": ""},
        "Luis Violante": {"rol": "Operativo", "alias": "LUIS", "mod": "Estándar (Con retención 25% Pub)", "porc": 20, "correo": "", "dui": "", "cuenta": ""},
        "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA", "mod": "Porcentaje Directo (%)", "porc": 20, "correo": "", "dui": "", "cuenta": ""},
        "Mario de Paz": {"rol": "Operativo", "alias": "MARIO", "mod": "Estándar (Con retención 25% Pub)", "porc": 20, "correo": "", "dui": "", "cuenta": ""},
        "Dr. Gio Molina": {"rol": "Administrativo", "alias": "GIO|MARVIN|DOCTOR", "mod": "Fijo", "porc": 0, "correo": "", "dui": "", "cuenta": ""},
        "Gerson Ulises Molina Flores": {"rol": "Administrativo", "alias": "GERSON", "mod": "Fijo", "porc": 0, "correo": "", "dui": "", "cuenta": ""},
        "Edwin Ponce": {"rol": "Administrativo", "alias": "EDWIN", "mod": "Fijo", "porc": 0, "correo": "", "dui": "", "cuenta": ""}
    }


def guardar_empleados(datos):
    if not datos:
        return False
    worksheet = conectar_gsheets("Personal")
    if not worksheet:
        return False
    filas = [["Nombre", "Rol", "Alias", "Modalidad", "Porcentaje", "Correo", "DUI", "Cuenta"]]
    for nombre, info in datos.items():
        filas.append([_valor_para_sheets(x) for x in [nombre, info.get("rol", ""), info.get("alias", ""), info.get("mod", ""), info.get("porc", 0), info.get("correo", ""), info.get("dui", ""), info.get("cuenta", "")]])
    try:
        worksheet.clear()
        worksheet.update(values=filas, range_name="A1")
        return True
    except Exception:
        return False


def cargar_proveedores():
    worksheet = conectar_gsheets("Proveedores")
    if worksheet:
        try:
            records = worksheet.get_all_records()
            if records:
                return records
        except Exception:
            pass
    return [{
        "ID_Proveedor": "1", "Nombre_Proveedor": "JG SUMINISTROS", "Nombre_Contacto": "JULIO CESAR HERNANDEZ POSADA",
        "Telefono_1": "7398 4751", "Telefono_2": "73984751", "Correo": "jgsuministrossv@gmail.com",
        "Banco": "Banco Cuscatlan", "Cuenta": "325-301-000002077", "Direccion_1": "Plaza comercial San Antonio, P°. El Carmen",
        "Direccion_2": "San Salvador", "Pais": "El Salvador", "Patrocinador": "JULIO CESAR HERNANDEZ POSADA",
        "Valoracion": "50%", "Fecha_Ultima_Rev": "", "Fecha_Prox_Rev": "", "Fecha_Contrato": "", "Fecha_Vencimiento": "",
        "Fecha_Calif_Riesgo": "", "Fecha_Diligencia": "", "Fecha_Rev_Contrato": "", "Fecha_Aprobacion": "",
        "Descripcion": "suministros medicos", "Notas": ""
    }]


def guardar_proveedores(datos_list):
    if not datos_list:
        return False
    return _escribir_hoja("Proveedores", datos_list)


# =====================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# =====================================================================
logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
try:
    if os.path.exists(logo_path):
        icono = Image.open(logo_path)
        st.set_page_config(page_title="Gio Group Admin", page_icon=icono, layout="wide", initial_sidebar_state="expanded")
    else:
        st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")
except Exception:
    st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide")


# =====================================================================
# 2. ESTADO DE MEMORIA (inicialización centralizada; nunca se sobrescribe al navegar)
# =====================================================================
DEFAULTS_GLOBALES = {
    "salario_operativo_neto": 183.96,
    "salario_directivo_neto": 300.00,
    "quincenas_multiplicador": 1.0,
    "periodo_texto": "1 Quincena (Por defecto)",
    "detalle_extras": [],
    "historial_auditoria": [],
    "total_ingresos_pdf": 0.0,
    "ingresos_por_marca": {},
    "extras_por_marca": {},
    # Control del PDF: se procesa una sola vez por archivo (hash) y el uploader se puede reiniciar.
    "pdf_hash": None,
    "pdf_nombre": "",
    "uploader_nonce": 0,
    "_toasts": [],
}
for _k, _v in DEFAULTS_GLOBALES.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v.copy() if isinstance(_v, (list, dict)) else _v

if "empleados" not in st.session_state: st.session_state["empleados"] = cargar_empleados()
if "proveedores" not in st.session_state: st.session_state["proveedores"] = cargar_proveedores()


def calcular_bruto_acumulado(rol, quincenas=None):
    neto_quincenal = st.session_state["salario_operativo_neto"] if rol == "Operativo" else st.session_state["salario_directivo_neto"]
    mult = quincenas if quincenas is not None else st.session_state["quincenas_multiplicador"]
    return round((neto_quincenal * mult) / 0.90, 2)


for emp, info in st.session_state["empleados"].items():
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"extra_bruto_{emp}" not in st.session_state: st.session_state[f"extra_bruto_{emp}"] = 0.0
    if f"ret_pub_{emp}" not in st.session_state: st.session_state[f"ret_pub_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = info.get("correo", "")
    if f"notas_{emp}" not in st.session_state: st.session_state[f"notas_{emp}"] = "Ninguno"

    mod_init = info.get("mod", "Fijo")
    if "Porcentaje" in mod_init:
        if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = 0.0
    else:
        if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", "Operativo"))


# --- Notificaciones flotantes (sobreviven a st.rerun) ---
def notificar(msg, icon="✅"):
    st.session_state["_toasts"].append((msg, icon))


def mostrar_notificaciones():
    pendientes = st.session_state.get("_toasts", [])
    st.session_state["_toasts"] = []
    for msg, icon in pendientes:
        st.toast(msg, icon=icon)


# --- Widgets persistentes: el valor canónico vive en session_state y el widget se re-siembra al volver a la pestaña ---
def campo_persistente(widget_fn, label, state_key, ui_key, conv=None, **kwargs):
    if ui_key not in st.session_state:
        valor_inicial = st.session_state[state_key]
        st.session_state[ui_key] = conv(valor_inicial) if conv else valor_inicial
    valor = widget_fn(label, key=ui_key, **kwargs)
    st.session_state[state_key] = valor
    return valor


def reiniciar_widgets_planilla(prefijos=("ui_b_", "ui_c_")):
    """Fuerza a los inputs de Planillas a tomar los valores recién calculados."""
    for emp in st.session_state["empleados"].keys():
        for p in prefijos:
            st.session_state.pop(f"{p}{emp}", None)


# =====================================================================
# 3. CSS PREMIUM
# =====================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --gg-bg: #F8FAFC;
    --gg-card: #FFFFFF;
    --gg-ink: #0F172A;
    --gg-ink-2: #334155;
    --gg-muted: #64748B;
    --gg-border: #E2E8F0;
    --gg-navy: #0A192F;
    --gg-accent: #2563EB;
    --gg-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 16px rgba(15, 23, 42, 0.05);
    --gg-shadow-hover: 0 4px 10px rgba(15, 23, 42, 0.06), 0 16px 36px rgba(15, 23, 42, 0.10);
}

/* Tipografía global (sin tocar los íconos Material de Streamlit) */
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea,
.stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stMarkdown, [data-testid="stMetric"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* Chrome de Streamlit */
#MainMenu, footer, [data-testid="stDecoration"], .stAppDeployButton { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }
.stApp { background-color: var(--gg-bg) !important; }
.block-container { padding-top: 2rem !important; padding-bottom: 3rem !important; max-width: 1400px; }

h1, h2, h3 { color: var(--gg-ink) !important; font-weight: 800 !important; letter-spacing: -0.02em; }
h4 { color: var(--gg-ink) !important; font-weight: 700 !important; letter-spacing: -0.01em; }

/* Tarjetas con elevación dinámica */
[data-testid="stMetric"], [data-testid="stExpander"], [class*="st-key-card_"] {
    background-color: var(--gg-card) !important;
    border-radius: 12px !important;
    border: 1px solid var(--gg-border) !important;
    box-shadow: var(--gg-shadow) !important;
    transition: transform .22s cubic-bezier(.2,.8,.2,1), box-shadow .22s cubic-bezier(.2,.8,.2,1), border-color .22s ease;
}
[data-testid="stMetric"] { padding: 18px 20px !important; }
[class*="st-key-card_"] { padding: 18px 20px !important; }
/* Elevación al pasar el ratón (sin transform en expanders: rompería overlays de las tablas editables) */
[data-testid="stMetric"]:hover, [class*="st-key-card_"]:hover {
    transform: translateY(-2px);
    box-shadow: var(--gg-shadow-hover) !important;
    border-color: #CBD5E1 !important;
}
[data-testid="stExpander"]:hover { box-shadow: var(--gg-shadow-hover) !important; border-color: #CBD5E1 !important; }
[data-testid="stMetricLabel"] p { color: var(--gg-muted) !important; font-weight: 600 !important; font-size: 0.82rem !important; text-transform: uppercase; letter-spacing: .04em; }
[data-testid="stMetricValue"] { color: var(--gg-ink) !important; font-weight: 800 !important; letter-spacing: -0.02em; }
[data-testid="stExpander"] details { border: none !important; }
[data-testid="stExpander"] summary p { font-weight: 600 !important; color: var(--gg-ink) !important; }

/* Botones con gradiente y pulsación */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, #0A192F 0%, #1E3A8A 55%, #2563EB 100%) !important;
    background-size: 160% 160% !important;
    background-position: 0% 50% !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.15rem !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.18), inset 0 1px 0 rgba(255,255,255,0.10) !important;
    transition: transform .15s ease, box-shadow .2s ease, background-position .45s ease, filter .2s ease !important;
}
.stButton > button p, .stDownloadButton > button p { color: #FFFFFF !important; font-weight: 600 !important; }
.stButton > button:hover, .stDownloadButton > button:hover {
    background-position: 100% 50% !important;
    transform: translateY(-1px);
    box-shadow: 0 8px 22px rgba(37, 99, 235, 0.30) !important;
    color: #FFFFFF !important;
}
.stButton > button:active, .stDownloadButton > button:active { transform: scale(0.97); box-shadow: 0 1px 3px rgba(37, 99, 235, 0.25) !important; }
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible { outline: 3px solid rgba(37, 99, 235, 0.35) !important; outline-offset: 2px; }
.stButton > button:disabled { filter: grayscale(0.7); opacity: 0.45; transform: none; box-shadow: none !important; }

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
    border-radius: 10px !important;
    border-color: var(--gg-border) !important;
    transition: border-color .15s ease, box-shadow .15s ease;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {
    border-color: var(--gg-accent) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}
.stApp label p { color: var(--gg-ink-2) !important; font-weight: 500 !important; }

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    background: var(--gg-card) !important;
    border: 1.5px dashed #CBD5E1 !important;
    border-radius: 12px !important;
    transition: border-color .2s ease, background .2s ease;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--gg-accent) !important; background: #F5F8FF !important; }

/* Tabs */
[data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--gg-border); }
[data-baseweb="tab"] { border-radius: 8px 8px 0 0 !important; padding: 8px 14px !important; font-weight: 600 !important; }
[data-baseweb="tab"][aria-selected="true"] p { color: var(--gg-accent) !important; }
[data-baseweb="tab-highlight"] { background-color: var(--gg-accent) !important; height: 3px !important; border-radius: 3px; }

/* Toasts */
[data-testid="stToast"] {
    border-radius: 12px !important;
    border: 1px solid var(--gg-border) !important;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.14) !important;
    background: #FFFFFF !important;
}

/* Sidebar */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0A192F 0%, #0B1F3A 100%) !important; border-right: 1px solid rgba(148, 163, 184, 0.12); }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: #94A3B8 !important; }

/* Componentes propios */
.gg-hero { margin: 0 0 1.25rem 0; animation: ggFade .45s ease both; }
.gg-hero .gg-eyebrow { font-size: .75rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--gg-accent); margin-bottom: .35rem; }
.gg-hero h2 { margin: 0 !important; padding: 0 !important; font-size: 1.85rem !important; }
.gg-hero .gg-sub { color: var(--gg-muted); font-size: .95rem; margin-top: .35rem; }
.gg-pill {
    display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 999px;
    background: #EEF4FF; color: #1E3A8A; font-weight: 600; font-size: .85rem; border: 1px solid #DBE7FE;
}
.gg-pill.ok { background: #ECFDF5; color: #065F46; border-color: #A7F3D0; }
.gg-row { display: flex; flex-wrap: wrap; gap: 8px; margin: .25rem 0 1rem 0; }
.gg-card-title { font-weight: 700; color: var(--gg-ink); font-size: 1rem; margin: 2px 0 2px 0; }
.gg-card-sub { color: var(--gg-muted); font-size: .82rem; margin-bottom: 6px; }
.gg-empty {
    text-align: center; padding: 56px 24px; background: var(--gg-card); border: 1px dashed #CBD5E1; border-radius: 12px;
    color: var(--gg-muted); animation: ggFade .45s ease both;
}
.gg-empty .gg-empty-icon { font-size: 2.2rem; margin-bottom: 8px; }
.gg-empty b { color: var(--gg-ink); font-size: 1.05rem; }
.gg-status { margin: 10px 8px 0 8px; padding: 10px 12px; border-radius: 10px; font-size: .78rem; font-weight: 600; text-align: center; }
.gg-status.on { background: rgba(16, 185, 129, .12); color: #6EE7B7; border: 1px solid rgba(16, 185, 129, .25); }
.gg-status.off { background: rgba(245, 158, 11, .12); color: #FCD34D; border: 1px solid rgba(245, 158, 11, .25); }
@keyframes ggFade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* Perfil de proveedor estilo CRM (HubSpot / Salesforce) */
.st-key-card_prov_header { background: linear-gradient(180deg, #FFFFFF 0%, #FBFCFE 100%) !important; }
.crm-head { display: flex; gap: 18px; align-items: center; animation: ggFade .4s ease both; }
.crm-avatar {
    width: 68px; height: 68px; border-radius: 18px; flex-shrink: 0;
    background: linear-gradient(135deg, #2563EB 0%, #4F46E5 60%, #7C3AED 100%);
    color: #FFFFFF; font-weight: 800; font-size: 1.45rem; letter-spacing: .02em;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 8px 20px rgba(79, 70, 229, 0.28);
}
.crm-kicker { font-size: .7rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #94A3B8; }
.crm-name { font-size: 1.5rem; font-weight: 800; color: #0F172A; letter-spacing: -0.02em; line-height: 1.2; margin-top: 2px; }
.crm-desc { color: #64748B; font-size: .92rem; margin-top: 4px; }
.crm-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.crm-chip { font-size: .74rem; font-weight: 600; padding: 4px 10px; border-radius: 999px; background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0; white-space: nowrap; }
.crm-chip.green { background: #ECFDF5; color: #047857; border-color: #A7F3D0; }
.crm-chip.amber { background: #FFFBEB; color: #B45309; border-color: #FDE68A; }
.crm-chip.red { background: #FEF2F2; color: #B91C1C; border-color: #FECACA; }
.crm-chip.blue { background: #EFF6FF; color: #1D4ED8; border-color: #BFDBFE; }
.crm-section-title {
    display: flex; align-items: center; gap: 8px; font-size: .74rem; font-weight: 700; letter-spacing: .09em;
    text-transform: uppercase; color: #475569; margin-bottom: 6px; padding-bottom: 10px; border-bottom: 1px solid #F1F5F9;
}
.crm-section-title .dot { width: 8px; height: 8px; border-radius: 50%; background: #2563EB; box-shadow: 0 0 0 3px rgba(37, 99, 235, .15); }
.crm-field { display: flex; gap: 12px; align-items: flex-start; padding: 9px 0; }
.crm-ico { width: 36px; height: 36px; border-radius: 10px; background: #F1F5F9; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0; transition: background .2s ease, transform .2s ease; }
.crm-field:hover .crm-ico { background: #E0E7FF; transform: scale(1.06); }
.crm-label { font-size: .68rem; color: #94A3B8; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
.crm-value { font-size: .92rem; color: #0F172A; font-weight: 600; word-break: break-word; margin-top: 1px; }
.crm-value.mono { font-variant-numeric: tabular-nums; letter-spacing: .02em; }
.crm-value.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-value a { color: #2563EB; text-decoration: none; }
.crm-value a:hover { text-decoration: underline; }
.crm-date { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px dashed #EEF2F7; }
.crm-date:last-child { border-bottom: none; }
.crm-date .l { display: flex; align-items: center; gap: 10px; font-size: .86rem; color: #334155; font-weight: 500; }
.crm-date .r { display: flex; align-items: center; gap: 8px; font-size: .86rem; color: #0F172A; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.crm-date .r.empty { color: #CBD5E1; font-weight: 500; font-style: italic; }
.crm-text { color: #334155; font-size: .92rem; line-height: 1.6; white-space: pre-wrap; }
.crm-text.empty { color: #CBD5E1; font-style: italic; }
</style>
""", unsafe_allow_html=True)

mostrar_notificaciones()


def encabezado(titulo, subtitulo="", eyebrow="Gio Group · Admin"):
    sub_html = f"<div class='gg-sub'>{subtitulo}</div>" if subtitulo else ""
    st.markdown(f"<div class='gg-hero'><div class='gg-eyebrow'>{eyebrow}</div><h2>{titulo}</h2>{sub_html}</div>", unsafe_allow_html=True)


def estado_vacio(icono, titulo, texto):
    st.markdown(f"<div class='gg-empty'><div class='gg-empty-icon'>{icono}</div><b>{titulo}</b><div style='margin-top:6px'>{texto}</div></div>", unsafe_allow_html=True)


# =====================================================================
# 4. MENÚ LATERAL
# =====================================================================
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path): st.image(logo_path, use_container_width=True)
    else: st.markdown("<h2 style='text-align:center; color:white !important; letter-spacing:.08em;'>GIO GROUP</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Directorio de Proveedores", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "journal-bookmark-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        menu_icon="cast", default_index=1, key="menu_principal",
        styles={
            "container": {"background-color": "transparent", "padding": "4px"},
            "menu-title": {"color": "#E2E8F0", "font-size": "12px", "font-weight": "700", "letter-spacing": "1.5px"},
            "icon": {"color": "#94A3B8", "font-size": "16px"},
            "nav-link": {"font-size": "14px", "color": "#94A3B8", "border-radius": "10px", "margin": "3px 0", "--hover-color": "#112240"},
            "nav-link-selected": {"background-color": "#112240", "color": "#60A5FA", "font-weight": "700", "border-left": "4px solid #3B82F6"}
        }
    )

    if conectar_gsheets("Personal") is not None:
        st.markdown("<div class='gg-status on'>● Google Sheets conectado</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='gg-status off'>● Modo local (sin nube)</div>", unsafe_allow_html=True)


# =====================================================================
# 5. PROCESAMIENTO DEL PDF (cacheado + una sola vez por archivo)
# =====================================================================
@st.cache_data(show_spinner=False, max_entries=16)
def extraer_contenido_pdf(pdf_bytes):
    """Lectura pesada con pdfplumber: se ejecuta una sola vez por archivo (clave = contenido)."""
    texto_completo = ""
    todas_las_filas = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            texto_completo += (page.extract_text() or "") + " "
            tabla = page.extract_table()
            if tabla: todas_las_filas.extend(tabla)
    return texto_completo, todas_las_filas


def procesar_reporte_pdf(pdf_bytes):
    texto_completo, todas_las_filas = extraer_contenido_pdf(pdf_bytes)

    fechas_iso = re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', texto_completo)
    if len(fechas_iso) >= 2:
        min_f = datetime.strptime(fechas_iso[0], '%Y-%m-%d')
        max_f = datetime.strptime(fechas_iso[1], '%Y-%m-%d')
        dias_diff = (max_f - min_f).days + 1
        factor = 1.0 if dias_diff <= 16 else 2.0 if dias_diff <= 31 else float(max(2, round(dias_diff / 30.0)) * 2.0)
        st.session_state["quincenas_multiplicador"] = factor
        st.session_state["periodo_texto"] = f"Del {min_f.strftime('%d/%m/%Y')} al {max_f.strftime('%d/%m/%Y')} ({factor} Quincenas)"

    header_idx = -1
    for i, row in enumerate(todas_las_filas):
        if row and any(isinstance(c, str) and 'PROFESIONAL' in c.upper() for c in row): header_idx = i; break

    if header_idx == -1:
        return False

    df_reporte = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
    df_reporte.columns = df_reporte.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
    c_prof = next((c for c in df_reporte.columns if 'PROFESIONAL' in c), None)
    c_pre = next((c for c in df_reporte.columns if 'PRECIO' in c), None)
    c_cli = next((c for c in df_reporte.columns if 'CLIENTE' in c), None)
    c_ser = next((c for c in df_reporte.columns if 'SERVICIO' in c), None)

    if not (c_prof and c_pre):
        return False

    df_reporte = df_reporte.dropna(subset=[c_prof, c_pre])
    df_reporte = df_reporte[~df_reporte[c_prof].astype(str).str.upper().str.contains('PROFESIONAL', na=False)]
    df_reporte[c_pre] = pd.to_numeric(df_reporte[c_pre].astype(str).str.replace(r'[\$,\n]', '', regex=True), errors='coerce').fillna(0.0)
    st.session_state["total_ingresos_pdf"] = df_reporte[c_pre].sum()

    def asignar_marca(p):
        p = str(p).upper()
        if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
        if "LUIS" in p: return "Relájate Man"
        if "GIO" in p or "MARVIN" in p: return "Dr. Gio Molina"
        return "Relájate Clinic"

    df_reporte['MARCA'] = df_reporte[c_prof].apply(asignar_marca)
    st.session_state["ingresos_por_marca"] = df_reporte.groupby('MARCA')[c_pre].sum().to_dict()
    df_reporte['EXTRA'] = df_reporte.apply(lambda r: 0.0 if r['MARCA'] == "Dr. Gio Molina" else max(0.0, float(r[c_pre]) - 60.0), axis=1)
    st.session_state["extras_por_marca"] = df_reporte.groupby('MARCA')['EXTRA'].sum().to_dict()

    lista_ex = []
    for emp, info in st.session_state["empleados"].items():
        mod = st.session_state.get(f"mod_{emp}", info.get("mod", "Fijo"))
        st.session_state[f"base_{emp}"] = 0.0 if "Porcentaje" in mod else calcular_bruto_acumulado(info.get("rol", ""), st.session_state["quincenas_multiplicador"])
        df_p = df_reporte[df_reporte[c_prof].astype(str).str.contains(info.get("alias", ""), case=False, na=False, regex=True)]
        tot_s = df_p[c_pre].sum()
        st.session_state[f"serv_tot_{emp}"] = tot_s

        if info.get("rol", "") == "Operativo":
            if "Estándar" in mod:
                df_ex = df_p[df_p[c_pre] > 60.0]
                ex_tot = 0.0; ret_tot = 0.0
                for _, rx in df_ex.iterrows():
                    pr = float(rx[c_pre]); ex = pr - 60.0; ret = ex * 0.25; com = ex - ret
                    ex_tot += ex; ret_tot += ret
                    lista_ex.append({"Colaborador": emp, "Cliente": str(rx[c_cli]) if c_cli else "N/A", "Servicio": str(rx[c_ser]) if c_ser else "N/A", "Precio Final": pr, "Extra Generado": ex, "Retención (25%)": ret, "Comisión Neta": com})
                st.session_state[f"extra_bruto_{emp}"] = ex_tot
                st.session_state[f"ret_pub_{emp}"] = ret_tot
                st.session_state[f"com_{emp}"] = max(0.0, ex_tot - ret_tot)
            else:
                st.session_state[f"com_{emp}"] = tot_s * (info.get("porc", 20) / 100.0)

    st.session_state["detalle_extras"] = lista_ex
    reiniciar_widgets_planilla()
    return True


def limpiar_reporte_pdf():
    st.session_state["total_ingresos_pdf"] = 0.0
    st.session_state["periodo_texto"] = "1 Quincena (Por defecto)"
    st.session_state["detalle_extras"] = []
    st.session_state["ingresos_por_marca"] = {}
    st.session_state["extras_por_marca"] = {}
    for emp in st.session_state["empleados"].keys():
        st.session_state[f"com_{emp}"] = 0.0
        st.session_state[f"extra_bruto_{emp}"] = 0.0
        st.session_state[f"ret_pub_{emp}"] = 0.0
        st.session_state[f"serv_tot_{emp}"] = 0.0
    st.session_state["pdf_hash"] = None
    st.session_state["pdf_nombre"] = ""
    st.session_state["uploader_nonce"] += 1  # vacía el file_uploader
    reiniciar_widgets_planilla()
    notificar("Reporte PDF limpiado.", "🧹")


# =====================================================================
# 6. PANEL SUPERIOR (Solo en Dashboard y Planillas)
# =====================================================================
if menu_seleccionado in ["Dashboard", "Planillas"]:
    encabezado("Bienvenido, Administración 👋", "Sincroniza el reporte de ventas y toda la planilla se calcula al instante.")
    col_up1, col_up2 = st.columns([3, 1])
    with col_up1:
        archivo_subido = st.file_uploader("📥 Sincronizar reporte de ventas (PDF)", type=["pdf"], key=f"pdf_uploader_{st.session_state['uploader_nonce']}")
    with col_up2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        st.button("🧹 Limpiar Reporte PDF", on_click=limpiar_reporte_pdf, use_container_width=True)

    if archivo_subido is not None:
        pdf_bytes = archivo_subido.getvalue()
        pdf_hash = hashlib.md5(pdf_bytes).hexdigest()
        # Solo se procesa si es un archivo NUEVO: los reruns y cambios de pestaña no pisan las ediciones manuales.
        if pdf_hash != st.session_state["pdf_hash"]:
            with st.spinner('Analizando datos corporativos con IA...'):
                try:
                    if procesar_reporte_pdf(pdf_bytes):
                        st.toast("¡PDF analizado con éxito!", icon="✅")
                    else:
                        st.toast("No se encontró la tabla de PROFESIONAL / PRECIO en el PDF.", icon="⚠️")
                except Exception as e:
                    st.toast(f"Error procesando PDF: {e}", icon="🚨")
            st.session_state["pdf_hash"] = pdf_hash
            st.session_state["pdf_nombre"] = archivo_subido.name

    chips = f"<span class='gg-pill'>📅 Período en análisis: <b>{html.escape(st.session_state['periodo_texto'])}</b></span>"
    if st.session_state["pdf_nombre"]:
        chips += f"<span class='gg-pill ok'>📄 {html.escape(st.session_state['pdf_nombre'])} sincronizado</span>"
    st.markdown(f"<div class='gg-row'>{chips}</div>", unsafe_allow_html=True)


# =====================================================================
# 7. GRÁFICOS (Plotly)
# =====================================================================
ORDEN_MARCAS = ["Papi Spa", "Relájate Man", "Dr. Gio Molina", "Relájate Clinic"]
COLORES_MARCA = {"Papi Spa": "#2a78d6", "Relájate Man": "#eb6834", "Dr. Gio Molina": "#1baf7a", "Relájate Clinic": "#eda100"}
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


def estilo_plotly(fig, height=360):
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color="#334155", size=13),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E2E8F0", font=dict(family="Inter, sans-serif", color="#0F172A", size=13)),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5, title=None, font=dict(color="#334155")),
    )
    return fig


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
    fig.add_annotation(text=f"<span style='font-size:12px;color:#64748B'>TOTAL</span><br><b style='font-size:22px;color:#0F172A'>${sum(valores):,.0f}</b>", showarrow=False, x=0.5, y=0.5)
    return estilo_plotly(fig, 380)


def grafico_barras_marcas(ingresos_marca, extras_marca):
    marcas = marcas_ordenadas(ingresos_marca)
    filas = []
    for m in marcas:
        filas.append({"Marca": m, "Concepto": "Ingresos", "Monto": float(ingresos_marca.get(m, 0.0))})
        filas.append({"Marca": m, "Concepto": "Extras (> $60)", "Monto": float(extras_marca.get(m, 0.0))})
    df = pd.DataFrame(filas)
    fig = px.bar(df, y="Marca", x="Monto", color="Concepto", barmode="group", orientation="h",
                 color_discrete_map={"Ingresos": "#2a78d6", "Extras (> $60)": "#eb6834"},
                 category_orders={"Marca": marcas, "Concepto": ["Ingresos", "Extras (> $60)"]})
    fig.update_traces(hovertemplate="<b>%{y}</b><br>%{fullData.name}: $%{x:,.2f}<extra></extra>", marker_line_width=0,
                      texttemplate="$%{x:,.0f}", textposition="outside", textfont=dict(color="#334155", size=11), cliponaxis=False)
    fig.update_layout(bargap=0.28, bargroupgap=0.08, barcornerradius=4)
    fig.update_yaxes(title=None, showgrid=False, autorange="reversed", tickfont=dict(color="#0F172A"))
    fig.update_xaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    return estilo_plotly(fig, max(300, 92 * len(marcas) + 80))


def grafico_colaboradores(ventas):
    df = pd.DataFrame([{"Colaborador": k, "Ventas": float(v)} for k, v in ventas.items() if v > 0]).sort_values("Ventas")
    fig = px.bar(df, x="Ventas", y="Colaborador", orientation="h", text="Ventas")
    fig.update_traces(marker_color="#2a78d6", marker_line_width=0, texttemplate="$%{x:,.0f}", textposition="outside",
                      textfont=dict(color="#334155"), cliponaxis=False,
                      hovertemplate="<b>%{y}</b><br>Servicios: $%{x:,.2f}<extra></extra>")
    fig.update_layout(bargap=0.38, barcornerradius=4, showlegend=False)
    fig.update_xaxes(title=None, gridcolor="#EEF2F7", zeroline=False, tickprefix="$", tickformat=",.0f", tickfont=dict(color="#64748B"))
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(color="#0F172A"))
    return estilo_plotly(fig, max(260, 52 * len(df) + 60))


# =====================================================================
# 8. PDF DEL RECIBO
# =====================================================================
def generar_recibo_pdf(e_dat, periodo_texto):
    class PDF(FPDF):
        def header(self):
            if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
            self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
            if os.path.exists(logo_path): self.set_x(40)
            self.set_font('helvetica', '', 10); self.set_text_color(100, 100, 100); self.cell(0, 5, 'Comprobante Oficial de Pago', 0, 1, 'L')
            if os.path.exists(logo_path): self.set_x(40)
            self.cell(0, 5, limpiar_texto_pdf(f"Periodo Liquidado: {periodo_texto}"), 0, 1, 'L')
            self.ln(5)

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
            pdf.cell(130, 8, limpiar_texto_pdf(f"  {d}"), 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')

    pdf.set_text_color(201, 42, 42)
    if e_dat['Desc'] > 0:
        pdf.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Desc']:.2f}", 1, 1, 'R')

    if e_dat['Ret Pub'] > 0:
        pdf.cell(130, 8, "  (Informativo) Retención 25% Publicidad", 1, 0, 'L'); pdf.cell(60, 8, f"${e_dat['Ret Pub']:.2f}", 1, 1, 'R')

    if e_dat['Renta'] > 0:
        pdf.cell(130, 8, "  (-) 10% Retención de Renta", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Renta']:.2f}", 1, 1, 'R')

    pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
    pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total']:.2f}", 1, 1, 'R', fill=True)

    notas_val = str(e_dat.get('Notas', 'Ninguno')).strip()
    if not notas_val or notas_val.lower() == 'ninguno': notas_val = "Sin notas adicionales"
    pdf.ln(6)
    pdf.set_font('helvetica', 'B', 10); pdf.set_text_color(10, 25, 47); pdf.set_fill_color(243, 244, 246)
    pdf.cell(0, 7, "  Notas del Registro:", 0, 1, 'L', fill=True)
    pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(0, 6, limpiar_texto_pdf(f"  {notas_val}"), 0, 'L')
    return generar_pdf_bytes(pdf)


# =====================================================================
# 9. PERFIL DE PROVEEDOR (CRM con componentes nativos)
# =====================================================================
def _texto(v):
    """Valor como texto limpio ('' si viene vacío o NaN)."""
    try:
        if v is None or pd.isna(v): return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def _esc(v):
    return html.escape(_texto(v))


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
    m = re.search(r"\d+(?:[.,]\d+)?", _texto(v))
    if not m:
        return None
    return max(0.0, min(100.0, float(m.group().replace(",", "."))))


def estado_contrato(p):
    """(texto, clase de color) según la fecha de vencimiento del contrato."""
    venc = _parse_fecha(p.get("Fecha_Vencimiento"))
    if venc is None:
        return ("Sin fecha de vencimiento", "")
    dias = (venc.normalize() - pd.Timestamp.today().normalize()).days
    if dias < 0:
        return (f"Vencido hace {abs(dias)} días", "red")
    if dias <= 30:
        return (f"Vence en {dias} días", "amber")
    return ("Contrato vigente", "green")


def crm_seccion(titulo, color="#2563EB"):
    return f"<div class='crm-section-title'><span class='dot' style='background:{color};box-shadow:0 0 0 3px {color}26'></span>{titulo}</div>"


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


def crm_fecha(icono, etiqueta, valor, chip=""):
    f = _parse_fecha(valor)
    mostrar = f.strftime("%d/%m/%Y") if f is not None else _texto(valor)
    if mostrar:
        derecha = f"<div class='r'>{chip}{html.escape(mostrar)}</div>"
    else:
        derecha = "<div class='r empty'>Pendiente</div>"
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


def render_perfil_proveedor(p):
    nombre = _texto(p.get("Nombre_Proveedor")) or "Proveedor sin nombre"
    estado_txt, estado_cls = estado_contrato(p)

    # --- Encabezado del perfil ---
    with st.container(border=True, key="card_prov_header"):
        chips = f"<span class='crm-chip {estado_cls}'>● {estado_txt}</span>"
        if _texto(p.get("Pais")):
            chips += f"<span class='crm-chip'>🌎 {_esc(p.get('Pais'))}</span>"
        if _texto(p.get("ID_Proveedor")):
            chips += f"<span class='crm-chip blue'># ID {_esc(p.get('ID_Proveedor'))}</span>"
        desc = _esc(p.get("Descripcion")) or "Sin descripción registrada"
        st.markdown(
            f"<div class='crm-head'><div class='crm-avatar'>{html.escape(_iniciales(nombre))}</div>"
            f"<div><div class='crm-kicker'>Proveedor</div><div class='crm-name'>{html.escape(nombre)}</div>"
            f"<div class='crm-desc'>{desc}</div><div class='crm-chips'>{chips}</div></div></div>",
            unsafe_allow_html=True,
        )

    # --- KPIs ---
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("⭐ Valoración general", _texto(p.get("Valoracion")) or "—")
        pct = _valoracion_pct(p.get("Valoracion"))
        if pct is not None:
            st.progress(pct / 100.0)
    venc = _parse_fecha(p.get("Fecha_Vencimiento"))
    prox = _parse_fecha(p.get("Fecha_Prox_Rev"))
    k2.metric("⏳ Vencimiento de contrato", venc.strftime("%d/%m/%Y") if venc is not None else "—")
    k3.metric("📆 Próxima revisión", prox.strftime("%d/%m/%Y") if prox is not None else "—")

    # --- Secciones ---
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True, key="card_prov_contacto"):
            st.markdown(
                crm_seccion("Información de contacto", "#2563EB")
                + crm_campo("👤", "Contacto", p.get("Nombre_Contacto"))
                + crm_campo("📞", "Teléfono", p.get("Telefono_1"), "telefono")
                + crm_campo("📧", "Correo electrónico", p.get("Correo"), "correo")
                + crm_campo("📍", "Dirección", p.get("Direccion_1"))
                + crm_campo("🏙️", "Ciudad / Dirección 2", p.get("Direccion_2"))
                + crm_campo("🌎", "País", p.get("Pais")),
                unsafe_allow_html=True,
            )
    with c2:
        with st.container(border=True, key="card_prov_finanzas"):
            st.markdown(
                crm_seccion("Datos financieros", "#059669")
                + crm_campo("🏦", "Banco", p.get("Banco"))
                + crm_campo("💳", "Número de cuenta", p.get("Cuenta"), "mono")
                + crm_campo("🤝", "Patrocinador", p.get("Patrocinador"))
                + crm_campo("☎️", "Teléfono del patrocinador", p.get("Telefono_2"), "telefono"),
                unsafe_allow_html=True,
            )
            if _texto(p.get("Cuenta")):
                st.caption("Copiar número de cuenta")
                st.code(_texto(p.get("Cuenta")), language=None)
    with c3:
        with st.container(border=True, key="card_prov_fechas"):
            hoy = pd.Timestamp.today().normalize()
            filas = ""
            for icono, etiqueta, campo in FECHAS_PROVEEDOR:
                chip = ""
                if campo == "Fecha_Vencimiento" and estado_cls:
                    chip = f"<span class='crm-chip {estado_cls}'>{'Vencido' if estado_cls == 'red' else 'Por vencer' if estado_cls == 'amber' else 'Vigente'}</span>"
                elif campo == "Fecha_Prox_Rev" and prox is not None and prox.normalize() < hoy:
                    chip = "<span class='crm-chip red'>Atrasada</span>"
                filas += crm_fecha(icono, etiqueta, p.get(campo), chip)
            st.markdown(crm_seccion("Contratos y auditoría", "#7C3AED") + filas, unsafe_allow_html=True)

    # --- Notas ---
    with st.container(border=True, key="card_prov_notas"):
        notas = _esc(p.get("Notas"))
        cuerpo = f"<div class='crm-text'>{notas}</div>" if notas else "<div class='crm-text empty'>Sin notas registradas para este proveedor.</div>"
        st.markdown(crm_seccion("Notas internas", "#F59E0B") + cuerpo, unsafe_allow_html=True)


# =====================================================================
# 10. ENRUTAMIENTO DE PÁGINAS
# =====================================================================

if menu_seleccionado == "Dashboard":
    if st.session_state["total_ingresos_pdf"] > 0:
        costo_planilla = sum([round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] - (0.0 if "Porcentaje" in st.session_state.get(f"mod_{emp}", "") else round(st.session_state[f"base_{emp}"] * 0.10, 2)), 2) for emp in st.session_state["empleados"].keys()])
        ingresos = st.session_state['total_ingresos_pdf']
        utilidad = ingresos - costo_planilla
        margen = (utilidad / ingresos * 100.0) if ingresos else 0.0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Ingresos Brutos Totales", f"${ingresos:,.2f}")
        col2.metric("💸 Costo Operativo", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta", f"${utilidad:,.2f}")
        col4.metric("📈 Margen Neto", f"{margen:,.1f}%")

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        if st.session_state["ingresos_por_marca"]:
            g1, g2 = st.columns([1, 1.35])
            with g1:
                with st.container(border=True, key="card_donut"):
                    st.markdown("<div class='gg-card-title'>Ingresos por marca</div><div class='gg-card-sub'>Participación de cada unidad de negocio</div>", unsafe_allow_html=True)
                    st.plotly_chart(grafico_donut_marcas(st.session_state["ingresos_por_marca"]), use_container_width=True, config=PLOTLY_CONFIG)
            with g2:
                with st.container(border=True, key="card_barras"):
                    st.markdown("<div class='gg-card-title'>Ingresos vs. extras por marca</div><div class='gg-card-sub'>Extra = excedente sobre $60 por servicio</div>", unsafe_allow_html=True)
                    st.plotly_chart(grafico_barras_marcas(st.session_state["ingresos_por_marca"], st.session_state["extras_por_marca"]), use_container_width=True, config=PLOTLY_CONFIG)

        ventas_colab = {emp: st.session_state.get(f"serv_tot_{emp}", 0.0) for emp in st.session_state["empleados"].keys()}
        if any(v > 0 for v in ventas_colab.values()):
            with st.container(border=True, key="card_colaboradores"):
                st.markdown("<div class='gg-card-title'>Servicios facturados por colaborador</div><div class='gg-card-sub'>Total del período según el reporte de ventas</div>", unsafe_allow_html=True)
                st.plotly_chart(grafico_colaboradores(ventas_colab), use_container_width=True, config=PLOTLY_CONFIG)
    else:
        estado_vacio("📊", "Aún no hay métricas", "Sube el PDF de ingresos para generar métricas.")

elif menu_seleccionado == "Planillas":
    if st.session_state.get("detalle_extras"):
        with st.expander("🔍 Ver Desglose Informativo: Servicios con Extra Generado", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state["detalle_extras"]).style.format({"Precio Final": "${:.2f}", "Extra Generado": "${:.2f}", "Retención (25%)": "${:.2f}", "Comisión Neta": "${:.2f}"}), use_container_width=True, hide_index=True)

    resumen_planilla = st.container()

    datos_emp = []
    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info.get('rol', '')})"):
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                campo_persistente(st.number_input, "Sueldo Base ($)", f"base_{emp}", f"ui_b_{emp}", conv=float)
                campo_persistente(st.number_input, "Comisiones ($)", f"com_{emp}", f"ui_c_{emp}", conv=float)
            with c2:
                campo_persistente(st.number_input, "Bonos ($)", f"hex_{emp}", f"ui_h_{emp}", conv=float)
                campo_persistente(st.number_input, "Descuentos ($)", f"desc_{emp}", f"ui_d_{emp}", conv=float)
            with c3:
                n_desc = campo_persistente(st.text_input, "Notas", f"notas_{emp}", f"n_{emp}", conv=str)
                campo_persistente(st.text_input, "Correo", f"email_{emp}", f"ui_e_{emp}", conv=str)

            renta_calculada = 0.0 if "Porcentaje" in info.get("mod", "") and info.get("rol", "") == "Operativo" else round(st.session_state[f"base_{emp}"] * 0.10, 2)
            t_net = round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - renta_calculada - st.session_state[f"desc_{emp}"], 2)
            datos_emp.append({"Colaborador": emp, "Base": st.session_state[f"base_{emp}"], "Extra": st.session_state.get(f"extra_bruto_{emp}", 0), "Ret Pub": st.session_state.get(f"ret_pub_{emp}", 0), "Com Neta": st.session_state[f"com_{emp}"], "Bonos": st.session_state[f"hex_{emp}"], "Desc": st.session_state[f"desc_{emp}"], "Renta": renta_calculada, "Total": t_net, "Notas": n_desc, "Email": st.session_state[f"email_{emp}"], "DUI": info.get("dui", ""), "Cuenta": info.get("cuenta", "")})

    if datos_emp:
        with resumen_planilla:
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("🧾 Total Planilla", f"${sum(d['Total'] for d in datos_emp):,.2f}")
            r2.metric("💼 Comisiones Netas", f"${sum(d['Com Neta'] for d in datos_emp):,.2f}")
            r3.metric("🏛️ Retención Renta", f"${sum(d['Renta'] for d in datos_emp):,.2f}")
            r4.metric("👥 Colaboradores", f"{len(datos_emp)}")
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(datos_emp).drop(columns=["Notas", "Email", "DUI", "Cuenta"]).style.format("${:.2f}", subset=["Base", "Extra", "Ret Pub", "Com Neta", "Bonos", "Desc", "Renta", "Total"]), use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True, key="card_recibos"):
            st.markdown("<h3 style='margin-top:0'>Gestión y Envío de Recibos</h3>", unsafe_allow_html=True)
            e_sel = st.selectbox("Seleccionar Colaborador:", list(st.session_state["empleados"].keys()), key="recibo_colaborador")
            e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)

            if st.button("👁️ Visualizar y Generar Recibo (PDF)"):
                with st.spinner("Generando comprobante..."):
                    st.session_state['t_pdf'] = generar_recibo_pdf(e_dat, st.session_state['periodo_texto'])
                    st.session_state['t_path'] = f"Recibo_{e_sel.replace(' ', '_')}.pdf"
                    st.session_state['t_emp'] = e_sel
                st.toast(f"Recibo de {e_sel} generado.", icon="📄")

            # El recibo solo se muestra/envía si corresponde al colaborador seleccionado.
            if 't_pdf' in st.session_state and st.session_state.get('t_emp') == e_sel:
                b1, b2 = st.columns(2)
                with b1:
                    st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf", use_container_width=True)
                correo_ok = bool(e_dat["Email"]) and "@" in e_dat["Email"]
                with b2:
                    enviar = st.button("🚀 Enviar Recibo por Gmail", disabled=not correo_ok, use_container_width=True)
                if not correo_ok: st.warning("⚠️ Este colaborador no tiene un correo válido configurado.")

                if enviar:
                    with st.spinner("Enviando comprobante por Gmail..."):
                        try:
                            remitente = st.secrets["EMAIL_USER"]
                            password = st.secrets["EMAIL_PASS"]
                            destinatario = e_dat["Email"]

                            msg = MIMEMultipart()
                            msg['From'] = remitente; msg['To'] = destinatario
                            msg['Subject'] = f"Comprobante de Pago - Período: {st.session_state['periodo_texto']} | GIO GROUP"

                            cuerpo_correo = f"Estimado/a {e_dat['Colaborador']},\n\nAdjunto a este correo electrónico encontrará su Comprobante Oficial de Pago detallado.\n\nAtentamente,\nAdministración GIO GROUP SAS DE CV"
                            msg.attach(MIMEText(cuerpo_correo, 'plain'))

                            nombre_adjunto = st.session_state['t_path']
                            parte_adjunta = MIMEApplication(st.session_state['t_pdf'], Name=nombre_adjunto)
                            parte_adjunta['Content-Disposition'] = f'attachment; filename="{nombre_adjunto}"'
                            msg.attach(parte_adjunta)

                            servidor_smtp = smtplib.SMTP('smtp.gmail.com', 587)
                            servidor_smtp.starttls()
                            servidor_smtp.login(remitente, password)
                            servidor_smtp.sendmail(remitente, destinatario, msg.as_string())
                            servidor_smtp.quit()

                            st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": "Recibo de Pago", "Destinatario": e_sel})
                            st.toast(f"¡Comprobante enviado exitosamente por Gmail a {destinatario}!", icon="📨")
                            st.balloons()
                        except Exception as ex:
                            # Acción crítica: el error queda fijo en pantalla.
                            st.error(f"Error al enviar correo. Verifique secretos EMAIL_USER y EMAIL_PASS: {ex}")

# --- MÓDULO: DIRECTORIO DE PROVEEDORES ---
elif menu_seleccionado == "Directorio de Proveedores":
    encabezado("📇 Directorio de Proveedores", "Perfil 360° de cada proveedor: contacto, datos financieros y control de contratos.")
    proveedores = st.session_state["proveedores"]
    nombres_provs = [p.get("Nombre_Proveedor", f"Prov {p.get('ID_Proveedor', '')}") for p in proveedores]

    col_sel, col_info = st.columns([2.2, 1])
    with col_sel:
        prov_seleccionado = st.selectbox("🔎 Buscar proveedor", nombres_provs, key="prov_seleccionado", placeholder="Escribe para buscar...")
    with col_info:
        alertas = sum(1 for p in proveedores if estado_contrato(p)[1] in ("red", "amber"))
        pills = f"<span class='gg-pill'>📇 {len(proveedores)} proveedores</span>"
        if alertas:
            pills += f"<span class='crm-chip amber' style='padding:7px 12px;font-size:.82rem'>⚠️ {alertas} contrato(s) por atender</span>"
        st.markdown(f"<div style='height:28px'></div><div class='gg-row'>{pills}</div>", unsafe_allow_html=True)

    if prov_seleccionado:
        p_data = next((p for p in proveedores if p.get("Nombre_Proveedor") == prov_seleccionado), {})
        render_perfil_proveedor(p_data)
    else:
        estado_vacio("📇", "No hay proveedores registrados", "Agrega el primero desde el editor de abajo.")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    with st.expander("✏️ Agregar / Editar Proveedores (Base de Datos)"):
        df_prov = pd.DataFrame(proveedores)
        df_prov_edited = st.data_editor(df_prov, use_container_width=True, num_rows="dynamic", key="editor_proveedores")
        if st.button("💾 Guardar Cambios de Proveedores"):
            registros = _registros_validos(df_prov_edited.to_dict("records"))
            if not registros:
                st.toast("La lista de proveedores está vacía; no se guardó nada.", icon="⚠️")
            else:
                st.session_state["proveedores"] = registros
                if guardar_proveedores(st.session_state["proveedores"]):
                    notificar("Base de proveedores actualizada.", "✅")
                    st.rerun()
                else:
                    # Acción crítica: el aviso queda fijo en pantalla.
                    st.error("No se pudo sincronizar con Google Sheets. Los cambios quedaron solo en esta sesión.")


elif menu_seleccionado == "Memorándums":
    encabezado("📝 Emisión de Memorándums Internos", "Genera comunicaciones oficiales en PDF con la identidad corporativa.")
    with st.container(border=True, key="card_memo"):
        emp_memo = st.selectbox("Destinatario del Memorándum:", list(st.session_state["empleados"].keys()), key="memo_emp")
        asunto_memo = st.text_input("Asunto a tratar:", value="Aviso Administrativo Oficial", key="memo_asunto")
        texto_memo = st.text_area("Cuerpo o notas del Memorándum:", key="memo_texto", height=180)

        if st.button("👁️ Generar PDF Oficial"):
            if texto_memo:
                class PDFMemo(FPDF):
                    def header(self):
                        if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                        self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
                pdf_m = PDFMemo(); pdf_m.add_page(); pdf_m.set_font('helvetica', 'B', 11)
                pdf_m.cell(0, 10, limpiar_texto_pdf(f" Entregado a: {emp_memo}"), 0, 1, 'L'); pdf_m.cell(0, 10, limpiar_texto_pdf(f" Asunto Central: {asunto_memo}"), 0, 1, 'L')
                pdf_m.set_font('helvetica', '', 11); pdf_m.multi_cell(0, 7, limpiar_texto_pdf(texto_memo), 0, 'L')

                st.session_state['temp_memo_pdf'] = generar_pdf_bytes(pdf_m)
                st.session_state['temp_memo_path'] = f"Memorandum_{emp_memo.replace(' ', '_')}.pdf"
                st.toast("Memorándum generado.", icon="📝")
            else:
                st.toast("Indica el contenido del memorándum.", icon="ℹ️")

        if 'temp_memo_pdf' in st.session_state:
            st.download_button("📄 Descargar Archivo PDF", data=st.session_state['temp_memo_pdf'], file_name=st.session_state['temp_memo_path'])

elif menu_seleccionado == "Amonestaciones":
    encabezado("⚠️ Registro de Faltas y Amonestaciones", "Documenta incidentes y genera actas formales en PDF.")
    with st.container(border=True, key="card_amon"):
        emp_amon = st.selectbox("Colaborador involucrado:", list(st.session_state["empleados"].keys()), key="amon_emp")
        tipo_falta = st.selectbox("Gravedad de la Falta:", ["Llamada de Atención Verbal", "Amonestación Escrita Leve", "Amonestación Escrita Grave"], key="amon_tipo")
        motivo_amon = st.text_area("Detalles completos del incidente:", key="amon_motivo", height=180)

        if st.button("👁️ Redactar Acta PDF"):
            if motivo_amon:
                class PDFAmon(FPDF):
                    def header(self):
                        if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                        self.set_font('helvetica', 'B', 16); self.set_text_color(201, 42, 42); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
                pdf_a = PDFAmon(); pdf_a.add_page(); pdf_a.set_font('helvetica', 'B', 11)
                pdf_a.cell(0, 10, limpiar_texto_pdf(f" Dirigido a: {emp_amon}"), 0, 1, 'L'); pdf_a.cell(0, 10, limpiar_texto_pdf(f" Tipo de Falta: {tipo_falta}"), 0, 1, 'L')
                pdf_a.set_font('helvetica', '', 11); pdf_a.multi_cell(0, 7, limpiar_texto_pdf(motivo_amon), 1, 'L')

                st.session_state['temp_amon_pdf'] = generar_pdf_bytes(pdf_a)
                st.session_state['temp_amon_path'] = f"Acta_Amonestacion_{emp_amon.replace(' ', '_')}.pdf"
                st.toast("Acta redactada.", icon="⚖️")
            else:
                st.toast("Describe el incidente para poder redactar el acta formal.", icon="ℹ️")

        if 'temp_amon_pdf' in st.session_state:
            st.download_button("📄 Descargar Acta Formal", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])

elif menu_seleccionado == "Auditoría":
    encabezado("🖨️ Registro y Control de Auditoría", "Trazabilidad de todos los documentos enviados en esta sesión.")
    if st.session_state["historial_auditoria"]:
        st.dataframe(pd.DataFrame(st.session_state["historial_auditoria"]), use_container_width=True, hide_index=True)
    else:
        estado_vacio("🗂️", "El registro está limpio.", "Los recibos enviados por correo aparecerán aquí.")

elif menu_seleccionado == "Configuración":
    encabezado("⚙️ Configuración del Sistema (Admin)", "Base de datos del personal sincronizada con Google Sheets.")

    try:
        _ = st.secrets["gcp_service_account"]
        st.markdown("<div class='gg-row'><span class='gg-pill ok'>✅ Sistema conectado exitosamente a Google Sheets.</span></div>", unsafe_allow_html=True)
    except Exception:
        st.warning("⚠️ **MODO LOCAL ACTIVADO:** No se detectan credenciales de Google Cloud.")

    st.markdown("#### 📇 Base de Datos del Personal")
    df_emp_db = pd.DataFrame.from_dict(st.session_state["empleados"], orient="index")
    df_edited = st.data_editor(df_emp_db, use_container_width=True, disabled=["rol", "alias", "mod", "porc"], key="editor_personal")

    if st.button("💾 Guardar Cambios de Personal"):
        st.session_state["empleados"] = df_edited.to_dict(orient="index")
        # Refresca los correos usados en Planillas con los recién guardados.
        for emp, info in st.session_state["empleados"].items():
            st.session_state[f"email_{emp}"] = str(_valor_para_sheets(info.get("correo", "")))
            st.session_state.pop(f"ui_e_{emp}", None)
        if guardar_empleados(st.session_state["empleados"]):
            st.toast("¡Base de personal actualizada!", icon="✅")
        else:
            st.error("No se pudo sincronizar con Google Sheets. Los cambios de personal quedaron solo en esta sesión.")
