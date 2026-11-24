"""Admin: contratos con quien nos vende o deja piezas a consignación (con copia de INE privada)."""
import uuid
from datetime import datetime
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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


# ---------------------------------------------------------------- vista previa, PDF y firma
def _priv(nombre: str):
    return config.PRIVADO_DIR / nombre


def _borrar_priv(*nombres: str) -> None:
    for n in nombres:
        if n:
            _priv(n).unlink(missing_ok=True)


def _puede_firmar(c: Contrato) -> str:
    if not c.piezas:
        return "Agrega al menos una pieza antes de firmar."
    if c.requiere_ine(config.INE_DESDE) and not c.ine_archivo:
        return f"Hay piezas de {config.INE_DESDE:,} pesos o más: sube la copia de la INE antes de firmar."
    return ""


def generar_pdf(c: Contrato, request: Request | None = None) -> bytes:
    """Contrato en PDF (xhtml2pdf). Las firmas se incrustan desde la carpeta privada."""
    from xhtml2pdf import pisa
    import base64
    firmas, tam = {}, {}
    for quien, nombre in (("vendedor", c.firma_vendedor), ("tienda", c.firma_tienda)):
        if nombre and _priv(nombre).exists():
            datos = _priv(nombre).read_bytes()
            w, h = Image.open(BytesIO(datos)).size
            esc = min(230 / w, 54 / h)   # cabe en el espacio de firma (pt)
            firmas[quien] = "data:image/png;base64," + base64.b64encode(datos).decode()
            tam[quien] = (round(w * esc), round(h * esc))
    html = templates.get_template("admin/contrato_pdf.html").render(
        c=c, hoy=datetime.now(), requiere_ine=c.requiere_ine(config.INE_DESDE), firmas=firmas, tam=tam)
    salida = BytesIO()
    resultado = pisa.CreatePDF(html, dest=salida, encoding="utf-8")
    if resultado.err:
        raise HTTPException(500, "No se pudo generar el PDF")
    return salida.getvalue()


