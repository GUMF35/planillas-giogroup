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

st.title("💆‍♂️ Gio Group SAS de CV - Control Integral de Planillas")

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

# Inicializar memoria de sesión para comisiones y totales de servicios
for emp in empleados_lista:
    if f"com_{emp}" not in st.session_state:
        st.session_state[f"com_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state:
        st.session_state[f"serv_tot_{emp}"] = 0.0

# --- LECTOR DE PDF AUTOMÁTICO ---
st.subheader("📂 Reporte de Ingresos (PDF)")
archivo_subido = st.file_uploader("Sube el archivo PDF de ingresos aquí", type=["pdf", "xlsx", "csv"])

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
                        df_prof = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre_corto, case=False, na=False)]
                        tot_servicios = df_prof[col_precio].sum()
                        
                        df_extras = df_prof[df_prof[col_precio] >= 60].copy()
                        df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                        total_bruto_extras = df_extras['EXTRA_BASE'].sum()
                        desc_pub = total_bruto_extras * 0.25
                        neto_estandar = max(0.0, total_bruto_extras - desc_pub)
                        
                        return neto_estandar, desc_pub, tot_servicios

                    # Maydely
                    m_est, m_pub, m_tot = procesar_empleado("MAYDELY")
                    st.session_state["serv_tot_Maydely Hernández"] = m_tot
                    if st.session_state.get(f"mod_Maydely Hernández", "Estándar") == "Estándar":
                        st.session_state["com_Maydely Hernández"] = m_est
                        st.session_state["pub_Maydely Hernández"] = m_pub
                    else:
                        st.session_state["com_Maydely Hernández"] = m_tot * 0.20
                        st.session_state["pub_Maydely Hernández"] = 0.0

                    # Luis
                    l_est, l_pub, l_tot = procesar_empleado("LUIS")
                    st.session_state["serv_tot_Luis Violante"] = l_tot
                    if st.session_state.get(f"mod_Luis Violante", "Estándar") == "Estándar":
                        st.session_state["com_Luis Violante"] = l_est
                        st.session_state["pub_Luis Violante"] = l_pub
                    else:
                        st.session_state["com_Luis Violante"] = l_tot * 0.20
                        st.session_state["pub_Luis Violante"] = 0.0

                    # Jessica
                    j_est, j_pub, j_tot = procesar_empleado("JESSICA")
                    st.session_state["serv_tot_Jessica Lemus"] = j_tot
                    if st.session_state.get(f"mod_Jessica Lemus", "Estándar") == "Estándar":
                        st.session_state["com_Jessica Lemus"] = j_est
                        st.session_state["pub_Jessica Lemus"] = j_pub
                    else:
                        st.session_state["com_Jessica Lemus"] = j_tot * 0.20
                        st.session_state["pub_Jessica Lemus"] = 0.0

                    st.success("¡Reporte PDF leído y comisiones sumadas con éxito!")
    except Exception as e:
        st.warning(f"Advertencia al leer PDF: {e}")

# --- PANEL DE PERSONALIZACIÓN Y MODALIDADES ---
st.subheader("✍️ Ajustes, Comisiones y Modalidades por Empleado")
st.markdown("Elige el esquema de pago para cada colaborador. Las comisiones se actualizarán y sumarán automáticamente:")

datos_empleados = []

for emp in empleados_lista:
    with st.expander(f"👤 {emp} - Configurar Planilla y Modalidad"):
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
                    df_aux = locals().get('df_reporte', None)
                    if df_aux is not None and 'col_prof' in locals() and 'col_precio' in locals():
                        nombre_corto = emp.split()[0]
                        df_p = df_aux[df_aux[col_prof].astype(str).str.contains(nombre_corto, case=False, na=False)]
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

            comision_extra = st.number_input(
                f"Comisiones / Servicios ($) [{emp}]", 
                key=f"com_{emp}", 
                step=5.0
            )

        with col2:
            horas_extras = st.number_input(f"Horas Extra / Bonos ($) [{emp}]", value=0.0, key=f"hex_{emp}", step=5.0)
            descuentos_extras = st.number_input(f"Otros Descuentos ($) [{emp}]", value=0.0, key=f"desc_{emp}", step=5.0)
        
        with col3:
            nota_descuento = st.text_input(f"Nota / Motivo Descuento [{emp}]", value="Ninguno", key=f"nota_{emp}")
            email_emp = st.text_input(f"Correo Electrónico [{emp}]", value="gersonmolina67@gmail.com" if "Gerson" in emp else "", key=f"email_{emp}")

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
st.dataframe(df_resumen[["Empleado", "Sueldo Base", "Comisiones", "Modalidad", "Descuento Publicidad", "Total a Pagar ($)"]].style.format({
    "Sueldo Base": "{:.2f}", "Comisiones": "{:.2f}", "Descuento Publicidad": "{:.2f}", "Total a Pagar ($)": "{:.2f}"
}))

