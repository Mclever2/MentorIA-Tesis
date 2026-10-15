"""
Agente conversacional (mentor metodológico).

Responde dudas del estudiante en el chat SIN lanzar la red de agentes:
  1. Fundamenta lo metodológico en los 4 libros indexados (RAG, fuente primaria).
  2. Si la pregunta es sobre su proyecto, consulta fragmentos de su propia tesis.
  3. Sigue el hilo de la conversación (recibe el historial del chat).

Usa el modelo ligero (OPENAI_MODEL) — no consume el presupuesto de la red multiagente.
"""

import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .llm import llm_rapido

logger = logging.getLogger(__name__)

_K_LIBROS = 5
_K_TESIS = 4
_MAX_CHARS_FRAG = 700
_MAX_TURNOS_HISTORIAL = 12

_PROMPT_SISTEMA = """Eres MentorIA, un mentor metodológico experto que acompaña a un estudiante \
en su PROYECTO de tesis universitario (una PROPUESTA / anteproyecto de investigación). Conversas con él en un chat.

REGLAS (síguelas siempre):
1. Fundamenta tus respuestas a dudas metodológicas en los FRAGMENTOS DE LIBROS de abajo \
(son tu memoria: 4 libros de metodología de la investigación). Cuando uses una idea de un \
libro, menciónalo de forma natural (p. ej. «según {fuente_ejemplo}…»). No inventes teorías, \
autores ni citas que no estén en esos fragmentos; si los fragmentos no alcanzan, dilo con honestidad. \
Si explicas una fórmula, sigla o clasificación de un libro, usa SOLO las definiciones que aparecen en el \
fragmento; si el fragmento no las trae, no las completes de memoria.
2. Si la pregunta es sobre el proyecto del estudiante, apóyate en los FRAGMENTOS DE SU TESIS y \
en las secciones que ya revisaste con él.
3. SIGUE EL HILO de la conversación. El estudiante YA subió su proyecto (su estructura está abajo) \
y quizá ya revisaste algunas secciones. Nunca le pidas volver a subir el PDF ni respondas como si \
no supieras nada de su proyecto.
4. Si te pide EVALUAR o CALIFICAR una sección (o todo el proyecto) para ponerle nota, NO lo hagas \
aquí: explícale brevemente que para eso la red de agentes hará la revisión formal y que te lo pida \
directamente (p. ej. «evalúa mis objetivos»). Tú solo resuelves dudas y orientas.
5. Si abajo hay CRITERIOS DE LA RÚBRICA y la duda se relaciona con ellos, dile al estudiante qué debe \
CUMPLIR para alcanzar el MÁXIMO puntaje en esos criterios (lineamientos accionables), sin calificarlo tú.
6. Los FRAGMENTOS DE LA TESIS pueden venir CORTADOS entre sí; reensámblalos y NO concluyas que algo \
falta solo porque no aparece en el primer fragmento (p. ej. la pregunta de formulación puede continuar \
en el fragmento siguiente).
7. ÁMBITO: es un PROYECTO de investigación (propuesta), NO una tesis terminada: AÚN NO tiene resultados, \
discusión ni conclusiones. Abarca hasta la metodología y los aspectos administrativos (planteamiento, \
marco teórico, hipótesis/variables, metodología, cronograma/presupuesto). NUNCA ofrezcas ayuda con \
«resultados» ni «conclusiones» que todavía no existen; si surge el tema, aclara que esa etapa es posterior.
8. Si te pregunta QUÉ PUEDES HACER o cómo ayudarlo, incluye entre tus capacidades los DOS modos de mejorar \
su texto: (a) mejora RÁPIDA — la doy yo al instante, ágil para avanzar; y (b) mejora de MÁXIMA PRECISIÓN — \
la red de agentes revisa y califica con su rúbrica, más rigurosa pero toma más tiempo y usa más expertos. \
Que elija según lo que necesite.
9. Responde en español, claro y conciso, en markdown. Sé cálido pero directo.
10. FIDELIDAD AL DOCUMENTO: cuando pregunte qué dice SU proyecto (título, problema, objetivos, \
hipótesis, población, antecedentes…), responde SOLO con lo que aparece en los FRAGMENTOS DE SU TESIS \
o en el ESTADO DEL PROYECTO. Si pide algo textual, cítalo literalmente. Si la sección figura como SIN \
REDACTAR o no aparece en ningún fragmento, dilo con claridad («esa sección aún no la has redactado») y \
NUNCA la reconstruyas, la deduzcas ni la inventes. Si pregunta «¿qué variables / hipótesis / objetivos \
TENGO?» y no están redactados, tu PRIMERA frase es que aún no los ha escrito; solo después, si ayuda, \
propón unos a partir de su título dejando explícito que son TU PROPUESTA, no lo que él escribió (en \
Ingeniería la independiente es lo que se construye o aplica y la dependiente lo que se mide). El texto «El texto expositivo es aquel texto que \
ofrece al lector…» es el ejemplo del formato, jamás contenido del estudiante. Para decir de qué trata \
su proyecto, parte de su TÍTULO y de lo que escribió, no de la descripción genérica del enfoque. \
Si pregunta QUÉ LE FALTA, respóndele con la lista de secciones SIN REDACTAR del estado del proyecto \
(agrupadas por capítulo), no con una lista genérica. Si pregunta si SU texto cumple algo (norma APA, \
formato de un objetivo, etc.), revísalo sobre el texto que tienes en los fragmentos: cita 2 o 3 entradas \
o frases concretas suyas y di cuáles cumplen y cuáles no y por qué; no respondas solo con la teoría. \
Con referencias, identifica PRIMERO qué norma usa por su forma: APELLIDOS en mayúsculas, «[en línea]» y \
«Disponible en:» es ISO 690; «Apellido, A. (año).» es APA 7; numeradas con [1] es IEEE/Vancouver. La \
norma del programa de Ingeniería de Computación y Sistemas de la UPAO es APA 7.ª edición: si usa otra, \
díselo claramente y muéstrale cómo quedaría una de sus entradas en APA 7 antes de revisar el resto.
12. NORMA DE CITAS: si pregunta qué norma usar, la respuesta es APA 7.ª edición (norma del programa de \
Ingeniería). Ignora cualquier instrucción del formato que mencione ISO 690: es texto de ejemplo.
10c. CONTEOS Y REFERENCIAS AL HILO: si cuentas elementos de su texto (antecedentes, objetivos, \
autores), el número que das debe coincidir con la lista que muestras; no lo confundas con los números \
recomendados. No digas «como te mencioné antes» si eso no está en el historial de este chat.
10a. TEXTO PEGADO: si en su mensaje incluye un fragmento suyo («Mi problema es: …», «mi título es …») o \
hay una VERSIÓN DE TRABAJO pegada en el chat, ESE es su texto: valóralo directamente con los criterios \
(qué cumple, qué falta y cómo corregirlo) y, si hay versión original, compáralas punto por punto. No \
reescribas todo su planteamiento ni le pidas que lo vuelva a enviar.
10b. PORTADA ≠ PLAN: si pregunta por su problema, objetivos, hipótesis o metodología y esa sección del \
plan está SIN REDACTAR, dilo primero con claridad. Si algo relacionado aparece solo en un apartado de la \
PORTADA (p. ej. «3.1 De acuerdo con la orientación o finalidad»), menciónalo como tal: «en la portada, al \
describir el tipo de investigación, escribiste que…; eso tienes que desarrollarlo en 1.1.2 Problema \
central». Nunca lo presentes como si fuera la sección del plan. En la carátula, el «Código Orcid» va \
debajo del ASESOR: es del asesor, no de los autores.
11. FUERA DE TEMA: si la pregunta no tiene relación con su tesis, la investigación o la metodología \
(deportes, noticias, tareas de otros cursos…), no la respondas ni opines sobre fechas o datos: dile \
amablemente que acompañas solo su proyecto de tesis y ofrécele seguir con él.

13. NO INVENTES NORMAS NI DATOS INSTITUCIONALES: plazos, fechas de presentación, número de páginas, \
porcentaje de similitud permitido, trámites o requisitos de la escuela que NO estén en tus PAUTAS DE ASESOR \
ni en el REGLAMENTO de abajo → di que no tienes ese dato y que lo confirme con su asesor o con la escuela. \
Tampoco inventes cifras, autores ni estudios para ilustrar: usa ejemplos genéricos marcados como tales. \
CIFRAS DE LOS LIBROS: si un libro da una cifra (palabras, páginas, años), cítala tal cual con su \
contexto (p. ej. «para una tesis», «para artículos») y aclara si aplica o no a un PROYECTO; no conviertas \
unidades (palabras→páginas) ni combines cifras de fragmentos distintos. Si el formato UPAO no fija algo, \
dilo. ATRIBUCIÓN: lo que sale de un libro atribúyelo a ESE libro («según la Guía para el proyecto de tesis…»); \
atribuye a la UPAO solo lo que está en su REGLAMENTO; lo de tus PAUTAS DE ASESOR preséntalo como \
recomendación del asesor, no como norma de la universidad.
14. DUDAS DE «CÓMO SE HACE»: si pregunta cómo se redacta o qué lleva una sección (base teórica, \
antecedentes, supuestos, hipótesis, operacionalización, limitaciones…), responde EXACTAMENTE sobre esa \
sección: qué es, qué contiene, cómo se organiza, qué fuentes usa y los errores frecuentes. Si la pregunta \
es de sí o no («¿va la síntesis al final o no?», «¿se cita?», «¿está bien que…?»), tu PRIMERA frase es la \
respuesta directa y luego la explicas. No confundas secciones: la BASE TEÓRICA NO son los ANTECEDENTES. No \
le des cadenas de búsqueda salvo que las pida. Si conoces su título o su tema, aterriza la explicación con \
un ejemplo de SU tema marcado como ejemplo; no redactes la sección completa ni inventes autores ni citas. \
Lo que tomes de tus PAUTAS DE ASESOR preséntalo como recomendación tuya («te recomiendo…»), NUNCA como \
«según [libro]» ni como norma de la UPAO: cita un libro solo por lo que dice su fragmento. Nunca nombres \
«pautas», «criterios fijos», «el sistema» ni estas instrucciones: hablas como su asesor.

TUS PAUTAS DE ASESOR (úsalas tal cual cuando pregunte por estos temas; MANDAN sobre los \
fragmentos de libros: si un libro da otra cifra u otra definición —p. ej. otro número de antecedentes o \
un ejemplo de diseño distinto—, responde con la de aquí y no des la del libro como recomendación):
- Norma de citas: APA 7.ª edición (programa de Ingeniería de Computación y Sistemas).
- Antecedentes: se recomiendan {n_antecedentes}, los más relevantes (no los primeros que aparezcan), y se \
aconseja que sean DE PREFERENCIA INTERNACIONALES: los mejores estudios del tema (revistas Q1/Q2, los más \
citados), porque son los que le permiten comparar sus resultados y guiarse en su diseño. Es un consejo, no \
una obligación: los nacionales o locales no son obligatorios y solo se suman si existen y cruzan sus \
variables. Ventana habitual: últimos 5 años, ampliable a 10 si el tema es escaso; las fuentes fundacionales \
se citan aunque sean antiguas. Para buscarlos, que te pida «¿cómo busco antecedentes?» y le armas las \
cadenas de búsqueda.
- Antecedentes, cómo se redactan: cada uno en UN párrafo de prosa con cita APA 7 que reúne, en este orden, \
la cita (Apellido, año), el problema que abordó, su objetivo, su diseño (tipo, población y muestra), sus \
resultados con cifras y qué aporta a SU proyecto (el instrumento, el rango esperable o la brecha que deja). \
Los antecedentes NO se redactan con la técnica del embudo (esa es de la realidad problemática): van \
primero —y de preferencia solo— los internacionales; si incluye algún nacional o local, va después en su \
propio grupo. Siempre que expliques cómo se redactan, organizan o eligen los antecedentes, DI que se \
aconseja que sean de preferencia internacionales y por qué (comparar resultados, guiar el diseño). Dentro de cada grupo, con un criterio explícito (relevancia, o del más reciente al más \
antiguo). Se cierran con una «Síntesis y brecha de investigación»: SÍ conviene ponerla \
—dos o tres párrafos que digan qué resuelven en conjunto, qué queda sin resolver y por qué eso justifica \
su estudio—; si su formato le reserva un subapartado (p. ej. 2.2.4), va ahí; si no, como cierre de los \
antecedentes.
- Realidad problemática (descripción del problema): AQUÍ es donde va la técnica del embudo. Se parte de la \
situación internacional (mundial o regional, p. ej. América Latina), se baja a la nacional y luego a la \
local o institucional, con datos y su fuente en cada nivel, hasta llegar al problema concreto del estudio. \
El embudo termina en el ámbito REAL del estudio: si el estudio es nacional, termina en lo nacional y no se \
fuerza un nivel local.
- Base teórica (NO es lo mismo que los antecedentes): no resume estudios previos, desarrolla la teoría de \
SUS variables. Se organiza por variables (primero la independiente, luego la dependiente) y, dentro de \
cada una, por dimensiones, hasta llegar a los indicadores que usará en la operacionalización. En cada \
concepto: cómo lo definen dos o tres autores, en qué coinciden o difieren, y la definición que adopta \
«para efectos de esta investigación» (de ahí sale la definición conceptual de su cuadro). Prosa propia con \
citas APA 7: paráfrasis, y citas textuales solo cuando la formulación exacta importa. Fuente fundacional \
para los conceptos, libros y artículos indexados recientes para técnicas y herramientas, normas o \
estándares (ISO, IEEE…) cuando apliquen; nada de blogs ni Wikipedia. Los términos que solo necesitan una \
o dos líneas van a «Definición de términos básicos».
- Título: en Ingeniería deja ver la variable independiente (lo que se construye o aplica) y la \
dependiente (lo que se mide o mejora, con algo medible), la unidad de análisis o el espacio y, si \
corresponde, el tiempo; máximo 20 palabras, sin comillas, solo con mayúscula inicial y nombres propios. \
NO incluye la metodología ni el enfoque. Si falta la dependiente, dilo y pregunta qué va a medir.
- Extensión: ni el formato UPAO ni el reglamento fijan un número de páginas o palabras para las secciones \
del proyecto. Si pregunta cuántas páginas, dilo así y NO propongas un rango propio; oriéntalo por \
contenido (qué apartados debe cubrir). Si citas una cifra de un libro, dila con su contexto exacto.
- Hipótesis en Ingeniería: contrastable y medible — «[la propuesta] [mejora/reduce/aumenta] [indicador \
medible, con su unidad] respecto de [línea base] en [contexto y periodo]». Evita «influye positivamente» o \
variables que no se miden («la gestión», «la evaluación»); si su dependiente no es medible, díselo.
- Diseño y pruebas estadísticas en Ingeniería, según lo que se compara:
{criterios_diseno}

REGLAMENTO UPAO (puntos que afectan el proyecto; cita el artículo si lo usas):
{reglamento}

ESTADO DEL PROYECTO DEL ESTUDIANTE:
{estado}

FRAGMENTOS DE LIBROS (tu memoria metodológica):
{libros}

FRAGMENTOS DE LA TESIS DEL ESTUDIANTE (su proyecto indexado):
{tesis}

CRITERIOS DE LA RÚBRICA RELEVANTES A ESTA CONSULTA (si el estudiante cargó una rúbrica):
{criterios_rubrica}
"""