@router.get("/formato/{modalidad}")
def formato_en_blanco(modalidad: str, yo: Usuario = Depends(solo_admin)):
    """Contrato vacío para imprimir y llenar a mano cuando no hay computadora a la mano."""
    from types import SimpleNamespace
    from xhtml2pdf import pisa
    if modalidad not in ("compra", "consigna"):
        raise HTTPException(404)
    c = SimpleNamespace(modalidad=modalidad, piezas=[], firmado=False, fecha_firma=None, notas="",
                        nombre="", ine_clave="", telefono="", domicilio="", folio="",
                        total_venta=0, total_vendedor=0, dias_pago=0, dias_exhibicion=0, ine_archivo="")
    html = templates.get_template("admin/contrato_pdf.html").render(
        c=c, hoy=datetime.now(), requiere_ine=False, firmas={}, tam={}, blanco=True, ine_desde=config.INE_DESDE)
    salida = BytesIO()
    if pisa.CreatePDF(html, dest=salida, encoding="utf-8").err:
        raise HTTPException(500, "No se pudo generar el PDF")
    nombre = "Contrato-compraventa-en-blanco.pdf" if modalidad == "compra" else "Contrato-consignacion-en-blanco.pdf"
    return Response(salida.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{nombre}"', "Cache-Control": "private, no-store"})


@router.get("/{cid}/imprimir", response_class=HTMLResponse)
def imprimir(request: Request, cid: int, embed: int = 0, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    firmas = {k: f"/admin/contratos/{cid}/firma/{k}" for k, v in
              (("vendedor", c.firma_vendedor), ("tienda", c.firma_tienda)) if v}
    return templates.TemplateResponse(request, "admin/contrato_imprimir.html", {
        "c": c, "hoy": datetime.now(), "requiere_ine": c.requiere_ine(config.INE_DESDE),
        "firmas": firmas, "embed": embed})


@router.get("/{cid}/pdf")
def pdf(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    nombre = f"Contrato-{c.folio}.pdf"
    if c.firmado and c.pdf_final and _priv(c.pdf_final).exists():
        datos = _priv(c.pdf_final).read_bytes()
    else:
        datos = generar_pdf(c)
    return Response(datos, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{nombre}"', "Cache-Control": "private, no-store"})


@router.get("/{cid}/firma/{quien}")
def ver_firma(cid: int, quien: str, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    nombre = {"vendedor": c.firma_vendedor, "tienda": c.firma_tienda}.get(quien)
    if not nombre or not _priv(nombre).exists():
        raise HTTPException(404)
    return FileResponse(_priv(nombre), headers={"Cache-Control": "private, no-store"})


def _guardar_firma(cid: int, quien: str, data_url: str) -> str:
    """Firma dibujada (data:image/png;base64,...) → PNG con fondo blanco en la carpeta privada."""
    import base64
    if not data_url.startswith("data:image/png;base64,"):
        raise ValueError("Firma inválida.")
    crudo = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    if len(crudo) > 2 * 1024 * 1024:
        raise ValueError("Firma demasiado grande.")
    img = Image.open(BytesIO(crudo)).convert("RGBA")
    caja = img.getchannel("A").getbbox()
    if not caja or (caja[2] - caja[0]) < 40 or (caja[3] - caja[1]) < 15:
        raise ValueError("La firma está vacía o es muy pequeña: firma de nuevo.")
    fondo = Image.new("RGB", img.size, (255, 255, 255))
    fondo.paste(img, mask=img.getchannel("A"))
    fondo = fondo.crop((max(caja[0] - 10, 0), max(caja[1] - 10, 0), caja[2] + 10, caja[3] + 10))
    config.PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    nombre = f"firma-{quien}-{cid}-{uuid.uuid4().hex[:10]}.png"
    fondo.save(_priv(nombre), "PNG", optimize=True)
    return nombre


def _cerrar_firma(c: Contrato, metodo: str) -> None:
    c.firmado, c.fecha_firma, c.firmado_metodo = True, datetime.now(), metodo
    datos = generar_pdf(c)   # copia final con firmas incrustadas: ya no cambia
    nombre = f"contrato-{c.folio}-{uuid.uuid4().hex[:8]}.pdf"
    _priv(nombre).write_bytes(datos)
    c.pdf_final = nombre


@router.post("/{cid}/firmar-pantalla")
def firmar_pantalla(cid: int, firma_vendedor: str = Form(""), firma_tienda: str = Form(""),
                    acepto: str = Form(""), yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if c.firmado:
        return _volver(cid)
    error = _puede_firmar(c)
    if not error and not acepto:
        error = "Confirma que el vendedor leyó y acepta el contrato."
    if error:
        return _volver(cid, error=error)
    try:
        fv = _guardar_firma(cid, "vendedor", firma_vendedor)
        ft = _guardar_firma(cid, "tienda", firma_tienda)
    except (ValueError, Exception) as e:
        return _volver(cid, error=str(e) if isinstance(e, ValueError) else "No se pudo leer la firma: firma de nuevo.")
    _borrar_priv(c.firma_vendedor, c.firma_tienda)
    c.firma_vendedor, c.firma_tienda = fv, ft
    _cerrar_firma(c, "pantalla")
    db.commit()
    return _volver(cid, ok="firmado")


@router.post("/{cid}/firmado-papel")
async def firmado_papel(cid: int, archivo: UploadFile = File(...), yo: Usuario = Depends(solo_admin),
                        db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if c.firmado:
        return _volver(cid)
    error = _puede_firmar(c)
    if error:
        return _volver(cid, error=error)
    datos = await archivo.read()
    if not datos or len(datos) > 15 * 1024 * 1024:
        return _volver(cid, error="Sube una foto o PDF del contrato firmado (máximo 15 MB).")
    config.PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    if datos[:4] == b"%PDF":
        nombre = f"firmado-{c.folio}-{uuid.uuid4().hex[:8]}.pdf"
        _priv(nombre).write_bytes(datos)
    else:
        try:
            img = ImageOps.exif_transpose(Image.open(BytesIO(datos))).convert("RGB")
        except Exception:
            return _volver(cid, error="El archivo no es una imagen ni un PDF válido.")
        img.thumbnail((2400, 2400))
        nombre = f"firmado-{c.folio}-{uuid.uuid4().hex[:8]}.jpg"
        img.save(_priv(nombre), "JPEG", quality=88)
    _borrar_priv(c.archivo_firmado)
    c.archivo_firmado = nombre
    _cerrar_firma(c, "papel")
    db.commit()
    return _volver(cid, ok="firmado")


@router.get("/{cid}/firmado")
def ver_firmado(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if not c.archivo_firmado or not _priv(c.archivo_firmado).exists():
        raise HTTPException(404)
    return FileResponse(_priv(c.archivo_firmado), headers={"Cache-Control": "private, no-store"})


@router.post("/{cid}/quitar-firma")
def quitar_firma(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    """Para corregir un error: borra firmas, foto firmada y PDF final (habrá que volver a firmar)."""
    c = o404(db.get(Contrato, cid))
    _borrar_priv(c.firma_vendedor, c.firma_tienda, c.archivo_firmado, c.pdf_final)
    c.firmado, c.fecha_firma, c.firmado_metodo = False, None, ""
    c.firma_vendedor = c.firma_tienda = c.archivo_firmado = c.pdf_final = ""
    db.commit()
    return _volver(cid)


@router.post("/{cid}/borrar")
def borrar(cid: int, yo: Usuario = Depends(solo_admin), db=Depends(get_db)):
    c = o404(db.get(Contrato, cid))
    if c.firmado:
        return _volver(cid, error="No se puede borrar un contrato firmado.")
    _borrar_priv(c.ine_archivo, c.firma_vendedor, c.firma_tienda, c.archivo_firmado, c.pdf_final)
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
