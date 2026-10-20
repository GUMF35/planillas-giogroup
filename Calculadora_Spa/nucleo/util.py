"""Utilidades puras: fechas en hora de El Salvador, montos, identificadores y normalización de textos."""
import math
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

ZONA_SV = timezone(timedelta(hours=-6))  # El Salvador no usa horario de verano
FORMATO_REGISTRO = "%Y-%m-%d %H:%M:%S"
CENTAVO = 0.005


def ahora_sv():
    return datetime.now(ZONA_SV)


def hoy_sv():
    return ahora_sv().date()


def marca_tiempo(momento=None):
    """'2026-10-20 14:32:05' en hora de El Salvador."""
    momento = momento or ahora_sv()
    if momento.tzinfo is not None:
        momento = momento.astimezone(ZONA_SV)
    return momento.strftime(FORMATO_REGISTRO)


def nuevo_id(prefijo):
    """Identificador único y legible: PAG-261020-1a2b3c4d."""
    return f"{prefijo}-{ahora_sv():%y%m%d}-{uuid.uuid4().hex[:8]}"


def texto(v):
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    t = str(v).strip()
    return "" if t.lower() in ("nan", "none", "nat") else t


def normalizar(v):
    """Mayúsculas, sin tildes y con un solo espacio entre palabras."""
    t = unicodedata.normalize("NFKD", texto(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().upper()


def numero(v, defecto=0.0):
    """Convierte '1,234.50', '$20', 20 o '20.5' a float. Vacío o ilegible → defecto."""
    if v is None or isinstance(v, bool):
        return defecto
    if isinstance(v, (int, float)):
        return defecto if isinstance(v, float) and math.isnan(v) else float(v)
    s = texto(v).replace("$", "").replace(" ", "")
    if not s:
        return defecto
    negativo = s.startswith("-") or s.startswith("(")
    s = s.strip("-()")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        s = s.replace(",", ".") if len(partes) == 2 and len(partes[1]) in (1, 2) else s.replace(",", "")
    try:
        n = float(s)
    except ValueError:
        return defecto
    return -n if negativo else n


def dinero(v):
    """Monto redondeado a centavos (mitad hacia arriba, como en contabilidad)."""
    n = numero(v)
    return math.floor(abs(n) * 100 + 0.5 + 1e-9) / 100 * (1 if n >= 0 else -1)


def es_cero(v):
    return abs(numero(v)) < CENTAVO


def usd(v):
    return f"${numero(v):,.2f}"


def fecha(v):
    """date desde '2026-10-20', '20/10/2026', datetime o date. None si no se puede leer."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = texto(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:19] if "%H" in fmt else s[:10], fmt).date()
        except ValueError:
            continue
    return None


def fecha_hora(v):
    """datetime (sin zona, hora local de El Salvador) desde '2026-10-20 08:02:00' o '2026-10-20 08:02'."""
    if isinstance(v, datetime):
        return v.astimezone(ZONA_SV).replace(tzinfo=None) if v.tzinfo else v
    s = texto(v)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def iso(d):
    return d.strftime("%Y-%m-%d") if d else ""


def clave_periodo(inicio, fin):
    """Clave estable de un período de planilla: '2026-09-01 al 2026-09-15'."""
    return f"{iso(fecha(inicio))} al {iso(fecha(fin))}"


def rango_de_clave(clave):
    """('2026-09-01 al 2026-09-15') → (date, date). None si no es una clave de período."""
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s+al\s+(\d{4}-\d{2}-\d{2})\s*$", texto(clave))
    if not m:
        return None
    return fecha(m.group(1)), fecha(m.group(2))


def quincenas_cercanas(hoy=None, antes=1, despues=2):
    """Quincenas estándar (1–15 y 16–fin de mes) alrededor de hoy, como claves de período."""
    hoy = hoy or hoy_sv()
    actual = 0 if hoy.day <= 15 else 1
    indice = hoy.year * 24 + (hoy.month - 1) * 2 + actual
    claves = []
    for i in range(indice - antes, indice + despues + 1):
        anio, resto = divmod(i, 24)
        mes, mitad = divmod(resto, 2)
        mes += 1
        if mitad == 0:
            ini, fin = date(anio, mes, 1), date(anio, mes, 15)
        else:
            siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
            ini, fin = date(anio, mes, 16), siguiente - timedelta(days=1)
        claves.append(clave_periodo(ini, fin))
    return claves


def palabras(v):
    return set(re.findall(r"[A-Z]+", normalizar(v)))
