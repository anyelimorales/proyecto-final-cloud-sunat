"""Prueba de humo de extremo a extremo contra el portal desplegado (Docker Compose o Kubernetes).
Uso: python scripts/e2e.py [URL_BASE]    (por defecto http://localhost:8080)"""
import sys
import httpx
import pyotp

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
RUC, USUARIO, CLAVE, TOTP = "10123456789", "PSICOLOGA1", "Demo#2026", "JBSWY3DPEHPK3PXP"
c = httpx.Client(base_url=BASE, timeout=15)
fallos = 0


def ok(cond, msg):
    global fallos
    print(("OK   " if cond else "FALLA"), msg)
    fallos += 0 if cond else 1


ok(c.get("/").status_code == 200, "El portal sirve la página principal")
h = c.get("/").headers
ok("content-security-policy" in h, "Encabezado CSP presente")
ok(c.get("/api/alertas/calendario/9").status_code == 200, "Calendario público")
ok(c.post("/api/simulador/multa", json={"tributo_omitido": 1000, "dias_retraso": 30}).status_code == 200, "Simulador de multas")
ok(c.get("/api/rhe").status_code == 401, "Los endpoints protegidos exigen token")
r = c.post("/api/auth/login", json={"ruc": RUC, "usuario": USUARIO, "clave": CLAVE})
ok(r.status_code == 200, "Primer factor")
r = c.post("/api/auth/mfa", json={"mfa_token": r.json()["mfa_token"], "codigo": pyotp.TOTP(TOTP).now()})
ok(r.status_code == 200, "Segundo factor (TOTP)")
H = {"Authorization": f"Bearer {r.json()['access_token']}"}
ok(c.get("/api/ruc/ficha", headers=H).status_code == 200, "Ficha RUC (lee la capa de datos privada)")
r = c.post("/api/rhe", headers=H, json={"cliente_ruc": "20100070970", "cliente_nombre": "Cliente E2E", "descripcion": "Prueba", "monto_bruto": 2500})
ok(r.status_code == 201 and r.json()["retencion"] == 200.0, "Emisión de RHE con retención del 8 %")
r = c.post("/api/declaraciones/calcular", headers=H, json={"ingresos_cuarta": 60000})
ok(r.status_code == 200 and r.json()["impuesto_determinado"] == 760, "Cálculo de renta anual")
ok(c.post("/api/fraccionamiento/solicitar", headers=H, json={"deuda": 6000, "cuotas": 12}).status_code == 201, "Solicitud de fraccionamiento")
periodo = __import__("datetime").date.today().strftime("%Y-%m")
r = c.get(f"/api/pagos/periodo/{periodo}", headers=H)
ok(r.status_code == 200 and r.json()["ingresos_del_periodo"] >= 2500, "Pago a cuenta determinado desde los recibos del mes")
ok(c.post("/api/pagos", headers=H, json={"periodo": periodo}).status_code in (201, 409), "Presentación del pago a cuenta")

# --- Paso 4 y 5 del flujo: expediente y notificación -------------------------
docs = c.get("/api/documentos", headers=H)
ok(docs.status_code == 200 and any(d["tramite"] == "rhe" for d in docs.json()),
   "Constancia del recibo archivada en la gestión documental")
primera = next(d for d in docs.json() if d["tramite"] == "rhe")
descarga = c.get(f"/api/documentos/{primera['id']}", headers=H)
ok(descarga.status_code == 200 and descarga.content.startswith(b"%PDF"), "Descarga de la constancia en PDF")
sustento = c.post("/api/documentos/adjuntar", headers=H,
                  data={"tramite": "rhe", "referencia": primera["referencia"], "titulo": "Sustento de prueba"},
                  files={"archivo": ("sustento.pdf", b"%PDF-1.4\n prueba \n", "application/pdf")})
ok(sustento.status_code == 201, "Adjuntar un sustento al expediente")
malo = c.post("/api/documentos/adjuntar", headers=H, data={"tramite": "rhe", "titulo": "Falso"},
              files={"archivo": ("falso.pdf", b"MZ\x90 ejecutable", "application/pdf")})
ok(malo.status_code == 422, "Rechazo de un archivo que no es PDF/PNG/JPG")
notifs = c.get("/api/alertas/notificaciones", headers=H)
ok(notifs.status_code == 200 and len(notifs.json()) >= 2, "Notificaciones de confirmación recibidas")
ok(c.post(f"/api/alertas/notificaciones/{notifs.json()[0]['id']}/leida", headers=H).status_code == 200,
   "Marcar una notificación como leída")
print("\nResultado:", "TODO CORRECTO" if not fallos else f"{fallos} verificación(es) con falla")
sys.exit(1 if fallos else 0)
