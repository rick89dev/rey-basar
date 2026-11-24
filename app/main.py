"""ReyBasar — catálogo de ropa y juguetes nuevos y usados."""
import secrets
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import catalogo, config
from .auth import usuario_actual
from .config import CATEGORIA_NOMBRE, CATEGORIAS, MEDIA_DIR
from .db import Foto, Producto, SessionLocal, init_db
from .web import APP_DIR, get_db, o404, render, templates

app = FastAPI(title="ReyBasar", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, max_age=60 * 60 * 24 * 30,
                   same_site="lax", https_only=config.SECRET_KEY != "cambia-esto-en-produccion")
app.add_middleware(GZipMiddleware, minimum_size=800)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
_o404 = o404


@app.on_event("startup")
def _startup():
    init_db()
    with SessionLocal() as db:
        catalogo.sincronizar(db)
    if config.DEMO:
        from .demo import cargar
        cargar()


# ---------------------------------------------------------------- tienda
BANNERS = [
    {"img": "inicio", "url": "/nuevos", "alt": "Piezas únicas a precio de rey: ropa y juguetes nuevos y seminuevos"},
    {"img": "familia", "url": "/categoria/ropa", "alt": "Dama, caballero, niños y juguetes"},
    {"img": "envio", "url": "/preguntas-frecuentes#envios", "alt": "Entregas en Cuernavaca: acordamos contigo el punto"},
]


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(APP_DIR / "static" / "img" / "favicon.ico")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return JSONResponse({
        "name": "ReyBasar", "short_name": "ReyBasar", "start_url": "/", "display": "standalone",
        "background_color": "#000000", "theme_color": "#000000",
        "icons": [{"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png"}],
    }, media_type="application/manifest+json")
@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, db=Depends(get_db)):
    destacados = catalogo.listar(db, destacados=True, limite=12)
    nuevos = catalogo.listar(db, limite=12)
    hero = (destacados or nuevos)[:7]
    return render(request, "inicio.html", hero=hero, banners=BANNERS, hay_productos=bool(nuevos),
                  destacados=destacados[:6] or nuevos[:6],
                  descuentos=catalogo.listar(db, descuentos=True, limite=5),
                  nuevos=catalogo.listar(db, condicion="nuevo", limite=6),
                  usados=catalogo.listar(db, condicion="usado", limite=6))


@app.get("/categoria/{clave}", response_class=HTMLResponse)
@app.get("/categoria/{clave}/{sub}", response_class=HTMLResponse)
def categoria(request: Request, clave: str, sub: str = "", condicion: str = "", orden: str = "nuevos",
              db=Depends(get_db)):
    from .config import CATEGORIAS_ANTERIORES, SUBCATEGORIAS
    if clave in CATEGORIAS_ANTERIORES:   # enlaces viejos: /categoria/dama → /categoria/ropa/dama
        return RedirectResponse(f"/categoria/{CATEGORIAS_ANTERIORES[clave]}/{clave}", 301)
    if clave not in CATEGORIA_NOMBRE:
        raise HTTPException(404)
    subs = SUBCATEGORIAS.get(clave, [])
    if sub and sub not in dict(subs):
        raise HTTPException(404)
    productos = catalogo.listar(db, categoria=clave, subcategoria=sub or None, condicion=condicion or None,
                                orden=orden)
    titulo = CATEGORIA_NOMBRE[clave] + (f" · {dict(subs)[sub]}" if sub else "")
    return render(request, "listado.html", titulo=titulo, clave=clave, sub=sub, subs=subs,
                  productos=productos, condicion=condicion, orden=orden)


@app.get("/nuevos", response_class=HTMLResponse)
@app.get("/usados", response_class=HTMLResponse)
def por_condicion(request: Request, orden: str = "nuevos", db=Depends(get_db)):
    cond = "nuevo" if request.url.path == "/nuevos" else "usado"
    return render(request, "listado.html", titulo="Nuevos" if cond == "nuevo" else "Seminuevos",
                  clave="", productos=catalogo.listar(db, condicion=cond, orden=orden),
                  condicion=cond, orden=orden)


