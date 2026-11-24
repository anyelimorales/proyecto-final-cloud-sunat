"""Fábrica de aplicaciones: salud, métricas Prometheus, encabezados de seguridad y registro JSON."""
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from . import datos

SOLICITUDES = Counter("http_requests_total", "Solicitudes HTTP", ["servicio", "metodo", "ruta", "estado"])
LATENCIA = Histogram("http_request_seconds", "Latencia HTTP", ["servicio", "ruta"])


class _Json(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        base = {"ts": self.formatTime(r), "nivel": r.levelname, "msg": r.getMessage()}
        base.update(getattr(r, "extra", {}))
        return json.dumps(base, ensure_ascii=False)


def _logger(nombre: str) -> logging.Logger:
    log = logging.getLogger(nombre)
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(_Json())
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log


def crear_app(nombre: str, titulo: str, lifespan=None) -> FastAPI:
    app = FastAPI(title=titulo, docs_url="/docs", redoc_url=None, lifespan=lifespan)
    datos.set_origen(nombre)
    log = _logger(nombre)

    @app.middleware("http")
    async def instrumentar(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        t0 = time.perf_counter()
        resp: Response = await call_next(request)
        dt = time.perf_counter() - t0
        ruta = request.scope.get("route").path if request.scope.get("route") else request.url.path
        SOLICITUDES.labels(nombre, request.method, ruta, resp.status_code).inc()
        LATENCIA.labels(nombre, ruta).observe(dt)
        resp.headers["X-Request-ID"] = rid
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "no-store"
        if ruta not in ("/health", "/metrics"):
            log.info("solicitud", extra={"extra": {"id": rid, "metodo": request.method, "ruta": ruta,
                                                  "estado": resp.status_code, "ms": round(dt * 1000, 1)}})
        return resp

    @app.get("/health", include_in_schema=False)
    def health():
        return {"servicio": nombre, "estado": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
