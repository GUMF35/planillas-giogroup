import streamlit as st
import pandas as pd
import io
import os
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

# --- 2. BASE DE DATOS EN MEMORIA (EMPLEADOS Y SALARIOS) ---
if "salario_operativo" not in st.session_state:
    st.session_state["salario_operativo"] = 183.96
if "salario_directivo" not in st.session_state:
    st.session_state["salario_directivo"] = 300.00

if "empleados" not in st.session_state:
    st.session_state["empleados"] = {
        "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY"},
        "Luis Violante": {"rol": "Operativo", "alias": "LUIS"},
        "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA"},
        "Dr. Gio Molina": {"rol": "Directivo", "alias": "GIO|MARVIN|DOCTOR"},
        "Gerson Ulises Molina Flores": {"rol": "Directivo", "alias": "GERSON"},
        "Edwin Ponce": {"rol": "Directivo", "alias": "EDWIN"},
        "Mario de Paz": {"rol": "Directivo", "alias": "MARIO"}
    }

# Inicializar variables para todos los empleados activos
for emp in st.session_state["empleados"].keys():
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = ""
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0

if "historial_auditoria" not in st.session_state: st.session_state["historial_auditoria"] = []
if "ingresos_por_marca" not in st.session_state: st.session_state["ingresos_por_marca"] = {}
if "total_ingresos_pdf" not in st.session_state: st.session_state["total_ingresos_pdf"] = 0.0

# --- 3. CSS AVANZADO: TEMA "AZUL MARINO CORPORATIVO" + LIMPIEZA VISUAL ---
estilo_azul = """
<style>
    /* OCULTAR ELEMENTOS MOLESTOS (HEADER, FOOTER, MANAGE APP, FLECHAS SIDEBAR) */
    [data-testid="stHeader"] {display: none !important;}
    footer {display: none !important;}
    .viewerBadge_container, .stDeployButton, #Manage-app {display: none !important;}
    [data-testid="stSidebarCollapseButton"] {display: none !important;}
    
    /* Fondo Global de la App */
    .stApp {
        background-color: #F3F4F6 !important;
    }
    
    /* WIDGETS Y TARJETAS BLANCAS (Glassmorphism) */
    [data-testid="stMetric"], div[data-testid="metric-container"], .stDataFrame, [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.04) !important;
        border: 1px solid #E5E7EB !important;
    }
    
    /* Acento Azul Rey en las Tarjetas de Métricas */
    [data-testid="stMetric"] {
        border-bottom: 4px solid #2563EB !important; 
    }
    [data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #0F172A !important;
        font-weight: 800 !important;
        font-size: 1.8rem !important;
    }

    /* FORZAR SIDEBAR A AZUL MARINO PROFUNDO */
    [data-testid="stSidebar"] {
        background-color: #0A192F !important;
        border-right: none !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #94A3B8 !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }

    /* Diseño de Botones Principales */
    div.stButton > button:first-child {
        background-color: #0A192F !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: bold !important;
        padding: 0.6rem 1.2rem !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #2563EB !important; /* Acento Azul Rey */
        color: #FFFFFF !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
    }
    
    /* Títulos limpios */
    h1, h2, h3 {
        color: #0F172A !important;
        font-weight: 800 !important;
    }
    
    /* Inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
        background-color: #F8FAFC !important;
        border-radius: 8px !important;
        border: 1px solid #CBD5E1 !important;
        color: #0F172A !important;
    }
</style>
"""
st.markdown(estilo_azul, unsafe_allow_html=True)

