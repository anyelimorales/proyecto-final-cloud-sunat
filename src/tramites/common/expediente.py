"""Expediente electrónico: archivo de constancias y notificación al contribuyente.

Cada trámite que se completa deja dos rastros además del registro del propio trámite:
una constancia archivada en la gestión documental (nube privada, cifrada) y una
notificación dirigida al contribuyente. Ambos pasan por la capa de datos privada, de
modo que quedan en la bitácora de auditoría como cualquier otra operación.
"""
import base64
from datetime import datetime, timezone

from . import datos

TIPO_DOC = "documento"
TIPO_NOTIF = "notificacion"

# Tipos de archivo admitidos como sustento, con su firma binaria.
FIRMAS = {"application/pdf": b"%PDF", "image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff"}
LIMITE_BYTES = 2 * 1024 * 1024


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def constancia_pdf(titulo: str, lineas: list[tuple[str, str]], pie: str) -> bytes:
    """Genera un PDF mínimo y válido sin dependencias externas.

    Se escribe a mano porque la constancia es un documento de una página con texto
    plano; añadir una biblioteca de maquetación para esto no se justifica.
    """
    def esc(t: str) -> str:
        # Los paréntesis y la barra invertida delimitan cadenas en PDF. Las tildes y las eñes se
        # conservan: la fuente se declara con WinAnsiEncoding y el flujo se codifica en cp1252.
        return t.replace("\\", "").replace("(", "[").replace(")", "]")

    y = 780
    partes = [f"BT /F1 16 Tf 60 {y} Td ({esc(titulo)}) Tj ET"]
    y -= 34
    for etiqueta, valor in lineas:
        partes.append(f"BT /F1 10 Tf 60 {y} Td ({esc(etiqueta)}) Tj ET")
        partes.append(f"BT /F1 10 Tf 230 {y} Td ({esc(str(valor))}) Tj ET")
        y -= 18
    partes.append(f"BT /F1 8 Tf 60 {y - 20} Td ({esc(pie)}) Tj ET")
    flujo = ("\n".join(partes)).encode("cp1252", "replace")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for i, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n"
    for pos in posiciones:
        salida += f"{pos:010d} 00000 n \n".encode()
    salida += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n"
               f"{inicio_xref}\n%%EOF\n").encode()
    return bytes(salida)


def archivar(ruc: str, tramite: str, titulo: str, lineas: list[tuple[str, str]],
             referencia: str, usuario: str | None = None) -> dict:
    """Guarda la constancia del trámite en la gestión documental de la nube privada."""
    pdf = constancia_pdf(titulo, lineas, "Documento generado por la plataforma de trámites tributarios.")
    doc = {
        "tramite": tramite,
        "titulo": titulo,
        "referencia": referencia,
        "origen": "constancia",
        "nombre_archivo": f"{tramite}_{referencia}.pdf".replace("/", "-"),
        "tipo_mime": "application/pdf",
        "tamano_bytes": len(pdf),
        "archivado": _ahora(),
        "contenido_b64": base64.b64encode(pdf).decode(),
    }
    return datos.crear(TIPO_DOC, ruc, doc, usuario=usuario or ruc)


def notificar(ruc: str, asunto: str, mensaje: str, tramite: str,
              referencia: str, usuario: str | None = None) -> dict:
    """Deja la confirmación dirigida al contribuyente. El despachador la entrega por su canal."""
    notif = {
        "asunto": asunto,
        "mensaje": mensaje,
        "tramite": tramite,
        "referencia": referencia,
        "creada": _ahora(),
        "leida": False,
        "entregada": False,
    }
    return datos.crear(TIPO_NOTIF, ruc, notif, usuario=usuario or ruc)


def validar_adjunto(nombre: str, contenido: bytes) -> str:
    """Comprueba tamaño y firma binaria. Devuelve el tipo MIME detectado."""
    if not contenido:
        raise ValueError("El archivo está vacío")
    if len(contenido) > LIMITE_BYTES:
        raise ValueError(f"El archivo supera el límite de {LIMITE_BYTES // (1024 * 1024)} MB")
    for mime, firma in FIRMAS.items():
        if contenido.startswith(firma):
            return mime
    raise ValueError("Solo se admiten archivos PDF, PNG o JPG")
