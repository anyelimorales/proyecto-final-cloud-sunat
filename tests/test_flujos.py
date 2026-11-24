"""Flujos extremo a extremo de los trámites, paso por paso.

Cada prueba recorre las cinco etapas del caso —identidad, borde, nube pública,
nube privada y notificación— y comprueba que ninguna quede sin rastro en la
bitácora de auditoría. El flujo de referencia es la emisión de un recibo por
honorarios; los demás trámites siguen el mismo patrón.
"""
from datetime import date

import pyotp
import pytest
from fastapi.testclient import TestClient

from tramites.common.expediente import TIPO_DOC, TIPO_NOTIF
from tramites.datos import main as datos_main

CLAVE_INTERNA = {"X-Internal-Key": "clave-de-prueba"}


# --------------------------------------------------------------------- utilidades
def _registros_auditoria(datos_app) -> int:
    return datos_app.get("/internal/auditoria/verificar", headers=CLAVE_INTERNA).json()["registros"]


def _cliente(modulo):
    return TestClient(modulo)


def _alta_contribuyente(ruc: str, usuario: str, clave: str) -> dict:
    """Crea un contribuyente propio y devuelve su cabecera de autorización.

    Los flujos usan su propio titular para no alterar los datos del contribuyente
    de demostración, del que dependen otras pruebas.
    """
    from tramites.auth.main import app as auth_app
    from tramites.common import datos as capa
    capa.crear("usuario", ruc, {"usuario": usuario.upper(), "clave_hash": datos_main.hash_clave(clave),
                                "totp_secret": datos_main.DEMO_TOTP, "intentos": 0}, usuario="sistema")
    capa.crear("contribuyente", ruc, {"razon_social": f"Titular {ruc}", "regimen": "Rentas de cuarta categoría",
                                      "suspension_retenciones": False}, usuario="sistema")
    c = TestClient(auth_app)
    r = c.post("/api/auth/login", json={"ruc": ruc, "usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    r = c.post("/api/auth/mfa", json={"mfa_token": r.json()["mfa_token"],
                                      "codigo": pyotp.TOTP(datos_main.DEMO_TOTP).now()})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def titular(datos_app):
    return _alta_contribuyente("10555555555", "titular1", "Flujo#2026")


@pytest.fixture
def documentos(datos_app):
    from tramites.documentos.main import app
    return TestClient(app)


@pytest.fixture
def notificaciones(datos_app):
    from tramites.alertas.main import app
    return TestClient(app)


