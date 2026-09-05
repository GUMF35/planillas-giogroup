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

st.title("💆‍♂️ Gio Group SAS de CV - Control de Planillas")

# --- CONFIGURACIÓN LATERAL ---
st.sidebar.header("⚙️ Configuración")
periodo = st.sidebar.radio("Selecciona el periodo:", ("Quincenal", "Mensual"))

base_masajistas = st.sidebar.number_input("Sueldo Base Masajistas/Ventas ($):", value=183.96 if periodo == "Quincenal" else 367.92, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Administrativo/Docs ($):", value=300.00 if periodo == "Quincenal" else 600.00, step=10.0)
comision_jessica = st.sidebar.slider("Comisión Jessica (%):", min_value=0, max_value=100, value=20) / 100
comision_mario = st.sidebar.number_input("Comisiones Extra Mario de Paz ($):", min_value=0.0, value=0.0, step=10.0)

# Configuración de Correo Gmail (Se puede rellenar aquí o en barra lateral)
st.sidebar.subheader("📧 Configuración de Envío Gmail")
remitente_email = st.sidebar.text_input("Tu Correo de Gmail:", value="gersonmolina67@gmail.com")
password_email = st.sidebar.text_input("Contraseña de Aplicación (16 letras):", type="password")

# --- LECTOR DE PDF ---
st.write("Sube el reporte de ingresos en formato **PDF**.")
archivo_subido = st.file_uploader("Sube tu archivo aquí", type=["pdf", "xlsx", "csv"])

if archivo_subido is not None:
    try:
        df = None
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

        if df is not None:
            df.columns = df.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
            col_prof = next((col for col in df.columns if 'PROFESIONAL' in col), None)
            col_precio = next((col for col in df.columns if 'PRECIO' in col), None)

            if col_prof and col_precio:
                df = df.dropna(subset=[col_prof, col_precio])
                df[col_precio] = df[col_precio].astype(str).str.replace(r'[\$,\n]', '', regex=True)
                df[col_precio] = pd.to_numeric(df[col_precio], errors='coerce').fillna(0.0)

                # Cálculos
                def calcular_extras(nombre):
                    df_prof = df[df[col_prof].astype(str).str.contains(nombre, case=False, na=False)]
                    df_extras = df_prof[df_prof[col_precio] >= 60].copy()
                    df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                    total_bruto = df_extras['EXTRA_BASE'].sum()
                    desc_pub = total_bruto * 0.25
                    neto = total_bruto - desc_pub
                    total = neto + base_masajistas
                    return total_bruto, desc_pub, neto, total

                may_bruto, may_desc, may_neto, may_total = calcular_extras("MAYDELY")
                luis_bruto, luis_desc, luis_neto, luis_total = calcular_extras("LUIS")

                jessica_trabajado = df[df[col_prof].astype(str).str.contains("JESSICA", case=False, na=False)][col_precio].sum()
                jessica_total = jessica_trabajado * comision_jessica

                gio_total = base_fijos 
                gerson_total, edwin_total = base_fijos, base_fijos
                mario_total = base_masajistas + comision_mario
                gran_total = may_total + luis_total + jessica_total + gio_total + gerson_total + edwin_total + mario_total

                st.subheader("📋 Resumen de Pagos Calculados")
                resumen_data = {
                    "Empleado": ["Maydely Hernández", "Luis Violante", "Jessica Lemus", "Dr. Gio Molina", "Gerson Flores", "Edwin Ponce", "Mario de Paz"],
                    "Total a Pagar ($)": [may_total, luis_total, jessica_total, gio_total, gerson_total, edwin_total, mario_total]
                }
                st.dataframe(pd.DataFrame(resumen_data).style.format({"Total a Pagar ($)": "{:.2f}"}))

                # --- APARTADO DE CORREOS ---
                st.subheader("✉️ Enviar Comprobantes por Gmail")
                col_nombre_envio = st.selectbox("Selecciona a quién enviar recibo:", ["Maydely Hernández", "Luis Violante", "Jessica Lemus"])
                email_destino = st.text_input(f"Correo electrónico de {col_nombre_envio}:")

                if st.button("Enviar Recibo por Correo"):
                    if not password_email:
                        st.error("⚠️ Debes ingresar tu contraseña de aplicación de Gmail en la barra lateral.")
                    elif not email_destino:
                        st.error("⚠️ Ingresa un correo electrónico de destino válido.")
                    else:
                        try:
                            # Estructura del correo
                            msg = MIMEMultipart()
                            msg['From'] = remitente_email
                            msg['To'] = email_destino
                            msg['Subject'] = f"Comprobante de Pago - {periodo} - Gio Group SAS de CV"

                            cuerpo = f"""Estimado/a {col_nombre_envio},
Adjunto encontrará el detalle y comprobante correspondiente a su pago del periodo {periodo}.

Atentamente,
Gio Group SAS de CV"""
                            msg.attach(MIMEText(cuerpo, 'plain'))

                            # Adjunto simulado en texto plano/archivo como comprobante
                            contenido_recibo = f"GIO GROUP SAS DE CV\nCOMPROBANTE DE PAGO\nPeriodo: {periodo}\nEmpleado: {col_nombre_envio}\nTotal Neto: ${may_total if 'Maydely' in col_nombre_envio else luis_total:.2f}"
                            adjunto = MIMEApplication(contenido_recibo.encode('utf-8'), Name="Recibo_Pago.txt")
                            adjunto['Content-Disposition'] = 'attachment; filename="Recibo_Pago.txt"'
                            msg.attach(adjunto)

                            # Conexión SMTP de Gmail
                            server = smtplib.SMTP('smtp.gmail.com', 587)
                            server.starttls()
                            server.login(remitente_email, password_email)
                            server.sendmail(remitente_email, email_destino, msg.as_string())
                            server.quit()

                            st.success(f"¡Correo enviado con éxito a {email_destino}!")
                        except Exception as ex:
                            st.error(f"Error al enviar correo: {ex}")

    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")

    except Exception as e:
        st.error(f"Error procesando archivo: {e}")
