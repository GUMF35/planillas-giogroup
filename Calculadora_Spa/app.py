import streamlit as st
import pandas as pd
import io
import os
import re
import json
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
        except:
            return doc.sheet1
    except Exception:
        return None

# --- CARGA Y GUARDADO DE DATOS (EMPLEADOS, INVENTARIO, PROVEEDORES) ---
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
        except Exception: pass
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
    worksheet = conectar_gsheets("Personal")
    if worksheet:
        filas = [["Nombre", "Rol", "Alias", "Modalidad", "Porcentaje", "Correo", "DUI", "Cuenta"]]
        for nombre, info in datos.items():
            filas.append([nombre, info.get("rol", ""), info.get("alias", ""), info.get("mod", ""), info.get("porc", 0), info.get("correo", ""), info.get("dui", ""), info.get("cuenta", "")])
        try:
            worksheet.clear()
            worksheet.update(values=filas, range_name="A1")
        except Exception: pass

def cargar_inventario():
    worksheet = conectar_gsheets("Inventario")
    if worksheet:
        try:
            records = worksheet.get_all_records()
            if records: return records
        except: pass
    return [{"ID": "S001", "Producto": "Toxina Botulínica", "Categoría/Clínica": "Dr. Gio Molina", "Stock Disponible": 10, "Costo Unitario ($)": 150.00, "Alerta Stock Mínimo": 5}]

def guardar_inventario(datos_list):
    worksheet = conectar_gsheets("Inventario")
    if worksheet and datos_list:
        filas = [list(datos_list[0].keys())]
        for item in datos_list: filas.append(list(item.values()))
        try:
            worksheet.clear()
            worksheet.update(values=filas, range_name="A1")
        except Exception: pass

def cargar_proveedores():
    worksheet = conectar_gsheets("Proveedores")
    if worksheet:
        try:
            records = worksheet.get_all_records()
            if records: return records
        except: pass
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
    worksheet = conectar_gsheets("Proveedores")
    if worksheet and datos_list:
        filas = [list(datos_list[0].keys())]
        for item in datos_list: filas.append(list(item.values()))
        try:
            worksheet.clear()
            worksheet.update(values=filas, range_name="A1")
        except Exception: pass

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

if "empleados" not in st.session_state: st.session_state["empleados"] = cargar_empleados()
if "inventario" not in st.session_state: st.session_state["inventario"] = cargar_inventario()
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
    
    mod_init = info.get("mod", "Fijo")
    if "Porcentaje" in mod_init:
        if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = 0.0
    else:
        if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = calcular_bruto_acumulado(info.get("rol", "Operativo"))

if "historial_auditoria" not in st.session_state: st.session_state["historial_auditoria"] = []
if "total_ingresos_pdf" not in st.session_state: st.session_state["total_ingresos_pdf"] = 0.0
if "ingresos_por_marca" not in st.session_state: st.session_state["ingresos_por_marca"] = {}
if "extras_por_marca" not in st.session_state: st.session_state["extras_por_marca"] = {}

# --- 3. CSS ---
st.markdown("""
<style>
    [data-testid="stHeader"] {display: none !important;} footer {display: none !important;}
    .stApp { background-color: #F3F4F6 !important; }
    [data-testid="stMetric"], div[data-testid="metric-container"], .stDataFrame, [data-testid="stExpander"] {
        background-color: #FFFFFF !important; border-radius: 12px !important; padding: 15px !important; 
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.04) !important; border: 1px solid #E5E7EB !important;
    }
    [data-testid="stSidebar"] { background-color: #0A192F !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: #94A3B8 !important; }
    div.stButton > button:first-child { background-color: #0A192F !important; color: #FFFFFF !important; border-radius: 8px !important; }
    div.stButton > button:first-child:hover { background-color: #2563EB !important; color: #FFFFFF !important; }
    h1, h2, h3 { color: #0F172A !important; font-weight: 800 !important; }
</style>
""", unsafe_allow_html=True)

# --- 4. MENÚ LATERAL ---
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path): st.image(logo_path, use_container_width=True)
    else: st.markdown("<h2 style='text-align:center; color:white;'>GIO GROUP</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Inventario y Proveedores", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "box-seam-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        menu_icon="cast", default_index=1,
        styles={
            "container": {"background-color": "#0A192F"},
            "icon": {"color": "#94A3B8", "font-size": "16px"},
            "nav-link": {"font-size": "14px", "color": "#94A3B8", "--hover-color": "#112240"},
            "nav-link-selected": {"background-color": "#112240", "color": "#3B82F6", "font-weight": "bold", "border-left": "4px solid #3B82F6"}
        }
    )

