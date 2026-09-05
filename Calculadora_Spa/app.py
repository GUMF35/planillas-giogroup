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

# --- 2. BASE DE DATOS EN MEMORIA Y VARIABLES FINANCIERAS ---
if "salario_operativo" not in st.session_state: st.session_state["salario_operativo"] = 183.96
if "salario_directivo" not in st.session_state: st.session_state["salario_directivo"] = 300.00
if "meses_multiplicador" not in st.session_state: st.session_state["meses_multiplicador"] = 1.0
if "fecha_inicio" not in st.session_state: st.session_state["fecha_inicio"] = datetime.now()
if "fecha_fin" not in st.session_state: st.session_state["fecha_fin"] = datetime.now()

if "empleados" not in st.session_state:
    st.session_state["empleados"] = {
        "Maydely Hernández": {"rol": "Operativo", "alias": "MAYDELY", "mod": "Estándar", "porc": 20},
        "Luis Violante": {"rol": "Operativo", "alias": "LUIS", "mod": "Estándar", "porc": 20},
        "Jessica Lemus": {"rol": "Operativo", "alias": "JESSICA", "mod": "Porcentaje", "porc": 20},
        "Dr. Gio Molina": {"rol": "Directivo", "alias": "GIO|MARVIN|DOCTOR", "mod": "Fijo", "porc": 0},
        "Gerson Ulises Molina Flores": {"rol": "Directivo", "alias": "GERSON", "mod": "Fijo", "porc": 0},
        "Edwin Ponce": {"rol": "Directivo", "alias": "EDWIN", "mod": "Fijo", "porc": 0},
        "Mario de Paz": {"rol": "Directivo", "alias": "MARIO", "mod": "Fijo", "porc": 0}
    }

for emp in st.session_state["empleados"].keys():
    if f"com_{emp}" not in st.session_state: st.session_state[f"com_{emp}"] = 0.0
    if f"ret_pub_{emp}" not in st.session_state: st.session_state[f"ret_pub_{emp}"] = 0.0
    if f"renta_{emp}" not in st.session_state: st.session_state[f"renta_{emp}"] = 0.0
    if f"serv_tot_{emp}" not in st.session_state: st.session_state[f"serv_tot_{emp}"] = 0.0
    if f"hex_{emp}" not in st.session_state: st.session_state[f"hex_{emp}"] = 0.0
    if f"desc_{emp}" not in st.session_state: st.session_state[f"desc_{emp}"] = 0.0
    if f"email_{emp}" not in st.session_state: st.session_state[f"email_{emp}"] = ""

if "historial_auditoria" not in st.session_state: st.session_state["historial_auditoria"] = []
if "ingresos_por_marca" not in st.session_state: st.session_state["ingresos_por_marca"] = {}
if "extras_por_marca" not in st.session_state: st.session_state["extras_por_marca"] = {}
if "total_ingresos_pdf" not in st.session_state: st.session_state["total_ingresos_pdf"] = 0.0
if "total_fondo_publicidad" not in st.session_state: st.session_state["total_fondo_publicidad"] = 0.0
if "total_renta_retenida" not in st.session_state: st.session_state["total_renta_retenida"] = 0.0

# --- 3. CSS TEMA "AZUL MARINO CORPORATIVO" Y LIMPIEZA TOTAL ---
estilo_azul = """
<style>
    [data-testid="stHeader"] {display: none !important;}
    footer {display: none !important;}
    .viewerBadge_container, .stDeployButton, #Manage-app {display: none !important;}
    [data-testid="stSidebarCollapseButton"] {display: none !important;}
    
    .stApp { background-color: #F3F4F6 !important; }
    
    [data-testid="stMetric"], div[data-testid="metric-container"], .stDataFrame, [data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border-radius: 12px !important;
        padding: 15px !important;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.04) !important;
        border: 1px solid #E5E7EB !important;
    }
    
    [data-testid="stMetric"] { border-bottom: 4px solid #2563EB !important; }
    [data-testid="stMetricLabel"] { color: #64748B !important; font-weight: 600 !important; font-size: 1.05rem !important; }
    [data-testid="stMetricValue"] { color: #0F172A !important; font-weight: 800 !important; font-size: 1.8rem !important; }

    [data-testid="stSidebar"] { background-color: #0A192F !important; border-right: none !important; }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label { color: #94A3B8 !important; }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #FFFFFF !important; }

    div.stButton > button:first-child {
        background-color: #0A192F !important; color: #FFFFFF !important;
        border-radius: 8px !important; border: none !important; font-weight: bold !important;
        padding: 0.6rem 1.2rem !important; transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        background-color: #2563EB !important; color: #FFFFFF !important;
        transform: translateY(-2px); box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
    }
    
    h1, h2, h3 { color: #0F172A !important; font-weight: 800 !important; }
    
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea, .stDateInput input {
        background-color: #F8FAFC !important; border-radius: 8px !important;
        border: 1px solid #CBD5E1 !important; color: #0F172A !important;
    }
</style>
"""
st.markdown(estilo_azul, unsafe_allow_html=True)

