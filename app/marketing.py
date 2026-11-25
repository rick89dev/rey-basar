"""
Admin → Marketing: publicaciones para la página de Facebook de ReyBasar.

Nada se publica sin que un admin lo apruebe viendo la imagen final, el texto y los hashtags
(decisión de Ricardo, nov 2026). Las publicaciones nacen de dos lados:
  - la campaña de arranque ("Estamos de regreso" y "Quiero vender"), ya escrita;
  - piezas de la tienda que el admin elige: la imagen sale de sus fotos reales y la IA escribe
    el texto con los datos de la pieza (nunca inventa precio, talla ni estado).

Programar: la guardamos nosotros con su hora y la publica el revisor que corre dentro de la
app cada minuto. No usamos la programación de Facebook para poder cancelar o editar desde
aquí hasta el último momento, y para no depender de sus reglas de fotos programadas.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from . import config, marketing_ia, marketing_img
from .admin_extra import solo_admin
from .db import ESTADOS_PUBLICACION, Producto, Publicacion, SessionLocal, Usuario
from .web import get_db, o404, render

router = APIRouter(prefix="/admin/marketing")
MAX_PIEZAS = 4
BASE_HASHTAGS = "#ReyBasar #Cuernavaca #Morelos"


def _volver(pid: int | None = None, **q) -> RedirectResponse:
    extra = "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
    ruta = f"/admin/marketing/{pid}" if pid else "/admin/marketing"
    return RedirectResponse(ruta + (f"?{extra}" if extra else ""), 303)


def _productos(db, ids: list[int]) -> list[Producto]:
    if not ids:
        return []
    filas = {p.id: p for p in db.scalars(select(Producto).options(selectinload(Producto.fotos))
                                         .where(Producto.id.in_(ids)))}
    return [filas[i] for i in ids if i in filas]


# ── campaña de arranque ──────────────────────────────────────────────────────
# (clave, titulo, encabezado de la imagen, subtitulo, texto, hashtags extra)
# R8 no va aquí: es "lo nuevo de la semana" y se arma con las piezas reales.
CAMPANA = [
    ("R1", "Regreso · El anuncio", "¡ReyBasar está de regreso!",
     "Ropa y juguetes nuevos y seminuevos, ahora con tienda en línea",
     "¡ReyBasar está de regreso!\n\nDespués de una pausa, volvemos con todo y ahora con tienda en línea: "
     "ropa y juguetes nuevos y seminuevos, revisados y a buen precio, aquí en Cuernavaca.\n\n"
     "Gracias a quienes nos siguieron todo este tiempo. Esto apenas empieza.\n\n"
     "Ve lo que ya tenemos: {sitio}", "#EstamosDeRegreso #RopaSeminueva #Juguetes"),
    ("R2", "Regreso · Nuestra historia", "¿Basar con S?", "No es error de ortografía. Te contamos por qué.",
     "¿Basar con S? Sí, lo sabemos. No es error de ortografía.\n\n"
     "ReyBasar nació en 2019 como un proyecto familiar en Cuernavaca. Al elegir el nombre quisimos que "
     "cada persona que lo comenzó estuviera presente con la inicial de su nombre. Por eso la S está ahí, "
     "y es muy especial para nosotros.\n\nLa pandemia nos obligó a pausar, pero hoy volvemos con más ganas.\n\n"
     "Conoce la historia completa: {sitio}/sobre-nosotros", "#NegocioFamiliar #HechoEnCuernavaca"),
    ("R3", "Regreso · Qué vendemos", "¿Qué encuentras en ReyBasar?",
     "Ropa · Juguetes · Electrónicos · Deportes · Alberca y verano",
     "¿Qué encuentras en ReyBasar?\n\n- Ropa para dama, caballero, niñas y niños\n- Juguetes\n- Electrónicos\n"
     "- Deportes y ejercicio\n- Alberca y verano\n\nNuevo y seminuevo, todo revisado y con fotos reales de "
     "cada pieza.\n\nEcha un vistazo: {sitio}", "#RopaSeminueva #Juguetes #ComprasCuernavaca"),
    ("R4", "Regreso · Cómo comprar", "Comprar es así de fácil", "Elige · Agrega al carrito · Te contactamos por WhatsApp",
     "Comprar en ReyBasar es así de fácil:\n\n1. Entra a {sitio} y elige lo que te guste.\n"
     "2. Agrégalo al carrito y envía tu pedido.\n3. Te contactamos por WhatsApp para confirmar y acordar "
     "dónde te lo entregamos.\n\nSin complicaciones y sin quedar con desconocidos.\n\n"
     "¿Dudas? Escríbenos al WhatsApp {telefono}.", "#ComprasEnLinea #ComprasCuernavaca"),
    ("R5", "Regreso · Nuevo y seminuevo", "¿Nuevo o seminuevo?", "Tenemos los dos. Lo que ves en la foto es lo que recibes.",
     "¿Nuevo o seminuevo? En ReyBasar tenemos los dos.\n\nCada pieza dice claramente si es nueva o seminueva, "
     "y las seminuevas las revisamos antes de publicarlas. Si tiene algún detalle, te lo decimos en la "
     "descripción.\n\nLo que ves en la foto es lo que recibes.\n\n{sitio}", "#RopaSeminueva #ModaCircular"),
    ("R6", "Regreso · Entregas", "Somos de aquí y entregamos aquí", "Entregas en Cuernavaca, en el punto que te quede mejor",
     "Somos de aquí y entregamos aquí.\n\nHacemos entregas en Cuernavaca y acordamos contigo el punto de entrega "
     "que te quede mejor. Sin envíos de paquetería ni esperas de semanas.\n\n"
     "Haz tu pedido en {sitio} o escríbenos al WhatsApp {telefono}.", "#ComprasCuernavaca #EntregasLocales"),
    ("R7", "Regreso · La tienda en línea", "Conoce nuestra tienda en línea", "Busca por categoría, filtra nuevo o seminuevo y pide desde tu celular",
     "Te damos un recorrido por nuestra nueva tienda en línea.\n\nBusca por categoría, filtra por nuevo o "
     "seminuevo, mira todas las fotos de cada pieza y arma tu pedido desde el celular.\n\nPruébala tú: {sitio}",
     "#ComprasEnLinea #TiendaEnLinea"),
    ("V1", "Quiero vender · Te compramos", "Lo que ya no usas, conviértelo en dinero hoy", "Te compramos ropa y juguetes en buen estado",
     "¿Tienes ropa o juguetes en buen estado que ya no usas?\n\nTe los compramos y te pagamos al momento. "
     "Sin publicar, sin esperar a que alguien se interese y sin quedar con desconocidos.\n\n"
     "Mándanos fotos y te decimos cuánto te damos: {sitio}/quiero-vender", "#VendeTuRopa #DineroExtra"),
    ("V2", "Quiero vender · ¿Y si lo vendo yo?", "¿Y si lo vendo yo?", "Claro que puedes. Esto es lo que te ahorras con ReyBasar.",
     "Claro que puedes venderlo tú. Pero piensa en lo que te toca:\n\n- Tomar fotos y publicar pieza por pieza\n"
     "- Contestar mil veces \"¿sigue disponible?\"\n- Aguantar el regateo\n- Quedar con desconocidos que a veces "
     "ni llegan\n- Esperar semanas\n\nCon ReyBasar te lo compramos y te pagamos hoy mismo.\n\n{sitio}/quiero-vender",
     "#VendeTuRopa #DineroExtra"),
    ("V3", "Quiero vender · Cómo funciona", "Vender en 3 pasos", "1. Fotos  ·  2. Oferta  ·  3. Dinero",
     "Vender con ReyBasar en 3 pasos:\n\n1. Nos mandas fotos de lo que quieres vender.\n2. Te decimos cuánto te "
     "pagamos.\n3. Nos vemos en Cuernavaca, revisamos las piezas, firmamos un contrato sencillo y te pagamos al "
     "momento.\n\nSi prefieres esperar a que se venda, también lo dejamos a consignación.\n\n"
     "Empieza aquí: {sitio}/quiero-vender", "#VendeTuRopa #Consignacion"),
    ("V4", "Quiero vender · Limpia tu clóset", "Libera espacio y gana dinero", "En el mismo día",
     "Esa ropa que ya no le queda a los niños. Esos juguetes que ya nadie usa. Esa prenda que nunca estrenaste.\n\n"
     "Libera espacio y gana dinero en el mismo día. Nosotros nos encargamos de darle una segunda vida.\n\n"
     "{sitio}/quiero-vender", "#LimpiaTuCloset #VendeTuRopa"),
    ("V5", "Quiero vender · Recordatorio", "Lo que ya no usas vale dinero", "Te compramos ropa y juguetes y te pagamos al momento",
     "Recordatorio: lo que ya no usas vale dinero.\n\nEn ReyBasar te compramos ropa y juguetes en buen estado y "
     "te pagamos al momento, aquí en Cuernavaca.\n\nEscríbenos al WhatsApp {telefono} o entra a {sitio}/quiero-vender",
     "#VendeTuRopa #DineroExtra"),
]


HORA_PROPUESTA = 20   # 8 pm: cuando las familias revisan el celular


def _dias_ocupados(db) -> set:
    dias = set()
    for p in db.scalars(select(Publicacion).where(Publicacion.estado.in_(("borrador", "programada")))):
        if p.fecha:
            dias.add(p.fecha.date())
    return dias


def siguiente_libre(db, ocupados: set | None = None) -> datetime:
    """Primer día desde mañana sin otra publicación por aprobar o programada, a las 8 pm."""
    ocupados = _dias_ocupados(db) if ocupados is None else ocupados
    dia = (datetime.now() + timedelta(days=1)).replace(hour=HORA_PROPUESTA, minute=0, second=0, microsecond=0)
    while dia.date() in ocupados:
        dia += timedelta(days=1)
    ocupados.add(dia.date())
    return dia


def proponer_fechas(db) -> int:
    """Da fecha propuesta, en orden, a las publicaciones por aprobar que no tienen."""
    ocupados = _dias_ocupados(db)
    sin = list(db.scalars(select(Publicacion).where(Publicacion.estado == "borrador",
                                                    Publicacion.propuesta_para.is_(None))
                          .order_by(Publicacion.orden, Publicacion.id)))
    for p in sin:
        p.propuesta_para = siguiente_libre(db, ocupados)
    db.commit()
    return len(sin)


def _telefono() -> str:
    t = "".join(c for c in config.WHATSAPP if c.isdigit())[-10:]
    return f"{t[:3]} {t[3:6]} {t[6:]}" if len(t) == 10 else config.WHATSAPP


def cargar_campana(db) -> int:
    """Crea en borrador las publicaciones de la campaña que todavía no existan."""
    ya = set(db.scalars(select(Publicacion.titulo).where(Publicacion.tipo == "campana")))
    sitio = config.SITIO_URL.replace("https://", "")
    nuevas = 0
    for orden, (_, titulo, enc, sub, texto, tags) in enumerate(CAMPANA):
        if titulo in ya:
            continue
        db.add(Publicacion(tipo="campana", titulo=titulo, encabezado=enc, subtitulo=sub, orden=orden,
                           texto=texto.format(sitio=sitio, telefono=_telefono()),
                           hashtags=f"{BASE_HASHTAGS} {tags}",
                           imagen=marketing_img.tarjeta(enc, sub)))
        nuevas += 1
    db.commit()
    proponer_fechas(db)
    return nuevas


# ── textos de productos con IA ───────────────────────────────────────────────
REGLAS = """Escribes publicaciones de Facebook para ReyBasar, una tienda en Cuernavaca, México, de ropa y
juguetes NUEVOS y SEMINUEVOS. Las piezas son únicas. Entregamos solo en Cuernavaca, en un punto que
acordamos con el cliente. Pedidos en {sitio} o por WhatsApp al {telefono}.

