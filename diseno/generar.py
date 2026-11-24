"""Genera las imágenes del sitio (banners, mosaicos de categoría, favicon, imagen para compartir).

Requiere: pip install playwright pillow && playwright install chromium
Uso (desde la carpeta del proyecto):  python diseno/generar.py
Edita textos/colores aquí y vuelve a correrlo; las imágenes salen en app/static/img/.
"""
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
F = (RAIZ / "diseno" / "fuente").as_uri()
IMG = RAIZ / "app" / "static" / "img"
FONTS = (RAIZ / "app" / "static" / "fonts").as_uri()
SALIDA_B = IMG / "banners"
SALIDA_C = IMG / "categorias"

CSS = f"""
@font-face{{font-family:T;src:url({FONTS}/TitilliumWeb-Regular.ttf);font-weight:400}}
@font-face{{font-family:T;src:url({FONTS}/TitilliumWeb-SemiBold.ttf);font-weight:600}}
@font-face{{font-family:T;src:url({FONTS}/TitilliumWeb-Bold.ttf);font-weight:700}}
@font-face{{font-family:T;src:url({FONTS}/TitilliumWeb-Black.ttf);font-weight:900}}
*{{margin:0;box-sizing:border-box}}
body{{font-family:T;width:var(--w);height:var(--h);overflow:hidden;position:relative;background-size:cover;background-position:center}}
.claro{{color:#000}} .oscuro{{color:#fff}} .dorado{{color:#000}}
.txt{{position:absolute;display:flex;flex-direction:column;gap:18px}}
.kicker{{font-weight:700;letter-spacing:.22em;font-size:22px;text-transform:uppercase}}
h1{{font-weight:900;line-height:.98;letter-spacing:.01em;text-transform:uppercase}}
h1 em{{font-style:normal;background:#000;color:#fff;padding:0 14px;display:inline-block;line-height:1.08}}
.oscuro h1 em{{background:#fff;color:#000}}
p{{font-size:27px;line-height:1.3;font-weight:400}}
.btn{{align-self:flex-start;font-weight:700;letter-spacing:.16em;font-size:22px;padding:14px 40px;border:3px solid currentColor;margin-top:8px}}
.claro .btn,.dorado .btn{{background:#000;color:#fff;border-color:#000}}
.oscuro .btn{{background:#fff;color:#000;border-color:#fff}}
.foto{{position:absolute;filter:drop-shadow(0 18px 22px rgba(0,0,0,.28))}}
.velo{{position:absolute;inset:0}}
.chips{{display:flex;gap:14px;flex-wrap:wrap}}
.chip{{border:2px solid currentColor;padding:8px 18px;font-size:22px;font-weight:600}}
.chip b{{font-weight:900}}
.sello{{position:absolute;width:190px;height:190px;border-radius:50%;border:6px double #000;display:grid;place-items:center;text-align:center;font-weight:900;font-size:30px;line-height:1;transform:rotate(-14deg);background:#fff}}
.sello small{{display:block;font-size:17px;letter-spacing:.12em;font-weight:700}}
.logo{{position:absolute}}
.insignia{{position:absolute;border-radius:50%;border:7px double;display:grid;place-items:center;box-shadow:0 16px 30px rgba(0,0,0,.25)}}
"""

