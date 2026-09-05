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

# --- 1. CONFIGURACIÓN DE LA PÁGINA Y BRANDING ---
# Cargar el logo para la pestaña del navegador web (Favicon)
logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
try:
    if os.path.exists(logo_path):
        icono = Image.open(logo_path)
        st.set_page_config(page_title="Gio Group - Admin", page_icon=icono, layout="wide")
    else:
        st.set_page_config(page_title="Gio Group - Admin", page_icon="🏢", layout="wide")
except:
    st.set_page_config(page_title="Gio Group - Admin", page_icon="🏢", layout="wide")

# --- OCULTAR ELEMENTOS DE STREAMLIT ---
esconder_menu = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
div[data-testid="stToolbar"] {visibility: hidden !important;}
div.stButton > button:first-child {
    background-color: #0056b3;
    color: white;
    border-radius: 8px;
    border: none;
    font-weight: bold;
}
div.stButton > button:first-child:hover {
    background-color: #004494;
    border-color: #004494;
}
</style>
"""
st.markdown(esconder_menu, unsafe_allow_html=True)

# --- CABECERA CON LOGO ---
col_logo, col_title = st.columns([1, 4])
with col_logo:
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
with col_title:
    st.title("📊 Panel Gerencial y Administrativo")
    st.markdown("*Holding Empresarial: Relájate Clinic, Papi Spa, Relájate Man & Dr. Gio Molina.*")

if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
else:
    st.sidebar.markdown("### 🏢 GIO GROUP SAS DE CV")

# --- CONFIGURACIÓN BASE ---
st.sidebar.header("⚙️ Configuración Base")
base_masajistas = st.sidebar.number_input("Sueldo Base Operativo ($):", value=183.96, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Directivo ($):", value=300.00, step=10.0)

empleados_lista = [
    "Maydely Hernández", 
    "Luis Violante", 
    "Jessica Lemus", 
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)", 
    "Gerson Ulises Molina Flores", 
    "Edwin Ponce", 
    "Mario de Paz"
]

mapa_busqueda_pdf = {
    "Maydely Hernández": "MAYDELY",
    "Luis Violante": "LUIS",
    "Jessica Lemus": "JESSICA",
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)": "GIO|MARVIN|DOCTOR",
    "Gerson Ulises Molina Flores": "GERSON",
    "Edwin Ponce": "EDWIN",
    "Mario de Paz": "MARIO"
}

# Inicializar memoria de sesión
for emp in empleados_lista:
    if f"com_{emp}" not in st.session_state:
        st.session_state[f"com_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state:
        st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state:
        st.session_state[f"email_{emp}"] = "gersonmolina67@gmail.com"

if "historial_auditoria" not in st.session_state:
    st.session_state["historial_auditoria"] = []
if "ingresos_por_marca" not in st.session_state:
    st.session_state["ingresos_por_marca"] = {}

# --- LECTOR DE PDF AUTOMÁTICO CON INTELIGENCIA DE MARCAS ---
st.subheader("📂 Reporte Global de Ingresos (PDF)")
archivo_subido = st.file_uploader("Sube el reporte para calcular métricas de Holding y Planillas:", type=["pdf"])

df_reporte = None
total_ingresos_pdf = 0.0

if archivo_subido is not None:
    try:
        todas_las_filas = []
        with pdfplumber.open(archivo_subido) as pdf:
            for page in pdf.pages:
                tabla = page.extract_table()
                if tabla:
                    todas_las_filas.extend(tabla)
        
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

                total_ingresos_pdf = df_reporte[col_precio].sum()

                # Inteligencia para asignar cada servicio a una Marca del Holding
                def asignar_marca(profesional):
                    p = str(profesional).upper()
                    if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
                    if "LUIS" in p: return "Relájate Man"
                    if "GIO" in p or "MARVIN" in p or "DOCTOR" in p: return "Dr. Gio Molina"
                    return "Relájate Clinic (General)"

                df_reporte['MARCA_HOLDING'] = df_reporte[col_prof].apply(asignar_marca)
                ingresos_marcas = df_reporte.groupby('MARCA_HOLDING')[col_precio].sum().to_dict()
                st.session_state["ingresos_por_marca"] = ingresos_marcas

                def procesar_empleado(clave_busqueda):
                    df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(clave_busqueda, case=False, na=False, regex=True)]
                    tot_servicios = df_p[col_precio].sum()
                    
                    df_extras = df_p[df_p[col_precio] >= 60].copy()
                    df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                    total_bruto_extras = df_extras['EXTRA_BASE'].sum()
                    desc_pub = total_bruto_extras * 0.25
                    neto_estandar = max(0.0, total_bruto_extras - desc_pub)
                    
                    return neto_estandar, desc_pub, tot_servicios

                for emp, clave in mapa_busqueda_pdf.items():
                    estandar_val, desc_pub_val, tot_servicios_val = procesar_empleado(clave)
                    st.session_state[f"serv_tot_{emp}"] = tot_servicios_val
                    
                    if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                        mod = st.session_state.get(f"mod_{emp}", "Estándar")
                        if "Estándar" in mod:
                            st.session_state[f"com_{emp}"] = estandar_val
                        else:
                            porcentaje_actual = st.session_state.get(f"porc_{emp}", 20)
                            st.session_state[f"com_{emp}"] = tot_servicios_val * (porcentaje_actual / 100.0)
                    else:
                        st.session_state[f"com_{emp}"] = 0.0

                st.success("✅ ¡Reporte consolidado! Métricas calculadas para Empleados y Marcas (Papi Spa, Relájate Man, etc.).")
    except Exception as e:
        st.warning(f"Advertencia al leer PDF: {e}")

st.markdown("---")

# --- CREACIÓN DE PESTAÑAS GERENCIALES ---
tab_metas, tab_planillas, tab_memos, tab_amonestaciones, tab_auditoria = st.tabs([
    "📈 1. Finanzas y Metas Holding",
    "📊 2. Control de Planillas", 
    "📝 3. Memorándums", 
    "⚠️ 4. Amonestaciones", 
    "🖨️ 5. Auditoría"
])

# ==========================================
# PESTAÑA 1: DASHBOARD GERENCIAL DE HOLDING
# ==========================================
with tab_metas:
    st.subheader("📈 Estado de Resultados y Metas por Marca")
    st.markdown("Análisis financiero de viabilidad para **Papi Spa, Relájate Man, Dr. Gio Molina y Relájate Clinic**.")

    if archivo_subido is not None and df_reporte is not None:
        
        # 1. CÁLCULO DE UTILIDAD NETA (INGRESOS - PLANILLA)
        costo_planilla_estimado = sum([
            st.session_state.get(f"base_{emp}", base_fijos if emp not in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"] else base_masajistas) + 
            st.session_state.get(f"com_{emp}", 0.0) +
            st.session_state.get(f"hex_{emp}", 0.0) -
            st.session_state.get(f"desc_{emp}", 0.0)
            for emp in empleados_lista
        ])
        utilidad_neta_clinica = total_ingresos_pdf - costo_planilla_estimado

        st.markdown("### 🏦 Finanzas Globales del Grupo")
        col_fin1, col_fin2, col_fin3 = st.columns(3)
        col_fin1.metric("💰 Ingresos Brutos Totales", f"${total_ingresos_pdf:,.2f}")
        col_fin2.metric("💸 Costo Operativo (Planillas)", f"${costo_planilla_estimado:,.2f}")
        col_fin3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta_clinica:,.2f}", 
                        help="Ingresos Brutos menos los Sueldos, Comisiones y Bonos de TODO el equipo.",
                        delta=f"{((utilidad_neta_clinica/total_ingresos_pdf)*100):.1f}% Margen" if total_ingresos_pdf > 0 else "")

        st.markdown("---")
        st.markdown("### 🎯 Configuración de Metas Empresariales")
        marcas_detectadas = st.session_state["ingresos_por_marca"]
        
        cols_metas = st.columns(len(marcas_detectadas) if len(marcas_detectadas) > 0 else 1)
        metas_configuradas = {}
        
        for i, (marca, ingresos) in enumerate(marcas_detectadas.items()):
            # Por defecto proponemos $5000 de meta por empresa
            meta_defecto = 5000.0 if "Dr" not in marca else 8000.0
            metas_configuradas[marca] = cols_metas[i].number_input(f"Meta: {marca}", value=meta_defecto, step=500.0, key=f"meta_{marca}")

        st.markdown("#### 📊 Rendimiento de Ingresos vs Metas por Empresa")
        df_marcas = pd.DataFrame([
            {"Marca": m, "Ingresos Reales ($)": ing, "Meta ($)": metas_configuradas[m], "Estado": "✅ Superada" if ing >= metas_configuradas[m] else "⚠️ En progreso"}
            for m, ing in marcas_detectadas.items()
        ])
        
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            st.bar_chart(pd.DataFrame.from_dict(marcas_detectadas, orient='index', columns=['Ingresos ($)']))
        with col_m2:
            st.dataframe(df_marcas.style.format({"Ingresos Reales ($)": "{:,.2f}", "Meta ($)": "{:,.2f}"}), hide_index=True)

    else:
        st.info("ℹ️ Sube un reporte de ingresos en PDF en la pestaña principal para ver el Estado de Resultados de las marcas.")

# ==========================================
# PESTAÑA 2: CONTROL DE PLANILLAS
# ==========================================
with tab_planillas:
    st.subheader("✍️ Ajustes, Nivelaciones y Planilla")
    datos_empleados = []

    for emp in empleados_lista:
        with st.expander(f"👤 {emp} - Configurar Pago"):
            col1, col2, col3 = st.columns(3)
            
            base_sugerido = base_fijos if emp not in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"] else base_masajistas
            desc_pub_actual = 0.0
            modalidad_str = "Estándar"

            with col1:
                sueldo_base = st.number_input(f"Sueldo Base ($) [{emp}]", value=float(base_sugerido), key=f"base_{emp}")
                
                if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                    modalidad = st.selectbox(f"Modalidad [{emp}]", ["Estándar (Sueldo + Comisiones con 25% Pub)", "Porcentaje Directo (%)"], key=f"mod_{emp}")
                    tot_serv = st.session_state.get(f"serv_tot_{emp}", 0.0)
                    
                    if "Estándar" in modalidad:
                        modalidad_str = "Estándar"
                        if df_reporte is not None and 'col_prof' in locals() and 'col_precio' in locals():
                            clave = mapa_busqueda_pdf.get(emp, emp.split()[0])
                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(clave, case=False, na=False, regex=True)]
                            df_ex = df_p[df_p[col_precio] >= 60].copy()
                            ext_val = (df_ex[col_precio] - 60).sum()
                            d_pub = ext_val * 0.25
                            st.session_state[f"com_{emp}"] = max(0.0, ext_val - d_pub)
                            desc_pub_actual = d_pub
                    else:
                        modalidad_str = "Porcentaje Directo"
                        porc_personalizado = st.slider(f"Porcentaje (%) [{emp}]", 0, 100, 20, key=f"porc_{emp}")
                        st.session_state[f"com_{emp}"] = tot_serv * (porc_personalizado / 100.0)
                else:
                    modalidad_str = "Administrativo/Fijo"
                    tot_serv_admin = st.session_state.get(f"serv_tot_{emp}", 0.0)
                    st.info(f"💼 Rol Directivo. Producción para la clínica: ${tot_serv_admin:.2f}. (Sueldo fijo, sin comisión automática).")

                comision_extra = st.number_input(f"Comisión Real Generada ($) [{emp}]", key=f"com_{emp}", step=5.0)

            with col2:
                horas_extras = st.number_input(f"Bonos / Nivelación / Extras ($) [{emp}]", value=0.0, key=f"hex_{emp}", step=5.0)
                descuentos_extras = st.number_input(f"Descuentos ($) [{emp}]", value=0.0, key=f"desc_{emp}", step=5.0)
            
            with col3:
                nota_descuento = st.text_input(f"Nota de Descuento/Bono [{emp}]", value="Ninguno", key=f"nota_{emp}")
                email_emp = st.text_input(f"Correo [{emp}]", key=f"email_{emp}")

            total_neto = sueldo_base + comision_extra + horas_extras - descuentos_extras
            
            datos_empleados.append({
                "Empleado": emp, "Sueldo Base": sueldo_base, "Comisiones": comision_extra, "Bonos/Nivelación": horas_extras, 
                "Modalidad": modalidad_str, "Desc. Publicidad": desc_pub_actual, "Otros Desc": descuentos_extras, 
                "Nota": nota_descuento, "Total a Pagar": total_neto, "Email": email_emp
            })

    df_resumen = pd.DataFrame(datos_empleados)

    st.markdown("### 📋 Resumen General de Planilla")
    st.dataframe(df_resumen[["Empleado", "Sueldo Base", "Comisiones", "Bonos/Nivelación", "Desc. Publicidad", "Total a Pagar"]].style.format({
        "Sueldo Base": "{:.2f}", "Comisiones": "{:.2f}", "Bonos/Nivelación": "{:.2f}", "Desc. Publicidad": "{:.2f}", "Total a Pagar": "{:.2f}"
    }), use_container_width=True, hide_index=True)

    output_excel = io.BytesIO()
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        df_resumen.to_excel(writer, index=False, sheet_name='Planilla General')
    output_excel.seek(0)
    st.download_button("📥 Descargar Planilla en Excel (.xlsx)", data=output_excel, file_name=f"Planilla_GioGroup_{datetime.now().strftime('%Y%m%d')}.xlsx")

    st.markdown("---")
    st.subheader("✉️ Envío de Comprobantes")
    emp_sel_planilla = st.selectbox("Seleccionar empleado:", empleados_lista, key="sel_emp_plan")
    emp_data = next(item for item in datos_empleados if item["Empleado"] == emp_sel_planilla)

    if st.button("👁️ Generar Vista Previa del Recibo PDF"):
        class PDFPlanilla(FPDF):
            def header(self):
                if os.path.exists(logo_path):
                    self.image(logo_path, 10, 8, 25)
                    self.set_x(40)
                self.set_font('helvetica', 'B', 16)
                self.set_text_color(0, 86, 179)
                self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                
                if os.path.exists(logo_path):
                    self.set_x(40)
                self.set_font('helvetica', '', 10)
                self.set_text_color(100, 100, 100)
                self.cell(0, 5, f'Comprobante Oficial de Pago - Modalidad: {emp_data["Modalidad"]}', 0, 1, 'L')
                
                if os.path.exists(logo_path):
                    self.set_x(40)
                self.cell(0, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
                self.ln(10)

        pdf_p = PDFPlanilla()
        pdf_p.add_page()
        pdf_p.set_font('helvetica', 'B', 11)
        pdf_p.set_fill_color(240, 243, 246)
        pdf_p.cell(0, 10, f" Colaborador/a: {emp_data['Empleado']}", 0, 1, 'L', fill=True)
        pdf_p.ln(5)
        pdf_p.set_font('helvetica', 'B', 10)
        pdf_p.set_fill_color(0, 86, 179)
        pdf_p.set_text_color(255, 255, 255)
        pdf_p.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True)
        pdf_p.cell(60, 8, ' Monto ($) ', 1, 1, 'R', fill=True)
        pdf_p.set_font('helvetica', '', 10)
        pdf_p.set_text_color(50, 50, 50)
        
        for desc, val in [("Sueldo Base", emp_data['Sueldo Base']), ("Comisiones y Servicios", emp_data['Comisiones']), ("Bonos / Extras / Nivelación", emp_data['Bonos/Nivelación'])]:
            pdf_p.cell(130, 8, f"  {desc}", 1, 0, 'L')
            pdf_p.cell(60, 8, f"${val:.2f} ", 1, 1, 'R')

        if emp_data['Desc. Publicidad'] > 0:
            pdf_p.set_text_color(201, 42, 42)
            pdf_p.cell(130, 8, "  (-) Retención 25% Publicidad", 1, 0, 'L')
            pdf_p.cell(60, 8, f"-${emp_data['Desc. Publicidad']:.2f} ", 1, 1, 'R')
            pdf_p.set_text_color(50, 50, 50)

        if emp_data['Otros Desc'] > 0:
            pdf_p.set_text_color(201, 42, 42)
            pdf_p.cell(130, 8, "  (-) Otros Descuentos", 1, 0, 'L')
            pdf_p.cell(60, 8, f"-${emp_data['Otros Desc']:.2f} ", 1, 1, 'R')
            pdf_p.set_text_color(50, 50, 50)

        pdf_p.set_font('helvetica', 'B', 11)
        pdf_p.set_fill_color(230, 235, 240)
        pdf_p.cell(130, 10, "  TOTAL NETO A RECIBIR", 1, 0, 'L', fill=True)
        pdf_p.cell(60, 10, f"${emp_data['Total a Pagar']:.2f} ", 1, 1, 'R', fill=True)
        
        pdf_path = f"Recibo_{emp_sel_planilla.replace(' ', '_')}.pdf"
        pdf_p.output(pdf_path)
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        st.session_state['temp_pdf_planilla'] = pdf_bytes
        st.session_state['temp_pdf_path'] = pdf_path

    if 'temp_pdf_planilla' in st.session_state:
        st.download_button("📄 Descargar Recibo Generado para Revisión", data=st.session_state['temp_pdf_planilla'], file_name=st.session_state['temp_pdf_path'], mime="application/pdf")
        
        if st.button("🚀 Confirmar y Enviar por Correo", type="primary"):
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = emp_data['Email']
                msg['Subject'] = f"Comprobante de Pago Oficial - Gio Group"
                msg.attach(MIMEText(f"Estimado/a {emp_sel_planilla},\nAdjunto su comprobante de pago oficial.\nTotal Neto: ${emp_data['Total a Pagar']:.2f}\nAtentamente,\nGerencia", 'plain'))
                
                with open(st.session_state['temp_pdf_path'], "rb") as f:
                    adj = MIMEApplication(f.read(), Name=st.session_state['temp_pdf_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["temp_pdf_path"]}"'
                msg.attach(adj)
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, emp_data['Email'], msg.as_string())
                server.quit()
                
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo": "Recibo Planilla", "Destinatario": emp_sel_planilla, "Correo": emp_data['Email'], "Detalle": f"${emp_data['Total a Pagar']:.2f}"})
                st.success("¡Recibo enviado con éxito!")
                del st.session_state['temp_pdf_planilla']
            except Exception as e:
                st.error(f"Error al enviar: {e}")

# ==========================================
# PESTAÑA 3: MEMORÁNDUMS
# ==========================================
with tab_memos:
    st.subheader("📝 Emisión de Memorándums Internos")
    emp_memo = st.selectbox("Destinatario:", empleados_lista, key="memo_emp")
    asunto_memo = st.text_input("Asunto:", value="Aviso Administrativo")
    texto_memo = st.text_area("Cuerpo del Memorándum:")
    email_memo = st.text_input("Correo destinatario:", value=st.session_state.get(f"email_{emp_memo}", ""), key="email_memo_input")

    if st.button("👁️ Generar PDF del Memorándum"):
        if texto_memo:
            class PDFMemo(FPDF):
                def header(self):
                    if os.path.exists(logo_path):
                        self.image(logo_path, 10, 8, 25)
                        self.set_x(40)
                    self.set_font('helvetica', 'B', 16)
                    self.set_text_color(0, 86, 179)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    
                    if os.path.exists(logo_path):
                        self.set_x(40)
                    self.set_font('helvetica', '', 10)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 5, 'MEMORANDUM OFICIAL', 0, 1, 'L')
                    self.ln(10)

            pdf_m = PDFMemo()
            pdf_m.add_page()
            pdf_m.set_font('helvetica', 'B', 11)
            pdf_m.cell(0, 10, f" Para: {emp_memo}", 0, 1, 'L')
            pdf_m.cell(0, 10, f" Asunto: {asunto_memo}", 0, 1, 'L')
            pdf_m.ln(5)
            pdf_m.set_font('helvetica', '', 11)
            pdf_m.multi_cell(0, 7, texto_memo, 0, 'L')
            
            m_path = f"Memo_{emp_memo.replace(' ','_')}.pdf"
            pdf_m.output(m_path)
            with open(m_path, "rb") as f:
                st.session_state['temp_memo_pdf'] = f.read()
                st.session_state['temp_memo_path'] = m_path

    if 'temp_memo_pdf' in st.session_state:
        st.download_button("📄 Descargar Memo para Revisión", data=st.session_state['temp_memo_pdf'], file_name=st.session_state['temp_memo_path'])
        if st.button("🚀 Enviar Memorándum por Correo", type="primary"):
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_memo
                msg['Subject'] = f"MEMORÁNDUM: {asunto_memo}"
                msg.attach(MIMEText("Adjunto documento oficial.\nAtentamente,\nGerencia", 'plain'))
                with open(st.session_state['temp_memo_path'], "rb") as f:
                    adj = MIMEApplication(f.read(), Name=st.session_state['temp_memo_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["temp_memo_path"]}"'
                msg.attach(adj)
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_memo, msg.as_string())
                server.quit()
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo": "Memo", "Destinatario": emp_memo, "Correo": email_memo, "Detalle": asunto_memo})
                st.success("¡Memo enviado!")
                del st.session_state['temp_memo_pdf']
            except Exception as e:
                st.error(e)

# ==========================================
# PESTAÑA 4: AMONESTACIONES
# ==========================================
with tab_amonestaciones:
    st.subheader("⚠️ Registro de Amonestaciones")
    emp_amon = st.selectbox("Colaborador:", empleados_lista, key="amon_emp")
    tipo_falta = st.selectbox("Falta:", ["Llamada de Atención Verbal", "Amonestación Escrita Leve", "Amonestación Escrita Grave"])
    motivo_amon = st.text_area("Detalles de la falta:")
    email_amon = st.text_input("Correo confidencial:", value=st.session_state.get(f"email_{emp_amon}", ""), key="email_amon_input")

    if st.button("👁️ Generar Acta PDF"):
        if motivo_amon:
            class PDFAmon(FPDF):
                def header(self):
                    if os.path.exists(logo_path):
                        self.image(logo_path, 10, 8, 25)
                        self.set_x(40)
                    self.set_font('helvetica', 'B', 16)
                    self.set_text_color(201, 42, 42)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    
                    if os.path.exists(logo_path):
                        self.set_x(40)
                    self.set_font('helvetica', '', 10)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 5, 'ACTA OFICIAL DE AMONESTACION', 0, 1, 'L')
                    self.ln(10)

            pdf_a = PDFAmon()
            pdf_a.add_page()
            pdf_a.set_font('helvetica', 'B', 11)
            pdf_a.cell(0, 10, f" Colaborador/a: {emp_amon}", 0, 1, 'L')
            pdf_a.cell(0, 10, f" Tipo: {tipo_falta}", 0, 1, 'L')
            pdf_a.ln(5)
            pdf_a.set_font('helvetica', '', 11)
            pdf_a.multi_cell(0, 7, motivo_amon, 1, 'L')
            
            a_path = f"Amonestacion_{emp_amon.replace(' ','_')}.pdf"
            pdf_a.output(a_path)
            with open(a_path, "rb") as f:
                st.session_state['temp_amon_pdf'] = f.read()
                st.session_state['temp_amon_path'] = a_path

    if 'temp_amon_pdf' in st.session_state:
        st.download_button("📄 Descargar Acta para Revisión", data=st.session_state['temp_amon_pdf'], file_name=st.session_state['temp_amon_path'])
        if st.button("🚀 Enviar Amonestación por Correo", type="primary"):
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_amon
                msg['Subject'] = f"NOTIFICACIÓN ADMINISTRATIVA - Gio Group"
                msg.attach(MIMEText("Adjunto documento oficial a su expediente.\nAtentamente,\nRecursos Humanos", 'plain'))
                with open(st.session_state['temp_amon_path'], "rb") as f:
                    adj = MIMEApplication(f.read(), Name=st.session_state['temp_amon_path'])
                adj['Content-Disposition'] = f'attachment; filename="{st.session_state["temp_amon_path"]}"'
                msg.attach(adj)
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_amon, msg.as_string())
                server.quit()
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo": "Amonestación", "Destinatario": emp_amon, "Correo": email_amon, "Detalle": tipo_falta})
                st.success("¡Amonestación enviada!")
                del st.session_state['temp_amon_pdf']
            except Exception as e:
                st.error(e)

# ==========================================
# PESTAÑA 5: AUDITORÍA
# ==========================================
with tab_auditoria:
    st.subheader("🖨️ Log de Envíos y Auditoría")
    if len(st.session_state["historial_auditoria"]) > 0:
        df_audit = pd.DataFrame(st.session_state["historial_auditoria"])
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
        out_aud = io.BytesIO()
        with pd.ExcelWriter(out_aud, engine='openpyxl') as w:
            df_audit.to_excel(w, index=False)
        out_aud.seek(0)
        st.download_button("📥 Descargar Historial (.xlsx)", data=out_aud, file_name="Auditoria.xlsx")
    else:
        st.info("No hay registros de envío en esta sesión todavía.")
