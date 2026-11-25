#!/usr/bin/env python3
"""
Prueba (nov 2026): 3 conceptos de publicidad con escena hecha por IA y texto de la marca encima.
Los deja en Admin -> Marketing como "Por aprobar" para compararlos con las tarjetas actuales.

    cd /srv/reybasar/app && set -a && . /etc/reybasar/reybasar.env && set +a \
      && .venv/bin/python scripts/conceptos_prueba.py

Cada imagen cuesta unos centavos de dolar (calidad media, 1024x1536).
"""
from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app import config, marketing_img  # noqa: E402
from app.db import Publicacion, SessionLocal, init_db  # noqa: E402
from app.marketing import BASE_HASHTAGS, siguiente_libre  # noqa: E402

MODELOS = ("gpt-image-2", "gpt-image-1.5", "gpt-image-1")
ESTILO = ("Photorealistic lifestyle photograph, natural warm daylight, shot on a 35mm lens, shallow depth "
          "of field, bright and cheerful, a modest Mexican family home. Absolutely no text, letters, numbers, "
          "logos or brand names anywhere in the image. No faces. Leave calm empty space for a headline")

CONCEPTOS = [
    {"titulo": "Tu hijo creció. Su ropa no.", "destacado": "Su ropa no.",
     "subtitulo": "Ropa y juguetes nuevos y seminuevos para la siguiente talla, a precio de bazar.",
     "llamada": "reybasar.mx", "arriba": True,
     "escena": "Top-down view of a light wooden floor: a pair of worn, small toddler sneakers placed next to a "
               "slightly bigger pair of clean kids sneakers, a folded tiny t-shirt beside them. "
               + ESTILO + " in the upper half.",
     "texto": "Pasa en todas las casas: un día les queda y al siguiente ya no.\n\nEn ReyBasar encuentras ropa y "
              "juguetes nuevos y seminuevos, revisados y a precio de bazar, para la talla que sigue. Y si quieres, "
              "te compramos la que ya no les queda.\n\nVe lo que tenemos: reybasar.mx",
     "tags": "#Mamás #RopaDeNiños #RopaSeminueva"},
    {"titulo": "Tu clóset pide auxilio.", "destacado": "auxilio.",
     "subtitulo": "Te compramos la ropa y los juguetes que ya no usas y te pagamos al momento.",
     "llamada": "reybasar.mx/quiero-vender", "arriba": False,
     "escena": "A home wardrobe overflowing with clothes, a pile of sweaters about to fall, a kids toy car and a "
               "plush teddy bear squeezed between hangers, one door that cannot close, a sock falling out. "
               "Humorous but realistic. " + ESTILO + " in the lower third.",
     "texto": "¿Ese clóset que ya no cierra? Tiene solución.\n\nTe compramos la ropa y los juguetes en buen estado "
              "que ya no usas y te pagamos al momento, aquí en Cuernavaca. Sin publicar, sin regatear y sin quedar "
              "con desconocidos.\n\nMándanos fotos: reybasar.mx/quiero-vender",
     "tags": "#VendeTuRopa #LimpiaTuCloset #DineroExtra"},
    {"titulo": "47 veces “¿sigue disponible?”", "destacado": "“¿sigue disponible?”",
     "subtitulo": "Y nadie llegó. Mejor nosotros te lo compramos hoy.",
     "llamada": "reybasar.mx/quiero-vender", "arriba": True,
     "escena": "A smartphone lying face up on a kitchen table next to a cup of coffee, its screen glowing with a "
               "long stack of blank chat notification bubbles (no readable text), a hand resting tiredly beside it. "
               + ESTILO + " in the upper half.",
     "texto": "Publicaste, contestaste mil mensajes, aguantaste el regateo… y al final nadie llegó.\n\nCon ReyBasar "
              "nos mandas fotos, te decimos cuánto te pagamos y te pagamos al momento.\n\n"
              "Empieza aquí: reybasar.mx/quiero-vender",
     "tags": "#VendeTuRopa #Marketplace #DineroExtra"},
]


def generar_escena(cliente, prompt: str) -> Image.Image:
    ultimo = None
    for modelo in MODELOS:
        try:
            r = cliente.images.generate(model=modelo, prompt=prompt, size="1024x1536", quality="medium", n=1)
            print(f"   escena con {modelo}")
            return Image.open(BytesIO(base64.b64decode(r.data[0].b64_json)))
        except Exception as e:  # modelo no disponible en la cuenta: probar el siguiente
            ultimo = e
            print(f"   {modelo} no disponible: {str(e)[:120]}")
    raise SystemExit(f"Ningun modelo de imagen respondio: {ultimo}")


def main() -> None:
    if not config.OPENAI_API_KEY:
        raise SystemExit("Falta OPENAI_API_KEY en /etc/reybasar/reybasar.env")
    from openai import OpenAI
    cliente = OpenAI(api_key=config.OPENAI_API_KEY, timeout=180)
    init_db()
    with SessionLocal() as db:
        for c in CONCEPTOS:
            print("Generando:", c["titulo"])
            escena = generar_escena(cliente, c["escena"])
            imagen = marketing_img.concepto(escena, c["titulo"], c["destacado"], c["subtitulo"], c["llamada"], c["arriba"])
            from app.marketing_ia import _guardar_escena
            pub = Publicacion(tipo="concepto", titulo=f"Prueba IA · {c['titulo']}"[:120], texto=c["texto"],
                              hashtags=f"{BASE_HASHTAGS} {c['tags']}", imagen=imagen,
                              propuesta_para=siguiente_libre(db), encabezado=c["titulo"],
                              destacado=c["destacado"], subtitulo=c["subtitulo"], llamada=c["llamada"],
                              texto_arriba=c["arriba"], escena=c["escena"], escena_archivo=_guardar_escena(escena))
            db.add(pub)
            db.commit()
            print(f"   listo: {config.SITIO_URL}/admin/marketing/{pub.id}")


if __name__ == "__main__":
    main()
