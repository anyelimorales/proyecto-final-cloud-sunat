"""Cliente hacia la capa de datos privada (el 'enlace híbrido').
Los servicios de la nube pública nunca acceden a la base de datos: solo a esta API interna."""
import httpx
from fastapi import HTTPException

from .config import settings

_client: httpx.Client | None = None
ORIGEN = "desconocido"


def set_client(client: httpx.Client | None) -> None:
    """Permite inyectar un cliente (pruebas)."""
    global _client
    _client = client


def set_origen(nombre: str) -> None:
    global ORIGEN
    ORIGEN = nombre


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(base_url=settings.datos_url, timeout=5.0)
    return _client


def _headers(usuario: str | None) -> dict:
    h = {"X-Internal-Key": settings.internal_key, "X-Origen": ORIGEN}
    if usuario:
        h["X-Usuario"] = usuario
    return h


def _manejar(resp: httpx.Response):
    if resp.status_code == 404:
        raise HTTPException(404, "Recurso no encontrado")
    if resp.status_code >= 400:
        raise HTTPException(502, "Error en la capa de datos privada")
    return resp.json()


def _llamar(metodo: str, url: str, usuario: str | None, **kw):
    try:
        return _manejar(_http().request(metodo, url, headers=_headers(usuario), **kw))
    except httpx.HTTPError:
        raise HTTPException(503, "Capa de datos privada no disponible")


def crear(tipo: str, ruc: str, data: dict, usuario: str | None = None) -> dict:
    return _llamar("POST", "/internal/docs", usuario, json={"tipo": tipo, "ruc": ruc, "data": data})


def listar(tipo: str, ruc: str | None = None, usuario: str | None = None) -> list[dict]:
    params = {"tipo": tipo}
    if ruc:
        params["ruc"] = ruc
    return _llamar("GET", "/internal/docs", usuario, params=params)


def obtener(doc_id: str, usuario: str | None = None) -> dict:
    return _llamar("GET", f"/internal/docs/{doc_id}", usuario)


def actualizar(doc_id: str, data: dict, usuario: str | None = None) -> dict:
    return _llamar("PUT", f"/internal/docs/{doc_id}", usuario, json={"data": data})