Te paso los datos reales de 1 a 4 piezas. Devuelve:
- texto: español de México, cálido y directo, de 3 a 6 renglones cortos. Menciona cada pieza con su
  precio exacto y si es nueva o seminueva; la talla solo si viene en los datos. Usa SOLO los datos que
  te paso: prohibido inventar marcas, materiales, medidas, descuentos o promociones. Termina invitando a
  pedirla en el enlace que te paso (o en {sitio} si son varias) y recordando que son piezas únicas.
  Como máximo 2 emojis en todo el texto. No pongas hashtags en el texto.
- hashtags: de 5 a 8 hashtags en español, separados por espacio, relevantes a las piezas. Incluye
  siempre #ReyBasar y #Cuernavaca."""

ESQUEMA = {"type": "object", "additionalProperties": False, "required": ["texto", "hashtags"],
           "properties": {"texto": {"type": "string"}, "hashtags": {"type": "string"}}}


def _datos_pieza(p: Producto) -> dict:
    return {"nombre": p.nombre, "precio": p.precio, "precio_antes": p.precio_antes,
            "estado": "nuevo" if p.condicion == "nuevo" else "seminuevo", "talla": p.talla or None,
            "marca": p.marca or None, "categoria": p.categoria_nombre, "descripcion": p.descripcion[:400],
            "enlace": f"{config.SITIO_URL.replace('https://', '')}/producto/{p.slug}"}


