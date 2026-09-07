"""
Configuración central del sistema de mentoría académica UPAO.

Contiene:
  - RUBRICA_ITEMS_UPAO: Los 33 ítems exactos de la ficha oficial de evaluación
  - SECCION_ITEMS_MAP:  Qué ítems evaluar según la sección elegida
  - SECCIONES_TESIS:    Opciones del menú + query de búsqueda para ChromaDB
  - LIBRARY_CHROMA_PATH / BOOKS_PRELOAD_DIR: Paths para la biblioteca de libros
"""

import os
import re
import unicodedata

_ROOT = os.path.dirname(os.path.dirname(__file__))
LIBRARY_CHROMA_PATH = os.path.join(_ROOT, "chroma_db", "biblioteca")
BOOKS_PRELOAD_DIR   = os.path.join(_ROOT, "books")


RUBRICA_ITEMS_UPAO: dict[int, str] = {
    1:  "El título es claro, conciso y refleja fielmente el contenido y el propósito de la investigación.",
    2:  "El título articula las variables, espacio y tiempo de la investigación.",
    3:  "El estudio se enmarca en la línea de investigación que promueve el programa de estudios.",

    4:  "El problema central del estudio describe con claridad la realidad social, económica, cultural, científica o tecnológica que motiva la investigación.",
    5:  "El problema central del estudio recoge el estado de la investigación (antecedentes) de las variables de estudio.",
    6:  "El objetivo general guarda relación con el problema.",
    7:  "Los objetivos específicos derivan del objetivo general.",
    8:  "Se explica por qué el estudio es relevante y qué aportaciones hará al campo de investigación.",
    9:  "El problema está claramente formulado.",
    10: "Se detalla la justificación de la investigación, precisando cómo contribuirá al conocimiento existente y su impacto potencial.",

    11: "Los antecedentes guardan relación con el problema de investigación.",
    12: "Las bases teóricas / científicas proporcionan una base sólida con teorías, modelos y conceptos relevantes.",
    13: "La definición de términos básicos define claramente términos técnicos y específicos para evitar confusiones.",
    14: "Las citas textuales o de paráfrasis son concordantes con la naturaleza de las variables.",
    15: "Los textos y autores citados se encuentran en las referencias bibliográficas.",
    16: "Los autores asumen una postura crítica y no solo copian las ideas de los autores citados.",
    17: "Se citan a los autores conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",

    18: "Las hipótesis guardan relación con el problema de investigación.",
    19: "Si hay hipótesis específicas, éstas derivan de problemas derivados.",
    20: "Es clara la definición operacional de las variables: dimensiones o indicadores.",
    21: "La matriz de consistencia asegura que todos los elementos del estudio están alineados.",

    22: "El tipo de investigación y el método de investigación guardan relación con el problema de investigación.",
    23: "Se presenta el esquema (gráfico) del diseño de investigación.",
    24: "Define claramente la población y muestra de estudio. Si fuera el caso, se hace uso del cálculo estadístico para el tamaño y selección de la muestra.",
    25: "Describe los instrumentos de recolección de datos de manera detallada en correspondencia con el problema y diseño metodológico.",
    26: "Especifica el procedimiento de ejecución del estudio.",
    27: "Especifica las técnicas de procesamiento y análisis de datos apropiadas conforme al problema y naturaleza de las variables.",

    28: "El cronograma detalla todas las actividades y plazos para el desarrollo del proyecto.",
    29: "Se detallan claramente los recursos humanos y materiales para ejecutar el proyecto.",
    30: "El presupuesto estima los costos de los bienes y servicios requeridos para ejecutar el proyecto.",
    31: "Se precisa las fuentes de financiamiento para ejecutar el proyecto: propia y/o externas.",

    32: "Se encuentran incorporados todos los autores citados.",
    33: "La redacción de las referencias bibliográficas es conforme a las normas internacionales (HARVARD, VANCOUVER, APA, ISO).",
}

