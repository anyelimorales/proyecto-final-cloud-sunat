"""Despachador de alertas (CronJob). Recorre las suscripciones y 'envía' avisos.
En producción el envío usa el servicio gestionado de notificaciones (correo/SMS/mensajería);
aquí se registra en el log para poder demostrar el flujo sin proveedores externos."""
import json
from datetime import date

from ..common import datos
from ..common.expediente import TIPO_NOTIF
from .main import _con_estado, calendario


def entregar_pendientes() -> list[dict]:
    """Entrega las confirmaciones de trámite que dejó el paso de notificación.

    Se recorren una sola vez: al entregarlas se marcan, de modo que un segundo pase
    del CronJob no vuelva a enviar lo mismo.
    """
    datos.set_origen("alertas-dispatcher")
    entregadas = []
    for n in datos.listar(TIPO_NOTIF):
        cfg = n["data"]
        if cfg.get("entregada"):
            continue
        aviso = {"ruc": n["ruc"][:2] + "*******" + n["ruc"][-2:], "canal": "bandeja",
                 "asunto": cfg["asunto"], "tramite": cfg["tramite"], "referencia": cfg.get("referencia", "")}
        print(json.dumps({"evento": "notificacion_entregada", **aviso}, ensure_ascii=False))
        datos.actualizar(n["id"], {**cfg, "entregada": True})
        entregadas.append(aviso)
    return entregadas


def ejecutar(hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    enviados = []
    datos.set_origen("alertas-dispatcher")
    for s in datos.listar("suscripcion"):
        cfg = s["data"]
        digito = int(s["ruc"][-1])
        for it in _con_estado(calendario(digito, hoy.year), hoy):
            if 0 <= it["dias_restantes"] <= cfg["anticipacion_dias"]:
                for canal in cfg["canales"]:
                    aviso = {"ruc": s["ruc"][:2] + "*******" + s["ruc"][-2:], "canal": canal,
                             "obligacion": it["obligacion"], "vence": it["vence"], "dias": it["dias_restantes"]}
                    print(json.dumps({"evento": "alerta_enviada", **aviso}, ensure_ascii=False))
                    enviados.append(aviso)
    return enviados


if __name__ == "__main__":
    ejecutar()            # avisos de vencimiento próximos
    entregar_pendientes()  # confirmaciones de trámite aún no entregadas