# Íconos de línea (viewBox 0 0 100 100), trazo negro; sin fotos de producto.
ICONOS = {
    "dama": '<path d="M40 8v14M60 8v14M40 22q10 8 20 0M40 22l-4 22h28l-4-22M36 44 20 92h60L64 44"/><path d="M36 44h28" stroke-width="5"/>',
    "caballero": '<path d="M30 14 42 9l8 9 8-9 12 5 18 16-10 12-6-6v54H28V36l-6 6-10-12z"/><path d="M42 9l4 14 4-5 4 5 4-14"/><path d="M47 23h6l2 6-5 34-5-34z" fill="#000"/>',
    "ninos": '<path d="M32 18l10-5q8 9 16 0l10 5 16 14-10 10-6-6v50H32V36l-6 6-10-10z"/><path d="M50 44l4 9 10 1-7 7 2 10-9-5-9 5 2-10-7-7 10-1z" fill="#000" stroke-width="2"/>',
    "ninas": '<path d="M37 20q13 9 26 0l7 7-5 13 15 48H20l15-48-5-13z"/><path d="M35 40h30"/><path d="M50 20l-9-6v12zM50 20l9-6v12z" fill="#000" stroke-width="2"/><circle cx="40" cy="62" r="2.5" fill="#000"/><circle cx="58" cy="70" r="2.5" fill="#000"/><circle cx="46" cy="78" r="2.5" fill="#000"/><circle cx="62" cy="56" r="2.5" fill="#000"/>',
    "juguetes": '<circle cx="34" cy="20" r="7"/><circle cx="66" cy="20" r="7"/><circle cx="50" cy="34" r="17"/><ellipse cx="50" cy="72" rx="20" ry="20"/><ellipse cx="50" cy="74" rx="10" ry="11"/><circle cx="44" cy="31" r="2.5" fill="#000"/><circle cx="56" cy="31" r="2.5" fill="#000"/><path d="M47 39q3 3 6 0" /><circle cx="50" cy="37" r="2" fill="#000"/><circle cx="27" cy="66" r="7"/><circle cx="73" cy="66" r="7"/><circle cx="38" cy="90" r="7"/><circle cx="62" cy="90" r="7"/>',
    "gancho": '<path d="M50 36v-6a8 8 0 1 0-8-8"/><path d="M50 36 10 64q-3 4 2 4h76q5 0 2-4z"/>',
    "etiqueta": '<path d="M52 12h32v32L46 82 18 54z"/><circle cx="72" cy="24" r="5"/><text x="47" y="58" font-size="26" font-weight="900" text-anchor="middle" transform="rotate(-45 47 50)" fill="#000" stroke="none" font-family="T">$</text>',
    "camion": '<path d="M8 30h50v40H8zM58 44h18l14 14v12H58z"/><circle cx="24" cy="74" r="8" fill="#fff"/><circle cx="74" cy="74" r="8" fill="#fff"/><path d="M64 48h10l8 9H64z" fill="#000" stroke-width="2"/>',
}


def icono(nombre: str, color: str = "#000", grosor: float = 3.6) -> str:
    cuerpo = ICONOS[nombre].replace('fill="#000"', f'fill="{color}"').replace('fill="#fff"', 'fill="var(--fondo,#fff)"')
    return (f'<svg viewBox="0 0 100 100" fill="none" stroke="{color}" stroke-width="{grosor}" '
            f'stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">{cuerpo}</svg>')


def insignia(nombre: str, lado: int, oscuro: bool = False, extra: str = "") -> str:
    fondo, tinta = ("#000", "#fff") if oscuro else ("#fff", "#000")
    return (f'<div class="insignia" style="--fondo:{fondo};width:{lado}px;height:{lado}px;background:{fondo};'
            f'border-color:{tinta};{extra}"><div style="width:58%;height:58%">{icono(nombre, tinta)}</div></div>')


BANNERS = {
    "inicio": dict(fondo="fondo3-large.jpg", tema="claro", arte="conejo",
                   kicker="Nuevo y seminuevo", titulo="Piezas únicas<br>a precio <em>de rey</em>",
                   texto="Ropa y juguetes para toda la familia,<br>revisados y listos para estrenar.", boton="VER CATÁLOGO"),
    "vender": dict(fondo="fondo1.jpg", tema="oscuro", arte=["gancho", "etiqueta"],
                   kicker="Quiero vender", titulo="¿Ya no lo usas?<br><em>Véndelo</em> con nosotros",
                   texto="Nosotros ponemos fotos, publicación y clientes.",
                   chips=["<b>Consignación:</b> recibes más", "<b>Compra directa:</b> dinero hoy"], boton="QUIERO VENDER"),
    "envio": dict(fondo="fondo2.jpg", tema="claro", arte=["camion"],
                  kicker="Entrega local", titulo="Entregas en<br><em>Cuernavaca</em>",
                  texto="Haz tu pedido y acordamos contigo<br>el lugar y la hora por WhatsApp.", boton="EMPEZAR A COMPRAR", tam=80),
    "familia": dict(fondo="fondo3-large.jpg", tema="dorado", arte=["dama", "caballero", "ninas", "ninos", "juguetes"],
                    kicker="Para toda la familia", titulo="Dama, caballero,<br>niños y <em>juguetes</em>", tam=72,
                    texto="Cada semana subimos piezas nuevas.<br>Cuando se van, se van.", boton="VER CATEGORÍAS"),
}