# --- APARTADO DE CORREOS Y RECIBOS PDF ---
st.subheader("✉️ Enviar Comprobantes en PDF por Gmail")
empleado_seleccionado = st.selectbox("Selecciona a quién generar y enviar el recibo:", empleados_lista)

emp_data = next(item for item in datos_empleados if item["Empleado"] == empleado_seleccionado)

if st.button("Generar PDF y Enviar por Correo"):
    if not emp_data["Email"]:
        st.error(f"⚠️ El empleado {empleado_seleccionado} no tiene un correo electrónico válido registrado.")
    else:
        try:
            class PDF(FPDF):
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
                    self.cell(0, 10, 'Este documento es un comprobante digital generado por el Sistema de Planillas de Gio Group SAS de CV.', 0, 0, 'C')

            pdf = PDF()
            pdf.add_page()
            
            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(240, 243, 246)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 10, f" Colaborador/a: {emp_data['Empleado']} ({emp_data['Modalidad']})", 0, 1, 'L', fill=True)
            pdf.ln(5)

            pdf.set_font('helvetica', 'B', 10)
            pdf.set_fill_color(0, 86, 179)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(130, 8, ' Concepto de Ingreso / Deduccion', 1, 0, 'L', fill=True)
            pdf.cell(60, 8, ' Monto ($) ', 1, 1, 'R', fill=True)

            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(50, 50, 50)
            
            conceptos = [
                ("Sueldo Base", emp_data['Sueldo Base']),
                ("Comisiones y Servicios", emp_data['Comisiones']),
                ("Horas Extra / Bonos", emp_data['Horas Extra/Bonos'])
            ]

            for desc, val in conceptos:
                pdf.cell(130, 8, f"  {desc}", 1, 0, 'L')
                pdf.cell(60, 8, f"${val:.2f} ", 1, 1, 'R')

            if emp_data['Descuento Publicidad'] > 0:
                pdf.set_text_color(201, 42, 42)
                pdf.cell(130, 8, "  (-) Retención de 25% para Publicidad", 1, 0, 'L')
                pdf.cell(60, 8, f"-${emp_data['Descuento Publicidad']:.2f} ", 1, 1, 'R')
                pdf.set_text_color(50, 50, 50)

            if emp_data['Otros Descuentos'] > 0:
                pdf.set_text_color(201, 42, 42)
                pdf.cell(130, 8, "  (-) Otros Descuentos Aplicados", 1, 0, 'L')
                pdf.cell(60, 8, f"-${emp_data['Otros Descuentos']:.2f} ", 1, 1, 'R')
                pdf.set_text_color(50, 50, 50)

            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(230, 235, 240)
            pdf.cell(130, 10, "  TOTAL NETO A RECIBIR", 1, 0, 'L', fill=True)
            pdf.cell(60, 10, f"${emp_data['Total a Pagar ($)']:.2f} ", 1, 1, 'R', fill=True)
            pdf.ln(8)

            pdf.set_font('helvetica', 'B', 10)
            pdf.set_text_color(0, 86, 179)
            pdf.cell(0, 6, "Motivo / Notas de Descuentos o Deducciones:", 0, 1, 'L')
            
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(50, 50, 50)
            nota_completa = f"Nota: {emp_data['Nota Descuento']}"
            if emp_data['Modalidad'] == "Estándar" and emp_data['Descuento Publicidad'] > 0:
                nota_completa += " | Incluye retención del 25% destinada a publicidad institucional."
            elif emp_data['Modalidad'] == "Porcentaje Directo":
                nota_completa += " | Modalidad de porcentaje directo aplicada (sin deducción de publicidad)."
            
            pdf.multi_cell(0, 6, nota_completa, 1, 'L')

            pdf_path = f"Recibo_{empleado_seleccionado.replace(' ', '_')}.pdf"
            pdf.output(pdf_path)

            remitente_email = st.secrets["EMAIL_USER"]
            password_email = st.secrets["EMAIL_PASS"]

            msg = MIMEMultipart()
            msg['From'] = remitente_email
            msg['To'] = emp_data['Email']
            msg['Subject'] = f"Comprobante de Pago Oficial - {emp_data['Modalidad']} - Gio Group SAS de CV"

            cuerpo = f"""Estimado/a {empleado_seleccionado},

Adjunto encontrará su comprobante de pago oficial correspondiente al periodo bajo la modalidad: {emp_data['Modalidad']}.
Monto Total Neto a Recibir: ${emp_data['Total a Pagar ($)']:.2f}

Atentamente,
Gio Group SAS de CV"""
            msg.attach(MIMEText(cuerpo, 'plain'))

            with open(pdf_path, "rb") as f:
                adjunto = MIMEApplication(f.read(), Name=pdf_path)
            adjunto['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
            msg.attach(adjunto)

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(remitente_email, password_email)
            server.sendmail(remitente_email, emp_data['Email'], msg.as_string())
            server.quit()

            st.success(f"¡Recibo en PDF generado y enviado con éxito a {emp_data['Email']}!")

        except Exception as ex:
            st.error(f"Error al generar o enviar el recibo: {ex}")
