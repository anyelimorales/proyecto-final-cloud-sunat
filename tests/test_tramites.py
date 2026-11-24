from datetime import date

import pyotp
from fastapi.testclient import TestClient

from tramites.datos import main as datos_main

RUC = datos_main.DEMO_RUC


def test_login_requiere_mfa_y_bloquea(datos_app):
    from tramites.auth.main import app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"ruc": RUC, "usuario": "X", "clave": "mala"}).status_code == 401
    ok = c.post("/api/auth/login", json={"ruc": RUC, "usuario": "PSICOLOGA1", "clave": "Demo#2026"})
    assert ok.status_code == 200 and "access_token" not in ok.json()  # primer factor no basta
    assert c.post("/api/auth/mfa", json={"mfa_token": ok.json()["mfa_token"], "codigo": "000000"}).status_code == 401


def test_endpoints_protegidos_sin_token(datos_app):
    from tramites.rhe.main import app
    assert TestClient(app).get("/api/rhe").status_code == 401
    assert TestClient(app).get("/api/rhe", headers={"Authorization": "Bearer falso"}).status_code == 401


def test_token_mfa_no_sirve_como_acceso(datos_app):
    from tramites.common.security import emitir_token
    from tramites.rhe.main import app
    t = emitir_token(RUC, tipo="mfa")
    assert TestClient(app).get("/api/rhe", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_ficha_y_cambio_regimen(auth):
    from tramites.ruc.main import app
    c = TestClient(app)
    assert c.get("/api/ruc/ficha", headers=auth).json()["regimen"] == "Renta de cuarta categoría"
    assert c.put("/api/ruc/ficha", json={"domicilio": "Jr. Nuevo 456, Lima"}, headers=auth).json()["domicilio"] == "Jr. Nuevo 456, Lima"
    assert c.post("/api/ruc/cambio-regimen", json={"regimen": "Inventado"}, headers=auth).status_code == 422
    assert c.post("/api/ruc/cambio-regimen", json={"regimen": "Nuevo RUS"}, headers=auth).status_code == 200
    c.post("/api/ruc/cambio-regimen", json={"regimen": "Renta de cuarta categoría"}, headers=auth)


def test_rhe_emision_retencion_y_anulacion(auth):
    from tramites.rhe.main import app
    c = TestClient(app)
    base = {"cliente_ruc": "20100070970", "cliente_nombre": "Clínica Demo SAC", "descripcion": "Sesiones de terapia"}
    r1 = c.post("/api/rhe", json={**base, "monto_bruto": 1000}, headers=auth)
    assert r1.status_code == 201 and r1.json()["retencion"] == 0  # bajo el umbral
    r2 = c.post("/api/rhe", json={**base, "monto_bruto": 2000}, headers=auth).json()
    assert r2["retencion"] == 160.0 and r2["monto_neto"] == 1840.0 and r2["numero"] == "E001-2"
    assert c.post(f"/api/rhe/{r2['id']}/anular", json={"motivo": "Error en el monto"}, headers=auth).json()["estado"] == "anulado"
    assert c.post(f"/api/rhe/{r2['id']}/anular", json={"motivo": "Otra vez"}, headers=auth).status_code == 409
    assert len(c.get("/api/rhe", headers=auth).json()) == 2


def test_rhe_ajeno_no_visible(datos_app, auth):
    """Un contribuyente no puede anular el recibo de otro (se responde 404, sin revelar existencia)."""
    from tramites.common import datos
    from tramites.common.security import emitir_token
    from tramites.rhe.main import app
    ajeno = datos.crear("rhe", "10999999999", {"estado": "emitido"})
    t = emitir_token(RUC)
    r = TestClient(app).post(f"/api/rhe/{ajeno['id']}/anular", json={"motivo": "intento de acceso"}, headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 404


def test_declaracion_calculo():
    from tramites.declaraciones.main import Insumos, calcular
    # UIT 5 500: ingresos 60 000 -> deducción 20 % = 12 000; neta 48 000; menos 7 UIT (38 500) = 9 500 base
    r = calcular(Insumos(ingresos_cuarta=60000))
    assert r["deduccion_20pct_cuarta"] == 12000 and r["base_imponible"] == 9500
    # 5 UIT = 27 500 al 8 % si la base fuese mayor; aquí base 9 500 al 8 % = 760
    assert r["impuesto_determinado"] == 760 and r["saldo_a_pagar"] == 760
    r2 = calcular(Insumos(ingresos_cuarta=60000, retenciones=1000))
    assert r2["saldo_a_favor"] == 240 and r2["saldo_a_pagar"] == 0
    assert calcular(Insumos(ingresos_cuarta=20000))["impuesto_determinado"] == 0  # bajo el mínimo no imponible


def test_declaracion_escala_progresiva():
    from tramites.declaraciones.main import impuesto_escala
    uit = 5500
    assert round(impuesto_escala(5 * uit, uit), 2) == round(5 * uit * 0.08, 2)
    esperado = 5 * uit * 0.08 + 5 * uit * 0.14
    assert round(impuesto_escala(10 * uit, uit), 2) == round(esperado, 2)


def test_presentar_y_rectificar(auth):
    from tramites.declaraciones.main import app
    c = TestClient(app)
    assert c.post("/api/declaraciones/rectificar", json={"ejercicio": 2025, "ingresos_cuarta": 1}, headers=auth).status_code == 404
    r = c.post("/api/declaraciones", json={"ejercicio": 2025, "ingresos_cuarta": 80000}, headers=auth)
    assert r.status_code == 201 and r.json()["tipo"] == "original"
    assert c.post("/api/declaraciones", json={"ejercicio": 2025, "ingresos_cuarta": 80000}, headers=auth).status_code == 409
    rect = c.post("/api/declaraciones/rectificar", json={"ejercicio": 2025, "ingresos_cuarta": 70000}, headers=auth).json()
    assert rect["version"] == 2 and rect["tipo"] == "rectificatoria"


def test_calendario_publico_y_digito():
    from tramites.alertas.main import app
    c = TestClient(app)
    r = c.get("/api/alertas/calendario/9").json()
    assert r["digito"] == 9 and any("anual" in v["obligacion"].lower() for v in r["vencimientos"])
    assert c.get("/api/alertas/calendario/10").status_code == 422


def test_suscripcion_y_despachador(auth):
    from tramites.alertas.main import app
    from tramites.alertas import dispatcher
    c = TestClient(app)
    assert c.put("/api/alertas/suscripcion", json={"canales": ["fax"]}, headers=auth).status_code == 422
    assert c.put("/api/alertas/suscripcion", json={"canales": ["correo", "whatsapp"], "anticipacion_dias": 15}, headers=auth).status_code == 200
    # Día 10 del mes: el vencimiento mensual del dígito 9 es el 21 -> 11 días restantes (dentro de 15)
    enviados = dispatcher.ejecutar(date(2026, 6, 10))
    assert {e["canal"] for e in enviados} == {"correo", "whatsapp"}
    assert all("*" in e["ruc"] for e in enviados)  # el RUC se enmascara en logs


def test_simulador():
    from tramites.simulador.main import app
    c = TestClient(app)
    r = c.post("/api/simulador/multa", json={"tributo_omitido": 1000, "dias_retraso": 30, "subsanacion": "ninguna"}).json()
    assert r["multa_sin_rebaja"] == 2750 and r["multa_con_rebaja"] == 2750
    r2 = c.post("/api/simulador/multa", json={"tributo_omitido": 1000, "dias_retraso": 30}).json()
    assert r2["multa_con_rebaja"] == 275 and r2["ahorro_por_subsanar_ahora"] == 2475
    assert r2["total_estimado"] < r["total_estimado"]
    assert c.post("/api/simulador/multa", json={"dias_retraso": 1, "infraccion": "x"}).status_code == 422


def test_fraccionamiento(auth):
    from tramites.fraccionamiento.main import app
    c = TestClient(app)
    s = c.post("/api/fraccionamiento/simular", json={"deuda": 6000, "cuotas": 12}).json()
    assert s["cronograma"][-1]["saldo"] == 0 and abs(s["cuota_mensual"] * 12 - s["total_a_pagar"]) < 0.2
    assert c.post("/api/fraccionamiento/simular", json={"deuda": 150, "cuotas": 12}).status_code == 422
    assert c.post("/api/fraccionamiento/solicitar", json={"deuda": 6000, "cuotas": 12}).status_code == 401
    r = c.post("/api/fraccionamiento/solicitar", json={"deuda": 6000, "cuotas": 12}, headers=auth)
    assert r.status_code == 201 and r.json()["estado"] == "en evaluación"


def test_datos_privados_cifrado_auditoria_y_acceso(datos_app):
    from sqlalchemy import text
    # 1. Sin clave de servicio no hay acceso
    assert datos_app.get("/internal/docs", params={"tipo": "rhe"}).status_code == 403
    # 2. En disco el contenido está cifrado (no aparece texto plano)
    with datos_main.engine().connect() as cn:
        filas = cn.execute(text("select payload from documentos")).scalars().all()
    assert filas and all("Clínica" not in f and "Demo#2026" not in f and "totp" not in f for f in filas)
    # 3. La bitácora es íntegra y detecta manipulación
    h = {"X-Internal-Key": "clave-de-prueba"}
    assert datos_app.get("/internal/auditoria/verificar", headers=h).json()["integra"] is True
    with datos_main.engine().begin() as cn:
        cn.execute(text("update auditoria set accion='borrar' where id=2"))
    assert datos_app.get("/internal/auditoria/verificar", headers=h).json()["integra"] is False


def test_salud_y_metricas(datos_app):
    from tramites.simulador.main import app
    c = TestClient(app)
    assert c.get("/health").json()["estado"] == "ok"
    assert "http_requests_total" in c.get("/metrics").text
    assert c.get("/health").headers["x-content-type-options"] == "nosniff"


# ---- Trámite 4: pagos a cuenta mensuales -----------------------------------
def _cliente_pagos():
    from tramites.pagos.main import app as pagos_app
    return TestClient(pagos_app)


def test_pago_a_cuenta_usa_los_recibos_del_periodo(datos_app, auth):
    from tramites.rhe.main import app as rhe_app
    rhe = TestClient(rhe_app)
    # Dos recibos del mismo mes: 4 000 + 2 000 = 6 000 brutos, con 8 % retenido en cada uno
    for monto in (4000, 2000):
        r = rhe.post("/api/rhe", headers=auth, json={"cliente_ruc": "20100070970", "cliente_nombre": "Entidad",
                     "descripcion": "Servicio profesional", "monto_bruto": monto, "fecha": "2026-03-15"})
        assert r.status_code == 201, r.text
    r = _cliente_pagos().get("/api/pagos/periodo/2026-03", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["recibos_considerados"] == 2
    assert d["ingresos_del_periodo"] == 6000
    assert d["pago_a_cuenta_bruto"] == 480          # 8 % de 6 000
    assert d["retenciones_del_periodo"] == 480      # ya retenido por los clientes
    assert d["importe_a_pagar"] == 0                # la retención cubre el pago a cuenta
    assert d["obligado"] is True


def test_pago_a_cuenta_exonerado_bajo_el_umbral(datos_app, auth):
    d = _cliente_pagos().get("/api/pagos/periodo/2026-07", headers=auth).json()
    assert d["ingresos_del_periodo"] == 0
    assert d["obligado"] is False
    assert d["importe_a_pagar"] == 0
    assert "umbral" in d["motivo_exoneracion"]


def test_pago_a_cuenta_no_se_presenta_dos_veces(datos_app, auth):
    c = _cliente_pagos()
    assert c.post("/api/pagos", headers=auth, json={"periodo": "2026-03"}).status_code == 201
    assert c.post("/api/pagos", headers=auth, json={"periodo": "2026-03"}).status_code == 409
    assert any(p["periodo"] == "2026-03" for p in c.get("/api/pagos", headers=auth).json())


def test_pago_a_cuenta_exige_token_y_periodo_valido(datos_app, auth):
    c = _cliente_pagos()
    assert c.get("/api/pagos/periodo/2026-03").status_code == 401
    assert c.get("/api/pagos/periodo/2026-13", headers=auth).status_code == 422


# ---- Capa de datos: cifrado AES-256 y bitácora bajo concurrencia -----------
def test_cifrado_aes256_y_rotacion_de_claves(datos_app):
    import base64, os
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tramites.datos import main as dm
    with Session(dm.engine()) as db:
        fila = db.execute(select(dm.Documento).where(dm.Documento.tipo == "contribuyente")).scalars().first()
    assert fila.payload.startswith("v2$")                 # AES-256-GCM
    assert "Mariana" not in fila.payload                  # el texto plano no toca el disco
    assert len(dm._claves()[0]) == 32                     # 256 bits
    original = dm._claves_aes
    try:                                                  # una clave nueva al frente no impide leer lo anterior
        dm._claves_aes = [base64.urlsafe_b64decode(base64.urlsafe_b64encode(os.urandom(32)))] + original
        assert dm._descifrar(fila.payload)["razon_social"].startswith("Mariana")
    finally:
        dm._claves_aes = original


def test_la_bitacora_resiste_escrituras_concurrentes(datos_app):
    """Con varias réplicas escribiendo a la vez, la cadena de hashes no debe bifurcarse.
    (Otra prueba altera la bitácora a propósito, así que aquí se revisa el tramo nuevo
    y la unicidad de los enlaces, no la verificación global.)"""
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tramites.datos import main as dm

    with ThreadPoolExecutor(max_workers=8) as ex:
        codigos = list(ex.map(lambda i: datos_app.post("/internal/docs", headers={"X-Internal-Key": "clave-de-prueba"},
                       json={"tipo": "prueba_concurrencia", "ruc": "10123456789", "data": {"n": i}}).status_code, range(30)))
    assert all(c == 200 for c in codigos), codigos

    with Session(dm.engine()) as db:
        filas = db.execute(select(dm.Auditoria).order_by(dm.Auditoria.id)).scalars().all()
    enlaces = [f.hash_prev for f in filas]
    assert len(enlaces) == len(set(enlaces)), "dos registros apuntan al mismo anterior: la cadena se bifurcó"
    recientes = filas[-30:]
    for anterior, actual in zip(recientes, recientes[1:]):
        assert actual.hash_prev == anterior.hash, f"eslabón roto en el registro {actual.id}"