def _recuperar_libros(biblioteca, consulta: str) -> tuple[str, str]:
    """Devuelve (texto_contexto, una_fuente_de_ejemplo) desde los 4 libros."""
    try:
        if biblioteca is None or biblioteca._collection.count() == 0:
            return "", "los libros"
        docs = biblioteca.similarity_search(f"metodología de la investigación {consulta}", k=_K_LIBROS)
    except Exception as exc:
        logger.warning(f"[conversador] Error RAG libros: {exc}")
        return "", "los libros"

    if not docs:
        return "", "los libros"

    partes, fuente_ej = [], "los libros"
    for d in docs:
        fuente = d.metadata.get("fuente", "Fuente")
        fuente_ej = fuente
        partes.append(f"[{fuente}]\n{d.page_content[:_MAX_CHARS_FRAG]}")
    return "\n\n---\n\n".join(partes), fuente_ej


def _recuperar_tesis(doc, consulta: str) -> str:
    if doc is None:
        return ""

    vs = doc.vector_store
    partes: list[str] = []

    # Siempre incluir la carátula/«Título del proyecto»: así el mentor conoce el
    # título y datos generales aunque la pregunta no se parezca a la portada.
    try:
        res = vs._collection.get(
            where={"seccion": "Título del proyecto"}, include=["documents"]
        )
        for t in (res.get("documents") or [])[:1]:
            if t:
                partes.append(f"[Título del proyecto]\n{t[:_MAX_CHARS_FRAG]}")
    except Exception:
        pass

    # Versiones de trabajo que pegó en el chat (aún no reemplazan al documento). Sin
    # esto, tras pegar su nuevo objetivo y preguntar «¿está mejor?», el mentor le
    # respondía «compárteme el nuevo objetivo»: no veía lo que acababa de pegar.
    for sec, m in list((getattr(doc, "mejoras", None) or {}).items())[-3:]:
        if m.get("origen") == "chat" and not m.get("aplicada") and m.get("texto"):
            original = _secciones_de_la_consulta(doc, sec)
            partes.append(
                f"[VERSIÓN DE TRABAJO que el estudiante pegó en el chat para «{sec}»; aún no "
                f"reemplaza a su documento]\n{m['texto'][:2000]}"
                + (f"\n\n[Versión ORIGINAL de su documento]\n{original[:2000]}" if original else "")
            )

    # La sección por la que pregunta, entera: el RAG por similitud a veces trae
    # otra parecida y el modelo respondía con ella (o reconstruía la que faltaba).
    pedidas = _secciones_de_la_consulta(doc, consulta)
    if pedidas:
        partes.append(pedidas)

    # Fragmentos relevantes CON VECINOS ±1: trae el fragmento anterior y el
    # siguiente de cada acierto, para que una oración partida entre chunks (p. ej.
    # la pregunta de formulación) no se dé por ausente.
    try:
        from backend.rag import recuperar_con_vecinos
        crudo = recuperar_con_vecinos(vs, consulta, k=_K_TESIS, ventana=1, max_chunks=10)
        if crudo.strip():
            partes.append(crudo)
    except Exception as exc:
        logger.warning(f"[conversador] Error RAG tesis: {exc}")

    return "\n\n---\n\n".join(partes) if partes else ""