TABLA_VIGESIMAL: list[tuple[int, int, int]] = [
    (96, 99, 20), (91, 95, 19), (86, 90, 18), (81, 85, 17),
    (76, 80, 16), (71, 75, 15), (66, 70, 14), (61, 65, 13),
    (56, 60, 12), (51, 55, 11), (46, 50, 10), (41, 45,  9),
    (36, 40,  8), (31, 35,  7), (26, 30,  6), (21, 25,  5),
    (0,  20,  0),
]


def puntaje_a_nota(puntaje: int) -> int:
    """Convierte puntaje 0-99 a nota vigesimal 0-20 según tabla UPAO."""
    for pmin, pmax, nota in TABLA_VIGESIMAL:
        if pmin <= puntaje <= pmax:
            return nota
    return 0


# ── Plantilla UPAO: dos árboles de numeración en el MISMO documento ─────────
#
# El proyecto oficial se parte en «I GENERALIDADES» (portada administrativa:
# 1 Título · 2 Equipo investigador · 3 Tipo de investigación · 4 Línea ·
# 5 Unidad académica · 6 Institución · 7 Duración · 8 Horas) y «II PLAN DE
# INVESTIGACIÓN» (1 Planteamiento · 2 Marco teórico · 3 Hipótesis y variables ·
# 4 Marco metodológico · 5 Aspectos administrativos · 6 Referencias · 7 Anexos).
# Los números se repiten, así que el mapeo por PREFIJO cruzaba las dos mitades:
#   «2.2 Asesor»                        → «2.2 Investigaciones antecedentes» (11, 15)
#   «3.1 De acuerdo con la orientación» → «3.1–3.2 Hipótesis»                (18, 19)
#   «5.1 Programa de estudio»           → «5. Aspectos administrativos»      (28-31)
#   «1.5 Limitaciones del estudio»      → «1. Título del proyecto» (por ancestro «1»)
# Es decir: los datos del asesor se calificaban como antecedentes y las
# limitaciones como título. Verificado en los 10 proyectos REP_ISIA de la
# facultad: la estructura es idéntica en todos, no es una rareza de uno.
#
# La portada no tiene ítems de rúbrica propios, pero NO es ruido descartable: la
# línea de investigación y el programa son la ÚNICA evidencia del ítem 3 («el
# estudio se enmarca en la línea que promueve el programa»), que hasta ahora se
# puntuaba leyendo solo el título. Por eso esas dos se enrutan al título y el
# resto se agrupa aparte, disponible como contexto pero sin calificar.
PORTADA_UPAO = "I. Generalidades (portada)"

# (prefijo del árbol de GENERALIDADES) → palabras que deben aparecer en el
# encabezado. El prefijo es lo que desambigua: «3 Tipo de investigación» es
# portada, «4.1 Tipo de investigación» es el marco metodológico y sí se califica.
_PORTADA_UPAO: dict[str, tuple[str, ...]] = {
    "2":   ("equipo", "investigador"),
    "2.1": ("autor",),
    "2.2": ("asesor",),
    "3":   ("tipo", "investigacion"),
    "3.1": ("acuerdo", "orientacion"),
    "3.2": ("acuerdo", "tecnica"),
    "4":   ("linea", "investigacion"),
    "5":   ("unidad", "academica"),
    "5.1": ("programa", "estudio"),
    "5.2": ("facultad",),
    "5.3": ("universidad",),
    "6":   ("institucion", "localidad"),
    "7":   ("duracion",),
    "7.1": ("fecha", "inicio"),
    "7.2": ("fecha", "termino"),
    "8":   ("horas", "dedicadas"),
}

# Las dos secciones de portada que SÍ son evidencia de rúbrica (ítem 3).
_PORTADA_AL_TITULO = {"4", "5.1"}


