"""
Resolución de la estructura de un proyecto de tesis.

Este módulo existe porque la indexación dependía de UNA sola señal: un índice
con puntos guía ("Objetivos.........12"). Si el proyecto no tenía índice —el
caso normal cuando el estudiante sube un avance de tres páginas— la estructura
salía vacía, los fragmentos se guardaban sin metadato `seccion`, ningún ítem de
rúbrica se podía mapear y la revisión terminaba con "no se pudo extraer
contenido evaluable" pese a que el texto SÍ se había extraído.

Ahora la estructura se busca en cascada, de la señal más fiable a la más débil:

    1. estilos de encabezado de Word / marcadores del PDF / encabezados Markdown
    2. encabezados detectados en el propio cuerpo del texto
    3. índice con puntos guía, CALIBRANDO el desfase entre la página impresa y
       la página física
    4. clasificación semántica de cada bloque contra las secciones de la rúbrica

El paso 4 garantiza que SIEMPRE haya secciones con nombre: a partir de aquí, un
documento legible nunca vuelve a quedar sin evaluar.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from backend.config import SECCIONES_TESIS

logger = logging.getLogger(__name__)

# ── Índice (TOC) ─────────────────────────────────────────────────────────────

_RE_LINEA_TOC = re.compile(r'\.{4,}\s*\d{1,4}\s*$')
_RE_ENTRADA_TOC = re.compile(
    r'^(\d[\d\.\-–]*\.?\s*[A-ZÁÉÍÓÚÜÑ][^\.]{3,}?)\s*\.{3,}\s*(\d{1,4})\s*$',
    re.IGNORECASE,
)
_UMBRAL_PAGINA_TOC = 0.28

# ── Encabezados en el cuerpo ─────────────────────────────────────────────────

# Numerado: "1.2 Objetivos", "2.3.1. Bases teóricas", "IV. Metodología".
_RE_ENCABEZADO_NUM = re.compile(
    r'^\s*(?:\d+(?:\.\d+)*\.?|[IVXLC]{1,5}\.)\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ][^\n]{2,90})$'
)
# Rótulo canónico sin numerar: "OBJETIVOS", "Marco teórico".
_SINONIMOS_SECCION = (
    "titulo del proyecto", "titulo", "introduccion", "realidad problematica",
    "planteamiento del problema", "descripcion de la realidad",
    "formulacion del problema", "problema de investigacion", "problema central",
    "objetivos", "objetivo general", "objetivos especificos",
    "importancia del estudio", "importancia", "justificacion",
    "marco teorico", "antecedentes", "investigaciones antecedentes",
    "bases teoricas", "base teorica", "definicion de terminos",
    "hipotesis", "variables", "operacionalizacion de variables",
    "matriz de consistencia", "marco metodologico", "metodologia",
    "tipo de investigacion", "metodo de investigacion", "diseno de investigacion",
    "poblacion y muestra", "poblacion", "muestra",
    "instrumentos de recoleccion de datos", "tecnicas e instrumentos",
    "procedimiento", "procedimiento de ejecucion", "analisis de datos",
    "procesamiento y analisis de datos", "aspectos administrativos",
    "cronograma", "recursos", "presupuesto", "financiamiento",
    "referencias bibliograficas", "referencias", "bibliografia", "anexos",
)
_MAX_CHARS_ENCABEZADO = 100


@dataclass
class ResultadoEstructura:
    grupos: list[tuple[str, str, int]] = field(default_factory=list)  # (nombre, texto, orden)
    estructura: dict[str, int] = field(default_factory=dict)          # nombre → orden
    origen: str = "ninguna"
    avisos: list[str] = field(default_factory=list)


def _norm(texto: str) -> str:
    """Minúsculas sin acentos ni puntuación de borde, para comparar rótulos."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9\s]", " ", t.lower()).strip()


# ── 1. Índice con puntos guía ────────────────────────────────────────────────

