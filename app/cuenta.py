"""Cuentas de clientes y administradores (un solo login), y pedidos."""
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import catalogo, config
from .auth import hashear, rol_inicial, usuario_actual, verificar
from .db import Pedido, PedidoItem, Producto, Usuario
from .web import get_db, o404, pesos, render

router = APIRouter()
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def _siguiente(valor: str) -> str:
    """Solo rutas internas, para no redirigir a otro sitio."""
    return valor if valor.startswith("/") and not valor.startswith("//") else "/cuenta"


def _telefono(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")[-10:]


def requiere_usuario(request: Request, db=Depends(get_db)) -> Usuario:
    u = usuario_actual(request, db)
    if not u:
        raise HTTPException(303, headers={"Location": f"/cuenta/entrar?siguiente={quote(request.url.path)}"})
    return u


# ---------------------------------------------------------------- entrar / registro
@router.get("/cuenta/entrar", response_class=HTMLResponse)
def entrar_form(request: Request, siguiente: str = "/cuenta", db=Depends(get_db)):
    if usuario_actual(request, db):
        return RedirectResponse(_siguiente(siguiente), 303)
    return render(request, "cuenta/entrar.html", siguiente=siguiente, error="", email="")


@router.post("/cuenta/entrar")
def entrar(request: Request, email: str = Form(...), clave: str = Form(...),
           siguiente: str = Form("/cuenta"), db=Depends(get_db)):
    email = email.strip().lower()
    u = db.scalar(select(Usuario).where(Usuario.email == email))
    if not u or not u.activo or not verificar(clave, u.password):
        return render(request, "cuenta/entrar.html", siguiente=siguiente, email=email,
                      error="Correo o contraseña incorrectos.", status_code=400)
    request.session["uid"] = u.id
    destino = _siguiente(siguiente)
    if destino == "/cuenta" and u.es_admin:
        destino = "/admin"
    return RedirectResponse(destino, 303)


@router.get("/cuenta/registro", response_class=HTMLResponse)
def registro_form(request: Request, siguiente: str = "/cuenta"):
    return render(request, "cuenta/registro.html", siguiente=siguiente, error="", datos={})


@router.post("/cuenta/registro")
def registro(request: Request, nombre: str = Form(...), email: str = Form(...), telefono: str = Form(...),
             clave: str = Form(...), clave2: str = Form(...), siguiente: str = Form("/cuenta"),
             acepto: str = Form(""), db=Depends(get_db)):
    email = email.strip().lower()
    datos = {"nombre": nombre, "email": email, "telefono": telefono}
    error = ""
    if len(nombre.strip()) < 3:
        error = "Escribe tu nombre."
    elif not EMAIL.match(email):
        error = "El correo no es válido."
    elif len(_telefono(telefono)) != 10:
        error = "El teléfono debe tener 10 dígitos."
    elif len(clave) < 8:
        error = "La contraseña debe tener al menos 8 caracteres."
    elif clave != clave2:
        error = "Las contraseñas no coinciden."
    elif not acepto:
        error = "Para crear tu cuenta acepta el Aviso de privacidad y los Términos y condiciones."
    elif db.scalar(select(Usuario.id).where(Usuario.email == email)):
        error = "Ya hay una cuenta con ese correo. Inicia sesión."
    if error:
        return render(request, "cuenta/registro.html", siguiente=siguiente, error=error, datos=datos,
                      status_code=400)
    u = Usuario(nombre=nombre.strip(), email=email, telefono=_telefono(telefono), password=hashear(clave),
                rol=rol_inicial(db, email))
    db.add(u)
    db.commit()
    request.session["uid"] = u.id
    destino = _siguiente(siguiente)
    if destino == "/cuenta" and u.es_admin:
        destino = "/admin?bienvenida=1"
    return RedirectResponse(destino, 303)


@router.get("/cuenta/salir")
def salir(request: Request):
    request.session.clear()
    return RedirectResponse("/", 303)


# ---------------------------------------------------------------- mi cuenta
@router.get("/cuenta", response_class=HTMLResponse)
def mi_cuenta(request: Request, ok: int = 0, u: Usuario = Depends(requiere_usuario), db=Depends(get_db)):
    pedidos = list(db.scalars(select(Pedido).options(selectinload(Pedido.items))
                              .where(Pedido.usuario_id == u.id).order_by(Pedido.id.desc())))
    return render(request, "cuenta/mi_cuenta.html", u=u, pedidos=pedidos, ok=ok)


@router.post("/cuenta")
def guardar_cuenta(request: Request, nombre: str = Form(...), telefono: str = Form(""),
                   direccion: str = Form(""), referencias: str = Form(""),
                   u: Usuario = Depends(requiere_usuario), db=Depends(get_db)):
    u = db.merge(u)
    u.nombre = nombre.strip() or u.nombre
    u.telefono = _telefono(telefono) or u.telefono
    u.direccion = direccion.strip()[:250]
    u.referencias = referencias.strip()[:250]
    db.commit()
    return RedirectResponse("/cuenta?ok=1", 303)


@router.get("/cuenta/pedidos/{pid}", response_class=HTMLResponse)
def ver_pedido(request: Request, pid: int, nuevo: int = 0, u: Usuario = Depends(requiere_usuario),
               db=Depends(get_db)):
    p = o404(db.get(Pedido, pid))
    if p.usuario_id != u.id and not u.es_admin:
        raise HTTPException(404)
    return render(request, "cuenta/pedido.html", p=p, nuevo=nuevo, wa=mensaje_whatsapp(p))


def costo_entrega(subtotal: int) -> int:
    if config.ENTREGA_GRATIS_DESDE and subtotal >= config.ENTREGA_GRATIS_DESDE:
        return 0
    return config.ENTREGA_COSTO


def mensaje_whatsapp(p: Pedido) -> str:
    lineas = "\n".join(f"• {i.cantidad} × {i.nombre} ({i.sku}) {pesos(i.precio)}" if i.cantidad > 1
                       else f"• {i.nombre} ({i.sku}) {pesos(i.precio)}" for i in p.items)
    envio = pesos(p.envio) if p.envio else ("Gratis" if config.ENTREGA_COSTO else "por acordar")
    txt = (f"Hola ReyBasar, hice el pedido *{p.folio}*:\n{lineas}\n\n"
           f"Total: {pesos(p.total)} (entrega {envio})\n"
           f"Entrega en {p.municipio}" + (f", punto preferido: {p.direccion}" if p.direccion else ": acordamos el punto")
           + f"\nNombre: {p.nombre} · Tel. {p.telefono}")
    return f"https://wa.me/{config.WHATSAPP}?text={quote(txt)}"


# ---------------------------------------------------------------- API carrito / pedidos
@router.get("/api/disponibles")
def disponibles(ids: str = "", db=Depends(get_db)):
    """Piezas disponibles de cada producto del carrito (0 = ya no hay)."""
    lista = [int(x) for x in ids.split(",") if x.strip().isdigit()][:50]
    if not lista:
        return {"disponibles": {}, "no_disponibles": []}
    ps = {p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(lista))).all()}
    disp = {str(i): (ps[i].disponibles if i in ps and ps[i].visible else 0) for i in lista}
    return {"disponibles": disp, "no_disponibles": [i for i in lista if disp[str(i)] == 0]}


