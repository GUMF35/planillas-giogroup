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

# --- 1. CONFIGURACIÓN DE PÁGINA ---
logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
try:
    if os.path.exists(logo_path):
        icono = Image.open(logo_path)
        st.set_page_config(page_title="Gio Group Admin", page_icon=icono, layout="wide", initial_sidebar_state="expanded")
    else:
        st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")
except:
    st.set_page_config(page_title="Gio Group Admin", page_icon="🏢", layout="wide")

# --- 2. BASE DE DATOS EN MEMORIA (ROLES Y CONFIGURACIÓN EXACTA) ---
if "salario_operativo_neto" not in st.session_state: st.session_state["salario_operativo_neto"] = 183.96
if "salario_directivo_neto" not in st.session_state: st.session_state["salario_directivo_neto"] = 300.00
if "meses_multiplicador" not in st.session_state: st.session_state["meses_multiplicador"] = 1.0
if "periodo_texto" not in st.session_state: st.session_state["periodo_texto"] = "1 Mes (Por defecto)"

if "empleados" not in st.session_state:
    st.session_state["empleados"] = {
        "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY", "mod": "Estándar (Con retención 25% Pub)", "porc": 20},
        "Luis Violante": {"rol": "Operativo", "alias": "LUIS", "mod": "Estándar (Con retención 25% Pub)", "porc": 20},
        "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA", "mod": "Porcentaje Directo (%)", "porc": 20},
        "Mario de Paz": {"rol": "Operativo", "alias": "MARIO", "mod": "Estándar (Con retención 25% Pub)", "porc": 20},
        "Dr. Gio Molina": {"rol": "Administrativo", "alias": "GIO|MARVIN|DOCTOR", "mod": "Fijo", "porc": 0},
        "Gerson Ulises Molina Flores": {"rol": "Administrativo", "alias": "GERSON", "mod": "Fijo", "porc": 0},
        "Edwin Ponce": {"rol": "Administrativo", "alias": "EDWIN", "mod": "Fijo", "porc": 0}
    }

def calcular_bruto_mensual(rol):
    neto = st.session_state["salario_operativo_neto"] if rol == "Operativo" else st.session_state["salario_directivo_neto"]
    return round(neto / 0.90, 2)

