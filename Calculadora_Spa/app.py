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

# --- OCULTAR ELEMENTOS DE STREAMLIT ---
esconder_menu = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
div[data-testid="stToolbar"] {visibility: hidden !important;}
.viewerBadge_container {display: none !important; visibility: hidden !important;}
[class*="viewerBadge"] {display: none !important; visibility: hidden !important;}
footer {visibility: hidden !important;}
</style>
"""
st.markdown(esconder_menu, unsafe_allow_html=True)

st.title("💆‍♂️ Gio Group SAS de CV - Panel Gerencial y Administrativo")

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

# Inicializar historial de auditoría global en sesión
if "historial_auditoria" not in st.session_state:
    st.session_state["historial_auditoria"] = []

# --- LECTOR DE PDF AUTOMÁTICO (COMPARTIDO) ---
st.subheader("📂 Reporte Global de Ingresos (PDF)")
archivo_subido = st.file_uploader("Sube el archivo PDF de ingresos para alimentar todo el sistema gerencial:", type=["pdf", "xlsx", "csv"])

df_reporte = None
if archivo_subido is not None:
    try:
        if archivo_subido.name.endswith('.pdf'):
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

                    def procesar_empleado(nombre_corto):
                        df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre_corto, case=False, na=False)]
                        tot_servicios = df_p[col_precio].sum()
                        
                        df_extras = df_p[df_p[col_precio] >= 60].copy()
                        df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                        total_bruto_extras = df_extras['EXTRA_BASE'].sum()
                        desc_pub = total_bruto_extras * 0.25
                        neto_estandar = max(0.0, total_bruto_extras - desc_pub)
                        
                        return neto_estandar, desc_pub, tot_servicios

                    # Maydely
                    m_est, m_pub, m_tot = procesar_empleado("MAYDELY")
                    st.session_state["serv_tot_Maydely Hernández"] = m_tot
                    if st.session_state.get("mod_Maydely Hernández", "Estándar") == "Estándar":
                        st.session_state["com_Maydely Hernández"] = m_est
                        st.session_state["pub_Maydely Hernández"] = m_pub
                    else:
                        st.session_state["com_Maydely Hernández"] = m_tot * 0.20
                        st.session_state["pub_Maydely Hernández"] = 0.0

                    # Luis
                    l_est, l_pub, l_tot = procesar_empleado("LUIS")
                    st.session_state["serv_tot_Luis Violante"] = l_tot
                    if st.session_state.get("mod_Luis Violante", "Estándar") == "Estándar":
                        st.session_state["com_Luis Violante"] = l_est
                        st.session_state["pub_Luis Violante"] = l_pub
                    else:
                        st.session_state["com_Luis Violante"] = l_tot * 0.20
                        st.session_state["pub_Luis Violante"] = 0.0

                    # Jessica
                    j_est, j_pub, j_tot = procesar_empleado("JESSICA")
                    st.session_state["serv_tot_Jessica Lemus"] = j_tot
                    if st.session_state.get("mod_Jessica Lemus", "Estándar") == "Estándar":
                        st.session_state["com_Jessica Lemus"] = j_est
                        st.session_state["pub_Jessica Lemus"] = j_pub
                    else:
                        st.session_state["com_Jessica Lemus"] = j_tot * 0.20
                        st.session_state["pub_Jessica Lemus"] = 0.0

                    st.success("¡Reporte PDF leído y sincronizado con éxito para todos los módulos!")
    except Exception as e:
        st.warning(f"Advertencia al leer PDF: {e}")

st.markdown("---")

# --- CREACIÓN DE PESTAÑAS GERENCIALES ---
tab_planillas, tab_memos, tab_amonestaciones, tab_metas, tab_auditoria = st.tabs([
    "📊 1. Control de Planillas", 
    "📝 2. Memorándums", 
    "⚠️ 3. Amonestaciones", 
    "📈 4. Metas y Rendimiento",
    "🖨️ 5. Historial de Envíos"
])

# ==========================================
# PESTAÑA 1: CONTROL DE PLANILLAS
# ==========================================
with tab_planillas:
    st.subheader("✍️ Ajustes, Comisiones y Modalidades por Empleado")
    
    datos_empleados = []

    for emp in empleados_lista:
        with st.expander(f"👤 {emp} - Configurar Planilla"):
            col1, col2, col3 = st.columns(3)
            
            base_sugerido = base_fijos if "Gio" in emp or "Gerson" in emp or "Edwin" in emp else base_masajistas
            desc_pub_actual = 0.0
            modalidad_str = "Estándar"

            with col1:
                sueldo_base = st.number_input(f"Sueldo Base ($) [{emp}]", value=float(base_sugerido), key=f"base_{emp}")
                
                if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                    modalidad = st.selectbox(
                        f"Modalidad de Pago [{emp}]", 
                        ["Estándar (Sueldo + Comisiones con 25% Publicidad)", "Porcentaje Directo (Ej. 20% sobre todo lo trabajado)"],
                        key=f"mod_{emp}"
                    )
                    
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
                        porc_def = 20
                        porc_personalizado = st.slider(f"Porcentaje Directo (%) [{emp}]", min_value=0, max_value=100, value=porc_def, key=f"porc_{emp}")
                        st.session_state[f"com_{emp}"] = tot_serv * (porc_personalizado / 100.0)
                        desc_pub_actual = 0.0
                else:
                    modalidad_str = "Administrativo/Fijo"

                comision_extra = st.number_input(f"Comisiones / Servicios ($) [{emp}]", key=f"com_{emp}", step=5.0)

            with col2:
                horas_extras = st.number_input(f"Horas Extra / Bonos ($) [{emp}]", value=0.0, key=f"hex_{emp}", step=5.0)
                descuentos_extras = st.number_input(f"Otros Descuentos ($) [{emp}]", value=0.0, key=f"desc_{emp}", step=5.0)
            
            with col3:
                nota_descuento = st.text_input(f"Nota / Motivo Descuento [{emp}]", value="Ninguno", key=f"nota_{emp}")
                email_emp = st.text_input(f"Correo Electrónico [{emp}]", key=f"email_{emp}")

            total_bruto = sueldo_base + comision_extra + horas_extras
            total_neto = total_bruto - descuentos_extras
            
            datos_empleados.append({
                "Empleado": emp,
                "Sueldo Base": sueldo_base,
                "Comisiones": comision_extra,
                "Horas Extra/Bonos": horas_extras,
                "Modalidad": modalidad_str,
                "Descuento Publicidad": desc_pub_actual,
                "Otros Descuentos": descuentos_extras,
                "Nota Descuento": nota_descuento,
                "Total a Pagar ($)": total_neto,
                "Email": email_emp
            })

    df_resumen = pd.DataFrame(datos_empleados)

    st.subheader("📋 Resumen General de Planilla")
    st.dataframe(
        df_resumen[["Empleado", "Sueldo Base", "Comisiones", "Modalidad", "Descuento Publicidad", "Total a Pagar ($)"]].style.format({
            "Sueldo Base": "{:.2f}", "Comisiones": "{:.2f}", "Descuento Publicidad": "{:.2f}", "Total a Pagar ($)": "{:.2f}"
        }),
        use_container_width=True,
        hide_index=True
    )

    # --- BOTÓN DE DESCARGA EXCEL GLOBAL ---
    output_excel = io.BytesIO()
    with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
        df_resumen.to_excel(writer, index=False, sheet_name='Planilla General')
    output_excel.seek(0)
    
    st.download_button(
        label="📥 Descargar Planilla Completa en Excel (.xlsx)",
        data=output_excel,
        file_name=f"Planilla_GioGroup_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.subheader("✉️ Envío y Revisión de Comprobantes")
    emp_sel_planilla = st.selectbox("Selecciona colaborador para gestionar recibo:", empleados_lista, key="sel_emp_plan")
    
    email_actual = st.session_state.get(f"email_{emp_sel_planilla}", "gersonmolina67@gmail.com")
    emp_data = next(item for item in datos_empleados if item["Empleado"] == emp_sel_planilla)
    emp_data["Email"] = email_actual

    # Generación del PDF físico para previsualizar y enviar
    class PDFPlanilla(FPDF):
        def header(self):
            self.set_font('helvetica', 'B', 16)
            self.set_text_color(0, 86, 179)
            self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
            self.set_font('helvetica', '', 10)
            self.set_text_color(100, 100, 100)
            self.cell(0, 5, f'Comprobante Oficial de Pago - Modalidad: {emp_data["Modalidad"]}', 0, 1, 'L')
            self.cell(0, 5, f"Fecha de Emision: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
            self.ln(5)
        def footer(self):
            self.set_y(-25)
            self.set_font('helvetica', 'I', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, 'Comprobante digital generado por el Sistema de Planillas de Gio Group SAS de CV.', 0, 0, 'C')

    pdf_p = PDFPlanilla()
    pdf_p.add_page()
    pdf_p.set_font('helvetica', 'B', 11)
    pdf_p.set_fill_color(240, 243, 246)
    pdf_p.set_text_color(50, 50, 50)
    pdf_p.cell(0, 10, f" Colaborador/a: {emp_data['Empleado']} ({emp_data['Modalidad']})", 0, 1, 'L', fill=True)
    pdf_p.ln(5)

    pdf_p.set_font('helvetica', 'B', 10)
    pdf_p.set_fill_color(0, 86, 179)
    pdf_p.set_text_color(255, 255, 255)
    pdf_p.cell(130, 8, ' Concepto de Ingreso / Deduccion', 1, 0, 'L', fill=True)
    pdf_p.cell(60, 8, ' Monto ($) ', 1, 1, 'R', fill=True)

    pdf_p.set_font('helvetica', '', 10)
    pdf_p.set_text_color(50, 50, 50)
    
    conceptos = [
        ("Sueldo Base", emp_data['Sueldo Base']),
        ("Comisiones y Servicios", emp_data['Comisiones']),
        ("Horas Extra / Bonos", emp_data['Horas Extra/Bonos'])
    ]
    for desc, val in conceptos:
        pdf_p.cell(130, 8, f"  {desc}", 1, 0, 'L')
        pdf_p.cell(60, 8, f"${val:.2f} ", 1, 1, 'R')

    if emp_data['Descuento Publicidad'] > 0:
        pdf_p.set_text_color(201, 42, 42)
        pdf_p.cell(130, 8, "  (-) Retención de 25% para Publicidad", 1, 0, 'L')
        pdf_p.cell(60, 8, f"-${emp_data['Descuento Publicidad']:.2f} ", 1, 1, 'R')
        pdf_p.set_text_color(50, 50, 50)

    if emp_data['Otros Descuentos'] > 0:
        pdf_p.set_text_color(201, 42, 42)
        pdf_p.cell(130, 8, "  (-) Otros Descuentos Aplicados", 1, 0, 'L')
        pdf_p.cell(60, 8, f"-${emp_data['Otros Descuentos']:.2f} ", 1, 1, 'R')
        pdf_p.set_text_color(50, 50, 50)

    pdf_p.set_font('helvetica', 'B', 11)
    pdf_p.set_fill_color(230, 235, 240)
    pdf_p.cell(130, 10, "  TOTAL NETO A RECIBIR", 1, 0, 'L', fill=True)
    pdf_p.cell(60, 10, f"${emp_data['Total a Pagar ($)']:.2f} ", 1, 1, 'R', fill=True)
    pdf_p.ln(8)

    pdf_path = f"Recibo_{emp_sel_planilla.replace(' ', '_')}.pdf"
    pdf_p.output(pdf_path)

    # Vista previa segura con botón de descarga directa
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
        
    st.info("💡 El recibo ha sido generado. Puedes descargarlo para revisarlo antes de enviarlo por correo.")
    
    st.download_button(
        label="📄 Descargar Recibo PDF para Revisión",
        data=pdf_bytes,
        file_name=pdf_path,
        mime="application/pdf"
    )

    if st.button("🚀 Confirmar y Enviar Recibo por Correo"):
        if not emp_data["Email"] or "@" not in emp_data["Email"]:
            st.error(f"⚠️ El empleado {emp_sel_planilla} no tiene un correo válido.")
        else:
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = emp_data['Email']
                msg['Subject'] = f"Comprobante de Pago Oficial - {emp_data['Modalidad']} - Gio Group"
                cuerpo = f"Estimado/a {emp_sel_planilla},\n\nAdjunto su comprobante de pago oficial.\nTotal Neto: ${emp_data['Total a Pagar ($)']:.2f}\n\nAtentamente,\nGio Group SAS de CV"
                msg.attach(MIMEText(cuerpo, 'plain'))
                with open(pdf_path, "rb") as f:
                    adj = MIMEApplication(f.read(), Name=pdf_path)
                adj['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
                msg.attach(adj)

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, emp_data['Email'], msg.as_string())
                server.quit()
                
                # Registrar en auditoría
                st.session_state["historial_auditoria"].append({
                    "Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "Tipo": "Recibo de Planilla",
                    "Destinatario": emp_sel_planilla,
                    "Correo": emp_data['Email'],
                    "Monto/Detalle": f"${emp_data['Total a Pagar ($)']:.2f}"
                })
                
                st.success(f"¡Recibo enviado con éxito a {emp_data['Email']} y registrado en auditoría!")
            except Exception as ex:
                st.error(f"Error al enviar correo: {ex}")

# ==========================================
# PESTAÑA 2: MEMORÁNDUMS
# ==========================================
with tab_memos:
    st.subheader("📝 Emisión y Envío de Memorándums Internos")
    st.markdown("Redacta notas formales, acuerdos o avisos gerenciales para el personal:")

    emp_memo = st.selectbox("Colaborador destinatario:", empleados_lista, key="memo_emp")
    asunto_memo = st.text_input("Asunto del Memorándum:", value="Aviso Administrativo / Comunicado Interno")
    texto_memo = st.text_area("Cuerpo o notas del Memorándum:", placeholder="Escribe aquí los detalles del acuerdo o asunto tratado...")
    email_memo = st.text_input("Correo de envío:", value=st.session_state.get(f"email_{emp_memo}", "gersonmolina67@gmail.com"), key="email_memo_input")

    if texto_memo:
        class PDFMemo(FPDF):
            def header(self):
                self.set_font('helvetica', 'B', 16)
                self.set_text_color(0, 86, 179)
                self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                self.set_font('helvetica', '', 10)
                self.set_text_color(100, 100, 100)
                self.cell(0, 5, 'DEPARTAMENTO ADMINISTRATIVO - MEMORÁNDUM OFICIAL', 0, 1, 'L')
                self.cell(0, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
                self.ln(5)
            def footer(self):
                self.set_y(-25)
                self.set_font('helvetica', 'I', 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 10, 'Documento oficial interno emitido por la Gerencia de Gio Group SAS de CV.', 0, 0, 'C')

        pdf_m = PDFMemo()
        pdf_m.add_page()
        pdf_m.set_font('helvetica', 'B', 11)
        pdf_m.set_fill_color(240, 243, 246)
        pdf_m.set_text_color(50, 50, 50)
        pdf_m.cell(0, 10, f" Para: {emp_memo}", 0, 1, 'L', fill=True)
        pdf_m.cell(0, 10, f" Asunto: {asunto_memo}", 0, 1, 'L', fill=True)
        pdf_m.ln(5)
        pdf_m.set_font('helvetica', '', 11)
        pdf_m.multi_cell(0, 7, texto_memo, 0, 'L')
        pdf_m.ln(15)
        pdf_m.cell(60, 10, "____________________________", 0, 1, 'L')
        pdf_m.cell(60, 5, "Administración / Gerencia", 0, 1, 'L')

        memo_path = f"Memorandum_{emp_memo.replace(' ', '_')}.pdf"
        pdf_m.output(memo_path)

        with open(memo_path, "rb") as f:
            memo_bytes = f.read()
            
        st.info("💡 El Memorándum ha sido generado. Puedes descargarlo para revisarlo antes de enviarlo por correo.")
        
        st.download_button(
            label="📄 Descargar Memorándum PDF para Revisión",
            data=memo_bytes,
            file_name=memo_path,
            mime="application/pdf",
            key="down_memo"
        )

    if st.button("🚀 Confirmar y Enviar Memorándum por Correo"):
        if not texto_memo:
            st.error("⚠️ Debes redactar el contenido del memorándum.")
        else:
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_memo
                msg['Subject'] = f"MEMORÁNDUM OFICIAL: {asunto_memo} - Gio Group"
                cuerpo = f"Estimado/a {emp_memo},\n\nAdjunto encontrará un memorándum oficial emitido por la administración.\n\nAtentamente,\nGerencia - Gio Group SAS de CV"
                msg.attach(MIMEText(cuerpo, 'plain'))
                with open(memo_path, "rb") as f:
                    adj = MIMEApplication(f.read(), Name=memo_path)
                adj['Content-Disposition'] = f'attachment; filename="{memo_path}"'
                msg.attach(adj)

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_memo, msg.as_string())
                server.quit()
                
                st.session_state["historial_auditoria"].append({
                    "Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "Tipo": "Memorándum",
                    "Destinatario": emp_memo,
                    "Correo": email_memo,
                    "Monto/Detalle": asunto_memo
                })
                
                st.success(f"¡Memorándum enviado por correo a {email_memo} y registrado en auditoría!")
            except Exception as e:
                st.error(f"Error al enviar memorándum: {e}")

# ==========================================
# PESTAÑA 3: AMONESTACIONES
# ==========================================
with tab_amonestaciones:
    st.subheader("⚠️ Registro de Amonestaciones y Llamadas de Atención")
    st.markdown("Documenta faltas o incumplimientos para el expediente del colaborador:")

    emp_amon = st.selectbox("Colaborador:", empleados_lista, key="amon_emp")
    tipo_falta = st.selectbox("Gravedad / Tipo de Falta:", ["Llamada de Atención Verbal (Registro)", "Amonestación Escrita Leve", "Amonestación Escrita Grave"])
    motivo_amon = st.text_area("Motivo detallado de la amonestación:", placeholder="Describe claramente el motivo, fecha, hora y detalles de la falta...")
    email_amon = st.text_input("Correo de envío confidencial:", value=st.session_state.get(f"email_{emp_amon}", "gersonmolina67@gmail.com"), key="email_amon_input")

    if motivo_amon:
        class PDFAmonestacion(FPDF):
            def header(self):
                self.set_font('helvetica', 'B', 16)
                self.set_text_color(201, 42, 42)
                self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                self.set_font('helvetica', '', 10)
                self.set_text_color(100, 100, 100)
                self.cell(0, 5, 'ACTA OFICIAL DE AMONESTACIÓN / LLAMADA DE ATENCIÓN', 0, 1, 'L')
                self.cell(0, 5, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
                self.ln(5)
            def footer(self):
                self.set_y(-25)
                self.set_font('helvetica', 'I', 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 10, 'Este documento pasa a formar parte del expediente laboral en Gio Group SAS de CV.', 0, 0, 'C')

        pdf_a = PDFAmonestacion()
        pdf_a.add_page()
        pdf_a.set_font('helvetica', 'B', 11)
        pdf_a.set_fill_color(255, 235, 235)
        pdf_a.set_text_color(50, 50, 50)
        pdf_a.cell(0, 10, f" Colaborador/a: {emp_amon}", 0, 1, 'L', fill=True)
        pdf_a.cell(0, 10, f" Clasificación: {tipo_falta}", 0, 1, 'L', fill=True)
        pdf_a.ln(5)
        pdf_a.set_font('helvetica', 'B', 10)
        pdf_a.set_text_color(201, 42, 42)
        pdf_a.cell(0, 6, "Motivo e Incidentes Reportados:", 0, 1, 'L')
        pdf_a.set_font('helvetica', '', 11)
        pdf_a.set_text_color(50, 50, 50)
        pdf_a.multi_cell(0, 7, motivo_amon, 1, 'L')
        pdf_a.ln(15)
        pdf_a.cell(60, 10, "____________________________", 0, 1, 'L')
        pdf_a.cell(60, 5, "Recibido de Conformidad (Colaborador)", 0, 1, 'L')

        amon_path = f"Amonestacion_{emp_amon.replace(' ', '_')}.pdf"
        pdf_a.output(amon_path)

        with open(amon_path, "rb") as f:
            amon_bytes = f.read()
            
        st.info("💡 El acta de amonestación ha sido generada. Puedes descargarla para revisión.")
        
        st.download_button(
            label="📄 Descargar Amonestación PDF para Revisión",
            data=amon_bytes,
            file_name=amon_path,
            mime="application/pdf",
            key="down_amon"
        )

    if st.button("🚀 Confirmar y Enviar Amonestación por Correo"):
        if not motivo_amon:
            st.error("⚠️ Debes detallar el motivo de la amonestación.")
        else:
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_amon
                msg['Subject'] = f"NOTIFICACIÓN ADMINISTRATIVA: {tipo_falta} - Gio Group"
                cuerpo = f"Estimado/a {emp_amon},\n\nAdjunto documento oficial de amonestación registrado en su expediente.\n\nAtentamente,\nRecursos Humanos - Gio Group SAS de CV"
                msg.attach(MIMEText(cuerpo, 'plain'))
                with open(amon_path, "rb") as f:
                    adj = MIMEApplication(f.read(), Name=amon_path)
                adj['Content-Disposition'] = f'attachment; filename="{amon_path}"'
                msg.attach(adj)

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_amon, msg.as_string())
                server.quit()
                
                st.session_state["historial_auditoria"].append({
                    "Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "Tipo": "Amonestación",
                    "Destinatario": emp_amon,
                    "Correo": email_amon,
                    "Monto/Detalle": tipo_falta
                })
                
                st.success(f"¡Amonestación registrada, enviada a {email_amon} y guardada en auditoría!")
            except Exception as e:
                st.error(f"Error al enviar amonestación: {e}")

# ==========================================
# PESTAÑA 4: METAS Y RENDIMIENTO
# ==========================================
with tab_metas:
    st.subheader("📈 Control de Metas y Rendimiento por Servicios")
    st.markdown("Cruza los datos del reporte de ingresos para evaluar el cumplimiento de objetivos del personal:")

    meta_minima = st.number_input("Meta Mínima de Servicios por Periodo ($):", value=300.0, step=50.0)

    if archivo_subido is not None and df_reporte is not None:
        metricas_lista = []
        for emp in empleados_lista:
            tot_serv = st.session_state.get(f"serv_tot_{emp}", 0.0)
            cumplio = "✅ Cumplida" if tot_serv >= meta_minima else "⚠️ No Cumplida"
            
            metricas_lista.append({
                "Empleado": emp,
                "Total Servicios Vendidos ($)": tot_serv,
                "Meta Establecida ($)": meta_minima,
                "Estado": cumplio
            })

        df_metas = pd.DataFrame(metricas_lista)
        st.dataframe(
            df_metas.style.format({"Total Servicios Vendidos ($)": "{:.2f}", "Meta Establecida ($)": "{:.2f}"}),
            use_container_width=True,
            hide_index=True
        )

        st.markdown("### ✉️ Notificación de Rendimiento")
        emp_meta_sel = st.selectbox("Seleccionar empleado para enviar reporte de meta:", empleados_lista, key="meta_emp_sel")
        datos_emp_sel = next(item for item in metricas_lista if item["Empleado"] == emp_meta_sel)
        email_meta = st.session_state.get(f"email_{emp_meta_sel}", "gersonmolina67@gmail.com")

        if st.button("🚀 Enviar Alerta o Reporte de Meta por Correo"):
            try:
                remitente_email = st.secrets["EMAIL_USER"]
                password_email = st.secrets["EMAIL_PASS"]
                msg = MIMEMultipart()
                msg['From'] = remitente_email
                msg['To'] = email_meta
                msg['Subject'] = f"Reporte de Rendimiento y Metas - Gio Group"
                
                estado_texto = "¡Felicitaciones! Has cumplido con la meta establecida." if datos_emp_sel["Estado"] == "✅ Cumplida" else "Te invitamos a incrementar el ritmo de servicios para alcanzar la meta establecida en el próximo periodo."
                
                cuerpo = f"""Estimado/a {emp_meta_sel},

