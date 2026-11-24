"""
Llenar la ficha de un producto con IA a partir de fotos + lo que escribe el admin.

Mismas reglas que el agente de WhatsApp: la IA describe SOLO lo que se ve o lo que
dijo el dueño; nunca inventa marcas, tallas ni medidas. Los números (lo que pagó,
precio de venta, piezas) solo se llenan si el dueño los escribió.
"""
from __future__ import annotations

import base64
import json
from io import BytesIO

from PIL import Image, ImageOps

from . import config
from .config import CATEGORIAS

REGLAS = """Eres quien escribe las fichas del catálogo de ReyBasar, una tienda en Cuernavaca, México,
de ropa, calzado, juguetes y accesorios NUEVOS y SEMINUEVOS. Recibes de 1 a 6 fotos de la MISMA
pieza y lo que escribió el dueño (puede traer precio, costo, talla, marca, estado, piezas o nada).

Devuelve:
- nombre: corto y claro, como lo buscaría un cliente (máx. 70 caracteres). Ej. "Blusa rosa con
  olanes", "Chamarra de mezclilla", "Triciclo infantil". Incluye la marca solo si se lee en la
  etiqueta o el dueño la dijo.
- descripcion: 2 a 4 frases en español de México que inviten a comprar, SOLO con lo que se ve o
  lo que dijo el dueño: prenda, color, corte, detalles, estado. Si el dueño menciona un detalle o
  defecto, inclúyelo con honestidad. Prohibido inventar medidas, materiales, tallas o marcas. Nada
  de "excelente calidad". No menciones precios.
- categoria: una de {categorias}. Calzado y accesorios van con la persona a la que van dirigidos;
  aparatos (celulares, audífonos, consolas, bocinas, cargadores) van en "electronicos"; ropa,
  calzado o artículos para hacer deporte (balones, tenis deportivos, uniformes, pants deportivos,
  raquetas) van en "deportes". Si no se puede saber, "otros".
- subcategoria: SOLO si la categoría es "deportes": "ninos", "ninas", "hombre" o "mujer" según
  para quién es. En cualquier otra categoría, o si no se puede saber, null.
- condicion: "nuevo" si el dueño dice nuevo / con etiqueta / sin usar, o se ve la etiqueta de tienda
  colgando; si no, "usado".
- talla: la que dijo el dueño o la que se lea en la etiqueta ("M", "10", "26 MX"). null si no se sabe.
  Nunca la adivines por el tamaño.
- marca: si se lee en la etiqueta o el dueño la dijo. null si no.
- costo: lo que el dueño dice que PAGÓ por cada pieza ("pagué 100", "me costó 80", "costo 50"). Si
  dice que fue regalo o ya la tenía, 0. null si no lo dijo.
- precio: el precio de VENTA por pieza ("la vendo en 250", "precio 250", o un número suelto si no
  dice que es costo). null si no lo dijo.
- piezas: cuántas piezas iguales tiene ("tengo 3", "5 piezas"). null si no lo dijo.
Nunca inventes números: si el dueño no los escribió, null."""

ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nombre", "descripcion", "categoria", "subcategoria", "condicion", "talla", "marca", "costo",
                 "precio", "piezas"],
    "properties": {
        "nombre": {"type": "string"},
        "descripcion": {"type": "string"},
        "categoria": {"type": "string", "enum": [k for k, _ in CATEGORIAS if k != "demo"]},
        "subcategoria": {"type": ["string", "null"], "enum": ["ninos", "ninas", "hombre", "mujer", None]},
        "condicion": {"type": "string", "enum": ["nuevo", "usado"]},
        "talla": {"type": ["string", "null"]},
        "marca": {"type": ["string", "null"]},
        "costo": {"type": ["integer", "null"]},
        "precio": {"type": ["integer", "null"]},
        "piezas": {"type": ["integer", "null"]},
    },
}


class SinClave(RuntimeError):
    pass


def _data_uri(datos: bytes, lado: int = 1024) -> str:
    """Reduce la foto (más rápido y barato) y la manda como JPEG en base64."""
    img = ImageOps.exif_transpose(Image.open(BytesIO(datos)))
    if img.mode != "RGB":
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.convert("RGBA").split()[-1])
        img = fondo
    img.thumbnail((lado, lado))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _limpiar(f: dict) -> dict:
    """Valida lo que regresa la IA antes de ponerlo en el formulario."""
    def num(v, minimo=0, maximo=1_000_000):
        return v if isinstance(v, int) and minimo <= v <= maximo else None
    from .config import SUBCATEGORIAS
    cats = {k for k, _ in CATEGORIAS}
    cat = f.get("categoria") if f.get("categoria") in cats else "otros"
    sub = f.get("subcategoria") if f.get("subcategoria") in dict(SUBCATEGORIAS.get(cat, [])) else ""
    return {
        "nombre": (f.get("nombre") or "").strip()[:150],
        "descripcion": (f.get("descripcion") or "").strip()[:2000],
        "categoria": cat,
        "subcategoria": sub,
        "condicion": f.get("condicion") if f.get("condicion") in ("nuevo", "usado") else "usado",
        "talla": (f.get("talla") or "").strip()[:30],
        "marca": (f.get("marca") or "").strip()[:60],
        "costo": num(f.get("costo")),
        "precio": num(f.get("precio"), 1),
        "piezas": num(f.get("piezas"), 1, 999),
    }


async def llenar_ficha(fotos: list[bytes], texto: str) -> dict:
    if not config.OPENAI_API_KEY:
        raise SinClave("Falta la clave de OpenAI (OPENAI_API_KEY en el archivo .env de ReyBasar).")
    from openai import AsyncOpenAI
    cliente = AsyncOpenAI(api_key=config.OPENAI_API_KEY, timeout=60)
    partes = [{"type": "text", "text": f"Lo que escribió el dueño: {texto.strip() or '(nada)'}"}]
    for datos in fotos[:6]:
        partes.append({"type": "image_url", "image_url": {"url": _data_uri(datos), "detail": "high"}})
    categorias = ", ".join(f'"{k}"' for k, _ in CATEGORIAS if k != "demo")
    r = await cliente.chat.completions.create(
        model=config.IA_MODELO,
        messages=[{"role": "system", "content": REGLAS.format(categorias=categorias)},
                  {"role": "user", "content": partes}],
        temperature=0.3,
        response_format={"type": "json_schema",
                         "json_schema": {"name": "ficha_producto", "schema": ESQUEMA, "strict": True}},
    )
    return _limpiar(json.loads(r.choices[0].message.content or "{}"))