def _ratio_lineas_toc(texto_pagina: str) -> float:
    lineas = [l.strip() for l in texto_pagina.split('\n') if l.strip()]
    if len(lineas) < 2:
        return 0.0
    return sum(1 for l in lineas if _RE_LINEA_TOC.search(l)) / len(lineas)


def separar_indice(paginas: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], dict[str, int]]:
    """Aparta las páginas de índice y devuelve (contenido, estructura del índice)."""
    contenido: list[tuple[int, str]] = []
    texto_toc: list[str] = []

    for numero, texto in paginas:
        if not texto or not texto.strip():
            continue
        if _ratio_lineas_toc(texto) >= _UMBRAL_PAGINA_TOC:
            texto_toc.append(texto)
            logger.info(f"Pág. {numero}: índice — excluida del contenido")
        else:
            contenido.append((numero, texto.strip()))

    estructura: dict[str, int] = {}
    for texto in texto_toc:
        for linea in texto.split('\n'):
            m = _RE_ENTRADA_TOC.match(linea.strip())
            if m:
                nombre = re.sub(r'\s+', ' ', m.group(1)).strip()
                try:
                    estructura[nombre] = int(m.group(2))
                except ValueError:
                    pass
    return contenido, estructura


def calibrar_indice(
    paginas: list[tuple[int, str]],
    estructura_toc: dict[str, int],
) -> tuple[dict[str, int], int]:
    """Corrige el desfase entre la página IMPRESA del índice y la página FÍSICA.

    Los preliminares (carátula, dedicatoria, índice) suelen ir sin numerar o en
    romanos, así que "Objetivos ... 12" está en realidad en la hoja 15 del PDF.
    Sin corregirlo, el contenido se reparte en las secciones equivocadas y, si
    el desfase es grande, ninguna página encaja y el documento entero acaba en
    un cajón sin nombre. Se busca cada encabezado en el cuerpo y se aplica el
    desplazamiento más repetido.
    """
    if not estructura_toc or not paginas:
        return estructura_toc, 0

    texto_por_pagina = {n: _norm(t) for n, t in paginas}
    desfases: list[int] = []

    for nombre, pagina_impresa in estructura_toc.items():
        clave = _norm(nombre)
        if len(clave) < 6:
            continue
        for numero, texto in texto_por_pagina.items():
            if clave[:60] in texto:
                desfases.append(numero - pagina_impresa)
                break

    if not desfases:
        return estructura_toc, 0

    offset, repeticiones = Counter(desfases).most_common(1)[0]
    # Un desfase creíble lo confirma más de una sección; con una sola coincidencia
    # es más probable que sea una cita del título dentro del texto.
    if offset == 0 or repeticiones < 2:
        return estructura_toc, 0

    paginas_validas = {n for n, _ in paginas}
    corregida = {
        nombre: pagina + offset
        for nombre, pagina in estructura_toc.items()
        if (pagina + offset) in paginas_validas
    }
    if not corregida:
        return estructura_toc, 0

    logger.info(
        f"Índice calibrado: desfase de {offset:+d} páginas confirmado por "
        f"{repeticiones} secciones ({len(corregida)}/{len(estructura_toc)} ubicadas)"
    )
    return corregida, offset


# ── 2. Encabezados en el cuerpo ──────────────────────────────────────────────

def _es_encabezado(linea: str) -> bool:
    limpio = linea.strip()
    if not (4 <= len(limpio) <= _MAX_CHARS_ENCABEZADO):
        return False
    if limpio.endswith(('.', ',', ';', ':')) and len(limpio) > 60:
        return False
    if _RE_LINEA_TOC.search(limpio):          # es una entrada de índice, no un encabezado
        return False

    if _RE_ENCABEZADO_NUM.match(limpio):
        return True

    clave = _norm(limpio)
    if clave in _SINONIMOS_SECCION:
        return True
    # Rótulo en mayúsculas y corto: "PLANTEAMIENTO DEL PROBLEMA".
    letras = [c for c in limpio if c.isalpha()]
    if (letras and len(limpio.split()) <= 10
            and sum(1 for c in letras if c.isupper()) / len(letras) > 0.85
            and any(s in clave for s in _SINONIMOS_SECCION)):
        return True
    return False


