"""Piezas comunes de las rutas: plantillas, base de datos y usuario en sesión."""
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from . import config
from .auth import usuario_actual
from .config import BASE_DIR, CATEGORIAS, SUBCATEGORIAS
from .db import Producto, SessionLocal

APP_DIR = BASE_DIR / "app"
templates = Jinja2Templates(directory=APP_DIR / "templates")


def pesos(v) -> str:
    return f"${int(v):,}" if v is not None else ""


# Fotos de categoría: Unsplash (licencia libre, uso comercial permitido). Si existe
# app/static/img/categorias/foto-<clave>.jpg se usa la copia local (diseno/descargar_fotos.sh).
FOTOS_CATEGORIA = {
    "dama": "1612423284934-2850a4ea6b0f",       # blusas estampadas en ganchos de madera
    "caballero": "1489987707025-afc232f7ea0f",  # camisas colgadas
    "ninas": "1622290291720-ac961c43ee30",      # ropa de bebé rosa
    "ninos": "1622290319146-7b63df48a635",      # ropa de bebé azul
    "juguetes": "1596461404969-9ae70f2830c1",   # tren de madera
    "otros": "1540221652346-e5dd6b50f3e7",      # ropa en perchero de madera
    "demo": "1603252109303-2751441dd157",       # camisa blanca en gancho
}


def foto_categoria(clave: str, ancho: int = 900) -> str:
    local = APP_DIR / "static" / "img" / "categorias" / f"foto-{clave}.jpg"
    if local.exists():
        return f"/static/img/categorias/foto-{clave}.jpg"
    return (f"https://images.unsplash.com/photo-{FOTOS_CATEGORIA.get(clave, FOTOS_CATEGORIA['otros'])}"
            f"?w={ancho}&q=75&fit=crop&auto=format")


templates.env.filters["pesos"] = pesos
templates.env.globals.update(cfg=config, CATEGORIAS=CATEGORIAS, SUBCATEGORIAS=SUBCATEGORIAS, quote=quote,
                             foto_categoria=foto_categoria, dict=dict)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def o404(obj):
    if obj is None:
        raise HTTPException(404)
    return obj


def menu_categorias(db) -> list[tuple[str, str]]:
    """Categorías del menú: todas, excepto 'demo' si no tiene productos visibles."""
    hay_demo = db.scalar(select(func.count()).select_from(Producto).where(
        Producto.categoria == "demo", Producto.visible.is_(True)))
    return [(k, n) for k, n in CATEGORIAS if k != "demo" or hay_demo]


def render(request: Request, nombre: str, status_code: int = 200, **ctx):
    db = SessionLocal()
    try:
        ctx.setdefault("usuario", usuario_actual(request, db))
        ctx.setdefault("menu", menu_categorias(db))
        return templates.TemplateResponse(request, nombre, ctx, status_code=status_code)
    finally:
        db.close()