# --- 5. PANEL SUPERIOR (Solo en Dashboard y Planillas) ---
if menu_seleccionado in ["Dashboard", "Planillas"]:
    with st.container():
        st.markdown("<h2 style='color:#0F172A; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)
        col_up1, col_up2 = st.columns([3, 1])
        with col_up1: archivo_subido = st.file_uploader("📥 Sincronizar reporte de ventas (PDF)", type=["pdf"])
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🧹 Limpiar Reporte PDF"):
                st.session_state["total_ingresos_pdf"] = 0.0
                st.session_state["periodo_texto"] = "1 Quincena (Por defecto)"
                st.session_state["detalle_extras"] = [] 
                for emp, info in st.session_state["empleados"].items():
                    st.session_state[f"com_{emp}"] = 0.0
                    st.session_state[f"extra_bruto_{emp}"] = 0.0
                    st.session_state[f"serv_tot_{emp}"] = 0.0
                st.rerun()

        if archivo_subido is not None:
            try:
                texto_completo = ""
                todas_las_filas = []
                with pdfplumber.open(archivo_subido) as pdf:
                    for page in pdf.pages:
                        texto_completo += (page.extract_text() or "") + " "
                        tabla = page.extract_table()
                        if tabla: todas_las_filas.extend(tabla)

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

                if header_idx != -1:
                    df_reporte = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
                    df_reporte.columns = df_reporte.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
                    c_prof = next((c for c in df_reporte.columns if 'PROFESIONAL' in c), None)
                    c_pre = next((c for c in df_reporte.columns if 'PRECIO' in c), None)
                    c_cli = next((c for c in df_reporte.columns if 'CLIENTE' in c), None)
                    c_ser = next((c for c in df_reporte.columns if 'SERVICIO' in c), None)

                    if c_prof and c_pre:
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
                        df_reporte['EXTRA'] = df_reporte.apply(lambda r: 0.0 if r['MARCA']=="Dr. Gio Molina" else max(0.0, float(r[c_pre])-60.0), axis=1)
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
                        st.success(f"✅ ¡PDF analizado con éxito!")
            except Exception as e: st.error(f"Error procesando PDF: {e}")
        st.info(f"📅 **Período en análisis:** {st.session_state['periodo_texto']}")
    st.markdown("<br>", unsafe_allow_html=True)

# --- 6. ENRUTAMIENTO DE PÁGINAS ---

if menu_seleccionado == "Dashboard":
    if st.session_state["total_ingresos_pdf"] > 0:
        costo_planilla = sum([round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] - (0.0 if "Porcentaje" in st.session_state.get(f"mod_{emp}", "") else round(st.session_state[f"base_{emp}"] * 0.10, 2)), 2) for emp in st.session_state["empleados"].keys()])
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos Totales", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Costo Operativo", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta", f"${st.session_state['total_ingresos_pdf'] - costo_planilla:,.2f}")
    else: st.info("Sube el PDF de ingresos para generar métricas.")

