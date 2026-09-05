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

# --- 1. CONFIGURACIÓN DE LA PÁGINA Y BRANDING ---
st.set_page_config(page_title="Gio Group - Admin", page_icon="🏢", layout="wide")

logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)
else:
    st.sidebar.markdown("### 🏢 GIO GROUP SAS DE CV")

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

st.title("📊 Panel Gerencial y Administrativo")
st.markdown("*Sistema integral de recursos humanos, planillas y métricas financieras de rendimiento.*")

# --- CONFIGURACIÓN BASE ---
st.sidebar.header("⚙️ Configuración Base")
base_masajistas = st.sidebar.number_input("Sueldo Base Estándar ($):", value=183.96, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Administrativo ($):", value=300.00, step=10.0)

empleados_lista = [
    "Maydely Hernández", 
    "Luis Violante", 
    "Jessica Lemus", 
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)", 
    "Gerson Ulises Molina Flores", 
    "Edwin Ponce", 
    "Mario de Paz"
]

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

# --- LECTOR DE PDF AUTOMÁTICO (GLOBAL PARA TODOS LOS PROFESIONALES) ---
st.subheader("📂 Reporte Global de Ingresos (PDF)")
archivo_subido = st.file_uploader("Sube el archivo PDF de ingresos para alimentar el Dashboard y las Planillas:", type=["pdf"])

df_reporte = None
servicios_por_profesional = {}
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

                # Extraer automáticamente a TODOS los profesionales únicos que aparecen en el PDF
                nombres_en_pdf = df_reporte[col_prof].dropna().unique()

                def procesar_empleado(nombre_corto):
                    df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre_corto, case=False, na=False)]
                    tot_servicios = df_p[col_precio].sum()
                    
                    df_extras = df_p[df_p[col_precio] >= 60].copy()
                    df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                    total_bruto_extras = df_extras['EXTRA_BASE'].sum()
                    desc_pub = total_bruto_extras * 0.25
                    neto_estandar = max(0.0, total_bruto_extras - desc_pub)
                    
                    return neto_estandar, desc_pub, tot_servicios

                # Mapear totales de servicios para cada empleado de la lista
                for emp in empleados_lista:
                    # Buscar la coincidencia clave (ej. Maydely, Luis, Jessica, Gio, Gerson, etc.)
                    clave_busqueda = "GIO" if "Gio" in emp else ("GERSON" if "Gerson" in emp else emp.split()[0])
                    
                    df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(clave_busqueda, case=False, na=False)]
                    tot_serv = df_p[col_precio].sum()
                    st.session_state[f"serv_tot_{emp}"] = tot_serv
                    servicios_por_profesional[emp] = tot_serv

                # Cálculos específicos para modalidades de masajistas
                m_est, m_pub, m_tot = procesar_empleado("MAYDELY")
                if st.session_state.get("mod_Maydely Hernández", "Estándar") == "Estándar":
                    st.session_state["com_Maydely Hernández"] = m_est
                else:
                    st.session_state["com_Maydely Hernández"] = m_tot * 0.20

                l_est, l_pub, l_tot = procesar_empleado("LUIS")
                if st.session_state.get("mod_Luis Violante", "Estándar") == "Estándar":
                    st.session_state["com_Luis Violante"] = l_est
                else:
                    st.session_state["com_Luis Violante"] = l_tot * 0.20

                j_est, j_pub, j_tot = procesar_empleado("JESSICA")
                if st.session_state.get("mod_Jessica Lemus", "Estándar") == "Estándar":
                    st.session_state["com_Jessica Lemus"] = j_est
                else:
                    st.session_state["com_Jessica Lemus"] = j_tot * 0.20

                st.success("✅ ¡Reporte global PDF procesado! Se incluyeron todos los profesionales (Doctor y equipo).")
    except Exception as e:
        st.warning(f"Advertencia al leer PDF: {e}")

st.markdown("---")

# --- CREACIÓN DE PESTAÑAS GERENCIALES ---
tab_metas, tab_planillas, tab_memos, tab_amonestaciones, tab_auditoria = st.tabs([
    "📈 1. Dashboard de Metas y Finanzas",
    "📊 2. Control de Planillas", 
    "📝 3. Memorándums", 
    "⚠️ 4. Amonestaciones", 
    "🖨️ 5. Auditoría"
])

