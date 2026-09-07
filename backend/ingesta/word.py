"""
Extracción de documentos Word (.docx).

Es el formato en el que el estudiante REALMENTE escribe, y tiene una ventaja
decisiva sobre el PDF: los encabezados vienen marcados con estilos (`Heading N`
/ `Título N`), así que la estructura del proyecto se lee de forma exacta en vez
de inferirse de un índice con puntos guía. Aquí no hay páginas: se devuelven
bloques delimitados por los encabezados, que es la unidad que de verdad importa.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Estilos de encabezado en las dos localizaciones de Word que usan los alumnos.
_RE_ESTILO_TITULO = re.compile(r"^(heading|t[íi]tulo)\s*(\d+)", re.I)

# Encabezado escrito a mano (sin estilo): "1.2 OBJETIVOS", "CAPÍTULO II", etc.
_RE_ENCABEZADO_MANUAL = re.compile(
    r"^\s*(?:cap[íi]tulo\s+[ivxlc\d]+[\.\)]?\s*)?"
    r"(?:\d+(?:\.\d+)*\.?\s+)?"
    r"[A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9\s,:;\-–/()º°\.]{3,90}$"
)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Una lista numerada es el ESQUEMA del documento (sus títulos) y no una lista de
# contenido cuando sus elementos son cortos y no son oraciones. Un título es
# «Población y muestra»; un ítem de lista es «1 paquete de papel bond A4 90g.».
_MAX_MEDIANA_TITULO = 80
_MAX_RATIO_ORACIONES = 0.25

# Cuántos títulos numerados hacen falta para fiarse del esquema y dejar de
# adivinar encabezados por el formato. Un proyecto de tesis completo pasa de 40;
# por debajo de esto la numeración cubre solo una parte y conviene la red.
_MIN_TITULOS_ESQUEMA = 8


class WordNoSoportado(ValueError):
    """El archivo es .doc antiguo u otro formato que python-docx no abre."""


@dataclass
class ResultadoWord:
    bloques: list[tuple[int, str]] = field(default_factory=list)  # (orden, texto)
    estructura: dict[str, int] = field(default_factory=dict)      # encabezado → orden
    avisos: list[str] = field(default_factory=list)
    # True solo si los encabezados venían con estilo real de Word; False si se
    # dedujeron del formato del párrafo (mayúsculas/negrita). Cambia la confianza
    # con la que el resto del sistema trata la estructura.
    uso_estilos: bool = False
    # True si la estructura salió de la numeración multinivel de Word. No es un
    # estilo de título, pero tampoco es una deducción: el número lo puso Word.
    uso_numeracion: bool = False


def _nivel_encabezado(parrafo) -> int | None:
    """Nivel del encabezado por estilo (1, 2, 3…), o None si es texto normal."""
    try:
        nombre = (parrafo.style.name or "")
    except Exception:                                          # noqa: BLE001
        return None
    m = _RE_ESTILO_TITULO.match(nombre.strip())
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            return 1
    if nombre.strip().lower() in ("title", "título", "titulo"):
        return 1
    return None


def _parece_encabezado_manual(texto: str, parrafo) -> bool:
    """Encabezado sin estilo: línea corta, en mayúsculas o en negrita completa."""
    limpio = texto.strip()
    if not (4 <= len(limpio) <= 100) or limpio.endswith(('.', ':')) and len(limpio) > 60:
        return False
    if _RE_ENCABEZADO_MANUAL.match(limpio):
        return True
    try:
        runs = [r for r in parrafo.runs if (r.text or "").strip()]
        if runs and all(r.bold for r in runs) and len(limpio.split()) <= 12:
            return True
    except Exception:                                          # noqa: BLE001
        pass
    return False


# ── Numeración automática de Word ───────────────────────────────────────────
#
# El caso que rompía la estructura de los proyectos reales de la escuela: el
# alumno numera sus capítulos con la numeración multinivel de Word (Inicio →
# Lista multinivel), no escribiendo «2.1» a mano. Word guarda ese número en las
# propiedades del párrafo, NO en su texto, así que `parrafo.text` devuelve
# «Formulación del problema» pelado. Sin el número, la deducción por mayúsculas
# solo veía los capítulos en versales y se perdía TODAS las subsecciones —que es
# justo lo que la rúbrica califica—, mientras recogía la portada como si fueran
# secciones. Aquí se reconstruye la numeración tal como Word la pinta.


def _numeracion_parrafo(parrafo) -> tuple[str, int] | None:
    """(numId, nivel) si el párrafo pertenece a una lista numerada de Word."""
    pPr = parrafo._p.find(_W + "pPr")
    if pPr is None:
        return None
    numPr = pPr.find(_W + "numPr")
    if numPr is None:
        return None
    num = numPr.find(_W + "numId")
    if num is None or not num.get(_W + "val"):
        return None
    ilvl = numPr.find(_W + "ilvl")
    try:
        nivel = int(ilvl.get(_W + "val")) if ilvl is not None else 0
    except (TypeError, ValueError):
        nivel = 0
    return num.get(_W + "val"), nivel


def _definiciones_numeracion(documento) -> dict[str, dict[int, tuple[str, str, int]]]:
    """numId → {nivel: (formato, plantilla, inicio)} leído de numbering.xml."""
    try:
        raiz = documento.part.numbering_part.element
    except Exception:                                          # noqa: BLE001
        return {}                                              # el .docx no trae listas

    abstractos: dict[str, dict[int, tuple[str, str, int]]] = {}
    for abstracto in raiz.findall(_W + "abstractNum"):
        niveles: dict[int, tuple[str, str, int]] = {}
        for lvl in abstracto.findall(_W + "lvl"):
            try:
                indice = int(lvl.get(_W + "ilvl") or 0)
            except ValueError:
                continue

            def _val(tag: str, defecto: str = "") -> str:
                elem = lvl.find(_W + tag)
                return (elem.get(_W + "val") if elem is not None else None) or defecto

            try:
                inicio = int(_val("start", "1"))
            except ValueError:
                inicio = 1
            niveles[indice] = (_val("numFmt", "decimal"), _val("lvlText", "%1"), inicio)
        abstractos[abstracto.get(_W + "abstractNumId")] = niveles

    definiciones: dict[str, dict[int, tuple[str, str, int]]] = {}
    for num in raiz.findall(_W + "num"):
        ref = num.find(_W + "abstractNumId")
        clave = ref.get(_W + "val") if ref is not None else None
        if clave in abstractos:
            definiciones[num.get(_W + "numId")] = abstractos[clave]
    return definiciones


def _romano(n: int) -> str:
    pares = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
             (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    salida = ""
    for valor, signo in pares:
        while n >= valor:
            salida += signo
            n -= valor
    return salida


def _formatear(n: int, formato: str) -> str:
    if formato in ("upperRoman", "lowerRoman"):
        r = _romano(n)
        return r if formato == "upperRoman" else r.lower()
    if formato in ("upperLetter", "lowerLetter"):
        letra = chr(ord("A") + (n - 1) % 26) * (1 + (n - 1) // 26)
        return letra if formato == "upperLetter" else letra.lower()
    if formato == "decimalZero":
        return f"{n:02d}"
    return str(n)


class _Numerador:
    """Lleva los contadores de las listas y devuelve el número que Word pinta.

    Hay que recorrer el documento en orden: el número de un título depende de
    cuántos hermanos suyos vinieron antes, y un nivel se reinicia cada vez que
    avanza el nivel superior —así «2.1» pasa a «3.1» y no a «3.4»—.
    """

    def __init__(self, definiciones: dict[str, dict[int, tuple[str, str, int]]]):
        self._def = definiciones
        self._contadores: dict[str, dict[int, int]] = {}

    def etiqueta(self, num_id: str, nivel: int) -> str:
        niveles = self._def.get(num_id)
        if not niveles:
            return ""
        contador = self._contadores.setdefault(num_id, {})
        contador[nivel] = contador.get(nivel, niveles.get(nivel, ("", "", 1))[2] - 1) + 1
        for hondo in [n for n in contador if n > nivel]:
            contador.pop(hondo, None)

        formato, plantilla, _ = niveles[nivel]
        if formato in ("bullet", "none"):
            return ""
        texto = plantilla
        for n in sorted(niveles):
            if n > nivel:
                break
            fmt_n = niveles[n][0]
            valor = contador.get(n, niveles[n][2])
            texto = texto.replace(f"%{n + 1}", _formatear(valor, fmt_n))
        return texto.strip().strip(".)-").strip()


def _listas_de_esquema(documento, definiciones) -> tuple[set[str], int]:
    """Qué listas numeradas son el esquema del documento y no listas de contenido.

    Se decide por la forma de sus elementos, no por su posición: los títulos son
    breves y no terminan en punto; los ítems de una enumeración del presupuesto o
    de los objetivos son oraciones. Confundirlos convertía cada renglón del
    presupuesto en una sección de la rúbrica.
    """
    import statistics

    reunidos: dict[str, list[str]] = {}
    for parrafo in documento.paragraphs:
        texto = (parrafo.text or "").strip()
        if not texto:
            continue
        marca = _numeracion_parrafo(parrafo)
        if marca:
            reunidos.setdefault(marca[0], []).append(texto)

    esquema: set[str] = set()
    for num_id, textos in reunidos.items():
        niveles = definiciones.get(num_id) or {}
        if not niveles or all(f in ("bullet", "none") for f, _, _ in niveles.values()):
            continue
        oraciones = sum(1 for t in textos if t.endswith("."))
        if (statistics.median(len(t) for t in textos) <= _MAX_MEDIANA_TITULO
                and oraciones / len(textos) <= _MAX_RATIO_ORACIONES):
            esquema.add(num_id)
    return esquema, sum(len(reunidos[n]) for n in esquema)


def _texto_tabla(tabla) -> str:
    """Tabla → texto tabulado. Las matrices de consistencia y de
    operacionalización de variables viven en tablas: perderlas dejaba secciones
    enteras vacías para la rúbrica."""
    filas = []
    for fila in tabla.rows:
        celdas = [" ".join(c.text.split()) for c in fila.cells]
        # Word repite la celda combinada en cada columna que ocupa.
        deduplicadas: list[str] = []
        for celda in celdas:
            if not deduplicadas or celda != deduplicadas[-1]:
                deduplicadas.append(celda)
        linea = " | ".join(c for c in deduplicadas if c)
        if linea.strip(" |"):
            filas.append(linea)
    return "\n".join(filas)


def extraer_word(datos: bytes) -> ResultadoWord:
    """Extrae texto y estructura nativa de un .docx."""
    try:
        import docx
    except ImportError as exc:                                 # pragma: no cover
        raise WordNoSoportado(
            "Falta la librería python-docx en el servidor para leer archivos Word."
        ) from exc

    try:
        documento = docx.Document(io.BytesIO(datos))
    except Exception as exc:                                   # noqa: BLE001
        raise WordNoSoportado(
            "No pude abrir el archivo de Word. Si es un .doc antiguo, ábrelo en "
            "Word y usa «Guardar como» → .docx (o PDF) antes de subirlo."
        ) from exc

    from docx.table import Table
    from docx.text.paragraph import Paragraph

    resultado = ResultadoWord()
    cuerpo = documento.element.body

    definiciones = _definiciones_numeracion(documento)
    esquema, n_esquema = _listas_de_esquema(documento, definiciones)
    numerador = _Numerador(definiciones)
    # Si el documento trae un esquema propio, la deducción por mayúsculas y
    # negrita estorba: convertía la portada, el código Orcid y las fechas en
    # secciones. Solo se conserva como red de seguridad cuando no hay esquema, o
    # cuando el que hay es demasiado corto para ser el índice del proyecto.
    deducir = n_esquema < _MIN_TITULOS_ESQUEMA

    seccion_actual = "Documento"
    bloques: dict[str, list[str]] = {seccion_actual: []}
    orden: dict[str, int] = {seccion_actual: 0}
    siguiente = 1
    n_tablas = 0

    for hijo in cuerpo.iterchildren():
        etiqueta = hijo.tag.split('}')[-1]

        if etiqueta == "tbl":
            texto = _texto_tabla(Table(hijo, documento))
            if texto.strip():
                bloques[seccion_actual].append(texto)
                n_tablas += 1
            continue

        if etiqueta != "p":
            continue

        parrafo = Paragraph(hijo, documento)
        texto = (parrafo.text or "").strip()
        if not texto:
            continue

        # La numeración se consume SIEMPRE que el párrafo esté en una lista de
        # esquema, aunque luego no lo tratemos como título: los contadores de
        # Word avanzan con cada elemento, y saltarse uno desplazaría todos los
        # números siguientes.
        etiqueta_num = ""
        marca = _numeracion_parrafo(parrafo)
        if marca and marca[0] in esquema:
            etiqueta_num = numerador.etiqueta(*marca)

        nivel = _nivel_encabezado(parrafo)
        es_encabezado = (
            nivel is not None
            or bool(etiqueta_num)
            or (deducir and _parece_encabezado_manual(texto, parrafo))
        )
        if nivel is not None:
            resultado.uso_estilos = True
        if etiqueta_num:
            resultado.uso_numeracion = True
            texto = f"{etiqueta_num} {texto}"

        if es_encabezado:
            # Un encabezado repetido (p. ej. el mismo rótulo en dos capítulos)
            # no debe pisar al anterior: se le añade un sufijo discreto.
            nombre = texto
            if nombre in bloques:
                nombre = f"{texto} ({siguiente})"
            seccion_actual = nombre
            bloques[seccion_actual] = [texto]
            orden[seccion_actual] = siguiente
            siguiente += 1
        else:
            bloques[seccion_actual].append(texto)

    # La sección sintética inicial solo se conserva si tiene contenido propio
    # (portada, resumen, todo lo que va antes del primer encabezado).
    if not "".join(bloques.get("Documento", [])).strip():
        bloques.pop("Documento", None)
        orden.pop("Documento", None)

    for nombre, partes in bloques.items():
        texto = "\n\n".join(p for p in partes if p.strip()).strip()
        if texto:
            resultado.bloques.append((orden[nombre], texto))
            resultado.estructura[nombre] = orden[nombre]

    resultado.bloques.sort()
    con_estilo = sum(1 for n in resultado.estructura if n != "Documento")
    origen = ("estilos" if resultado.uso_estilos
              else "numeración" if resultado.uso_numeracion else "deducidos")
    logger.info(
        f"[word] {len(resultado.bloques)} bloques, {con_estilo} encabezados "
        f"({origen}), {n_tablas} tablas"
    )
    if not resultado.uso_estilos and not resultado.uso_numeracion:
        resultado.avisos.append(
            "Tu documento no usa estilos de título de Word, así que deduje la "
            "estructura del texto. Aplicar «Título 1/2» a los encabezados mejora "
            "bastante la precisión de la evaluación."
        )
    return resultado
