from datetime import datetime

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

from .config import CATEGORIA_NOMBRE, DATABASE_URL, SUBCATEGORIAS

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    categoria: Mapped[str] = mapped_column(String(20), index=True)
    subcategoria: Mapped[str] = mapped_column(String(20), default="", index=True)
    condicion: Mapped[str] = mapped_column(String(10), default="usado", index=True)
    talla: Mapped[str] = mapped_column(String(30), default="")
    marca: Mapped[str] = mapped_column(String(60), default="")
    precio: Mapped[int] = mapped_column(Integer)
    precio_antes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    costo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origen: Mapped[str] = mapped_column(String(10), default="propio")
    vendedor: Mapped[str] = mapped_column(String(120), default="")  # consignación
    creado_por: Mapped[str] = mapped_column(String(60), default="")  # admin / quién lo mandó por WhatsApp
    destacado: Mapped[bool] = mapped_column(Boolean, default=False)
    apartado: Mapped[bool] = mapped_column(Boolean, default=False)  # sin piezas libres: todas en pedidos
    piezas: Mapped[int] = mapped_column(Integer, default=1)    # piezas compradas (inventario total)
    vendidas: Mapped[int] = mapped_column(Integer, default=0)  # cache: suma de ventas
    apartadas: Mapped[int] = mapped_column(Integer, default=0)  # cache: en pedidos nuevos/confirmados
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    vendido: Mapped[bool] = mapped_column(Boolean, default=False)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    fotos: Mapped[list["Foto"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="Foto.orden")

    @property
    def sku(self) -> str:
        return f"RB-{self.id:04d}"

    @property
    def categoria_nombre(self) -> str:
        return CATEGORIA_NOMBRE.get(self.categoria, self.categoria)

    @property
    def subcategoria_nombre(self) -> str:
        return dict(SUBCATEGORIAS.get(self.categoria, [])).get(self.subcategoria, "")

    @property
    def foto(self) -> str | None:
        return self.fotos[0].url if self.fotos else None

    @property
    def disponibles(self) -> int:
        return max((self.piezas or 0) - (self.vendidas or 0) - (self.apartadas or 0), 0)

    @property
    def en_existencia(self) -> int:
        """Piezas que aún no se venden (incluye apartadas)."""
        return max((self.piezas or 0) - (self.vendidas or 0), 0)

    @property
    def margen(self) -> int | None:
        return None if self.costo is None else self.precio - self.costo

    @property
    def margen_pct(self) -> int | None:
        if self.costo is None or not self.costo:
            return None
        return round(100 * (self.precio - self.costo) / self.costo)

    @property
    def invertido(self) -> int:
        """Lo que pagaste por todas las piezas (consignación = 0)."""
        if self.origen == "consigna" or self.costo is None:
            return 0
        return self.costo * (self.piezas or 0)

    @property
    def descuento_pct(self) -> int:
        if self.precio_antes and self.precio_antes > self.precio:
            return round(100 * (self.precio_antes - self.precio) / self.precio_antes)
        return 0


class Foto(Base):
    __tablename__ = "fotos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"))
    archivo: Mapped[str] = mapped_column(String(255))
    orden: Mapped[int] = mapped_column(Integer, default=0)

    producto: Mapped[Producto] = relationship(back_populates="fotos")

    @property
    def url(self) -> str:
        if self.archivo.startswith(("/", "http")):
            return self.archivo
        return f"/media/{self.archivo}"


