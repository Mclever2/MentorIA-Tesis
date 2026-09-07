"""
Ingesta de proyectos de tesis — punto de entrada único.

Antes solo se aceptaba PDF y con un único extractor, así que un avance en Word,
un texto pegado o un PDF con fuentes raras se quedaban fuera. Aquí se decide el
formato por firma binaria (no por la extensión, que el alumno cambia a mano) y
cada formato entra por su propio extractor:

    PDF          → cascada pdfium / pdfplumber / pdfminer, página a página
    DOCX         → estilos de encabezado nativos (la estructura más fiable)
    TXT / MD     → decodificación con detección de encoding
    Texto pegado → mismo camino que TXT
    Google Docs  → se exporta a .docx y entra como Word

Todos devuelven la misma forma (`DocumentoExtraido`), así que el resto del
sistema —vectorización, rúbrica, agentes— no sabe de qué formato vino.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .calidad import es_utilizable
from .gdocs import EnlaceInvalido, descargar_docx, es_enlace_google_docs
from .pdf import PdfProtegido, extraer_pdf
from .texto_plano import TextoIlegible, decodificar, extraer_texto
from .word import WordNoSoportado, extraer_word

logger = logging.getLogger(__name__)

__all__ = [
    "DocumentoExtraido",
    "FormatoNoSoportado",
    "extraer_documento",
    "extraer_de_texto",
    "es_enlace_google_docs",
    "EXTENSIONES_ACEPTADAS",
    "MIMES_ACEPTADOS",
]

EXTENSIONES_ACEPTADAS = (".pdf", ".docx", ".txt", ".md", ".markdown")
MIMES_ACEPTADOS = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
)

_MIN_CHARS_UTILES = 100


class FormatoNoSoportado(ValueError):
    """El archivo no es de un formato que se pueda indexar."""


@dataclass
class DocumentoExtraido:
    nombre: str
    formato: str                                                  # pdf | docx | texto
    bloques: list[tuple[int, str]] = field(default_factory=list)   # (orden, texto)
    estructura: dict[str, int] = field(default_factory=dict)       # sección → orden
    origen_estructura: str = "ninguna"                             # de dónde salió
    extractores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n\n".join(t for _, t in sorted(self.bloques))

    @property
    def chars(self) -> int:
        return sum(len(t) for _, t in self.bloques)


# ── Detección de formato por firma binaria ───────────────────────────────────

def _detectar_formato(nombre: str, datos: bytes) -> str:
    cabecera = datos[:8]
    if cabecera.startswith(b"%PDF"):
        return "pdf"
    if cabecera.startswith(b"PK\x03\x04"):
        # Cualquier Office moderno es un ZIP; solo aceptamos Word.
        if datos[:4000].find(b"word/") != -1 or nombre.lower().endswith(".docx"):
            return "docx"
        raise FormatoNoSoportado(
            "Ese archivo de Office no es un documento de Word. Sube tu proyecto "
            "en .docx, .pdf o pega el texto directamente en el chat."
        )
    if cabecera.startswith(b"\xd0\xcf\x11\xe0"):
        raise FormatoNoSoportado(
            "Es un .doc de Word antiguo, que no puedo leer. Ábrelo en Word y usa "
            "«Guardar como» → Word (.docx) o PDF, y vuelve a subirlo."
        )
    if nombre.lower().endswith((".txt", ".md", ".markdown")):
        return "texto"
    # Sin firma conocida: si decodifica como texto legible, lo tratamos como tal.
    try:
        muestra = decodificar(datos[:8192])
    except TextoIlegible:
        muestra = ""
    if es_utilizable(muestra):
        return "texto"
    raise FormatoNoSoportado(
        "No reconozco ese formato. Puedes subir tu proyecto en PDF, Word (.docx) "
        "o texto (.txt/.md), pegar el texto en el chat, o compartir el enlace de "
        "tu Google Doc."
    )


# ── Entradas públicas ────────────────────────────────────────────────────────

def extraer_documento(nombre: str, datos: bytes) -> DocumentoExtraido:
    """Extrae texto y estructura de un archivo subido, sea cual sea su formato."""
    if not datos:
        raise FormatoNoSoportado("El archivo llegó vacío.")

    formato = _detectar_formato(nombre or "", datos)

    if formato == "pdf":
        crudo = extraer_pdf(datos)
        extraido = DocumentoExtraido(
            nombre=nombre or "proyecto.pdf",
            formato="pdf",
            bloques=crudo.paginas,
            estructura=crudo.outline,
            origen_estructura="marcadores_pdf" if crudo.outline else "ninguna",
            extractores=crudo.extractores,
            avisos=list(crudo.avisos),
        )
    elif formato == "docx":
        crudo = extraer_word(datos)
        extraido = DocumentoExtraido(
            nombre=nombre or "proyecto.docx",
            formato="docx",
            bloques=crudo.bloques,
            estructura=crudo.estructura,
            origen_estructura=(
                ("estilos_word" if crudo.uso_estilos
                 else "numeracion_word" if crudo.uso_numeracion
                 else "encabezados_word")
                if crudo.estructura else "ninguna"
            ),
            extractores=["python-docx"],
            avisos=list(crudo.avisos),
        )
    else:
        crudo = extraer_texto(decodificar(datos))
        extraido = DocumentoExtraido(
            nombre=nombre or "proyecto.txt",
            formato="texto",
            bloques=crudo.bloques,
            estructura=crudo.estructura,
            origen_estructura="encabezados_markdown" if crudo.estructura else "ninguna",
            extractores=["texto"],
            avisos=list(crudo.avisos),
        )

    _validar(extraido)
    logger.info(
        f"[ingesta] '{extraido.nombre}' ({extraido.formato}): {len(extraido.bloques)} bloques, "
        f"{extraido.chars:,} chars, estructura={extraido.origen_estructura}"
    )
    return extraido


def extraer_de_texto(texto: str, nombre: str = "Texto pegado") -> DocumentoExtraido:
    """Texto pegado por el estudiante en el chat."""
    crudo = extraer_texto(texto)
    extraido = DocumentoExtraido(
        nombre=nombre,
        formato="texto",
        bloques=crudo.bloques,
        estructura=crudo.estructura,
        origen_estructura="encabezados_markdown" if crudo.estructura else "ninguna",
        extractores=["pegado"],
        avisos=list(crudo.avisos),
    )
    _validar(extraido)
    return extraido


def extraer_de_google_docs(url: str) -> DocumentoExtraido:
    """Google Doc compartido por enlace → se exporta a .docx y entra como Word."""
    datos, nombre = descargar_docx(url)
    extraido = extraer_documento(nombre, datos)
    extraido.avisos.insert(0, f"Importado desde Google Docs: {nombre}")
    return extraido


def _validar(extraido: DocumentoExtraido) -> None:
    if extraido.chars < _MIN_CHARS_UTILES:
        detalle = " ".join(extraido.avisos) if extraido.avisos else ""
        raise FormatoNoSoportado(
            "No encontré texto legible en el documento. "
            + (detalle or "Si es un PDF escaneado, sube el archivo de Word original.")
        )
