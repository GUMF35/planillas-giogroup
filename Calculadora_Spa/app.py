import streamlit as st
import pandas as pd
import io
import os
import re
from datetime import datetime
import pdfplumber
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from fpdf import FPDF
import base64
from PIL import Image
from streamlit_option_menu import option_menu
import gspread
from google.oauth2.service_account import Credentials

# --- 0. UTILIDADES DE SEGURIDAD Y GOOGLE SHEETS ---
def limpiar_texto_pdf(txt):
    if txt is None: return ""
    return str(txt).encode('latin-1', 'replace').decode('latin-1')

def generar_pdf_bytes(pdf_obj):
    return bytes(pdf_obj.output())

@st.cache_resource
def conectar_gsheets():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        skey = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(skey, scopes=scopes)
        gc = gspread.authorize(credentials)
        sheet_url = st.secrets["gsheets"]["url"]
        return gc.open_by_url(sheet_url).sheet1
    except Exception:
        return None

def cargar_empleados():
    worksheet = conectar_gsheets()
    if worksheet:
        try:
            records = worksheet.get_all_records()
            if records:
                emp_dict = {}
                for r in records:
                    nombre = r.get("Nombre")
                    if nombre:
                        emp_dict[nombre] = {
                            "rol": str(r.get("Rol", "Operativo")),
                            "alias": str(r.get("Alias", "")),
                            "mod": str(r.get("Modalidad", "Fijo")),
                            "porc": float(r.get("Porcentaje", 0)),
                            "correo": str(r.get("Correo", "")),
                            "dui": str(r.get("DUI", "")),
                            "cuenta": str(r.get("Cuenta", ""))
                        }
                return emp_dict
        except Exception:
            pass

    # Base de datos por defecto si falla Google Sheets o no está configurado
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
    worksheet = conectar_gsheets()
    if worksheet:
        filas = [["Nombre", "Rol", "Alias", "Modalidad", "Porcentaje", "Correo", "DUI", "Cuenta"]]
        for nombre, info in datos.items():
            filas.append([
                nombre, info.get("rol", ""), info.get("alias", ""), info.get("mod", ""), 
                info.get("porc", 0), info.get("correo", ""), info.get("dui", ""), info.get("cuenta", "")
            ])
        try:
            worksheet.clear()
            try:
                worksheet.update(values=filas, range_name="A1")
            except TypeError:
                worksheet.update("A1", filas)
        except Exception:
            pass

# --- 1. CONFIGURACIÓN DE PÁGINA ---
logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
try:
    if os.path.exists(logo_path):
        icono = Image.open(logo_path)
        st.set_page_config(page_title="Gio Group Admin", page_icon=icono, layout="wide", initial_sidebar_state="expanded")
    else:
        st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")
except Exception:
    st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide")

# --- 2. ESTADO DE MEMORIA ---
if "salario_operativo_neto" not in st.session_state: st.session_state["salario_operativo_neto"] = 183.96 
if "salario_directivo_neto" not in st.session_state: st.session_state["salario_directivo_neto"] = 300.00 
if "quincenas_multiplicador" not in st.session_state: st.session_state["quincenas_multiplicador"] = 1.0
if "periodo_texto" not in st.session_state: st.session_state["periodo_texto"] = "1 Quincena (Por defecto)"
if "detalle_extras" not in st.session_state: st.session_state["detalle_extras"] = [] 

if "empleados" not in st.session_state:
    st.session_state["empleados"] = cargar_empleados()

def calcular_bruto_acumulado(rol, quincenas=None):
    neto_quincenal = st.session_state["salario_operativo_neto"] if rol == "Operativo" else st.session_state["salario_directivo_neto"]
    mult = quincenas if quincenas is not None else st.session_state["quincenas_multiplicador"]
    neto_acumulado = neto_quincenal * mult
    return round(neto_acumulado / 0.90, 2)