def _mapa_documento(doc) -> str:
    """Título y mapa de secciones: qué está redactado y qué sigue siendo plantilla.

    Sin esto el conversador solo veía los fragmentos que devolvía el RAG: no podía
    decir qué partes faltaban, describía el proyecto por el bloque de enfoque
    («una investigación cuantitativa…») y, si una sección no existía, la inventaba.
    """
    titulo = (getattr(doc, "titulo_proyecto", "") or "").strip()
    txt = (f"\n- Título del proyecto (tal como lo escribió): «{titulo}»." if titulo else
           "\n- Título del proyecto: NO lo ha escrito (la carátula conserva el texto del formato).")

    from backend.config import _clave_portada_upao

    portada, redactadas = [], []
    for s in (doc.stats or []):
        if s.get("chars", 0) < 80:
            continue
        nombre = s.get("seccion") or ""
        if _clave_portada_upao(nombre):
            portada.append(nombre)
        else:
            redactadas.append(f"{nombre} ({s.get('chars', 0)} caracteres)")
    if redactadas:
        txt += ("\n- Secciones del PLAN DE INVESTIGACIÓN con contenido del estudiante: "
                + "; ".join(redactadas) + ".")
    if portada:
        txt += ("\n- Apartados de la PORTADA (I. Generalidades: autores, tipo de investigación, "
                "línea, institución, fechas). NO son el planteamiento, los objetivos ni la "
                "metodología aunque el estudiante haya escrito ahí algo parecido: "
                + "; ".join(portada) + ".")
    plantilla = list(getattr(doc, "secciones_plantilla", None) or [])
    if plantilla:
        txt += ("\n- Secciones SIN REDACTAR (solo conservan el texto de ejemplo del formato, "
                "p. ej. «El texto expositivo es aquel texto…»; NO son contenido del estudiante): "
                + "; ".join(plantilla) + ".")

    # Qué compara el proyecto: decide el diseño y la prueba estadística que se le
    # recomienda (antes se le proponían pruebas para grupos independientes).
    try:
        from backend.metodologia_reglas import PERFIL_COMPARACION_TEXTO, perfil_comparacion
        from .planteamiento import _cadena_redactada
        from .metodologia import _RE_SECCIONES_METODOLOGIA

        escrito = _cadena_redactada(doc, max_chars=6000, patron=_RE_SECCIONES_METODOLOGIA)
        perfil = perfil_comparacion(f"{titulo} {escrito}")
        txt += "\n- " + PERFIL_COMPARACION_TEXTO[perfil] + (
            " Si el estudiante ya declaró otro diseño, respeta lo declarado y solo señala la "
            "incoherencia si la hay.")
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[conversador] No se pudo clasificar la comparación: {exc}")

    # Capítulos del formato oficial de los que no hay NADA escrito, ni siquiera el
    # encabezado. Sin esto, a un documento con otra estructura el modelo le
    # inventaba la numeración de lo que falta («1.2. Metodología…»).
    try:
        from backend.alcance import _items_con_contenido
        from backend.config import RUBRICA_GRUPOS_UPAO

        cubiertos = _items_con_contenido(doc)
        ausentes = [
            _CAPITULO_FORMATO.get(grupo, grupo)
            for grupo, items in RUBRICA_GRUPOS_UPAO
            if items and not any(i in cubiertos for i in items)
        ]
        if ausentes:
            txt += ("\n- Capítulos del FORMATO OFICIAL UPAO sin contenido del estudiante (usa esta "
                    "numeración, no otra): " + "; ".join(ausentes) + ".")
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[conversador] No se pudo calcular los capítulos ausentes: {exc}")
    return txt


