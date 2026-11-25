"""
Conceptos de publicidad con IA para Admin -> Marketing.

Dos pasos, a proposito separados:
  1. Un modelo de texto piensa el concepto (titulo, subtitulo, texto, hashtags y la escena) a partir
     de lo que ya hay y de la indicacion del admin.
  2. Un modelo de imagen pinta SOLO la escena, sin letras: los modelos de imagen todavia escriben
     mal. Las letras, el logo y el sitio los pone marketing_img.concepto() con la tipografia de la marca.

Si la indicacion solo pide cambios de texto, se reusa la escena anterior: no se paga otra imagen
ni se esperan 1-2 minutos por nada.

Corre en segundo plano (una tarea asyncio; el servicio tiene un solo worker): la pagina muestra
"La IA esta trabajando" y se actualiza sola.
"""
from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO

from PIL import Image

from . import config, marketing_img
from .db import Publicacion, SessionLocal

MODELOS_IMAGEN = ("gpt-image-2", "gpt-image-1.5", "gpt-image-1")
LLAMADAS = ("reybasar.mx", "reybasar.mx/quiero-vender")

ESTILO_ESCENA = ("Photorealistic lifestyle photograph, natural warm daylight, 35mm lens, shallow depth of field, "
                 "bright and cheerful, a modest Mexican family home or a street in Cuernavaca. Absolutely no text, "
                 "letters, numbers, logos or brand names anywhere in the image. No recognizable faces. Leave calm "
                 "empty space for a headline in the {zona}.")

REGLAS = """Eres el director creativo de ReyBasar, una tienda familiar de Cuernavaca, Morelos, que vende
ropa y juguetes NUEVOS y SEMINUEVOS (tambien electronicos, deportes y articulos de alberca), revisados y
con fotos reales, con entregas solo en Cuernavaca en un punto que se acuerda con el cliente. Tambien
COMPRA la ropa y los juguetes que la gente ya no usa y paga al momento, o los recibe a consignacion.
Pedidos en reybasar.mx o por WhatsApp al {telefono}. Venderle a ReyBasar: reybasar.mx/quiero-vender.

Haces publicaciones de Facebook que detienen el scroll, como la mejor publicidad: UNA sola idea grande,
que la persona se sienta identificada (mamas y papas de Cuernavaca, su casa, sus hijos, su closet), con
humor o calidez y un toque local. Habla del cliente, no de nosotros.

Reglas que no se rompen:
- Nada de marcas, logotipos ni personajes con derechos (Disney, Marvel, etc.), ni en el texto ni en la escena.
- Prohibido inventar precios, descuentos, promociones, fechas, sucursales o servicios que no esten arriba.
- La escena no lleva caras reconocibles: manos, objetos, espacios, personas de espaldas o recortadas.
- Espanol de Mexico, cercano y sin groserias. Maximo 2 emojis en el texto.

Devuelve:
- titulo: la frase grande de la imagen, maximo 7 palabras.
- destacado: la parte final del titulo que va en dorado (copiada tal cual del titulo) o "".
- subtitulo: una frase de apoyo para la imagen, maximo 18 palabras.
- llamada: "reybasar.mx" si invita a comprar o "reybasar.mx/quiero-vender" si invita a vender.
- texto_arriba: true si el titulo va arriba de la imagen, false si va abajo.
- cambiar_escena: true si hace falta una escena nueva (no hay escena, o la indicacion pide cambiar lo
  que se ve); false si basta con cambiar textos.
- escena: descripcion EN INGLES de la foto (que se ve, donde, luz, composicion), sin texto en la imagen.
- texto: la publicacion para Facebook, de 3 a 7 renglones cortos, que termine con la llamada a la accion
  y el enlace (reybasar.mx o reybasar.mx/quiero-vender). Sin hashtags.
- hashtags: de 5 a 8 en espanol separados por espacio; siempre #ReyBasar y #Cuernavaca."""

