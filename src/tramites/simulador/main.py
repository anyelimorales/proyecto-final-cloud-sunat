"""Trámite 6: simulador de multas, intereses y rebajas por subsanación. Servicio público, sin datos personales."""
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..common.app import crear_app
from ..common.parametros import parametros

app = crear_app("simulador", "Simulador de multas e intereses")


class Consulta(BaseModel):
    infraccion: str = "no_presentar_declaracion"
    tributo_omitido: float = Field(default=0, ge=0)
    dias_retraso: int = Field(ge=0, le=3650)
    subsanacion: str = "voluntaria_antes_de_notificacion"


def interes_moratorio(monto: float, dias: int) -> float:
    tim_diaria = parametros()["interes"]["tim_mensual"] / 30
    return monto * ((1 + tim_diaria) ** dias - 1)


@app.get("/api/simulador/infracciones")
def infracciones():
    p = parametros()
    return {"infracciones": p["multas"], "subsanaciones": list(p["gradualidad"].keys()), "aviso": p["_aviso"]}


@app.post("/api/simulador/multa")
def simular(c: Consulta):
    p = parametros()
    if c.infraccion not in p["multas"]:
        raise HTTPException(422, "Infracción no admitida")
    if c.subsanacion not in p["gradualidad"]:
        raise HTTPException(422, "Tipo de subsanación no válido")
    m = p["multas"][c.infraccion]
    base = m["porcentaje_uit"] * p["uit"] if "porcentaje_uit" in m else m["porcentaje_tributo_omitido"] * c.tributo_omitido
    rebaja_pct = p["gradualidad"][c.subsanacion]
    multa_final = base * (1 - rebaja_pct)
    int_tributo = interes_moratorio(c.tributo_omitido, c.dias_retraso)
    int_multa = interes_moratorio(multa_final, c.dias_retraso)
    total = c.tributo_omitido + int_tributo + multa_final + int_multa
    return {
        "infraccion": m["descripcion"], "multa_sin_rebaja": round(base, 2), "rebaja_aplicada": rebaja_pct,
        "multa_con_rebaja": round(multa_final, 2), "tributo_omitido": round(c.tributo_omitido, 2),
        "interes_sobre_tributo": round(int_tributo, 2), "interes_sobre_multa": round(int_multa, 2),
        "total_estimado": round(total, 2),
        "ahorro_por_subsanar_ahora": round(base - multa_final, 2) if rebaja_pct else 0.0,
        "aviso": p["_aviso"],
    }