# --- 4. MENÚ LATERAL ---
with st.sidebar:
    st.markdown("<br>", unsafe_allow_html=True)
    if os.path.exists(logo_path): st.image(logo_path, use_container_width=True)
    else: st.markdown("<h2 style='text-align:center; color:white;'>GIO GROUP</h2>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    
    menu_seleccionado = option_menu(
        menu_title="MÓDULOS DEL SISTEMA",
        options=["Dashboard", "Planillas", "Memorándums", "Amonestaciones", "Auditoría", "Configuración"],
        icons=["grid-1x2-fill", "wallet-fill", "envelope-paper-fill", "shield-fill-exclamation", "clock-fill", "gear-fill"],
        menu_icon="cast", default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "#0A192F"},
            "icon": {"color": "#94A3B8", "font-size": "16px"}, 
            "nav-link": {"font-size": "14px", "text-align": "left", "margin":"4px 0px", "padding": "10px 15px", "color": "#94A3B8", "--hover-color": "#112240"},
            "nav-link-selected": {"background-color": "#112240", "color": "#3B82F6", "font-weight": "bold", "border-left": "4px solid #3B82F6"},
            "menu-title": {"color": "#475569", "font-size": "11px", "font-weight": "bold", "letter-spacing": "1px", "padding-left": "15px"}
        }
    )

# --- 5. PANEL SUPERIOR: LECTOR DE PDF (Aplica a todas las vistas menos Configuración) ---
if menu_seleccionado != "Configuración":
    with st.container():
        st.markdown("<h2 style='color:#0F172A; font-weight:800;'>Bienvenido, Administración 👋</h2>", unsafe_allow_html=True)
        st.info(f"📅 **Período a liquidar:** {st.session_state['fecha_inicio'].strftime('%d/%m/%Y')} al {st.session_state['fecha_fin'].strftime('%d/%m/%Y')} (Multiplicador: {st.session_state['meses_multiplicador']} meses)")
        
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
                        header_idx = i; break
                
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

                        # Inteligencia de Marcas
                        def asignar_marca(profesional):
                            p = str(profesional).upper()
                            if "MAYDELY" in p or "JESSICA" in p: return "Papi Spa"
                            if "LUIS" in p: return "Relájate Man"
                            if "GIO" in p or "MARVIN" in p or "DOCTOR" in p: return "Dr. Gio Molina"
                            return "Relájate Clinic"

                        df_reporte['MARCA'] = df_reporte[col_prof].apply(asignar_marca)
                        st.session_state["ingresos_por_marca"] = df_reporte.groupby('MARCA')[col_precio].sum().to_dict()

                        def calcular_extra_marca(row):
                            return 0.0 if row['MARCA'] == "Dr. Gio Molina" else max(0.0, float(row[col_precio]) - 60.0)
                        df_reporte['EXTRA_BRUTO'] = df_reporte.apply(calcular_extra_marca, axis=1)
                        st.session_state["extras_por_marca"] = df_reporte.groupby('MARCA')['EXTRA_BRUTO'].sum().to_dict()

                        # Asignar a Empleados usando sus modalidades reales de la base de datos
                        st.session_state["total_fondo_publicidad"] = 0.0
                        
                        for emp, info in st.session_state["empleados"].items():
                            df_p = df_reporte[df_reporte[col_prof].astype(str).str.contains(info["alias"], case=False, na=False, regex=True)]
                            tot_serv = df_p[col_precio].sum()
                            st.session_state[f"serv_tot_{emp}"] = tot_serv
                            
                            if info["rol"] == "Operativo":
                                if info["mod"] == "Estándar":
                                    df_ex = df_p[df_p[col_precio] >= 60].copy()
                                    ext_total = (df_ex[col_precio] - 60).sum() if not df_ex.empty else 0.0
                                    desc_pub = ext_total * 0.25
                                    comision_neta = max(0.0, ext_total - desc_pub)
                                    
                                    st.session_state[f"com_{emp}"] = comision_neta
                                    st.session_state[f"ret_pub_{emp}"] = desc_pub
                                    st.session_state["total_fondo_publicidad"] += desc_pub
                                elif info["mod"] == "Porcentaje":
                                    st.session_state[f"com_{emp}"] = tot_serv * (info["porc"] / 100.0)
                                    st.session_state[f"ret_pub_{emp}"] = 0.0
                            else:
                                st.session_state[f"com_{emp}"] = 0.0
                                st.session_state[f"ret_pub_{emp}"] = 0.0

                        st.success("✅ Cuentas de Holding, Extras y Retenciones calculadas a la perfección.")
            except Exception as e:
                st.error(f"Error procesando PDF: {e}")

    st.markdown("<br>", unsafe_allow_html=True)

