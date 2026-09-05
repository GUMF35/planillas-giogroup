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

# --- 2. CSS AVANZADO: TEMA "GLINT" BLINDADO ---
estilo_glint = """
<style>
    /* Ocultar elementos molestos pero DEJAR EL HEADER PARA EL MENÚ */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* Hacer transparente el header para que no arruine el diseño pero mantenga el botón del menú visible */
    header {background-color: transparent !important;}
    
    /* Fondo Global de la App */
    .stApp {
        background-color: #F4F5F7 !important;
    }
    
    /* WIDGETS Y TARJETAS BLANCAS (Glassmorphism) */
    [data-testid="stMetric"], div[data-testid="metric-container"], .stDataFrame, [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.04) !important;
        border: 1px solid #EAEAEA !important;
    }
    
    /* Acento en las Tarjetas de Métricas */
    [data-testid="stMetric"] {
        border-bottom: 4px solid #00C4B5 !important; /* Color Cyan/Teal adaptable al logo */
    }
    [data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
    [data-testid="stMetricValue"] {
        color: #1B1B1E !important;
        font-weight: 800 !important;
        font-size: 1.8rem !important;
    }

    /* FORZAR SIDEBAR A MODO OSCURO (GLINT STYLE) */
    [data-testid="stSidebar"] {
        background-color: #1B1B1E !important;
        border-right: 1px solid #2A2A35 !important;
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #A1A1AA !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }

    /* Diseño de Botones Principales */
    div.stButton > button:first-child {
        background-color: #1B1B1E !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: bold !important;
        padding: 0.6rem 1.2rem !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #00C4B5 !important; /* Acento al pasar el mouse */
        color: #FFFFFF !important;
        transform: translateY(-2px);
    }
    
    /* Títulos limpios */
    h1, h2, h3 {
        color: #1B1B1E !important;
        font-weight: 800 !important;
    }
    
    /* Inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
        background-color: #F9FAFB !important;
        border-radius: 8px !important;
        border: 1px solid #E2E8F0 !important;
        color: #1B1B1E !important;
    }
</style>
"""
st.markdown(estilo_glint, unsafe_allow_html=True)

# --- 3. MENÚ LATERAL INTERACTIVO (SIDEBAR) ---
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
    else:
        st.markdown("<h2 style='text-align:center; color:white;'>GIO GROUP</h2>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Menú 100% en español
    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Memorándums", "Amonestaciones", "Auditoría"],
        icons=["grid-1x2-fill", "wallet-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#1B1B1E"},
            "icon": {"color": "#A1A1AA", "font-size": "16px"}, 
            "nav-link": {
                "font-size": "14px", 
                "text-align": "left", 
                "margin":"4px 0px", 
                "padding": "10px 15px",
                "color": "#A1A1AA", 
                "border-radius": "0px",
                "--hover-color": "#2A2B32"
            },
            "nav-link-selected": {
                "background-color": "#2A2B32", 
                "color": "#00C4B5", 
                "font-weight": "bold",
                "border-left": "4px solid #00C4B5"
            },
            "menu-title": {"color": "#64748B", "font-size": "11px", "font-weight": "bold", "letter-spacing": "1px", "padding-left": "15px"}
        }
    )
    
    st.markdown("---")
    st.markdown("<p style='color:#64748B; font-size:11px; font-weight:bold; letter-spacing:1px; padding-left:15px;'>AJUSTES DE SISTEMA</p>", unsafe_allow_html=True)
    base_masajistas = st.number_input("Base Operativo ($):", value=183.96, step=10.0)
    base_fijos = st.number_input("Base Directivo ($):", value=300.00, step=10.0)

# --- 4. VARIABLES GLOBALES Y LÓGICA DE NEGOCIO ---
empleados_lista = [
    "Maydely Hernández", "Luis Violante", "Jessica Lemus", 
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)", "Gerson Ulises Molina Flores", 
    "Edwin Ponce", "Mario de Paz"
]

mapa_busqueda_pdf = {
    "Maydely Hernández": "MAYDELY", "Luis Violante": "LUIS", "Jessica Lemus": "JESSICA",
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)": "GIO|MARVIN|DOCTOR",
    "Gerson Ulises Molina Flores": "GERSON", "Edwin Ponce": "EDWIN", "Mario de Paz": "MARIO"
}

for emp in empleados_lista:
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = "gersonmolina67@gmail.com"
    if f"base_{emp}" not in st.session_state: st.session_state[f"base_{emp}"] = base_fijos if emp not in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"] else base_masajistas
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0

if "historial_auditoria" not in st.session_state: st.session_state["historial_auditoria"] = []
if "ingresos_por_marca" not in st.session_state: st.session_state["ingresos_por_marca"] = {}
if "total_ingresos_pdf" not in st.session_state: st.session_state["total_ingresos_pdf"] = 0.0

