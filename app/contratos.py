"""Admin: contratos con quien nos vende o deja piezas a consignación (con copia de INE privada)."""
import uuid
from datetime import datetime
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import catalogo, config
from .admin_extra import solo_admin
from .db import MODALIDADES, Contrato, ContratoPieza, Usuario
from .web import get_db, o404, render, templates

router = APIRouter(prefix="/admin/contratos")
MAX_INE = 8 * 1024 * 1024


def _entero(v) -> int | None:
    v = str(v or "").replace("$", "").replace(",", "").strip()
    try:
        return max(int(round(float(v))), 0) if v else None
    except ValueError:
        return None


def _volver(cid: int, **q) -> RedirectResponse:
    extra = "&".join(f"{k}={quote(str(v))}" for k, v in q.items())
    return RedirectResponse(f"/admin/contratos/{cid}" + (f"?{extra}" if extra else ""), 303)


@router.get("", response_class=HTMLResponse)
def lista(request: Request, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    contratos = list(db.scalars(select(Contrato).options(selectinload(Contrato.piezas))
                                .order_by(Contrato.id.desc())))
    return render(request, "admin/contratos.html", contratos=contratos)


@router.get("/nuevo", response_class=HTMLResponse)
def nuevo(request: Request, yo: Usuario = Depends(solo_admin)):
    return render(request, "admin/contrato.html", c=None, modalidades=MODALIDADES, ok="", error="")


@router.get("/{cid}", response_class=HTMLResponse)
def ver(request: Request, cid: int, ok: str = "", error: str = "", yo: Usuario = Depends(solo_admin),
        db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    return render(request, "admin/contrato.html", c=c, modalidades=MODALIDADES, ok=ok, error=error)


@router.post("/guardar")
async def guardar(request: Request, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    f = await request.form()
    cid = _entero(f.get("cid"))
    c = o404(db.get(Contrato, cid)) if cid else Contrato()
    if c.firmado:
        return _volver(c.id, error="El contrato ya está firmado. Quita la firma para editarlo.")
    nombre = (f.get("nombre") or "").strip()
    if len(nombre) < 3:
        destino = f"/admin/contratos/{c.id}" if c.id else "/admin/contratos/nuevo"
        return RedirectResponse(destino + "?error=" + quote("Escribe el nombre completo del vendedor."), 303)
    c.modalidad = f.get("modalidad") if f.get("modalidad") in dict(MODALIDADES) else "consigna"
    c.nombre = nombre[:150]
    c.telefono = "".join(ch for ch in (f.get("telefono") or "") if ch.isdigit())[-10:]
    c.domicilio = (f.get("domicilio") or "").strip()[:250]
    c.ine_clave = (f.get("ine_clave") or "").strip().upper()[:30]
    c.dias_exhibicion = _entero(f.get("dias_exhibicion")) or 60
    c.dias_pago = _entero(f.get("dias_pago")) or 7
    c.notas = (f.get("notas") or "").strip()[:2000]
    # piezas: se reemplazan con lo que viene en el formulario (conservando el vínculo a producto)
    previas = {p.id: p for p in c.piezas}
    nuevas = []
    for pid, desc, est, pv, pg in zip(f.getlist("pieza_id"), f.getlist("descripcion"), f.getlist("estado"),
                                      f.getlist("precio_venta"), f.getlist("pago_vendedor")):
        desc = (desc or "").strip()
        if not desc:
            continue
        p = previas.pop(_entero(pid), None) or ContratoPieza()
        p.descripcion, p.estado = desc[:200], (est or "").strip()[:60]
        p.precio_venta, p.pago_vendedor = _entero(pv), _entero(pg)
        nuevas.append(p)
    c.piezas = nuevas
    if not cid:
        db.add(c)
    db.commit()
    return _volver(c.id, ok="guardado")


# ---------------------------------------------------------------- INE (privada)
@router.post("/{cid}/ine")
async def subir_ine(cid: int, archivo: UploadFile = File(...), yo: Usuario = Depends(solo_admin),
                    db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    datos = await archivo.read()
    if not datos or len(datos) > MAX_INE:
        return _volver(cid, error="Sube una foto o PDF de la INE de máximo 8 MB.")
    config.PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    if datos[:4] == b"%PDF":
        nombre = f"ine-{cid}-{uuid.uuid4().hex[:12]}.pdf"
        (config.PRIVADO_DIR / nombre).write_bytes(datos)
    else:
        try:
            img = ImageOps.exif_transpose(Image.open(BytesIO(datos))).convert("RGB")  # sin datos EXIF
        except Exception:
            return _volver(cid, error="El archivo no es una imagen ni un PDF válido.")
        img.thumbnail((2000, 2000))
        nombre = f"ine-{cid}-{uuid.uuid4().hex[:12]}.jpg"
        img.save(config.PRIVADO_DIR / nombre, "JPEG", quality=88)
    if c.ine_archivo:
        (config.PRIVADO_DIR / c.ine_archivo).unlink(missing_ok=True)
    c.ine_archivo = nombre
    db.commit()
    return _volver(cid, ok="ine")


@router.get("/{cid}/ine")
def ver_ine(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    ruta = config.PRIVADO_DIR / (c.ine_archivo or "_")
    if not c.ine_archivo or not ruta.exists():
        raise HTTPException(404)
    return FileResponse(ruta, headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex"})


@router.post("/{cid}/ine/borrar")
def borrar_ine(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if c.firmado:
        return _volver(cid, error="Quita la firma antes de borrar la INE.")
    if c.ine_archivo:
        (config.PRIVADO_DIR / c.ine_archivo).unlink(missing_ok=True)
        c.ine_archivo = ""
        db.commit()
    return _volver(cid)


# ---------------------------------------------------------------- firma
@router.post("/{cid}/firmar")
def firmar(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if not c.piezas:
        return _volver(cid, error="Agrega al menos una pieza antes de firmar.")
    if c.requiere_ine(config.INE_DESDE) and not c.ine_archivo:
        return _volver(cid, error=f"Hay piezas de {config.INE_DESDE:,} pesos o más: sube la copia de la INE antes de firmar.")
    c.firmado, c.fecha_firma = True, datetime.now()
    db.commit()
    return _volver(cid, ok="firmado")


@router.post("/{cid}/quitar-firma")
def quitar_firma(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    c.firmado, c.fecha_firma = False, None
    db.commit()
    return _volver(cid)


@router.get("/{cid}/imprimir", response_class=HTMLResponse)
def imprimir(request: Request, cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    return templates.TemplateResponse(request, "admin/contrato_imprimir.html",
                                      {"c": c, "hoy": datetime.now(), "requiere_ine": c.requiere_ine(config.INE_DESDE)})


@router.post("/{cid}/borrar")
def borrar(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if c.firmado:
        return _volver(cid, error="No se puede borrar un contrato firmado.")
    if c.ine_archivo:
        (config.PRIVADO_DIR / c.ine_archivo).unlink(missing_ok=True)
    db.delete(c)
    db.commit()
    return RedirectResponse("/admin/contratos", 303)


# ---------------------------------------------------------------- pieza → producto
@router.post("/{cid}/pieza/{pid}/producto")
def crear_producto(cid: int, pid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    p = next((x for x in c.piezas if x.id == pid), None)
    if not p:
        raise HTTPException(404)
    if p.producto_id:
        return RedirectResponse(f"/admin/producto/{p.producto_id}", 303)
    compra = c.modalidad == "compra"
    prod = catalogo.crear(
        db, nombre=p.descripcion, categoria="otros", precio=p.precio_venta or 0,
        origen="propio" if compra else "consigna",
        costo=p.pago_vendedor if compra else None,   # en compra, lo que pagaste es tu inversión
        vendedor="" if compra else f"{c.nombre} · {c.folio}",
        descripcion=p.estado and f"Estado: {p.estado}." or "",
        visible=False, creado_por=f"contrato {c.folio}")
    p.producto_id = prod.id
    db.commit()
    return RedirectResponse(f"/admin/producto/{prod.id}?ok=1", 303)