elif menu_seleccionado == "Planillas":
    if st.session_state.get("detalle_extras"):
        with st.expander("🔍 Ver Desglose Informativo: Servicios con Extra Generado", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state["detalle_extras"]).style.format({"Precio Final": "${:.2f}", "Extra Generado": "${:.2f}", "Retención (25%)": "${:.2f}", "Comisión Neta": "${:.2f}"}), use_container_width=True, hide_index=True)
    
    datos_emp = []
    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info.get('rol', '')})"):
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                val_base = st.number_input(f"Sueldo Base ($)", value=float(st.session_state[f"base_{emp}"]), key=f"ui_b_{emp}")
                st.session_state[f"base_{emp}"] = val_base
                st.session_state[f"com_{emp}"] = st.number_input(f"Comisiones ($)", value=float(st.session_state[f"com_{emp}"]), key=f"ui_c_{emp}")
            with c2:
                st.session_state[f"hex_{emp}"] = st.number_input(f"Bonos ($)", value=float(st.session_state[f"hex_{emp}"]), key=f"ui_h_{emp}")
                st.session_state[f"desc_{emp}"] = st.number_input(f"Descuentos ($)", value=float(st.session_state[f"desc_{emp}"]), key=f"ui_d_{emp}")
            with c3:
                n_desc = st.text_input(f"Notas", value="Ninguno", key=f"n_{emp}")
                st.session_state[f"email_{emp}"] = st.text_input(f"Correo", value=info.get("correo", ""), key=f"ui_e_{emp}")

            renta_calculada = 0.0 if "Porcentaje" in info.get("mod","") and info.get("rol","")=="Operativo" else round(st.session_state[f"base_{emp}"] * 0.10, 2)
            t_net = round(st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - renta_calculada - st.session_state[f"desc_{emp}"], 2)
            datos_emp.append({"Colaborador": emp, "Base": st.session_state[f"base_{emp}"], "Extra": st.session_state.get(f"extra_bruto_{emp}",0), "Ret Pub": st.session_state.get(f"ret_pub_{emp}",0), "Com Neta": st.session_state[f"com_{emp}"], "Bonos": st.session_state[f"hex_{emp}"], "Desc": st.session_state[f"desc_{emp}"], "Renta": renta_calculada, "Total": t_net, "Notas": n_desc, "Email": st.session_state[f"email_{emp}"], "DUI": info.get("dui", ""), "Cuenta": info.get("cuenta", "")})

    if datos_emp:
        st.dataframe(pd.DataFrame(datos_emp).drop(columns=["Notas", "Email", "DUI", "Cuenta"]).style.format("${:.2f}", subset=["Base", "Extra", "Ret Pub", "Com Neta", "Bonos", "Desc", "Renta", "Total"]), use_container_width=True, hide_index=True)

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
            if not notas_val or notas_val.lower() == 'ninguno': notas_val = "Sin notas adicionales"
            pdf.ln(6)
            pdf.set_font('helvetica', 'B', 10); pdf.set_text_color(10, 25, 47); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 7, "  Notas del Registro:", 0, 1, 'L', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, limpiar_texto_pdf(f"  {notas_val}"), 0, 'L')

            st.session_state['t_pdf'] = generar_pdf_bytes(pdf)
            st.session_state['t_path'] = f"Recibo_{e_sel.replace(' ','_')}.pdf"

        if 't_pdf' in st.session_state:
            st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")
            correo_ok = bool(e_dat["Email"]) and "@" in e_dat["Email"]
            if not correo_ok: st.warning("⚠️ Este colaborador no tiene un correo válido configurado.")

            if st.button("🚀 Enviar Recibo por Gmail", disabled=not correo_ok):
                try:
                    remitente = st.secrets["EMAIL_USER"]
                    password = st.secrets["EMAIL_PASS"]
                    destinatario = e_dat["Email"]

                    msg = MIMEMultipart()
                    msg['From'] = remitente; msg['To'] = destinatario
                    msg['Subject'] = f"Comprobante de Pago - Período: {st.session_state['periodo_texto']} | GIO GROUP"

                    cuerpo_correo = f"Estimado/a {e_dat['Colaborador']},\n\nAdjunto a este correo electrónico encontrará su Comprobante Oficial de Pago detallado.\n\nAtentamente,\nAdministración GIO GROUP SAS DE CV"
                    msg.attach(MIMEText(cuerpo_correo, 'plain'))
                    
                    parte_adjunta = MIMEApplication(st.session_state['t_pdf'], Name=st.session_state['t_path'])
                    parte_adjunta['Content-Disposition'] = f'attachment; filename="{st.session_state["t_path"]}"'
                    msg.attach(parte_adjunta)

                    servidor_smtp = smtplib.SMTP('smtp.gmail.com', 587)
                    servidor_smtp.starttls()
                    servidor_smtp.login(remitente, password)
                    servidor_smtp.sendmail(remitente, destinatario, msg.as_string())
                    servidor_smtp.quit()

                    st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": "Recibo de Pago", "Destinatario": e_sel})
                    st.success(f"¡Comprobante enviado exitosamente por Gmail a {destinatario}!")
                except Exception as ex: st.error(f"Error al enviar correo. Verifique secretos EMAIL_USER y EMAIL_PASS: {ex}")

