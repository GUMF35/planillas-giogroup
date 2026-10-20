"""Inicio de sesión y configuración de usuarios (las contraseñas solo existen como hash en los Secrets)."""
import html

import pandas as pd
import streamlit as st

from nucleo import seguridad as seg

from . import comun as cm


def pantalla_login(ctx, usuarios):
    """Formulario de acceso. Devuelve True si hay una sesión iniciada."""
    ss = st.session_state
    if ss.get("usuario_sesion"):
        return True
    limitador = ss.setdefault("_limitador_login", seg.Limitador())
    _, centro, _ = st.columns([1, 1.4, 1])
    with centro:
        ctx.md(f"<div class='brand' style='justify-content:center;border:none;margin-top:6vh'><img src='{ctx.img_logo()}' alt=''/>"
               f"<div><div class='brand-name'>{html.escape(ctx.aj('empresa_corto'))}</div><div class='brand-sub'>Suite administrativa</div></div></div>")
        with ctx.tarjeta("login"):
            ctx.md(ctx.titulo_seccion("🔐 Iniciar sesión", "Ingresa con el usuario que te asignó la administración."))
            if limitador.bloqueado():
                st.error(f"Demasiados intentos fallidos. Espera {limitador.segundos_restantes()} segundos.")
                return False
            with st.form("form_login"):
                usuario = st.text_input("Usuario", key="login_usuario", autocomplete="username")
                clave = st.text_input("Contraseña", type="password", key="login_clave", autocomplete="current-password")
                entrar = st.form_submit_button("Entrar", type="primary", **ctx.ancho(st.form_submit_button))
            if entrar:
                datos = seg.autenticar(usuarios, usuario, clave)
                if datos:
                    limitador.exito()
                    ss["usuario_sesion"] = datos
                    ss["pagina"] = "Planillas" if datos["rol"] == "admin" else "MiAsistencia"
                    ss.pop("login_clave", None)
                    st.rerun()
                limitador.fallo()
                st.error("Usuario o contraseña incorrectos.")
    return False


def tarjeta_usuarios(ctx, usuarios):
    with ctx.tarjeta("seg_estado"):
        ctx.md(ctx.titulo_seccion("🔐 Inicio de sesión y roles", "Administración ve todo. Personal operativo solo marca su asistencia, ve su horario y solicita permisos."))
        if not usuarios:
            st.warning("El inicio de sesión está DESACTIVADO: cualquier persona con el enlace de la app puede ver salarios, cuentas bancarias, préstamos y anticipos. "
                       "Crea al menos un usuario de administración (pasos abajo).")
        else:
            st.success(f"Inicio de sesión activado · {len(usuarios)} usuario(s).")
            cm.tabla(ctx, pd.DataFrame([{"Usuario": u["usuario"], "Nombre": u["nombre"], "Rol": seg.ROLES[u["rol"]], "Colaborador vinculado": u["colaborador"] or "—"}
                                        for u in usuarios.values()]))
        st.caption("Además, en Streamlit Cloud puedes hacer la app privada (Settings → Sharing → «Only specific people»): así solo los correos invitados pueden abrirla.")
    with ctx.tarjeta("seg_generador"):
        ctx.md(ctx.titulo_seccion("🧩 Crear un usuario", "La contraseña se convierte en un hash irreversible. Copia el bloque en Streamlit Cloud → tu app → ⋮ → Settings → Secrets."))
        with st.form("form_hash", clear_on_submit=True):
            a, b = st.columns(2)
            usuario = a.text_input("Usuario (sin espacios)", key="seg_u", placeholder="gerencia")
            nombre = b.text_input("Nombre visible", key="seg_n", placeholder="Gerencia General")
            a, b = st.columns(2)
            rol = a.selectbox("Rol", list(seg.ROLES), format_func=seg.ROLES.get, key="seg_r")
            colaborador = b.selectbox("Colaborador vinculado (obligatorio para operativos)", [""] + list(ctx.empleados()), key="seg_c",
                                      format_func=lambda c: c or "—")
            c1, c2 = st.columns(2)
            clave = c1.text_input("Contraseña (mínimo 8 caracteres)", type="password", key="seg_p1", autocomplete="new-password")
            clave2 = c2.text_input("Repite la contraseña", type="password", key="seg_p2", autocomplete="new-password")
            generar = st.form_submit_button("Generar bloque para Secrets", type="primary")
        if generar:
            usuario_l = usuario.strip().lower()
            if not usuario_l or " " in usuario_l or not usuario_l.replace("_", "").replace("-", "").isalnum():
                st.error("El usuario solo puede tener letras, números, guion o guion bajo.")
            elif clave != clave2:
                st.error("Las contraseñas no coinciden.")
            elif rol == "operativo" and not colaborador:
                st.error("Un usuario operativo debe estar vinculado a su nombre en el personal.")
            else:
                try:
                    h = seg.hash_clave(clave)
                except ValueError as ex:
                    st.error(str(ex))
                else:
                    lineas = [f"[usuarios.{usuario_l}]", f'nombre = "{(nombre or usuario_l).replace(chr(34), "")}"', f'rol = "{rol}"']
                    if colaborador:
                        lineas.append(f'colaborador = "{colaborador}"')
                    lineas.append(f'clave = "{h}"')
                    st.code("\n".join(lineas), language="toml")
                    st.caption("Pega este bloque al final de tus Secrets y guarda. La app se reinicia y pedirá iniciar sesión. Nunca compartas tus Secrets ni los subas a GitHub.")