def _texto_plantilla(piezas: list[Producto]) -> tuple[str, str]:
    """Sin clave de OpenAI (o si falla): un texto sencillo y correcto con los datos reales."""
    sitio = config.SITIO_URL.replace("https://", "")
    renglones = []
    for p in piezas:
        estado = "Nuevo" if p.condicion == "nuevo" else "Seminuevo"
        talla = f" · Talla {p.talla}" if p.talla else ""
        renglones.append(f"{p.nombre} · {estado}{talla} · ${p.precio:,}")
    destino = f"{sitio}/producto/{piezas[0].slug}" if len(piezas) == 1 else sitio
    texto = ("Nuevo en ReyBasar:\n\n" if len(piezas) > 1 else "") + "\n".join(renglones) + \
        f"\n\nSon piezas únicas: cuando se van, se van.\nPíde{'la' if len(piezas) == 1 else 'las'} en {destino} " \
        f"o por WhatsApp al {_telefono()}."
    return texto, f"{BASE_HASHTAGS} #RopaSeminueva #ModaCircular"


async def texto_ia(piezas: list[Producto]) -> tuple[str, str]:
    if not config.OPENAI_API_KEY:
        return _texto_plantilla(piezas)
    try:
        from openai import AsyncOpenAI
        cliente = AsyncOpenAI(api_key=config.OPENAI_API_KEY, timeout=45)
        r = await cliente.chat.completions.create(
            model=config.IA_MODELO, temperature=0.7,
            messages=[{"role": "system", "content": REGLAS.format(
                          sitio=config.SITIO_URL.replace("https://", ""), telefono=_telefono())},
                      {"role": "user", "content": json.dumps([_datos_pieza(p) for p in piezas], ensure_ascii=False)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "publicacion", "schema": ESQUEMA, "strict": True}})
        d = json.loads(r.choices[0].message.content or "{}")
        texto, tags = (d.get("texto") or "").strip(), (d.get("hashtags") or "").strip()
        if not texto:
            return _texto_plantilla(piezas)
        for base in ("#ReyBasar", "#Cuernavaca"):
            if base.lower() not in tags.lower():
                tags = f"{base} {tags}".strip()
        return texto, tags
    except Exception:
        return _texto_plantilla(piezas)


