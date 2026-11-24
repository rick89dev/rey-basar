"""Admin: pedidos y usuarios."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from .auth import usuario_actual
from . import catalogo
from datetime import datetime

from .db import CATEGORIAS_GASTO, ESTADOS_PEDIDO, METODOS_PAGO, Gasto, Pedido, Usuario, Venta
from .web import get_db, o404, render

router = APIRouter(prefix="/admin")


def solo_admin(request: Request, db=Depends(get_db)) -> Usuario:
    u = usuario_actual(request, db)
    if not u:
        raise HTTPException(303, headers={"Location": "/cuenta/entrar?siguiente=/admin"})
    if not u.es_admin:
        raise HTTPException(403, "Solo administradores")
    return u


# ---------------------------------------------------------------- pedidos
@router.get("/pedidos", response_class=HTMLResponse)
def pedidos(request: Request, estado: str = "", yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    q = select(Pedido).options(selectinload(Pedido.items)).order_by(Pedido.id.desc())
    if estado == "por_cobrar":
        q = q.where(Pedido.pagado.is_(False), Pedido.estado.in_(("confirmado", "entregado")))
    elif estado:
        q = q.where(Pedido.estado == estado)
    conteo = dict(db.execute(select(Pedido.estado, func.count()).group_by(Pedido.estado)).all())
    conteo["por_cobrar"] = db.scalar(select(func.count()).select_from(Pedido).where(
        Pedido.pagado.is_(False), Pedido.estado.in_(("confirmado", "entregado"))))
    return render(request, "admin/pedidos.html", pedidos=list(db.scalars(q)), estado=estado,
                  estados=ESTADOS_PEDIDO, conteo=conteo)


@router.get("/pedidos/{pid}", response_class=HTMLResponse)
def pedido(request: Request, pid: int, error: str = "", yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    from .cuenta import mensaje_whatsapp
    p = o404(db.get(Pedido, pid))
    tel = f"52{p.telefono}" if len(p.telefono) == 10 else p.telefono
    return render(request, "admin/pedido.html", p=p, estados=ESTADOS_PEDIDO, wa_cliente=f"https://wa.me/{tel}",
                  metodos=METODOS_PAGO, hoy=datetime.now().strftime("%Y-%m-%d"),
                  error="Ya no hay piezas suficientes para reactivar este pedido." if error == "sin_piezas" else "")


@router.post("/pedidos/{pid}/estado")
def cambiar_estado(pid: int, estado: str = Form(...), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """
    Nuevo / Confirmado: las piezas quedan apartadas.
    Entregado: se registran las ventas (cuentan en tu resumen de inversión).
    Cancelado: se liberan las piezas (y se deshacen las ventas si ya estaba entregado).
    """
    p = o404(db.get(Pedido, pid))
    if estado not in dict(ESTADOS_PEDIDO):
        raise HTTPException(400)
    if p.estado == "cancelado" and estado != "cancelado":
        # reactivar un pedido cancelado: sus piezas pudieron venderse mientras tanto
        for item in p.items:
            if item.producto and item.producto.disponibles < item.cantidad:
                return RedirectResponse(f"/admin/pedidos/{pid}?error=sin_piezas", 303)
    p.estado = estado
    db.flush()
    for v in db.scalars(select(Venta).where(Venta.pedido_id == p.id)).all():
        db.delete(v)
    db.flush()
    for item in p.items:
        if item.producto and estado == "entregado":
            catalogo.registrar_venta(db, item.producto, item.cantidad, item.precio, canal="web", pedido_id=p.id)
        elif item.producto:
            catalogo.recalcular(db, item.producto)
    db.commit()
    return RedirectResponse(f"/admin/pedidos/{pid}", 303)


@router.post("/pedidos/{pid}/pago")
def registrar_pago(pid: int, metodo: str = Form("efectivo"), monto: str = Form(""), fecha: str = Form(""),
                   nota: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    p = o404(db.get(Pedido, pid))
    try:
        cantidad = _monto(monto) if monto.strip() else p.total
    except ValueError:
        cantidad = p.total
    p.pagado = True
    p.metodo_pago = metodo if metodo in dict(METODOS_PAGO) else "otro"
    p.monto_pagado = cantidad
    p.fecha_pago = _fecha(fecha)
    p.nota_pago = nota.strip()[:250]
    db.commit()
    return RedirectResponse(f"/admin/pedidos/{pid}?ok=pago", 303)


@router.post("/pedidos/{pid}/pago/deshacer")
def deshacer_pago(pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    p = o404(db.get(Pedido, pid))
    p.pagado, p.metodo_pago, p.monto_pagado, p.fecha_pago, p.nota_pago = False, "", 0, None, ""
    db.commit()
    return RedirectResponse(f"/admin/pedidos/{pid}", 303)


# ---------------------------------------------------------------- usuarios
@router.get("/usuarios", response_class=HTMLResponse)
def usuarios(request: Request, q: str = "", yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    consulta = select(Usuario).order_by(Usuario.rol, Usuario.id.desc())
    if q:
        like = f"%{q}%"
        consulta = consulta.where(or_(Usuario.nombre.ilike(like), Usuario.email.ilike(like),
                                      Usuario.telefono.ilike(like)))
    pedidos_por = dict(db.execute(select(Pedido.usuario_id, func.count()).group_by(Pedido.usuario_id)).all())
    return render(request, "admin/usuarios.html", usuarios=list(db.scalars(consulta)), q=q, yo=yo,
                  pedidos_por=pedidos_por)


@router.post("/usuarios/{uid}/rol")
def cambiar_rol(uid: int, rol: str = Form(...), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    u = o404(db.get(Usuario, uid))
    if rol not in ("cliente", "admin"):
        raise HTTPException(400)
    if u.id == yo.id and rol != "admin":
        raise HTTPException(400, "No puedes quitarte el rol de administrador a ti mismo.")
    u.rol = rol
    db.commit()
    return RedirectResponse("/admin/usuarios", 303)


@router.post("/usuarios/{uid}/activo")
def cambiar_activo(uid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    u = o404(db.get(Usuario, uid))
    if u.id == yo.id:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta.")
    u.activo = not u.activo
    db.commit()
    return RedirectResponse("/admin/usuarios", 303)


# ---------------------------------------------------------------- gastos de operación
def _monto(v: str) -> int:
    v = (v or "").replace("$", "").replace(",", "").strip()
    return max(int(round(float(v))), 0) if v else 0


def _fecha(v: str) -> datetime:
    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except (TypeError, ValueError):
        return datetime.now()


@router.get("/gastos", response_class=HTMLResponse)
def gastos(request: Request, categoria: str = "", editar: int = 0, ok: str = "", error: str = "",
           yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    q = select(Gasto).order_by(Gasto.fecha.desc(), Gasto.id.desc())
    if categoria:
        q = q.where(Gasto.categoria == categoria)
    lista = list(db.scalars(q))
    por_cat = dict(db.execute(select(Gasto.categoria, func.sum(Gasto.monto)).group_by(Gasto.categoria)).all())
    total = sum(por_cat.values())
    por_mes = {}
    for g in db.scalars(select(Gasto)).all():
        k = g.fecha.strftime("%Y-%m")
        por_mes[k] = por_mes.get(k, 0) + g.monto
    return render(request, "admin/gastos.html", gastos=lista, categoria=categoria, cats=CATEGORIAS_GASTO,
                  por_cat=por_cat, total=total, por_mes=sorted(por_mes.items(), reverse=True)[:6],
                  editar=db.get(Gasto, editar) if editar else None, ok=ok, error=error,
                  hoy=datetime.now().strftime("%Y-%m-%d"))


@router.post("/gastos")
def guardar_gasto(concepto: str = Form(...), monto: str = Form(...), categoria: str = Form("otros"),
                  fecha: str = Form(""), nota: str = Form(""), gid: int = Form(0), volver: str = Form(""),
                  yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    try:
        cantidad = _monto(monto)
    except ValueError:
        cantidad = 0
    if not concepto.strip() or cantidad <= 0:
        return RedirectResponse("/admin/gastos?error=Escribe+el+concepto+y+un+monto+mayor+a+0", 303)
    g = db.get(Gasto, gid) if gid else Gasto()
    g.concepto = concepto.strip()[:160]
    g.monto = cantidad
    g.categoria = categoria if categoria in dict(CATEGORIAS_GASTO) else "otros"
    g.fecha = _fecha(fecha)
    g.nota = nota.strip()[:250]
    if not gid:
        db.add(g)
    db.commit()
    return RedirectResponse("/admin?ok=gasto" if volver == "resumen" else "/admin/gastos?ok=1", 303)


@router.post("/gastos/{gid}/borrar")
def borrar_gasto(gid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    g = o404(db.get(Gasto, gid))
    db.delete(g)
    db.commit()
    return RedirectResponse("/admin/gastos?ok=borrado", 303)
