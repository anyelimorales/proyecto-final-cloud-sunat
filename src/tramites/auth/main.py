"""Identidad: inicio de sesión (RUC + usuario + clave, simulando Clave SOL) y segundo factor TOTP."""
import time
from collections import defaultdict

import pyotp
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.security import decodificar, emitir_token, verificar_clave

app = crear_app("auth", "Servicio de identidad")

MAX_INTENTOS = 5
BLOQUEO_SEG = 300
_fallos: dict[str, list[float]] = defaultdict(list)


class Login(BaseModel):
    ruc: str = Field(pattern=r"^\d{11}$")
    usuario: str
    clave: str


class Mfa(BaseModel):
    mfa_token: str
    codigo: str = Field(pattern=r"^\d{6}$")


def _bloqueado(ruc: str) -> bool:
    ahora = time.time()
    _fallos[ruc] = [t for t in _fallos[ruc] if ahora - t < BLOQUEO_SEG]
    return len(_fallos[ruc]) >= MAX_INTENTOS


@app.post("/api/auth/login")
def login(body: Login):
    if _bloqueado(body.ruc):
        raise HTTPException(429, "Cuenta bloqueada temporalmente por intentos fallidos")
    usuarios = datos.listar("usuario", body.ruc)
    u = usuarios[0]["data"] if usuarios else None
    if not u or u["usuario"] != body.usuario.upper() or not verificar_clave(body.clave, u["clave_hash"]):
        _fallos[body.ruc].append(time.time())
        raise HTTPException(401, "Credenciales inválidas")
    # Primer factor correcto: se emite un token de corta vida que solo sirve para el segundo factor.
    return {"mfa_token": emitir_token(body.ruc, tipo="mfa", minutos=5), "mensaje": "Ingrese el código de su aplicación autenticadora"}


@app.post("/api/auth/mfa")
def mfa(body: Mfa):
    claims = decodificar(body.mfa_token, tipo="mfa")
    ruc = claims["sub"]
    if _bloqueado(ruc):
        raise HTTPException(429, "Cuenta bloqueada temporalmente por intentos fallidos")
    usuarios = datos.listar("usuario", ruc)
    if not usuarios or not pyotp.TOTP(usuarios[0]["data"]["totp_secret"]).verify(body.codigo, valid_window=1):
        _fallos[ruc].append(time.time())
        raise HTTPException(401, "Código de verificación inválido")
    return {"access_token": emitir_token(ruc), "token_type": "bearer", "ruc": ruc}