def _texto_recurrente(paginas: list[tuple[int, str]]) -> set[str]:
    """Líneas que se repiten página tras página: encabezados y pies corridos.

    Es un filtro imprescindible, no una optimización. El pie de página de una
    tesis («15 Universidad Privada Antenor Orrego») empieza por el número de
    página, así que encaja con el patrón de encabezado numerado y convertía
    CADA página del documento en una sección falsa, arrasando el mapeo de la
    rúbrica. Se compara sin el número inicial, que es justo lo que cambia.
    """
    if len(paginas) < 4:
        return set()

    conteo: Counter = Counter()
    for _, texto in paginas:
        vistos = set()
        for linea in (texto or "").split('\n'):
            clave = _norm(re.sub(r'^\s*\d{1,4}\s+', '', linea))
            if len(clave) >= 8:
                vistos.add(clave)
        conteo.update(vistos)

    umbral = max(3, len(paginas) // 4)
    return {clave for clave, n in conteo.items() if n >= umbral}


def detectar_encabezados(paginas: list[tuple[int, str]]) -> dict[str, int]:
    """Encabezados hallados en el TEXTO del documento → {nombre: página/bloque}."""
    recurrentes = _texto_recurrente(paginas)
    encontrados: dict[str, int] = {}
    descartados = 0

    for numero, texto in paginas:
        for linea in (texto or "").split('\n'):
            limpio = re.sub(r'\s+', ' ', linea).strip()
            if not _es_encabezado(limpio) or limpio in encontrados:
                continue
            if _norm(re.sub(r'^\s*\d{1,4}\s+', '', limpio)) in recurrentes:
                descartados += 1
                continue
            encontrados[limpio] = numero

    if encontrados:
        logger.info(
            f"Encabezados detectados en el cuerpo: {len(encontrados)}"
            + (f" ({descartados} descartados por ser encabezado/pie corrido)" if descartados else "")
        )
    return encontrados


# ── 3. Clasificación semántica (último recurso) ──────────────────────────────

# Marcadores léxicos de altísima precisión en una tesis en español. La
# similitud por embeddings sola confunde secciones (ver `_z_por_seccion`); estas
# frases son inequívocas y no cuestan nada, así que mandan cuando aparecen.
_PISTAS_LEXICAS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"objetivos?\s+(general|especific)|se busca determinar|"
                r"determinar en que medida", re.I), "1.2 Objetivos (General y Específicos)"),
    (re.compile(r"\bhipotesis\b|se plantea que|\bh[i01]\s*:", re.I), "3.1–3.2 Hipótesis"),
    (re.compile(r"matriz de consistencia", re.I), "3.4 Matriz de consistencia"),
    (re.compile(r"operacionalizacion|dimensiones e indicadores|"
                r"variable (in)?dependiente", re.I), "3.3 Variables (Operacionalización)"),
    (re.compile(r"\bpoblacion\b|\bmuestra\b|muestreo|criterios de (in|ex)clusion",
                re.I), "4.4 Población y muestra"),
    (re.compile(r"instrumentos? de recoleccion|cuestionario|ficha de observacion|"
                r"validez y confiabilidad|alfa de cronbach", re.I),
     "4.5 Instrumentos de recolección de datos"),
    (re.compile(r"tipo de investigacion|diseno (de la )?investigacion|"
                r"cuasi\s*experimental|preexperimental", re.I), "4.1–4.3 Tipo, Método y Diseño"),
    (re.compile(r"procesamiento y analisis|analisis de (los )?datos|"
                r"prueba de hipotesis|spss", re.I), "4.7 Análisis de datos"),
    (re.compile(r"cronograma|presupuesto|financiamiento|recursos humanos", re.I),
     "5. Aspectos administrativos"),
    (re.compile(r"antecedentes", re.I), "2.2 Investigaciones antecedentes"),
    (re.compile(r"definicion de terminos|glosario", re.I), "2.4 Definición de términos básicos"),
    (re.compile(r"justificacion", re.I), "1.4 Justificación del estudio"),
    (re.compile(r"importancia del estudio", re.I), "1.3 Importancia del estudio"),
    (re.compile(r"bases? teoric|marco teorico", re.I), "2.3 Base teórica (Variables)"),
    (re.compile(r"realidad problematica|formulacion del problema|"
                r"planteamiento del problema", re.I), "1.1 Descripción y delimitación"),
]

