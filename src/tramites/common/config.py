"""Configuración central. Todo valor sensible se inyecta por variables de entorno
(en producción provienen de un gestor de secretos / KMS, nunca del repositorio)."""
import os


def env(nombre: str, defecto: str | None = None) -> str:
    valor = os.environ.get(nombre, defecto)
    if valor is None:
        raise RuntimeError(f"Variable de entorno requerida: {nombre}")
    return valor


class Settings:
    @property
    def jwt_secret(self) -> str:
        return env("JWT_SECRET", "dev-solo-para-pruebas-cambiar-en-produccion-0123456789")

    @property
    def jwt_minutos(self) -> int:
        return int(env("JWT_MINUTOS", "30"))

    @property
    def datos_url(self) -> str:
        return env("DATOS_URL", "http://datos-privados:8000")

    @property
    def internal_key(self) -> str:
        return env("INTERNAL_API_KEY", "dev-internal-key")

    @property
    def database_url(self) -> str:
        return env("DATABASE_URL", "sqlite:///./datos_dev.db")

    @property
    def kms_keys(self) -> list[str]:
        # Lista separada por comas: la primera cifra, todas descifran (rotación de claves).
        return [k.strip() for k in env("KMS_KEYS", "").split(",") if k.strip()]

    @property
    def seed_demo(self) -> bool:
        return env("SEED_DEMO", "0") == "1"


settings = Settings()