for emp, info in st.session_state["empleados"].items():
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"extra_bruto_{emp}" not in st.session_state: st.session_state[f"extra_bruto_{emp}"] = 0.0
    if f"ret_pub_{emp}" not in st.session_state: st.session_state[f"ret_pub_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = info.get("correo", "")
    
    mod_init = info.get("mod", "Fijo")
    if "Porcentaje" in mod_init:
        if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = 0.0
    else:
        if f"base_{emp}" not in st.session_state:
            st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", "Operativo"))

if "historial_auditoria" not in st.session_state: st.session_state["historial_auditoria"] = []
if "ingresos_por_marca" not in st.session_state: st.session_state["ingresos_por_marca"] = {}
if "extras_por_marca" not in st.session_state: st.session_state["extras_por_marca"] = {}
if "total_ingresos_pdf" not in st.session_state: st.session_state["total_ingresos_pdf"] = 0.0
if "total_fondo_publicidad" not in st.session_state: st.session_state["total_fondo_publicidad"] = 0.0

# --- 3. CSS TEMA AZUL MARINO CORPORATIVO ---
estilo_azul = """
<style>
    [data-testid="stHeader"] {display: none !important;}
    footer {display: none !important;}
    .viewerBadge_container, .stDeployButton, #Manage-app {display: none !important;}
    [data-testid="stSidebarCollapseButton"] {display: none !important;}
    .stApp { background-color: #F3F4F6 !important; }

    [data-testid="stMetric"], div[data-testid="metric-container"], .stDataFrame, [data-testid="stExpander"] {
        background-color: #FFFFFF !important; border-radius: 12px !important;
        padding: 15px !important; box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.04) !important;
        border: 1px solid #E5E7EB !important;
    }
    [data-testid="stMetric"] { border-bottom: 4px solid #2563EB !important; }
    [data-testid="stMetricLabel"] { color: #64748B !important; font-weight: 600 !important; font-size: 1.05rem !important; }
    [data-testid="stMetricValue"] { color: #0F172A !important; font-weight: 800 !important; font-size: 1.8rem !important; }
    [data-testid="stSidebar"] { background-color: #0A192F !important; border-right: none !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label { color: #94A3B8 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #FFFFFF !important; }

    div.stButton > button:first-child {
        background-color: #0A192F !important; color: #FFFFFF !important; border-radius: 8px !important;
        border: none !important; font-weight: bold !important; padding: 0.6rem 1.2rem !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover { background-color: #2563EB !important; color: #FFFFFF !important; transform: translateY(-2px); }
    h1, h2, h3 { color: #0F172A !important; font-weight: 800 !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea, .stDateInput input {
        background-color: #F8FAFC !important; border-radius: 8px !important; border: 1px solid #CBD5E1 !important; color: #0F172A !important;
    }
</style>
"""
st.markdown(estilo_azul, unsafe_allow_html=True)

# --- 4. MENÚ LATERAL ---
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path): st.image(logo_path, use_container_width=True)
    else: st.markdown("<h2 style='text-align:center; color:white;'>GIO GROUP</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        menu_icon="cast", default_index=1,
        styles={
            "container": {"padding": "0!important", "background-color": "#0A192F"},
            "icon": {"color": "#94A3B8", "font-size": "16px"},
            "nav-link": {"font-size": "14px", "text-align": "left", "margin":"4px 0px", "padding": "10px 15px", "color": "#94A3B8", "--hover-color": "#112240"},
            "nav-link-selected": {"background-color": "#112240", "color": "#3B82F6", "font-weight": "bold", "border-left": "4px solid #3B82F6"}
        }
    )

