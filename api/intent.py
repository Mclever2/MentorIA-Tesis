"""
Intérprete de intención del chat.

Una sola llamada barata a gpt-4o-mini decide qué hacer con el mensaje del
usuario: lanzar la revisión completa, revisar secciones específicas del TOC,
o responder conversacionalmente (sin lanzar el grafo → cero tokens de agentes).
"""

import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage

from .llm import llm_rapido, extraer_json

logger = logging.getLogger(__name__)

# Verbo EXPLÍCITO de evaluación → es una orden de lanzar la red GRANDE (no una pregunta).
# OJO: "corregir" y "mejorar" NO van aquí — esos los atiende el mini-grafo de debate.
_RE_ACCION_EVAL = re.compile(
    r"\b(eval[uú]a\w*|evaluar|calific\w*|revis\w*|"
    r"audit\w*|punt[uú]a\w*|puntuar|analiz\w*)\b",
    re.I,
)

# Verbo de MEJORA/REDACCIÓN → mini-grafo de debate rápido (no lanza la red grande).
_RE_MEJORA = re.compile(
    r"\b(corrig\w*|corrije\w*|mejor\w*|redact\w*|reescrib\w*|"
    r"reformul\w*|recomend\w*|lineamient\w*)\b",
    re.I,
)

# El TÍTULO tiene su propio panel (propone → aterriza → audita) porque juega con
# reglas que ninguna otra sección tiene: límite duro de palabras, delimitación
# espacio/tiempo condicionada al tipo de estudio, y evidencia del repositorio.
_RE_TITULO = re.compile(r"\bt[ií]tulo?s?\b", re.I)
# Verbos que piden TRABAJAR el título (proponer/mejorar), no solo consultarlo.
# Incluye los verbos con los que un estudiante pide ayuda para ELEGIR («qué título
# hago», «no sé cuál escoger»): faltaban, y por eso «no sé qué tema hacer o título»
# no llegaba al panel especializado y lo contestaba el chat genérico.
_RE_TITULO_ACCION = re.compile(
    r"\b(propon\w*|proponer|sugier\w*|sugerir|dame|damelo|plantea\w*|formul\w*|"
    r"cre[ae]\w*|gener\w*|arma\w*|escrib\w*|redact\w*|mejor\w*|corrig\w*|corrije\w*|"
    r"reescrib\w*|reformul\w*|acort\w*|ajust\w*|delimit\w*|opciones|alternativas|ideas|"
    r"hacer|hago|elegir|elijo|escoger|escojo|definir|defino|pensar|piens\w*|"
    r"empez\w*|comenz\w*|orient\w*|ayud\w*)\b",
    re.I,
)

# IDEACIÓN: el estudiante todavía NO tiene tema ni título. Es el momento más
# valioso para el corpus del repositorio y el peor atendido hasta ahora: caía en
# el conversador genérico, que respondía «habla con tu profesor» —exactamente lo
# que daría cualquier modelo suelto—. Este panel SÍ funciona sin proyecto subido,
# porque justo aún no hay proyecto que subir.
_RE_IDEACION = re.compile(
    r"(no\s+s[eé]\s+(qu[eé]|de\s+qu[eé]|sobre\s+qu[eé]|cu[aá]l)\s*(tema|t[ií]tulo|hacer|investigar|"
    r"elegir|escoger)?|"
    r"no\s+(tengo|se\s+me\s+ocurre)\s+(un\s+)?(tema|t[ií]tulo|idea)|"
    r"qu[eé]\s+(tema|t[ií]tulo)\s+(hago|puedo|podr[ií]a|elijo|escojo)|"
    r"(dame|sugi[eé]r\w*|propon\w*|recomi[eé]nda\w*)\s+(me\s+)?(un(os)?\s+)?(tema|t[ií]tulo|idea)|"
    r"ideas?\s+(de|para)\s+(tema|t[ií]tulo|tesis|investigaci[oó]n)|"
    r"no\s+s[eé]\s+por\s+d[oó]nde\s+(empezar|empiezo)|"
    r"ay[uú]dame\s+a\s+(elegir|escoger|definir)\s+(el\s+)?(tema|t[ií]tulo))",
    re.I,
)

