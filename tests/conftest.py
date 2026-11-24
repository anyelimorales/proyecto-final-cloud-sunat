import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["KMS_KEYS"] = "uSD0u0H0yxXmN1x2d5CzSYUR4vUm5C9LF7bxWk2Wq4k="
os.environ["SEED_DEMO"] = "1"
os.environ["INTERNAL_API_KEY"] = "clave-de-prueba"
os.environ["JWT_SECRET"] = "secreto-de-prueba-suficientemente-largo-123456"

import pyotp
import pytest
from fastapi.testclient import TestClient

from tramites.common import datos
from tramites.datos import main as datos_main


@pytest.fixture(scope="session")
def datos_app():
    with TestClient(datos_main.app) as c:  # ejecuta startup (siembra demo)
        datos.set_client(c)  # los servicios 'públicos' hablan con la capa privada en memoria
        yield c


@pytest.fixture(scope="session")
def token(datos_app):
    from tramites.auth.main import app as auth_app
    c = TestClient(auth_app)
    r = c.post("/api/auth/login", json={"ruc": datos_main.DEMO_RUC, "usuario": "psicologa1", "clave": "Demo#2026"})
    assert r.status_code == 200, r.text
    codigo = pyotp.TOTP(datos_main.DEMO_TOTP).now()
    r = c.post("/api/auth/mfa", json={"mfa_token": r.json()["mfa_token"], "codigo": codigo})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}
