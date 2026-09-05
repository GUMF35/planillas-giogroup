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

# --- CONFIGURACIÓN LATERAL ---
st.sidebar.header("⚙️ Configuración General")
periodo = st.sidebar.radio("Selecciona el periodo:", ("Quincenal", "Mensual"))

base_masajistas = st.sidebar.number_input("Sueldo Base Masajistas/Ventas ($):", value=183.96 if periodo == "Quincenal" else 367.92, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Administrativo ($):", value=300.00 if periodo == "Quincenal" else 600.00, step=10.0)

# --- LECTOR DE PDF (OPCIONAL) ---
st.write("📂 **Sube tu reporte de ingresos en PDF** (opcional, para referencia):")
archivo_subido = st.file_uploader("Sube tu archivo aquí", type=["pdf", "xlsx", "csv"])

df = None
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
                df = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
    except Exception as e:
        st.warning(f"Aviso de lectura de archivo: {e}")

# --- PANEL DE AJUSTE MANUAL Y DETALLADO POR EMPLEADO ---
st.subheader("✍️ Detalle y Ajustes por Empleado")
st.markdown("Personaliza comisiones, horas extra, bonos y notas de descuentos para cada integrante:")

empleados_lista = [
    "Maydely Hernández", 
    "Luis Violante", 
    "Jessica Lemus", 
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)", 
    "Gerson Ulises Molina Flores", 
    "Edwin Ponce", 
    "Mario de Paz"
]

datos_empleados = []

for emp in empleados_lista:
    with st.expander(f"👤 {emp} - Ajustar Pagos y Descuentos"):
        col1, col2, col3 = st.columns(3)
        
        base_sugerido = base_fijos if "Gio" in emp or "Gerson" in emp or "Edwin" in emp else base_masajistas
        
        with col1:
            sueldo_base = st.number_input(f"Sueldo Base ($) [{emp}]", value=float(base_sugerido), key=f"base_{emp}")
            comision_extra = st.number_input(f"Comisiones / Servicios ($) [{emp}]", value=0.0, key=f"com_{emp}")
        with col2:
            horas_extras = st.number_input(f"Horas Extra / Bonos ($) [{emp}]", value=0.0, key=f"hex_{emp}")
            descuentos = st.number_input(f"Total Descuentos ($) [{emp}]", value=0.0, key=f"desc_{emp}")
        with col3:
            nota_descuento = st.text_input(f"Nota / Motivo de Descuento [{emp}]", value="Ninguno", key=f"nota_{emp}")
            email_emp = st.text_input(f"Correo Electrónico [{emp}]", value="gersonmolina67@gmail.com" if "Gerson" in emp else "", key=f"email_{emp}")

        total_bruto = sueldo_base + comision_extra + horas_extras
        total_neto = total_bruto - descuentos
        
        datos_empleados.append({
            "Empleado": emp,
            "Sueldo Base": sueldo_base,
            "Comisiones": comision_extra,
            "Horas Extra/Bonos": horas_extras,
            "Descuentos": descuentos,
            "Nota Descuento": nota_descuento,
            "Total a Pagar ($)": total_neto,
            "Email": email_emp
        })

df_resumen = pd.DataFrame(datos_empleados)

st.subheader("📋 Resumen General de Planilla")
st.dataframe(df_resumen[["Empleado", "Sueldo Base", "Comisiones", "Horas Extra/Bonos", "Descuentos", "Total a Pagar ($)"]].style.format({
    "Sueldo Base": "{:.2f}", "Comisiones": "{:.2f}", "Horas Extra/Bonos": "{:.2f}", "Descuentos": "{:.2f}", "Total a Pagar ($)": "{:.2f}"
}))

# --- APARTADO DE GENERACIÓN Y ENVÍO DE RECIBOS PROFESIONALES ---
st.subheader("✉️ Enviar Comprobantes en PDF por Gmail")
empleado_seleccionado = st.selectbox("Selecciona a quién generar y enviar el recibo:", empleados_lista)

emp_data = next(item for item in datos_empleados if item["Empleado"] == empleado_seleccionado)

if st.button("Generar PDF y Enviar por Correo"):
    if not emp_data["Email"]:
        st.error(f"⚠️ El empleado {empleado_seleccionado} no tiene un correo electrónico válido registrado.")
    else:
        try:
            # Generar PDF limpio y profesional con FPDF
            class PDF(FPDF):
                def header(self):
                    self.set_font('helvetica', 'B', 16)
                    self.set_text_color(0, 86, 179)
                    self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    self.set_font('helvetica', '', 10)
                    self.set_text_color(100, 100, 100)
                    self.cell(0, 5, f'Comprobante Oficial de Pago - Periodo: {periodo}', 0, 1, 'L')
                    self.cell(0, 5, f"Fecha de Emision: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'L')
                    self.ln(5)

                def footer(self):
                    self.set_y(-25)
                    self.set_font('helvetica', 'I', 8)
                    self.set_text_color(150, 150, 150)
                    self.cell(0, 10, 'Este documento es un comprobante digital generado por el Sistema de Planillas de Gio Group SAS de CV.', 0, 0, 'C')

            pdf = PDF()
            pdf.add_page()
            
            # Caja de datos del empleado
            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(240, 243, 246)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 10, f" Colaborador/a: {emp_data['Empleado']}", 0, 1, 'L', fill=True)
            pdf.ln(5)

            # Tabla de conceptos
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
                ("Horas Extra / Bonos", emp_data['Horas Extra/Bonos']),
                ("Descuentos Aplicados", -emp_data['Descuentos'])
            ]

            for desc, val in conceptos:
                pdf.cell(130, 8, f"  {desc}", 1, 0, 'L')
                pdf.cell(60, 8, f"${val:.2f} ", 1, 1, 'R')

            # Fila Total Neto
            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(230, 235, 240)
            pdf.cell(130, 10, "  TOTAL NETO A RECIBIR", 1, 0, 'L', fill=True)
            pdf.cell(60, 10, f"${emp_data['Total a Pagar ($)']:.2f} ", 1, 1, 'R', fill=True)
            pdf.ln(8)

            # Apartado de Notas
            pdf.set_font('helvetica', 'B', 10)
            pdf.set_text_color(0, 86, 179)
            pdf.cell(0, 6, "Motivo / Nota de Descuentos o Ajustes:", 0, 1, 'L')
            
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, emp_data['Nota Descuento'], 1, 'L')

            # Guardar PDF localmente
            pdf_path = f"Recibo_{empleado_seleccionado.replace(' ', '_')}.pdf"
            pdf.output(pdf_path)

            # Envío por correo utilizando los Secrets configurados
            remitente_email = st.secrets["EMAIL_USER"]
            password_email = st.secrets["EMAIL_PASS"]

            msg = MIMEMultipart()
            msg['From'] = remitente_email
            msg['To'] = emp_data['Email']
            msg['Subject'] = f"Comprobante de Pago Oficial - {periodo} - Gio Group SAS de CV"

            cuerpo = f"""Estimado/a {empleado_seleccionado},

Adjunto encontrará su recibo y comprobante de pago oficial correspondiente al periodo {periodo}.
Monto Total Neto a Recibir: ${emp_data['Total a Pagar ($)']:.2f}

Cualquier duda o aclaración sobre los montos o notas de descuento descritas en el PDF adjunto, por favor comunicarse con administración.

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