# PLANTEAMIENTO: ya tiene título y pide la cadena problema → preguntas → objetivos.
# Es la etapa siguiente a la ideación y se torcía igual: sin proyecto subido caía
# en el chat genérico, que redactaba problemas inventados y preguntas específicas
# que respondían por sí solas la general.
_RE_PLANTEAMIENTO = re.compile(
    r"(planteamiento|realidad problem[aá]tica|formulaci[oó]n del problema|"
    r"redact\w*\s+(el\s+|mi\s+)?problema|plantea\w*\s+(el\s+|mi\s+)?problema|"
    r"pregunta\s+(general|del problema|de investigaci[oó]n)|preguntas?\s+espec[ií]ficas?|"
    r"problemas?\s+espec[ií]ficos?|objetivos?\s+(general|espec[ií]ficos?)|"
    r"qu[eé]\s+sigue|c[oó]mo\s+(sigo|contin[uú]o|avanzo)|"
    r"ya\s+tengo\s+(el\s+)?t[ií]tulo)",
    re.I,
)

# ANTECEDENTES y MARCO TEÓRICO. Panel aparte porque su regla es la contraria a
# la del resto: aquí NO se redacta el contenido. Un antecedente es un estudio
# real y un modelo que lo "redacta" produce referencias inexistentes, que en una
# tesis son falta académica. El panel entrega la búsqueda y la estructura.
_RE_ANTECEDENTES = re.compile(
    r"(antecedent|marco te[oó]rico|marco referencial|bases? te[oó]rica|estado del arte|"
    r"revisi[oó]n (de |de la )?literatura|definici[oó]n de t[eé]rminos|"
    r"art[ií]culos?\s+(cient[ií]fic|para (mi|el))|paper|scopus|scielo|"
    r"c[oó]mo\s+(busco|buscar|encuentro|encontrar)\s+.{0,24}(art[ií]culo|paper|fuente|estudio|"
    r"antecedent|bibliograf))",
    re.I,
)

# OPERACIONALIZACIÓN, MATRIZ DE CONSISTENCIA y MARCO METODOLÓGICO. Panel propio
# porque aquí casi todo es verificable —la muestra se calcula, las columnas están
# fijadas, y qué necesita juicio de expertos se decide de forma determinista— y
# porque es el tramo que deja el camino listo para Tesis 1.
_RE_METODOLOGIA = re.compile(
    r"(operacionalizaci|matriz de consistencia|marco metodol[oó]gic|metodolog[ií]a|"
    r"dimensiones? e indicadores?|escala de medici[oó]n|"
    r"poblaci[oó]n(\s+y\s+muestra)?|tama[nñ]o de (la )?muestra|muestreo|"
    r"dise[nñ]o de (la )?investigaci|preexperiment|cuasiexperiment|experimental puro|"
    r"procedimiento de ejecuci|t[eé]cnicas? (e instrumentos?|de recolecci|de procesamiento)|"
    r"instrumentos? de recolecci|juicio de expertos|cronbach|validaci[oó]n de(l)? instrumento)",
    re.I,
)

# Señal de que el estudiante ESTÁ en una conversación de ideación y responde con
# sus intereses («1. sistemas agénticos 2. …»). Sin esto, el turno siguiente al
# «no sé qué tema» se salía del panel y volvía al chat genérico.
_RE_IDEACION_EN_CURSO = re.compile(
    r"(elegir|escoger|definir)\s+(un\s+)?(tema|t[ií]tulo)|"
    r"posibles?\s+t[ií]tulos|"
    r"problemas?\s+investigables?|"
    r"qu[eé]\s+te\s+interesa|"
    r"[aá]reas?\s+de\s+inter[eé]s",
    re.I,
)

