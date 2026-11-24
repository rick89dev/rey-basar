"""Productos de EJEMPLO (categoría "Demo") con fotos de Unsplash (licencia libre).

Se cargan solos una vez al arrancar si REYBASAR_DEMO=1 (así lo hace iniciar.sh en local).
Borrarlos:  .venv/bin/python -m app.demo --borrar   (o desde el admin)
"""
import sys

from sqlalchemy import select

from . import catalogo
from .config import MEDIA_DIR
from .db import Foto, Producto, SessionLocal, init_db

MARCA = "ReyBasar Demo"
MARCADOR = MEDIA_DIR / ".demo_cargado"


def u(foto_id: str, ancho: int = 800) -> str:
    return f"https://images.unsplash.com/photo-{foto_id}?w={ancho}&q=70&fit=crop&auto=format"


PRODUCTOS = [
    dict(nombre="Camisa blanca de vestir", condicion="usado", talla="M", precio=250, precio_antes=350, costo=120, piezas=1,
         destacado=True, descripcion="Camisa blanca de manga larga, cuello clásico y botones al frente. "
         "Seminueva, sin manchas ni detalles. Producto de ejemplo para el demo.",
         fotos=["1603252109303-2751441dd157", "1603251578711-3290ca1a0187"]),
    dict(nombre="Blusa ligera de verano", condicion="nuevo", talla="CH", precio=220, costo=90, piezas=3, destacado=True,
         descripcion="Blusa ligera, ideal para el calor de Cuernavaca. Nueva con etiqueta. "
         "Producto de ejemplo para el demo.", fotos=["1558769132-cb1aea458c5e"]),
    dict(nombre="Playera blanca básica", condicion="nuevo", talla="10", precio=120, costo=50, piezas=5,
         descripcion="Playera de cuello redondo, básica para todos los días. Producto de ejemplo para el demo.",
         fotos=["1622290291468-a28f7a7dc6a8"]),
    dict(nombre="Oso de peluche con moño", condicion="usado", talla="", precio=180, precio_antes=240, costo=70, piezas=1,
         destacado=True, descripcion="Oso de peluche suave con moño rojo, limpio y en muy buen estado. "
         "Producto de ejemplo para el demo.", fotos=["1556012018-50c5c0da73bf"]),
    dict(nombre="Tren de madera", condicion="usado", talla="", precio=300, costo=150, piezas=2,
         descripcion="Tren de madera con vagones para armar, completo. Producto de ejemplo para el demo.",
         fotos=["1596461404969-9ae70f2830c1"]),
]


def cargar(forzar: bool = False) -> int:
    init_db()
    if MARCADOR.exists() and not forzar:
        return 0
    with SessionLocal() as db:
        if db.scalar(select(Producto.id).where(Producto.marca == MARCA)):
            MARCADOR.parent.mkdir(parents=True, exist_ok=True)
            MARCADOR.touch()
            return 0
        for d in PRODUCTOS:
            d = dict(d)
            fotos = d.pop("fotos")
            p = catalogo.crear(db, categoria="demo", marca=MARCA, creado_por="demo", **d)
            for i, f in enumerate(fotos):
                p.fotos.append(Foto(archivo=u(f), orden=i))
            db.commit()
    MARCADOR.parent.mkdir(parents=True, exist_ok=True)
    MARCADOR.touch()
    return len(PRODUCTOS)


def borrar() -> int:
    with SessionLocal() as db:
        demos = db.scalars(select(Producto).where(Producto.marca == MARCA)).all()
        for p in demos:
            catalogo.eliminar(db, p)
        return len(demos)


if __name__ == "__main__":
    if "--borrar" in sys.argv:
        print(f"{borrar()} productos demo borrados")
    elif "--reiniciar" in sys.argv:
        print(f"{borrar()} borrados, {cargar(forzar=True)} cargados de nuevo")
    else:
        print(f"{cargar(forzar=True)} productos demo cargados")
