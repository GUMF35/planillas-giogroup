"""Inicio de sesión y permisos.

Las contraseñas NUNCA se guardan en el código: en los Secrets de Streamlit solo va su hash PBKDF2-SHA256,
generado desde Configuración → Seguridad. Ejemplo de secrets.toml:

    [usuarios.gerencia]
    nombre = "Gerencia"
    rol = "admin"
    clave = "pbkdf2_sha256$260000$<sal>$<hash>"

    [usuarios.luis]
    nombre = "Luis Violante"
    rol = "operativo"
    colaborador = "Luis Violante"
    clave = "pbkdf2_sha256$260000$<sal>$<hash>"
"""
import hashlib
import hmac
import os
import time

ALGORITMO = "pbkdf2_sha256"
ITERACIONES = 260_000
ROLES = {"admin": "Administración", "operativo": "Personal operativo"}
PERMISOS = {
    "admin": {"todo"},
    "operativo": {"marcar_propia", "ver_propia_asistencia", "solicitar_permisos"},
}
INTENTOS_MAXIMOS = 5
BLOQUEO_SEGUNDOS = 60
_HASH_FICTICIO = None


def hash_clave(clave, iteraciones=ITERACIONES, sal=None):
    if not clave or len(clave) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    sal = sal or os.urandom(16).hex()
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal.encode("utf-8"), int(iteraciones)).hex()
    return f"{ALGORITMO}${int(iteraciones)}${sal}${derivada}"


def verificar_clave(clave, almacenado):
    try:
        algoritmo, iteraciones, sal, esperado = str(almacenado).split("$", 3)
    except ValueError:
        return False
    if algoritmo != ALGORITMO or not clave:
        return False
    calculado = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal.encode("utf-8"), int(iteraciones)).hex()
    return hmac.compare_digest(calculado, esperado)


def puede(rol, permiso):
    permisos = PERMISOS.get(rol, set())
    return "todo" in permisos or permiso in permisos


def cargar_usuarios(seccion):
    """Usuarios válidos desde st.secrets['usuarios'] (o un dict equivalente). Ignora los mal configurados."""
    usuarios = {}
    if not seccion:
        return usuarios
    for usuario, datos in dict(seccion).items():
        try:
            datos = dict(datos)
        except (TypeError, ValueError):
            continue
        rol = str(datos.get("rol", "")).strip().lower()
        clave = str(datos.get("clave", "")).strip()
        if rol not in ROLES or not clave.startswith(ALGORITMO + "$"):
            continue
        if rol == "operativo" and not str(datos.get("colaborador", "")).strip():
            continue  # un operativo debe estar vinculado a su nombre en el personal
        usuarios[str(usuario).strip().lower()] = {"usuario": str(usuario).strip().lower(), "nombre": str(datos.get("nombre", usuario)).strip(),
                                                   "rol": rol, "clave": clave, "colaborador": str(datos.get("colaborador", "")).strip()}
    return usuarios


def autenticar(usuarios, usuario, clave):
    """Usuario autenticado (sin la clave) o None. Tarda lo mismo exista o no el usuario."""
    global _HASH_FICTICIO
    datos = usuarios.get(str(usuario or "").strip().lower())
    if datos is None:
        if _HASH_FICTICIO is None:
            _HASH_FICTICIO = hash_clave("clave-ficticia-para-igualar-tiempos")
        verificar_clave(clave or "x", _HASH_FICTICIO)
        return None
    if not verificar_clave(clave or "", datos["clave"]):
        return None
    return {k: v for k, v in datos.items() if k != "clave"}


class Limitador:
    """Bloquea temporalmente después de varios intentos fallidos (por sesión)."""

    def __init__(self, maximo=INTENTOS_MAXIMOS, bloqueo=BLOQUEO_SEGUNDOS, reloj=time.monotonic):
        self.maximo, self.bloqueo, self._reloj = maximo, bloqueo, reloj
        self.fallos, self.hasta = 0, 0.0

    def bloqueado(self):
        return self._reloj() < self.hasta

    def segundos_restantes(self):
        return max(0, int(self.hasta - self._reloj()) + 1)

    def fallo(self):
        self.fallos += 1
        if self.fallos >= self.maximo:
            self.hasta = self._reloj() + self.bloqueo
            self.fallos = 0

    def exito(self):
        self.fallos, self.hasta = 0, 0.0
