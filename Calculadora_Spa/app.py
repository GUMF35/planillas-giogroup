import streamlit as st
import pandas as pd
import io
import os
from datetime import datetime
import pdfplumber

st.set_page_config(page_title="Gestión de Planillas Spa", layout="wide")
st.title("💆‍♂️ Sistema Integral de Pagos y Comisiones")
# --- OCULTAR ELEMENTOS DE STREAMLIT ---
esconder_menu = """
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.viewerBadge_container__1QSob {visibility: hidden;}
</style>
"""
st.markdown(esconder_menu, unsafe_allow_html=True)

# --- 1. CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Personal")
periodo = st.sidebar.radio("Selecciona el periodo:", ("Quincenal", "Mensual"))

base_masajistas = st.sidebar.number_input("Sueldo Base Masajistas/Ventas ($):", value=183.96 if periodo == "Quincenal" else 367.92, step=10.0)
base_fijos = st.sidebar.number_input("Sueldo Base Administrativo/Docs ($):", value=300.00 if periodo == "Quincenal" else 600.00, step=10.0)
comision_jessica = st.sidebar.slider("Comisión Jessica (%):", min_value=0, max_value=100, value=20) / 100
comision_mario = st.sidebar.number_input("Comisiones Extra Mario de Paz ($):", min_value=0.0, value=0.0, step=10.0)

# --- 2. LECTOR DE ARCHIVOS ---
st.write("Sube tu reporte de ingresos (PDF, Excel o CSV).")
archivo_subido = st.file_uploader("Sube tu archivo aquí", type=["xlsx", "csv", "pdf"])

