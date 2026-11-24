"""Capa de datos privada (nube privada / centro de datos).

- Único componente con acceso a la base de datos.
- Cifrado a nivel de campo con AES-256-GCM y rotación de claves (la primera cifra, todas descifran).
  En producción la clave maestra la custodia un KMS/HSM bajo control de la entidad.
- Autenticación de servicio por clave interna (en producción: mTLS + red privada).
- Bitácora de auditoría encadenada por hash (evidencia de integridad), con un único escritor a la vez.
"""
import base64
import hashlib
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, String, Text, create_engine, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ..common.app import crear_app
from ..common.config import settings
from ..common.security import hash_clave

SERVICIO = "datos-privados"


class Base(DeclarativeBase):
    pass


class Documento(Base):
    __tablename__ = "documentos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    ruc: Mapped[str] = mapped_column(String(11), index=True)
    payload: Mapped[str] = mapped_column(Text)  # JSON cifrado
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actualizado: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Auditoria(Base):
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40))
    origen: Mapped[str] = mapped_column(String(40))
    usuario: Mapped[str] = mapped_column(String(20))
    accion: Mapped[str] = mapped_column(String(20))
    recurso: Mapped[str] = mapped_column(String(80))
    hash_prev: Mapped[str] = mapped_column(String(64), unique=True)  # impide bifurcar la cadena
    hash: Mapped[str] = mapped_column(String(64))


_engine = None
_fernet: MultiFernet | None = None       # solo para leer documentos cifrados con la versión anterior
_claves_aes: list[bytes] | None = None
PREFIJO_AES = "v2$"                      # marca el formato AES-256-GCM
NONCE = 12


def engine():
    global _engine
    if _engine is None:
        url = settings.database_url
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
        _engine = create_engine(url, **kw)
        Base.metadata.create_all(_engine)
    return _engine


def reiniciar(url: str | None = None):
    """Uso en pruebas: reconstruye motor y claves."""
    global _engine, _fernet, _claves_aes
    _engine = None
    _fernet = None
    _claves_aes = None


def _claves() -> list[bytes]:
    """Claves de 256 bits. La primera cifra; todas se prueban al descifrar (rotación)."""
    global _claves_aes
    if _claves_aes is None:
        brutas = settings.kms_keys or [Fernet.generate_key().decode()]  # efímera si no hay KMS (solo desarrollo)
        claves = []
        for k in brutas:
            try:
                b = base64.urlsafe_b64decode(k)
            except Exception:
                raise RuntimeError("KMS_KEYS: cada clave debe venir en base64 urlsafe de 32 bytes")
            if len(b) != 32:
                raise RuntimeError(f"KMS_KEYS: se esperaban 32 bytes (256 bits) y llegaron {len(b)}")
            claves.append(b)
        _claves_aes = claves
    return _claves_aes


def cifrador() -> MultiFernet:
    """Descifrado de documentos escritos antes de la migración a AES-256."""
    global _fernet
    if _fernet is None:
        brutas = settings.kms_keys or [Fernet.generate_key().decode()]
        _fernet = MultiFernet([Fernet(k.encode()) for k in brutas])
    return _fernet


@asynccontextmanager
async def _ciclo_de_vida(_app):
    engine()
    if settings.seed_demo:
        sembrar_demo()
    yield


app = crear_app(SERVICIO, "Capa de datos privada", lifespan=_ciclo_de_vida)


def autorizar(x_internal_key: str = Header(default=""), x_origen: str = Header(default="?"),
              x_usuario: str = Header(default="-")) -> dict:
    if x_internal_key != settings.internal_key:
        raise HTTPException(403, "Servicio no autorizado")
    return {"origen": x_origen, "usuario": x_usuario}


CLAVE_BITACORA = 727110          # identificador del cerrojo consultivo de PostgreSQL


def _serializar_bitacora(db: Session) -> None:
    """Un solo escritor a la vez: dos réplicas que leyeran el mismo último hash
    bifurcarían la cadena y la bitácora dejaría de verificar. En PostgreSQL se toma
    un cerrojo consultivo que dura hasta el commit; en SQLite la escritura ya está
    serializada y el índice único de hash_prev actúa de red de seguridad."""
    if engine().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CLAVE_BITACORA})


def _transaccion(operacion, intentos: int = 5):
    """Ejecuta la operación en una transacción y reintenta si otro escritor se adelantó."""
    for intento in range(intentos):
        try:
            with Session(engine()) as db:
                _serializar_bitacora(db)
                resultado = operacion(db)
                db.commit()
                return resultado
        except (IntegrityError, OperationalError):
            if intento == intentos - 1:
                raise HTTPException(503, "No se pudo registrar en la bitácora de auditoría; reintente")
    raise HTTPException(503, "No se pudo registrar en la bitácora de auditoría; reintente")


def _auditar(db: Session, ctx: dict, accion: str, recurso: str) -> None:
    ultimo = db.execute(select(Auditoria).order_by(Auditoria.id.desc()).limit(1)).scalar_one_or_none()
    prev = ultimo.hash if ultimo else "0" * 64
    ts = datetime.now(timezone.utc).isoformat()
    h = hashlib.sha256(f"{prev}|{ts}|{ctx['origen']}|{ctx['usuario']}|{accion}|{recurso}".encode()).hexdigest()
    db.add(Auditoria(ts=ts, origen=ctx["origen"][:40], usuario=ctx["usuario"][:20], accion=accion,
                     recurso=recurso[:80], hash_prev=prev, hash=h))