# Una lista de referencias son muchas entradas "Autor, A. (2020)." seguidas.
_RE_ENTRADA_REFERENCIA = re.compile(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+,\s*[A-Z]\.\s*\(\d{4}\)")


def _pista_lexica(texto: str) -> str | None:
    """Sección sugerida por marcadores inequívocos del texto (o None)."""
    normalizado = _norm(texto)
    if len(_RE_ENTRADA_REFERENCIA.findall(texto)) >= 2:
        return "III. Referencias bibliográficas"

    votos: Counter = Counter()
    for patron, seccion in _PISTAS_LEXICAS:
        aciertos = len(patron.findall(normalizado))
        if aciertos:
            votos[seccion] += aciertos
    if not votos:
        return None
    return votos.most_common(1)[0][0]


def _z_por_seccion(matriz: list[list[float]]) -> list[list[float]]:
    """Normaliza cada COLUMNA (sección) a z-score.

    Corrige el efecto *hub* de los embeddings: algunas secciones —«Instrumentos
    de recolección» sobre todo— se parecen un poco a todo y ganaban el argmax
    crudo en 5 de 8 bloques de prueba. Comparando cada sección consigo misma a
    lo largo del documento, ese sesgo constante se cancela.
    """
    if not matriz:
        return matriz
    columnas = list(zip(*matriz))
    medias = [sum(c) / len(c) for c in columnas]
    desvios = []
    for col, media in zip(columnas, medias):
        var = sum((x - media) ** 2 for x in col) / len(col)
        desvios.append(var ** 0.5 or 1e-9)
    return [
        [(fila[j] - medias[j]) / desvios[j] for j in range(len(fila))]
        for fila in matriz
    ]


def clasificar_semantica(
    bloques: list[tuple[int, str]],
    embeddings,
) -> list[tuple[str, str, int]]:
    """Asigna a cada bloque la sección de la rúbrica a la que pertenece.

    Es la red de seguridad final: sin nombre de sección no hay ítems de rúbrica
    que mapear, y el proyecto quedaría sin evaluar. Combina dos señales gratuitas
    —marcadores léxicos del dominio y embeddings ya cargados en memoria—, así que
    no cuesta ni una llamada al LLM.
    """
    if not bloques:
        return []

    nombres = [s["nombre"] for s in SECCIONES_TESIS]
    consultas = [f"{s['nombre']}. {s['query']}" for s in SECCIONES_TESIS]

    matriz: list[list[float]] = []
    try:
        # multilingual-e5 es asimétrico: las secciones son la CONSULTA y los
        # bloques del proyecto el PASAJE. Invertirlo degrada la similitud.
        vec_secciones = [embeddings.embed_query(c) for c in consultas]
        vec_bloques = embeddings.embed_documents([t for _, t in bloques])
        matriz = [[sum(x * y for x, y in zip(b, v)) for v in vec_secciones] for b in vec_bloques]
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"Embeddings no disponibles al clasificar: {exc}")

    z = _z_por_seccion(matriz) if matriz else []

    agrupado: dict[str, list[tuple[int, str]]] = {}
    for i, (orden, texto) in enumerate(bloques):
        destino = _pista_lexica(texto)
        if destino is None and z:
            mejor = max(range(len(nombres)), key=lambda j: z[i][j])
            # Un bloque que no destaca en ninguna sección (portada, anexos,
            # tablas sueltas) se deja aparte en vez de contaminar la rúbrica.
            destino = nombres[mejor] if z[i][mejor] >= 0.30 else None
        agrupado.setdefault(destino or "Documento (sin clasificar)", []).append((orden, texto))

    grupos = [
        (nombre, "\n\n".join(t for _, t in sorted(partes)), min(o for o, _ in partes))
        for nombre, partes in agrupado.items()
    ]
    grupos.sort(key=lambda g: g[2])
    logger.info(
        f"Clasificación semántica: {len(bloques)} bloques → {len(grupos)} secciones "
        f"({', '.join(n for n, _, _ in grupos[:5])}…)"
    )
    return grupos