class Venta(Base):
    """Una venta (en web al entregar un pedido, o en persona). Guarda el costo de ese momento."""
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"),
                                                    nullable=True, index=True)
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id", ondelete="SET NULL"),
                                                  nullable=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    precio_unitario: Mapped[int] = mapped_column(Integer)
    costo_unitario: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origen_producto: Mapped[str] = mapped_column(String(10), default="propio")  # propio | consigna
    canal: Mapped[str] = mapped_column(String(10), default="tienda")  # web | tienda
    nota: Mapped[str] = mapped_column(String(250), default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Devolución: renglón con cantidad NEGATIVA que apunta a la venta original
    devolucion_de: Mapped[int | None] = mapped_column(ForeignKey("ventas.id", ondelete="CASCADE"),
                                                      nullable=True, index=True)

    producto: Mapped["Producto | None"] = relationship()
    devoluciones: Mapped[list["Venta"]] = relationship(cascade="all, delete-orphan", single_parent=True)

    @property
    def es_devolucion(self) -> bool:
        return self.cantidad < 0

    @property
    def devueltas(self) -> int:
        return -sum(d.cantidad for d in self.devoluciones)

    @property
    def devolvibles(self) -> int:
        return 0 if self.es_devolucion else self.cantidad - self.devueltas

    @property
    def total(self) -> int:
        return self.precio_unitario * self.cantidad

    @property
    def ganancia(self) -> int | None:
        if self.costo_unitario is None or self.origen_producto == "consigna":
            return None
        return (self.precio_unitario - self.costo_unitario) * self.cantidad


CATEGORIAS_GASTO = [
    ("servidor", "Servidor y dominio"),
    ("software", "Software y licencias"),
    ("transporte", "Transporte y viáticos"),
    ("publicidad", "Publicidad"),
    ("empaque", "Empaque y envíos"),
    ("fotos", "Fotos y producción"),
    ("otros", "Otros"),
]


class Gasto(Base):
    """Gasto de operación (no mercancía): servidor, licencias, pasajes… Cuenta como inversión."""
    __tablename__ = "gastos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concepto: Mapped[str] = mapped_column(String(160))
    categoria: Mapped[str] = mapped_column(String(20), default="otros", index=True)
    monto: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    nota: Mapped[str] = mapped_column(String(250), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def categoria_nombre(self) -> str:
        return dict(CATEGORIAS_GASTO).get(self.categoria, self.categoria)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    telefono: Mapped[str] = mapped_column(String(20), default="")
    password: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(10), default="cliente")  # cliente | admin
    municipio: Mapped[str] = mapped_column(String(60), default="")
    direccion: Mapped[str] = mapped_column(String(250), default="")
    referencias: Mapped[str] = mapped_column(String(250), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def primer_nombre(self) -> str:
        return (self.nombre or "").split(" ")[0]


METODOS_PAGO = [("efectivo", "Efectivo"), ("transferencia", "Transferencia"), ("deposito", "Depósito"),
                ("otro", "Otro")]

ESTADOS_PEDIDO = [("nuevo", "Nuevo"), ("confirmado", "Confirmado"), ("entregado", "Entregado"),
                  ("cancelado", "Cancelado")]


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    estado: Mapped[str] = mapped_column(String(12), default="nuevo", index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str] = mapped_column(String(20))
    municipio: Mapped[str] = mapped_column(String(60))
    direccion: Mapped[str] = mapped_column(String(250))
    referencias: Mapped[str] = mapped_column(String(250), default="")
    notas: Mapped[str] = mapped_column(Text, default="")
    subtotal: Mapped[int] = mapped_column(Integer, default=0)
    envio: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    # Pago (lo registra el admin a mano)
    pagado: Mapped[bool] = mapped_column(Boolean, default=False)
    metodo_pago: Mapped[str] = mapped_column(String(20), default="")
    monto_pagado: Mapped[int] = mapped_column(Integer, default=0)
    fecha_pago: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nota_pago: Mapped[str] = mapped_column(String(250), default="")

    usuario: Mapped[Usuario | None] = relationship()
    items: Mapped[list["PedidoItem"]] = relationship(back_populates="pedido", cascade="all, delete-orphan")

    @property
    def folio(self) -> str:
        return f"P-{self.id:05d}"

    @property
    def estado_nombre(self) -> str:
        return dict(ESTADOS_PEDIDO).get(self.estado, self.estado)

    @property
    def metodo_nombre(self) -> str:
        return dict(METODOS_PAGO).get(self.metodo_pago, self.metodo_pago)

    @property
    def por_cobrar(self) -> bool:
        return not self.pagado and self.estado in ("confirmado", "entregado")


class PedidoItem(Base):
    __tablename__ = "pedido_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="CASCADE"))
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(160))
    sku: Mapped[str] = mapped_column(String(20))
    precio: Mapped[int] = mapped_column(Integer)
    foto: Mapped[str] = mapped_column(String(300), default="")
    talla: Mapped[str] = mapped_column(String(30), default="")
    cantidad: Mapped[int] = mapped_column(Integer, default=1)

    @property
    def total(self) -> int:
        return self.precio * (self.cantidad or 1)

    pedido: Mapped[Pedido] = relationship(back_populates="items")
    producto: Mapped[Producto | None] = relationship()


def init_db() -> None:
    Base.metadata.create_all(engine)
    _agregar_columnas_faltantes()


def _agregar_columnas_faltantes() -> None:
    """Mini-migración: agrega columnas nuevas a tablas existentes (solo ADD COLUMN)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as con:
        for tabla in Base.metadata.sorted_tables:
            if not insp.has_table(tabla.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabla.name)}
            for col in tabla.columns:
                if col.name in existentes:
                    continue
                tipo = col.type.compile(engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                sql_default = ""
                if isinstance(default, bool):
                    sql_default = f" DEFAULT {int(default)}" if engine.dialect.name == "sqlite" else f" DEFAULT {str(default).lower()}"
                elif isinstance(default, (int, str)):
                    sql_default = f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {default}"
                con.execute(text(f'ALTER TABLE {tabla.name} ADD COLUMN {col.name} {tipo}{sql_default}'))