# ============================================================ flujo de referencia
def test_flujo_emitir_recibo_por_honorarios(datos_app, titular, documentos, notificaciones):
    """Paso 1 identidad · 2 borde · 3 nube pública · 4 nube privada · 5 notificación."""
    from tramites.rhe.main import app as rhe_app
    rhe = TestClient(rhe_app)

    # --- Paso 1: identidad. Sin credencial válida el trámite no empieza.
    assert rhe.post("/api/rhe", json={"cliente_ruc": "20100070970", "cliente_nombre": "Entidad",
                                      "descripcion": "Servicio", "monto_bruto": 1000}).status_code == 401
    assert rhe.post("/api/rhe", headers={"Authorization": "Bearer falsificado"},
                    json={"cliente_ruc": "20100070970", "cliente_nombre": "Entidad",
                          "descripcion": "Servicio", "monto_bruto": 1000}).status_code == 401

    # --- Paso 2: borde. Las validaciones de entrada rechazan lo que no cumple el contrato.
    for cuerpo in ({"cliente_ruc": "123", "cliente_nombre": "X", "descripcion": "Servicio", "monto_bruto": 1000},
                   {"cliente_ruc": "20100070970", "cliente_nombre": "Entidad", "descripcion": "Servicio", "monto_bruto": -5}):
        assert rhe.post("/api/rhe", headers=titular, json=cuerpo).status_code == 422

    antes = _registros_auditoria(datos_app)

    # --- Paso 3: nube pública. El microservicio valida y calcula; no toca la base de datos.
    r = rhe.post("/api/rhe", headers=titular, json={"cliente_ruc": "20512333456",
                 "cliente_nombre": "Clínica San Borja SAC", "descripcion": "Evaluación psicológica",
                 "monto_bruto": 2500, "fecha": date.today().isoformat()})
    assert r.status_code == 201, r.text
    recibo = r.json()
    assert recibo["retencion"] == 200.0                      # 8 % de 2 500
    assert recibo["monto_neto"] == 2300.0
    assert recibo["estado"] == "emitido"

    # --- Paso 4: nube privada. El recibo se guarda y su constancia va a la gestión documental.
    expediente = documentos.get("/api/documentos?tramite=rhe", headers=titular).json()
    constancia = next(d for d in expediente if d["referencia"] == recibo["numero"])
    assert constancia["id"] == recibo["documento_id"]
    assert constancia["tipo_mime"] == "application/pdf" and constancia["tamano_bytes"] > 0

    descarga = documentos.get(f"/api/documentos/{constancia['id']}", headers=titular)
    assert descarga.status_code == 200
    assert descarga.content.startswith(b"%PDF")              # es un PDF de verdad
    assert "attachment" in descarga.headers["content-disposition"]

    # El contenido nunca se guarda en claro: en la base está cifrado con AES-256.
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    with Session(datos_main.engine()) as db:
        fila = db.execute(select(datos_main.Documento).where(
            datos_main.Documento.tipo == TIPO_DOC)).scalars().first()
    assert fila.payload.startswith("v2$") and "%PDF" not in fila.payload

    # --- Paso 5: notificación. Queda una confirmación dirigida al contribuyente.
    bandeja = notificaciones.get("/api/alertas/notificaciones", headers=titular).json()
    aviso = next(n for n in bandeja if n["referencia"] == recibo["numero"])
    assert aviso["tramite"] == "rhe" and aviso["leida"] is False
    assert recibo["numero"] in aviso["asunto"]

    # El despachador la entrega y no la repite en una segunda pasada.
    from tramites.alertas import dispatcher
    assert any(e["referencia"] == recibo["numero"] for e in dispatcher.entregar_pendientes())
    assert not any(e["referencia"] == recibo["numero"] for e in dispatcher.entregar_pendientes())

    marcada = notificaciones.post(f"/api/alertas/notificaciones/{aviso['id']}/leida", headers=titular)
    assert marcada.status_code == 200 and marcada.json()["leida"] is True

    # --- Transversal: cada paso dejó rastro en la bitácora y la cadena sigue enlazada.
    assert _registros_auditoria(datos_app) > antes
    with Session(datos_main.engine()) as db:
        filas = db.execute(select(datos_main.Auditoria).order_by(datos_main.Auditoria.id)).scalars().all()
    recientes = filas[-12:]
    for anterior, actual in zip(recientes, recientes[1:]):
        assert actual.hash_prev == anterior.hash
    # El recurso identifica qué se tocó: el recibo, su constancia y la notificación.
    recursos = [f.recurso for f in filas]
    assert any(r.startswith("rhe:") for r in recursos)
    assert any(r.startswith(f"{TIPO_DOC}:") for r in recursos)
    assert any(r.startswith(f"{TIPO_NOTIF}:") for r in recursos)


# ============================================================ mismos pasos, otros trámites
def test_flujo_pago_a_cuenta(datos_app, titular, documentos, notificaciones):
    from tramites.pagos.main import app
    pagos = TestClient(app)
    periodo = date.today().strftime("%Y-%m")

    assert pagos.get(f"/api/pagos/periodo/{periodo}").status_code == 401          # identidad
    assert pagos.get("/api/pagos/periodo/2026-13", headers=titular).status_code == 422  # borde

    det = pagos.get(f"/api/pagos/periodo/{periodo}", headers=titular).json()          # nube pública
    assert det["ingresos_del_periodo"] >= 2500 and det["recibos_considerados"] >= 1

    r = pagos.post("/api/pagos", headers=titular, json={"periodo": periodo})
    assert r.status_code == 201, r.text
    presentado = r.json()
    assert pagos.post("/api/pagos", headers=titular, json={"periodo": periodo}).status_code == 409  # idempotente

    doc = documentos.get(f"/api/documentos/{presentado['documento_id']}", headers=titular)  # nube privada
    assert doc.status_code == 200 and doc.content.startswith(b"%PDF")

    bandeja = notificaciones.get("/api/alertas/notificaciones", headers=titular).json()      # notificación
    assert any(n["referencia"] == presentado["numero_orden"] for n in bandeja)


