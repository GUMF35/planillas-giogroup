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
from weasyprint import HTML

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
comision_jessica_def = st.sidebar.slider("Comisión Estándar Jessica (%):", min_value=0, max_value=100, value=20) / 100

# --- LECTOR DE PDF (OPCIONAL PARA EXTRAS AUTOMÁTICOS) ---
st.write("📂 **Sube tu reporte de ingresos en PDF** (opcional, para extraer datos base o ingresarlos manualmente abajo):")
archivo_subido = st.file_uploader("Sube tu archivo aquí", type=["pdf", "xlsx", "csv"])

# Extracción inicial si hay archivo
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
        st.warning(f"No se pudo leer automáticamente el PDF, se usarán valores manuales: {e}")

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

# Contenedores en pestañas o desplegables limpios para editar a cada uno
for emp in empleados_lista:
    with st.expander(f"👤 {emp} - Ajustar Pagos y Descuentos"):
        col1, col2, col3 = st.columns(3)
        
        # Asignar sueldo base según puesto
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

        # Cálculo Neto Individual
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
st.subheader("✉️ Enviar Recibos Profesionales en PDF por Gmail")
empleado_seleccionado = st.selectbox("Selecciona a quién generar y enviar el recibo:", empleados_lista)

# Buscar datos del empleado seleccionado
emp_data = next(item for item in datos_empleados if item["Empleado"] == empleado_seleccionado)

if st.button("Generar PDF y Enviar por Correo"):
    if not emp_data["Email"]:
        st.error(f"⚠️ El empleado {empleado_seleccionado} no tiene un correo electrónico válido registrado.")
    else:
        try:
            # 1. Crear el diseño HTML profesional del recibo
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <style>
                @page {{ size: A4; margin: 20mm; background-color: #ffffff; }}
                body {{ font-family: 'Helvetica', Arial, sans-serif; color: #333333; margin: 0; padding: 0; }}
                .header {{ border-bottom: 2px solid #0056b3; padding-bottom: 10px; margin-bottom: 20px; }}
                .header h1 {{ margin: 0; color: #0056b3; font-size: 22px; }}
                .header p {{ margin: 2px 0; color: #666; font-size: 12px; }}
                .info-box {{ background-color: #f8f9fa; border-left: 4px solid #0056b3; padding: 10px; margin-bottom: 20px; font-size: 13px; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #dee2e6; }}
                th {{ background-color: #f1f3f5; color: #333; }}
                .total-row {{ font-weight: bold; background-color: #e9ecef; }}
                .notes {{ background-color: #fff3cd; border: 1px solid #ffeeba; padding: 10px; border-radius: 4px; font-size: 12px; margin-top: 15px; }}
                .footer {{ margin-top: 40px; text-align: center; font-size: 11px; color: #888; border-top: 1px solid #eee; padding-top: 10px; }}
            </style>
            </head>
            <body>
                <div class="header">
                    <h1>GIO GROUP SAS DE CV</h1>
                    <p>Comprobante Oficial de Pago - Periodo: {periodo}</p>
                    <p>Fecha de Emisión: {datetime.now().strftime('%d/%m/%Y')}</p>
                </div>

                <div class="info-box">
                    <strong>Colaborador/a:</strong> {emp_data['Empleado']}<br>
                    <strong>Empresa:</strong> Gio Group SAS de CV
                </div>

                <table>
                    <thead>
                        <tr>
                            <th>Concepto de Ingreso / Deducción</th>
                            <th style="text-align: right;">Monto ($)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Sueldo Base</td>
                            <td style="text-align: right;">${emp_data['Sueldo Base']:.2f}</td>
                        </tr>
                        <tr>
                            <td>Comisiones y Servicios</td>
                            <td style="text-align: right;">${emp_data['Comisiones']:.2f}</td>
                        </tr>
                        <tr>
                            <td>Horas Extra / Bonos</td>
                            <td style="text-align: right;">${emp_data['Horas Extra/Bonos']:.2f}</td>
                        </tr>
                        <tr>
                            <td>Descuentos Aplicados</td>
                            <td style="text-align: right; color: #c92a2a;">-${emp_data['Descuentos']:.2f}</td>
                        </tr>
                        <tr class="total-row">
                            <td>TOTAL NETO A RECIBIR</td>
                            <td style="text-align: right; color: #0056b3;">${emp_data['Total a Pagar ($)']:.2f}</td>
                        </tr>
                    </tbody>
                </table>

                <div class="notes">
                    <strong>Motivo / Nota de Descuentos o Ajustes:</strong><br>
                    {emp_data['Nota Descuento']}
                </div>

                <div class="footer">
                    Este documento es un comprobante digital generado automáticamente por el Sistema Integral de Pagos de Gio Group SAS de CV.
                </div>
            </body>
            </html>
            """

            # 2. Convertir HTML a PDF usando WeasyPrint
            pdf_path = f"Recibo_{empleado_seleccionado.replace(' ', '_')}.pdf"
            HTML(string=html_content).write_pdf(pdf_path)

            # 3. Enviar por correo usando los Secrets de Gmail configurados
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

            # Adjuntar el archivo PDF real
            with open(pdf_path, "rb") as f:
                adjunto = MIMEApplication(f.read(), Name=pdf_path)
            adjunto['Content-Disposition'] = f'attachment; filename="{pdf_path}"'
            msg.attach(adjunto)

            # Conexión SMTP
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(remitente_email, password_email)
            server.sendmail(remitente_email, emp_data['Email'], msg.as_string())
            server.quit()

            st.success(f"¡Recibo en PDF generado y enviado con éxito a {emp_data['Email']}!")

        except Exception as ex:
            st.error(f"Error al generar o enviar el recibo: {ex}")