Aquí tienes tu resumen de rendimiento del periodo actual:
- Total de Servicios Realizados: ${datos_emp_sel['Total Servicios Vendidos ($)']:.2f}
- Meta Requerida: ${datos_emp_sel['Meta Establecida ($)']:.2f}
- Estado: {datos_emp_sel['Estado']}

{estado_texto}

Atentamente,
Gerencia - Gio Group SAS de CV"""
                msg.attach(MIMEText(cuerpo, 'plain'))

                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente_email, password_email)
                server.sendmail(remitente_email, email_meta, msg.as_string())
                server.quit()
                
                st.session_state["historial_auditoria"].append({
                    "Fecha": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "Tipo": "Reporte de Metas",
                    "Destinatario": emp_meta_sel,
                    "Correo": email_meta,
                    "Monto/Detalle": datos_emp_sel['Estado']
                })
                
                st.success(f"¡Reporte de metas enviado exitosamente a {email_meta} y registrado en auditoría!")
            except Exception as e:
                st.error(f"Error al enviar correo de metas: {e}")
    else:
        st.info("ℹ️ Sube un reporte de ingresos en PDF en la parte superior para habilitar el análisis automático de metas.")

# ==========================================
# PESTAÑA 5: HISTORIAL DE ENVÍOS (AUDITORÍA)
# ==========================================
with tab_auditoria:
    st.subheader("🖨️ Historial y Registro de Correos Enviados")
    st.markdown("Registro gerencial en tiempo real de todos los documentos y recibos despachados:")

    if len(st.session_state["historial_auditoria"]) > 0:
        df_audit = pd.DataFrame(st.session_state["historial_auditoria"])
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
        
        # Botón para descargar el log de auditoría en Excel
        out_aud = io.BytesIO()
        with pd.ExcelWriter(out_aud, engine='openpyxl') as w:
            df_audit.to_excel(w, index=False, sheet_name='Auditoria')
        out_aud.seek(0)
        
        st.download_button(
            label="📥 Descargar Historial en Excel (.xlsx)",
            data=out_aud,
            file_name=f"Auditoria_Envios_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("ℹ️ Aún no se han enviado correos en esta sesión. Los registros aparecerán aquí automáticamente conforme vayas despachando recibos, memorándums o amonestaciones.")