# --- PANEL SUPERIOR: LECTOR DE PDF ---
with st.container():
    st.markdown("<h2 style='color:#1B1B1E; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)
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

                    for emp, clave in mapa_busqueda_pdf.items():
                        est_val, d_pub, tot_val = procesar_empleado(clave)
                        st.session_state[f"serv_tot_{emp}"] = tot_val
                        
                        if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                            mod = st.session_state.get(f"mod_{emp}", "Estándar")
                            st.session_state[f"com_{emp}"] = est_val if "Estándar" in mod else tot_val * (st.session_state.get(f"porc_{emp}", 20) / 100.0)
                        else:
                            st.session_state[f"com_{emp}"] = 0.0

                    st.success("✅ Sincronización exitosa. Los datos se han actualizado en todos los módulos.")
        except Exception as e:
            st.error(f"Error al leer el documento PDF: {e}")

st.markdown("<br>", unsafe_allow_html=True)

# --- 5. ENRUTAMIENTO DE VISTAS (PÁGINAS 100% ESPAÑOL) ---

if menu_seleccionado == "Dashboard":
    
    meta_minima = st.sidebar.number_input("Meta KPI Individual ($):", value=300.0, step=50.0)

    if st.session_state["total_ingresos_pdf"] > 0:
        costo_planilla = sum([st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"] for emp in empleados_lista])
        utilidad_neta = st.session_state["total_ingresos_pdf"] - costo_planilla

        # KPIs Corporativos
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos Totales", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Costo Operativo (Planillas)", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta:,.2f}", delta=f"{((utilidad_neta/st.session_state['total_ingresos_pdf'])*100):.1f}% Margen" if st.session_state['total_ingresos_pdf'] > 0 else "")

        st.markdown("<br><h3 style='color:#1B1B1E;'>🎯 Rendimiento de Marcas (Holding)</h3>", unsafe_allow_html=True)
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

        st.markdown("<br><h3 style='color:#1B1B1E;'>⭐ Rendimiento del Personal</h3>", unsafe_allow_html=True)
        metricas = [{"Colaborador": e, "Total Generado ($)": st.session_state[f"serv_tot_{e}"], "Estado": "✅ Meta Superada" if st.session_state[f"serv_tot_{e}"] >= meta_minima else "En progreso"} for e in empleados_lista]
        st.dataframe(pd.DataFrame(metricas).style.format({"Total Generado ($)": "{:,.2f}"}), use_container_width=True, hide_index=True)

    else:
        st.info("Sube un reporte PDF en la parte superior para visualizar las métricas y los gráficos del sistema.")

elif menu_seleccionado == "Planillas":
    st.markdown("<h2 style='color:#1B1B1E;'>Control Financiero de Planillas</h2>", unsafe_allow_html=True)
    datos_emp = []

    for emp in empleados_lista:
        with st.expander(f"👤 {emp}"):
            c1, c2, c3 = st.columns(3)
            mod_str = "Estándar"

            with c1:
                st.session_state[f"base_{emp}"] = st.number_input(f"Sueldo Base ($) [{emp}]", value=st.session_state[f"base_{emp}"], key=f"in_b_{emp}")
                if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                    mod = st.selectbox(f"Modalidad de Pago [{emp}]", ["Estándar (Con retención publicidad)", "Porcentaje Directo (%)"], key=f"m_{emp}")
                    if "Estándar" in mod: mod_str = "Estándar"
                    else:
                        mod_str = "Porcentaje Directo"
                        st.session_state[f"com_{emp}"] = st.session_state[f"serv_tot_{emp}"] * (st.slider(f"Porcentaje de Ganancia (%) [{emp}]", 0, 100, 20, key=f"p_{emp}") / 100.0)
                else:
                    mod_str = "Directivo/Fijo"
                    st.caption(f"Ingresos brutos aportados a la clínica: ${st.session_state[f'serv_tot_{emp}']:.2f}")

                st.session_state[f"com_{emp}"] = st.number_input(f"Comisiones Generadas ($) [{emp}]", value=float(st.session_state[f"com_{emp}"]), key=f"in_c_{emp}")

            with c2:
                st.session_state[f"hex_{emp}"] = st.number_input(f"Bonos o Nivelación ($) [{emp}]", value=float(st.session_state[f"hex_{emp}"]), key=f"in_h_{emp}")
                st.session_state[f"desc_{emp}"] = st.number_input(f"Descuentos Aplicados ($) [{emp}]", value=float(st.session_state[f"desc_{emp}"]), key=f"in_d_{emp}")
            
            with c3:
                n_desc = st.text_input(f"Motivo Descuento/Bono [{emp}]", value="Ninguno", key=f"n_{emp}")
                st.session_state[f"email_{emp}"] = st.text_input(f"Correo Electrónico [{emp}]", value=st.session_state[f"email_{emp}"], key=f"in_e_{emp}")

            t_net = st.session_state[f"base_{emp}"] + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"desc_{emp}"]
            datos_emp.append({"Colaborador": emp, "Sueldo Base": st.session_state[f"base_{emp}"], "Comisiones": st.session_state[f"com_{emp}"], "Bonos Adicionales": st.session_state[f"hex_{emp}"], "Total a Pagar": t_net, "Email": st.session_state[f"email_{emp}"]})

    df_res = pd.DataFrame(datos_emp)
    st.markdown("<br><h4>Resumen Consolidado</h4>", unsafe_allow_html=True)
    st.dataframe(df_res.style.format({"Sueldo Base": "${:.2f}", "Comisiones": "${:.2f}", "Bonos Adicionales": "${:.2f}", "Total a Pagar": "${:.2f}"}), use_container_width=True, hide_index=True)

    out_ex = io.BytesIO()
    with pd.ExcelWriter(out_ex, engine='openpyxl') as w: df_res.to_excel(w, index=False)
    out_ex.seek(0)
    st.download_button("📥 Exportar Reporte de Planilla (Excel)", data=out_ex, file_name="Reporte_Planilla.xlsx")

    st.markdown("---")
    st.markdown("<h3>Gestión y Envío de Recibos de Pago</h3>", unsafe_allow_html=True)
    e_sel = st.selectbox("Seleccionar Colaborador:", empleados_lista)
    e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)

    if st.button("👁️ Visualizar y Generar Recibo (PDF)"):
        class PDF(FPDF):
            def header(self):
                if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                self.set_font('helvetica', 'B', 16); self.set_text_color(27, 27, 30); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                if os.path.exists(logo_path): self.set_x(40)
                self.set_font('helvetica', '', 10); self.set_text_color(100, 100, 100); self.cell(0, 5, 'Comprobante Oficial de Pago', 0, 1, 'L'); self.ln(10)
        
        pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(244, 245, 247)
        pdf.cell(0, 10, f" Colaborador: {e_dat['Colaborador']}", 0, 1, 'L', fill=True); pdf.ln(5)
        pdf.set_fill_color(27, 27, 30); pdf.set_text_color(255, 255, 255)
        pdf.cell(130, 8, ' Concepto / Descripción', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
        pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
        
        for d, v in [("Sueldo Base", e_dat['Sueldo Base']), ("Comisiones por Servicios", e_dat['Comisiones']), ("Bonos de Productividad", e_dat['Bonos Adicionales'])]:
            pdf.cell(130, 8, f"  {d}", 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')
        
        pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(244, 245, 247); pdf.set_text_color(27, 27, 30)
        pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total a Pagar']:.2f}", 1, 1, 'R', fill=True)
        
        p_path = f"Recibo_Pago_{e_sel.replace(' ','_')}.pdf"; pdf.output(p_path)
        with open(p_path, "rb") as f: st.session_state['t_pdf'] = f.read(); st.session_state['t_path'] = p_path

    if 't_pdf' in st.session_state:
        st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")
        if st.button("🚀 Enviar Comprobante al Correo"):
            try:
                rem, pwd = st.secrets["EMAIL_USER"], st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'], msg['To'], msg['Subject'] = rem, e_dat['Email'], "Comprobante de Pago Mensual - Gio Group"
                msg.attach(MIMEText("Estimado equipo, adjuntamos su comprobante oficial de pago.\n\nAdministración Gio Group.", 'plain'))
                with open(st.session_state['t_path'], "rb") as f: adj = MIMEApplication(f.read(), Name=st.session_state['t_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["t_path"]}"'; msg.attach(adj)
                s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(rem, pwd); s.sendmail(rem, e_dat['Email'], msg.as_string()); s.quit()
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": "Recibo de Pago", "Destinatario": e_sel})
                st.success("¡Documento enviado con éxito al colaborador!"); del st.session_state['t_pdf']
            except Exception as e: st.error(e)

elif menu_seleccionado == "Memorándums":
    st.markdown("<h2 style='color:#1B1B1E;'>📝 Emisión de Memorándums Internos</h2>", unsafe_allow_html=True)
    emp_memo = st.selectbox("Destinatario del Memorándum:", empleados_lista)
    asunto_memo = st.text_input("Asunto a tratar:", value="Aviso Administrativo Oficial")
    texto_memo = st.text_area("Cuerpo o notas del Memorándum:")
    email_memo = st.text_input("Correo destinatario:", value=st.session_state.get(f"email_{emp_memo}", ""))

    if st.button("👁️ Generar PDF Oficial"):
        if texto_memo:
            class PDFMemo(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
            pdf_m = PDFMemo(); pdf_m.add_page(); pdf_m.set_font('helvetica', 'B', 11)
            pdf_m.cell(0, 10, f" Entregado a: {emp_memo}", 0, 1, 'L'); pdf_m.cell(0, 10, f" Asunto Central: {asunto_memo}", 0, 1, 'L')
            pdf_m.set_font('helvetica', '', 11); pdf_m.multi_cell(0, 7, texto_memo, 0, 'L')
            m_path = f"Memorandum_{emp_memo.replace(' ','_')}.pdf"; pdf_m.output(m_path)
            with open(m_path, "rb") as f: st.session_state['temp_memo_pdf'] = f.read(); st.session_state['temp_memo_path'] = m_path

    if 'temp_memo_pdf' in st.session_state:
        st.download_button("📄 Descargar Archivo PDF", data=st.session_state['temp_memo_pdf'], file_name=st.session_state['temp_memo_path'])
        if st.button("🚀 Enviar por Correo Electrónico"):
            try:
                rem, pwd = st.secrets["EMAIL_USER"], st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'], msg['To'], msg['Subject'] = rem, email_memo, f"MEMORÁNDUM CORPORATIVO: {asunto_memo}"
                msg.attach(MIMEText("Se adjunta un memorándum oficial de la administración para su revisión.\n\nGerencia.", 'plain'))
                with open(st.session_state['temp_memo_path'], "rb") as f: adj = MIMEApplication(f.read(), Name=st.session_state['temp_memo_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["temp_memo_path"]}"'; msg.attach(adj)
                s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(rem, pwd); s.sendmail(rem, email_memo, msg.as_string()); s.quit()
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": "Memorándum", "Destinatario": emp_memo})
                st.success("¡Comunicado enviado satisfactoriamente!"); del st.session_state['temp_memo_pdf']
            except Exception as e: st.error(e)

elif menu_seleccionado == "Amonestaciones":
    st.markdown("<h2 style='color:#1B1B1E;'>⚠️ Registro de Faltas y Amonestaciones</h2>", unsafe_allow_html=True)
    emp_amon = st.selectbox("Colaborador involucrado:", empleados_lista)
    tipo_falta = st.selectbox("Gravedad de la Falta:", ["Llamada de Atención Verbal (Registro)", "Amonestación Escrita Leve", "Amonestación Escrita Grave"])
    motivo_amon = st.text_area("Detalles completos del incidente:")
    email_amon = st.text_input("Correo electrónico para expediente:", value=st.session_state.get(f"email_{emp_amon}", ""))
    
    if st.button("👁️ Redactar Acta PDF"):
        if motivo_amon:
            class PDFAmon(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(201, 42, 42)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L'); self.ln(5)
            pdf_a = PDFAmon(); pdf_a.add_page(); pdf_a.set_font('helvetica', 'B', 11)
            pdf_a.cell(0, 10, f" Dirigido a: {emp_amon}", 0, 1, 'L'); pdf_a.multi_cell(0, 7, motivo_amon, 1, 'L')
            a_path = f"Acta_Amonestacion_{emp_amon.replace(' ','_')}.pdf"; pdf_a.output(a_path)
            with open(a_path, "rb") as f: st.session_state['temp_amon_pdf'] = f.read(); st.session_state['temp_amon_path'] = a_path

    if 'temp_amon_pdf' in st.session_state:
        st.download_button("📄 Descargar Acta Formal", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])
        if st.button("🚀 Remitir Amonestación Oficial"):
            try:
                rem, pwd = st.secrets["EMAIL_USER"], st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'], msg['To'], msg['Subject'] = rem, email_amon, "NOTIFICACIÓN DE RECURSOS HUMANOS - Gio Group"
                msg.attach(MIMEText("Se ha adjuntado un acta oficial a su expediente corporativo.\n\nAtentamente,\nRecursos Humanos.", 'plain'))
                with open(st.session_state['temp_amon_path'], "rb") as f: adj = MIMEApplication(f.read(), Name=st.session_state['temp_amon_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["temp_amon_path"]}"'; msg.attach(adj)
                s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(rem, pwd); s.sendmail(rem, email_amon, msg.as_string()); s.quit()
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo Documento": "Acta Amonestación", "Destinatario": emp_amon})
                st.success("¡Acta registrada y remitida al colaborador!"); del st.session_state['temp_amon_pdf']
            except Exception as e: st.error(e)

elif menu_seleccionado == "Auditoría":
    st.markdown("<h2 style='color:#1B1B1E;'>🖨️ Registro y Control de Auditoría</h2>", unsafe_allow_html=True)
    if st.session_state["historial_auditoria"]:
        st.dataframe(pd.DataFrame(st.session_state["historial_auditoria"]), use_container_width=True)
    else:
        st.info("El registro está limpio. No se han detectado envíos ni acciones en el sistema durante esta sesión.")