def _clave_portada_upao(seccion: str) -> str | None:
    """Clave de rúbrica de una sección de «I GENERALIDADES», o None si no lo es."""
    prefijo = _prefijo_num(seccion)
    requeridas = _PORTADA_UPAO.get(prefijo)
    if not requeridas:
        return None
    texto = unicodedata.normalize("NFKD", seccion).encode("ascii", "ignore").decode().lower()
    if not all(palabra in texto for palabra in requeridas):
        return None
    return "1. Título del proyecto" if prefijo in _PORTADA_AL_TITULO else PORTADA_UPAO


SECCION_ITEMS_MAP: dict[str, list[int]] = {
    "1. Título del proyecto":                    [1, 2, 3],
    "1.1 Descripción y delimitación":            [4, 5],
    "1.1.2 Problema central (formulación)":      [4, 5, 9],
    "1.2 Objetivos (General y Específicos)":     [6, 7],
    "1.3 Importancia del estudio":               [8],
    "1.4 Justificación del estudio":             [10],
    "2.2 Investigaciones antecedentes":          [11, 15],
    "2.3 Base teórica (Variables)":              [12, 14, 16, 17],
    "2.4 Definición de términos básicos":        [13],
    "3.1–3.2 Hipótesis":                         [18, 19],
    "3.3 Variables (Operacionalización)":        [20],
    "3.4 Matriz de consistencia":                [21],
    "4.1–4.3 Tipo, Método y Diseño":             [22, 23],
    "4.4 Población y muestra":                   [24],
    "4.5 Instrumentos de recolección de datos":  [25],
    "4.6 Procedimiento de ejecución":            [26],
    "4.7 Análisis de datos":                     [27],
    "5. Aspectos administrativos":               [28, 29, 30, 31],
    "III. Referencias bibliográficas":           [32, 33],
    # Sin ítems propios, pero con clave propia a propósito: son las dos secciones
    # que el mapeo por número mandaba a la unidad equivocada. Ver PORTADA_UPAO.
    PORTADA_UPAO:                                [],
    "1.5 Limitaciones del estudio":              [],
}

SECCIONES_TESIS: list[dict] = [
    {
        "nombre": "1. Título del proyecto",
        "query":  "título proyecto investigación variables espacio tiempo línea investigación",
    },
    {
        "nombre": "1.1 Descripción y delimitación",
        "query":  "descripción problema central delimitación realidad antecedentes variables",
    },
    {
        "nombre": "1.1.2 Problema central (formulación)",
        "query":  "formulación problema central estudio planteamiento pregunta investigación",
    },
    {
        "nombre": "1.2 Objetivos (General y Específicos)",
        "query":  "objetivo general específicos investigación derivan problema",
    },
    {
        "nombre": "1.3 Importancia del estudio",
        "query":  "importancia relevancia aportaciones campo investigación estudio",
    },
    {
        "nombre": "1.4 Justificación del estudio",
        "query":  "justificación teórica práctica metodológica social investigación",
    },
    {
        "nombre": "2.2 Investigaciones antecedentes",
        "query":  "antecedentes investigaciones previas estudios relacionados citados",
    },
    {
        "nombre": "2.3 Base teórica (Variables)",
        "query":  "base teórica científica modelos teorías conceptos citas paráfrasis",
    },
    {
        "nombre": "2.4 Definición de términos básicos",
        "query":  "definición términos básicos técnicos específicos glosario",
    },
    {
        "nombre": "3.1–3.2 Hipótesis",
        "query":  "hipótesis general específicas supuestos básicos problema relación",
    },
    {
        "nombre": "3.3 Variables (Operacionalización)",
        "query":  "variables definición operacional dimensiones indicadores ítems escala",
    },
    {
        "nombre": "3.4 Matriz de consistencia",
        "query":  "matriz de consistencia alineación elementos problema objetivo hipótesis variable",
    },
    {
        "nombre": "4.1–4.3 Tipo, Método y Diseño",
        "query":  "tipo investigación método diseño esquema gráfico investigación",
    },
    {
        "nombre": "4.4 Población y muestra",
        "query":  "población muestra estudio cálculo estadístico selección criterios",
    },
    {
        "nombre": "4.5 Instrumentos de recolección de datos",
        "query":  "instrumentos técnicas recolección datos correspondencia diseño",
    },
    {
        "nombre": "4.6 Procedimiento de ejecución",
        "query":  "procedimiento ejecución estudio pasos etapas actividades",
    },
    {
        "nombre": "4.7 Análisis de datos",
        "query":  "técnicas procesamiento análisis datos estadísticas naturaleza variables",
    },
    {
        "nombre": "5. Aspectos administrativos",
        "query":  "cronograma actividades recursos humanos materiales presupuesto financiamiento",
    },
    {
        "nombre": "III. Referencias bibliográficas",
        "query":  "referencias bibliográficas autores citados normas APA VANCOUVER HARVARD",
    },
]