# ── Facebook ─────────────────────────────────────────────────────────────────
class ErrorFacebook(Exception):
    pass


async def publicar_en_facebook(pub: Publicacion) -> str:
    """Sube la imagen con su texto a la página. Devuelve el id del post."""
    if not (config.FB_PAGE_ID and config.FB_PAGE_TOKEN):
        raise ErrorFacebook("Falta conectar la página: REYBASAR_FB_PAGE_ID y REYBASAR_FB_PAGE_TOKEN en el servidor.")
    import httpx
    ruta = marketing_img.CARPETA / pub.imagen
    if not pub.imagen or not ruta.exists():
        raise ErrorFacebook("La publicación no tiene imagen.")
    async with httpx.AsyncClient(timeout=90) as cliente:
        r = await cliente.post(f"{config.FB_GRAPH}/{config.FB_PAGE_ID}/photos",
                               data={"message": pub.mensaje, "published": "true",
                                     "access_token": config.FB_PAGE_TOKEN},
                               files={"source": (ruta.name, ruta.read_bytes(), "image/jpeg")})
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200 or not (d.get("post_id") or d.get("id")):
        msg = (d.get("error") or {}).get("message") or r.text[:200]
        raise ErrorFacebook(f"Facebook respondió {r.status_code}: {msg}")
    return d.get("post_id") or f"{config.FB_PAGE_ID}_{d['id']}"