# --- NUEVO MÓDULO: INVENTARIO Y PROVEEDORES ---
elif menu_seleccionado == "Inventario y Proveedores":
    st.markdown("<h2 style='color:#0F172A;'>📦 Gestión de Inventario y Proveedores</h2>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🤝 Directorio de Proveedores", "📦 Control de Inventario"])

    with tab2: # INVENTARIO
        st.info("Actualiza las cantidades y costos del inventario general de las clínicas.")
        df_inv = pd.DataFrame(st.session_state["inventario"])
        df_inv_edited = st.data_editor(df_inv, use_container_width=True, num_rows="dynamic")
        if st.button("💾 Guardar Inventario en la Nube"):
            st.session_state["inventario"] = df_inv_edited.to_dict("records")
            guardar_inventario(st.session_state["inventario"])
            st.success("Inventario actualizado correctamente.")

    with tab1: # PROVEEDORES
        col_lista, col_vista = st.columns([1, 2])
        nombres_provs = [p.get("Nombre_Proveedor", f"Prov {p.get('ID_Proveedor','')}") for p in st.session_state["proveedores"]]
        
        with col_lista:
            st.markdown("#### Selección de Proveedor")
            prov_seleccionado = st.selectbox("Elige un proveedor para ver su ficha:", nombres_provs)
            
            with st.expander("➕ Agregar / Editar Proveedores (Base de Datos)"):
                df_prov = pd.DataFrame(st.session_state["proveedores"])
                df_prov_edited = st.data_editor(df_prov, use_container_width=True, num_rows="dynamic")
                if st.button("💾 Guardar Cambios de Proveedores"):
                    st.session_state["proveedores"] = df_prov_edited.to_dict("records")
                    guardar_proveedores(st.session_state["proveedores"])
                    st.success("Base de proveedores actualizada.")
                    st.rerun()

        with col_vista:
            if prov_seleccionado:
                p_data = next((p for p in st.session_state["proveedores"] if p.get("Nombre_Proveedor") == prov_seleccionado), {})
                
                # HTML EXACTO AL REPORTE SOLICITADO
                ficha_html = f"""
                <div style="background-color: white; padding: 0px; border: 1px solid #B0C4DE; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
                    <div style="padding: 15px; border-bottom: 2px solid #B0C4DE;">
                        <h3 style="color: #2F5573; margin: 0; font-size: 18px; text-transform: uppercase;">Lista de Contactos de Proveedores</h3>
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                        <tr>
                            <td style="background-color: #2F5573; color: white; padding: 8px; font-weight: bold; width: 20%; border: 1px solid #FFF;">NOMBRE DEL PROVEEDOR</td>
                            <td style="background-color: #E8F0FE; padding: 8px; font-weight: bold; width: 30%; border: 1px solid #FFF; color:#333;">{p_data.get('Nombre_Proveedor', '')}</td>
                            <td style="background-color: #2F5573; color: white; padding: 8px; font-weight: bold; width: 20%; border: 1px solid #FFF;">VALORACIÓN GENERAL</td>
                            <td style="background-color: #F8F9FA; padding: 8px; text-align: center; font-weight: bold; width: 10%; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Valoracion', '')}</td>
                            <td style="background-color: #2F5573; color: white; padding: 8px; font-weight: bold; width: 15%; border: 1px solid #FFF;">ID DE PROVEEDOR</td>
                            <td style="background-color: #F8F9FA; padding: 8px; text-align: center; font-weight: bold; width: 5%; border: 1px solid #E5E7EB; color:#333;">{p_data.get('ID_Proveedor', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">NOMBRE DEL CONTACTO</td>
                            <td style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; color:#333;">{p_data.get('Nombre_Contacto', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE LA ÚLTIMA REVISIÓN</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Ultima_Rev', '')}</td>
                            <td colspan="2" style="background-color: #2F5573; color: white; padding: 8px; font-weight: bold; text-align: center; border: 1px solid #FFF;">DESCRIPCIÓN DEL PRODUCTO / SERVICIO</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">TELÉFONO</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; border: 1px solid #FFF;">{p_data.get('Telefono_1', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE LA PRÓXIMA REVISIÓN</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Prox_Rev', '')}</td>
                            <td colspan="2" rowspan="2" style="background-color: #F8F9FA; padding: 8px; border: 1px solid #E5E7EB; vertical-align: top; color:#333;">{p_data.get('Descripcion', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">CORREO ELECTRÓNICO</td>
                            <td style="background-color: #F8F9FA; color: orange; padding: 8px; border: 1px solid #FFF; font-weight: bold;">{p_data.get('Correo', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA CONTRATO FIRMADO</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Contrato', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">NOMBRE DE BANCO</td>
                            <td style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; color:#333;">{p_data.get('Banco', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE VENCIMIENTO DEL CONTRATO</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Vencimiento', '')}</td>
                            <td colspan="2" style="background-color: #2F5573; color: white; padding: 8px; font-weight: bold; text-align: center; border: 1px solid #FFF;">NOTAS</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">NUMERO DE CUENTA</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; border: 1px solid #FFF;">{p_data.get('Cuenta', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE LA CALIFICACIÓN DE RIESGO</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Calif_Riesgo', '')}</td>
                            <td colspan="2" rowspan="4" style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; vertical-align: top; color:#333;">{p_data.get('Notas', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">DIRECCIÓN</td>
                            <td style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; color:#333;">{p_data.get('Direccion_1', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE LA DILIGENCIA DEBIDA</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Diligencia', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">DIRECCIÓN</td>
                            <td style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; color:#333;">{p_data.get('Direccion_2', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE REVISIÓN DEL CONTRATO</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Rev_Contrato', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">PAÍS</td>
                            <td style="background-color: #E8F0FE; padding: 8px; border: 1px solid #FFF; color:#333;">{p_data.get('Pais', '')}</td>
                            <td style="background-color: #4A7B9D; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">FECHA DE APROBACIÓN</td>
                            <td style="background-color: #FFFFFF; padding: 8px; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Fecha_Aprobacion', '')}</td>
                        </tr>
                        <tr>
                            <td style="background-color: #7B8D9A; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">NOMBRE DEL PATROCINADOR</td>
                            <td style="background-color: #F8F9FA; padding: 8px; font-weight: bold; border: 1px solid #FFF; color:#333;">{p_data.get('Patrocinador', '')}</td>
                            <td style="background-color: #7B8D9A; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">TELÉFONO</td>
                            <td style="background-color: #F8F9FA; padding: 8px; font-weight: bold; border: 1px solid #E5E7EB; color:#333;">{p_data.get('Telefono_2', '')}</td>
                            <td style="background-color: #7B8D9A; color: white; padding: 8px; font-weight: bold; border: 1px solid #FFF;">CORREO ELECTRÓNICO</td>
                            <td style="background-color: #F8F9FA; color: orange; padding: 8px; border: 1px solid #E5E7EB; font-weight: bold;">{p_data.get('Correo', '')}</td>
                        </tr>
                    </table>
                </div>
                """
                st.markdown(ficha_html, unsafe_allow_html=True)


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

            st.session_state['temp_memo_pdf'] = generar_pdf_bytes(pdf_m)
            st.session_state['temp_memo_path'] = f"Memorandum_{emp_memo.replace(' ','_')}.pdf"
        else: st.info("Indica el contenido del memorándum.")

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
            pdf_a.cell(0, 10, limpiar_texto_pdf(f" Dirigido a: {emp_amon}"), 0, 1, 'L'); pdf_a.cell(0, 10, limpiar_texto_pdf(f" Tipo de Falta: {tipo_falta}"), 0, 1, 'L')
            pdf_a.set_font('helvetica', '', 11); pdf_a.multi_cell(0, 7, limpiar_texto_pdf(motivo_amon), 1, 'L')

            st.session_state['temp_amon_pdf'] = generar_pdf_bytes(pdf_a)
            st.session_state['temp_amon_path'] = f"Acta_Amonestacion_{emp_amon.replace(' ','_')}.pdf"
        else: st.info("Describe el incidente para poder redactar el acta formal.")

    if 'temp_amon_pdf' in st.session_state:
        st.download_button("📄 Descargar Acta Formal", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])

