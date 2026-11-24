"""Contraseñas (PBKDF2, solo librería estándar) y usuario en sesión."""
import hashlib
import hmac
import secrets

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .db import Usuario

ITERACIONES = 260_000


def hashear(clave: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), ITERACIONES).hex()
    return f"pbkdf2${ITERACIONES}${sal}${h}"


def verificar(clave: str, guardada: str) -> bool:
    try:
        _, it, sal, h = guardada.split("$")
        prueba = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), int(it)).hex()
        return hmac.compare_digest(prueba, h)
    except ValueError:
        return False


def usuario_actual(request: Request, db: Session) -> Usuario | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    u = db.get(Usuario, uid)
    if not u or not u.activo:
        request.session.pop("uid", None)
        return None
    return u


def rol_inicial(db: Session, email: str) -> str:
    """
    Quién nace administrador:
    - si REYBASAR_ADMINS tiene correos, solo esos;
    - si está vacío, el PRIMER usuario que se registra (para arrancar).
    Después, un admin da de alta a otros desde Admin > Usuarios.
    """
    lista = {e.strip().lower() for e in config.ADMINS.split(",") if e.strip()}
    if lista:
        return "admin" if email.lower() in lista else "cliente"
    hay_admin = db.scalar(select(func.count()).select_from(Usuario).where(Usuario.rol == "admin"))
    return "cliente" if hay_admin else "admin"