if archivo_subido is not None:
    try:
        df = None
        if archivo_subido.name.endswith('.csv'):
            df = pd.read_csv(archivo_subido)
        elif archivo_subido.name.endswith('.xlsx'):
            df = pd.read_excel(archivo_subido)
        elif archivo_subido.name.endswith('.pdf'):
            st.info("Procesando PDF...")
            todas_las_filas = []
            with pdfplumber.open(archivo_subido) as pdf:
                for page in pdf.pages:
                    tabla = page.extract_table()
                    if tabla:
                        todas_las_filas.extend(tabla)
            
            # Buscar dónde están los encabezados (donde dice PROFESIONAL)
            header_idx = -1
            for i, row in enumerate(todas_las_filas):
                if row and any(isinstance(cell, str) and 'PROFESIONAL' in cell.upper() for cell in row):
                    header_idx = i
                    break
            
            if header_idx != -1:
                df = pd.DataFrame(todas_las_filas[header_idx+1:], columns=todas_las_filas[header_idx])
            else:
                st.error("No se detectaron los encabezados en el PDF.")

        if df is not None:
            # Limpiar columnas
            df.columns = df.columns.astype(str).str.strip().str.upper().str.replace('\n', ' ')
            
            # Identificar columnas clave dinámicamente
            col_prof = next((col for col in df.columns if 'PROFESIONAL' in col), None)
            col_precio = next((col for col in df.columns if 'PRECIO' in col), None)
            col_fecha = next((col for col in df.columns if 'CORRELATIVO' in col or 'FECHA' in col), None)

            if not col_prof or not col_precio:
                st.error("El documento no tiene columnas de PROFESIONAL o PRECIO legibles.")
            else:
                # Limpiar la data
                df = df.dropna(subset=[col_prof, col_precio])
                df[col_precio] = df[col_precio].astype(str).str.replace(r'[\$,\n]', '', regex=True)
                df[col_precio] = pd.to_numeric(df[col_precio], errors='coerce').fillna(0.0)

                # --- 3. CÁLCULOS ---
                def calcular_extras(nombre):
                    df['Temp_Prof'] = df[col_prof].astype(str).fillna('')
                    df_prof = df[df['Temp_Prof'].str.contains(nombre, case=False, na=False)]
                    df_extras = df_prof[df_prof[col_precio] >= 60].copy()
                    df_extras['EXTRA_BASE'] = df_extras[col_precio] - 60
                    
                    total_bruto = df_extras['EXTRA_BASE'].sum()
                    desc_pub = total_bruto * 0.25
                    neto = total_bruto - desc_pub
                    total = neto + base_masajistas
                    return total_bruto, desc_pub, neto, total, df_extras

                may_bruto, may_desc, may_neto, may_total, may_df = calcular_extras("MAYDELY")
                luis_bruto, luis_desc, luis_neto, luis_total, luis_df = calcular_extras("LUIS")

                df_jess = df[df[col_prof].astype(str).str.contains("JESSICA", case=False, na=False)]
                jessica_trabajado = df_jess[col_precio].sum()
                jessica_total = jessica_trabajado * comision_jessica

                df_gio = df[df[col_prof].astype(str).str.contains("MARVIN", case=False, na=False)]
                gio_facturado = df_gio[col_precio].sum()
                gio_total = base_fijos 

                gerson_total, edwin_total = base_fijos, base_fijos
                mario_total = base_masajistas + comision_mario
                gran_total = may_total + luis_total + jessica_total + gio_total + gerson_total + edwin_total + mario_total

                # --- 4. INTERFAZ ---
                tab1, tab2 = st.tabs(["📋 Planilla y WhatsApp", "📊 Rendimiento Bruto"])

                with tab1:
                    resumen_data = {
                        "Empleado": ["Maydely Hernández", "Luis Violante", "Jessica Lemus", "Dr. Gio Molina", "Gerson Flores", "Edwin Ponce", "Mario de Paz"],
                        "Total a Pagar ($)": [may_total, luis_total, jessica_total, gio_total, gerson_total, edwin_total, mario_total]
                    }
                    st.dataframe(pd.DataFrame(resumen_data).style.format({"Total a Pagar ($)": "{:.2f}"}))
                    
                    st.subheader("📱 WhatsApp")
                    def get_fecha(row):
                        val = str(row.get(col_fecha, 'N/A')).split('\n')[0]
                        return f"{val[:4]}-{val[4:6]}-{val[6:8]}" if len(val)>=8 and val[:8].isdigit() else val

                    det_may = "\n".join([f"- Fecha: {get_fecha(row)} | Servicio: ${row[col_precio]:.2f} | Extra: ${row['EXTRA_BASE']:.2f}" for _, row in may_df.iterrows()])
                    det_luis = "\n".join([f"- Fecha: {get_fecha(row)} | Servicio: ${row[col_precio]:.2f} | Extra: ${row['EXTRA_BASE']:.2f}" for _, row in luis_df.iterrows()])

                    msg = f"""*A. Detalle de Extras - Maydely*
{det_may if det_may else 'No aplica'}
Total de extras: ${may_bruto:.2f}

*B. Pago Final - Maydely*
- Total bruto extras: ${may_bruto:.2f}
- Descuento publicidad (25%): -${may_desc:.2f}
- Neto extras: ${may_neto:.2f}
- Sueldo base: ${base_masajistas:.2f}
*Total a pagar: ${may_total:.2f}*

*C. Detalle de Extras - Luis*
{det_luis if det_luis else 'No aplica'}
Total de extras: ${luis_bruto:.2f}

*D. Pago Final - Luis*
- Total bruto extras: ${luis_bruto:.2f}
- Descuento publicidad (25%): -${luis_desc:.2f}
- Neto extras: ${luis_neto:.2f}
- Sueldo base: ${base_masajistas:.2f}
*Total a pagar: ${luis_total:.2f}*

*E. Pago Final - Jessica*
- Total trabajado: ${jessica_trabajado:.2f}
- Comisión ({int(comision_jessica*100)}%): ${jessica_total:.2f}
*Total a pagar: ${jessica_total:.2f}*

*F. Pago Final - Dr. Gio Molina*
- Total facturado: ${gio_facturado:.2f} (No se suma al pago)
- Sueldo base: ${base_fijos:.2f}
*Total a pagar: ${gio_total:.2f}*

*G. Pago Final - Gerson Flores*
- Sueldo base: ${base_fijos:.2f}
*Total a pagar: ${gerson_total:.2f}*

*H. Pago Final - Edwin Ponce*
- Sueldo base: ${base_fijos:.2f}
*Total a pagar: ${edwin_total:.2f}*

*I. Pago Final - Mario de Paz (Vendedor)*
- Sueldo base: ${base_masajistas:.2f}
- Comisiones de ventas: ${comision_mario:.2f}
*Total a pagar base: ${mario_total:.2f}*

*RESUMEN FINAL*
- Maydely: ${may_total:.2f}
- Luis: ${luis_total:.2f}
- Jessica: ${jessica_total:.2f}
- Dr. Gio: ${gio_total:.2f}
- Gerson: ${gerson_total:.2f}
- Edwin: ${edwin_total:.2f}
- Mario de Paz: ${mario_total:.2f}
*GRAN TOTAL: ${gran_total:.2f}*"""

                    st.text_area("Copia este texto y pégalo en WhatsApp:", value=msg, height=400)

                with tab2:
                    st.subheader("Rendimiento Bruto Facturado")
                    graf_data = pd.DataFrame({
                        "Empleado": ["Maydely", "Luis", "Jessica", "Dr. Gio"],
                        "Bruto ($)": [may_df[col_precio].sum() if not may_df.empty else 0, luis_df[col_precio].sum() if not luis_df.empty else 0, jessica_trabajado, gio_facturado]
                    })
                    st.bar_chart(graf_data.set_index("Empleado")["Bruto ($)"])

    except Exception as e:
        st.error(f"Error procesando archivo: {e}")
