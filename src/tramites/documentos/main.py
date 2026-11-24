"""Gestión documental: expediente electrónico del contribuyente.

Archiva la constancia de cada trámite y admite el sustento que el ciudadano adjunte.
Los archivos no se guardan en disco ni en la nube pública: viajan cifrados a la capa de
datos privada, igual que el resto de la información tributaria.
"""
import base64

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import LIMITE_BYTES, TIPO_DOC, _ahora, validar_adjunto
from ..common.security import usuario_actual

app = crear_app("documentos", "Gestión documental del expediente")

TRAMITES = {"rhe", "declaracion", "pago_a_cuenta", "fraccionamiento", "tramite_ruc", "otro"}


def _ficha(d: dict) -> dict:
    """Metadatos del documento, sin el contenido: el listado no mueve los archivos."""
    data = d["data"]
    return {
        "id": d["id"],
        "tramite": data["tramite"],
        "titulo": data["titulo"],
        "referencia": data.get("referencia", ""),
        "origen": data.get("origen", "constancia"),
        "nombre_archivo": data["nombre_archivo"],
        "tipo_mime": data["tipo_mime"],
        "tamano_bytes": data["tamano_bytes"],
        "archivado": data["archivado"],
    }


@app.get("/api/documentos")
def listar(tramite: str | None = None, u: dict = Depends(usuario_actual)):
    """Expediente del contribuyente, opcionalmente filtrado por trámite."""
    docs = datos.listar(TIPO_DOC, u["sub"], usuario=u["sub"])
    fichas = [_ficha(d) for d in docs]
    if tramite:
        fichas = [f for f in fichas if f["tramite"] == tramite]
    return sorted(fichas, key=lambda f: f["archivado"], reverse=True)


@app.get("/api/documentos/{doc_id}")
def descargar(doc_id: str, u: dict = Depends(usuario_actual)):
    """Entrega el archivo. Solo su titular puede descargarlo."""
    d = datos.obtener(doc_id, usuario=u["sub"])
    if d["tipo"] != TIPO_DOC or d["ruc"] != u["sub"]:
        raise HTTPException(404, "Documento no encontrado")   # no se revela su existencia a terceros
    data = d["data"]
    contenido = base64.b64decode(data["contenido_b64"])
    return Response(
        content=contenido,
        media_type=data["tipo_mime"],
        headers={"Content-Disposition": f'attachment; filename="{data["nombre_archivo"]}"',
                 "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/documentos/adjuntar", status_code=201)
async def adjuntar(tramite: str = Form(...), referencia: str = Form(""), titulo: str = Form(...),
                   archivo: UploadFile = File(...), u: dict = Depends(usuario_actual)):
    """Adjunta un sustento al expediente (PDF, PNG o JPG, hasta 2 MB)."""
    if tramite not in TRAMITES:
        raise HTTPException(422, f"Trámite no admitido. Use uno de: {', '.join(sorted(TRAMITES))}")
    contenido = await archivo.read(LIMITE_BYTES + 1)
    try:
        mime = validar_adjunto(archivo.filename or "", contenido)
    except ValueError as e:
        raise HTTPException(422, str(e))
    doc = {
        "tramite": tramite,
        "titulo": titulo[:120],
        "referencia": referencia[:60],
        "origen": "sustento",
        "nombre_archivo": (archivo.filename or "sustento")[:80],
        "tipo_mime": mime,
        "tamano_bytes": len(contenido),
        "archivado": _ahora(),
        "contenido_b64": base64.b64encode(contenido).decode(),
    }
    d = datos.crear(TIPO_DOC, u["sub"], doc, usuario=u["sub"])
    return _ficha({"id": d["id"], "data": doc})