CATEGORIAS = {  # nombre: (fondo, alto)
    "juguetes": ("fondo2.jpg", 420),
    "caballero": ("fondo3-large.jpg", 420),
    "dama": ("fondo3-large.jpg", 860),
    "ninos": ("fondo2.jpg", 420),
    "ninas": ("fondo3-large.jpg", 420),
    "otros": ("fondo2.jpg", 420),
}


def arte_banner(b: dict, movil: bool) -> str:
    oscuro = b["tema"] == "oscuro"
    arte = b["arte"]
    if arte == "conejo":
        lado = 400 if movil else 470
        pos = "left:50%;top:40px;transform:translateX(-50%)" if movil else "right:130px;top:50%;transform:translateY(-50%)"
        return (f'<div class="insignia" style="width:{lado}px;height:{lado}px;background:#fff;border-color:#000;{pos}">'
                f'<img src="{(IMG / "conejo.png").as_uri()}" style="width:66%;margin-left:6%"></div>')
    if len(arte) == 1:
        lado = 400 if movil else 440
        pos = "left:50%;top:40px;transform:translateX(-50%)" if movil else "right:160px;top:50%;transform:translateY(-50%)"
        return insignia(arte[0], lado, oscuro, pos)
    if len(arte) == 2:
        if movil:
            return (insignia(arte[0], 330, oscuro, "left:130px;top:40px") +
                    insignia(arte[1], 200, not oscuro, "right:120px;top:230px;transform:rotate(-10deg)"))
        return (insignia(arte[0], 380, oscuro, "right:250px;top:60px") +
                insignia(arte[1], 220, not oscuro, "right:110px;top:290px;transform:rotate(-10deg)"))
    # varios: fila/arco de insignias
    if movil:
        coords = [(60, 60, 200), (300, 30, 200), (540, 60, 200), (180, 250, 190), (430, 250, 190)]
    else:
        coords = [(930, 60, 180), (1150, 30, 180), (1370, 60, 180), (1040, 285, 170), (1260, 285, 170)]
    return "".join(insignia(n, l, oscuro, f"left:{x}px;top:{y}px") for n, (x, y, l) in zip(arte, coords))
def html_banner(b: dict, movil: bool) -> str:
    w, h = (800, 1000) if movil else (1600, 560)
    chips = "".join(f'<span class="chip">{c}</span>' for c in b.get("chips", []))
    if movil:
        velo = {"oscuro": "linear-gradient(180deg,rgba(0,0,0,0) 38%,rgba(0,0,0,.88) 52%)",
                "dorado": "linear-gradient(180deg,rgba(242,182,48,.86),rgba(242,182,48,.97) 50%)"}.get(
                    b["tema"], "linear-gradient(180deg,rgba(255,255,255,0) 38%,rgba(255,255,255,.93) 52%)")
        txt = f'style="left:50px;right:50px;top:470px;align-items:center;text-align:center"'
        h1 = f"font-size:{60 if b.get('tam') else 72}px"
        extra = ".btn{align-self:center}.chips{justify-content:center}p{font-size:28px}"
    else:
        velo = {"oscuro": "linear-gradient(90deg,rgba(0,0,0,.85) 0 48%,rgba(0,0,0,.15) 75%)",
                "dorado": "linear-gradient(90deg,rgba(242,182,48,.97) 0 50%,rgba(242,182,48,.86))"}.get(
                    b["tema"], "linear-gradient(90deg,rgba(255,255,255,.92) 0 46%,rgba(255,255,255,.2) 75%)")
        txt = 'style="left:110px;top:50%;transform:translateY(-50%);max-width:780px"'
        h1 = f"font-size:{b.get('tam', 84)}px"
        extra = ""
    return f"""<html><head><style>{CSS}{extra}</style></head>
<body class="{b['tema']}" style="--w:{w}px;--h:{h}px;background-image:url({F}/{b['fondo']})">
<div class="velo" style="background:{velo}"></div>{arte_banner(b, movil)}
<div class="txt" {txt}><span class="kicker">{b['kicker']}</span><h1 style="{h1}">{b['titulo']}</h1>
<p>{b['texto']}</p>{f'<div class="chips">{chips}</div>' if chips else ''}<span class="btn">{b['boton']}</span></div>
</body></html>"""