class ItemIn(BaseModel):
    id: int
    cantidad: int = 1


class PedidoIn(BaseModel):
    items: list[ItemIn] = []
    ids: list[int] = []   # compatibilidad: carrito viejo (1 pieza por producto)
    nombre: str
    telefono: str
    municipio: str = ""
    direccion: str = ""
    referencias: str = ""
    notas: str = ""
    guardar_direccion: bool = True


@router.post("/api/pedidos")
def crear_pedido(datos: PedidoIn, request: Request, db=Depends(get_db)):
    u = usuario_actual(request, db)
    if not u:
        return JSONResponse({"error": "Inicia sesión para hacer tu pedido.", "login": True}, 401)
    pedidas: dict[int, int] = {}
    for it in (datos.items or [ItemIn(id=i) for i in datos.ids])[:30]:
        if it.cantidad > 0:
            pedidas[it.id] = pedidas.get(it.id, 0) + min(it.cantidad, 99)
    if not pedidas:
        return JSONResponse({"error": "Tu carrito está vacío."}, 400)
    tel = _telefono(datos.telefono)
    if len(datos.nombre.strip()) < 3 or len(tel) != 10:
        return JSONResponse({"error": "Revisa tu nombre y tu WhatsApp (10 dígitos)."}, 400)

    productos = {p.id: p for p in db.scalars(select(Producto).options(selectinload(Producto.fotos))
                                              .where(Producto.id.in_(list(pedidas)))).all()}
    faltan = {}
    for pid, cant in pedidas.items():
        p = productos.get(pid)
        disp = p.disponibles if p and p.visible else 0
        if disp < cant:
            faltan[str(pid)] = disp
    if faltan:
        return JSONResponse({"error": "Algunas piezas ya no están disponibles en esa cantidad; ajustamos tu carrito.",
                             "disponibles": faltan, "no_disponibles": [int(k) for k, v in faltan.items() if v == 0]}, 409)
    validos = [productos[pid] for pid in pedidas]
    subtotal = sum(p.precio * pedidas[p.id] for p in validos)
    envio = costo_entrega(subtotal)
    pedido = Pedido(usuario_id=u.id, nombre=datos.nombre.strip()[:120], telefono=tel,
                    municipio=config.ENTREGA_CIUDAD, direccion=datos.direccion.strip()[:250],
                    referencias=datos.referencias.strip()[:250], notas=datos.notas.strip()[:1000],
                    subtotal=subtotal, envio=envio, total=subtotal + envio)
    for p in validos:
        pedido.items.append(PedidoItem(producto_id=p.id, nombre=p.nombre, sku=p.sku, precio=p.precio,
                                       foto=p.foto or "", talla=p.talla, cantidad=pedidas[p.id]))
    db.add(pedido)
    db.flush()
    for p in validos:
        catalogo.recalcular(db, p)
    if datos.guardar_direccion:
        if pedido.direccion:
            u.direccion = pedido.direccion
        if not u.telefono:
            u.telefono = tel
    db.commit()
    return {"id": pedido.id, "folio": pedido.folio, "url": f"/cuenta/pedidos/{pedido.id}?nuevo=1",
            "whatsapp": mensaje_whatsapp(pedido)}