async def _publicar(db, pub: Publicacion) -> None:
    try:
        pub.fb_post_id = await publicar_en_facebook(pub)
        pub.estado, pub.publicada_en, pub.error = "publicada", datetime.now(), ""
    except ErrorFacebook as e:
        pub.error = str(e)[:400]
    except Exception as e:  # red, timeout: se queda donde estaba y se ve el error
        pub.error = f"No se pudo conectar con Facebook: {type(e).__name__}"[:400]
    db.commit()


async def revisar_programadas() -> int:
    """Publica las programadas cuya hora ya llegó. Lo llama el bucle de fondo cada minuto."""
    hechas = 0
    with SessionLocal() as db:
        pendientes = list(db.scalars(select(Publicacion).where(
            Publicacion.estado == "programada", Publicacion.programada_para <= datetime.now(),
            Publicacion.error == "")))
        for pub in pendientes:
            await _publicar(db, pub)
            hechas += pub.estado == "publicada"
    return hechas


async def bucle_programadas() -> None:
    while True:
        try:
            await revisar_programadas()
        except Exception:
            pass
        await asyncio.sleep(60)


# ── pantallas ────────────────────────────────────────────────────────────────
SEMANAS = 4
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


@router.get("", response_class=HTMLResponse)
def lista(request: Request, estado: str = "", ok: str = "", semana: int = 0, yo: Usuario = Depends(solo_admin),
          db=Depends(get_db)):
    if estado not in dict(ESTADOS_PUBLICACION):
        return calendario(request, ok, semana, db)
    orden = {"borrador": (Publicacion.orden, Publicacion.id), "programada": (Publicacion.programada_para,),
             "publicada": (Publicacion.publicada_en.desc(),), "descartada": (Publicacion.id.desc(),)}[estado]
    pubs = list(db.scalars(select(Publicacion).where(Publicacion.estado == estado).order_by(*orden)))
    conteo = dict(db.execute(select(Publicacion.estado, func.count()).group_by(Publicacion.estado)).all())
    campana_cargada = db.scalar(select(func.count()).where(Publicacion.tipo == "campana")) or 0
    return render(request, "admin/marketing.html", pubs=pubs, estado=estado, estados=ESTADOS_PUBLICACION,
                  conteo=conteo, ok=ok, campana_cargada=campana_cargada, total_campana=len(CAMPANA),
                  fb_listo=bool(config.FB_PAGE_ID and config.FB_PAGE_TOKEN))


def calendario(request: Request, ok: str, semana: int, db):
    hoy = datetime.now().date()
    inicio = hoy - timedelta(days=hoy.weekday()) + timedelta(weeks=max(min(semana, 52), -52))
    fin = inicio + timedelta(weeks=SEMANAS)
    por_dia: dict = {}
    sin_fecha = []
    for p in db.scalars(select(Publicacion).where(Publicacion.estado.in_(("borrador", "programada", "publicada")))
                        .order_by(Publicacion.orden, Publicacion.id)):
        f = p.fecha
        if f is None:
            if p.estado == "borrador":
                sin_fecha.append(p)
        elif inicio <= f.date() < fin:
            por_dia.setdefault(f.date(), []).append(p)
    for lista_dia in por_dia.values():
        lista_dia.sort(key=lambda p: p.fecha)
    semanas = [[inicio + timedelta(days=7 * s + d) for d in range(7)] for s in range(SEMANAS)]
    conteo = dict(db.execute(select(Publicacion.estado, func.count()).group_by(Publicacion.estado)).all())
    campana_cargada = db.scalar(select(func.count()).where(Publicacion.tipo == "campana")) or 0
    return render(request, "admin/marketing_calendario.html", semanas=semanas, por_dia=por_dia, sin_fecha=sin_fecha,
                  primer_libre=_primer_dia_libre(db), en_stock=len(_piezas_para_semana(db, 99)),
                  dias_parrilla=DIAS_PARRILLA,
                  hoy=hoy, semana=semana, dias=DIAS, estados=ESTADOS_PUBLICACION, conteo=conteo, ok=ok,
                  campana_cargada=campana_cargada, total_campana=len(CAMPANA),
                  fb_listo=bool(config.FB_PAGE_ID and config.FB_PAGE_TOKEN))