def html_categoria(nombre: str, fondo: str, alto: int) -> str:
    lado = int(alto * (0.5 if alto > 600 else 0.78))
    return f"""<html><head><style>{CSS}</style></head>
<body style="--w:900px;--h:{alto}px;background-image:url({F}/{fondo})">
<div class="velo" style="background:radial-gradient(ellipse at center,rgba(255,255,255,.85),rgba(255,255,255,.1) 70%)"></div>
{insignia(nombre, lado, False, "left:50%;top:50%;transform:translate(-50%,-50%)")}
</body></html>"""


def html_og() -> str:
    return f"""<html><head><style>{CSS}</style></head>
<body class="oscuro" style="--w:1200px;--h:630px;background-image:url({F}/fondo1.jpg)">
<div class="velo" style="background:radial-gradient(ellipse at center,rgba(0,0,0,.82) 30%,rgba(0,0,0,.35))"></div>
<div class="txt" style="inset:0;align-items:center;justify-content:center;text-align:center">
<img src="{(IMG / 'logo-blanco.png').as_uri()}" style="width:640px">
<p style="font-size:34px;font-weight:600;letter-spacing:.04em">Ropa y juguetes nuevos y seminuevos</p>
<span class="kicker" style="font-size:24px">Piezas únicas · Envíos a todo México</span></div></body></html>"""


def favicons():
    conejo = Image.open(IMG / "conejo.png").convert("RGBA")
    # conejo blanco sobre cuadro negro redondeado (igual que el encabezado)
    r, g, b, a = conejo.split()
    inv = Image.merge("RGBA", (*(Image.eval(c, lambda v: 255 - v) for c in (r, g, b)), a))
    from PIL import ImageDraw
    def icono(lado, radio):
        base = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        ImageDraw.Draw(base).rounded_rectangle((0, 0, lado - 1, lado - 1), radius=radio, fill=(0, 0, 0, 255))
        c = inv.copy(); c.thumbnail((int(lado * .86), int(lado * .86)), Image.LANCZOS)
        base.alpha_composite(c, ((lado - c.width) // 2, (lado - c.height) // 2 + int(lado * .02)))
        return base
    icono(512, 96).save(IMG / "icon-512.png")
    icono(192, 36).save(IMG / "icon-192.png")
    icono(180, 0).convert("RGB").save(IMG / "apple-touch-icon.png")
    icono(64, 12).save(IMG / "favicon.png")
    icono(256, 48).save(IMG / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])


def main():
    SALIDA_B.mkdir(parents=True, exist_ok=True)
    SALIDA_C.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pg = nav.new_page()

        def foto(html, w, h, destino, calidad=86):
            pg.set_viewport_size({"width": w, "height": h})
            plantilla = RAIZ / "diseno" / "_tmp.html"
            plantilla.write_text(html, encoding="utf-8")
            pg.goto(plantilla.as_uri())
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(200)
            plantilla.unlink()
            tmp = destino.with_suffix(".png")
            pg.screenshot(path=str(tmp))
            Image.open(tmp).convert("RGB").save(destino, quality=calidad, optimize=True, progressive=True)
            tmp.unlink()
            print("✓", destino.relative_to(RAIZ))

        for nombre, b in BANNERS.items():
            foto(html_banner(b, False), 1600, 560, SALIDA_B / f"{nombre}.jpg")
            foto(html_banner(b, True), 800, 1000, SALIDA_B / f"{nombre}-movil.jpg")
        for nombre, (fondo, alto) in CATEGORIAS.items():
            icono_cat = "ninas" if nombre == "otros" else nombre
            foto(html_categoria(icono_cat if nombre != "otros" else "etiqueta", fondo, alto), 900, alto,
                 SALIDA_C / f"{nombre}.jpg", 84)
        foto(html_og(), 1200, 630, IMG / "compartir.jpg")
        nav.close()
    favicons()
    print("✓ favicons")


if __name__ == "__main__":
    main()
