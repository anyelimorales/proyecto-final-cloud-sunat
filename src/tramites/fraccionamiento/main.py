"""Trámite 7: simulación y solicitud de fraccionamiento (cuotas con amortización francesa)."""
from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import archivar, notificar
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("fraccionamiento", "Aplazamiento y fraccionamiento")


class Plan(BaseModel):
    deuda: float = Field(gt=0, le=100_000_000)
    cuotas: int = Field(ge=2, le=72)


def simular(deuda: float, cuotas: int) -> dict:
    p = parametros()["fraccionamiento"]
    if not p["cuotas_min"] <= cuotas <= p["cuotas_max"]:
        raise HTTPException(422, f"Las cuotas deben estar entre {p['cuotas_min']} y {p['cuotas_max']}")
    i = p["tasa_mensual"]
    cuota = deuda / cuotas if i == 0 else deuda * i / (1 - (1 + i) ** -cuotas)
    if cuota < p["cuota_minima"]:
        raise HTTPException(422, f"La cuota resultante (S/ {cuota:.2f}) es menor que el mínimo de S/ {p['cuota_minima']}")
    saldo, cronograma = deuda, []
    for n in range(1, cuotas + 1):
        interes = saldo * i
        amort = cuota - interes
        saldo = max(saldo - amort, 0)
        cronograma.append({"n": n, "cuota": round(cuota, 2), "interes": round(interes, 2),
                           "amortizacion": round(amort, 2), "saldo": round(saldo, 2)})
    return {"deuda": round(deuda, 2), "cuotas": cuotas, "tasa_mensual": i, "cuota_mensual": round(cuota, 2),
            "total_a_pagar": round(cuota * cuotas, 2), "total_intereses": round(cuota * cuotas - deuda, 2),
            "cronograma": cronograma}


@app.post("/api/fraccionamiento/simular")
def endpoint_simular(body: Plan):
    return simular(body.deuda, body.cuotas)


@app.post("/api/fraccionamiento/solicitar", status_code=201)
def solicitar(body: Plan, u: dict = Depends(usuario_actual)):
    plan = simular(body.deuda, body.cuotas)
    doc = {"estado": "en evaluación", "solicitada": date.today().isoformat(),
           **{k: plan[k] for k in ("deuda", "cuotas", "cuota_mensual", "total_a_pagar", "total_intereses")}}
    d = datos.crear("fraccionamiento", u["sub"], doc, usuario=u["sub"])
    referencia = f'F-{d["id"][:8].upper()}'
    archivo = archivar(u["sub"], "fraccionamiento", "Constancia de solicitud de fraccionamiento", [
        ("Número de solicitud", referencia), ("Fecha", doc["solicitada"]),
        ("Deuda acogida", f'S/ {doc["deuda"]:,.2f}'), ("Número de cuotas", doc["cuotas"]),
        ("Cuota mensual", f'S/ {doc["cuota_mensual"]:,.2f}'),
        ("Total a pagar", f'S/ {doc["total_a_pagar"]:,.2f}'),
        ("Estado", doc["estado"]),
    ], referencia, usuario=u["sub"])
    notificar(u["sub"], "Solicitud de fraccionamiento registrada",
              f'Su solicitud {referencia} por S/ {doc["deuda"]:,.2f} en {doc["cuotas"]} cuotas '
              f'quedó {doc["estado"]}.', "fraccionamiento", referencia, usuario=u["sub"])
    return {"id": d["id"], "numero_solicitud": referencia, "documento_id": archivo["id"], **doc}


@app.get("/api/fraccionamiento")
def listar(u: dict = Depends(usuario_actual)):
    return [{"id": d["id"], **d["data"]} for d in datos.listar("fraccionamiento", u["sub"], usuario=u["sub"])]