# --- 5. PANEL SUPERIOR: LECTOR DE PDF Y DEPURADOR ---
if menu_seleccionado != "Configuración":
    with st.container():
        st.markdown("<h2 style='color:#0F172A; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)

        col_up1, col_up2 = st.columns([3, 1])
        with col_up1:
            archivo_subido = st.file_uploader("📥 Sincronizar reporte de ventas (PDF)", type=["pdf"])
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🧹 Limpiar Reporte PDF"):
                st.session_state["total_ingresos_pdf"] = 0.0
                st.session_state["ingresos_por_marca"] = {}
                st.session_state["extras_por_marca"] = {}
                st.session_state["total_fondo_publicidad"] = 0.0
                st.session_state["quincenas_multiplicador"] = 1.0
                st.session_state["periodo_texto"] = "1 Quincena (Por defecto)"
                st.session_state["detalle_extras"] = [] 
                for emp, info in st.session_state["empleados"].items():
                    st.session_state[f"com_{emp}"] = 0.0
                    st.session_state[f"extra_bruto_{emp}"] = 0.0
                    st.session_state[f"ret_pub_{emp}"] = 0.0
                    st.session_state[f"serv_tot_{emp}"] = 0.0
                    if "Porcentaje" in st.session_state.get(f"mod_{emp}", info.get("mod", "")):
                        st.session_state[f"base_{emp}"] = 0.0
                    else:
                        st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", "Operativo"), 1.0)
                st.rerun()

        if archivo_subido is not None:
            try:
                texto_completo = ""
                todas_las_filas = []
                with pdfplumber.open(archivo_subido) as pdf:
                    for page in pdf.pages:
                        texto_pagina = page.extract_text() or ""
                        texto_completo += texto_pagina + " "
                        tabla = page.extract_table()
                        if tabla: todas_las_filas.extend(tabla)

                fechas_iso = re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', texto_completo)
                if len(fechas_iso) >= 2:
                    min_fecha = datetime.strptime(fechas_iso[0], '%Y-%m-%d')
                    max_fecha = datetime.strptime(fechas_iso[1], '%Y-%m-%d')
                else:
                    fechas_alt = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', texto_completo)
                    fechas_dt = []
                    for f in fechas_alt:
                        try: fechas_dt.append(datetime.strptime(f.replace('-','/'), '%d/%m/%Y'))
                        except: pass
                    min_fecha = min(fechas_dt) if fechas_dt else datetime.now()
                    max_fecha = max(fechas_dt) if fechas_dt else datetime.now()

                dias_diff = (max_fecha - min_fecha).days + 1

                if dias_diff <= 16:
                    factor_mult = 1.0
                    texto_periodo = f"Del {min_fecha.strftime('%d/%m/%Y')} al {max_fecha.strftime('%d/%m/%Y')} (1 Quincena)"
                elif dias_diff <= 31:
                    factor_mult = 2.0
                    texto_periodo = f"Del {min_fecha.strftime('%d/%m/%Y')} al {max_fecha.strftime('%d/%m/%Y')} (1 Mes / 2 Quincenas)"
                else:
                    meses_calculados = max(2, round(dias_diff / 30.0))
                    factor_mult = float(meses_calculados * 2.0)
                    texto_periodo = f"Del {min_fecha.strftime('%d/%m/%Y')} al {max_fecha.strftime('%d/%m/%Y')} ({meses_calculados} Meses / {int(factor_mult)} Quincenas)"

                st.session_state["quincenas_multiplicador"] = factor_mult
                st.session_state["periodo_texto"] = texto_periodo

                header_idx = -1
                for i, row in enumerate(todas_las_filas):
                    if row and any(isinstance(cell, str) and 'PROFESIONAL' in cell.upper() for cell in row):
                        header_idx = i; break

                if header_idx != -1:
                    df_reporte = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
                    df_reporte.columns = df_reporte.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
                    
                    col_prof = next((col for col in df_reporte.columns if 'PROFESIONAL' in col), None)
                    col_precio = next((col for col in df_reporte.columns if 'PRECIO' in col), None)
                    col_cliente = next((col for col in df_reporte.columns if 'CLIENTE' in col), None)
                    col_corr = next((col for col in df_reporte.columns if 'CORRELATIVO' in col), None)
                    col_serv = next((col for col in df_reporte.columns if 'SERVICIO' in col), None)

                    if col_prof and col_precio:
                        df_reporte = df_reporte.dropna(subset=[col_prof, col_precio])
                        df_reporte = df_reporte[~df_reporte[col_prof].astype(str).str.upper().str.contains('PROFESIONAL', na=False)]
                        df_reporte[col_precio] = df_reporte[col_precio].astype(str).str.replace(r'[\$,\n]', '', regex=True)
                        df_reporte[col_precio] = pd.to_numeric(df_reporte[col_precio], errors='coerce').fillna(0.0)

                        st.session_state["total_ingresos_pdf"] = df_reporte[col_precio].sum()

                        def asignar_marca(profesional):
                            p = str(profesional).upper()
                            if "MAYDELY" in p or "JESSICA" in p or "MARIO" in p: return "Papi Spa"
                            if "LUIS" in p: return "Relájate Man"
                            if "GIO" in p or "MARVIN" in p or "DOCTOR" in p: return "Dr. Gio Molina"
                            return "Relájate Clinic"

                        df_reporte['MARCA'] = df_reporte[col_prof].apply(asignar_marca)
                        st.session_state["ingresos_por_marca"] = df_reporte.groupby('MARCA')[col_precio].sum().to_dict()

                        def calcular_extra_marca(row):
                            return 0.0 if row['MARCA'] == "Dr. Gio Molina" else max(0.0, float(row[col_precio]) - 60.0)
                        df_reporte['EXTRA_BRUTO'] = df_reporte.apply(calcular_extra_marca, axis=1)
                        st.session_state["extras_por_marca"] = df_reporte.groupby('MARCA')['EXTRA_BRUTO'].sum().to_dict()

                        st.session_state["total_fondo_publicidad"] = 0.0
                        lista_detalles_extra = []

                        for emp, info in st.session_state["empleados"].items():
                            mod_actual = st.session_state.get(f"mod_{emp}", info.get("mod", "Fijo"))
                            if "Porcentaje" in mod_actual:
                                st.session_state[f"base_{emp}"] = 0.0
                            else:
                                st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", "Operativo"), st.session_state["quincenas_multiplicador"])

                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(info.get("alias", ""), case=False, na=False, regex=True)]
                            tot_serv = df_p[col_precio].sum()
                            st.session_state[f"serv_tot_{emp}"] = tot_serv

                            if info.get("rol", "") == "Operativo":
                                if "Estándar" in mod_actual:
                                    df_ex = df_p[df_p[col_precio] > 60.0].copy()
                                    ext_bruto_total = 0.0
                                    desc_pub_total = 0.0
                                    
                                    if not df_ex.empty:
                                        for _, row_ex in df_ex.iterrows():
                                            precio_val = float(row_ex[col_precio])
                                            extra_indiv = precio_val - 60.0
                                            ret_indiv = extra_indiv * 0.25
                                            com_indiv = extra_indiv - ret_indiv
                                            
                                            ext_bruto_total += extra_indiv
                                            desc_pub_total += ret_indiv
                                            
                                            c_corr = str(row_ex[col_corr]) if col_corr else "N/A"
                                            fecha_str = c_corr.split('-')[0] if '-' in c_corr else c_corr
                                            try:
                                                if len(fecha_str) == 8:
                                                    fecha_fmt = f"{fecha_str[6:8]}/{fecha_str[4:6]}/{fecha_str[0:4]}"
                                                else:
                                                    fecha_fmt = fecha_str
                                            except:
                                                fecha_fmt = fecha_str

                                            lista_detalles_extra.append({
                                                "Colaborador": emp,
                                                "Fecha": fecha_fmt,
                                                "Cliente": str(row_ex[col_cliente]).replace('\n', ' ') if col_cliente else "N/A",
                                                "Servicio": str(row_ex[col_serv]).replace('\n', ' ') if col_serv else "N/A",
                                                "Precio Final": precio_val,
                                                "Extra Generado": extra_indiv,
                                                "Retención (25%)": ret_indiv,
                                                "Comisión Neta": com_indiv
                                            })
                                    
                                    comision_neta_total = max(0.0, ext_bruto_total - desc_pub_total)
                                    
                                    st.session_state[f"extra_bruto_{emp}"] = ext_bruto_total
                                    st.session_state[f"com_{emp}"] = comision_neta_total
                                    st.session_state[f"ret_pub_{emp}"] = desc_pub_total
                                    st.session_state["total_fondo_publicidad"] += desc_pub_total
                                else:
                                    porc = st.session_state.get(f"porc_{emp}", info.get("porc", 20))
                                    st.session_state[f"extra_bruto_{emp}"] = 0.0
                                    st.session_state[f"com_{emp}"] = tot_serv * (porc / 100.0)
                                    st.session_state[f"ret_pub_{emp}"] = 0.0
                            else:
                                st.session_state[f"extra_bruto_{emp}"] = 0.0
                                st.session_state[f"com_{emp}"] = 0.0
                                st.session_state[f"ret_pub_{emp}"] = 0.0
                                
                        st.session_state["detalle_extras"] = lista_detalles_extra
                        st.success(f"✅ ¡PDF analizado con éxito! {st.session_state['periodo_texto']}")
                    else:
                        st.warning("⚠️ Se encontró una tabla, pero no se pudieron identificar las columnas 'PROFESIONAL' y 'PRECIO'.")
                else:
                    st.warning("⚠️ No se detectó ninguna tabla válida en el PDF.")
            except Exception as e:
                st.error(f"Error procesando PDF: {e}")

        st.info(f"📅 **Período en análisis:** {st.session_state['periodo_texto']}")
    st.markdown("<br>", unsafe_allow_html=True)

