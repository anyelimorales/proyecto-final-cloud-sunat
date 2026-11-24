"""Identidad y acceso: hash de claves, JWT y dependencia de autorización."""
import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

_bearer = HTTPBearer(auto_error=False)


def hash_clave(clave: str, sal: bytes | None = None) -> str:
    sal = sal or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, 310_000)
    return f"pbkdf2${sal.hex()}${h.hex()}"


def verificar_clave(clave: str, almacenado: str) -> bool:
    try:
        _, sal, h = almacenado.split("$")
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), 310_000).hex()
    return hmac.compare_digest(calc, h)


def emitir_token(ruc: str, rol: str = "contribuyente", tipo: str = "acceso", minutos: int | None = None) -> str:
    ahora = int(time.time())
    minutos = minutos if minutos is not None else settings.jwt_minutos
    claims = {"sub": ruc, "rol": rol, "tipo": tipo, "iat": ahora, "exp": ahora + minutos * 60}
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def decodificar(token: str, tipo: str = "acceso") -> dict:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Token inválido o expirado")
    if claims.get("tipo") != tipo:
        raise HTTPException(401, "Tipo de token no permitido")
    return claims


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """Dependencia FastAPI: exige un token de acceso emitido tras autenticación multifactor."""
    if cred is None:
        raise HTTPException(401, "Autenticación requerida")
    return decodificar(cred.credentials)