elif menu_seleccionado == "Auditoría":
    st.markdown("<h2 style='color:#0F172A;'>🖨️ Registro y Control de Auditoría</h2>", unsafe_allow_html=True)
    if st.session_state["historial_auditoria"]: st.dataframe(pd.DataFrame(st.session_state["historial_auditoria"]), use_container_width=True)
    else: st.info("El registro está limpio.")

elif menu_seleccionado == "Configuración":
    st.markdown("<h2 style='color:#0F172A;'>⚙️ Configuración del Sistema (Admin)</h2>", unsafe_allow_html=True)
    st.markdown("### 📇 Base de Datos del Personal (Sincronizada con Google Sheets)")
    
    try:
        _ = st.secrets["gcp_service_account"]
        st.success("✅ Sistema conectado exitosamente a Google Sheets.")
    except Exception:
        st.warning("⚠️ **MODO LOCAL ACTIVADO:** No se detectan credenciales de Google Cloud.")
    
    df_emp_db = pd.DataFrame.from_dict(st.session_state["empleados"], orient="index")
    df_edited = st.data_editor(df_emp_db, use_container_width=True, disabled=["rol", "alias", "mod", "porc"])
    
    if st.button("💾 Guardar Cambios de Personal"):
        st.session_state["empleados"] = df_edited.to_dict(orient="index")
        guardar_empleados(st.session_state["empleados"])
        st.success("¡Base de personal actualizada!")
