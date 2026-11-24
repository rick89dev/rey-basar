"""Configuración de ReyBasar (variables de entorno con valores por defecto para el demo local)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path) -> None:
    """Lee KEY=VALOR de .env (sin pisar variables ya definidas)."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / ".env")

DATABASE_URL = os.getenv("REYBASAR_DATABASE_URL", f"sqlite:///{BASE_DIR / 'reybasar.db'}")
MEDIA_DIR = Path(os.getenv("REYBASAR_MEDIA_DIR", BASE_DIR / "media"))
SECRET_KEY = os.getenv("REYBASAR_SECRET_KEY", "cambia-esto-en-produccion")
# Correos que nacen administradores al registrarse (separados por coma). Vacío = el primero que se registre.
ADMINS = os.getenv("REYBASAR_ADMINS", "")
DEMO = os.getenv("REYBASAR_DEMO", "") == "1"  # carga productos de ejemplo una vez (solo local)
# IA para llenar fichas de producto desde el admin (misma clave de OpenAI que usa el bot)
OPENAI_API_KEY = os.getenv("REYBASAR_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
IA_MODELO = os.getenv("REYBASAR_IA_MODELO", "gpt-4o")
BOT_TOKEN = os.getenv("REYBASAR_BOT_TOKEN", "")  # Bearer para el bot de WhatsApp

WHATSAPP = os.getenv("REYBASAR_WHATSAPP", "527774166464")
TELEFONO = os.getenv("REYBASAR_TELEFONO", "(777) 416 64 64")
ACTUALIZACION_LEGAL = os.getenv("REYBASAR_ACTUALIZACION_LEGAL", "24 de noviembre de 2026")
FACEBOOK = os.getenv("REYBASAR_FACEBOOK", "https://www.facebook.com/ReyBasarOnline")

# Entregas: solo en Cuernavaca; el punto y la hora se acuerdan con el admin por WhatsApp.
ENTREGA_CIUDAD = os.getenv("REYBASAR_ENTREGA_CIUDAD", "Cuernavaca")
ENTREGA_COSTO = int(os.getenv("REYBASAR_ENTREGA_COSTO", "0"))  # 0 = se confirma por WhatsApp
ENTREGA_GRATIS_DESDE = int(os.getenv("REYBASAR_ENTREGA_GRATIS_DESDE", "0"))  # 0 = sin promoción

# Quiero vender: lo que recibe el vendedor (porcentaje del precio de venta)
CONSIGNA_PCT = int(os.getenv("REYBASAR_CONSIGNA_PCT", "60"))
COMPRA_DIRECTA_PCT = int(os.getenv("REYBASAR_COMPRA_DIRECTA_PCT", "35"))

CATEGORIAS = [
    ("dama", "Dama"),
    ("caballero", "Caballero"),
    ("ninas", "Niñas"),
    ("ninos", "Niños"),
    ("juguetes", "Juguetes"),
    ("electronicos", "Electrónicos"),
    ("deportes", "Deportes"),
    ("otros", "Otros"),
    ("demo", "Demo"),  # solo aparece en el menú si tiene productos
]
CATEGORIA_NOMBRE = dict(CATEGORIAS)
# Categorías con submenú
SUBCATEGORIAS = {
    "deportes": [("ninos", "Niños"), ("ninas", "Niñas"), ("hombre", "Hombre"), ("mujer", "Mujer")],
}
CONDICIONES = [("nuevo", "Nuevo"), ("usado", "Usado")]
ORIGENES = [("propio", "Propio"), ("consigna", "Consignación")]