# Pregunta/consulta: empieza con palabra interrogativa o lleva signos de pregunta.
# Alta precisión a propósito: ante la duda preferimos NO lanzar la red.
_RE_PREGUNTA = re.compile(
    r"^\s*(sab[eé]s?|conoc\w+|cu[aá]l\w*|qu[eé]\s|c[oó]mo|d[oó]nde|cu[aá]nto\w*|"
    r"mu[eé]stra\w*|ens[eé][ñn]\w*|recu[eé]rda\w*|dime|tienes?|"
    r"me\s+puedes?\s+decir|puedes?\s+decirme)\b|[¿?]",
    re.I,
)

_PROMPT_SISTEMA = """Eres el enrutador de un sistema multiagente que revisa proyectos de tesis.
Tu ÚNICA tarea es clasificar el mensaje del estudiante. Responde SOLO con JSON válido:

{{
  "modo": "completo" | "secciones" | "conversacion" | "ideacion" | "planteamiento",
  "secciones": ["nombre exacto de la lista"]
}}

Reglas:
- "ideacion": el estudiante AÚN NO TIENE tema o título de tesis, o lo está eligiendo. Incluye tanto
  el pedido inicial («no sé qué tema hacer», «dame ideas de título», «no sé por dónde empezar») como
  sus RESPUESTAS dentro de esa conversación: si en el historial MentorIA le acaba de plantear
  problemas, áreas o títulos candidatos y el estudiante contesta con sus intereses, un área, una
  empresa o una lista de ideas sueltas (p. ej. «1. sistemas agénticos 2. revísalo tú 3. automatizar
  registros en el sector agrario»), eso SIGUE siendo "ideacion", NO "conversacion". Mientras el hilo
  trate de decidir el tema, el modo es "ideacion".
- "planteamiento": YA TIENE tema o título y pide construir lo que sigue: la realidad problemática,
  la formulación del problema, la pregunta general, las preguntas específicas o los objetivos
  («¿qué sigue?» tras pegar su título, «redacta el problema», «dame la pregunta general y las
  específicas», «ahora los objetivos»). Se distingue de "ideacion" en que aquí YA hay tema: si en el
  mensaje o en el historial aparece un título de tesis, NO es "ideacion", es "planteamiento".
- "completo": pide revisar/evaluar TODO el proyecto, la tesis entera, una revisión general o los puntos débiles globales.
- "secciones": SOLO cuando hay una ORDEN EXPLÍCITA de evaluar/revisar/corregir/calificar/mejorar/auditar una parte
  concreta (p. ej. «revisa mis objetivos», «evalúa mi operacionalización», «corrige mi población»). Usa SOLO nombres
  EXACTOS de la lista del documento. Máximo 3. Si el estudiante menciona un SUB-TEMA que no es un título exacto pero
  pertenece claramente a una sección de la lista (p. ej. «operacionalización de variables», «variable
  dependiente/independiente» → la sección de Variables; «población y muestra» → la sección de Metodología), elige el
  título de la lista que lo CONTIENE. Si no estás seguro de a qué título pertenece, incluye igual tu mejor candidato.
  ⚠️ Una PREGUNTA o consulta sobre el contenido NO es una orden de evaluar, aunque nombre una sección:
  «¿sabes cuál es mi operacionalización?», «¿qué dice mi marco teórico?», «¿cuál es mi población?»,
  «muéstrame mis objetivos», «¿está bien mi hipótesis?» → eso es "conversacion" (el mentor lo responde sin lanzar la red).
  Considera el HISTORIAL: si antes hablaron de una sección y ahora dice «sí, revísala» o «corrígela», resuélvelo a esa sección.
- "conversacion": saludos, dudas metodológicas, preguntas sobre cómo funciona el sistema, preguntas sobre resultados
  previos, o CUALQUIER cosa que no sea una orden explícita de ejecutar una revisión. Ante la duda, usa "conversacion".

SECCIONES DEL DOCUMENTO:
{toc}

ÚLTIMOS TURNOS DE LA CONVERSACIÓN (para resolver referencias como «esa sección», «sí», «la anterior»):
{historial}
"""