# --- 4. MENÚ LATERAL INTERACTIVO (AZUL MARINO) ---
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
    else:
        st.markdown("<h2 style='text-align:center; color:white;'>GIO GROUP</h2>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#0A192F"},
            "icon": {"color": "#94A3B8", "font-size": "16px"}, 
            "nav-link": {
                "font-size": "14px", 
                "text-align": "left", 
                "margin":"4px 0px", 
                "padding": "10px 15px",
                "color": "#94A3B8", 
                "border-radius": "0px",
                "--hover-color": "#112240"
            },
            "nav-link-selected": {
                "background-color": "#112240", 
                "color": "#3B82F6", 
                "font-weight": "bold",
                "border-left": "4px solid #3B82F6"
            },
            "menu-title": {"color": "#475569", "font-size": "11px", "font-weight": "bold", "letter-spacing": "1px", "padding-left": "15px"}
        }
    )

# --- 5. PANEL SUPERIOR: LECTOR DE PDF ---
if menu_seleccionado != "Configuración":
    with st.container():
        st.markdown("<h2 style='color:#0F172A; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)
        archivo_subido = st.file_uploader("📥 Sincronizar reporte de ventas (PDF)", type=["pdf"])

        if archivo_subido is not None:
            try:
                todas_las_filas = []
                with pdfplumber.open(archivo_subido) as pdf:
                    for page in pdf.pages:
                        tabla = page.extract_table()
                        if tabla: todas_las_filas.extend(tabla)
                
                header_idx = -1
                for i, row in enumerate(todas_las_filas):
                    if row and any(isinstance(cell, str) and 'PROFESIONAL' in cell.upper() for cell in row):
                        header_idx = i
                        break
                
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
                            if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
                            if "LUIS" in p: return "Relájate Man"
                            if "GIO" in p or "MARVIN" in p or "DOCTOR" in p: return "Dr. Gio Molina"
                            return "Relájate Clinic"

                        df_reporte['MARCA'] = df_reporte[col_prof].apply(asignar_marca)
                        st.session_state["ingresos_por_marca"] = df_reporte.groupby('MARCA')[col_precio].sum().to_dict()

                        def procesar_empleado(clave):
                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(clave, case=False, na=False, regex=True)]
                            tot_serv = df_p[col_precio].sum()
                            df_ex = df_p[df_p[col_precio] >= 60].copy()
                            df_ex['EXT'] = df_ex[col_precio] - 60
                            desc_pub = df_ex['EXT'].sum() * 0.25
                            neto_est = max(0.0, df_ex['EXT'].sum() - desc_pub)
                            return neto_est, desc_pub, tot_serv

                        for emp, datos in st.session_state["empleados"].items():
                            est_val, d_pub, tot_val = procesar_empleado(datos["alias"])
                            st.session_state[f"serv_tot_{emp}"] = tot_val
                            
                            if datos["rol"] == "Operativo":
                                mod = st.session_state.get(f"mod_{emp}", "Estándar")
                                st.session_state[f"com_{emp}"] = est_val if "Estándar" in mod else tot_val * (st.session_state.get(f"porc_{emp}", 20) / 100.0)
                            else:
                                st.session_state[f"com_{emp}"] = 0.0

                        st.success("✅ Sincronización exitosa. Los datos se han actualizado en todos los módulos.")
            except Exception as e:
                st.error(f"Error al leer el documento PDF: {e}")

    st.markdown("<br>", unsafe_allow_html=True)

# --- 6. ENRUTAMIENTO DE PÁGINAS ---