_STOP_CFG = {
    "de", "del", "la", "el", "los", "las", "un", "una", "y", "e", "o", "u",
    "con", "en", "al", "para", "por", "que", "se", "su", "sus", "es", "son",
    "a", "ante", "bajo", "desde", "sin", "sobre", "tras", "como",
    "estudio", "investigacion", "proyecto",
}


def _stem_token(t: str) -> str:
    """Stemming ligero ES: une singular/plural recortando solo la 's' final.

    Los plurales relevantes aquí son de '+s' (variable→variables, término→términos,
    objetivo→objetivos), así que recortar 'es' rompería 'variables'→'variabl'≠'variable'.
    """
    if len(t) > 4 and t.endswith("s"):
        return t[:-1]
    return t


def _kw_seccion(texto: str) -> set[str]:
    """Palabras significativas de un nombre de sección (sin números, acentos, ni stop words)."""
    sin_acentos = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    tokens = re.sub(r'[\d\.\,\-–\(\)\[\]/]', ' ', sin_acentos.lower()).split()
    return {_stem_token(t) for t in tokens if len(t) > 2 and t not in _STOP_CFG}


def _prefijo_num(nombre: str) -> str:
    """Prefijo numérico de una sección: '2.1. Título' → '2.1'."""
    m = re.match(r'^(\d[\d\.]*)', nombre.strip())
    return m.group(1).rstrip('.') if m else ""


def _prefijos_rango(seccion: str) -> list[str]:
    """
    Prefijos de una sección, expandiendo rangos explícitos.
    '4.1–4.3 Tipo, Método y Diseño' → ['4.1', '4.2', '4.3']
    '1.2 Objetivos (General y Específicos)' → ['1.2']
    """
    m = re.match(r'^(\d[\d\.]*)\s*[–\-]\s*(\d[\d\.]*)', seccion.strip())
    if not m:
        p = _prefijo_num(seccion)
        return [p] if p else []
    ini = m.group(1).rstrip('.')
    fin = m.group(2).rstrip('.')
    pi = [int(x) for x in ini.split('.')]
    pf = [int(x) for x in fin.split('.')]
    if len(pi) != len(pf) or not pi or pi[:-1] != pf[:-1]:
        return [ini]
    padre = '.'.join(str(x) for x in pi[:-1])
    return [f"{padre}.{i}" if padre else str(i) for i in range(pi[-1], pf[-1] + 1)]