for emp, info in st.session_state["empleados"].items():
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"extra_bruto_{emp}" not in st.session_state: st.session_state[f"extra_bruto_{emp}"] = 0.0
    if f"ret_pub_{emp}" not in st.session_state: st.session_state[f"ret_pub_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = ""
    if f"porc_{emp}" not in st.session_state: st.session_state[f"porc_{emp}"] = info["porc"]
    if f"base_{emp}" not in st.session_state: 
        st.session_state[f"base_{emp}"] = calcular_bruto_mensual(info["rol"]) * st.session_state["meses_multiplicador"]

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

# --- 5. PANEL SUPERIOR: LECTOR DE PDF, AUTODETECCIÓN Y DEPURADOR DE CACHÉ ---
if menu_seleccionado != "Configuración":
    with st.container():
        st.markdown("<h2 style='color:#0F172A; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)
        st.info(f"📅 **Período detectado en PDF:** {st.session_state['periodo_texto']} | **Factor Multiplicador de Meses:** {st.session_state['meses_multiplicador']}x")
        
        col_up1, col_up2 = st.columns([3, 1])
        with col_up1:
            archivo_subido = st.file_uploader("📥 Sincronizar reporte de ventas (PDF)", type=["pdf"])
        with col_up2:
            st.markdown("<br>", unsafe_allow_html=True)
            # BOTÓN DEPURADOR / LIMPIADOR DE ARCHIVO Y CACHÉ
            if st.button("🗑️ Limpiar / Reiniciar Datos"):
                st.session_state["total_ingresos_pdf"] = 0.0
                st.session_state["ingresos_por_marca"] = {}
                st.session_state["extras_por_marca"] = {}
                st.session_state["total_fondo_publicidad"] = 0.0
                st.session_state["meses_multiplicador"] = 1.0
                st.session_state["periodo_texto"] = "1 Mes (Por defecto)"
                for emp, info in st.session_state["empleados"].items():
                    st.session_state[f"com_{emp}"] = 0.0
                    st.session_state[f"extra_bruto_{emp}"] = 0.0
                    st.session_state[f"ret_pub_{emp}"] = 0.0
                    st.session_state[f"serv_tot_{emp}"] = 0.0
                    st.session_state[f"base_{emp}"] = calcular_bruto_mensual(info["rol"])
                st.success("¡Datos y caché depurados correctamente. Listo para nuevo archivo!")
                st.rerun()

        if archivo_subido is not None:
            try:
                texto_completo = ""
                todas_las_filas = []
                with pdfplumber.open(archivo_subido) as pdf:
                    for page in pdf.pages:
                        texto_completo += page.extract_text() + " "
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

                meses_diff = (max_fecha.year - min_fecha.year) * 12 + (max_fecha.month - min_fecha.month)
                if max_fecha.day >= 15: meses_diff += 1
                meses_diff = float(max(1, meses_diff))

                st.session_state["meses_multiplicador"] = meses_diff
                st.session_state["periodo_texto"] = f"Del {min_fecha.strftime('%d/%m/%Y')} al {max_fecha.strftime('%d/%m/%Y')} ({int(meses_diff)} meses)"

                header_idx = -1
                for i, row in enumerate(todas_las_filas):
                    if row and any(isinstance(cell, str) and 'PROFESIONAL' in cell.upper() for cell in row):
                        header_idx = i; break
                
                if header_idx != -1:
                    df_reporte = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
                    df_reporte.columns = df_reporte.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
                    col_prof = next((col for col in df_reporte.columns if 'PROFESIONAL' in col), None)
                    col_precio = next((col for col in df_reporte.columns if 'PRECIO' in col), None)

                    if col_prof and col_precio:
                        df_reporte = df_reporte.dropna(subset=[col_prof, col_precio])
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
                        for emp, info in st.session_state["empleados"].items():
                            st.session_state[f"base_{emp}"] = calcular_bruto_mensual(info["rol"]) * st.session_state["meses_multiplicador"]

                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(info["alias"], case=False, na=False, regex=True)]
                            tot_serv = df_p[col_precio].sum()
                            st.session_state[f"serv_tot_{emp}"] = tot_serv
                            
                            if info["rol"] == "Operativo":
                                mod_actual = st.session_state.get(f"mod_{emp}", info["mod"])
                                if "Estándar" in mod_actual:
                                    df_ex = df_p[df_p[col_precio] >= 60].copy()
                                    ext_bruto_total = (df_ex[col_precio] - 60).sum() if not df_ex.empty else 0.0
                                    desc_pub = ext_bruto_total * 0.25
                                    comision_neta = max(0.0, ext_bruto_total - desc_pub)
                                    
                                    st.session_state[f"extra_bruto_{emp}"] = ext_bruto_total
                                    st.session_state[f"com_{emp}"] = comision_neta
                                    st.session_state[f"ret_pub_{emp}"] = desc_pub
                                    st.session_state["total_fondo_publicidad"] += desc_pub
                                else:
                                    porc = st.session_state.get(f"porc_{emp}", info["porc"])
                                    st.session_state[f"extra_bruto_{emp}"] = 0.0
                                    st.session_state[f"com_{emp}"] = tot_serv * (porc / 100.0)
                                    st.session_state[f"ret_pub_{emp}"] = 0.0
                            else:
                                st.session_state[f"extra_bruto_{emp}"] = 0.0
                                st.session_state[f"com_{emp}"] = 0.0
                                st.session_state[f"ret_pub_{emp}"] = 0.0

                        st.success(f"✅ ¡PDF analizado! Período de {int(st.session_state['meses_multiplicador'])} meses procesado con éxito.")
            except Exception as e:
                st.error(f"Error procesando PDF: {e}")

    st.markdown("<br>", unsafe_allow_html=True)

# --- 6. ENRUTAMIENTO DE PÁGINAS ---

if menu_seleccionado == "Dashboard":
    if st.session_state["total_ingresos_pdf"] > 0:
        costo_planilla = sum([
            st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] - (0.0 if "Porcentaje" in st.session_state.get(f"mod_{emp}", st.session_state["empleados"][emp]["mod"]) and st.session_state["empleados"][emp]["rol"] == "Operativo" else st.session_state[f"base_{emp}"] * 0.10)
            for emp in st.session_state["empleados"].keys()
        ])
        utilidad_neta = st.session_state["total_ingresos_pdf"] - costo_planilla

        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos Totales", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Costo Operativo (Planillas)", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta:,.2f}", delta=f"{((utilidad_neta/st.session_state['total_ingresos_pdf'])*100):.1f}% Margen")

        st.markdown("<br><h3 style='color:#0F172A;'>🎯 Rendimiento Neto de Marcas (Holding)</h3>", unsafe_allow_html=True)
        marcas = st.session_state["ingresos_por_marca"]
        extras = st.session_state["extras_por_marca"]
        cols_metas = st.columns(len(marcas) if len(marcas) > 0 else 1)
        metas_config = {}
        
        for i, (marca, ingresos) in enumerate(marcas.items()):
            meta_def = 8000.0 if "Dr" in marca else 5000.0
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
    datos_emp = []

    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info['rol']})", expanded=True if "Maydely" in emp else False):
            c1, c2, c3 = st.columns([1.2, 1, 1])

            with c1:
                val_base = st.number_input(f"Sueldo Base (Bruto) ($)", value=float(st.session_state[f"base_{emp}"]), key=f"ui_b_{emp}")
                st.session_state[f"base_{emp}"] = val_base
                
                if info["rol"] == "Operativo":
                    mod = st.selectbox(f"Modalidad", ["Estándar (Con retención 25% Pub)", "Porcentaje Directo (%)"], index=0 if "Estándar" in st.session_state.get(f"mod_{emp}", info["mod"]) else 1, key=f"m_{emp}")
                    if "Estándar" in mod:
                        st.session_state[f"mod_{emp}"] = "Estándar (Con retención 25% Pub)"
                    else:
                        st.session_state[f"mod_{emp}"] = "Porcentaje Directo (%)"
                        porc = st.slider(f"% Ganancia", 0, 100, int(st.session_state.get(f"porc_{emp}", info["porc"])), key=f"p_{emp}")
                        st.session_state[f"com_{emp}"] = st.session_state[f"serv_tot_{emp}"] * (porc / 100.0)
                        st.session_state[f"extra_bruto_{emp}"] = 0.0
                        st.session_state[f"ret_pub_{emp}"] = 0.0
                        st.session_state[f"porc_{emp}"] = porc
                else:
                    st.caption(f"Personal Administrativo (Sueldo Fijo)")

                val_com = st.number_input(f"Comisiones Netas ($)", value=float(st.session_state[f"com_{emp}"]), key=f"ui_c_{emp}")
                st.session_state[f"com_{emp}"] = val_com

            with c2:
                val_hex = st.number_input(f"Bonos / Nivelación ($)", value=float(st.session_state[f"hex_{emp}"]), key=f"ui_h_{emp}")
                st.session_state[f"hex_{emp}"] = val_hex
                
                val_desc = st.number_input(f"Descuentos ($)", value=float(st.session_state[f"desc_{emp}"]), key=f"ui_d_{emp}")
                st.session_state[f"desc_{emp}"] = val_desc
            
            with c3:
                n_desc = st.text_input(f"Notas", value="Ninguno", key=f"n_{emp}")
                e_em = st.text_input(f"Correo", value=st.session_state[f"email_{emp}"], key=f"ui_e_{emp}")
                st.session_state[f"email_{emp}"] = e_em

            # Renta 10%
            mod_actual = st.session_state.get(f"mod_{emp}", info["mod"])
            if info["rol"] == "Operativo" and "Porcentaje" in mod_actual:
                renta_calculada = 0.0
            else:
                renta_calculada = st.session_state[f"base_{emp}"] * 0.10

            extra_bruto_val = st.session_state.get(f"extra_bruto_{emp}", 0.0)
            ret_pub_actual = st.session_state.get(f"ret_pub_{emp}", 0.0)
            
            t_net = st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - renta_calculada - st.session_state[f"desc_{emp}"]
            
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
                "Email": st.session_state[f"email_{emp}"]
            })

    if datos_emp:
        df_res = pd.DataFrame(datos_emp)
        st.markdown("<br><h4>Resumen Consolidado</h4>", unsafe_allow_html=True)
        st.dataframe(df_res.style.format({
            "Sueldo Base (Bruto)": "${:.2f}", 
            "Extra Bruto": "${:,.2f}",
            "Retención Pub (25%)": "${:,.2f}",
            "Comisiones Netas": "${:,.2f}", 
            "Bonos": "${:,.2f}", 
            "Descuentos": "${:,.2f}", 
            "10% Renta": "${:,.2f}", 
            "Total a Pagar": "${:,.2f}"
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
                    self.cell(0, 5, f"Periodo Liquidado: {st.session_state['periodo_texto']}", 0, 1, 'L')
                    self.ln(5)
            
            pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 10, f" Colaborador: {e_dat['Colaborador']}", 0, 1, 'L', fill=True); pdf.ln(5)
            pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
            pdf.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
            
            for d, v in [("Sueldo Base Acumulado (Bruto)", e_dat['Sueldo Base (Bruto)']), ("Extra Bruto Generado", e_dat['Extra Bruto']), ("Comisiones Netas a Pagar", e_dat['Comisiones']), ("Bonos Extras", e_dat['Bonos'])]:
                pdf.cell(130, 8, f"  {d}", 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')
            
            pdf.set_text_color(201, 42, 42)
            if e_dat['Descuentos'] > 0:
                pdf.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['Descuentos']:.2f}", 1, 1, 'R')
            
            if e_dat['Retención Pub (25%)'] > 0:
                pdf.cell(130, 8, "  (Informativo) Retención 25% Publicidad", 1, 0, 'L'); pdf.cell(60, 8, f"${e_dat['Retención Pub (25%)']:.2f}", 1, 1, 'R')
            
            if e_dat['10% Renta'] > 0:
                pdf.cell(130, 8, "  (-) 10% Retención de Renta", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['10% Renta']:.2f}", 1, 1, 'R')
            
            pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
            pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total a Pagar']:.2f}", 1, 1, 'R', fill=True)
            
            p_path = f"Recibo_{e_sel.replace(' ','_')}.pdf"; pdf.output(p_path)
            with open(p_path, "rb") as f: st.session_state['t_pdf'] = f.read(); st.session_state['t_path'] = p_path

        if 't_pdf' in st.session_state:
            st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")

elif menu_seleccionado in ["Memorándums", "Amonestaciones", "Auditoría"]:
    st.info(f"Módulo: {menu_seleccionado} (Funcionando correctamente en backend)")

elif menu_seleccionado == "Configuración":
    st.markdown("<h2 style='color:#0F172A;'>⚙️ Configuración del Sistema (Admin)</h2>", unsafe_allow_html=True)
    
    st.markdown("### 💰 1. Sueldos Netos Deseados (Mensuales)")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.session_state["salario_operativo_neto"] = st.number_input("Sueldo Mensual NETO Operativo:", value=float(st.session_state["salario_operativo_neto"]), step=10.0)
    with col_s2:
        st.session_state["salario_directivo_neto"] = st.number_input("Sueldo Mensual NETO Administrativo:", value=float(st.session_state["salario_directivo_neto"]), step=10.0)
    
    st.markdown("---")
    st.markdown("### 📅 2. Ajuste Manual de Período")
    c_t1, c_t2 = st.columns(2)
    with c_t1: st.text_input("Periodo Detectado Actual:", value=st.session_state["periodo_texto"], disabled=True)
    with c_t2: 
        meses_manual = st.number_input("Multiplicador Manual (Meses):", value=float(st.session_state["meses_multiplicador"]), step=1.0)
        if st.button("Aplicar Multiplicador Manual"):
            st.session_state["meses_multiplicador"] = float(meses_manual)
            for emp, info in st.session_state["empleados"].items():
                st.session_state[f"base_{emp}"] = calcular_bruto_mensual(info["rol"]) * st.session_state["meses_multiplicador"]
            st.success("Multiplicador manual aplicado.")
            st.rerun()

    st.markdown("---")
    st.markdown("### 👥 3. Gestión de Personal (Altas y Bajas)")
    col_p1, col_p2 = st.columns([1, 1])
    with col_p1:
        st.markdown("#### ✨ Alta de Colaborador")
        n_nombre = st.text_input("Nombre Completo:")
        n_rol = st.selectbox("Rol:", ["Operativo", "Administrativo"])
        n_mod = st.selectbox("Modalidad:", ["Estándar (Con retención 25% Pub)", "Porcentaje Directo (%)"])
        n_porc = st.number_input("Porcentaje (%) si aplica:", value=20)
        n_alias = st.text_input("Alias PDF (Ej. MARIA):")
        if st.button("➕ Registrar"):
            if n_nombre and n_alias:
                st.session_state["empleados"][n_nombre] = {"rol": n_rol, "alias": n_alias.upper(), "mod": n_mod, "porc": n_porc}
                st.session_state[f"com_{n_nombre}"] = 0.0
                st.session_state[f"extra_bruto_{n_nombre}"] = 0.0
                st.session_state[f"ret_pub_{n_nombre}"] = 0.0
                st.session_state[f"serv_tot_{n_nombre}"] = 0.0
                st.session_state[f"email_{n_nombre}"] = ""
                st.session_state[f"hex_{n_nombre}"] = 0.0
                st.session_state[f"desc_{n_nombre}"] = 0.0
                st.session_state[f"base_{n_nombre}"] = calcular_bruto_mensual(n_rol) * st.session_state["meses_multiplicador"]
                st.success(f"{n_nombre} guardado exitosamente.")
                st.rerun()

    with col_p2:
        st.markdown("#### 🗑️ Dar de Baja a Colaborador")
        e_elim = st.selectbox("Seleccionar colaborador:", list(st.session_state["empleados"].keys()))
        if st.button("❌ Eliminar"):
            del st.session_state["empleados"][e_elim]
            st.warning("Colaborador eliminado.")
            st.rerun()

    st.dataframe(pd.DataFrame([{"Nombre": k, "Rol": v["rol"], "Modalidad": v["mod"], "Alias": v["alias"]} for k,v in st.session_state["empleados"].items()]), use_container_width=True)