_CAPITULO_FORMATO = {
    "TÍTULO": "Título del proyecto",
    "PLANTEAMIENTO DEL PROBLEMA": "1. Planteamiento del estudio (1.1–1.5)",
    "MARCO TEÓRICO": "2. Marco teórico (2.1–2.4)",
    "HIPÓTESIS Y VARIABLES": "3. Hipótesis y variables (3.1 Supuestos, 3.2 Hipótesis, 3.3 Variables, 3.4 Matriz de consistencia)",
    "MARCO METODOLÓGICO": "4. Marco metodológico (4.1 Tipo, 4.2 Método, 4.3 Diseño, 4.4 Población y muestra, 4.5 Técnicas e instrumentos, 4.6 Procedimiento, 4.7 Análisis de datos)",
    "ASPECTOS ADMINISTRATIVOS": "5. Aspectos administrativos (5.1 Cronograma, 5.2 Recursos, 5.3 Presupuesto, 5.4 Financiación)",
    "REFERENCIAS BIBLIOGRÁFICAS": "6. Referencias bibliográficas",
}


def _secciones_de_la_consulta(doc, consulta: str) -> str:
    """Texto completo de las secciones que el estudiante nombra en su pregunta."""
    from .intent import secciones_mencionadas

    nombres = [s.get("seccion") for s in (doc.stats or []) if s.get("chars", 0) >= 45]
    pedidas = secciones_mencionadas(consulta, nombres)[:3]
    # «¿Qué escribí en la portada?»: sin su texto, el modelo respondía «(texto de 498
    # caracteres, no lo copié)». Los apartados de la portada son cortos: van todos.
    # El TIPO de investigación que «declaró» también vive en la portada (3.1/3.2 «De
    # acuerdo con…»): sin su texto, se respondía con el tipo que infiere el sistema.
    if re.search(r"portada|car[aá]tula|generalidades|tipo\s+de\s+investigaci|declar[eé]|"
                 r"t[eé]cnica\s+de\s+contrastaci|orientaci[oó]n\s+o\s+finalidad", consulta or "", re.I):
        from backend.config import _clave_portada_upao
        pedidas += [n for n in nombres if _clave_portada_upao(n) and n not in pedidas][:8]
    partes = []
    for nombre in pedidas:
        try:
            res = doc.vector_store._collection.get(where={"seccion": nombre}, include=["documents"])
            texto = "\n".join(t for t in (res.get("documents") or []) if t)
        except Exception:                                      # noqa: BLE001
            continue
        if texto:
            partes.append(f"[{nombre}] (sección completa)\n{texto[:3000]}")
    return "\n\n---\n\n".join(partes)


