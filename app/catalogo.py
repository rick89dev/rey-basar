"""Lógica del catálogo: alta, edición, fotos y consultas."""
import re
import unicodedata
import uuid
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .config import CATEGORIA_NOMBRE, MEDIA_DIR
from .db import Foto, Producto

MAX_LADO = 1600


def slugify(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "producto"


def _slug_unico(db: Session, base: str, excluir: int | None = None) -> str:
    slug, n = base, 2
    while True:
        q = select(Producto.id).where(Producto.slug == slug)
        if excluir:
            q = q.where(Producto.id != excluir)
        if not db.scalar(q):
            return slug
        slug, n = f"{base}-{n}", n + 1


def guardar_imagen(datos: bytes) -> str:
    """Guarda la foto tal cual (solo orienta y limita a 1600px). Devuelve nombre relativo."""
    from io import BytesIO
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    img = ImageOps.exif_transpose(Image.open(BytesIO(datos)))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((MAX_LADO, MAX_LADO))
    nombre = f"{uuid.uuid4().hex[:16]}"
    if img.mode == "RGBA":
        nombre += ".png"
        img.save(MEDIA_DIR / nombre, optimize=True)
    else:
        nombre += ".jpg"
        img.save(MEDIA_DIR / nombre, quality=88, optimize=True)
    return nombre


def subcategoria_valida(categoria: str, sub: str | None) -> str:
    from .config import SUBCATEGORIAS
    return sub if sub and sub in dict(SUBCATEGORIAS.get(categoria, [])) else ""


def crear(db: Session, *, nombre: str, categoria: str, precio: int, fotos: list[bytes] = (),
          **campos) -> Producto:
    if categoria not in CATEGORIA_NOMBRE:
        raise ValueError(f"Categoría inválida: {categoria}")
    campos["subcategoria"] = subcategoria_valida(categoria, campos.get("subcategoria"))
    p = Producto(nombre=nombre.strip(), categoria=categoria, precio=int(precio), slug="tmp", **campos)
    db.add(p)
    db.flush()
    p.slug = _slug_unico(db, slugify(p.nombre))
    agregar_fotos(db, p, fotos)
    db.commit()
    return p


def actualizar(db: Session, p: Producto, **campos) -> Producto:
    for k, v in campos.items():
        setattr(p, k, v)
    if "nombre" in campos:
        p.slug = _slug_unico(db, slugify(p.nombre), excluir=p.id)
    db.commit()
    return p


def agregar_fotos(db: Session, p: Producto, fotos) -> None:
    orden = max((f.orden for f in p.fotos), default=-1) + 1
    for datos in fotos:
        if datos:
            p.fotos.append(Foto(archivo=guardar_imagen(datos), orden=orden))
            orden += 1


def quitar_foto(db: Session, foto: Foto) -> None:
    _borrar_archivo(foto.archivo)
    db.delete(foto)
    db.commit()


def hacer_principal(db: Session, p: Producto, foto_id: int) -> None:
    fotos = sorted(p.fotos, key=lambda f: (f.id != foto_id, f.orden))
    for i, f in enumerate(fotos):
        f.orden = i
    db.commit()


def tiene_ventas(db: Session, p: Producto) -> bool:
    from .db import Venta
    return bool(db.scalar(select(Venta.id).where(Venta.producto_id == p.id).limit(1)))


def eliminar(db: Session, p: Producto) -> None:
    for f in p.fotos:
        _borrar_archivo(f.archivo)
    db.delete(p)
    db.commit()


def _borrar_archivo(nombre: str) -> None:
    if "/" not in nombre:
        Path(MEDIA_DIR / nombre).unlink(missing_ok=True)


def _base():
    return (select(Producto).options(selectinload(Producto.fotos))
            .where(Producto.visible.is_(True), Producto.vendido.is_(False)))


def listar(db: Session, *, categoria: str | None = None, subcategoria: str | None = None,
           condicion: str | None = None,
           texto: str | None = None, orden: str = "nuevos", limite: int | None = None,
           destacados: bool = False, descuentos: bool = False) -> list[Producto]:
    q = _base()
    if categoria:
        q = q.where(Producto.categoria == categoria)
    if subcategoria:
        q = q.where(Producto.subcategoria == subcategoria)
    if condicion:
        q = q.where(Producto.condicion == condicion)
    if destacados:
        q = q.where(Producto.destacado.is_(True))
    if descuentos:
        q = q.where(Producto.precio_antes > Producto.precio)
    if texto:
        like = f"%{texto.strip()}%"
        filtros = [Producto.nombre.ilike(like), Producto.descripcion.ilike(like),
                   Producto.marca.ilike(like)]
        m = re.fullmatch(r"(?i)rb-?0*(\d+)", texto.strip())
        if m:
            filtros.append(Producto.id == int(m.group(1)))
        q = q.where(or_(*filtros))
    q = q.order_by({"precio_asc": Producto.precio.asc(), "precio_desc": Producto.precio.desc()}
                   .get(orden, Producto.id.desc()))
    if limite:
        q = q.limit(limite)
    return list(db.scalars(q))


def por_slug(db: Session, slug: str) -> Producto | None:
    return db.scalar(select(Producto).options(selectinload(Producto.fotos))
                     .where(Producto.slug == slug))


def todos_admin(db: Session, texto: str = "", estado: str = "") -> list[Producto]:
    q = select(Producto).options(selectinload(Producto.fotos)).order_by(Producto.id.desc())
    if texto:
        like = f"%{texto}%"
        m = re.fullmatch(r"(?i)rb-?0*(\d+)", texto.strip())
        q = q.where(or_(Producto.nombre.ilike(like), Producto.id == int(m.group(1)) if m else False))
    if estado == "vendidos":
        q = q.where(Producto.vendido.is_(True))
    elif estado == "ocultos":
        q = q.where(Producto.visible.is_(False))
    elif estado == "consigna":
        q = q.where(Producto.origen == "consigna")
    elif estado == "disponibles":
        q = q.where(Producto.vendido.is_(False), Producto.apartado.is_(False))
    elif estado == "sin_costo":
        q = q.where(Producto.origen == "propio", Producto.costo.is_(None))
    return list(db.scalars(q))


# ---------------------------------------------------------------- inventario y ventas
from sqlalchemy import func  # noqa: E402

from .db import Pedido, PedidoItem, Venta  # noqa: E402

PEDIDO_ABIERTO = ("nuevo", "confirmado")


def recalcular(db: Session, p: Producto) -> None:
    """Actualiza vendidas/apartadas y las banderas vendido/apartado a partir de ventas y pedidos."""
    p.vendidas = db.scalar(select(func.coalesce(func.sum(Venta.cantidad), 0))
                           .where(Venta.producto_id == p.id)) or 0
    p.apartadas = db.scalar(select(func.coalesce(func.sum(PedidoItem.cantidad), 0))
                            .join(Pedido, Pedido.id == PedidoItem.pedido_id)
                            .where(PedidoItem.producto_id == p.id, Pedido.estado.in_(PEDIDO_ABIERTO))) or 0
    p.vendido = p.vendidas >= (p.piezas or 0)
    p.apartado = not p.vendido and p.disponibles == 0


def registrar_venta(db: Session, p: Producto, cantidad: int, precio_unitario: int, *, canal: str = "tienda",
                    pedido_id: int | None = None, nota: str = "") -> Venta:
    v = Venta(producto_id=p.id, pedido_id=pedido_id, nombre=p.nombre, sku=p.sku, cantidad=cantidad,
              precio_unitario=precio_unitario, costo_unitario=p.costo, origen_producto=p.origen,
              canal=canal, nota=nota[:250])
    db.add(v)
    db.flush()
    recalcular(db, p)
    return v


def registrar_devolucion(db: Session, v: Venta, cantidad: int, monto_por_pieza: int, nota: str = "") -> Venta:
    """Devolución de piezas de una venta: renglón negativo; las piezas regresan al inventario."""
    if v.es_devolucion or cantidad < 1 or cantidad > v.devolvibles:
        raise ValueError(f"Solo puedes devolver hasta {v.devolvibles} pieza(s) de esta venta.")
    d = Venta(producto_id=v.producto_id, pedido_id=v.pedido_id, nombre=v.nombre, sku=v.sku,
              cantidad=-cantidad, precio_unitario=monto_por_pieza, costo_unitario=v.costo_unitario,
              origen_producto=v.origen_producto, canal="devolucion", nota=nota[:250], devolucion_de=v.id)
    db.add(d)
    db.flush()
    if v.producto:
        recalcular(db, v.producto)
    return d


def ultimas_ventas(db: Session, limite: int = 15) -> list[Venta]:
    return list(db.scalars(select(Venta).order_by(Venta.id.desc()).limit(limite)))


def borrar_venta(db: Session, v: Venta) -> None:
    p = v.producto
    db.delete(v)
    db.flush()
    if p:
        recalcular(db, p)


def ventas_de(db: Session, producto_id: int) -> list[Venta]:
    return list(db.scalars(select(Venta).where(Venta.producto_id == producto_id).order_by(Venta.id.desc())))


def resumen_finanzas(db: Session) -> dict:
    """
    Inversión total = mercancía (costo × piezas compradas, solo propias) + gastos de operación.
    Recuperado = el costo de las piezas propias ya vendidas.
    Ganancia = lo cobrado por encima del costo en piezas propias.
    Por recuperar = mercancía - recuperado (lo que tienes en piezas sin vender).
    Ganancia neta = ganancia - gastos.
    Balance = ventas de piezas propias - inversión total (negativo = números rojos).
    """
    from .db import Gasto
    productos = db.scalars(select(Producto)).all()
    mercancia = sum(p.invertido for p in productos)
    gastos = db.scalar(select(func.coalesce(func.sum(Gasto.monto), 0))) or 0
    inversion = mercancia + gastos
    sin_costo = sum(1 for p in productos if p.origen == "propio" and p.costo is None)
    ventas = db.scalars(select(Venta)).all()
    propias = [v for v in ventas if v.origen_producto != "consigna"]
    cobrado_propio = sum(v.total for v in propias)
    recuperado = sum((v.costo_unitario or 0) * v.cantidad for v in propias)
    ganancia = sum(v.ganancia or 0 for v in propias)
    consigna = sum(v.total for v in ventas if v.origen_producto == "consigna")
    devoluciones = [v for v in ventas if v.cantidad < 0]
    return {
        "inversion": inversion,
        "mercancia": mercancia,
        "gastos": gastos,
        "ganancia_neta": ganancia - gastos,
        "ventas": sum(v.total for v in ventas),
        "ventas_consigna": consigna,
        "recuperado": recuperado,
        "ganancia": ganancia,
        "por_recuperar": mercancia - recuperado,
        "balance": cobrado_propio - inversion,
        "piezas_vendidas": sum(v.cantidad for v in ventas),
        "devoluciones": -sum(v.total for v in devoluciones),
        "piezas_devueltas": -sum(v.cantidad for v in devoluciones),
        "piezas_existencia": sum(p.en_existencia for p in productos if p.visible),
        "sin_costo": sin_costo,
        # cuánto de lo que has puesto (mercancía + gastos) ya regresó en ventas
        "recuperado_pct": round(100 * cobrado_propio / inversion) if inversion else 0,
        **_por_cobrar(db),
    }


def sincronizar(db: Session) -> None:
    """Al arrancar: ventas para pedidos entregados que no las tengan y existencias recalculadas."""
    for ped in db.scalars(select(Pedido).where(Pedido.estado == "entregado")).all():
        if not db.scalar(select(Venta.id).where(Venta.pedido_id == ped.id).limit(1)):
            for it in ped.items:
                if it.producto:
                    registrar_venta(db, it.producto, it.cantidad or 1, it.precio, canal="web", pedido_id=ped.id)
    for p in db.scalars(select(Producto)).all():
        recalcular(db, p)
    db.commit()


def _por_cobrar(db: Session) -> dict:
    """Pedidos confirmados o entregados que todavía no registras como pagados."""
    pend = db.scalars(select(Pedido).where(Pedido.pagado.is_(False),
                                           Pedido.estado.in_(("confirmado", "entregado")))).all()
    return {"por_cobrar": sum(p.total for p in pend), "pedidos_por_cobrar": len(pend)}