ESQUEMA = {"type": "object", "additionalProperties": False,
           "required": ["titulo", "destacado", "subtitulo", "llamada", "texto_arriba", "cambiar_escena",
                        "escena", "texto", "hashtags"],
           "properties": {"titulo": {"type": "string"}, "destacado": {"type": "string"},
                          "subtitulo": {"type": "string"}, "llamada": {"type": "string", "enum": list(LLAMADAS)},
                          "texto_arriba": {"type": "boolean"}, "cambiar_escena": {"type": "boolean"},
                          "escena": {"type": "string"}, "texto": {"type": "string"},
                          "hashtags": {"type": "string"}}}


class SinClave(Exception):
    pass


def _cliente():
    if not config.OPENAI_API_KEY:
        raise SinClave("Falta la clave de OpenAI en el servidor (OPENAI_API_KEY).")
    from openai import OpenAI
    return OpenAI(api_key=config.OPENAI_API_KEY, timeout=240)


def _telefono() -> str:
    t = "".join(c for c in config.WHATSAPP if c.isdigit())[-10:]
    return f"{t[:3]} {t[3:6]} {t[6:]}" if len(t) == 10 else config.WHATSAPP


def pensar_concepto(actual: dict, indicacion: str) -> dict:
    """Modelo de texto: devuelve el concepto nuevo (dict con las llaves de ESQUEMA)."""
    cliente = _cliente()
    pedido = {"publicacion_actual": actual, "indicacion_del_dueno": indicacion.strip() or "(ninguna: mejoralo)"}
    r = cliente.chat.completions.create(
        model=config.IA_MODELO, temperature=0.8,
        messages=[{"role": "system", "content": REGLAS.format(telefono=_telefono())},
                  {"role": "user", "content": json.dumps(pedido, ensure_ascii=False)}],
        response_format={"type": "json_schema", "json_schema": {"name": "concepto", "schema": ESQUEMA, "strict": True}})
    c = json.loads(r.choices[0].message.content or "{}")
    c["titulo"] = (c.get("titulo") or "").strip()[:120]
    c["destacado"] = c.get("destacado", "").strip() if c.get("destacado", "").strip() in c["titulo"] else ""
    tags = c.get("hashtags", "")
    for base in ("#ReyBasar", "#Cuernavaca"):
        if base.lower() not in tags.lower():
            tags = f"{base} {tags}".strip()
    c["hashtags"] = " ".join(tags.split())[:400]
    if c.get("llamada") not in LLAMADAS:
        c["llamada"] = LLAMADAS[0]
    return c


