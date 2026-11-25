"""
Imágenes para Facebook (Admin → Marketing), con la identidad de ReyBasar: negro, dorado,
tipografía Titillium y el logo. 1080x1350 (4:5), el formato que más ocupa en el feed del celular.

- tarjeta(): campañas e informativas. Encabezado grande en dorado y un subtítulo.
- producto(): una pieza con su foto real, precio, Nuevo/Seminuevo y talla.
- varios(): de 2 a 4 piezas en cuadrícula, cada una con su precio.

Se dibujan con Pillow y no con un modelo de imágenes a propósito: el producto tiene que salir
tal cual es (lo que ves es lo que recibes) y el precio no puede salir mal escrito.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

ANCHO, ALTO = 1080, 1350
NEGRO = (0, 0, 0)
ORO = (242, 180, 28)
BLANCO = (255, 255, 255)
GRIS = (170, 170, 170)
VERDE = (17, 130, 63)
NARANJA = (194, 65, 12)

STATIC = config.BASE_DIR / "app" / "static"
FUENTES = STATIC / "fonts"
LOGO = STATIC / "img" / "logo-blanco.png"
CARPETA = config.MEDIA_DIR / "marketing"


def _f(peso: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FUENTES / f"TitilliumWeb-{peso}.ttf"), tam)


def _ajustar(draw: ImageDraw.ImageDraw, texto: str, fuente, ancho: int) -> list[str]:
    """Parte el texto en renglones que caben en `ancho` (respeta los saltos que ya trae)."""
    renglones: list[str] = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split():
            prueba = f"{actual} {palabra}".strip()
            if draw.textlength(prueba, font=fuente) <= ancho or not actual:
                actual = prueba
            else:
                renglones.append(actual)
                actual = palabra
        renglones.append(actual)
    return renglones


def _bloque(draw, texto: str, peso: str, tam: int, ancho: int, max_renglones: int, minimo: int = 30):
    """Baja el tamaño de letra hasta que el texto quepa en `max_renglones`."""
    while True:
        f = _f(peso, tam)
        r = _ajustar(draw, texto, f, ancho)
        if len(r) <= max_renglones or tam <= minimo:
            return f, r[:max_renglones]
        tam -= 4


def _centrado(draw, renglones, fuente, y: int, color, interlineado: float = 1.12) -> int:
    alto = int(fuente.size * interlineado)
    for r in renglones:
        w = draw.textlength(r, font=fuente)
        draw.text(((ANCHO - w) / 2, y), r, font=fuente, fill=color)
        y += alto
    return y


def _logo(lienzo: Image.Image, ancho: int, centro_x: int, y: int) -> int:
    if not LOGO.exists():
        return y
    logo = Image.open(LOGO).convert("RGBA")
    logo = logo.resize((ancho, round(logo.height * ancho / logo.width)), Image.LANCZOS)
    lienzo.paste(logo, (centro_x - ancho // 2, y), logo)
    return y + logo.height


def _guardar(lienzo: Image.Image) -> str:
    CARPETA.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex[:16]}.jpg"
    lienzo.convert("RGB").save(CARPETA / nombre, "JPEG", quality=90, optimize=True)
    return nombre


def borrar(nombre: str) -> None:
    if nombre:
        (CARPETA / nombre).unlink(missing_ok=True)


def _foto_producto(p) -> Image.Image | None:
    """Primera foto de la pieza, venga de /media (subida) o de /static (demo)."""
    for f in p.fotos:
        a = f.archivo
        ruta = STATIC / a[len("/static/"):] if a.startswith("/static/") else \
            None if a.startswith(("http", "/")) else config.MEDIA_DIR / a
        if ruta and ruta.exists():
            try:
                return ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
            except Exception:
                continue
    return None


def _marco(draw) -> None:
    draw.rectangle((28, 28, ANCHO - 29, ALTO - 29), outline=ORO, width=3)


# ── campañas ─────────────────────────────────────────────────────────────────

def tarjeta(encabezado: str, subtitulo: str = "") -> str:
    img = Image.new("RGB", (ANCHO, ALTO), NEGRO)
    d = ImageDraw.Draw(img)
    _marco(d)
    _logo(img, 420, ANCHO // 2, 120)
    f_enc, r_enc = _bloque(d, encabezado.strip(), "Black", 118, ANCHO - 200, 4, 64)
    f_sub, r_sub = _bloque(d, subtitulo.strip(), "SemiBold", 50, ANCHO - 220, 4, 34) if subtitulo.strip() else (None, [])
    alto_enc = len(r_enc) * int(f_enc.size * 1.08)
    alto_sub = (len(r_sub) * int(f_sub.size * 1.3) + 74) if r_sub else 0
    y = 330 + max(0, (ALTO - 330 - 200 - alto_enc - alto_sub) // 2)
    y = _centrado(d, r_enc, f_enc, y, ORO, 1.08)
    if r_sub:
        d.line((ANCHO / 2 - 60, y + 40, ANCHO / 2 + 60, y + 40), fill=ORO, width=4)
        _centrado(d, r_sub, f_sub, y + 74, BLANCO, 1.3)
    _pie(d)
    return _guardar(img)


def _pie(d, color_fondo=None) -> None:
    f = _f("Bold", 40)
    texto = "reybasar.mx  ·  Cuernavaca"
    w = d.textlength(texto, font=f)
    d.text(((ANCHO - w) / 2, ALTO - 130), texto, font=f, fill=ORO)


# ── productos ────────────────────────────────────────────────────────────────

def _encajar(foto: Image.Image, w: int, h: int) -> Image.Image:
    """La foto completa (sin recortar la prenda) sobre la misma foto difuminada: nada de
    franjas blancas cuando la foto es vertical y el espacio es cuadrado."""
    from PIL import ImageEnhance, ImageFilter
    caja = ImageOps.fit(foto, (w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    caja = ImageEnhance.Brightness(caja).enhance(0.75)
    f = ImageOps.contain(foto, (w, h), Image.LANCZOS)
    caja.paste(f, ((w - f.width) // 2, (h - f.height) // 2))
    return caja


def _sello(d, x: int, y: int, condicion: str, tam: int = 34) -> int:
    texto = "NUEVO" if condicion == "nuevo" else "SEMINUEVO"
    f = _f("Bold", tam)
    w = d.textlength(texto, font=f)
    d.rectangle((x, y, x + w + 28, y + tam + 18), fill=VERDE if condicion == "nuevo" else NARANJA)
    d.text((x + 14, y + 4), texto, font=f, fill=BLANCO)
    return int(x + w + 28)


def _precio(d, x: int, y: int, p, tam: int = 92) -> None:
    f = _f("Black", tam)
    texto = f"${p.precio:,}"
    d.text((x, y), texto, font=f, fill=ORO)
    if p.precio_antes and p.precio_antes > p.precio:
        fa = _f("Regular", tam // 2)
        xa = x + d.textlength(texto, font=f) + 24
        antes = f"${p.precio_antes:,}"
        ya = y + tam * 0.45
        d.text((xa, ya), antes, font=fa, fill=GRIS)
        wa = d.textlength(antes, font=fa)
        d.line((xa, ya + fa.size * 0.62, xa + wa, ya + fa.size * 0.62), fill=GRIS, width=3)


def producto(p) -> str:
    img = Image.new("RGB", (ANCHO, ALTO), NEGRO)
    foto = _foto_producto(p)
    alto_foto = 930
    if foto:
        img.paste(_encajar(foto, ANCHO, alto_foto), (0, 0))
    d = ImageDraw.Draw(img)
    x = 60
    fin_sello = _sello(d, x, alto_foto - 76, p.condicion)
    if p.talla:
        f = _f("Bold", 34)
        t = f"TALLA {p.talla.upper()}"
        w = d.textlength(t, font=f)
        d.rectangle((fin_sello + 12, alto_foto - 76, fin_sello + 12 + w + 28, alto_foto - 24), fill=NEGRO)
        d.text((fin_sello + 26, alto_foto - 72), t, font=f, fill=BLANCO)
    f_nom, r_nom = _bloque(d, p.nombre, "Bold", 58, ANCHO - 120, 2, 40)
    y = alto_foto + 34
    for r in r_nom:
        d.text((x, y), r, font=f_nom, fill=BLANCO)
        y += int(f_nom.size * 1.12)
    _precio(d, x, y + 6, p)
    _logo(img, 230, ANCHO - 60 - 115, ALTO - 150)
    f = _f("Bold", 34)
    d.text((x, ALTO - 84), "reybasar.mx", font=f, fill=ORO)
    return _guardar(img)


def varios(productos: list, titulo: str = "Lo nuevo en ReyBasar") -> str:
    productos = productos[:4]
    img = Image.new("RGB", (ANCHO, ALTO), NEGRO)
    d = ImageDraw.Draw(img)
    cabeza = 170
    f_t, r_t = _bloque(d, titulo, "Black", 76, ANCHO - 120, 1, 48)
    _centrado(d, r_t, f_t, 52, ORO)
    margen, sep = 30, 16
    pie = 170
    columnas = 2 if len(productos) > 1 else 1
    filas = (len(productos) + 1) // 2
    w = (ANCHO - 2 * margen - (columnas - 1) * sep) // columnas
    h = (ALTO - cabeza - pie - (filas - 1) * sep) // filas
    if len(productos) == 3:   # 3 piezas: la primera ocupa todo el ancho arriba
        posiciones = [(margen, cabeza, ANCHO - 2 * margen, h)] + \
                     [(margen + i * (w + sep), cabeza + h + sep, w, h) for i in range(2)]
    else:
        posiciones = [(margen + (i % 2) * (w + sep), cabeza + (i // 2) * (h + sep), w, h)
                      for i in range(len(productos))]
    for p, (px, py, pw, ph) in zip(productos, posiciones):
        foto = _foto_producto(p)
        img.paste(_encajar(foto, pw, ph) if foto else Image.new("RGB", (pw, ph), (30, 30, 30)), (px, py))
        f = _f("Black", 50)
        t = f"${p.precio:,}"
        tw = d.textlength(t, font=f)
        d.rectangle((px, py + ph - 76, px + tw + 32, py + ph), fill=NEGRO)
        d.text((px + 16, py + ph - 76), t, font=f, fill=ORO)
        _sello(d, px + 12, py + 12, p.condicion, 26)
    _logo(img, 220, ANCHO - 60 - 110, ALTO - 140)
    d.text((60, ALTO - 104), "reybasar.mx", font=_f("Bold", 40), fill=ORO)
    return _guardar(img)


# ── conceptos con escena de IA ───────────────────────────────────────────────
# La IA hace SOLO la escena (sin letras: los modelos de imagen todavia escriben mal). El texto,
# el logo y el sitio los pone este codigo, con la tipografia de la marca, siempre bien escritos.

def _degradado(img: Image.Image, arriba: bool, alto: int, fuerza: int = 235) -> None:
    capa = Image.new("L", (1, alto))
    for y in range(alto):
        t = y / max(alto - 1, 1)
        capa.putpixel((0, y), int(fuerza * ((1 - t) if arriba else t) ** 1.3))
    capa = capa.resize((ANCHO, alto))
    negro = Image.new("RGB", (ANCHO, alto), NEGRO)
    y0 = 0 if arriba else ALTO - alto
    zona = img.crop((0, y0, ANCHO, y0 + alto))
    img.paste(Image.composite(negro, zona, capa), (0, y0))


def concepto(escena: Image.Image, titulo: str, destacado: str = "", subtitulo: str = "",
             llamada: str = "", texto_arriba: bool = True) -> str:
    """Escena a sangre + frase grande (con una parte en dorado) + subtítulo + llamada + marca.
    `destacado` es la parte de `titulo` que va en dorado (debe aparecer tal cual en el título)."""
    img = ImageOps.fit(escena.convert("RGB"), (ANCHO, ALTO), Image.LANCZOS, centering=(0.5, 0.5))
    _degradado(img, arriba=texto_arriba, alto=760)
    _degradado(img, arriba=not texto_arriba, alto=300, fuerza=200)
    d = ImageDraw.Draw(img)
    margen = 70
    f_t, renglones = _bloque(d, titulo, "Black", 124, ANCHO - 2 * margen, 3, 70)
    alto_r = int(f_t.size * 1.02)
    f_s, r_s = _bloque(d, subtitulo, "SemiBold", 46, ANCHO - 2 * margen, 3, 32) if subtitulo else (None, [])
    alto_total = len(renglones) * alto_r + (len(r_s) * int(f_s.size * 1.28) + 26 if r_s else 0)
    y = 90 if texto_arriba else ALTO - 300 - alto_total
    for r in renglones:
        x = margen
        # pinta en dorado las palabras que forman parte de `destacado`
        dest = set(destacado.lower().split())
        for palabra in r.split(" "):
            limpia = palabra.lower().strip(".,!¡?¿\"“”")
            color = ORO if limpia and limpia in {w.strip(".,!¡?¿\"“”") for w in dest} else BLANCO
            d.text((x + 4, y + 4), palabra, font=f_t, fill=NEGRO)   # sombra: legible sobre cualquier foto
            d.text((x, y), palabra, font=f_t, fill=color)
            x += d.textlength(palabra + " ", font=f_t)
        y += alto_r
    if r_s:
        y += 26
        for r in r_s:
            d.text((margen + 2, y + 2), r, font=f_s, fill=NEGRO)
            d.text((margen, y), r, font=f_s, fill=BLANCO)
            y += int(f_s.size * 1.28)
    # pie: llamada a la izquierda, logo a la derecha
    if llamada:
        f_l = _f("Bold", 40)
        w = d.textlength(llamada, font=f_l)
        d.rectangle((margen, ALTO - 150, margen + w + 40, ALTO - 84), fill=ORO)
        d.text((margen + 20, ALTO - 147), llamada, font=f_l, fill=NEGRO)
    _logo(img, 250, ANCHO - margen - 125, ALTO - 165)
    return _guardar(img)
