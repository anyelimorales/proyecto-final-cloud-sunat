"""Trámite 4: pagos a cuenta mensuales de la renta de cuarta categoría.

El importe se calcula sobre los ingresos del periodo: el servicio toma los recibos por
honorarios ya emitidos por el contribuyente, de modo que la cifra no se escribe a mano.
Quien tenga suspensión de retenciones o no supere el umbral mensual no está obligado.
"""
from datetime import date

from fastapi import Depends, HTTPException, Path
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import archivar, notificar
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("pagos", "Pagos a cuenta mensuales")

PERIODO = r"^\d{4}-(0[1-9]|1[0-2])$"


class Periodo(BaseModel):
    periodo: str = Field(pattern=PERIODO, description="Mes del pago a cuenta, en formato AAAA-MM")


def _ingresos_del_periodo(ruc: str, periodo: str) -> tuple[float, float, int]:
    """Suma los recibos emitidos (no anulados) cuya fecha cae en el periodo."""
    recibos = [r["data"] for r in datos.listar("rhe", ruc, usuario=ruc)]
    del_mes = [r for r in recibos if r["estado"] == "emitido" and r["fecha"].startswith(periodo)]
    bruto = round(sum(r["monto_bruto"] for r in del_mes), 2)
    retenido = round(sum(r["retencion"] for r in del_mes), 2)
    return bruto, retenido, len(del_mes)


def calcular(ingresos: float, retenciones: float, suspension: bool) -> dict:
    p = parametros()["pago_a_cuenta"]
    umbral = p["umbral_mensual"]
    if suspension:
        motivo = "Tiene suspensión de retenciones y pagos a cuenta vigente"
    elif ingresos <= umbral:
        motivo = f"Los ingresos del mes no superan el umbral de S/ {umbral:,.2f}"
    else:
        motivo = None
    bruto = 0.0 if motivo else round(ingresos * p["tasa"], 2)
    importe = round(max(bruto - retenciones, 0), 2)
    return {
        "ingresos_del_periodo": round(ingresos, 2),
        "tasa": p["tasa"],
        "umbral_mensual": umbral,
        "pago_a_cuenta_bruto": bruto,
        "retenciones_del_periodo": round(retenciones, 2),
        "importe_a_pagar": importe,
        "obligado": motivo is None,
        "motivo_exoneracion": motivo,
        "aviso": p["_aviso"],
    }


def _resolver(ruc: str, periodo: str) -> dict:
    ingresos, retenciones, n = _ingresos_del_periodo(ruc, periodo)
    ficha = datos.listar("contribuyente", ruc, usuario=ruc)
    suspension = bool(ficha and ficha[0]["data"].get("suspension_retenciones"))
    return {"periodo": periodo, "recibos_considerados": n, **calcular(ingresos, retenciones, suspension)}


@app.get("/api/pagos/periodo/{periodo}")
def ver_periodo(periodo: str = Path(pattern=PERIODO, description="AAAA-MM"),
                u: dict = Depends(usuario_actual)):
    """Determinación del periodo a partir de los recibos ya emitidos."""
    return _resolver(u["sub"], periodo)


@app.post("/api/pagos", status_code=201)
def presentar(body: Periodo, u: dict = Depends(usuario_actual)):
    ruc = u["sub"]
    previos = [d for d in datos.listar("pago_a_cuenta", ruc, usuario=ruc) if d["data"]["periodo"] == body.periodo]
    if previos:
        raise HTTPException(409, "Ya presentó el pago a cuenta de ese periodo")
    det = _resolver(ruc, body.periodo)
    doc = {**det, "presentado": date.today().isoformat(),
           "estado": "presentado" if det["obligado"] else "sin importe que pagar"}
    d = datos.crear("pago_a_cuenta", ruc, doc, usuario=ruc)
    orden = f"P-{body.periodo}-{d['id'][:8].upper()}"
    archivo = archivar(ruc, "pago_a_cuenta", "Constancia de pago a cuenta mensual", [
        ("Número de orden", orden), ("Periodo", body.periodo),
        ("Ingresos del periodo", f'S/ {det["ingresos_del_periodo"]:,.2f}'),
        ("Retenciones efectuadas", f'S/ {det["retenciones_del_periodo"]:,.2f}'),
        ("Importe a pagar", f'S/ {det["importe_a_pagar"]:,.2f}'),
        ("Estado", doc["estado"]),
    ], orden, usuario=ruc)
    notificar(ruc, f"Pago a cuenta de {body.periodo} presentado",
              f'Se registró el pago a cuenta del periodo {body.periodo} por '
              f'S/ {det["importe_a_pagar"]:,.2f}. Orden {orden}.',
              "pago_a_cuenta", orden, usuario=ruc)
    return {"id": d["id"], "numero_orden": orden, "documento_id": archivo["id"], **doc}


@app.get("/api/pagos")
def listar(u: dict = Depends(usuario_actual)):
    return [{"id": d["id"], **d["data"]} for d in datos.listar("pago_a_cuenta", u["sub"], usuario=u["sub"])]
