"""Trámite 5: calendario de vencimientos personalizado y suscripción a alertas multicanal."""
from datetime import date, timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import datos
from ..common.app import crear_app
from ..common.expediente import TIPO_NOTIF
from ..common.parametros import parametros
from ..common.security import usuario_actual

app = crear_app("alertas", "Calendario y alertas de vencimiento")

CANALES = {"correo", "sms", "whatsapp"}


class Suscripcion(BaseModel):
    canales: list[str] = Field(min_length=1)
    anticipacion_dias: int = Field(default=3, ge=1, le=15)
    contacto: dict[str, str] = Field(default_factory=dict, description="Ej.: {'correo': 'a@b.pe'}")


def calendario(digito: int, anio: int) -> list[dict]:
    p = parametros()["cronograma_ilustrativo"]
    dia = p["dia_vencimiento_mensual"][str(digito)]
    items = [{"obligacion": "Pago a cuenta mensual (renta de cuarta categoría)", "periodo": f"{anio}-{m:02d}",
              "vence": date(anio, m, dia).isoformat()} for m in range(1, 13)]
    a = p["declaracion_anual"]
    inicio = date(anio, a["mes_inicio"], a["dia_base"])
    items.append({"obligacion": "Declaración anual de renta (ejercicio anterior)", "periodo": str(anio - 1),
                  "vence": (inicio + timedelta(days=30 + a["dias_extra_por_digito"] * digito)).isoformat()})
    return sorted(items, key=lambda x: x["vence"])


def _con_estado(items: list[dict], hoy: date) -> list[dict]:
    out = []
    for it in items:
        dias = (date.fromisoformat(it["vence"]) - hoy).days
        estado = "vencido" if dias < 0 else "urgente" if dias <= 3 else "proximo" if dias <= 15 else "programado"
        out.append({**it, "dias_restantes": dias, "estado": estado})
    return out


@app.get("/api/alertas/calendario/{digito}")
def calendario_publico(digito: int, anio: int | None = None):
    """Información pública (nivel 'Público'): no requiere autenticación ni datos personales."""
    if not 0 <= digito <= 9:
        raise HTTPException(422, "El dígito debe estar entre 0 y 9")
    if anio is not None and not 1 <= anio <= 9999:
        raise HTTPException(422, "El año debe estar entre 1 y 9999")
    anio = anio or parametros()["ejercicio"]
    return {"aviso": parametros()["cronograma_ilustrativo"]["_aviso"], "digito": digito,
            "vencimientos": _con_estado(calendario(digito, anio), date.today())}


@app.get("/api/alertas/mis-vencimientos")
def mis_vencimientos(u: dict = Depends(usuario_actual)):
    digito = int(u["sub"][-1])
    todos = _con_estado(calendario(digito, date.today().year), date.today())
    return {"digito": digito, "vencimientos": [x for x in todos if x["dias_restantes"] >= -15]}


@app.put("/api/alertas/suscripcion")
def suscribir(body: Suscripcion, u: dict = Depends(usuario_actual)):
    invalidos = set(body.canales) - CANALES
    if invalidos:
        raise HTTPException(422, f"Canales no válidos: {sorted(invalidos)}")
    existentes = datos.listar("suscripcion", u["sub"], usuario=u["sub"])
    data = body.model_dump()
    if existentes:
        datos.actualizar(existentes[0]["id"], data, usuario=u["sub"])
    else:
        datos.crear("suscripcion", u["sub"], data, usuario=u["sub"])
    return data


@app.get("/api/alertas/suscripcion")
def ver_suscripcion(u: dict = Depends(usuario_actual)):
    s = datos.listar("suscripcion", u["sub"], usuario=u["sub"])
    return s[0]["data"] if s else None


# ---- Bandeja de notificaciones del contribuyente -----------------------------
# El paso de "notificar" de cada trámite deja aquí una confirmación persistente;
# el despachador la entrega además por el canal suscrito.
def _vista_notificacion(d: dict) -> dict:
    return {"id": d["id"], **d["data"]}


@app.get("/api/alertas/notificaciones")
def notificaciones(solo_no_leidas: bool = False, u: dict = Depends(usuario_actual)):
    items = [_vista_notificacion(d) for d in datos.listar(TIPO_NOTIF, u["sub"], usuario=u["sub"])]
    if solo_no_leidas:
        items = [n for n in items if not n["leida"]]
    return sorted(items, key=lambda n: n["creada"], reverse=True)


@app.post("/api/alertas/notificaciones/{notif_id}/leida")
def marcar_leida(notif_id: str, u: dict = Depends(usuario_actual)):
    d = datos.obtener(notif_id, usuario=u["sub"])
    if d["tipo"] != TIPO_NOTIF or d["ruc"] != u["sub"]:
        raise HTTPException(404, "Notificación no encontrada")
    nuevo = {**d["data"], "leida": True}
    datos.actualizar(notif_id, nuevo, usuario=u["sub"])
    return {"id": notif_id, **nuevo}
