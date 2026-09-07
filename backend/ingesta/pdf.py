"""
Extracción de PDF en cascada, página por página.

Por qué en cascada y no con un solo motor: `pdfplumber` (pdfminer) falla en
seco con fuentes *subset* sin `/ToUnicode`, y devuelve None o mojibake en vez
de un error. PDFium (`pypdfium2`) usa un decodificador de fuentes distinto y
rescata justo esos casos. Ambas librerías ya venían instaladas con pdfplumber,
así que la cascada no añade peso a la imagen de Cloud Run.

La mezcla es POR PÁGINA (no por documento): un proyecto con 20 páginas buenas
y 3 corruptas se recupera entero en vez de forzar a elegir un solo motor.
"""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass, field

from .calidad import es_utilizable, puntuar

logger = logging.getLogger(__name__)

_UMBRAL_PAGINA_OK = 0.45


class PdfProtegido(ValueError):
    """El PDF está cifrado y no se puede abrir sin contraseña."""


@dataclass
class ResultadoPdf:
    paginas: list[tuple[int, str]] = field(default_factory=list)   # (nº 1-indexed, texto)
    outline: dict[str, int] = field(default_factory=dict)          # marcadores → página
    extractores: list[str] = field(default_factory=list)           # motores que aportaron
    avisos: list[str] = field(default_factory=list)


# ── Motores ──────────────────────────────────────────────────────────────────

def _con_pdfplumber(datos: bytes, objetivo: set[int] | None = None) -> dict[int, str]:
    import pdfplumber

    paginas: dict[int, str] = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Cannot set.*color")
        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            for i, pagina in enumerate(pdf.pages):
                if objetivo is not None and (i + 1) not in objetivo:
                    continue
                try:
                    texto = pagina.extract_text() or ""
                except Exception as exc:                       # noqa: BLE001
                    logger.debug(f"[pdf] pdfplumber no pudo con la pág. {i + 1}: {exc}")
                    texto = ""
                paginas[i + 1] = texto.strip()
    return paginas


def _con_pdfium(datos: bytes, objetivo: set[int] | None = None) -> dict[int, str]:
    import pypdfium2 as pdfium

    paginas: dict[int, str] = {}
    documento = pdfium.PdfDocument(datos)
    try:
        for i in range(len(documento)):
            if objetivo is not None and (i + 1) not in objetivo:
                continue
            try:
                texto = documento[i].get_textpage().get_text_bounded() or ""
            except Exception as exc:                           # noqa: BLE001
                logger.debug(f"[pdf] pdfium no pudo con la pág. {i + 1}: {exc}")
                texto = ""
            paginas[i + 1] = texto.strip()
    finally:
        documento.close()
    return paginas


def _con_pdfminer(datos: bytes, objetivo: set[int] | None = None) -> dict[int, str]:
    """pdfminer.six directo, con tolerancias laxas.

    Rescata maquetados a dos columnas y tablas donde el agrupado por defecto
    de pdfplumber parte las líneas o las devuelve vacías.
    """
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams
    from pdfminer.pdfpage import PDFPage

    params = LAParams(char_margin=3.0, line_margin=0.6, word_margin=0.2, boxes_flow=0.4)

    if objetivo is None:
        with io.BytesIO(datos) as buffer:
            total = sum(1 for _ in PDFPage.get_pages(buffer, check_extractable=False))
        numeros = range(1, total + 1)
    else:
        numeros = sorted(objetivo)

    paginas: dict[int, str] = {}
    for numero in numeros:
        try:
            texto = extract_text(
                io.BytesIO(datos), page_numbers=[numero - 1], laparams=params
            ) or ""
        except Exception as exc:                               # noqa: BLE001
            logger.debug(f"[pdf] pdfminer no pudo con la pág. {numero}: {exc}")
            texto = ""
        paginas[numero] = texto.strip()
    return paginas


# Orden medido sobre un proyecto real de 192 páginas: pdfium tarda 0.5 s contra
# los 13 s de pdfplumber con calidad idéntica (score medio 0.98 en ambos), así que
# va primero. pdfplumber entra solo para las páginas que pdfium deja mal — resuelve
# mejor tablas y maquetados a dos columnas — y pdfminer es el último recurso.
_MOTORES = [
    ("pdfium",     _con_pdfium),
    ("pdfplumber", _con_pdfplumber),
    ("pdfminer",   _con_pdfminer),
]