def _mejor_semantica(seccion: str) -> tuple[str | None, float]:
    """Mejor clave de SECCION_ITEMS_MAP por solapamiento de palabras clave.

    Se mide con Jaccard y con CONTENCIÓN (intersección / conjunto más pequeño),
    y se devuelve la mayor de las dos. La contención es la que salva el caso
    real que rompía la evaluación: un estudiante titula «1.3 OBJETIVOS» y la
    clave de la plantilla es «1.2 Objetivos (General y Específicos)». El Jaccard
    ahí es 1/3 = 0.33 —solo porque la plantilla añade dos palabras—, así que no
    llegaba al umbral de semántica fuerte y mandaba el PREFIJO numérico: sus
    objetivos se mapeaban a «1.3 Importancia del estudio» y los ítems 6 y 7
    salían «ausente» con 0 puntos pese a estar escritos. Con contención el
    solapamiento vale 1.0 y la semántica manda, que es lo correcto.
    """
    kw = _kw_seccion(seccion)
    if not kw:
        return None, 0.0
    mejor_key: str | None = None
    mejor: tuple[float, float] = (0.0, 0.0)
    fuerza = 0.0
    for k in SECCION_ITEMS_MAP:
        kw_k = _kw_seccion(k)
        inter = len(kw & kw_k)
        if inter == 0:
            continue
        jaccard = inter / len(kw | kw_k)
        contencion = inter / min(len(kw), len(kw_k))
        # El Jaccard desempata: varias claves pueden CONTENER la misma palabra
        # («Variables» está en «Base teórica (Variables)» y en «Variables
        # (Operacionalización)»), y sin desempate ganaba la primera del
        # diccionario. El Jaccard premia a la clave más ajustada.
        candidato = (max(jaccard, contencion), jaccard)
        if candidato > mejor:
            mejor = candidato
            mejor_key = k
            # La contención solo cuenta como semántica FUERTE cuando es TOTAL.
            # A medias es una palabra genérica compartida, no un significado
            # común: «2.3.1 Aplicación web con analítica de DATOS» contra
            # «4.7 Análisis de DATOS» da 0.5 y, con el umbral en 0.5, esa
            # subsección del marco teórico se calificaba como las técnicas de
            # procesamiento de datos (ítem 27). El caso que la contención vino a
            # resolver («1.3 OBJETIVOS» → «1.2 Objetivos (General y
            # Específicos)») es contención 1.0 y sigue ganando.
            fuerza = max(jaccard, contencion if contencion >= 1.0 else 0.0)
    return mejor_key, fuerza


def _seccion_rubrica_para(seccion: str) -> str | None:
    """
    Clave de SECCION_ITEMS_MAP que gobierna la rúbrica de `seccion` (o None).

    El SIGNIFICADO manda sobre el NÚMERO: si la tesis usa una numeración distinta
    a la plantilla UPAO (p. ej. 2.2 = Base teórica en lugar de Antecedentes), el
    prefijo numérico llevaría a la sección equivocada. Por eso:
      1. Coincidencia exacta de nombre.
      2. Semántica FUERTE (Jaccard ≥ 0.5) si discrepa del prefijo → manda la semántica.
      3. Prefijo numérico exacto.
      4. Ancestro numérico subiendo niveles ('5.2.1' → '5.2' → '5').
      5. Semántica débil (cualquier solapamiento).
    """
    if seccion in SECCION_ITEMS_MAP:
        return seccion

    # La portada se resuelve antes que nada: su numeración choca de frente con la
    # del plan de investigación y cualquier heurística posterior elige mal.
    portada = _clave_portada_upao(seccion)
    if portada:
        return portada

    prefijo_num = _prefijo_num(seccion) or None
    cand_prefijo: str | None = None
    if prefijo_num:
        for k in SECCION_ITEMS_MAP:
            if _prefijo_num(k) == prefijo_num:
                cand_prefijo = k
                break

    cand_sem, jaccard = _mejor_semantica(seccion)

    # La semántica fuerte corrige numeraciones distintas a UPAO.
    if cand_sem and jaccard >= 0.5 and cand_sem != cand_prefijo:
        return cand_sem
    if cand_prefijo:
        return cand_prefijo

    # El ANCESTRO numérico va ANTES que la semántica débil: que «2.3.1» viva
    # dentro de «2.3» es un hecho de la estructura del documento, mientras que un
    # solapamiento de una sola palabra suele ser casualidad. Con el orden
    # anterior, «2.3.1 Aplicación web con analítica de DATOS» —marco teórico—
    # terminaba en «4.7 Análisis de DATOS» y se calificaba con el ítem 27.
    if prefijo_num:
        partes = prefijo_num.split('.')
        for corte in range(len(partes) - 1, 0, -1):
            padre = '.'.join(partes[:corte])
            for k in SECCION_ITEMS_MAP:
                if _prefijo_num(k) == padre:
                    return k

    if cand_sem:
        return cand_sem

    return None


