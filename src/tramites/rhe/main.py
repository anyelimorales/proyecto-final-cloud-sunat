"""Trámite 2: recibos por honorarios electrónicos (emisión, anulación, consulta)."""
from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import archivar, notificar
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("rhe", "Recibos por honorarios electrónicos")


class Emision(BaseModel):
    cliente_ruc: str = Field(pattern=r"^\d{11}$")
    cliente_nombre: str = Field(min_length=2, max_length=120)
    descripcion: str = Field(min_length=3, max_length=200)
    monto_bruto: float = Field(gt=0, le=10_000_000)
    fecha: date | None = None


class Anulacion(BaseModel):
    motivo: str = Field(min_length=5, max_length=200)


def calcular_retencion(monto: float, suspension: bool) -> float:
    p = parametros()["renta_cuarta"]
    if suspension or monto <= p["umbral_retencion_rhe"]:
        return 0.0
    return round(monto * p["tasa_retencion"], 2)


@app.post("/api/rhe", status_code=201)
def emitir(body: Emision, u: dict = Depends(usuario_actual)):
    ruc = u["sub"]
    ficha = datos.listar("contribuyente", ruc, usuario=ruc)
    suspension = bool(ficha and ficha[0]["data"].get("suspension_retenciones"))
    previos = datos.listar("rhe", ruc, usuario=ruc)
    correlativo = len(previos) + 1
    retencion = calcular_retencion(body.monto_bruto, suspension)
    rhe = {
        "numero": f"E001-{correlativo}",
        "fecha": (body.fecha or date.today()).isoformat(),
        "cliente_ruc": body.cliente_ruc, "cliente_nombre": body.cliente_nombre, "descripcion": body.descripcion,
        "monto_bruto": round(body.monto_bruto, 2), "retencion": retencion,
        "monto_neto": round(body.monto_bruto - retencion, 2), "estado": "emitido",
    }
    d = datos.crear("rhe", ruc, rhe, usuario=ruc)
    # El recibo va a la gestión documental y el contribuyente recibe la confirmación.
    doc = archivar(ruc, "rhe", "Constancia de recibo por honorarios", [
        ("Número", rhe["numero"]), ("Fecha de emisión", rhe["fecha"]),
        ("Cliente", f'{rhe["cliente_nombre"]} (RUC {rhe["cliente_ruc"]})'),
        ("Descripción", rhe["descripcion"]),
        ("Monto bruto", f'S/ {rhe["monto_bruto"]:,.2f}'),
        ("Retención de cuarta", f'S/ {rhe["retencion"]:,.2f}'),
        ("Monto neto", f'S/ {rhe["monto_neto"]:,.2f}'),
    ], rhe["numero"], usuario=ruc)
    notificar(ruc, f'Recibo {rhe["numero"]} emitido',
              f'Se emitió el recibo {rhe["numero"]} por S/ {rhe["monto_bruto"]:,.2f}. '
              f'La constancia está disponible en su expediente.', "rhe", rhe["numero"], usuario=ruc)
    return {"id": d["id"], "documento_id": doc["id"], **rhe}


@app.get("/api/rhe")
def listar(u: dict = Depends(usuario_actual)):
    return [{"id": d["id"], **d["data"]} for d in datos.listar("rhe", u["sub"], usuario=u["sub"])]


@app.post("/api/rhe/{rhe_id}/anular")
def anular(rhe_id: str, body: Anulacion, u: dict = Depends(usuario_actual)):
    d = datos.obtener(rhe_id, usuario=u["sub"])
    if d["ruc"] != u["sub"] or d["tipo"] != "rhe":
        raise HTTPException(404, "Recibo no encontrado")  # no se revela existencia a terceros
    if d["data"]["estado"] == "anulado":
        raise HTTPException(409, "El recibo ya está anulado")
    nuevo = {**d["data"], "estado": "anulado", "motivo_anulacion": body.motivo}
    datos.actualizar(rhe_id, nuevo, usuario=u["sub"])
    archivar(u["sub"], "rhe", "Constancia de anulación de recibo", [
        ("Número", nuevo["numero"]), ("Fecha de emisión", nuevo["fecha"]),
        ("Motivo de anulación", body.motivo),
    ], f'{nuevo["numero"]}-anulado', usuario=u["sub"])
    notificar(u["sub"], f'Recibo {nuevo["numero"]} anulado',
              f'Se anuló el recibo {nuevo["numero"]}. Motivo: {body.motivo}.',
              "rhe", nuevo["numero"], usuario=u["sub"])
    return {"id": rhe_id, **nuevo}