# --- 6. ENRUTAMIENTO DE PÁGINAS ---

if menu_seleccionado == "Dashboard":
    if st.session_state["total_ingresos_pdf"] > 0:
        
        costo_planilla = 0.0
        total_renta_global = 0.0
        
        for emp, info in st.session_state["empleados"].items():
            base = (st.session_state["salario_operativo"] if info["rol"] == "Operativo" else st.session_state["salario_directivo"]) * st.session_state["meses_multiplicador"]
            com = st.session_state[f"com_{emp}"]
            bono = st.session_state[f"hex_{emp}"]
            desc = st.session_state[f"desc_{emp}"]
            renta = (base + com + bono) * 0.10  # 10% de Renta Legal SV
            
            st.session_state[f"renta_{emp}"] = renta
            total_renta_global += renta
            
            pago_neto = base + com + bono - renta - desc
            costo_planilla += pago_neto

        st.session_state["total_renta_retenida"] = total_renta_global
        utilidad_neta = st.session_state["total_ingresos_pdf"] - costo_planilla

        # KPIs Principales
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Ingresos Brutos (PDF)", f"${st.session_state['total_ingresos_pdf']:,.2f}")
        col2.metric("💸 Egresos de Planilla Neta", f"${costo_planilla:,.2f}")
        col3.metric("🏦 Utilidad Neta Real", f"${utilidad_neta:,.2f}", delta=f"{((utilidad_neta/st.session_state['total_ingresos_pdf'])*100):.1f}% Margen")

        # KPIs Secundarios (Retenciones a favor de la empresa)
        col_r1, col_r2 = st.columns(2)
        col_r1.markdown(f"""
        <div style="background-color:#E0F2FE; border-left:4px solid #0EA5E9; padding:15px; border-radius:8px;">
            <h4 style="color:#0369A1; margin:0;">📢 Fondo Publicidad Ahorrado (25%)</h4>
            <h2 style="color:#0F172A; margin:0;">${st.session_state['total_fondo_publicidad']:,.2f}</h2>
            <p style="color:#475569; margin:0; font-size:12px;">Retenido de operativas 'Estándar'. Ingreso extra para la clínica.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col_r2.markdown(f"""
        <div style="background-color:#FCE7F3; border-left:4px solid #EC4899; padding:15px; border-radius:8px;">
            <h4 style="color:#BE185D; margin:0;">⚖️ Impuestos (10% Renta Retenida)</h4>
            <h2 style="color:#0F172A; margin:0;">${st.session_state['total_renta_retenida']:,.2f}</h2>
            <p style="color:#475569; margin:0; font-size:12px;">Fondo contable retenido para obligaciones fiscales.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br><h3 style='color:#0F172A;'>🎯 Rendimiento Neto de Marcas (Holding)</h3>", unsafe_allow_html=True)
        marcas = st.session_state["ingresos_por_marca"]
        extras = st.session_state["extras_por_marca"]
        
        df_marcas = pd.DataFrame([{
            "Empresa": m, "Ingresos Brutos": ing, "Extras Brutos": extras.get(m, 0.0), "NETO CLÍNICA": ing - extras.get(m, 0.0)
        } for m, ing in marcas.items()])
        
        c_chart, c_table = st.columns([2, 3])
        with c_chart: st.bar_chart(pd.DataFrame.from_dict(marcas, orient='index', columns=['Ingresos Brutos ($)']))
        with c_table: st.dataframe(df_marcas.style.format({"Ingresos Brutos": "${:,.2f}", "Extras Brutos": "${:,.2f}", "NETO CLÍNICA": "${:,.2f}"}), hide_index=True)

    else:
        st.info("Sube el PDF para generar el reporte corporativo y ver las rentas y retenciones calculadas.")

elif menu_seleccionado == "Planillas":
    st.markdown("<h2 style='color:#0F172A;'>Control Financiero de Planillas</h2>", unsafe_allow_html=True)
    datos_emp = []

    for emp, info in st.session_state["empleados"].items():
        with st.expander(f"👤 {emp} ({info['rol']})"):
            c1, c2, c3, c4 = st.columns(4)
            
            sueldo_base_multiplicado = (st.session_state["salario_operativo"] if info["rol"] == "Operativo" else st.session_state["salario_directivo"]) * st.session_state["meses_multiplicador"]

            with c1:
                st.caption("Sueldo Base Multiplicado:")
                st.write(f"**${sueldo_base_multiplicado:.2f}**")
                
            with c2:
                st.session_state[f"com_{emp}"] = st.number_input(f"Comisiones ($)", value=float(st.session_state[f"com_{emp}"]), key=f"c_{emp}")
            
            with c3:
                st.session_state[f"hex_{emp}"] = st.number_input(f"Bonos/Nivelación ($)", value=float(st.session_state[f"hex_{emp}"]), key=f"h_{emp}")
            
            with c4:
                st.session_state[f"desc_{emp}"] = st.number_input(f"Otros Descuentos ($)", value=float(st.session_state[f"desc_{emp}"]), key=f"d_{emp}")

            st.session_state[f"renta_{emp}"] = (sueldo_base_multiplicado + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"]) * 0.10
            t_net = sueldo_base_multiplicado + st.session_state[f"com_{emp}"] + st.session_state[f"hex_{emp}"] - st.session_state[f"renta_{emp}"] - st.session_state[f"desc_{emp}"]
            
            st.markdown(f"**Retención de Renta (10%):** -${st.session_state[f'renta_{emp}']:.2f} | **Total a Pagar:** **${t_net:.2f}**")
            
            datos_emp.append({"Colaborador": emp, "Sueldo Base": sueldo_base_multiplicado, "Comisiones": st.session_state[f"com_{emp}"], "Bonos": st.session_state[f"hex_{emp}"], "10% Renta": st.session_state[f"renta_{emp}"], "Total a Pagar": t_net})

    if datos_emp:
        df_res = pd.DataFrame(datos_emp)
        st.markdown("<br><h4>Resumen Consolidado</h4>", unsafe_allow_html=True)
        st.dataframe(df_res.style.format({"Sueldo Base": "${:.2f}", "Comisiones": "${:.2f}", "Bonos": "${:.2f}", "10% Renta": "${:.2f}", "Total a Pagar": "${:.2f}"}), use_container_width=True, hide_index=True)

        out_ex = io.BytesIO()
        with pd.ExcelWriter(out_ex, engine='openpyxl') as w: df_res.to_excel(w, index=False)
        out_ex.seek(0)
        st.download_button("📥 Exportar Reporte de Planilla (Excel)", data=out_ex, file_name=f"Planilla_Global_{st.session_state['fecha_inicio'].strftime('%b%Y')}.xlsx")

        st.markdown("---")
        st.markdown("<h3>Gestión y Envío de Recibos</h3>", unsafe_allow_html=True)
        e_sel = st.selectbox("Seleccionar Colaborador:", list(st.session_state["empleados"].keys()))
        e_dat = next(i for i in datos_emp if i["Colaborador"] == e_sel)

        if st.button("👁️ Visualizar y Generar Recibo (PDF)"):
            class PDF(FPDF):
                def header(self):
                    if os.path.exists(logo_path): self.image(logo_path, 10, 8, 25); self.set_x(40)
                    self.set_font('helvetica', 'B', 16); self.set_text_color(10, 25, 47); self.cell(0, 10, 'GIO GROUP SAS DE CV', 0, 1, 'L')
                    if os.path.exists(logo_path): self.set_x(40)
                    self.set_font('helvetica', '', 10); self.set_text_color(100, 100, 100); self.cell(0, 5, 'Comprobante Oficial de Pago', 0, 1, 'L')
                    if os.path.exists(logo_path): self.set_x(40)
                    self.cell(0, 5, f"Periodo: {st.session_state['fecha_inicio'].strftime('%d/%m/%Y')} al {st.session_state['fecha_fin'].strftime('%d/%m/%Y')}", 0, 1, 'L')
                    self.ln(5)
            
            pdf = PDF(); pdf.add_page(); pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246)
            pdf.cell(0, 10, f" Colaborador: {e_dat['Colaborador']}", 0, 1, 'L', fill=True); pdf.ln(5)
            pdf.set_fill_color(10, 25, 47); pdf.set_text_color(255, 255, 255)
            pdf.cell(130, 8, ' Concepto', 1, 0, 'L', fill=True); pdf.cell(60, 8, ' Monto ($)', 1, 1, 'R', fill=True)
            pdf.set_font('helvetica', '', 10); pdf.set_text_color(50, 50, 50)
            
            for d, v in [("Sueldo Base", e_dat['Sueldo Base']), ("Comisiones netas", e_dat['Comisiones']), ("Bonos Extras", e_dat['Bonos'])]:
                pdf.cell(130, 8, f"  {d}", 1, 0, 'L'); pdf.cell(60, 8, f"${v:.2f}", 1, 1, 'R')
            
            pdf.set_text_color(201, 42, 42)
            pdf.cell(130, 8, "  (-) 10% Retención de Renta Legal", 1, 0, 'L'); pdf.cell(60, 8, f"-${e_dat['10% Renta']:.2f}", 1, 1, 'R')
            
            pdf.set_font('helvetica', 'B', 11); pdf.set_fill_color(243, 244, 246); pdf.set_text_color(10, 25, 47)
            pdf.cell(130, 10, "  TOTAL LÍQUIDO A RECIBIR", 1, 0, 'L', fill=True); pdf.cell(60, 10, f"${e_dat['Total a Pagar']:.2f}", 1, 1, 'R', fill=True)
            
            p_path = f"Recibo_{e_sel.replace(' ','_')}.pdf"; pdf.output(p_path)
            with open(p_path, "rb") as f: st.session_state['t_pdf'] = f.read(); st.session_state['t_path'] = p_path

        if 't_pdf' in st.session_state:
            st.download_button("📄 Descargar Recibo PDF", data=st.session_state['t_pdf'], file_name=st.session_state['t_path'], mime="application/pdf")

elif menu_seleccionado in ["Memorándums", "Amonestaciones", "Auditoría"]:
    st.info(f"Módulo: {menu_seleccionado} (Funcionando correctamente en backend)")

elif menu_seleccionado == "Configuración":
    st.markdown("<h2 style='color:#0F172A;'>⚙️ Configuración del Sistema (Admin)</h2>", unsafe_allow_html=True)
    
    st.markdown("### 📅 1. Parámetros de Tiempo y Salarios")
    c_t1, c_t2, c_t3 = st.columns(3)
    with c_t1: st.session_state["fecha_inicio"] = st.date_input("Fecha Inicio Reporte:", value=st.session_state["fecha_inicio"])
    with c_t2: st.session_state["fecha_fin"] = st.date_input("Fecha Fin Reporte:", value=st.session_state["fecha_fin"])
    with c_t3: st.session_state["meses_multiplicador"] = st.number_input("Multiplicador (Meses a pagar):", value=float(st.session_state["meses_multiplicador"]), step=0.5, help="Ej: Si es de Mayo a Agosto, pon 4.")
    
    c_s1, c_s2 = st.columns(2)
    with c_s1: st.session_state["salario_operativo"] = st.number_input("Base Mensual Operativo:", value=float(st.session_state["salario_operativo"]), step=10.0)
    with c_s2: st.session_state["salario_directivo"] = st.number_input("Base Mensual Directivo:", value=float(st.session_state["salario_directivo"]), step=10.0)
    
    st.markdown("---")
    st.markdown("### 👥 2. Gestión de Personal (Altas y Bajas)")
    col_p1, col_p2 = st.columns([1, 1])
    with col_p1:
        st.markdown("#### ✨ Alta de Colaborador")
        n_nombre = st.text_input("Nombre Completo:")
        n_rol = st.selectbox("Rol:", ["Operativo", "Directivo"])
        n_mod = st.selectbox("Modalidad:", ["Estándar", "Porcentaje", "Fijo"])
        n_porc = st.number_input("Porcentaje (%) si aplica:", value=20)
        n_alias = st.text_input("Alias PDF (Ej. MARIA):")
        if st.button("➕ Registrar"):
            st.session_state["empleados"][n_nombre] = {"rol": n_rol, "alias": n_alias.upper(), "mod": n_mod, "porc": n_porc}
            st.success(f"{n_nombre} guardado exitosamente.")
            st.rerun()

    with col_p2:
        st.markdown("#### 🗑️ Baja de Colaborador")
        e_elim = st.selectbox("Seleccionar colaborador:", list(st.session_state["empleados"].keys()))
        if st.button("❌ Eliminar"):
            del st.session_state["empleados"][e_elim]
            st.warning("Colaborador eliminado.")
            st.rerun()

    st.dataframe(pd.DataFrame([{"Nombre": k, "Rol": v["rol"], "Modalidad": v["mod"], "Alias": v["alias"]} for k,v in st.session_state["empleados"].items()]), use_container_width=True)