# ==========================================
# PESTAÑA 1: DASHBOARD GERENCIAL Y FINANCIERO
# ==========================================
with tab_metas:
    st.subheader("📈 Dashboard Gerencial: Rendimiento y Utilidad Neta")
    st.markdown("Análisis financiero completo de ingresos, cumplimiento del equipo y utilidad neta de la clínica.")

    meta_minima = st.number_input("Meta de Servicios Requerida ($):", value=300.0, step=50.0)

    if archivo_subido is not None and df_reporte is not None:
        # Calcular empleado estrella general (incluyendo al Dr. Gio y todos)
        mejor_empleado = ""
        mayor_venta = 0.0
        datos_grafica = {}

        metricas_lista = []
        for emp in empleados_lista:
            tot_serv = st.session_state.get(f"serv_tot_{emp}", 0.0)
            if tot_serv > 0:
                datos_grafica[emp.split()[0]] = tot_serv
            
            if tot_serv > mayor_venta:
                mayor_venta = tot_serv
                mejor_empleado = emp.split()[0]
                
            cumplio = "✅ Cumplida" if tot_serv >= meta_minima else "⚠️ No Cumplida"
            metricas_lista.append({
                "Empleado": emp,
                "Total Servicios ($)": tot_serv,
                "Meta ($)": meta_minima,
                "Estado": cumplio
            })

        # Nota: Calculamos provisionalmente el total de planillas para la utilidad neta
        costo_planilla_estimado = sum([
            (base_fijos if "Gio" in emp or "Gerson" in emp or "Edwin" in emp else base_masajistas) + 
            st.session_state.get(f"com_{emp}", 0.0) 
            for emp in empleados_lista
        ])
        utilidad_neta_clinica = total_ingresos_pdf - costo_planilla_estimado

        # Mostrar KPIs Financieros y Operativos Superiores
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Ingresos Brutos (PDF)", f"${total_ingresos_pdf:,.2f}")
        col2.metric("🏥 Utilidad Neta Clínica", f"${utilidad_neta_clinica:,.2f}", help="Ingresos brutos menos pago total de sueldos y comisiones de planillas")
        col3.metric("⭐ Empleado Estrella", f"{mejor_empleado}", f"${mayor_venta:,.2f}")
        col4.metric("🎯 Meta Actual", f"${meta_minima:,.2f}")

        st.markdown("#### 📊 Gráfica de Rendimiento Global (Incluyendo Doctor y Equipo)")
        if datos_grafica:
            st.bar_chart(pd.DataFrame.from_dict(datos_grafica, orient='index', columns=['Ventas ($)']))

        st.markdown("#### 📋 Detalle de Productividad por Colaborador")
        df_metas = pd.DataFrame(metricas_lista)
        st.dataframe(df_metas.style.format({"Total Servicios ($)": "{:.2f}", "Meta ($)": "{:.2f}"}), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### ✉️ Notificación de Rendimiento por Correo")
        emp_meta_sel = st.selectbox("Seleccionar colaborador:", empleados_lista, key="meta_emp_sel")
        datos_emp_sel = next(item for item in metricas_lista if item["Empleado"] == emp_meta_sel)
        email_meta = st.session_state.get(f"email_{emp_meta_sel}", "gersonmolina67@gmail.com")

        if st.button("🚀 Enviar Reporte de Meta al Empleado"):
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_meta
                msg['Subject'] = f"Reporte de Rendimiento - Gio Group"
                
                estado_texto = "¡Felicitaciones! Has superado la meta establecida. Tu desempeño destaca de forma sobresaliente." if datos_emp_sel["Estado"] == "✅ Cumplida" else "Te invitamos a incrementar el ritmo para alcanzar la meta establecida en el próximo periodo. ¡Confiamos en tu potencial!"
                
                cuerpo = f"""Estimado/a {emp_meta_sel},

Aquí tienes tu resumen de rendimiento del periodo actual:
- Total Generado en Servicios: ${datos_emp_sel['Total Servicios ($)']:.2f}
- Meta Requerida: ${datos_emp_sel['Meta ($)']:.2f}
- Estado de Meta: {datos_emp_sel['Estado']}

{estado_texto}

Atentamente,
Gerencia - Gio Group SAS de CV"""
                msg.attach(MIMEText(cuerpo, 'plain'))

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_meta, msg.as_string())
                server.quit()
                
                st.session_state["historial_auditoria"].append({"Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "Tipo": "Reporte Meta", "Destinatario": emp_meta_sel, "Correo": email_meta, "Detalle": datos_emp_sel['Estado']})
                st.success(f"¡Reporte enviado exitosamente a {email_meta}!")
            except Exception as e:
                st.error(f"Error al enviar correo: {e}")
    else:
        st.info("ℹ️ Sube un reporte de ingresos en PDF en la pestaña principal para ver el Dashboard interactivo y financiero.")

# ==========================================
# PESTAÑA 2: CONTROL DE PLANILLAS
# ==========================================
with tab_planillas:
    st.subheader("✍️ Ajustes, Nivelaciones y Planilla")
    
    datos_empleados = []

    for emp in empleados_lista:
        with st.expander(f"👤 {emp} - Configurar Pago"):
            col1, col2, col3 = st.columns(3)
            
            base_sugerido = base_fijos if "Gio" in emp or "Gerson" in emp or "Edwin" in emp else base_masajistas
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
                            nombre_corto = emp.split()[0]
                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre_corto, case=False, na=False)]
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
                    # Para el Dr. Gio u otros, la comisión puede ser leída del PDF o ajustada manualmente
                    tot_serv_doc = st.session_state.get(f"serv_tot_{emp}", 0.0)
                    if tot_serv_doc > 0 and "Gio" in emp:
                        # Si es el doctor, opcionalmente puede llevar un porcentaje o comisión directa de sus servicios
                        pass

                comision_extra = st.number_input(f"Comisión Real Generada ($) [{emp}]", key=f"com_{emp}", step=5.0)

            with col2:
                # Bonos / Nivelación exacta para llegar a la meta del empleado sin alterar su comisión real
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
                self.set_font('helvetica', 'B', 16)
                self.set_text_color(0, 86, 179)
                self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                self.set_font('helvetica', '', 10)
                self.set_text_color(100, 100, 100)
                self.cell(0, 5, f'Comprobante Oficial de Pago - Modalidad: {emp_data["Modalidad"]}', 0, 1, 'L')
                self.cell(0, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
                self.ln(5)

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
                    self.set_font('helvetica', 'B', 16)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    self.set_font('helvetica', '', 10)
                    self.cell(0, 5, 'MEMORANDUM OFICIAL', 0, 1, 'L')
                    self.ln(5)
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
                    self.set_font('helvetica', 'B', 16)
                    self.set_text_color(201, 42, 42)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    self.set_font('helvetica', '', 10)
                    self.cell(0, 5, 'ACTA OFICIAL DE AMONESTACION', 0, 1, 'L')
                    self.ln(5)
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