def pintar_escena(descripcion: str, texto_arriba: bool) -> Image.Image:
    """Modelo de imagen: solo la escena, sin letras. Prueba modelos del mas nuevo al mas viejo."""
    cliente = _cliente()
    prompt = descripcion.strip() + " " + ESTILO_ESCENA.format(zona="upper half" if texto_arriba else "lower third")
    ultimo = None
    for modelo in MODELOS_IMAGEN:
        try:
            r = cliente.images.generate(model=modelo, prompt=prompt, size="1024x1536", quality="medium", n=1)
            return Image.open(BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
        except Exception as e:   # modelo no disponible para la cuenta: siguiente
            ultimo = e
    raise RuntimeError(f"No se pudo crear la escena: {str(ultimo)[:200]}")


def _actual(pub: Publicacion) -> dict:
    return {"tipo": pub.tipo, "titulo_imagen": pub.encabezado, "subtitulo_imagen": pub.subtitulo,
            "texto": pub.texto, "hashtags": pub.hashtags, "escena": pub.escena or "(no tiene escena todavia)"}


def _guardar_escena(escena: Image.Image) -> str:
    """Guarda la escena sin texto para poder recomponer sin pagar otra."""
    import uuid
    marketing_img.CARPETA.mkdir(parents=True, exist_ok=True)
    nombre = f"escena-{uuid.uuid4().hex[:16]}.jpg"
    escena.save(marketing_img.CARPETA / nombre, "JPEG", quality=92)
    return nombre


def retrabajar_sync(pid: int, indicacion: str) -> None:
    """El trabajo completo (bloqueante). Deja la publicacion en tipo 'concepto'."""
    with SessionLocal() as db:
        pub = db.get(Publicacion, pid)
        if not pub:
            return
        try:
            c = pensar_concepto(_actual(pub), indicacion)
            escena_vieja = marketing_img.CARPETA / pub.escena_archivo if pub.escena_archivo else None
            necesita = c["cambiar_escena"] or not (escena_vieja and escena_vieja.exists())
            if necesita:
                escena = pintar_escena(c["escena"], c["texto_arriba"])
                nueva_escena = _guardar_escena(escena)
            else:
                escena = Image.open(escena_vieja).convert("RGB")
                nueva_escena = pub.escena_archivo
            imagen = marketing_img.concepto(escena, c["titulo"], c["destacado"], c["subtitulo"],
                                            c["llamada"], c["texto_arriba"])
            anteriores = [pub.imagen] + ([pub.escena_archivo] if nueva_escena != pub.escena_archivo else [])
            pub.tipo, pub.imagen, pub.escena_archivo = "concepto", imagen, nueva_escena
            pub.encabezado, pub.destacado, pub.subtitulo = c["titulo"][:160], c["destacado"][:160], c["subtitulo"][:200]
            pub.llamada, pub.texto_arriba = c["llamada"], bool(c["texto_arriba"])
            pub.escena = c["escena"][:4000] if necesita else pub.escena
            pub.texto, pub.hashtags = c["texto"].strip()[:5000], c["hashtags"]
            if pub.titulo.startswith(("Nueva idea", "Prueba IA")) or not pub.titulo:
                pub.titulo = c["titulo"][:120]
            pub.error_ia = ""
            for a in anteriores:
                marketing_img.borrar(a)
        except Exception as e:
            pub.error_ia = (str(e) if isinstance(e, (SinClave, RuntimeError)) else
                            f"La IA no pudo terminar ({type(e).__name__}). Intenta de nuevo.")[:300]
        finally:
            pub.trabajando = False
            db.commit()


def texto_con_indicacion_sync(pid: int, indicacion: str, piezas_datos: list[dict]) -> None:
    """Publicaciones de productos: solo el texto, con la indicacion; la imagen (fotos reales) no se toca."""
    with SessionLocal() as db:
        pub = db.get(Publicacion, pid)
        if not pub:
            return
        try:
            cliente = _cliente()
            from .marketing import ESQUEMA as ESQ_TEXTO, REGLAS as REGLAS_TEXTO
            r = cliente.chat.completions.create(
                model=config.IA_MODELO, temperature=0.8,
                messages=[{"role": "system", "content": REGLAS_TEXTO.format(
                              sitio=config.SITIO_URL.replace("https://", ""), telefono=_telefono())},
                          {"role": "user", "content": json.dumps(
                              {"piezas": piezas_datos, "texto_actual": pub.texto,
                               "indicacion_del_dueno": indicacion}, ensure_ascii=False)}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "publicacion", "schema": ESQ_TEXTO, "strict": True}})
            d = json.loads(r.choices[0].message.content or "{}")
            if d.get("texto"):
                pub.texto = d["texto"].strip()[:5000]
                tags = d.get("hashtags", "")
                for base in ("#ReyBasar", "#Cuernavaca"):
                    if base.lower() not in tags.lower():
                        tags = f"{base} {tags}".strip()
                pub.hashtags = " ".join(tags.split())[:400]
            pub.error_ia = ""
        except Exception as e:
            pub.error_ia = (str(e) if isinstance(e, SinClave) else
                            f"La IA no pudo terminar ({type(e).__name__}). Intenta de nuevo.")[:300]
        finally:
            pub.trabajando = False
            db.commit()


_tareas: set = set()


def en_segundo_plano(funcion, *args) -> None:
    """Corre `funcion` en un hilo sin bloquear la pagina. Guarda la referencia para que no se pierda."""
    tarea = asyncio.get_running_loop().create_task(asyncio.to_thread(funcion, *args))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)


