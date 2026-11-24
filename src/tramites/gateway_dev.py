"""Puerta de enlace SOLO PARA DESARROLLO LOCAL sin Docker (en despliegue real se usa nginx, ver portal/nginx.conf).
Sirve el portal estático y enruta /api/* hacia cada microservicio."""
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

PUERTOS = {"auth": 8101, "ruc": 8102, "rhe": 8103, "declaraciones": 8104, "alertas": 8105, "simulador": 8106, "fraccionamiento": 8107, "pagos": 8108, "documentos": 8109}
RUTAS = {"/api/auth": "auth", "/api/ruc": "ruc", "/api/rhe": "rhe", "/api/declaraciones": "declaraciones",
         "/api/alertas": "alertas", "/api/simulador": "simulador", "/api/fraccionamiento": "fraccionamiento",
         "/api/pagos": "pagos", "/api/documentos": "documentos"}
app = FastAPI(docs_url=None)
cliente = httpx.AsyncClient(timeout=15)


@app.api_route("/api/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(ruta: str, request: Request):
    path = "/api/" + ruta
    for prefijo, nombre in RUTAS.items():
        if path.startswith(prefijo):
            url = os.environ.get(f"URL_{nombre.upper()}", f"http://127.0.0.1:{PUERTOS[nombre]}") + path
            r = await cliente.request(request.method, url, content=await request.body(), params=request.query_params,
                                      headers={k: v for k, v in request.headers.items() if k.lower() in ("authorization", "content-type")})
            return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))
    return Response('{"detail":"Ruta no encontrada"}', 404, media_type="application/json")


CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def cabeceras(request: Request, call_next):
    r = await call_next(request)
    r.headers["Content-Security-Policy"] = CSP
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r


app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "portal" / "static"), html=True), name="portal")