# ── Agrupación por anclas ────────────────────────────────────────────────────

def _posicion_encabezado(texto: str, nombre: str) -> int:
    """Dónde empieza `nombre` dentro de `texto` (-1 si no aparece)."""
    idx = texto.find(nombre)
    if idx >= 0:
        return idx
    normalizado = re.sub(r'\s+', ' ', nombre).strip()
    idx = texto.find(normalizado)
    if idx >= 0:
        return idx
    m_pref = re.match(r'^(\d[\d\.]*)', normalizado)
    if m_pref:
        prefijo = m_pref.group(1).rstrip('.')
        m = re.search(r'(?:(?<=\n)|^)' + re.escape(prefijo) + r'[.\s]', texto)
        if m:
            pos = m.start()
            return pos + (1 if pos < len(texto) and texto[pos] == '\n' else 0)
    return -1


def agrupar_por_anclas(
    bloques: list[tuple[int, str]],
    anclas: dict[str, int],
) -> list[tuple[str, str, int]]:
    """Reparte el contenido entre las secciones ancladas, cortando dentro del
    bloque cuando varias secciones comparten la misma página."""
    if not anclas or not bloques:
        return []

    ordenadas = sorted(anclas.items(), key=lambda x: x[1])
    acumulado: dict[str, list[str]] = {nombre: [] for nombre, _ in ordenadas}
    asignados = 0

    for numero, texto in sorted(bloques):
        aqui = [n for n, o in ordenadas if o == numero]

        if not aqui:
            anterior = None
            for nombre, orden in reversed(ordenadas):
                if orden <= numero:
                    anterior = nombre
                    break
            if anterior is not None:
                acumulado[anterior].append(texto)
                asignados += 1
            continue

        previa = None
        for nombre, orden in reversed(ordenadas):
            if orden < numero:
                previa = nombre
                break

        posiciones = {}
        for nombre in aqui:
            pos = _posicion_encabezado(texto, nombre)
            if pos >= 0:
                posiciones[nombre] = pos

        if posiciones:
            ordenadas_pos = sorted(posiciones.items(), key=lambda x: x[1])
            if ordenadas_pos[0][1] > 0 and previa is not None:
                anterior = texto[:ordenadas_pos[0][1]].strip()
                if anterior:
                    acumulado[previa].append(anterior)
            for i, (nombre, pos) in enumerate(ordenadas_pos):
                fin = ordenadas_pos[i + 1][1] if i + 1 < len(ordenadas_pos) else len(texto)
                fragmento = texto[pos:fin].strip()
                if fragmento:
                    acumulado[nombre].append(fragmento)
        else:
            acumulado[aqui[-1]].append(texto)
        asignados += 1

    if asignados == 0:
        return []

    grupos = [
        (nombre, "\n\n".join(acumulado[nombre]).strip(), orden)
        for nombre, orden in ordenadas
        if "".join(acumulado[nombre]).strip()
    ]
    return grupos


