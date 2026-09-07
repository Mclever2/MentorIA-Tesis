"""
Google Docs por enlace compartido.

Alcance deliberado: SOLO documentos con enlace de lectura ("cualquiera con el
enlace"). No se pide iniciar sesión con Google ni se toca el Drive del alumno;
el conector de `backend/mcp/drive_connector.py` es otra cosa (rúbricas
institucionales con service account) y no se reutiliza aquí.

El documento se descarga exportado a .docx, no a texto plano, para que conserve
los estilos de encabezado y entre por la misma tubería que un Word subido a
mano — que es la que da la estructura más fiable.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_RE_ID = re.compile(r"/document/d/([a-zA-Z0-9_-]{20,})")
_RE_ID_QUERY = re.compile(r"[?&]id=([a-zA-Z0-9_-]{20,})")
_TIMEOUT = 30
_MAX_BYTES = 40 * 1024 * 1024


class EnlaceInvalido(ValueError):
    """La URL no es un Google Doc accesible."""


def es_enlace_google_docs(texto: str) -> bool:
    t = (texto or "").strip()
    return t.startswith(("http://", "https://")) and "docs.google.com/document" in t


def extraer_id(url: str) -> str:
    for patron in (_RE_ID, _RE_ID_QUERY):
        m = patron.search(url or "")
        if m:
            return m.group(1)
    raise EnlaceInvalido(
        "Ese enlace no parece un Google Doc. Copia la URL desde la barra del "
        "navegador con el documento abierto (debe contener «/document/d/…»)."
    )


def descargar_docx(url: str) -> tuple[bytes, str]:
    """Descarga el Doc exportado a .docx. Devuelve (bytes, nombre sugerido)."""
    import requests

    doc_id = extraer_id(url)
    export = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"

    try:
        respuesta = requests.get(export, timeout=_TIMEOUT, allow_redirects=True)
    except Exception as exc:                                   # noqa: BLE001
        raise EnlaceInvalido(f"No pude conectarme a Google Docs: {exc}") from exc

    if respuesta.status_code in (401, 403):
        raise EnlaceInvalido(_MENSAJE_PERMISOS)
    if respuesta.status_code == 404:
        raise EnlaceInvalido(
            "El documento no existe o fue eliminado. Verifica el enlace."
        )
    if respuesta.status_code != 200:
        raise EnlaceInvalido(
            f"Google Docs respondió {respuesta.status_code}. Revisa el enlace y "
            "vuelve a intentarlo."
        )

    contenido = respuesta.content or b""
    tipo = (respuesta.headers.get("content-type") or "").lower()

    # Un documento privado NO devuelve 403: devuelve 200 con la página de login.
    # Sin esta comprobación, el HTML del login se indexaba como si fuera la tesis.
    if "text/html" in tipo or contenido[:2] != b"PK":
        raise EnlaceInvalido(_MENSAJE_PERMISOS)
    if len(contenido) > _MAX_BYTES:
        raise EnlaceInvalido("El documento es demasiado grande para procesarlo.")

    nombre = _nombre_desde_cabecera(respuesta.headers.get("content-disposition", ""))
    logger.info(f"[gdocs] Documento '{nombre}' descargado ({len(contenido):,} bytes)")
    return contenido, nombre


_MENSAJE_PERMISOS = (
    "Ese Google Doc es privado y no puedo abrirlo. En el documento pulsa "
    "«Compartir» → «Acceso general» → «Cualquier persona con el enlace» (permiso "
    "de Lector) y vuelve a pegar la URL. Si prefieres no compartirlo, descárgalo "
    "con «Archivo → Descargar → Word (.docx)» y súbelo aquí."
)


def _nombre_desde_cabecera(cabecera: str) -> str:
    m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", cabecera or "")
    if not m:
        return "documento.docx"
    from urllib.parse import unquote

    nombre = unquote(m.group(1)).strip().strip('"')
    return nombre or "documento.docx"