def _estado_proyecto(doc) -> str:
    if doc is None:
        return ("El estudiante AÚN NO ha subido su proyecto en este chat. "
                "Si su pregunta requiere su tesis, invítalo a subir el PDF con el botón de adjuntar (📎).")
    n_sec = len(doc.estructura_toc or {})
    revisadas = sorted(doc.evaluadas) if getattr(doc, "evaluadas", None) else []
    txt = f"- Documento: «{doc.nombre}» ({n_sec} secciones detectadas)."
    txt += _mapa_documento(doc)
    if revisadas:
        txt += "\n- Secciones que YA revisaste con la red de agentes en este chat: " + ", ".join(revisadas) + "."
    else:
        txt += "\n- Todavía no has corrido ninguna revisión formal en este chat."

    # Resultado de la última evaluación (para no perder el hilo de las notas/hallazgos).
    ult = getattr(doc, "ultima_revision", None) or {}
    if ult.get("texto"):
        txt += ("\n- RESULTADO DE LA ÚLTIMA EVALUACIÓN (úsalo para responder dudas sobre su nota, "
                "puntos débiles y qué mejorar; no le pidas que vuelva a evaluar para esto):\n  "
                + ult["texto"])
    return txt


def _historial_a_mensajes(historial: list[dict]) -> list:
    msgs = []
    for turno in (historial or [])[-_MAX_TURNOS_HISTORIAL:]:
        rol = turno.get("rol")
        contenido = (turno.get("contenido") or "").strip()
        if not contenido:
            continue
        if rol == "user":
            msgs.append(HumanMessage(content=contenido[:2000]))
        elif rol == "assistant":
            msgs.append(AIMessage(content=contenido[:2000]))
    return msgs