def _historial_breve(historial: list[dict] | None) -> str:
    if not historial:
        return "(sin turnos previos)"
    lineas = []
    for t in historial[-6:]:
        rol = "Estudiante" if t.get("rol") == "user" else "MentorIA"
        contenido = (t.get("contenido") or "").strip().replace("\n", " ")
        if contenido:
            lineas.append(f"{rol}: {contenido[:200]}")
    return "\n".join(lineas) or "(sin turnos previos)"


def interpretar_mensaje(
    mensaje: str,
    toc_nombres: list[str],
    contexto_previo: str = "",
    hay_documento: bool = False,
    historial: list[dict] | None = None,
    vector_store=None,
) -> dict:
    toc_txt = "\n".join(f"- {n}" for n in toc_nombres) if toc_nombres else "(sin documento cargado)"

    llm = llm_rapido(temperatura=0.0)
    try:
        respuesta = llm.invoke([
            SystemMessage(content=_PROMPT_SISTEMA.format(
                toc=toc_txt, historial=_historial_breve(historial),
            )),
            HumanMessage(content=mensaje),
        ])
        data = extraer_json(respuesta.content)
    except Exception as exc:
        logger.error(f"[intent] Error LLM: {exc}")
        data = {}

    modo = data.get("modo")
    if modo not in ("completo", "secciones", "conversacion", "ideacion", "planteamiento",
                    "antecedentes", "metodologia"):
        msg = mensaje.lower()
        if any(p in msg for p in ("todo", "completo", "completa", "entera", "general")) and hay_documento:
            modo = "completo"
        else:
            modo = "conversacion"

    # METODOLOGÍA antes que antecedentes y planteamiento: es la más específica.
    if (_RE_METODOLOGIA.search(mensaje)
            and not (hay_documento and _RE_ACCION_EVAL.search(mensaje))):
        logger.info("[intent] Petición metodológica → modo 'metodologia'")
        return {"modo": "metodologia", "secciones": []}

    # ANTECEDENTES va antes que planteamiento: «redacta mis antecedentes» acababa
    # en el panel de planteamiento, que le devolvía la realidad problemática.
    if (_RE_ANTECEDENTES.search(mensaje)
            and not (hay_documento and _RE_ACCION_EVAL.search(mensaje))):
        logger.info("[intent] Petición de antecedentes / marco teórico → modo 'antecedentes'")
        return {"modo": "antecedentes", "secciones": []}

    # PLANTEAMIENTO va antes que ideación: quien ya trae título no está eligiendo
    # tema, está construyendo la cadena. Sin esta precedencia, «este es mi título,
    # ¿qué sigue?» caía en ideación y le proponía temas nuevos en vez de avanzar.
    if ((modo == "planteamiento" or _RE_PLANTEAMIENTO.search(mensaje))
            and not (hay_documento and _RE_ACCION_EVAL.search(mensaje))):
        logger.info("[intent] Petición de planteamiento → modo 'planteamiento'")
        return {"modo": "planteamiento", "secciones": []}

    # Panel de IDEACIÓN. NO exige documento: el estudiante que aún
    # no tiene tema es precisamente el que no puede subir nada, y era el caso peor
    # atendido del sistema. Se activa por petición explícita o porque el turno
    # anterior ya era de ideación y ahora está respondiendo con sus intereses.
    # El enrutador LLM decide la continuación del hilo —«1. sistemas agénticos
    # 2. revísalo tú…» sigue siendo ideación aunque no nombre la palabra «tema»—,
    # porque una regex sobre la prosa del asistente resultó demasiado frágil: no
    # reconocía sus propias respuestas y el turno siguiente volvía al chat genérico.
    # La regex se conserva como atajo para el pedido explícito.
    _ideando = modo == "ideacion" or bool(_RE_IDEACION.search(mensaje))
    if not _ideando and not hay_documento and historial:
        ultima_ia = next(
            (t.get("contenido", "") for t in reversed(historial) if t.get("rol") != "user"), ""
        )
        if _RE_IDEACION_EN_CURSO.search(ultima_ia) and not _RE_PREGUNTA.search(mensaje):
            _ideando = True
            logger.info("[intent] Continuación del hilo de ideación (marca en la respuesta previa)")

    # El verbo de evaluar solo cancela la ideación si HAY algo que evaluar. Sin
    # proyecto subido, un «revísalo tú» dentro de una conversación de tema no es
    # una orden de calificar —no hay nada que calificar—, es el estudiante
    # delegando la elección. Sin esta distinción, «1. sistemas agénticos
    # 2. revisa tú 3. …» se salía del panel y volvía al chat genérico.
    if _ideando and not (hay_documento and _RE_ACCION_EVAL.search(mensaje)):
        logger.info("[intent] Petición sin tema definido → modo 'ideacion'")
        return {"modo": "ideacion", "secciones": []}

    # Panel de TÍTULO: pide trabajar el título y no una calificación formal.
    # Va ANTES del debate rápido porque el título necesita el panel especializado
    # (límite de palabras, política de delimitación, corpus del repositorio) y el
    # debate genérico lo trataba como una sección cualquiera.
    if (hay_documento
            and _RE_TITULO.search(mensaje)
            and _RE_TITULO_ACCION.search(mensaje)
            and not _RE_ACCION_EVAL.search(mensaje)):
        logger.info("[intent] Petición sobre el título → modo 'titulo' (panel especializado)")
        return {"modo": "titulo", "secciones": []}

    # Mini-grafo de debate rápido: petición de MEJORAR/CORREGIR/REDACTAR/lineamientos
    # SIN orden explícita de evaluar (p. ej. «corrige mi planteamiento», «¿cómo mejoro
    # mi título?», «dame lineamientos para…»). No lanza la red grande; requiere documento.
    # Si además pide evaluar («revisa y mejora»), gana la evaluación → sigue al grafo grande.
    if _RE_MEJORA.search(mensaje) and not _RE_ACCION_EVAL.search(mensaje):
        if hay_documento:
            logger.info("[intent] Petición de mejora → modo 'mejora' (mini-grafo de debate)")
            return {"modo": "mejora", "secciones": []}
        modo = "conversacion"

    # Red de seguridad: una PREGUNTA sin verbo explícito de evaluación nunca debe
    # lanzar la red (p. ej. «¿sabes cuál es mi operacionalización?» es una consulta,
    # no una orden de calificar). El conversador la responde desde la tesis por RAG.
    if (modo in ("secciones", "completo")
            and not _RE_ACCION_EVAL.search(mensaje)
            and _RE_PREGUNTA.search(mensaje)):
        logger.info("[intent] Pregunta sin orden de evaluar → conversacion (guarda)")
        modo = "conversacion"

    raw_secciones = data.get("secciones") or []

    # Resuelve CADA pedido por separado: si es un título exacto del TOC se usa tal
    # cual; si es un sub-concepto que no aparece literal en el índice (p. ej.
    # «operacionalización de variables», «matriz de consistencia»), se ubica por RAG
    # dentro de la sección que lo contiene. Antes el RAG solo entraba si NINGÚN pedido
    # matcheaba exacto, así que pedir «operacionalización Y población» descartaba la
    # operacionalización en cuanto «población» matcheaba un título del índice.
    if modo == "secciones" and raw_secciones:
        from backend.rag import resolver_seccion_semantica
        resueltas: list[str] = []
        for guess in raw_secciones:
            if guess in toc_nombres:
                sec = guess
            elif vector_store is not None:
                sec = resolver_seccion_semantica(vector_store, guess, toc_nombres)
            else:
                sec = None
            if sec and sec not in resueltas:
                resueltas.append(sec)
        secciones = resueltas[:3]
        if secciones:
            logger.info(f"[intent] Secciones resueltas (exactas + RAG) → {secciones}")
    else:
        secciones = []

    if modo == "secciones" and not secciones:
        modo = "completo" if hay_documento else "conversacion"

    # Sin documento no se puede revisar: el conversador se encarga de orientar/pedir el PDF.
    if modo != "conversacion" and not hay_documento:
        modo = "conversacion"

    return {"modo": modo, "secciones": secciones}