def soltar_atoradas() -> None:
    """Al arrancar: si el servicio se reinicio a media tarea, no dejar la publicacion 'trabajando' para siempre."""
    with SessionLocal() as db:
        for pub in db.query(Publicacion).filter(Publicacion.trabajando.is_(True)):
            pub.trabajando, pub.error_ia = False, "Se interrumpió (reinicio del servidor). Vuelve a intentarlo."
        db.commit()


# ── parrilla semanal ─────────────────────────────────────────────────────────
PLAN = """Eres el director creativo de ReyBasar (tienda familiar de Cuernavaca de ropa y juguetes nuevos y
seminuevos, que tambien compra lo que la gente ya no usa). Planea los temas de las publicaciones de
"tema libre" de la semana: una por dia, en el orden de los dias que te paso.

Mezcla tipos distintos, sin repetir dos iguales seguidos: humor/meme de la vida diaria de mamas y papas;
moda y tendencias accesibles; consejo util (cuidar la ropa, ordenar el closet, tallas de ninos);
"vende lo que ya no usas"; temporada o fecha que este cerca de ese dia (sin inventar eventos de la
tienda); orgullo local de Cuernavaca. Evita repetir los temas recientes que te paso.

Para cada dia devuelve `indicacion`: 1 o 2 frases en espanol con la idea concreta y el angulo (a quien
le habla y por que se va a sentir identificado). Sin marcas, sin personajes con derechos, sin prometer
precios ni promociones."""

ESQUEMA_PLAN = {"type": "object", "additionalProperties": False, "required": ["temas"],
                "properties": {"temas": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["dia", "indicacion"],
                    "properties": {"dia": {"type": "string"}, "indicacion": {"type": "string"}}}}}}

DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def planear_temas(dias: list, recientes: list[str]) -> list[str]:
    cliente = _cliente()
    pedido = {"dias": [f"{DIAS_SEMANA[d.weekday()]} {d.isoformat()}" for d in dias], "temas_recientes": recientes[:30]}
    r = cliente.chat.completions.create(
        model=config.IA_MODELO, temperature=0.9,
        messages=[{"role": "system", "content": PLAN}, {"role": "user", "content": json.dumps(pedido, ensure_ascii=False)}],
        response_format={"type": "json_schema", "json_schema": {"name": "plan", "schema": ESQUEMA_PLAN, "strict": True}})
    temas = [t.get("indicacion", "").strip() for t in json.loads(r.choices[0].message.content or "{}").get("temas", [])]
    temas = [t for t in temas if t]
    while len(temas) < len(dias):   # si devolvio menos, que la IA elija libre en los que faltan
        temas.append("Tema libre: elige algo con lo que las familias de Cuernavaca se identifiquen.")
    return temas[:len(dias)]


def parrilla_sync(conceptos: list[int], dias: list, recientes: list[str], productos: list[tuple[int, list[dict]]]) -> None:
    """Segundo plano: primero los textos de productos (rapidos), luego el plan de temas y cada concepto."""
    for pid, datos in productos:
        texto_con_indicacion_sync(pid, "", datos)
    try:
        temas = planear_temas(dias, recientes)
    except Exception as e:
        with SessionLocal() as db:
            for pid in conceptos:
                pub = db.get(Publicacion, pid)
                if pub:
                    pub.trabajando = False
                    pub.error_ia = (str(e) if isinstance(e, SinClave) else
                                    f"La IA no pudo planear la semana ({type(e).__name__}). Usa Retrabajar.")[:300]
            db.commit()
        return
    with SessionLocal() as db:
        for pid, tema in zip(conceptos, temas):
            pub = db.get(Publicacion, pid)
            if pub:
                pub.indicacion, pub.titulo = tema, f"Nueva idea: {tema}"[:120]
        db.commit()
    for pid, tema in zip(conceptos, temas):
        retrabajar_sync(pid, tema)