# --- 6. ENRUTAMIENTO DE PÁGINAS ---

if menu_seleccionado == "Dashboard":
    if st.session_state["total_ingresos_pdf"] > 0:
        costo_planilla = sum([
            round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] - (0.0 if "Porcentaje" in st.session_state.get(f"mod_{emp}", st.session_state["empleados"][emp].get("mod", "")) and st.session_state["empleados"][emp].get("rol", "") == "Operativo" else round(st.session_state[f"base_{emp}"] * 0.10, 2)), 2)
            for emp in st.session_state["empleados"].keys()
        ])
        utilidad_neta = st.session_state["total_ingresos_pdf"] - costo_planilla

        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos Totales", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Costo Operativo (Planillas)", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta:,.2f}", delta=f"{((utilidad_neta/st.session_state['total_ingresos_pdf'])*100):.1f}% Margen")

        st.markdown("<br>", unsafe_allow_html=True)
        estrella_collab = max(st.session_state["empleados"].keys(), key=lambda e: st.session_state.get(f"serv_tot_{e}", 0.0))
        monto_estrella = st.session_state.get(f"serv_tot_{estrella_collab}", 0.0)

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 100%); padding: 20px; border-radius: 12px; color: white; box-shadow: 0px 4px 15px rgba(37,99,235,0.2);">
            <h3 style="margin: 0; color: #FFFFFF !important;">🌟 Colaborador Estrella del Período (MVP)</h3>
            <p style="margin: 5px 0 0 0; font-size: 1.2rem;"><b>{estrella_collab}</b> lidera el rendimiento con un total de <b>${monto_estrella:,.2f}</b> generados en servicios.</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("<h3 style='color:#0F172A;'>⭐ Rendimiento del Personal Activo</h3>", unsafe_allow_html=True)
        datos_rendimiento = [{"Colaborador": e, "Rol": st.session_state["empleados"][e].get("rol", ""), "Total Generado ($)": st.session_state.get(f"serv_tot_{e}", 0.0)} for e in st.session_state["empleados"]]
        st.dataframe(pd.DataFrame(datos_rendimiento).style.format({"Total Generado ($)": "${:,.2f}"}), use_container_width=True, hide_index=True)

        st.markdown("<br><h3 style='color:#0F172A;'>🎯 Rendimiento Neto de Marcas (Holding)</h3>", unsafe_allow_html=True)
        marcas = st.session_state["ingresos_por_marca"]
        extras = st.session_state["extras_por_marca"]
        cols_metas = st.columns(len(marcas) if len(marcas) > 0 else 1)
        metas_config = {}

        for i, (marca, ingresos) in enumerate(marcas.items()):
            meta_def = 8000.0 * (st.session_state["quincenas_multiplicador"] / 2.0) if "Dr" in marca else 5000.0 * (st.session_state["quincenas_multiplicador"] / 2.0)
            metas_config[marca] = cols_metas[i].number_input(f"Meta: {marca}", value=meta_def, step=500.0, key=f"meta_{marca}")

        df_marcas = pd.DataFrame([{
            "Empresa": m, "Ingresos Brutos": ing, "Extras Brutos": extras.get(m, 0.0), "NETO CLÍNICA": ing - extras.get(m, 0.0), "Meta Asignada": metas_config[m], "Estado": "✅ Alcanzada" if ing >= metas_config[m] else "⚠️ Pendiente"
        } for m, ing in marcas.items()])

        c_chart, c_table = st.columns([2, 3])
        with c_chart: st.bar_chart(pd.DataFrame.from_dict(marcas, orient='index', columns=['Ingresos Brutos ($)']))
        with c_table: st.dataframe(df_marcas.style.format({"Ingresos Brutos": "${:,.2f}", "Extras Brutos": "${:,.2f}", "NETO CLÍNICA": "${:,.2f}", "Meta Asignada": "${:,.2f}"}), hide_index=True)
    else:
        st.info("Sube el PDF de ingresos para generar el reporte corporativo.")