def test_flujo_declaracion_anual(datos_app, titular, documentos, notificaciones):
    from tramites.declaraciones.main import app
    dec = TestClient(app)
    insumos = {"ejercicio": 2025, "ingresos_cuarta": 92000, "ingresos_quinta": 0, "retenciones": 4200}

    assert dec.post("/api/declaraciones", json=insumos).status_code == 401
    r = dec.post("/api/declaraciones", headers=titular, json=insumos)
    assert r.status_code == 201, r.text
    original = r.json()
    assert dec.post("/api/declaraciones", headers=titular, json=insumos).status_code == 409

    rect = dec.post("/api/declaraciones/rectificar", headers=titular, json={**insumos, "retenciones": 5000})
    assert rect.status_code == 201 and rect.json()["version"] == 2

    for orden in (original["numero_orden"], rect.json()["numero_orden"]):
        assert any(d["referencia"] == orden for d in documentos.get("/api/documentos", headers=titular).json())
        assert any(n["referencia"] == orden for n in notificaciones.get("/api/alertas/notificaciones", headers=titular).json())


def test_flujo_fraccionamiento(datos_app, titular, documentos, notificaciones):
    from tramites.fraccionamiento.main import app
    fr = TestClient(app)
    assert fr.post("/api/fraccionamiento/solicitar", json={"deuda": 6000, "cuotas": 12}).status_code == 401
    r = fr.post("/api/fraccionamiento/solicitar", headers=titular, json={"deuda": 8400, "cuotas": 12})
    assert r.status_code == 201, r.text
    sol = r.json()
    doc = documentos.get(f"/api/documentos/{sol['documento_id']}", headers=titular)
    assert doc.status_code == 200 and doc.content.startswith(b"%PDF")
    assert any(n["referencia"] == sol["numero_solicitud"]
               for n in notificaciones.get("/api/alertas/notificaciones", headers=titular).json())


def test_flujo_cambio_de_regimen(datos_app, titular, documentos):
    from tramites.ruc.main import app
    ruc = TestClient(app)
    regimenes = list(ruc.get("/api/ruc/regimenes").json())
    r = ruc.post("/api/ruc/cambio-regimen", headers=titular, json={"regimen": regimenes[-1]})
    assert r.status_code == 200, r.text
    assert documentos.get(f"/api/documentos/{r.json()['documento_id']}", headers=titular).status_code == 200


# ============================================================ gestión documental
def test_expediente_admite_sustentos_y_rechaza_lo_que_no_debe(datos_app, titular, documentos):
    pdf = b"%PDF-1.4\n% sustento de prueba\n"
    r = documentos.post("/api/documentos/adjuntar", headers=titular,
                        data={"tramite": "fraccionamiento", "referencia": "F-PRUEBA", "titulo": "Boleta de pago"},
                        files={"archivo": ("boleta.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    assert r.json()["origen"] == "sustento"
    assert documentos.get(f"/api/documentos/{r.json()['id']}", headers=titular).content == pdf

    # Un ejecutable disfrazado de PDF no entra: se valida la firma binaria, no la extensión.
    malo = documentos.post("/api/documentos/adjuntar", headers=titular,
                           data={"tramite": "fraccionamiento", "titulo": "Falso"},
                           files={"archivo": ("virus.pdf", b"MZ\x90\x00ejecutable", "application/pdf")})
    assert malo.status_code == 422 and "PDF" in malo.json()["detail"]

    grande = documentos.post("/api/documentos/adjuntar", headers=titular,
                             data={"tramite": "fraccionamiento", "titulo": "Enorme"},
                             files={"archivo": ("grande.pdf", b"%PDF" + b"0" * (2 * 1024 * 1024), "application/pdf")})
    assert grande.status_code == 422 and "límite" in grande.json()["detail"]

    assert documentos.post("/api/documentos/adjuntar", headers=titular,
                           data={"tramite": "inventado", "titulo": "X"},
                           files={"archivo": ("a.pdf", pdf, "application/pdf")}).status_code == 422


def test_el_expediente_es_privado_de_su_titular(datos_app, titular, documentos):
    """Otro contribuyente autenticado no puede leer documentos ajenos."""
    cabecera_ajena = _alta_contribuyente("10999999999", "otro1", "Otra#2026")
    mios = documentos.get("/api/documentos", headers=titular).json()
    assert mios, "el titular debería tener documentos archivados"
    assert documentos.get("/api/documentos", headers=cabecera_ajena).json() == []
    assert documentos.get(f"/api/documentos/{mios[0]['id']}", headers=cabecera_ajena).status_code == 404
