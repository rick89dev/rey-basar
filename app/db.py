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


MODALIDADES = [("consigna", "Consignación"), ("compra", "Compra directa")]


class Contrato(Base):
    """Contrato con quien nos vende o deja a consignación sus piezas."""
    __tablename__ = "contratos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    modalidad: Mapped[str] = mapped_column(String(10), default="consigna")
    nombre: Mapped[str] = mapped_column(String(150))
    telefono: Mapped[str] = mapped_column(String(20), default="")
    domicilio: Mapped[str] = mapped_column(String(250), default="")
    ine_clave: Mapped[str] = mapped_column(String(30), default="")      # clave de elector / folio
    ine_archivo: Mapped[str] = mapped_column(String(120), default="")   # en PRIVADO_DIR, nunca público
    dias_exhibicion: Mapped[int] = mapped_column(Integer, default=60)
    dias_pago: Mapped[int] = mapped_column(Integer, default=7)
    # Consignación: cuotas acordadas en cada contrato (vacías = se llenan a mano en el impreso)
    cuota_retiro: Mapped[int | None] = mapped_column(Integer, nullable=True)       # por pieza, retiro anticipado
    almacenaje_semana: Mapped[int | None] = mapped_column(Integer, nullable=True)  # por pieza por semana
    dias_gracia: Mapped[int] = mapped_column(Integer, default=15)                  # tras el aviso, antes de cobrar almacenaje
    notas: Mapped[str] = mapped_column(Text, default="")
    firmado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_firma: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Prueba de firma (todo en PRIVADO_DIR): firmas dibujadas en pantalla o foto del contrato firmado en papel
    firmado_metodo: Mapped[str] = mapped_column(String(10), default="")     # pantalla | papel
    firma_vendedor: Mapped[str] = mapped_column(String(120), default="")
    firma_tienda: Mapped[str] = mapped_column(String(120), default="")
    archivo_firmado: Mapped[str] = mapped_column(String(120), default="")
    pdf_final: Mapped[str] = mapped_column(String(120), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    piezas: Mapped[list["ContratoPieza"]] = relationship(back_populates="contrato", cascade="all, delete-orphan",
                                                          order_by="ContratoPieza.id")

    @property
    def folio(self) -> str:
        return f"C-{self.id:04d}"

    @property
    def modalidad_nombre(self) -> str:
        return dict(MODALIDADES).get(self.modalidad, self.modalidad)

    @property
    def total_venta(self) -> int:
        return sum(p.precio_venta or 0 for p in self.piezas)

    @property
    def total_vendedor(self) -> int:
        return sum(p.pago_vendedor or 0 for p in self.piezas)

    def requiere_ine(self, desde: int) -> bool:
        return any((p.precio_venta or 0) >= desde for p in self.piezas)


class ContratoPieza(Base):
    __tablename__ = "contrato_piezas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contrato_id: Mapped[int] = mapped_column(ForeignKey("contratos.id", ondelete="CASCADE"))
    descripcion: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(60), default="")          # buenas condiciones, detalle…
    precio_venta: Mapped[int | None] = mapped_column(Integer, nullable=True)   # precio al que lo vendemos
    pago_vendedor: Mapped[int | None] = mapped_column(Integer, nullable=True)  # lo que recibe el vendedor
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"), nullable=True)

    contrato: Mapped[Contrato] = relationship(back_populates="piezas")
    producto: Mapped["Producto | None"] = relationship()


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
    _mover_ropa_a_subcategorias()


def _mover_ropa_a_subcategorias() -> None:
    """Nov 2026: Dama, Caballero, Niñas y Niños pasan a ser subcategorías de Ropa (idempotente)."""
    from sqlalchemy import text
    with engine.begin() as con:
        con.execute(text("UPDATE productos SET subcategoria = categoria, categoria = 'ropa' "
                         "WHERE categoria IN ('dama', 'caballero', 'ninas', 'ninos')"))
        # Deportes ya no tiene subcategorías: solo equipo y ejercicio.
        con.execute(text("UPDATE productos SET subcategoria = '' WHERE categoria = 'deportes' AND subcategoria != ''"))


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


ESTADOS_PUBLICACION = [("borrador", "Por aprobar"), ("programada", "Programadas"),
                       ("publicada", "Publicadas"), ("descartada", "Descartadas")]


class Publicacion(Base):
    """Admin → Marketing: una publicación de Facebook. La IA o la campaña la dejan en borrador
    y solo se publica cuando un admin la aprueba viendo la imagen final, el texto y los hashtags."""
    __tablename__ = "publicaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), default="producto")   # producto | campana
    titulo: Mapped[str] = mapped_column(String(120), default="")        # solo para el admin
    texto: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(String(400), default="")
    imagen: Mapped[str] = mapped_column(String(160), default="")        # en MEDIA_DIR/marketing
    # Para rehacer la imagen de una campaña sin volver a escribirla
    encabezado: Mapped[str] = mapped_column(String(160), default="")
    subtitulo: Mapped[str] = mapped_column(String(200), default="")
    productos: Mapped[str] = mapped_column(String(200), default="")     # ids "3,8,12"
    # Conceptos con escena de IA: lo necesario para recomponer la imagen sin pagar otra escena
    destacado: Mapped[str] = mapped_column(String(160), default="")     # parte del encabezado en dorado
    llamada: Mapped[str] = mapped_column(String(80), default="")        # etiqueta dorada del pie
    texto_arriba: Mapped[bool] = mapped_column(Boolean, default=True)
    escena: Mapped[str] = mapped_column(Text, default="")               # descripcion de la escena (para la IA)
    escena_archivo: Mapped[str] = mapped_column(String(160), default="")  # escena sin texto, en marketing/
    indicacion: Mapped[str] = mapped_column(Text, default="")           # ultima indicacion del admin a la IA
    trabajando: Mapped[bool] = mapped_column(Boolean, default=False)    # la IA la esta rehaciendo
    error_ia: Mapped[str] = mapped_column(String(300), default="")
    estado: Mapped[str] = mapped_column(String(12), default="borrador", index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    # Fecha que propone el sistema (o que el admin arrastra en el calendario) mientras está por
    # aprobar. Al aprobar con "Programar" se vuelve programada_para.
    propuesta_para: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    programada_para: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fb_post_id: Mapped[str] = mapped_column(String(80), default="")
    error: Mapped[str] = mapped_column(String(400), default="")
    aprobada_por: Mapped[str] = mapped_column(String(60), default="")
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    @property
    def imagen_url(self) -> str:
        return f"/media/marketing/{self.imagen}" if self.imagen else ""

    @property
    def ids_productos(self) -> list[int]:
        return [int(x) for x in self.productos.split(",") if x.strip().isdigit()]

    @property
    def mensaje(self) -> str:
        """Lo que se manda a Facebook: el texto y, al final, los hashtags."""
        return (self.texto.strip() + ("\n\n" + self.hashtags.strip() if self.hashtags.strip() else "")).strip()

    @property
    def fecha(self) -> datetime | None:
        """La fecha que se ve en el calendario, según el estado."""
        return {"borrador": self.propuesta_para, "programada": self.programada_para,
                "publicada": self.publicada_en}.get(self.estado)

    @property
    def fb_url(self) -> str:
        return f"https://www.facebook.com/{self.fb_post_id}" if self.fb_post_id else ""