if menu_seleccionado == "Dashboard":
    meta_minima = 300.0 # Meta base estándar
    
    if st.session_state["total_ingresos_pdf"] > 0:
        # Calcular nómina sumando la base correspondiente al rol de cada empleado activo
        costo_planilla = sum([
            (st.session_state["salario_operativo"] if st.session_state["empleados"][emp]["rol"] == "Operativo" else st.session_state["salario_directivo"]) 
            + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] 
            for emp in st.session_state["empleados"].keys()
        ])
        utilidad_neta = st.session_state["total_ingresos_pdf"] - costo_planilla

        # KPIs Corporativos
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos Totales", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Costo Operativo (Planillas)", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta:,.2f}", delta=f"{((utilidad_neta/st.session_state['total_ingresos_pdf'])*100):.1f}% Margen" if st.session_state['total_ingresos_pdf'] > 0 else "")

        st.markdown("<br><h3 style='color:#0F172A;'>🎯 Rendimiento de Marcas (Holding)</h3>", unsafe_allow_html=True)
        marcas = st.session_state["ingresos_por_marca"]
        cols_metas = st.columns(len(marcas) if len(marcas) > 0 else 1)
        metas_config = {}
        
        for i, (marca, ingresos) in enumerate(marcas.items()):
            meta_def = 8000.0 if "Dr" in marca else 5000.0
            metas_config[marca] = cols_metas[i].number_input(f"Meta: {marca}", value=meta_def, step=500.0, key=f"meta_{marca}")

        df_marcas = pd.DataFrame([{"Empresa/Marca": m, "Ingresos Generados": ing, "Meta Asignada": metas_config[m], "Estado": "✅ Alcanzada" if ing >= metas_config[m] else "⚠️ Pendiente"} for m, ing in marcas.items()])
        
        c_chart, c_table = st.columns([2, 1])
        with c_chart: st.bar_chart(pd.DataFrame.from_dict(marcas, orient='index', columns=['Ingresos ($)']))
        with c_table: st.dataframe(df_marcas.style.format({"Ingresos Generados": "${:,.2f}", "Meta Asignada": "${:,.2f}"}), hide_index=True)

        st.markdown("<br><h3 style='color:#0F172A;'>⭐ Rendimiento del Personal Activo</h3>", unsafe_allow_html=True)
        metricas = [{"Colaborador": e, "Rol": st.session_state["empleados"][e]["rol"], "Total Generado ($)": st.session_state[f"serv_tot_{e}"], "Estado": "✅ Cumple" if st.session_state[f"serv_tot_{e}"] >= meta_minima else "En progreso"} for e in st.session_state["empleados"].keys()]
        st.dataframe(pd.DataFrame(metricas).style.format({"Total Generado ($)": "{:,.2f}"}), use_container_width=True, hide_index=True)

    else:
        st.info("Sube un reporte PDF en la parte superior para visualizar las métricas y los gráficos del sistema.")

