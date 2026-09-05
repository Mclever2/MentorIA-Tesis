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

# Verbo de MEJORA/REDACCIÓN → mini-grafo multiagente (no lanza la red grande).
# Cubre los dos casos de redacción: partir de CERO («elabora un título») y partir
# del texto del estudiante («mejora mi hipótesis», «extiende esto», «parafrasea»).
_RE_MEJORA = re.compile(
    r"\b(corrig\w*|corrije\w*|mejor\w*|redact\w*|reescrib\w*|"
    r"reformul\w*|recomend\w*|lineamient\w*|"
    r"elab[oó]r\w*|gener\w*|escrib\w*|prop[oó]n\w*|propon\w*|plante\w*|formul\w*|"
    r"parafrase\w*|extend\w*|extiend\w*|ampl[ií]\w*|resum\w*|pul\w*|"
    r"ay[uú]dame\s+a\s+(hacer|armar|construir|formular)|"
    r"h[aá]zme|dame\s+(un|una|ideas)|ideas\s+(de|para)|"
    r"c[oó]mo\s+(redacto|formulo|planteo|escribo))\b",
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
  "modo": "completo" | "secciones" | "conversacion" | "mejora",
  "secciones": ["nombre exacto de la lista"]
}}

Reglas:
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
- "mejora": CONTINUIDAD del acompañamiento de redacción. Úsalo cuando el ÚLTIMO turno de MentorIA fue una lista de
  PREGUNTAS para poder redactar algo, o una propuesta de IDEAS/temas, y el mensaje actual del estudiante CONTINÚA ese
  hilo: responde a esas preguntas, elige una de las ideas, aporta su tema, o dice que no sabe qué hacer.
  ⚠️ Esto vale AUNQUE el mensaje no traiga ningún verbo y sea muy corto o una simple enumeración
  (p. ej. «1. deep learning 2. cáncer de piel», «la segunda», «en una clínica de Trujillo», «no sé, lo que sea»).
  Esos mensajes NO son "conversacion": son la respuesta que el mentor estaba esperando para poder seguir.

SECCIONES DEL DOCUMENTO:
{toc}

ÚLTIMOS TURNOS DE LA CONVERSACIÓN (para resolver referencias como «esa sección», «sí», «la anterior»):
{historial}
"""


# Marcas de que el ÚLTIMO turno del mentor dejó el hilo abierto esperando respuesta:
# una tanda de preguntas (elicitación) o una propuesta de ideas de tema (ideación).
_RE_MARCA_IDEACION = re.compile(
    r"artefacto\s+propuesto|riesgo\s+principal|variable\s+dependiente|subl[íi]nea|"
    r"acceso\s+real|l[íi]neas?\s+de\s+proyecto|de\s+d[óo]nde\s+saldr[íi]an",
    re.I,
)


def _hilo_abierto(historial: list[dict] | None) -> bool:
    """True si el mentor dejó una pregunta/propuesta pendiente en su último turno.

    Se mira SOLO el último turno del asistente: es el que el estudiante está
    respondiendo ahora.
    """
    ultimo = next(
        (t for t in reversed(historial or []) if t.get("rol") == "assistant"), None
    )
    if not ultimo:
        return False
    texto = (ultimo.get("contenido") or "")
    return texto.count("?") >= 3 or bool(_RE_MARCA_IDEACION.search(texto))


def _historial_breve(historial: list[dict] | None) -> str:
    """Historial para el enrutador, SIN mutilar los turnos del estudiante.

    Recortar al estudiante a 200 caracteres era lo que rompía la clasificación:
    cuando respondía a una tanda de preguntas («1. …Respuesta: …» × 7), lo único
    que llegaba aquí era el arranque de la primera pregunta, así que parecía que
    no había contestado. Los turnos del mentor sí se recortan: son largos,
    repetitivos y solo sirven para saber a qué está respondiendo.
    """
    if not historial:
        return "(sin turnos previos)"
    lineas = []
    for t in historial[-8:]:
        es_alumno = t.get("rol") == "user"
        rol = "Estudiante" if es_alumno else "MentorIA"
        contenido = (t.get("contenido") or "").strip().replace("\n", " ")
        if contenido:
            lineas.append(f"{rol}: {contenido[:1500 if es_alumno else 200]}")
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

    # META-PREGUNTA («¿sabes lo que te dije?», «ya te dije mi problema», «me
    # preguntas lo mismo»). Va derecho al mini-grafo, que la resuelve devolviendo
    # la ficha del estudiante sin pasar por ningún LLM. No se clasifica con el
    # modelo a propósito: es el turno en el que el estudiante ya desconfía, y
    # equivocarse ahí es lo que hace que abandone.
    from .ficha import es_meta_pregunta

    if es_meta_pregunta(mensaje):
        logger.info("[intent] Meta-pregunta («¿ya te lo dije?») → mini-grafo, ruta memoria")
        return {"modo": "mejora", "secciones": []}

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
    if modo not in ("completo", "secciones", "conversacion", "mejora"):
        msg = mensaje.lower()
        if any(p in msg for p in ("todo", "completo", "completa", "entera", "general")) and hay_documento:
            modo = "completo"
        else:
            modo = "conversacion"

    # CONTINUIDAD DEL HILO. Si el turno anterior del mentor dejó el acompañamiento
    # ABIERTO (le hizo preguntas para poder redactar, o le propuso ideas de tema), la
    # respuesta del estudiante debe volver al MINI-GRAFO aunque no traiga ningún verbo
    # («1. deep learning 2. cáncer de piel», «la segunda», «en una clínica»). Si no,
    # cae en el conversador plano —un solo agente, sin validador— y se pierde el hilo.
    if modo != "mejora" and not _RE_ACCION_EVAL.search(mensaje) and _hilo_abierto(historial):
        logger.info("[intent] Continuidad del hilo de redacción → modo 'mejora' (mini-grafo)")
        return {"modo": "mejora", "secciones": []}

    if modo == "mejora":
        logger.info("[intent] Continuidad detectada por el clasificador → modo 'mejora'")
        return {"modo": "mejora", "secciones": []}

    # Mini-grafo multiagente: petición de REDACTAR/MEJORAR/CORREGIR/lineamientos SIN
    # orden explícita de evaluar (p. ej. «corrige mi planteamiento», «elabórame un
    # título», «¿cómo mejoro mi hipótesis?», «dame lineamientos para…»).
    # NO requiere documento: si no hay base, el triaje del mini-grafo entra en modo
    # ELICITACIÓN y le pregunta al estudiante en vez de inventarle un texto.
    # Si además pide evaluar («revisa y mejora»), gana la evaluación → red grande.
    if _RE_MEJORA.search(mensaje) and not _RE_ACCION_EVAL.search(mensaje):
        logger.info(
            f"[intent] Petición de redacción/mejora → modo 'mejora' (mini-grafo multiagente; "
            f"documento={'sí' if hay_documento else 'no'})"
        )
        return {"modo": "mejora", "secciones": []}

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