def _buscar_items_seccion(seccion: str) -> list[int]:
    """Ítems de SECCION_ITEMS_MAP que aplican a `seccion` (vía la clave de rúbrica)."""
    key = _seccion_rubrica_para(seccion)
    return list(SECCION_ITEMS_MAP.get(key, [])) if key else []


def prefijos_evaluacion_para_seccion(seccion: str) -> list[str]:
    """
    Prefijos numéricos que delimitan la UNIDAD de evaluación de `seccion`,
    anclada a la sección de rúbrica que la gobierna.

    Por qué: el menú ofrece encabezados crudos del TOC (p.ej. '1.2.1 Objetivo
    general'), pero la rúbrica define la unidad un nivel arriba ('1.2 Objetivos
    (General y Específicos)', ítems 6 y 7). Evaluar solo la hoja deja fuera a la
    sub-sección hermana ('1.2.2 Objetivos específicos') y produce falsos errores
    (ej. "faltan objetivos específicos" cuando sí existen). Anclando al prefijo
    de la rúbrica, el RAG recupera TODA la unidad.

    Devuelve:
      - los prefijos del grupo de rúbrica cuando éste es ancestro (o igual) de la
        hoja elegida (ej. '1.2.1' → ['1.2']; '4.2' → ['4.1','4.2','4.3']);
      - los prefijos propios de la sección en caso contrario (sección ya amplia,
        o sin rúbrica resoluble).
    """
    propios = _prefijos_rango(seccion)
    key = _seccion_rubrica_para(seccion)
    if not key:
        return propios

    rubrica_prefijos = _prefijos_rango(key)
    hoja = _prefijo_num(seccion)
    if not hoja or not rubrica_prefijos:
        return propios or rubrica_prefijos

    for rp in rubrica_prefijos:
        if hoja == rp or hoja.startswith(rp + "."):
            return rubrica_prefijos

    return propios


# Escala de calificación POR ÍTEM (0 a ESCALA_MAX) — la de la FICHA OFICIAL UPAO:
# 3=Excelente, 2=Bueno, 1=Regular, 0=Insuficiente. Con 33 ítems el máximo es 99,
# consistente con la TABLA_VIGESIMAL (0-99 → nota 0-20) de la propia ficha.
ESCALA_MAX = 3

ESCALA_ETIQUETAS_UPAO: dict[int, str] = {
    3: "Excelente",
    2: "Bueno",
    1: "Regular",
    0: "Insuficiente",
}

# Grupos de la ficha oficial UPAO (encabezados bajo los que aparecen los 33 ítems).
# Solo para MOSTRAR la rúbrica al estudiante; el mapeo a las secciones reales del
# proyecto lo resuelve _seccion_rubrica_para contra el TOC de cada tesis.
RUBRICA_GRUPOS_UPAO: list[tuple[str, list[int]]] = [
    ("TÍTULO",                      [1, 2, 3]),
    ("PLANTEAMIENTO DEL PROBLEMA",  [4, 5, 6, 7, 8, 9, 10]),
    ("MARCO TEÓRICO",               [11, 12, 13, 14, 15, 16, 17]),
    ("HIPÓTESIS Y VARIABLES",       [18, 19, 20, 21]),
    ("MARCO METODOLÓGICO",          [22, 23, 24, 25, 26, 27]),
    ("ASPECTOS ADMINISTRATIVOS",    [28, 29, 30, 31]),
    ("REFERENCIAS BIBLIOGRÁFICAS",  [32, 33]),
]


