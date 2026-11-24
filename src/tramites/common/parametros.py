"""Carga los parámetros tributarios (separados del código para actualizarlos sin volver a desplegar el código)."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache
def parametros() -> dict:
    return json.loads((Path(__file__).with_name("parametros.json")).read_text(encoding="utf-8"))