@router.post("/proponer")
def proponer(yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    proponer_fechas(db)
    return _volver()


def _mover(pub: Publicacion, nueva: datetime) -> str:
    """Cambia la fecha de una por aprobar o programada. Devuelve el error o ''."""
    if pub.estado not in ("borrador", "programada"):
        return "Las publicaciones ya publicadas no se mueven."
    if nueva <= datetime.now():
        return "Esa fecha ya pasó: elige una más adelante."
    if pub.estado == "programada":
        pub.programada_para, pub.error = nueva, ""
    else:
        pub.propuesta_para = nueva
    return ""


@router.post("/{pid}/mover")
def mover(pid: int, dia: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """Arrastrar en el calendario: cambia el día y conserva la hora."""
    pub = o404(db.get(Publicacion, pid))
    try:
        d = datetime.strptime(dia, "%Y-%m-%d")
    except ValueError:
        return JSONResponse({"error": "Día inválido."}, 400)
    actual = pub.fecha or d.replace(hour=HORA_PROPUESTA)
    error = _mover(pub, d.replace(hour=actual.hour, minute=actual.minute))
    if error:
        return JSONResponse({"error": error}, 400)
    db.commit()
    f = pub.fecha
    return {"ok": True, "fecha": f.strftime("%Y-%m-%d %H:%M"), "hora": f.strftime("%H:%M")}


@router.post("/{pid}/fecha")
def fecha(pid: int, cuando: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """Desde el detalle: día y hora exactos de la propuesta (o de la programada)."""
    pub = o404(db.get(Publicacion, pid))
    try:
        error = _mover(pub, datetime.fromisoformat(cuando))
    except ValueError:
        error = "Elige día y hora."
    if error:
        return _volver(pid, error=error)
    db.commit()
    return _volver(pid, ok="fecha")


HORA_PRODUCTO, HORA_TEMA = 14, HORA_PROPUESTA
DIAS_PARRILLA = 3   # Ricardo prefiere revisar de 3 en 3 dias (nov 2026)


def _primer_dia_libre(db):
    ocupados = _dias_ocupados(db)
    dia = (datetime.now() + timedelta(days=1)).date()
    while dia in ocupados:
        dia += timedelta(days=1)
    return dia


def _piezas_para_semana(db, cuantas: int) -> list[Producto]:
    """En stock, primero las nunca publicadas ni propuestas; luego las que llevan mas tiempo sin salir."""
    ultima: dict[int, datetime] = {}
    for pub in db.scalars(select(Publicacion).where(Publicacion.tipo == "producto",
                                                    Publicacion.estado != "descartada")):
        fecha = pub.fecha or pub.creado
        for i in pub.ids_productos:
            if i not in ultima or fecha > ultima[i]:
                ultima[i] = fecha
    piezas = [p for p in db.scalars(select(Producto).options(selectinload(Producto.fotos))
                                    .where(Producto.visible.is_(True), Producto.vendido.is_(False)))
              if p.disponibles > 0 and p.fotos]
    piezas.sort(key=lambda p: (p.id in ultima, ultima.get(p.id, datetime.min), -p.id))
    return piezas[:cuantas]


@router.post("/parrilla")
async def parrilla(inicio: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """DIAS_PARRILLA dias desde `inicio`: a las 2 pm una pieza en stock y a las 8 pm un tema libre de la IA."""
    try:
        primero = datetime.strptime(inicio, "%Y-%m-%d").date()
    except ValueError:
        primero = _primer_dia_libre(db)
    if primero <= datetime.now().date():
        primero = (datetime.now() + timedelta(days=1)).date()
    dias = [primero + timedelta(days=i) for i in range(DIAS_PARRILLA)]
    hay_ia = bool(config.OPENAI_API_KEY)

    trabajos_productos = []
    piezas = _piezas_para_semana(db, DIAS_PARRILLA)
    for dia, p in zip(dias, piezas):
        texto, tags = _texto_plantilla([p])
        pub = Publicacion(tipo="producto", titulo=p.nombre[:120], productos=str(p.id), texto=texto, hashtags=tags,
                          imagen=marketing_img.producto(p), orden=-1, trabajando=hay_ia,
                          propuesta_para=datetime.combine(dia, datetime.min.time()).replace(hour=HORA_PRODUCTO))
        db.add(pub)
        db.flush()
        trabajos_productos.append((pub.id, [_datos_pieza(p)]))

    recientes = [t for (t,) in db.execute(select(Publicacion.titulo).where(Publicacion.tipo.in_(("concepto", "campana")))
                                           .order_by(Publicacion.id.desc()).limit(30))]
    conceptos = []
    for dia in dias:
        pub = Publicacion(tipo="concepto", titulo="Nueva idea: tema del día (la IA lo está planeando)",
                          trabajando=hay_ia, error_ia="" if hay_ia else "Falta la clave de OpenAI en el servidor.",
                          propuesta_para=datetime.combine(dia, datetime.min.time()).replace(hour=HORA_TEMA))
        db.add(pub)
        db.flush()
        conceptos.append(pub.id)
    db.commit()
    if hay_ia:
        marketing_ia.en_segundo_plano(marketing_ia.parrilla_sync, conceptos, dias, recientes, trabajos_productos)
    semana = (primero - (datetime.now().date() - timedelta(days=datetime.now().weekday()))).days // 7
    return _volver(ok=f"parrilla:{len(piezas)}", semana=max(semana, 0))


@router.post("/idea")
async def idea(idea: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """Una idea suelta del admin -> la IA arma la publicacion completa en segundo plano."""
    idea = idea.strip()[:1000]
    if not idea:
        return _volver()
    pub = Publicacion(tipo="concepto", titulo=f"Nueva idea: {idea}"[:120], indicacion=idea,
                      propuesta_para=siguiente_libre(db), trabajando=True)
    db.add(pub)
    db.commit()
    marketing_ia.en_segundo_plano(marketing_ia.retrabajar_sync, pub.id, idea)
    return _volver(pub.id, ok="trabajando")


@router.post("/{pid}/retrabajar")
async def retrabajar(pid: int, indicacion: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    if pub.trabajando or not _editable(pub):
        return _volver(pid)
    indicacion = indicacion.strip()[:1000]
    pub.indicacion, pub.trabajando, pub.error_ia = indicacion, True, ""
    db.commit()
    if pub.tipo == "producto":
        datos = [_datos_pieza(p) for p in _productos(db, pub.ids_productos)]
        marketing_ia.en_segundo_plano(marketing_ia.texto_con_indicacion_sync, pid, indicacion, datos)
    else:
        marketing_ia.en_segundo_plano(marketing_ia.retrabajar_sync, pid, indicacion)
    return _volver(pid, ok="trabajando")


@router.post("/campana")
def campana(yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    n = cargar_campana(db)
    return _volver(ok=f"campana:{n}")


@router.get("/nueva", response_class=HTMLResponse)
def nueva(request: Request, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    piezas = [p for p in db.scalars(select(Producto).options(selectinload(Producto.fotos))
                                    .where(Producto.visible.is_(True), Producto.vendido.is_(False))
                                    .order_by(Producto.creado.desc())) if p.disponibles > 0]
    publicadas = {}
    for pub in db.scalars(select(Publicacion).where(Publicacion.tipo == "producto",
                                                    Publicacion.estado.in_(("publicada", "programada")))):
        for i in pub.ids_productos:
            fecha = pub.publicada_en or pub.programada_para
            if fecha and (i not in publicadas or fecha > publicadas[i]):
                publicadas[i] = fecha
    return render(request, "admin/marketing_nueva.html", piezas=piezas, publicadas=publicadas,
                  max_piezas=MAX_PIEZAS, error="")


@router.post("/nueva")
async def crear(request: Request, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    form = await request.form()
    ids = [int(x) for x in form.getlist("pieza") if str(x).isdigit()][:MAX_PIEZAS]
    piezas = _productos(db, ids)
    if not piezas:
        return RedirectResponse("/admin/marketing/nueva", 303)
    titulo = (form.get("titulo") or "").strip()[:60] or "Lo nuevo en ReyBasar"
    imagen = marketing_img.producto(piezas[0]) if len(piezas) == 1 else marketing_img.varios(piezas, titulo)
    texto, tags = await texto_ia(piezas)
    nombre = piezas[0].nombre if len(piezas) == 1 else f"{titulo} ({len(piezas)} piezas)"
    pub = Publicacion(tipo="producto", titulo=nombre[:120], encabezado=titulo if len(piezas) > 1 else "",
                      productos=",".join(str(p.id) for p in piezas), texto=texto, hashtags=tags[:400],
                      imagen=imagen, orden=-1, propuesta_para=siguiente_libre(db))
    db.add(pub)
    db.commit()
    return _volver(pub.id, ok="creada")


@router.get("/{pid}", response_class=HTMLResponse)
def ver(request: Request, pid: int, ok: str = "", yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    sugerida = pub.propuesta_para
    if not sugerida or sugerida <= datetime.now():
        sugerida = datetime.now().replace(hour=HORA_PROPUESTA, minute=0, second=0, microsecond=0)
        if sugerida <= datetime.now() + timedelta(minutes=15):
            sugerida += timedelta(days=1)
    return render(request, "admin/marketing_ver.html", pub=pub, piezas=_productos(db, pub.ids_productos),
                  ok=ok, sugerida=sugerida, fb_listo=bool(config.FB_PAGE_ID and config.FB_PAGE_TOKEN))


def _editable(pub: Publicacion) -> bool:
    return pub.estado in ("borrador", "programada", "descartada")


@router.post("/{pid}/guardar")
def guardar(pid: int, texto: str = Form(""), hashtags: str = Form(""), yo: Usuario = Depends(solo_admin),
            db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    if _editable(pub):
        pub.texto, pub.hashtags = texto.strip()[:5000], " ".join(hashtags.split())[:400]
        db.commit()
    return _volver(pid, ok="guardada")


@router.post("/{pid}/texto")
async def rehacer_texto(pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    piezas = _productos(db, pub.ids_productos)
    if _editable(pub) and piezas:
        pub.texto, pub.hashtags = await texto_ia(piezas)
        db.commit()
    return _volver(pid, ok="texto")


@router.post("/{pid}/imagen")
def rehacer_imagen(pid: int, encabezado: str = Form(""), subtitulo: str = Form(""),
                   yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    if not _editable(pub):
        return _volver(pid)
    anterior = pub.imagen
    if pub.tipo == "campana":
        pub.encabezado, pub.subtitulo = encabezado.strip()[:160] or pub.encabezado, subtitulo.strip()[:200]
        pub.imagen = marketing_img.tarjeta(pub.encabezado, pub.subtitulo)
    else:
        piezas = _productos(db, pub.ids_productos)
        if not piezas:
            return _volver(pid)
        titulo = encabezado.strip()[:60] or pub.encabezado or "Lo nuevo en ReyBasar"
        pub.encabezado = titulo if len(piezas) > 1 else ""
        pub.imagen = marketing_img.producto(piezas[0]) if len(piezas) == 1 else marketing_img.varios(piezas, titulo)
    db.commit()
    marketing_img.borrar(anterior)
    return _volver(pid, ok="imagen")


@router.post("/{pid}/publicar")
async def publicar(pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    if pub.estado in ("borrador", "programada", "descartada") and not pub.trabajando:
        pub.aprobada_por = yo.primer_nombre
        await _publicar(db, pub)
    return _volver(pid, ok="publicada" if pub.estado == "publicada" else "")


@router.post("/{pid}/programar")
def programar(pid: int, cuando: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    try:
        fecha = datetime.fromisoformat(cuando)
    except ValueError:
        return _volver(pid, error="Elige día y hora.")
    if fecha <= datetime.now():
        return _volver(pid, error="Esa hora ya pasó: elige una más adelante.")
    if pub.estado in ("borrador", "programada", "descartada") and not pub.trabajando:
        pub.estado, pub.programada_para, pub.error, pub.aprobada_por = "programada", fecha, "", yo.primer_nombre
        db.commit()
    return _volver(pid, ok="programada")


@router.post("/{pid}/cancelar")
def cancelar(pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """Programada o descartada → vuelve a Por aprobar."""
    pub = o404(db.get(Publicacion, pid))
    if pub.estado in ("programada", "descartada"):
        if pub.estado == "programada" and pub.programada_para and pub.programada_para > datetime.now():
            pub.propuesta_para = pub.programada_para   # conserva el día que ya tenía
        pub.estado, pub.programada_para, pub.error = "borrador", None, ""
        db.commit()
    return _volver(pid)


@router.post("/{pid}/descartar")
def descartar(pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    pub = o404(db.get(Publicacion, pid))
    if pub.estado in ("borrador", "programada"):
        pub.estado, pub.programada_para = "descartada", None
        db.commit()
    return _volver()