def get_items_texto_para_seccion(seccion: str) -> str:
    """Genera la tabla de ítems relevantes para una sección, lista para inyectar en el prompt."""
    items_nums = _buscar_items_seccion(seccion) or list(RUBRICA_ITEMS_UPAO.keys())
    lineas = [f"| N° | Ítem de la Rúbrica UPAO | Puntaje (0-{ESCALA_MAX}) |",
              "|----|-----------------------------|--------------|"]
    for num in items_nums:
        desc = RUBRICA_ITEMS_UPAO.get(num, "Ítem sin descripción")
        lineas.append(f"| {num:02d} | {desc} | ___ |")
    return "\n".join(lineas)


def get_puntaje_maximo_seccion(seccion: str) -> int:
    """Puntaje máximo posible para la sección (nro. de ítems × ESCALA_MAX)."""
    return len(_buscar_items_seccion(seccion)) * ESCALA_MAX


DEPENDENCIAS_SECCIONES: dict[str, list[str]] = {
    "1. Título del proyecto": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
        "3.1–3.2 Hipótesis",
        "2.3 Base teórica (Variables)",
        "4.1–4.3 Tipo, Método y Diseño",
    ],
    "1.1 Descripción y delimitación": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
    ],
    "1.1.2 Problema central (formulación)": [
        "1. Título del proyecto",
        "1.2 Objetivos (General y Específicos)",
        "3.1–3.2 Hipótesis",
    ],
    "1.2 Objetivos (General y Específicos)": [
        "1.1.2 Problema central (formulación)",
        "3.1–3.2 Hipótesis",
        "3.3 Variables (Operacionalización)",
    ],
    "1.3 Importancia del estudio": [
        "1.1.2 Problema central (formulación)",
    ],
    "1.4 Justificación del estudio": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
    ],
    "2.2 Investigaciones antecedentes": [
        "1.1.2 Problema central (formulación)",
        "3.3 Variables (Operacionalización)",
    ],
    "2.3 Base teórica (Variables)": [
        "3.3 Variables (Operacionalización)",
        "1. Título del proyecto",
    ],
    "2.4 Definición de términos básicos": [
        "3.3 Variables (Operacionalización)",
        "2.3 Base teórica (Variables)",
    ],
    "3.1–3.2 Hipótesis": [
        "1.1.2 Problema central (formulación)",
        "1.2 Objetivos (General y Específicos)",
        "3.3 Variables (Operacionalización)",
    ],
    "3.3 Variables (Operacionalización)": [
        "3.4 Matriz de consistencia",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
    "3.4 Matriz de consistencia": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.7 Análisis de datos",
    ],
    "4.1–4.3 Tipo, Método y Diseño": [
        "3.3 Variables (Operacionalización)",
        "3.4 Matriz de consistencia",
        "4.4 Población y muestra",
    ],
    "4.4 Población y muestra": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
        "3.3 Variables (Operacionalización)",
    ],
    "4.5 Instrumentos de recolección de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
    ],
    "4.6 Procedimiento de ejecución": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
        "4.5 Instrumentos de recolección de datos",
    ],
    "4.7 Análisis de datos": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
    "5. Aspectos administrativos": [
        "4.1–4.3 Tipo, Método y Diseño",
        "4.4 Población y muestra",
        "4.6 Procedimiento de ejecución",
    ],
    "III. Referencias bibliográficas": [
        "3.3 Variables (Operacionalización)",
        "4.1–4.3 Tipo, Método y Diseño",
        "4.5 Instrumentos de recolección de datos",
    ],
}

MAX_ITERACIONES_DEFAULT  = 3
MAX_RONDAS_DEBATE_DEFAULT = 2
