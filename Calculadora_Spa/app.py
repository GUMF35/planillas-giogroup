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

base_masajistas = st.sidebar.number_input("Sueldo Base Estándar ($):", value=183.96 if periodo == "Quincenal" else 367.92, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Administrativo ($):", value=300.00 if periodo == "Quincenal" else 600.00, step=10.0)

# --- LECTOR DE PDF AUTOMÁTICO ---
st.subheader("📂 Reporte de Ingresos (PDF)")
archivo_subido = st.file_uploader("Sube el archivo PDF de ingresos aquí", type=["pdf", "xlsx", "csv"])

# Inicializar DataFrames o diccionarios base en memoria
df_reporte = None
comisiones_calculadas_pdf = {
    "Maydely Hernández": 0.0,
    "Luis Violante": 0.0,
    "Jessica Lemus": 0.0,
    "Dr. Gio Molina (Marvin Giovanni Molina Flores)": 0.0,
    "Gerson Ulises Molina Flores": 0.0,
    "Edwin Ponce": 0.0,
    "Mario de Paz": 0.0
}
totales_brutos_pdf = {
    "Maydely Hernández": 0.0,
    "Luis Violante": 0.0,
    "Jessica Lemus": 0.0
}

# Procesar PDF si se sube
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

                    # Cálculo Estándar (Servicios >= 60 menos 25% publicidad)
                    def calc_estandar(nombre):
                        df_prof = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre, case=False, na=False)]
                        df_extras = df_prof[df_prof[col_precio] >= 60].copy()
                        df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                        total_bruto = df_extras['EXTRA_BASE'].sum()
                        desc_pub = total_bruto * 0.25
                        return max(0.0, total_bruto - desc_pub)

                    # Total general de servicios (para modalidad de porcentaje directo)
                    def calc_total_servicios(nombre):
                        df_prof = df_reporte[df_reporte[col_prof].astype(str).str.contains(nombre, case=False, na=False)]
                        return df_prof[col_precio].sum()

                    comisiones_calculadas_pdf["Maydely Hernández"] = calc_estandar("MAYDELY")
                    comisiones_calculadas_pdf["Luis Violante"] = calc_estandar("LUIS")
                    comisiones_calculadas_pdf["Jessica Lemus"] = calc_total_servicios("JESSICA") * 0.20 # 20% por defecto

                    totales_brutos_pdf["Maydely Hernández"] = calc_total_servicios("MAYDELY")
                    totales_brutos_pdf["Luis Violante"] = calc_total_servicios("LUIS")
                    totales_brutos_pdf["Jessica Lemus"] = calc_total_servicios("JESSICA")

                    st.success("¡Reporte PDF leído y comisiones calculadas con éxito!")
    except Exception as e:
        st.warning(f"Advertencia al leer PDF: {e}")

# --- PANEL DE PERSONALIZACIÓN Y MODALIDADES ---
st.subheader("✍️ Ajustes, Comisiones y Modalidades por Empleado")
st.markdown("Revisa o modifica los valores calculados, cambia modalidades por porcentaje y agrega bonos o descuentos:")

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
    with st.expander(f"👤 {emp} - Configurar Planilla y Modalidad"):
        col1, col2, col3 = st.columns(3)
        
        base_sugerido = base_fijos if "Gio" in emp or "Gerson" in emp or "Edwin" in emp else base_masajistas
        
        with col1:
            sueldo_base = st.number_input(f"Sueldo Base ($) [{emp}]", value=float(base_sugerido), key=f"base_{emp}")
            
            # Valor sugerido inicial basado en el PDF
            valor_sugerido_comision = comisiones_calculadas_pdf.get(emp, 0.0)
            
            # Modalidad de porcentaje para Maydely, Luis y Jessica
            if emp in ["Maydely Hernández", "Luis Violante", "Jessica Lemus"]:
                modalidad = st.selectbox(
                    f"Modalidad de Comisión [{emp}]", 
                    ["Estándar (Servicios >= $60 - 25%)", "Porcentaje Directo (%)"],
                    key=f"mod_{emp}"
                )
                
                if modalidad == "Porcentaje Directo (%)":
                    porc_pred = 20 if emp == "Jessica Lemus" else 20
                    porc_personalizado = st.slider(f"Porcentaje Aplicado (%) [{emp}]", min_value=0, max_value=100, value=porc_pred, key=f"porc_{emp}")
                    total_serv_bruto = totales_brutos_pdf.get(emp, 0.0)
                    valor_sugerido_comision = total_serv_bruto * (porc_personalizado / 100.0)
            
            comision_extra = st.number_input(
                f"Comisiones / Servicios ($) [{emp}]", 
                value=float(valor_sugerido_comision), 
                key=f"com_{emp}", 
                step=5.0
            )

        with col2:
            horas_extras = st.number_input(f"Horas Extra / Bonos ($) [{emp}]", value=0.0, key=f"hex_{emp}", step=5.0)
            descuentos = st.number_input(f"Total Descuentos ($) [{emp}]", value=0.0, key=f"desc_{emp}", step=5.0)
        
        with col3:
            nota_descuento = st.text_input(f"Nota / Motivo Descuento [{emp}]", value="Ninguno", key=f"nota_{emp}")
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
            
            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(240, 243, 246)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 10, f" Colaborador/a: {emp_data['Empleado']}", 0, 1, 'L', fill=True)
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
                ("Horas Extra / Bonos", emp_data['Horas Extra/Bonos']),
                ("Descuentos Aplicados", -emp_data['Descuentos'])
            ]

            for desc, val in conceptos:
                pdf.cell(130, 8, f"  {desc}", 1, 0, 'L')
                pdf.cell(60, 8, f"${val:.2f} ", 1, 1, 'R')

            pdf.set_font('helvetica', 'B', 11)
            pdf.set_fill_color(230, 235, 240)
            pdf.cell(130, 10, "  TOTAL NETO A RECIBIR", 1, 0, 'L', fill=True)
            pdf.cell(60, 10, f"${emp_data['Total a Pagar ($)']:.2f} ", 1, 1, 'R', fill=True)
            pdf.ln(8)

            pdf.set_font('helvetica', 'B', 10)
            pdf.set_text_color(0, 86, 179)
            pdf.cell(0, 6, "Motivo / Nota de Descuentos o Ajustes:", 0, 1, 'L')
            
            pdf.set_font('helvetica', '', 10)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 6, emp_data['Nota Descuento'], 1, 'L')

            pdf_path = f"Recibo_{empleado_seleccionado.replace(' ', '_')}.pdf"
            pdf.output(pdf_path)

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