# ── Entrada pública ──────────────────────────────────────────────────────────

def resolver_estructura(extraido, embeddings=None) -> ResultadoEstructura:
    """Devuelve las secciones del proyecto usando la mejor señal disponible."""
    resultado = ResultadoEstructura()
    bloques = list(extraido.bloques)

    # El índice nunca es contenido evaluable, venga de donde venga el documento.
    if extraido.formato == "pdf":
        bloques, indice = separar_indice(bloques)
    else:
        indice = {}
    if not bloques:
        bloques = list(extraido.bloques)

    # 1. Estructura nativa (estilos de Word, marcadores del PDF, Markdown).
    if extraido.estructura:
        grupos = agrupar_por_anclas(bloques, extraido.estructura)
        if grupos:
            resultado.grupos = grupos
            resultado.origen = extraido.origen_estructura
            resultado.estructura = {n: o for n, _, o in grupos}
            return _con_caratula(resultado, bloques)

    # 2. Encabezados escritos en el cuerpo.
    encabezados = detectar_encabezados(bloques)
    if len(encabezados) >= 2:
        grupos = agrupar_por_anclas(bloques, encabezados)
        if grupos:
            resultado.grupos = grupos
            resultado.origen = "encabezados_cuerpo"
            resultado.estructura = {n: o for n, _, o in grupos}
            return _con_caratula(resultado, bloques)

    # 3. Índice con puntos guía, calibrando el desfase de páginas.
    if indice:
        calibrada, offset = calibrar_indice(bloques, indice)
        grupos = agrupar_por_anclas(bloques, calibrada)
        if grupos:
            resultado.grupos = grupos
            resultado.origen = "indice_calibrado" if offset else "indice"
            resultado.estructura = {n: o for n, _, o in grupos}
            if offset:
                resultado.avisos.append(
                    f"El índice de tu documento venía desfasado {offset:+d} páginas "
                    "respecto al archivo; lo ajusté automáticamente."
                )
            return _con_caratula(resultado, bloques)

    # 4. Red de seguridad: clasificación semántica contra la rúbrica.
    if embeddings is not None:
        grupos = clasificar_semantica(bloques, embeddings)
        if grupos:
            resultado.grupos = grupos
            resultado.origen = "semantica"
            resultado.estructura = {n: o for n, _, o in grupos}
            resultado.avisos.append(
                "Tu documento no traía encabezados ni índice reconocibles, así que "
                "identifiqué las secciones por su contenido. Numerar los títulos "
                "(«1.2 Objetivos») hará la evaluación más precisa."
            )
            return resultado

    resultado.grupos = [("Documento completo", "\n\n".join(t for _, t in bloques), 1)]
    resultado.estructura = {"Documento completo": 1}
    resultado.origen = "ninguna"
    return resultado


def _con_caratula(resultado: ResultadoEstructura, bloques: list[tuple[int, str]]) -> ResultadoEstructura:
    """Rescata los preliminares anteriores a la primera sección.

    La carátula lleva el TÍTULO del proyecto, que la rúbrica evalúa con tres
    ítems. Como no aparece en ningún índice, se perdía entera.
    """
    if not resultado.grupos or not bloques:
        return resultado

    primer_orden = min(o for _, _, o in resultado.grupos)
    previos = [(o, t) for o, t in bloques if o < primer_orden]
    if not previos:
        return resultado

    texto = "\n\n".join(t for _, t in sorted(previos)).strip()
    if len(texto) < 40:
        return resultado

    nombre = "Título del proyecto"
    orden = min(o for o, _ in previos)
    resultado.grupos.insert(0, (nombre, texto, orden))
    resultado.estructura[nombre] = orden
    logger.info(f"Carátula/preliminares rescatados como «{nombre}» ({len(texto)} chars)")
    return resultado