@app.get("/descuentos", response_class=HTMLResponse)
def descuentos(request: Request, db=Depends(get_db)):
    return render(request, "listado.html", titulo="Descuentos", clave="",
                  productos=catalogo.listar(db, descuentos=True), condicion="", orden="nuevos")


@app.get("/buscar", response_class=HTMLResponse)
def buscar(request: Request, q: str = "", db=Depends(get_db)):
    productos = catalogo.listar(db, texto=q) if q.strip() else []
    return render(request, "listado.html", titulo=f"Resultados para “{q}”", clave="",
                  productos=productos, condicion="", orden="nuevos", q=q)


@app.get("/producto/{slug}", response_class=HTMLResponse)
def producto(request: Request, slug: str, db=Depends(get_db)):
    p = catalogo.por_slug(db, slug)
    if not p or not p.visible:
        raise HTTPException(404)
    relacionados = [x for x in catalogo.listar(db, categoria=p.categoria, limite=7) if x.id != p.id][:6]
    return render(request, "producto.html", p=p, relacionados=relacionados)


@app.get("/carrito", response_class=HTMLResponse)
def carrito(request: Request):
    return render(request, "carrito.html")


@app.get("/quiero-vender", response_class=HTMLResponse)
def quiero_vender(request: Request):
    return render(request, "vender.html")


@app.get("/aviso-de-privacidad", response_class=HTMLResponse)
def aviso_privacidad(request: Request):
    return render(request, "legal/privacidad.html")


@app.get("/terminos-y-condiciones", response_class=HTMLResponse)
def terminos(request: Request):
    return render(request, "legal/terminos.html")


@app.get("/preguntas-frecuentes", response_class=HTMLResponse)
def faq(request: Request):
    return render(request, "faq.html")


@app.exception_handler(404)
async def no_encontrado(request: Request, exc):
    return render(request, "404.html", status_code=404)


# ---------------------------------------------------------------- admin
def admin_requerido(request: Request, db=Depends(get_db)):
    u = usuario_actual(request, db)
    if not u:
        raise HTTPException(303, headers={"Location": "/cuenta/entrar?siguiente=/admin"})
    if not u.es_admin:
        raise HTTPException(403, "Solo administradores")
    return u


@app.get("/admin/entrar")
def entrar_viejo():
    return RedirectResponse("/cuenta/entrar?siguiente=/admin", 303)