# ── Marcadores (outline) ─────────────────────────────────────────────────────

def _leer_outline(datos: bytes) -> dict[str, int]:
    """Marcadores del PDF → {título: nº de página física}.

    Los PDF exportados desde Word traen sus encabezados como marcadores. Es la
    fuente de estructura MÁS fiable que existe y hasta ahora se ignoraba por
    completo: no depende de que el índice tenga puntos guía, ni de que los
    números impresos coincidan con las páginas físicas.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return {}

    try:
        documento = pdfium.PdfDocument(datos)
    except Exception:                                          # noqa: BLE001
        return {}

    estructura: dict[str, int] = {}
    try:
        for marcador in documento.get_toc():
            titulo = (marcador.title or "").strip()
            indice = marcador.page_index
            if titulo and indice is not None:
                estructura.setdefault(titulo, int(indice) + 1)
    except Exception as exc:                                   # noqa: BLE001
        logger.debug(f"[pdf] No se pudieron leer los marcadores: {exc}")
    finally:
        documento.close()
    return estructura


# ── Entrada pública ──────────────────────────────────────────────────────────

def _esta_cifrado(datos: bytes) -> bool:
    try:
        import pypdfium2 as pdfium
        pdfium.PdfDocument(datos).close()
        return False
    except Exception as exc:                                   # noqa: BLE001
        texto = str(exc).lower()
        return "password" in texto or "encrypt" in texto


def extraer_pdf(datos: bytes) -> ResultadoPdf:
    """Extrae el texto de un PDF combinando motores página a página."""
    resultado = ResultadoPdf()
    mejor: dict[int, str] = {}
    puntajes: dict[int, float] = {}

    for nombre, motor in _MOTORES:
        # El primer motor barre el documento entero; los de respaldo solo
        # re-procesan las páginas que quedaron ilegibles. Sin esto, dos páginas
        # escaneadas obligaban a re-extraer el PDF completo con cada motor
        # (95 s en un proyecto de 192 páginas, contra menos de 1 s así).
        pendientes = {n for n, s in puntajes.items() if s < _UMBRAL_PAGINA_OK}
        objetivo = pendientes if puntajes else None
        if puntajes and not pendientes:
            break

        try:
            paginas = motor(datos, objetivo)
        except Exception as exc:                               # noqa: BLE001
            logger.info(f"[pdf] El motor '{nombre}' no pudo abrir el documento: {exc}")
            if _esta_cifrado(datos):
                raise PdfProtegido(
                    "El PDF está protegido con contraseña. Quita la protección "
                    "(Archivo -> Guardar como, sin cifrado) y vuelve a subirlo."
                ) from exc
            continue

        aporto = False
        for numero, texto in paginas.items():
            score = puntuar(texto)
            previo = puntajes.get(numero)
            # Solo se cambia de motor si la mejora es real: un empate técnico no
            # justifica mezclar maquetados distintos en el mismo documento.
            if previo is None or score - previo > 0.05:
                mejor[numero] = texto
                puntajes[numero] = score
                aporto = True
        if aporto:
            resultado.extractores.append(nombre)

    if not mejor:
        raise ValueError(
            "No se pudo leer ninguna página del PDF. Puede estar dañado o protegido; "
            "prueba a subir el archivo de Word original."
        )

    resultado.paginas = [
        (numero, texto) for numero, texto in sorted(mejor.items()) if es_utilizable(texto)
    ]

    sin_texto = [n for n in sorted(mejor) if not es_utilizable(mejor[n])]
    if sin_texto:
        muestra = ", ".join(str(n) for n in sin_texto[:8])
        sufijo = "…" if len(sin_texto) > 8 else ""
        resultado.avisos.append(
            f"{len(sin_texto)} página(s) sin texto seleccionable (nº {muestra}{sufijo}): "
            "suelen ser imágenes o capturas escaneadas, y su contenido no se pudo indexar."
        )

    resultado.outline = _leer_outline(datos)
    if resultado.outline:
        logger.info(f"[pdf] {len(resultado.outline)} marcadores leídos del PDF")
    logger.info(
        f"[pdf] {len(resultado.paginas)} páginas con texto útil "
        f"(motores: {', '.join(resultado.extractores) or 'ninguno'})"
    )
    return resultado
