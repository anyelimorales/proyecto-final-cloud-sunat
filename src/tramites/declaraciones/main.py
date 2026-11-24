"""Trámites 3 y 4: declaración anual de renta (cuarta y quinta) con cálculo guiado y rectificatorias."""
from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import archivar, notificar
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("declaraciones", "Declaración anual de renta")


class Insumos(BaseModel):
    ejercicio: int = Field(default=2026, ge=2015, le=2100)
    ingresos_cuarta: float = Field(default=0, ge=0)
    ingresos_quinta: float = Field(default=0, ge=0)
    gastos_deducibles: float = Field(default=0, ge=0, description="Gastos ya reducidos al porcentaje deducible")
    retenciones: float = Field(default=0, ge=0)
    pagos_a_cuenta: float = Field(default=0, ge=0)
    saldo_favor_anterior: float = Field(default=0, ge=0)


def impuesto_escala(base: float, uit: float) -> float:
    total, anterior = 0.0, 0.0
    for tramo in parametros()["escala_progresiva"]:
        limite = tramo["hasta_uit"] * uit if tramo["hasta_uit"] is not None else float("inf")
        if base > anterior:
            total += (min(base, limite) - anterior) * tramo["tasa"]
        anterior = limite
    return total


def calcular(i: Insumos) -> dict:
    p = parametros()
    uit = p["uit"]
    rc = p["renta_cuarta"]
    deduccion_cuarta = min(i.ingresos_cuarta * rc["deduccion_porcentaje"], rc["deduccion_tope_uit"] * uit)
    neta_cuarta = i.ingresos_cuarta - deduccion_cuarta
    neta_trabajo = neta_cuarta + i.ingresos_quinta
    deduccion_7uit = min(neta_trabajo, p["deduccion_fija_uit"] * uit)
    gastos = min(i.gastos_deducibles, p["gastos_deducibles_tope_uit"] * uit, max(neta_trabajo - deduccion_7uit, 0))
    base = max(neta_trabajo - deduccion_7uit - gastos, 0)
    impuesto = impuesto_escala(base, uit)
    creditos = i.retenciones + i.pagos_a_cuenta + i.saldo_favor_anterior
    saldo = round(impuesto - creditos, 2)
    return {
        "ejercicio": i.ejercicio, "uit": uit,
        "renta_bruta_cuarta": round(i.ingresos_cuarta, 2), "deduccion_20pct_cuarta": round(deduccion_cuarta, 2),
        "renta_neta_cuarta": round(neta_cuarta, 2), "renta_quinta": round(i.ingresos_quinta, 2),
        "deduccion_7_uit": round(deduccion_7uit, 2), "gastos_deducibles_aplicados": round(gastos, 2),
        "base_imponible": round(base, 2), "impuesto_determinado": round(impuesto, 2),
        "creditos_aplicados": round(creditos, 2),
        "saldo_a_pagar": max(saldo, 0.0), "saldo_a_favor": max(-saldo, 0.0),
        "aviso": p["_aviso"],
    }


def _archivar_declaracion(ruc: str, orden: str, doc: dict) -> dict:
    """Deja la constancia en el expediente y avisa al contribuyente."""
    r = doc["resultado"]
    archivo = archivar(ruc, "declaracion", f'Constancia de declaración anual ({doc["tipo"]})', [
        ("Número de orden", orden), ("Ejercicio", doc["ejercicio"]),
        ("Tipo", f'{doc["tipo"]} (versión {doc["version"]})'),
        ("Fecha de presentación", doc["presentada"]),
        ("Base imponible", f'S/ {r["base_imponible"]:,.2f}'),
        ("Impuesto determinado", f'S/ {r["impuesto_determinado"]:,.2f}'),
        ("Créditos aplicados", f'S/ {r["creditos_aplicados"]:,.2f}'),
        ("Saldo a pagar", f'S/ {r["saldo_a_pagar"]:,.2f}'),
        ("Saldo a favor", f'S/ {r["saldo_a_favor"]:,.2f}'),
    ], orden, usuario=ruc)
    notificar(ruc, f'Declaración anual {doc["ejercicio"]} presentada',
              f'Se registró la declaración {doc["tipo"]} del ejercicio {doc["ejercicio"]}. '
              f'Orden {orden}. Saldo a pagar: S/ {r["saldo_a_pagar"]:,.2f}.',
              "declaracion", orden, usuario=ruc)
    return archivo


@app.post("/api/declaraciones/calcular")
def endpoint_calcular(body: Insumos, u: dict = Depends(usuario_actual)):
    return calcular(body)


@app.post("/api/declaraciones", status_code=201)
def presentar(body: Insumos, u: dict = Depends(usuario_actual)):
    ruc = u["sub"]
    previas = [d for d in datos.listar("declaracion", ruc, usuario=ruc) if d["data"]["ejercicio"] == body.ejercicio and d["data"]["tipo"] == "original"]
    if previas:
        raise HTTPException(409, "Ya existe una declaración original para el ejercicio; presente una rectificatoria")
    doc = {"tipo": "original", "version": 1, "ejercicio": body.ejercicio, "presentada": date.today().isoformat(),
           "insumos": body.model_dump(), "resultado": calcular(body)}
    d = datos.crear("declaracion", ruc, doc, usuario=ruc)
    orden = f"D-{body.ejercicio}-{d['id'][:8].upper()}"
    archivo = _archivar_declaracion(ruc, orden, doc)
    return {"id": d["id"], "numero_orden": orden, "documento_id": archivo["id"], **doc}


@app.post("/api/declaraciones/rectificar", status_code=201)
def rectificar(body: Insumos, u: dict = Depends(usuario_actual)):
    ruc = u["sub"]
    del_ejercicio = [d for d in datos.listar("declaracion", ruc, usuario=ruc) if d["data"]["ejercicio"] == body.ejercicio]
    if not del_ejercicio:
        raise HTTPException(404, "No existe declaración original para rectificar")
    version = max(d["data"]["version"] for d in del_ejercicio) + 1
    doc = {"tipo": "rectificatoria", "version": version, "ejercicio": body.ejercicio, "presentada": date.today().isoformat(),
           "insumos": body.model_dump(), "resultado": calcular(body)}
    d = datos.crear("declaracion", ruc, doc, usuario=ruc)
    orden = f"D-{body.ejercicio}-{d['id'][:8].upper()}"
    archivo = _archivar_declaracion(ruc, orden, doc)
    return {"id": d["id"], "numero_orden": orden, "documento_id": archivo["id"], **doc}


@app.get("/api/declaraciones")
def listar(u: dict = Depends(usuario_actual)):
    return [{"id": d["id"], **d["data"]} for d in datos.listar("declaracion", u["sub"], usuario=u["sub"])]