elif menu_seleccionado == "Planillas":
    st.markdown("<h2 style='color:#0F172A;'>Control Financiero de Planillas</h2>", unsafe_allow_html=True)
    datos_emp = []

    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info['rol']})"):
            c1, c2, c3 = st.columns(3)
            mod_str = "Estándar"
            
            sueldo_base_defecto = st.session_state["salario_operativo"] if info["rol"] == "Operativo" else st.session_state["salario_directivo"]

            with c1:
                base_emp = st.number_input(f"Sueldo Base ($) [{emp}]", value=float(sueldo_base_defecto), key=f"in_b_{emp}")
                
                if info["rol"] == "Operativo":
                    mod = st.selectbox(f"Modalidad de Pago [{emp}]", ["Estándar (Con retención)", "Porcentaje Directo (%)"], key=f"m_{emp}")
                    if "Estándar" in mod: mod_str = "Estándar"
                    else:
                        mod_str = "Porcentaje Directo"
                        st.session_state[f"com_{emp}"] = st.session_state[f"serv_tot_{emp}"] * (st.slider(f"Porcentaje Ganancia (%) [{emp}]", 0, 100, 20, key=f"p_{emp}") / 100.0)
                else:
                    mod_str = "Directivo/Fijo"
                    st.caption(f"Ingresos brutos aportados: ${st.session_state[f'serv_tot_{emp}']:.2f}")

                st.session_state[f"com_{emp}"] = st.number_input(f"Comisiones Generadas ($) [{emp}]", value=float(st.session_state[f"com_{emp}"]), key=f"in_c_{emp}")

            with c2:
                st.session_state[f"hex_{emp}"] = st.number_input(f"Bonos o Nivelación ($) [{emp}]", value=float(st.session_state[f"hex_{emp}"]), key=f"in_h_{emp}")
                st.session_state[f"desc_{emp}"] = st.number_input(f"Descuentos Aplicados ($) [{emp}]", value=float(st.session_state[f"desc_{emp}"]), key=f"in_d_{emp}")
            
            with c3:
                n_desc = st.text_input(f"Motivo Descuento/Bono [{emp}]", value="Ninguno", key=f"n_{emp}")
                st.session_state[f"email_{emp}"] = st.text_input(f"Correo Electrónico [{emp}]", value=st.session_state[f"email_{emp}"], key=f"in_e_{emp}")

            t_net = base_emp + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"]
            datos_emp.append({"Colaborador": emp, "Rol": info["rol"], "Sueldo Base": base_emp, "Comisiones": st.session_state[f"com_{emp}"], "Bonos": st.session_state[f"hex_{emp}"], "Total a Pagar": t_net, "Email": st.session_state[f"email_{emp}"]})

    if datos_emp:
        df_res = pd.DataFrame(datos_emp)
        st.markdown("<br><h4>Resumen Consolidado</h4>", unsafe_allow_html=True)
        st.dataframe(df_res.style.format({"Sueldo Base": "${:.2f}", "Comisiones": "${:.2f}", "Bonos": "${:.2f}", "Total a Pagar": "${:.2f}"}), use_container_width=True, hide_index=True)

        out_ex = io.BytesIO()
        with pd.ExcelWriter(out_ex, engine='openpyxl') as w: df_res.to_excel(w, index=False)
        out_ex.seek(0)
        st.download_button("📥 Exportar Reporte de Planilla (Excel)", data=out_ex, file_name="Reporte_Planilla.xlsx")

        st.markdown("---")
        st.markdown("<h3>Gestión y Envío de Recibos de Pago</h3>", unsafe_allow_html=True)
        e_sel = st.selectbox("Seleccionar Colaborador:", list(st.session_state["empleados"].keys()))
        e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)

        if st.button("👁️ Visualizar y Generar Recibo (PDF)"):
            class PDF(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    if os.path.exists(logo_path): self.set_x(40)
                    self.set_font('helvetica', '', 10); self.set_text_color(100, 100, 100); self.cell(0, 5, 'Comprobante Oficial de Pago', 0, 1, 'L'); self.ln(10)
            
            pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 10, f" Colaborador: {e_dat['Colaborador']}", 0, 1, 'L', fill=True); pdf.ln(5)
            pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
            pdf.cell(130, 8, ' Concepto / Descripción', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
            
            for d, v in [("Sueldo Base", e_dat['Sueldo Base']), ("Comisiones por Servicios", e_dat['Comisiones']), ("Bonos de Productividad", e_dat['Bonos'])]:
                pdf.cell(130, 8, f"  {d}", 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')
            
            pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
            pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total a Pagar']:.2f}", 1, 1, 'R', fill=True)
            
            p_path = f"Recibo_Pago_{e_sel.replace(' ','_')}.pdf"; pdf.output(p_path)
            with open(p_path, "rb") as f: st.session_state['t_pdf'] = f.read(); st.session_state['t_path'] = p_path

        if 't_pdf' in st.session_state:
            st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")

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
            pdf_m.cell(0, 10, f" Entregado a: {emp_memo}", 0, 1, 'L'); pdf_m.cell(0, 10, f" Asunto Central: {asunto_memo}", 0, 1, 'L')
            pdf_m.set_font('helvetica', '', 11); pdf_m.multi_cell(0, 7, texto_memo, 0, 'L')
            m_path = f"Memorandum_{emp_memo.replace(' ','_')}.pdf"; pdf_m.output(m_path)
            with open(m_path, "rb") as f: st.session_state['temp_memo_pdf'] = f.read(); st.session_state['temp_memo_path'] = m_path

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
            pdf_a.cell(0, 10, f" Dirigido a: {emp_amon}", 0, 1, 'L'); pdf_a.multi_cell(0, 7, motivo_amon, 1, 'L')
            a_path = f"Acta_Amonestacion_{emp_amon.replace(' ','_')}.pdf"; pdf_a.output(a_path)
            with open(a_path, "rb") as f: st.session_state['temp_amon_pdf'] = f.read(); st.session_state['temp_amon_path'] = a_path

    if 'temp_amon_pdf' in st.session_state:
        st.download_button("📄 Descargar Acta Formal", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])

elif menu_seleccionado == "Auditoría":
    st.markdown("<h2 style='color:#0F172A;'>🖨️ Registro y Control de Auditoría</h2>", unsafe_allow_html=True)
    if st.session_state["historial_auditoria"]:
        st.dataframe(pd.DataFrame(st.session_state["historial_auditoria"]), use_container_width=True)
    else:
        st.info("El registro está limpio. No se han detectado acciones recientes.")

elif menu_seleccionado == "Configuración":
    st.markdown("<h2 style='color:#0F172A;'>⚙️ Configuración del Sistema</h2>", unsafe_allow_html=True)
    
    st.markdown("### 💰 Parámetros Salariales Globales")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.session_state["salario_operativo"] = st.number_input("Sueldo Base Operativo (Masajistas):", value=float(st.session_state["salario_operativo"]), step=10.0)
    with col_s2:
        st.session_state["salario_directivo"] = st.number_input("Sueldo Base Directivo/Admin:", value=float(st.session_state["salario_directivo"]), step=10.0)
    
    st.markdown("---")
    st.markdown("### 👥 Gestión de Personal (Altas y Bajas)")
    
    col_p1, col_p2 = st.columns([1, 1])
    
    with col_p1:
        st.markdown("#### ✨ Agregar Nuevo Colaborador")
        nuevo_nombre = st.text_input("Nombre Completo:")
        nuevo_rol = st.selectbox("Rol en la Empresa:", ["Operativo", "Directivo"])
        nuevo_alias = st.text_input("Alias en el PDF (Ej. MARIA|MAR):", help="Palabra clave con la que el sistema lo buscará en el reporte de ingresos.")
        
        if st.button("➕ Dar de Alta en Sistema"):
            if nuevo_nombre and nuevo_alias:
                st.session_state["empleados"][nuevo_nombre] = {"rol": nuevo_rol, "alias": nuevo_alias.upper()}
                # Inicializar sus variables
                st.session_state[f"com_{nuevo_nombre}"] = 0.0
                st.session_state[f"serv_tot_{nuevo_nombre}"] = 0.0
                st.session_state[f"email_{nuevo_nombre}"] = ""
                st.session_state[f"hex_{nuevo_nombre}"] = 0.0
                st.session_state[f"desc_{nuevo_nombre}"] = 0.0
                st.success(f"{nuevo_nombre} ha sido agregado exitosamente a la planilla.")
                st.rerun()
            else:
                st.error("Por favor completa el nombre y el alias.")

    with col_p2:
        st.markdown("#### 🗑️ Dar de Baja a Colaborador")
        emp_a_eliminar = st.selectbox("Seleccionar colaborador a eliminar:", list(st.session_state["empleados"].keys()))
        
        if st.button("❌ Eliminar del Sistema"):
            if emp_a_eliminar:
                del st.session_state["empleados"][emp_a_eliminar]
                st.warning(f"{emp_a_eliminar} ha sido dado de baja. Ya no aparecerá en planillas ni reportes.")
                st.rerun()

    st.markdown("#### 📋 Personal Activo Actualmente")
    df_activos = pd.DataFrame([{"Nombre": k, "Rol": v["rol"], "Alias PDF": v["alias"]} for k,v in st.session_state["empleados"].items()])
    st.dataframe(df_activos, use_container_width=True, hide_index=True)
