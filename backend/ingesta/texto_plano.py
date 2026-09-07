"""
Texto plano, Markdown y texto pegado en el chat.

Es la vía de entrada del pegado grande del estudiante: cuando pega media
sección desde Word, no hay archivo ni páginas, solo texto. Los encabezados
Markdown (`## Objetivos`) y los numerados (`1.2 Objetivos`) se aprovechan como
estructura cuando existen; si no, la estructura la resuelve después
`backend.rag.estructura` sobre el cuerpo del texto.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.{2,120})$")
_MAX_CHARS_BLOQUE = 4000


class TextoIlegible(ValueError):
    """No se pudo decodificar el archivo como texto."""


@dataclass
class ResultadoTexto:
    bloques: list[tuple[int, str]] = field(default_factory=list)
    estructura: dict[str, int] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


def decodificar(datos: bytes) -> str:
    """Bytes → str probando encodings reales antes de rendirse.

    Los .txt exportados desde Word en Windows llegan en cp1252, no en UTF-8;
    decodificar a ciegas convertía las tildes en basura.
    """
    try:
        from charset_normalizer import from_bytes

        resultado = from_bytes(datos).best()
        if resultado is not None:
            return str(resultado)
    except Exception:                                          # noqa: BLE001
        pass

    for codec in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return datos.decode(codec)
        except UnicodeDecodeError:
            continue
    raise TextoIlegible(
        "No pude leer el archivo como texto. Guárdalo en UTF-8 o súbelo como .docx."
    )


def extraer_texto(texto: str) -> ResultadoTexto:
    """Divide el texto en bloques, usando encabezados Markdown si los hay."""
    resultado = ResultadoTexto()
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not texto:
        raise TextoIlegible("El texto está vacío.")

    seccion_actual: str | None = None
    bloques: dict[str, list[str]] = {}
    orden: dict[str, int] = {}
    sueltas: list[str] = []
    siguiente = 1

    for linea in texto.split("\n"):
        m = _RE_MD_HEADING.match(linea.strip())
        if m:
            nombre = m.group(2).strip()
            if nombre in bloques:
                nombre = f"{nombre} ({siguiente})"
            seccion_actual = nombre
            bloques[seccion_actual] = [nombre]
            orden[seccion_actual] = siguiente
            siguiente += 1
            continue
        if seccion_actual is None:
            sueltas.append(linea)
        else:
            bloques[seccion_actual].append(linea)

    if bloques:
        preambulo = "\n".join(sueltas).strip()
        if preambulo:
            bloques["Documento"] = [preambulo]
            orden["Documento"] = 0
        for nombre, partes in bloques.items():
            contenido = "\n".join(partes).strip()
            if contenido:
                resultado.bloques.append((orden[nombre], contenido))
                resultado.estructura[nombre] = orden[nombre]
        resultado.bloques.sort()
    else:
        # Sin encabezados Markdown: se trocea por párrafos para no mandar un
        # muro de texto único a la detección de estructura.
        actual: list[str] = []
        indice = 1
        for parrafo in re.split(r"\n\s*\n", texto):
            actual.append(parrafo)
            if sum(len(p) for p in actual) >= _MAX_CHARS_BLOQUE:
                resultado.bloques.append((indice, "\n\n".join(actual).strip()))
                indice += 1
                actual = []
        if actual:
            resultado.bloques.append((indice, "\n\n".join(actual).strip()))

    logger.info(
        f"[texto] {len(resultado.bloques)} bloques, "
        f"{len(resultado.estructura)} encabezados Markdown"
    )
    return resultado
