"""Trámite 1: ficha RUC, actualización de datos y cambio de régimen."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import archivar, notificar
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("ruc", "Inscripción y actualización del RUC")


class Actualizacion(BaseModel):
    domicilio: str | None = Field(default=None, min_length=5, max_length=200)
    actividad: str | None = Field(default=None, min_length=3, max_length=120)
    suspension_retenciones: bool | None = None


class CambioRegimen(BaseModel):
    regimen: str


def _ficha(ruc: str) -> dict:
    docs = datos.listar("contribuyente", ruc, usuario=ruc)
    if not docs:
        raise HTTPException(404, "El contribuyente no tiene ficha RUC")
    return docs[0]


@app.get("/api/ruc/ficha")
def ficha(u: dict = Depends(usuario_actual)):
    d = _ficha(u["sub"])
    return {"ruc": u["sub"], **d["data"], "actualizado": d["actualizado"]}


@app.put("/api/ruc/ficha")
def actualizar(body: Actualizacion, u: dict = Depends(usuario_actual)):
    d = _ficha(u["sub"])
    nuevo = {**d["data"], **body.model_dump(exclude_none=True)}
    r = datos.actualizar(d["id"], nuevo, usuario=u["sub"])
    return {"ruc": u["sub"], **r["data"]}


@app.get("/api/ruc/regimenes")
def regimenes():
    return parametros()["regimenes"]


@app.post("/api/ruc/cambio-regimen")
def cambio_regimen(body: CambioRegimen, u: dict = Depends(usuario_actual)):
    if body.regimen not in parametros()["regimenes"]:
        raise HTTPException(422, "Régimen no válido")
    d = _ficha(u["sub"])
    nuevo = {**d["data"], "regimen": body.regimen}
    datos.actualizar(d["id"], nuevo, usuario=u["sub"])
    t = datos.crear("tramite_ruc", u["sub"], {"tipo": "cambio_regimen", "de": d["data"].get("regimen"), "a": body.regimen}, usuario=u["sub"])
    referencia = f'R-{t["id"][:8].upper()}'
    archivo = archivar(u["sub"], "tramite_ruc", "Constancia de cambio de régimen", [
        ("Número de trámite", referencia),
        ("Régimen anterior", d["data"].get("regimen", "no registrado")),
        ("Régimen nuevo", body.regimen),
    ], referencia, usuario=u["sub"])
    notificar(u["sub"], "Cambio de régimen registrado",
              f'Su régimen cambió a {body.regimen}. Trámite {referencia}.',
              "tramite_ruc", referencia, usuario=u["sub"])
    return {"mensaje": "Cambio de régimen registrado", "regimen": body.regimen,
            "numero_tramite": referencia, "documento_id": archivo["id"]}