elif menu_seleccionado == "Planillas":
    st.markdown("<h2 style='color:#0F172A;'>Control Financiero de Planillas</h2>", unsafe_allow_html=True)
    
    if st.session_state.get("detalle_extras"):
        with st.expander("🔍 Ver Desglose Informativo: Servicios con Extra Generado", expanded=False):
            st.info("Este apartado es informativo. Desglosa los servicios mayores a $60 para el personal Estándar.")
            df_det = pd.DataFrame(st.session_state["detalle_extras"])
            st.dataframe(df_det.style.format({
                "Precio Final": "${:.2f}",
                "Extra Generado": "${:.2f}",
                "Retención (25%)": "${:.2f}",
                "Comisión Neta": "${:.2f}"
            }), use_container_width=True, hide_index=True)
            
    st.markdown("<br>", unsafe_allow_html=True)
    datos_emp = []

    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info.get('rol', '')})", expanded=True if "Maydely" in emp else False):
            c1, c2, c3 = st.columns([1.2, 1, 1])

            with c1:
                if info.get("rol", "") == "Operativo":
                    mod = st.selectbox(f"Modalidad", ["Estándar (Con retención 25% Pub)", "Porcentaje Directo (%)"], index=0 if "Estándar" in st.session_state.get(f"mod_{emp}", info.get("mod", "")) else 1, key=f"m_{emp}")
                    if "Estándar" in mod:
                        st.session_state[f"mod_{emp}"] = "Estándar (Con retención 25% Pub)"
                    else:
                        st.session_state[f"mod_{emp}"] = "Porcentaje Directo (%)"
                        porc = st.slider(f"% Ganancia", 0, 100, int(st.session_state.get(f"porc_{emp}", info.get("porc", 20))), key=f"p_{emp}")
                        st.session_state[f"com_{emp}"] = st.session_state[f"serv_tot_{emp}"] * (porc / 100.0)
                        st.session_state[f"extra_bruto_{emp}"] = 0.0
                        st.session_state[f"ret_pub_{emp}"] = 0.0
                        st.session_state[f"porc_{emp}"] = porc
                else:
                    st.caption(f"Personal Administrativo (Sueldo Fijo)")

                mod_actual = st.session_state.get(f"mod_{emp}", info.get("mod", ""))
                if info.get("rol", "") == "Operativo" and "Porcentaje" in mod_actual:
                    st.session_state[f"base_{emp}"] = 0.0
                    st.write("Sueldo Base (Bruto): **$0.00** (Modalidad Porcentaje)")
                else:
                    val_base = st.number_input(f"Sueldo Base (Bruto) ($)", value=float(st.session_state[f"base_{emp}"]), key=f"ui_b_{emp}")
                    st.session_state[f"base_{emp}"] = val_base

                val_com = st.number_input(f"Comisiones Netas ($)", value=float(st.session_state[f"com_{emp}"]), key=f"ui_c_{emp}")
                st.session_state[f"com_{emp}"] = val_com

            with c2:
                val_hex = st.number_input(f"Bonos / Nivelación ($)", value=float(st.session_state[f"hex_{emp}"]), key=f"ui_h_{emp}")
                st.session_state[f"hex_{emp}"] = val_hex

                val_desc = st.number_input(f"Descuentos ($)", value=float(st.session_state[f"desc_{emp}"]), key=f"ui_d_{emp}")
                st.session_state[f"desc_{emp}"] = val_desc

            with c3:
                n_desc = st.text_input(f"Notas", value="Ninguno", key=f"n_{emp}")
                e_em = st.text_input(f"Correo", value=info.get("correo", ""), key=f"ui_e_{emp}", placeholder="correo@ejemplo.com")
                st.session_state[f"email_{emp}"] = e_em

            if info.get("rol", "") == "Operativo" and "Porcentaje" in mod_actual:
                renta_calculada = 0.0
            else:
                renta_calculada = round(st.session_state[f"base_{emp}"] * 0.10, 2)

            extra_bruto_val = round(st.session_state.get(f"extra_bruto_{emp}", 0.0), 2)
            ret_pub_actual = round(st.session_state.get(f"ret_pub_{emp}", 0.0), 2)

            t_net = round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - renta_calculada - st.session_state[f"desc_{emp}"], 2)

            datos_emp.append({
                "Colaborador": emp,
                "Sueldo Base (Bruto)": st.session_state[f"base_{emp}"],
                "Extra Bruto": extra_bruto_val,
                "Retención Pub (25%)": ret_pub_actual,
                "Comisiones Netas": st.session_state[f"com_{emp}"],
                "Bonos": st.session_state[f"hex_{emp}"],
                "Descuentos": st.session_state[f"desc_{emp}"],
                "10% Renta": renta_calculada,
                "Total a Pagar": t_net,
                "Notas": n_desc,
                "Email": st.session_state[f"email_{emp}"],
                "DUI": info.get("dui", ""),
                "Cuenta": info.get("cuenta", "")
            })

    if datos_emp:
        df_res = pd.DataFrame(datos_emp)
        st.markdown("<br><h4>Resumen Consolidado</h4>", unsafe_allow_html=True)
        df_display = df_res.drop(columns=["Notas", "Email", "DUI", "Cuenta"])
        st.dataframe(df_display.style.format({
            "Sueldo Base (Bruto)": "${:.2f}",
            "Extra Bruto": "${:,.2f}",
            "Retención Pub (25%)": "${:.2f}",
            "Comisiones Netas": "${:.2f}",
            "Bonos": "${:.2f}",
            "Descuentos": "${:.2f}",
            "10% Renta": "${:.2f}",
            "Total a Pagar": "${:.2f}"
        }), use_container_width=True, hide_index=True)

        out_ex = io.BytesIO()
        with pd.ExcelWriter(out_ex, engine='openpyxl') as w: df_res.to_excel(w, index=False)
        out_ex.seek(0)
        st.download_button("📥 Exportar Reporte de Planilla (Excel)", data=out_ex, file_name="Reporte_Planilla.xlsx")

        st.markdown("---")
        st.markdown("<h3>Gestión y Envío de Recibos</h3>", unsafe_allow_html=True)
        e_sel = st.selectbox("Seleccionar Colaborador:", list(st.session_state["empleados"].keys()))
        e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)

        if st.button("👁️ Visualizar y Generar Recibo (PDF)"):
            class PDF(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    if os.path.exists(logo_path): self.set_x(40)
                    self.set_font('helvetica', '', 10); self.set_text_color(100, 100, 100); self.cell(0, 5, 'Comprobante Oficial de Pago', 0, 1, 'L')
                    if os.path.exists(logo_path): self.set_x(40)
                    self.cell(0, 5, limpiar_texto_pdf(f"Periodo Liquidado: {st.session_state['periodo_texto']}"), 0, 1, 'L')
                    self.ln(5)

            pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 10, limpiar_texto_pdf(f" Colaborador: {e_dat['Colaborador']}"), 0, 1, 'L', fill=True); pdf.ln(5)
            
            pdf.set_font('helvetica', '', 9); pdf.set_text_color(80, 80, 80)
            txt_banco = f"DUI: {e_dat['DUI']} | Cuenta a Depositar: {e_dat['Cuenta']}" if e_dat['DUI'] or e_dat['Cuenta'] else "Datos bancarios no registrados"
            pdf.cell(0, 5, limpiar_texto_pdf(txt_banco), 0, 1, 'L'); pdf.ln(3)

            pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
            pdf.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)

            for d, v in [("Sueldo Base Acumulado (Bruto)", e_dat['Sueldo Base (Bruto)']), ("Extra Bruto Generado", e_dat['Extra Bruto']), ("Comisiones Netas a Pagar", e_dat['Comisiones Netas']), ("Bonos Extras", e_dat['Bonos'])]:
                if v > 0 or "Sueldo" in d or "Comisiones" in d:
                    pdf.cell(130, 8, limpiar_texto_pdf(f"  {d}"), 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')

            pdf.set_text_color(201, 42, 42)
            if e_dat['Descuentos'] > 0:
                pdf.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Descuentos']:.2f}", 1, 1, 'R')

            if e_dat['Retención Pub (25%)'] > 0:
                pdf.cell(130, 8, "  (Informativo) Retención 25% Publicidad", 1, 0, 'L'); pdf.cell(60, 8, f"${e_dat['Retención Pub (25%)']:.2f}", 1, 1, 'R')

            if e_dat['10% Renta'] > 0:
                pdf.cell(130, 8, "  (-) 10% Retención de Renta", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['10% Renta']:.2f}", 1, 1, 'R')

            pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
            pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total a Pagar']:.2f}", 1, 1, 'R', fill=True)

            notas_val = str(e_dat.get('Notas', 'Ninguno')).strip()
            if not notas_val or notas_val.lower() == 'ninguno':
                notas_val = "Sin notas adicionales"
            pdf.ln(6)
            pdf.set_font('helvetica', 'B', 10); pdf.set_text_color(10, 25, 47); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 7, "  Notas del Registro:", 0, 1, 'L', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, limpiar_texto_pdf(f"  {notas_val}"), 0, 'L')

            nombre_archivo = f"Recibo_{e_sel.replace(' ','_')}.pdf"
            st.session_state['t_pdf'] = generar_pdf_bytes(pdf)
            st.session_state['t_path'] = nombre_archivo

        if 't_pdf' in st.session_state:
            st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")

            correo_destino_valido = bool(e_dat["Email"]) and "@" in e_dat["Email"]
            if not correo_destino_valido:
                st.warning("⚠️ Este colaborador no tiene un correo válido configurado. Edítalo en 'Configuración' o ingresa uno temporalmente.")

            if st.button("🚀 Enviar Recibo por Gmail al Colaborador", disabled=not correo_destino_valido):
                try:
                    remitente = st.secrets["EMAIL_USER"]
                    password = st.secrets["EMAIL_PASS"]
                    destinatario = e_dat["Email"]

                    msg = MIMEMultipart()
                    msg['From'] = remitente
                    msg['To'] = destinatario
                    msg['Subject'] = f"Comprobante Oficial de Pago - Período: {st.session_state['periodo_texto']} | GIO GROUP"

                    cuerpo_correo = f"""Estimado/a {e_dat['Colaborador']},

Es un placer saludarle de parte de la Dirección Administrativa de GIO GROUP SAS DE CV.

Adjunto a este correo electrónico encontrará su Comprobante Oficial de Pago detallado, correspondiente al {st.session_state['periodo_texto']}. Le invitamos a revisar minuciosamente el desglose de su sueldo base, comisiones netas, retenciones e incentivos aplicados en este ciclo.

Agradecemos profundamente su valiosa labor, dedicación y compromiso continuo con el crecimiento y la excelencia de nuestras marcas y clínicas. Su esfuerzo diario es un pilar fundamental para nuestra organización.

Si tuviese alguna consulta técnica, aclaración sobre el cálculo o inquietud respecto a su comprobante, por favor no dude en comunicarse directamente con el departamento de Administración.

Atentamente y con los mejores deseos,

Departamento de Administración y Recursos Humanos
GIO GROUP SAS DE CV
"""

                    msg.attach(MIMEText(cuerpo_correo, 'plain'))

                    parte_adjunta = MIMEApplication(st.session_state['t_pdf'], Name=st.session_state['t_path'])
                    parte_adjunta['Content-Disposition'] = f'attachment; filename="{st.session_state["t_path"]}"'
                    msg.attach(parte_adjunta)

                    servidor_smtp = smtplib.SMTP('smtp.gmail.com', 587)
                    servidor_smtp.starttls()
                    servidor_smtp.login(remitente, password)
                    servidor_smtp.sendmail(remitente, destinatario, msg.as_string())
                    servidor_smtp.quit()

                    st.session_state["historial_auditoria"].append({
                        "Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "Tipo Documento": "Recibo de Pago",
                        "Destinatario": e_sel
                    })
                    st.success(f"¡Comprobante enviado exitosamente por Gmail con formato corporativo a {destinatario}!")
                except Exception as ex:
                    st.error(f"Error al enviar el correo mediante Gmail. Verifique sus secretos en Streamlit Cloud (EMAIL_USER y EMAIL_PASS): {ex}")