@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(admin_requerido)])
def admin_resumen(request: Request, db=Depends(get_db)):
    """Inicio del admin: resumen de cuentas."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from .db import Pedido
    fin = catalogo.resumen_finanzas(db)
    por_atender = list(db.scalars(select(Pedido).options(selectinload(Pedido.items))
                                  .where(Pedido.estado.in_(("nuevo", "confirmado"))).order_by(Pedido.id)))
    from datetime import datetime
    from .db import CATEGORIAS_GASTO
    return render(request, "admin/resumen.html", fin=fin, ventas=catalogo.ultimas_ventas(db, 15),
                  por_atender=por_atender, cats=CATEGORIAS_GASTO, hoy=datetime.now().strftime("%Y-%m-%d"))


@app.get("/admin/productos", response_class=HTMLResponse, dependencies=[Depends(admin_requerido)])
def admin_lista(request: Request, q: str = "", estado: str = "", db=Depends(get_db)):
    productos = catalogo.todos_admin(db, q, estado)
    fin = catalogo.resumen_finanzas(db)
    return render(request, "admin/lista.html", productos=productos, q=q, estado=estado, fin=fin)


def _entero(v, minimo: int | None = None) -> int | None:
    v = str(v or "").strip().replace("$", "").replace(",", "")
    if not v:
        return None
    n = int(float(v))
    return max(n, minimo) if minimo is not None else n


def _campos(nombre, categoria, condicion, talla, marca, descripcion, precio, precio_antes, costo,
            piezas, origen, vendedor, destacado, visible, subcategoria="") -> dict:
    categoria, subcategoria = catalogo.normalizar_categoria(categoria, subcategoria)
    return dict(nombre=nombre.strip(), categoria=categoria,
                subcategoria=catalogo.subcategoria_valida(categoria, subcategoria),
                condicion=condicion, talla=talla.strip(),
                marca=marca.strip(), descripcion=descripcion.strip(), precio=_entero(precio, 0) or 0,
                precio_antes=_entero(precio_antes, 0), costo=_entero(costo, 0), piezas=_entero(piezas, 1) or 1,
                origen=origen, vendedor=vendedor.strip(), destacado=bool(destacado), visible=bool(visible))


FORM = dict(nombre=Form(...), categoria=Form(...), condicion=Form("usado"), talla=Form(""),
            marca=Form(""), descripcion=Form(""), precio=Form(...), precio_antes=Form(""),
            costo=Form(""), piezas=Form("1"), origen=Form("propio"), vendedor=Form(""), destacado=Form(""),
            visible=Form(""), subcategoria=Form(""))


@app.get("/admin/nuevo", response_class=HTMLResponse, dependencies=[Depends(admin_requerido)])
def admin_nuevo(request: Request):
    return render(request, "admin/editar.html", p=None, ventas=[])


@app.post("/admin/nuevo", dependencies=[Depends(admin_requerido)])
async def admin_crear(request: Request, db=Depends(get_db), fotos: list[UploadFile] = File(default=[]),
                      nombre: str = FORM["nombre"], categoria: str = FORM["categoria"],
                      condicion: str = FORM["condicion"], talla: str = FORM["talla"],
                      marca: str = FORM["marca"], descripcion: str = FORM["descripcion"],
                      precio: str = FORM["precio"], precio_antes: str = FORM["precio_antes"],
                      costo: str = FORM["costo"], piezas: str = FORM["piezas"], origen: str = FORM["origen"],
                      vendedor: str = FORM["vendedor"], destacado: str = FORM["destacado"],
                      visible: str = FORM["visible"], subcategoria: str = FORM["subcategoria"]):
    campos = _campos(nombre, categoria, condicion, talla, marca, descripcion, precio, precio_antes,
                     costo, piezas, origen, vendedor, destacado, visible, subcategoria)
    datos = [await f.read() for f in fotos if f.filename]
    p = catalogo.crear(db, fotos=datos, creado_por="admin", **campos)
    return RedirectResponse(f"/admin/producto/{p.id}?ok=1", 303)


@app.get("/admin/producto/{pid}", response_class=HTMLResponse, dependencies=[Depends(admin_requerido)])
def admin_editar(request: Request, pid: int, ok: str = "", error: str = "", db=Depends(get_db)):
    p = _o404(db.get(Producto, pid))
    return render(request, "admin/editar.html", p=p, ok=ok, error=error, ventas=catalogo.ventas_de(db, pid))


@app.post("/admin/producto/{pid}", dependencies=[Depends(admin_requerido)])
async def admin_guardar(request: Request, pid: int, db=Depends(get_db),
                        fotos: list[UploadFile] = File(default=[]),
                        nombre: str = FORM["nombre"], categoria: str = FORM["categoria"],
                        condicion: str = FORM["condicion"], talla: str = FORM["talla"],
                        marca: str = FORM["marca"], descripcion: str = FORM["descripcion"],
                        precio: str = FORM["precio"], precio_antes: str = FORM["precio_antes"],
                        costo: str = FORM["costo"], piezas: str = FORM["piezas"], origen: str = FORM["origen"],
                        vendedor: str = FORM["vendedor"], destacado: str = FORM["destacado"],
                        visible: str = FORM["visible"], subcategoria: str = FORM["subcategoria"]):
    p = _o404(db.get(Producto, pid))
    campos = _campos(nombre, categoria, condicion, talla, marca, descripcion, precio, precio_antes,
                     costo, piezas, origen, vendedor, destacado, visible, subcategoria)
    comprometidas = (p.vendidas or 0) + (p.apartadas or 0)
    if campos["piezas"] < comprometidas:
        return RedirectResponse(f"/admin/producto/{pid}?error=" + quote(
            f"No puedes dejar {campos['piezas']} piezas: ya hay {comprometidas} vendidas o apartadas."), 303)
    catalogo.actualizar(db, p, **campos)
    catalogo.recalcular(db, p)
    db.commit()
    datos = [await f.read() for f in fotos if f.filename]
    if datos:
        catalogo.agregar_fotos(db, p, datos)
        db.commit()
    return RedirectResponse(f"/admin/producto/{p.id}?ok=1", 303)


@app.post("/admin/ia/ficha", dependencies=[Depends(admin_requerido)])
async def admin_ia_ficha(fotos: list[UploadFile] = File(default=[]), texto: str = Form("")):
    """Llena la ficha con IA a partir de las fotos seleccionadas y lo que escribió el admin."""
    from . import ia
    datos = [await f.read() for f in fotos if f.filename][:6]
    if not datos:
        return JSONResponse({"error": "Selecciona al menos una foto."}, 400)
    try:
        return await ia.llenar_ficha(datos, texto)
    except ia.SinClave as e:
        return JSONResponse({"error": str(e)}, 503)
    except Exception as e:  # red, cuota, respuesta inválida
        return JSONResponse({"error": f"La IA no respondió ({type(e).__name__}). Llena los campos a mano o intenta de nuevo."}, 502)


@app.post("/admin/foto/{fid}/principal", dependencies=[Depends(admin_requerido)])
def admin_foto_principal(fid: int, db=Depends(get_db)):
    f = _o404(db.get(Foto, fid))
    catalogo.hacer_principal(db, f.producto, fid)
    return RedirectResponse(f"/admin/producto/{f.producto_id}", 303)


@app.post("/admin/foto/{fid}/quitar", dependencies=[Depends(admin_requerido)])
def admin_foto_quitar(fid: int, db=Depends(get_db)):
    f = _o404(db.get(Foto, fid))
    pid = f.producto_id
    catalogo.quitar_foto(db, f)
    return RedirectResponse(f"/admin/producto/{pid}", 303)


@app.post("/admin/producto/{pid}/eliminar", dependencies=[Depends(admin_requerido)])
def admin_eliminar(pid: int, db=Depends(get_db)):
    p = _o404(db.get(Producto, pid))
    if catalogo.tiene_ventas(db, p) or p.apartadas:
        return RedirectResponse(f"/admin/producto/{pid}?error=" + quote(
            "Este producto tiene ventas o pedidos: si lo borras se descuadran tus cuentas. "
            "Mejor desmarca “Visible en la tienda”."), 303)
    catalogo.eliminar(db, p)
    return RedirectResponse("/admin/productos", 303)


@app.post("/admin/producto/{pid}/venta", dependencies=[Depends(admin_requerido)])
def admin_registrar_venta(pid: int, cantidad: str = Form("1"), precio: str = Form(""), nota: str = Form(""),
                          volver: str = Form(""), db=Depends(get_db)):
    p = _o404(db.get(Producto, pid))
    cant = _entero(cantidad, 1) or 1
    destino = {"lista": "/admin/productos", "resumen": "/admin"}.get(volver, f"/admin/producto/{pid}")
    if cant > p.disponibles:
        sep = "&" if "?" in destino else "?"
        return RedirectResponse(destino + f"{sep}error=" + quote(
            f"Solo hay {p.disponibles} pieza(s) disponible(s) de {p.sku}."), 303)
    precio_u = _entero(precio, 0)
    catalogo.registrar_venta(db, p, cant, p.precio if precio_u is None else precio_u, canal="tienda", nota=nota)
    db.commit()
    return RedirectResponse(destino + ("" if volver in ("lista", "resumen") else "?ok=venta") + "#ventas", 303)


@app.post("/admin/venta/{vid}/devolucion", dependencies=[Depends(admin_requerido)])
def admin_devolucion(vid: int, cantidad: str = Form("1"), monto: str = Form(""), nota: str = Form(""),
                     volver: str = Form(""), db=Depends(get_db)):
    """Devolución: el cliente regresa piezas; tú le regresas dinero. Las piezas vuelven al inventario."""
    from .db import Venta
    v = _o404(db.get(Venta, vid))
    destino = "/admin" if volver == "resumen" else f"/admin/producto/{v.producto_id}"
    cant = _entero(cantidad, 1) or 1
    monto_pieza = _entero(monto, 0)
    try:
        catalogo.registrar_devolucion(db, v, cant, v.precio_unitario if monto_pieza is None else monto_pieza,
                                      nota=nota or "Devolución")
    except ValueError as e:
        sep = "&" if "?" in destino else "?"
        return RedirectResponse(destino + f"{sep}error=" + quote(str(e)), 303)
    db.commit()
    return RedirectResponse(destino + ("?ok=devolucion" if volver != "resumen" else "?ok=devolucion") + "#ventas", 303)


@app.post("/admin/venta/{vid}/borrar", dependencies=[Depends(admin_requerido)])
def admin_borrar_venta(vid: int, volver: str = Form(""), db=Depends(get_db)):
    """Deshacer: para ventas capturadas por error (no es una devolución)."""
    from .db import Venta
    v = _o404(db.get(Venta, vid))
    pid = v.producto_id
    if v.pedido_id and not v.es_devolucion:
        return RedirectResponse(f"/admin/producto/{pid}?error=" + quote(
            "Esta venta viene de un pedido web: si fue un error cancela el pedido; si el cliente regresó la pieza, usa Devolución."), 303)
    catalogo.borrar_venta(db, v)
    db.commit()
    if volver == "resumen":
        return RedirectResponse("/admin", 303)
    return RedirectResponse(f"/admin/producto/{pid}#ventas" if pid else "/admin", 303)


# ---------------------------------------------------------------- API (bot de WhatsApp)
def bot_requerido(authorization: str = Header("")):
    if not config.BOT_TOKEN or not secrets.compare_digest(authorization, f"Bearer {config.BOT_TOKEN}"):
        raise HTTPException(401, "Token inválido")


def _json(p: Producto) -> dict:
    return {"id": p.id, "sku": p.sku, "nombre": p.nombre, "slug": p.slug, "precio": p.precio,
            "categoria": p.categoria, "subcategoria": p.subcategoria, "condicion": p.condicion, "talla": p.talla, "marca": p.marca,
            "visible": p.visible, "vendido": p.vendido, "apartado": p.apartado,
            "piezas": p.piezas, "disponibles": p.disponibles, "costo": p.costo, "fotos": [f.url for f in p.fotos]}


@app.post("/api/productos", dependencies=[Depends(bot_requerido)])
async def api_crear(nombre: str = Form(...), categoria: str = Form(...), precio: int = Form(...),
                    condicion: str = Form("usado"), talla: str = Form(""), descripcion: str = Form(""),
                    marca: str = Form(""), origen: str = Form("propio"), costo: int | None = Form(None),
                    autor: str = Form(""), nota: str = Form(""), piezas: int = Form(1),
                    subcategoria: str = Form(""),
                    fotos: list[UploadFile] = File(default=[]), db=Depends(get_db)):
    categoria, subcategoria = catalogo.normalizar_categoria(categoria, subcategoria)
    if categoria not in CATEGORIA_NOMBRE:
        categoria = "otros"
    if condicion not in ("nuevo", "usado"):
        condicion = "usado"
    datos = [await f.read() for f in fotos]
    p = catalogo.crear(db, nombre=nombre, categoria=categoria, precio=precio, condicion=condicion,
                       talla=talla.strip(), marca=marca.strip(), descripcion=descripcion, origen=origen,
                       costo=costo, piezas=max(piezas, 1), subcategoria=subcategoria,
                       creado_por=autor.strip() or "WhatsApp", fotos=datos)
    return JSONResponse(_json(p), 201)


@app.get("/api/productos", dependencies=[Depends(bot_requerido)])
def api_listar(q: str = "", db=Depends(get_db)):
    return [_json(p) for p in catalogo.todos_admin(db, q)[:50]]


@app.post("/api/productos/{pid}/estado", dependencies=[Depends(bot_requerido)])
def api_estado(pid: int, visible: bool | None = Form(None), db=Depends(get_db)):
    p = _o404(db.get(Producto, pid))
    if visible is not None:
        catalogo.actualizar(db, p, visible=visible)
    return _json(p)


from .cuenta import router as router_cuenta  # noqa: E402
from .admin_extra import router as router_admin_extra  # noqa: E402
from .contratos import router as router_contratos  # noqa: E402

app.include_router(router_cuenta)
app.include_router(router_admin_extra)
app.include_router(router_contratos)