def _descifrar(payload: str) -> dict:
    if not payload.startswith(PREFIJO_AES):
        return json.loads(cifrador().decrypt(payload.encode()).decode())   # formato anterior
    crudo = base64.urlsafe_b64decode(payload[len(PREFIJO_AES):])
    nonce, cifrado = crudo[:NONCE], crudo[NONCE:]
    for clave in _claves():
        try:
            return json.loads(AESGCM(clave).decrypt(nonce, cifrado, None).decode())
        except InvalidTag:
            continue
    raise HTTPException(500, "No se pudo descifrar: la clave no está disponible")


def _salida(d: Documento) -> dict:
    data = _descifrar(d.payload)
    return {"id": d.id, "tipo": d.tipo, "ruc": d.ruc, "creado": d.creado.isoformat(),
            "actualizado": d.actualizado.isoformat(), "data": data}


class DocIn(BaseModel):
    tipo: str
    ruc: str
    data: dict


class DocUpd(BaseModel):
    data: dict


def _cifrar(data: dict) -> str:
    nonce = os.urandom(NONCE)
    cifrado = AESGCM(_claves()[0]).encrypt(nonce, json.dumps(data, ensure_ascii=False).encode(), None)
    return PREFIJO_AES + base64.urlsafe_b64encode(nonce + cifrado).decode()


@app.post("/internal/docs")
def crear(body: DocIn, ctx: dict = Depends(autorizar)):
    def operacion(db: Session):
        ahora = datetime.now(timezone.utc)
        d = Documento(id=str(uuid.uuid4()), tipo=body.tipo, ruc=body.ruc,
                      payload=_cifrar(body.data), creado=ahora, actualizado=ahora)
        db.add(d)
        _auditar(db, ctx, "crear", f"{body.tipo}:{d.id}")
        db.flush()
        return _salida(d)
    return _transaccion(operacion)


@app.get("/internal/docs")
def listar(tipo: str, ruc: str | None = None, ctx: dict = Depends(autorizar)):
    def operacion(db: Session):
        q = select(Documento).where(Documento.tipo == tipo)
        if ruc:
            q = q.where(Documento.ruc == ruc)
        docs = db.execute(q.order_by(Documento.creado)).scalars().all()
        _auditar(db, ctx, "listar", f"{tipo}:{ruc or '*'}")
        return [_salida(d) for d in docs]
    return _transaccion(operacion)


@app.get("/internal/docs/{doc_id}")
def obtener(doc_id: str, ctx: dict = Depends(autorizar)):
    def operacion(db: Session):
        d = db.get(Documento, doc_id)
        if not d:
            raise HTTPException(404, "No encontrado")
        _auditar(db, ctx, "leer", f"{d.tipo}:{d.id}")
        return _salida(d)
    return _transaccion(operacion)


@app.put("/internal/docs/{doc_id}")
def actualizar(doc_id: str, body: DocUpd, ctx: dict = Depends(autorizar)):
    def operacion(db: Session):
        d = db.get(Documento, doc_id)
        if not d:
            raise HTTPException(404, "No encontrado")
        d.payload = _cifrar(body.data)
        d.actualizado = datetime.now(timezone.utc)
        _auditar(db, ctx, "actualizar", f"{d.tipo}:{d.id}")
        db.flush()
        return _salida(d)
    return _transaccion(operacion)


@app.get("/internal/auditoria/verificar")
def verificar_cadena(ctx: dict = Depends(autorizar)):
    """Recalcula la cadena de hashes; detecta alteraciones en la bitácora."""
    with Session(engine()) as db:
        filas = db.execute(select(Auditoria).order_by(Auditoria.id)).scalars().all()
    prev = "0" * 64
    for f in filas:
        esperado = hashlib.sha256(f"{prev}|{f.ts}|{f.origen}|{f.usuario}|{f.accion}|{f.recurso}".encode()).hexdigest()
        if f.hash_prev != prev or f.hash != esperado:
            return {"integra": False, "primer_error": f.id, "registros": len(filas)}
        prev = f.hash
    return {"integra": True, "registros": len(filas)}


# Datos de demostración (solo con SEED_DEMO=1) --------------------------------
DEMO_RUC = "10123456789"
DEMO_TOTP = "JBSWY3DPEHPK3PXP"


def sembrar_demo():
    with Session(engine()) as db:
        existe = db.execute(select(Documento).where(Documento.tipo == "usuario", Documento.ruc == DEMO_RUC)).first()
    if existe:
        return
    ctx = {"origen": "seed", "usuario": "-"}
    for tipo, data in [
        ("usuario", {"usuario": "PSICOLOGA1", "clave_hash": hash_clave("Demo#2026"), "totp_secret": DEMO_TOTP}),
        ("contribuyente", {"razon_social": "Mariana Quispe Rojas", "domicilio": "Av. Los Fresnos 123, Lima",
                           "actividad": "Servicios de psicología", "regimen": "Renta de cuarta categoría",
                           "suspension_retenciones": False}),
    ]:
        crear(DocIn(tipo=tipo, ruc=DEMO_RUC, data=data), ctx)