elif menu_seleccionado == "Memorándums":
    st.markdown("<h2 style='color:#0F172A;'>📝 Emisión de Memorándums Internos</h2>", unsafe_allow_html=True)
    emp_memo = st.selectbox("Destinatario del Memorándum:", list(st.session_state["empleados"].keys()))
    asunto_memo = st.text_input("Asunto a tratar:", value="Aviso Administrativo Oficial")
    texto_memo = st.text_area("Cuerpo o notas del Memorándum:")

    if st.button("👁️ Generar PDF Oficial"):
        if texto_memo:
            class PDFMemo(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
            pdf_m = PDFMemo(); pdf_m.add_page(); pdf_m.set_font('helvetica', 'B', 11)
            pdf_m.cell(0, 10, limpiar_texto_pdf(f" Entregado a: {emp_memo}"), 0, 1, 'L'); pdf_m.cell(0, 10, limpiar_texto_pdf(f" Asunto Central: {asunto_memo}"), 0, 1, 'L')
            pdf_m.set_font('helvetica', '', 11); pdf_m.multi_cell(0, 7, limpiar_texto_pdf(texto_memo), 0, 'L')

            nombre_memo = f"Memorandum_{emp_memo.replace(' ','_')}.pdf"
            st.session_state['temp_memo_pdf'] = generar_pdf_bytes(pdf_m)
            st.session_state['temp_memo_path'] = nombre_memo
        else:
            st.info("Indica el contenido del memorándum para poder redactar el documento.")

    if 'temp_memo_pdf' in st.session_state:
        st.download_button("📄 Descargar Archivo PDF", data=st.session_state['temp_memo_pdf'], file_name=st.session_state['temp_memo_path'])

elif menu_seleccionado == "Amonestaciones":
    st.markdown("<h2 style='color:#0F172A;'>⚠️ Registro de Faltas y Amonestaciones</h2>", unsafe_allow_html=True)
    emp_amon = st.selectbox("Colaborador involucrado:", list(st.session_state["empleados"].keys()))
    tipo_falta = st.selectbox("Gravedad de la Falta:", ["Llamada de Atención Verbal", "Amonestación Escrita Leve", "Amonestación Escrita Grave"])
    motivo_amon = st.text_area("Detalles completos del incidente:")

    if st.button("👁️ Redactar Acta PDF"):
        if motivo_amon:
            class PDFAmon(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(201, 42, 42); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
            pdf_a = PDFAmon(); pdf_a.add_page(); pdf_a.set_font('helvetica', 'B', 11)
            pdf_a.cell(0, 10, limpiar_texto_pdf(f" Dirigido a: {emp_amon}"), 0, 1, 'L')
            pdf_a.cell(0, 10, limpiar_texto_pdf(f" Tipo de Falta: {tipo_falta}"), 0, 1, 'L')
            pdf_a.set_font('helvetica', '', 11); pdf_a.multi_cell(0, 7, limpiar_texto_pdf(motivo_amon), 1, 'L')

            nombre_amon = f"Acta_Amonestacion_{emp_amon.replace(' ','_')}.pdf"
            st.session_state['temp_amon_pdf'] = generar_pdf_bytes(pdf_a)
            st.session_state['temp_amon_path'] = nombre_amon
        else:
            st.info("Describe el incidente para poder redactar el acta formal.")

    if 'temp_amon_pdf' in st.session_state:
        st.download_button("📄 Descargar Acta Formal", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])

elif menu_seleccionado == "Auditoría":
    st.markdown("<h2 style='color:#0F172A;'>🖨️ Registro y Control de Auditoría</h2>", unsafe_allow_html=True)
    if st.session_state["historial_auditoria"]:
        st.dataframe(pd.DataFrame(st.session_state["historial_auditoria"]), use_container_width=True)
    else:
        st.info("El registro está limpio. No se han detectado envíos recientes por correo.")

elif menu_seleccionado == "Configuración":
    st.markdown("<h2 style='color:#0F172A;'>⚙️ Configuración del Sistema (Admin)</h2>", unsafe_allow_html=True)
    
    st.markdown("### 📇 Base de Datos del Personal (Sincronizada con Google Sheets)")
    
    # Revisión de estado de conexión a Google Cloud
    try:
        _ = st.secrets["gcp_service_account"]
        _ = st.secrets["gsheets"]["url"]
        st.success("✅ Sistema conectado exitosamente a Google Sheets.")
    except Exception:
        st.warning("⚠️ **MODO LOCAL ACTIVADO:** No se han detectado credenciales de Google Cloud. Puedes usar el sistema hoy, pero los datos de esta tabla se perderán al reiniciar el servidor. Sigue las instrucciones de Google Cloud para hacerlos permanentes.")
    
    df_emp_db = pd.DataFrame.from_dict(st.session_state["empleados"], orient="index")
    df_edited = st.data_editor(
        df_emp_db, 
        use_container_width=True, 
        disabled=["rol", "alias", "mod", "porc"],
        column_config={
            "correo": st.column_config.TextColumn("Correo Electrónico"),
            "dui": st.column_config.TextColumn("DUI"),
            "cuenta": st.column_config.TextColumn("Cuenta Bancaria")
        }
    )
    
    if st.button("💾 Guardar Cambios en Base de Datos"):
        st.session_state["empleados"] = df_edited.to_dict(orient="index")
        guardar_empleados(st.session_state["empleados"])
        st.success("¡Base de datos actualizada! Los datos aparecerán automáticamente en las planillas.")

    st.markdown("---")

    st.markdown("### 💰 Sueldos Netos (Por Quincena)")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.session_state["salario_operativo_neto"] = st.number_input("Sueldo Quincenal NETO Operativo:", value=float(st.session_state["salario_operativo_neto"]), step=10.0)
    with col_s2:
        st.session_state["salario_directivo_neto"] = st.number_input("Sueldo Quincenal NETO Administrativo:", value=float(st.session_state["salario_directivo_neto"]), step=10.0)

    st.markdown("---")
    st.markdown("### 📅 Ajuste Manual de Período")
    c_t1, c_t2 = st.columns(2)
    with c_t1: st.text_input("Periodo Detectado Actual:", value=st.session_state["periodo_texto"], disabled=True)
    with c_t2:
        meses_manual = st.number_input("Multiplicador Manual (Quincenas):", value=float(st.session_state["quincenas_multiplicador"]), step=1.0)
        if st.button("Aplicar Multiplicador Manual"):
            st.session_state["quincenas_multiplicador"] = float(meses_manual)
            for emp, info in st.session_state["empleados"].items():
                if not "Porcentaje" in info.get("mod", ""):
                    st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", ""))
            st.success("Multiplicador manual aplicado.")
            st.rerun()

    st.markdown("---")
    st.markdown("### 👥 Gestión de Personal (Altas y Bajas)")
    col_p1, col_p2 = st.columns([1, 1])
    with col_p1:
        st.markdown("#### ✨ Alta de Colaborador")
        n_nombre = st.text_input("Nombre Completo:")
        n_rol = st.selectbox("Rol:", ["Operativo", "Administrativo"])
        n_mod = st.selectbox("Modalidad:", ["Estándar (Con retención 25% Pub)", "Porcentaje Directo (%)"])
        n_porc = st.number_input("Porcentaje (%) si aplica:", value=20)
        n_alias = st.text_input("Alias PDF (Ej. MARIA):")
        
        n_correo = st.text_input("Correo Electrónico (Opcional):")
        n_dui = st.text_input("DUI (Opcional):")
        n_cuenta = st.text_input("Cuenta Bancaria (Opcional):")

        if st.button("➕ Registrar"):
            if n_nombre and n_alias:
                if n_nombre in st.session_state["empleados"]:
                    st.error(f"Ya existe un colaborador registrado como '{n_nombre}'.")
                else:
                    st.session_state["empleados"][n_nombre] = {
                        "rol": n_rol, "alias": n_alias.upper(), "mod": n_mod, "porc": n_porc,
                        "correo": n_correo, "dui": n_dui, "cuenta": n_cuenta
                    }
                    st.session_state[f"com_{n_nombre}"] = 0.0
                    st.session_state[f"extra_bruto_{n_nombre}"] = 0.0
                    st.session_state[f"ret_pub_{n_nombre}"] = 0.0
                    st.session_state[f"serv_tot_{n_nombre}"] = 0.0
                    st.session_state[f"email_{n_nombre}"] = n_correo
                    st.session_state[f"hex_{n_nombre}"] = 0.0
                    st.session_state[f"desc_{n_nombre}"] = 0.0
                    if "Porcentaje" in n_mod:
                        st.session_state[f"base_{n_nombre}"] = 0.0
                    else:
                        st.session_state[f"base_{n_nombre}"] = calcular_bruto_acumulado(n_rol)
                    
                    guardar_empleados(st.session_state["empleados"])
                    st.success(f"{n_nombre} guardado exitosamente en la base de datos.")
                    st.rerun()
            else:
                st.info("Ingresa al menos el nombre completo y el alias en PDF antes de registrar.")

    with col_p2:
        st.markdown("#### 🗑️ Dar de Baja a Colaborador")
        e_elim = st.selectbox("Seleccionar colaborador:", list(st.session_state["empleados"].keys()))
        if st.button("❌ Eliminar Permanentemente"):
            del st.session_state["empleados"][e_elim]
            guardar_empleados(st.session_state["empleados"])
            st.warning("Colaborador eliminado de la base de datos.")
            st.rerun()