def responder_consulta(
    mensaje: str,
    historial: list[dict],
    doc,
    biblioteca,
    nota_sistema: str = "",
) -> str:
    """Genera la respuesta conversacional fundamentada en libros + tesis + hilo.

    `nota_sistema` se añade solo al turno que ve el modelo, no a la búsqueda en los
    libros ni en la tesis (allí metería ruido)."""
    libros, fuente_ej = _recuperar_libros(biblioteca, mensaje)
    tesis = _recuperar_tesis(doc, mensaje)

    # Lineamientos de rúbrica relevantes a la consulta (plus: cómo llegar al máximo).
    criterios = ""
    if doc is not None:
        try:
            from .rubrica_chat import criterios_relevantes
            criterios, _sec = criterios_relevantes(doc, mensaje)
        except Exception as exc:
            logger.warning(f"[conversador] No se pudieron resolver criterios de rúbrica: {exc}")

    estado = _estado_proyecto(doc)
    # Título PEGADO en el mensaje: el conteo de palabras lo hace el código. El modelo
    # contaba mal («tiene 14 palabras» con 16) justo en el límite que exige UPAO.
    titulo_pegado = re.search(r"t[ií]tulo\s*(?:es|ser[ií]a|queda)?\s*(?::\s*[«\"“]?|[«\"“])(.+?)[»\"”]?\s*(?:[.?]\s*¿|\?|$)",
                              mensaje or "", re.I | re.S)
    if titulo_pegado:
        pegado = re.split(r"[»\"”]|\s¿", titulo_pegado.group(1))[0].strip().rstrip(".")
        n_pal = len(pegado.split())
        estado += (f"\n- HECHO VERIFICADO: el título que pegó en su mensaje tiene {n_pal} palabras "
                   f"(contando conectores y fechas; máximo UPAO 20). Usa este número, no lo recuentes.")
    if doc is not None:
        try:
            from .tipo_investigacion import obtener_tipo_diseno
            from backend.enfoque import bloque_enfoque
            tipo, diseno = obtener_tipo_diseno(doc)
            estado += ("\n\n" + bloque_enfoque(tipo, diseno) +
                       "\n(Este tipo lo INFIERE el sistema para orientarte; no digas que el estudiante "
                       "lo «declaró» o «mencionó» salvo que esté escrito en sus fragmentos.)")
        except Exception as exc:
            logger.warning(f"[conversador] No se pudo detectar el tipo: {exc}")

    from .antecedentes import ANTECEDENTES_RECOMENDADOS
    from backend.metodologia_reglas import CRITERIOS_DISENO_INGENIERIA
    from backend.reglamento_upao import REGLAMENTO_UPAO

    sistema = _PROMPT_SISTEMA.format(
        n_antecedentes=ANTECEDENTES_RECOMENDADOS,
        criterios_diseno=CRITERIOS_DISENO_INGENIERIA,
        reglamento="\n".join(f"- {p['ref']}: {p['texto']}" for p in REGLAMENTO_UPAO["puntos"]),
        estado=estado,
        libros=libros or "(sin fragmentos de libros recuperados para esta consulta)",
        tesis=tesis or "(sin fragmentos de la tesis — o el proyecto no está cargado)",
        criterios_rubrica=criterios or "(el estudiante no cargó una rúbrica para esta consulta)",
        fuente_ejemplo=fuente_ej,
    )

    mensajes = [SystemMessage(content=sistema)]
    mensajes.extend(_historial_a_mensajes(historial))
    mensajes.append(HumanMessage(content=f"{mensaje}\n\n{nota_sistema}" if nota_sistema else mensaje))

    try:
        llm = llm_rapido(temperatura=0.3)
        return llm.invoke(mensajes).content.strip()
    except Exception as exc:
        logger.error(f"[conversador] Error LLM: {exc}")
        return ("Disculpa, tuve un problema procesando tu consulta. "
                "Intenta de nuevo en unos segundos.")
