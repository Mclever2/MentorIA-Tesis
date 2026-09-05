"""
MINI-GRAFO MULTIAGENTE de mentoría de redacción — sin lanzar la red de evaluación.

Arquitectura (macro = red / micro = secuencial), respaldada por los antecedentes
del proyecto:
  - Red macro: un `StateGraph` de LangGraph coordina agentes especializados
    (como GraphMASAL, Zeng et al. 2025).
  - Lógica secuencial interna: cada nodo procesa en pasos (como EduPlanner,
    Zhang et al. 2025: Evaluator → Optimizer → Analyst).
  - Debate por roles diferenciados activados en secuencia (como Du et al. 2025:
    afirmativo / negativo / moderador) + un VALIDADOR que cierra el ciclo.

Flujo (con enrutamiento condicional real, no una tubería fija):

                          ┌──────────────┐
                          │ recuperación │  (libros + tesis + rúbrica + marco UPAO)
                          └──────┬───────┘
                                 ▼
                          ┌──────────────┐
                          │    triaje    │  ¿qué necesita realmente el estudiante?
                          └──┬────┬───┬──┘
             elicitación ────┘    │   └──── duda
                    │             │              │
                    ▼        redacción           ▼
             ┌────────────┐      │         ┌──────────┐
             │ elicitador │      │         │  asesor  │
             └─────┬──────┘      ▼         └────┬─────┘
                   │   ┌────────────────────┐   │
                   │   │ redactor metodólogo│   │
                   │   └─────────┬──────────┘   │
                   │   ┌─────────▼──────────┐   │
                   │   │ redactor de dominio│   │  (responde al primero: debate)
                   │   └─────────┬──────────┘   │
                   │   ┌─────────▼──────────┐   │
                   │   │    integrador      │   │
                   │   └─────────┬──────────┘   │
                   │             ▼              │
                   │       ┌──────────┐◀────────┘
                   │       │ VALIDADOR│ ◀──────┐   anti-alucinación + rúbrica
                   │       └────┬─────┘        │   (recibe chequeos DETERMINISTAS
                   │     falla  │  ok          │    ya resueltos: nº de palabras
                   │       ┌────▼─────┐        │    del título, citas sin respaldo)
                   │       │ corrector├────────┘
                   │       └────┬─────┘
                   ▼            ▼
             ┌─────────────────────┐
             │    estructurador    │  respuesta de chat
             └─────────────────────┘

Roles del panel (multiagente de verdad: redactan unos, valida OTRO):
  - `redactor_metodologico` y `redactor_dominio` PROPONEN (memoria compartida; el
    segundo debe reaccionar al primero).
  - `integrador` resuelve el debate y produce el entregable.
  - `validador` NO redacta: audita el entregable contra la rúbrica UPAO, el marco
    institucional y los chequeos deterministas. Si falla, el `corrector` rehace y
    vuelve a pasar por el validador (máximo `_MAX_CORRECCIONES` vueltas).

Todo corre con gpt-4o-mini (llm_rapido): rápido y fuera del presupuesto del grafo
grande. Se usa para ACLARAR DUDAS y para REDACTAR/MEJORAR; si el estudiante pide
EVALUAR (poner nota), el grafo grande es el que actúa.
"""

import logging
import re
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from backend.upao_tesis import (
    AVISO_NO_SE,
    AVISO_SOLUCION_PRIMERO,
    atribuciones_linea_invalidas,
    aviso_etico,
    bloque_tesis_similares,
    chequeos_deterministas,
    detectar_no_se,
    detectar_solucion_primero,
    marco_para,
    nota_no_aplica,
    MOLDE_TITULO,
    PREGUNTA_DISENO,
    PREGUNTA_TIPO_INVESTIGACION,
    requiere_resguardo_etico,
    tesis_similares,
)
from .llm import llm_rapido

logger = logging.getLogger(__name__)

_FALLBACK = (
    "Disculpa, tuve un problema preparando la respuesta. "
    "Intenta de nuevo en unos segundos."
)

# Vueltas máximas del ciclo validador → corrector → validador.
_MAX_CORRECCIONES = 2

# Longitud mínima de texto de la tesis para considerar que hay BASE suficiente
# como para redactar sin preguntar antes.
_MIN_BASE_UTIL = 200

# Tandas de preguntas consecutivas antes de que el panel deje de preguntar y
# redacte con asunciones explícitas. A la tercera, el estudiante ya no colabora:
# se va.
_MAX_ELICITACIONES_SEGUIDAS = 2


# ── Estado compartido (blackboard del panel) ────────────────────────────────

class EstadoDebate(TypedDict, total=False):
    # entrada
    consulta: str
    historial: list
    doc: Any
    biblioteca: Any
    # ficha del proyecto (memoria estructurada de la asesoría; ver api/ficha.py)
    ficha: dict
    ficha_txt: str
    faltantes: list
    elicitaciones_previas: int
    # recursos (los puebla el nodo recuperacion)
    contexto_libros: str
    contexto_tesis: str
    criterios_rubrica: str
    seccion: str
    enfoque: str
    estado_proyecto: str
    aviso_no_aplica: str
    tipo_declarado: bool
    tesis_similares: str
    tesis_similares_lista: list
    aviso_solucion_primero: str
    aviso_no_se: str
    aviso_etico: str
    # triaje
    modo: str
    justificacion_triaje: str
    # debate (memoria compartida)
    debate_memory: list
    # entregable
    texto_sintetizado: str
    recomendaciones: str
    # validación
    problemas: list        # bloquean: incumplen una regla escrita de la plantilla
    advertencias: list     # NO bloquean: consejo para el estudiante
    intentos: int
    # salida
    respuesta_final: str


# ── Contratos estructurados de los agentes ──────────────────────────────────

class Triaje(BaseModel):
    """Decisión del enrutador: qué necesita REALMENTE el estudiante."""
    modo: Literal["duda", "ideacion", "elicitacion", "redaccion", "memoria"] = Field(
        description=(
            "'ideacion' = todavía no tiene tema, o lo tiene a medias y pide IDEAS / opciones / "
            "«no sé qué hacer», o solo ha nombrado tecnologías o un dominio sin un problema. "
            "'duda' = pregunta conceptual o metodológica y pide una explicación (qué es, cómo se "
            "hace, en qué se diferencian), teniendo ya un tema. "
            "'elicitacion' = pide que REDACTES una parte concreta de su proyecto pero NO hay base "
            "suficiente para hacerlo con criterio: hay que preguntarle antes. "
            "'redaccion' = pide que redactes, mejores, extiendas o parafrasees Y existe base real "
            "(su texto indexado, la FICHA DEL PROYECTO, o lo que describió en la conversación). "
            "'memoria' = pregunta por lo que YA te dijo o se queja de que lo estás olvidando "
            "(«¿sabes lo que te dije?», «ya te dije mi problema», «me preguntas lo mismo»): hay "
            "que devolverle lo registrado, NUNCA hacerle más preguntas."
        )
    )
    justificacion: str = Field(
        default="",
        description="Una frase: por qué elegiste ese modo y qué base encontraste (o faltó).",
    )


class PreguntaElicitacion(BaseModel):
    """Una pregunta con su porqué. Nunca una pregunta suelta sin justificar."""
    pregunta: str = Field(description="La pregunta, directa y en segunda persona.")
    opciones: str = Field(
        default="",
        description=(
            "Si la respuesta tiene opciones acotadas, enuméralas con su implicancia para que el "
            "estudiante elija con información. Vacío si es una pregunta abierta."
        ),
    )
    por_que_importa: str = Field(
        description="Una línea: qué parte del proyecto o qué ítem de la rúbrica depende de esta respuesta."
    )


class Elicitacion(BaseModel):
    """Entregable del elicitador. `molde` es obligatorio: era lo que siempre se caía."""
    encuadre: str = Field(
        description=(
            "2-3 líneas sin rodeos: por qué todavía no puedes redactarlo con rigor y qué decisiones "
            "son SUYAS, no tuyas. Nada de disculpas largas."
        )
    )
    preguntas: list[PreguntaElicitacion] = Field(
        description=(
            "Entre 4 y 7 preguntas, de la más determinante a la menos. Recuerda que el TIPO "
            "(aplicada/básica) y el DISEÑO (pre-experimental, cuasi, descriptiva…) son DOS preguntas "
            "distintas: nunca las juntes en una sola."
        )
    )
    molde: str = Field(
        description=(
            "El molde VACÍO que tendrá el entregable cuando el estudiante responda, con huecos entre "
            "<ángulos>. Es una plantilla, NUNCA una propuesta concreta para su proyecto."
        )
    )


class IdeaProyecto(BaseModel):
    """Una opción de tema. Todos los campos son OBLIGATORIOS a propósito.

    En prosa libre el modelo dejaba caer sistemáticamente los últimos requisitos del
    prompt (el riesgo y la sublínea). Como esquema no puede: si falta un campo, la
    respuesta no valida. Es el mismo principio que contar las palabras del título en
    Python en vez de pedírselo al LLM.
    """
    dominio: str = Field(description="Sector de aplicación en 1-3 palabras (p. ej. «logística», «salud»).")
    problema: str = Field(
        description="Qué falla hoy y en qué tipo de organización. Concreto, no genérico."
    )
    indicador: str = Field(
        description=(
            "Cómo se MIDE hoy ese problema: la variable dependiente, con su unidad "
            "(minutos, %, soles, tasa de error, exactitud, cobertura)."
        )
    )
    artefacto: str = Field(description="Lo que construiría el estudiante: la variable independiente.")
    por_que_mueve_el_indicador: str = Field(
        description=(
            "Mecanismo por el que ESE artefacto mueve ESE indicador. Si no puedes explicarlo en una "
            "frase creíble, la idea no sirve: cámbiala. Es lo primero que ataca un jurado."
        )
    )
    datos: str = Field(
        description="De dónde saldrían los datos. Fuente concreta y realista; di la verdad sobre la dificultad."
    )
    riesgo: str = Field(
        description=(
            "El riesgo principal REAL: acceso a la organización, permisos, comité de ética y "
            "consentimiento si hay personas o datos clínicos, disponibilidad del dataset, presupuesto. "
            "Nunca lo dejes vacío ni pongas «ninguno»."
        )
    )
    sublinea: str = Field(
        description=(
            "Sublínea EXACTA de la Línea 03 en la que encaja (p. ej. «Inteligencia artificial», "
            "«Sistemas de información», «Gestión de datos e información»)."
        )
    )


class Ideacion(BaseModel):
    """Entregable del ideador: opciones aterrizadas + cierre."""
    encuadre: str = Field(
        default="",
        description=(
            "2-4 líneas de encuadre. Si el estudiante venía con la tecnología decidida y sin "
            "problema, aquí es donde lo reconduces. Sin consejos de autoayuda."
        ),
    )
    ideas: list[IdeaProyecto] = Field(
        description="Entre 3 y 5 opciones, de DOMINIOS DISTINTOS salvo que el estudiante ya haya fijado uno."
    )
    aviso_duplicidad: str = Field(
        default="",
        description=(
            "Si el material trae TESIS YA APROBADAS parecidas, nómbralas aquí y di cómo diferenciarse. "
            "Vacío si no había ninguna."
        ),
    )
    pregunta_cierre: str = Field(
        description="UNA sola pregunta: a cuál de esas organizaciones o fuentes de datos tiene ACCESO REAL."
    )


class SintesisDebate(BaseModel):
    """Entregable del integrador: texto + observaciones aparte."""
    texto_mejorado: str = Field(
        description=(
            "Versión redactada/mejorada de SOLO el fragmento o sección que pidió el estudiante, "
            "lista para pegar en su proyecto. Sin notas ni avisos dentro: solo el texto de la tesis. "
            "Respeta el enfoque; no fuerces lo que el tipo de investigación no requiere. "
            "Las tablas, en markdown simple. Cadena vacía si la consulta no pedía redactar texto."
        )
    )
    recomendaciones: str = Field(
        default="",
        description=(
            "Observaciones que NO van dentro del texto: incongruencias con el enfoque/diseño, "
            "problemas de coherencia con otras secciones, qué debe verificar o buscar el estudiante, "
            "redactadas como sugerencias accionables. Cadena vacía si no hay nada que observar."
        ),
    )


class Veredicto(BaseModel):
    """Salida del VALIDADOR. No redacta: audita."""
    aprobado: bool = Field(
        description=(
            "True solo si el entregable cumple las reglas UPAO, no inventa nada y responde lo "
            "que el estudiante pidió. Ante la duda, False."
        )
    )
    problemas: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de incumplimientos concretos y accionables (qué está mal y cómo corregirlo). "
            "Vacía si aprobado=True."
        ),
    )


# ── Utilidades ──────────────────────────────────────────────────────────────

def _formatear_memoria(debate_memory: list) -> str:
    if not debate_memory:
        return "(aún no hay intervenciones del panel)"
    partes = []
    for e in debate_memory:
        partes.append(f"[{e.get('agente', '?')}]\n{e.get('contenido', '')}")
    return "\n\n".join(partes)


def _formatear_elicitacion(out: "Elicitacion", preguntas: list) -> str:
    """Renderiza la elicitación desde el esquema: el molde no puede perderse."""
    partes: list[str] = []
    if (out.encuadre or "").strip():
        partes.append(out.encuadre.strip())
    for i, p in enumerate(preguntas, 1):
        bloque = f"**{i}. {p.pregunta.strip()}**"
        if (p.opciones or "").strip():
            bloque += f"\n   {p.opciones.strip()}"
        if (p.por_que_importa or "").strip():
            bloque += f"\n   *Por qué importa:* {p.por_que_importa.strip()}"
        partes.append(bloque)
    molde = (out.molde or "").strip() or MOLDE_TITULO
    partes.append(
        "**La forma que tendrá cuando me respondas** (es un molde vacío, no una propuesta para tu "
        f"proyecto):\n{molde}"
    )
    return "\n\n".join(partes)


def _formatear_ideacion(out: "Ideacion") -> str:
    """Renderiza las ideas desde el esquema: el formato no depende del modelo."""
    partes: list[str] = []
    if (out.encuadre or "").strip():
        partes.append(out.encuadre.strip())
    for i, idea in enumerate(out.ideas or [], 1):
        partes.append(
            f"**Opción {i} — {idea.dominio.strip()}**\n"
            f"- **Problema:** {idea.problema.strip()}\n"
            f"- **Cómo se mide hoy (variable dependiente):** {idea.indicador.strip()}\n"
            f"- **Artefacto a construir (variable independiente):** {idea.artefacto.strip()}\n"
            f"- **Por qué el artefacto movería ese indicador:** {idea.por_que_mueve_el_indicador.strip()}\n"
            f"- **De dónde saldrían los datos:** {idea.datos.strip()}\n"
            f"- **Riesgo principal a confirmar:** {idea.riesgo.strip()}\n"
            f"- **Sublínea (Línea 03):** {idea.sublinea.strip()}"
        )
    if (out.aviso_duplicidad or "").strip():
        partes.append("**Ojo con la duplicidad:** " + out.aviso_duplicidad.strip())
    if (out.pregunta_cierre or "").strip():
        partes.append("**Para decidir:** " + out.pregunta_cierre.strip())
    return "\n\n".join(partes)


def _formatear_problemas(problemas: list | None) -> str:
    if not problemas:
        return "(sin problemas detectados)"
    return "\n".join(f"{i}. {p}" for i, p in enumerate(problemas, 1))


def _invocar(chain, inputs):
    """Invoca la cadena con los reintentos de backoff compartidos del proyecto.

    Devuelve el modelo pydantic tal cual si la cadena usa `with_structured_output`,
    y el texto plano si devuelve un mensaje. OJO con el orden: `AIMessage` TAMBIÉN
    es un `BaseModel` de pydantic, así que el mensaje debe comprobarse ANTES que el
    modelo estructurado — al revés, los nodos de texto recibirían el AIMessage crudo.
    """
    from backend.graph.nodes._utils import invocar_con_backoff
    salida = invocar_con_backoff(chain, inputs)
    if hasattr(salida, "content"):
        return (salida.content or "").strip()
    if isinstance(salida, BaseModel):
        return salida
    return str(salida).strip()


# ── Prompts de los agentes ──────────────────────────────────────────────────

_PROMPT_TRIAJE = """\
Eres el ENRUTADOR de un panel de mentoría de tesis. NO respondes al estudiante: solo decides qué \
necesita realmente, para que el panel actúe en consecuencia.

Criterio clave — NO SEAS COMPLACIENTE: si el estudiante pide que le redacten algo (título, hipótesis, \
problema, objetivos, justificación…) y NO hay base real para hacerlo con criterio, la respuesta correcta \
NO es inventar un texto plausible: es PREGUNTAR. Eso es "elicitacion".
Hay BASE suficiente si se cumple al menos una:
  - la FICHA DEL PROYECTO de abajo ya trae los datos que gobiernan lo que pide;
  - el MATERIAL DE SU PROYECTO de abajo trae texto real sobre lo que pide;
  - en la CONVERSACIÓN el estudiante ya describió su tema, su organización, su problema o su idea;
  - el estudiante pegó texto en su propio mensaje para que lo trabajes.
Si solo dice «hazme un título» / «redacta mi hipótesis» sin nada de lo anterior → "elicitacion".
Si pregunta algo conceptual, pide ideas, pide que le expliques o pide orientación → "duda".

⚠️ REGLA QUE PESA MÁS QUE LA ANTERIOR — NO REPREGUNTAR:
La FICHA es lo que el estudiante YA respondió, aunque fuera hace varios turnos. Si lo que pide se puede
construir con lo que hay en la ficha, es "redaccion", NO "elicitacion" — aunque falte algún dato: lo que
falte se redacta como asunción explícita y él la corrige. Volver a preguntar algo que ya está en la ficha
es el peor error posible: destruye la confianza del estudiante y no aporta nada.
Solo elige "elicitacion" si la ficha está prácticamente vacía para lo que pide.
Si se queja de que le repites las preguntas o pregunta qué le dijiste → "memoria".

CONSULTA DEL ESTUDIANTE:
{consulta}

SECCIÓN A LA QUE APUNTA (puede venir vacía): {seccion}

FICHA DEL PROYECTO — lo que el estudiante YA declaró en esta asesoría:
{ficha_txt}

MATERIAL DE SU PROYECTO RECUPERADO PARA ESTA CONSULTA:
{contexto_tesis}

ESTADO DEL PROYECTO:
{estado_proyecto}

ÚLTIMOS TURNOS DE LA CONVERSACIÓN:
{historial_txt}"""


_PROMPT_ELICITADOR = """\
Eres el MENTOR ELICITADOR del panel. El estudiante pidió que le redactes algo, pero NO hay base \
suficiente para hacerlo con criterio. Tu trabajo NO es inventar un texto plausible: es hacer las \
PREGUNTAS que permitirán construirlo bien.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

⛔ REGLA NÚMERO UNO — NO REPREGUNTAR LO YA RESPONDIDO:
Abajo tienes la FICHA DEL PROYECTO: todo lo que el estudiante YA te dijo en esta asesoría, y los turnos \
recientes de la conversación. Preguntar de nuevo algo que ya está ahí es el peor error que puedes \
cometer: el estudiante siente que no lo escuchas y abandona.
- Pregunta ÚNICAMENTE por los campos que la ficha marca como no dichos.
- Si un dato está en la ficha, DALO POR BUENO y no lo menciones como pregunta.
- En el `encuadre`, empieza reconociendo en una línea lo que ya sabes de su proyecto (nómbralo: su \
problema, su organización), para que vea que partes de lo suyo y no de cero.
- Si la ficha ya trae casi todo, haz 1 o 2 preguntas como mucho. No rellenes hasta cuatro por inercia.

CÓMO DEBES RESPONDER (rellena TODOS los campos del esquema; ninguno es opcional):
- `encuadre`: 2-3 líneas, sin rodeos, sobre por qué no puedes redactarlo todavía con rigor y qué \
decisiones son SUYAS y no tuyas. Nada de disculpas largas. Si viene con la solución decidida y busca \
dónde aplicarla, reconduce aquí al problema.
- `preguntas`: entre 1 y 7 —tantas como campos falten de verdad, ni una más—, ordenadas de la más \
determinante a la menos. Cada una con su \
`por_que_importa` (qué parte del proyecto o qué ítem de la rúbrica depende de ella) y, si la respuesta \
tiene opciones acotadas, con `opciones` para que elija con información.
- ⚠️ El TIPO (aplicada/básica) y el DISEÑO (pre-experimental, cuasi-experimental, descriptiva, \
correlacional) van en DOS PREGUNTAS SEPARADAS. Si las fundes en una, el estudiante contesta solo \
«aplicada» y se queda sin declarar el diseño, que es lo que decide si necesita hipótesis y medición \
pre/post.
- Cubre siempre, si aplican al pedido: el PROBLEMA real y CÓMO SE MIDE HOY (la variable dependiente); \
la ORGANIZACIÓN; el artefacto (variable independiente); el año SOLO si su estudio se ciñe a un periodo; \
y el acceso REAL a los datos y a la organización.
- `molde`: la forma VACÍA que tendrá el entregable cuando responda, con huecos entre <ángulos>. Es una \
plantilla, NUNCA una propuesta ya hecha para su proyecto.

PROHIBIDO: proponer un título, hipótesis u objetivo concreto como si fuera suyo; inventar la \
organización, los datos, los autores o las cifras.

CONSULTA DEL ESTUDIANTE:
{consulta}

FICHA DEL PROYECTO — lo que YA te dijo (NO lo vuelvas a preguntar):
{ficha_txt}

ÚLTIMOS TURNOS DE LA CONVERSACIÓN:
{historial_txt}

LO POCO QUE SE SABE DE SU PROYECTO:
{contexto_tesis}

CRITERIOS DE LA RÚBRICA QUE GOBIERNAN LO QUE PIDE:
{criterios_rubrica}"""


_PROMPT_IDEADOR = """\
Eres el MENTOR DE IDEACIÓN del panel. El estudiante no tiene tema, o solo tiene una tecnología o un \
dominio en la cabeza. Tu trabajo NO es darle consejos genéricos de autoayuda («piensa en tus \
intereses», «habla con tus profesores»): eso no le sirve de nada. Tu trabajo es ATERRIZARLE opciones \
concretas y realistas para SU programa.

{marco}

{aviso_solucion_primero}

{aviso_etico}

{tesis_similares}

CÓMO DEBES RESPONDER (obligatorio):
- Rellena TODOS los campos del esquema para CADA idea. Ninguno es opcional.
- `problema` + `indicador`: el problema debe venir con la forma en que se MIDE hoy, con unidad.
  Sin indicador no hay variable dependiente y la idea no sirve.
- `por_que_mueve_el_indicador`: si no puedes explicar en una frase creíble por qué ese artefacto
  mueve ese indicador, DESCARTA la idea y propón otra. Es lo primero que ataca un jurado.
- `riesgo`: nunca vacío, nunca «ninguno». Si la idea toca personas o datos clínicos, el riesgo es
  el comité de ética y el consentimiento informado, y debes decirlo.
- `sublinea`: la sublínea EXACTA de la Línea 03 listada arriba. Es lo que declarará en Generalidades.
- Propón ideas de DOMINIOS DISTINTOS entre sí, salvo que el estudiante ya haya fijado un dominio.
- `encuadre`: si venía con la tecnología decidida y sin problema, reconduce ahí (ver aviso de arriba).
- `aviso_duplicidad`: si arriba aparecen TESIS YA APROBADAS parecidas, nómbralas y di cómo diferenciarse.
- `pregunta_cierre`: UNA sola pregunta sobre a qué organización o fuente de datos tiene ACCESO REAL.
  Esa respuesta decide el tema, no el gusto.

PROHIBIDO: consejos vagos de motivación; inventar organizaciones, cifras, datasets o antecedentes; \
prometer que un dataset existe si no lo sabes; proponer un alcance imposible para 1-2 tesistas en un ciclo.

PROHIBIDO TAMBIÉN — ATRIBUIRLE UN TEMA QUE NO TIENE: su línea de investigación es UNA y está fijada por \
resolución (la de arriba). NO le digas que su línea «es sobre X», ni des por hecho que su tema es de \
educación, salud, agro ni ningún otro dominio, salvo que ÉL lo haya dicho en «LO QUE YA SE SABE DE ÉL» o \
en su consulta. Si no ha declarado dominio, ofrécele opciones de VARIOS dominios distintos y que elija él.

CONSULTA DEL ESTUDIANTE:
{consulta}

LO QUE YA SE SABE DE ÉL (si dice que no hay proyecto cargado, es que NO sabes nada de su tema):
{contexto_tesis}"""


_PROMPT_ASESOR = """\
Eres el ASESOR METODOLÓGICO del panel. El estudiante hizo una consulta que se responde con \
explicación y orientación, no redactando una sección de su tesis.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

REGLAS:
- Fundamenta lo metodológico en los FRAGMENTOS DE LIBROS de abajo (son tu memoria: libros de \
metodología de la investigación). Menciona el libro de forma natural cuando uses una idea suya.
- NO inventes autores, teorías, cifras ni citas que no estén en los fragmentos. Si no alcanzan, dilo.
- Si la consulta toca su proyecto, apóyate en el MATERIAL DE SU PROYECTO.
- Da consejos PRÁCTICOS y accionables, como un profesor con experiencia: dónde buscar, qué hacer \
primero, qué error evitar. Concreto, no genérico.
- Si te pide IDEAS de tema, propón enfoques a partir del alcance real del programa (los patrones del \
repositorio), y aterriza cada idea en problema → variable dependiente medible → artefacto propuesto.
- Si detectas la mentalidad «solución primero», reconduce al problema.
- Si te piden EVALUAR o CALIFICAR (poner nota), aclara que para eso la red de agentes hace la revisión \
formal y que te lo pida con «evalúa…». Tú orientas y resuelves dudas.

CONSULTA DEL ESTUDIANTE:
{consulta}

FICHA DEL PROYECTO — lo que el estudiante YA declaró en esta asesoría (dalo por sabido: responderle \
como si no lo hubiera dicho es el error que más lo frustra):
{ficha_txt}

MATERIAL DE SU PROYECTO:
{contexto_tesis}

FRAGMENTOS DE LIBROS:
{contexto_libros}

CRITERIOS DE LA RÚBRICA RELEVANTES:
{criterios_rubrica}"""


_PROMPT_REDACTOR_METODOLOGICO = """\
Eres el REDACTOR METODÓLOGO del panel. {especialista}

Tu foco: que lo redactado sea metodológicamente CORRECTO y cumpla la rúbrica UPAO (trazabilidad \
problema → objetivos → hipótesis → variables → método), no que suene bonito.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

Fundamenta en los FRAGMENTOS DE LIBROS. No inventes autores, teorías ni citas que no estén ahí.

USA LA FICHA COMO FUENTE PRINCIPAL: son los datos que el estudiante YA te dio. Su problema, su \
organización y su diseño salen de ahí, no de tu imaginación.
Si falta algún dato para completar la redacción, NO lo inventes en silencio y NO pares a preguntar: \
redáctalo con el supuesto más razonable y márcalo en línea como `[ASUNCIÓN: …]`. Así el estudiante \
corrige en una frase en vez de rellenar otro cuestionario.

CONSULTA DEL ESTUDIANTE:
{consulta}

FICHA DEL PROYECTO — lo que el estudiante YA declaró:
{ficha_txt}

BASE REAL DEL ESTUDIANTE (puede venir partida en fragmentos: reensámblala; no asumas que algo falta \
solo porque no aparece en el primer fragmento):
{contexto_tesis}

CRITERIOS DE LA RÚBRICA A SATISFACER:
{criterios_rubrica}

FRAGMENTOS DE LIBROS:
{contexto_libros}

Entrega tu PROPUESTA DE REDACCIÓN del fragmento pedido, seguida de una nota breve con lo que quedó \
apoyado en la base real y lo que es inferencia tuya (y por tanto el estudiante debe confirmar). \
Sé concreto y con suficiente desarrollo: nada de dos frases sueltas."""


_PROMPT_REDACTOR_DOMINIO = """\
Eres el REDACTOR DE DOMINIO del panel (ingeniería de sistemas aplicada). Tu foco: que lo redactado \
sea VIABLE y esté aterrizado en el contexto real del estudiante — la organización, el proceso, los \
datos disponibles, la tecnología y el alcance ejecutable en un ciclo académico.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

El REDACTOR METODÓLOGO ya hizo su propuesta. DEBES reaccionar a ella: señala al menos un punto donde \
discrepas o donde su versión no es viable/aterrizada, y luego entrega TU versión mejorada. No repitas \
la suya sin más.

Estructura tu respuesta así:
REACCIÓN AL METODÓLOGO: [en qué coincides y en qué su propuesta falla de viabilidad, alcance o contexto]
MI VERSIÓN: [tu propuesta de redacción completa]
RIESGOS QUE EL ESTUDIANTE DEBE CONFIRMAR: [acceso a datos, acceso a la organización, instrumentos que \
tendrá que buscar validados o validar, presupuesto — solo los que apliquen; no inventes que los tiene]

CONSULTA DEL ESTUDIANTE:
{consulta}

FICHA DEL PROYECTO — lo que el estudiante YA declaró (fuente principal; lo que falte se marca \
`[ASUNCIÓN: …]`, nunca se inventa en silencio ni se para a preguntar):
{ficha_txt}

BASE REAL DEL ESTUDIANTE:
{contexto_tesis}

CRITERIOS DE LA RÚBRICA A SATISFACER:
{criterios_rubrica}

FRAGMENTOS DE LIBROS:
{contexto_libros}

PROPUESTA DEL METODÓLOGO (responde a esto):
{historial_panel}"""


_PROMPT_INTEGRADOR = """\
Eres el INTEGRADOR del panel. No debates: RESUELVES el debate de los dos redactores y produces el \
entregable. Toma lo más sólido de cada propuesta y descarta lo que fue refutado.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

CONSULTA DEL ESTUDIANTE:
{consulta}

BASE REAL DEL ESTUDIANTE:
{contexto_tesis}

CRITERIOS DE LA RÚBRICA:
{criterios_rubrica}

DEBATE COMPLETO DE LOS REDACTORES:
{historial_panel}

REGLAS DEL ENTREGABLE:
- TRABAJA SOBRE LA BASE REAL DE ARRIBA: ese es el texto del estudiante (ya indexado). Tu \
`texto_mejorado` es la versión redactada de SU proyecto, NO un ejemplo genérico. Si hay base, NUNCA \
digas «no tengo acceso a tu texto» ni inventes uno de muestra.
- PRESERVA SU CONTENIDO REAL: mejora la REDACCIÓN, la estructura y la completitud, NUNCA la SUSTANCIA. \
No cambies sus variables ni sus nombres, no inventes variables/dimensiones/indicadores nuevos ni \
reemplaces los suyos. CONSERVA sus CITAS, autores, datos y factores específicos; NUNCA los sustituyas \
por afirmaciones genéricas ni los borres. EDITA su texto (no escribas uno nuevo desde cero, no lo resumas).
- Si le falta algo para cumplir la rúbrica, complétalo de forma coherente con SU proyecto; si no hay \
base para ello, dilo en `recomendaciones` en vez de inventarlo.
- EXTENSIÓN: entrega texto SUFICIENTE para lo que la sección exige. No devuelvas un par de frases \
cuando se pide una sección de desarrollo; tampoco rellenes con paja.
- ÁMBITO: es un PROYECTO (propuesta), NO una tesis terminada: aún NO hay resultados, discusión ni \
conclusiones. No agregues ni pidas esas secciones.
- OPERACIONALIZACIÓN DE VARIABLES: NUNCA la entregues como tabla (es ancha y se rompe en el chat) ni \
copies la tabla cruda del PDF. Preséntala SIEMPRE como LISTA con viñetas anidadas, MISMO formato para \
TODAS las variables: «- **Variable independiente: <nombre>**» y debajo «- Definición conceptual: …», \
«- Definición operacional: …», «- Dimensiones: …», «- Indicadores: …», «- Ítems: …», «- Escala de \
medición: …»; igual para la dependiente. No dejes una variable en tabla y otra en lista.

Devuelve DOS campos separados:
- `texto_mejorado`: la versión redactada de SOLO el fragmento pedido, lista para entregar (sin notas dentro).
- `recomendaciones`: lo que NO va dentro del texto (incongruencias, riesgos a confirmar, qué debe \
buscar o validar el estudiante), como sugerencias accionables."""


_PROMPT_VALIDADOR = """\
Eres el VALIDADOR del panel. NO redactas: AUDITAS el entregable que produjo el panel antes de que \
llegue al estudiante. Tu deber es impedir que se le entregue algo inventado, complaciente o que \
incumpla las reglas UPAO. Ante la duda, RECHAZA.

{marco}

{enfoque}

{aviso_no_aplica}

{aviso_no_se}

{aviso_etico}

{tesis_similares}

CHEQUEOS AUTOMÁTICOS YA EJECUTADOS (son HECHOS verificados por el sistema, no opiniones: si esta \
lista trae algo, el entregable NO puede aprobarse y debes incluirlos entre los problemas):
{chequeos_deterministas}

AUDITA ADEMÁS, uno por uno:
1. ALUCINACIÓN: ¿hay autores, años, cifras, porcentajes, nombres de organizaciones, instrumentos o \
resultados que NO aparecen ni en la base del estudiante ni en los fragmentos de libros? Cualquier dato \
inventado es motivo de rechazo.
2. SUSTANCIA DEL ESTUDIANTE: ¿se conservaron sus variables, sus citas y sus datos concretos, o el \
panel los reemplazó por genéricos?
2b. ATRIBUCIONES FALSAS: ¿el entregable afirma algo sobre EL PROYECTO DEL ESTUDIANTE que él nunca dijo? \
Ejemplos de rechazo inmediato: darle por hecho un dominio o sector («tu línea de investigación sobre IA y \
educación», «tu proyecto sobre salud»), una organización, un tipo o diseño de investigación, o que ya \
tiene datos. Su línea es UNA y fija; el dominio lo elige ÉL. Si no consta en el material real, es invención.
3. RÚBRICA: ¿cumple los criterios listados abajo? Señala el ítem que quede corto.
4. COHERENCIA CON EL TIPO/DISEÑO declarado: ¿pide o asume algo que ese enfoque no requiere, o al revés?
5. ÁMBITO: ¿se coló algo de resultados, discusión o conclusiones? Es un PROYECTO: no corresponde.
6. COMPLACENCIA: ¿el panel le dio la razón al estudiante sin base, o afirmó que tiene datos, acceso, \
presupuesto o instrumentos que en ninguna parte consta que tenga?
7. SUFICIENCIA: ¿el texto tiene el desarrollo que la sección exige, o se quedó en un par de frases?

CONSULTA DEL ESTUDIANTE:
{consulta}

SECCIÓN OBJETIVO: {seccion}

BASE REAL DEL ESTUDIANTE (única fuente legítima de sus datos):
{contexto_tesis}

FRAGMENTOS DE LIBROS (única fuente legítima de teoría y autores):
{contexto_libros}

CRITERIOS DE LA RÚBRICA:
{criterios_rubrica}

ENTREGABLE A AUDITAR — TEXTO:
{texto_sintetizado}

ENTREGABLE A AUDITAR — RECOMENDACIONES:
{recomendaciones}

Responde con `aprobado` y, si es False, `problemas`: una lista de incumplimientos CONCRETOS, cada uno \
diciendo qué está mal y cómo corregirlo."""


_PROMPT_CORRECTOR = """\
Eres el CORRECTOR del panel. El VALIDADOR rechazó el entregable. Tu única tarea es rehacerlo \
corrigiendo TODOS los problemas listados, sin introducir ninguno nuevo.

{marco}

{enfoque}

REGLAS INNEGOCIABLES:
- Corrige CADA problema de la lista. Si un problema dice que hay datos o citas inventadas, ELIMÍNALOS: \
no los sustituyas por otros inventados. Cuando falte un dato que solo el estudiante puede aportar, \
déjalo señalado en `recomendaciones` como algo que él debe completar o verificar.
- Si el problema es de longitud del título, recorta hasta cumplir el máximo contando TODAS las palabras \
(los conectores «y», «o», «de», «la», «en», «para» cuentan) sin perder variables, espacio ni tiempo.
- No cambies la sustancia del estudiante (sus variables, sus citas reales, sus datos).
- Mantén el resto del entregable que sí estaba bien.

PROBLEMAS DETECTADOS POR EL VALIDADOR:
{problemas}

CONSULTA DEL ESTUDIANTE:
{consulta}

BASE REAL DEL ESTUDIANTE:
{contexto_tesis}

FRAGMENTOS DE LIBROS:
{contexto_libros}

CRITERIOS DE LA RÚBRICA:
{criterios_rubrica}

ENTREGABLE RECHAZADO — TEXTO:
{texto_sintetizado}

ENTREGABLE RECHAZADO — RECOMENDACIONES:
{recomendaciones}

Devuelve el entregable corregido en los dos campos (`texto_mejorado` y `recomendaciones`)."""


_PROMPT_ESTRUCTURADOR = """\
Eres MentorIA, un mentor metodológico que acompaña a un estudiante de la UPAO en su PROYECTO de tesis, \
en un chat. Un panel interno ya preparó el material; tu tarea es entregar UNA respuesta clara, cálida y \
bien estructurada en español y markdown.

MODO DE ESTA RESPUESTA: {modo}
- Si es `elicitacion`: entrega la explicación y las PREGUNTAS tal como vienen del análisis. NO propongas \
tú un título/hipótesis/objetivo concreto: el objetivo del turno es que el estudiante responda. Deja claro \
que en cuanto conteste, se lo redactas.
- Si es `duda`: entrega la explicación y los consejos. Sé concreto y útil.
- Si es `redaccion`: incluye (1) una explicación breve de qué cambió y por qué; (2) el TEXTO en un bloque \
claro, titulado «Tu <sección>» — NUNCA lo presentes como «un ejemplo de cómo podrías estructurarlo»: es SU \
texto redactado; (3) las recomendaciones y lo que debe verificar; (4) lineamientos para alcanzar el máximo \
según la rúbrica.

REGLAS:
- NO menciones el mecanismo interno (no hables de «agentes», «panel», «validador» ni «debate»): responde \
como un mentor.
- NO inventes citas ni autores. Sigue el hilo de la conversación.
- Si el estudiante YA subió su proyecto, NUNCA le pidas compartir, pegar ni subir su texto: trabaja con el \
material del análisis.
- ÁMBITO: es un PROYECTO (propuesta), NO una tesis terminada: aún NO tiene resultados, discusión ni \
conclusiones. No ofrezcas ayuda con esas etapas.
- Si te piden EVALUAR o CALIFICAR (poner nota), aclara que para eso la red de agentes hará la revisión \
formal (máxima precisión, pero toma más tiempo) y que te lo pida con «evalúa…». Tú aquí orientas y \
redactas rápido.
- Sé directo y conciso: nada de relleno.

MATERIAL DEL ANÁLISIS INTERNO:
- TEXTO PREPARADO (puede estar vacío):
{texto_sintetizado}

- RECOMENDACIONES / OBSERVACIONES:
{recomendaciones}

- CRITERIOS DE LA RÚBRICA RELEVANTES:
{criterios_rubrica}

- SÍNTESIS DEL ANÁLISIS DEL PANEL:
{historial_panel}

{aviso_no_aplica}"""


# ── Nodos del grafo ─────────────────────────────────────────────────────────

def _nodo_recuperacion(state: EstadoDebate) -> dict:
    """Reúne TODO el contexto: libros, tesis, rúbrica, enfoque y marco UPAO."""
    from .conversador import _recuperar_libros, _estado_proyecto
    from .rubrica_chat import criterios_relevantes

    doc = state.get("doc")
    biblioteca = state.get("biblioteca")
    consulta = state.get("consulta", "")

    libros, _fuente = _recuperar_libros(biblioteca, consulta)

    criterios, seccion = "", None
    if doc is not None:
        try:
            criterios, seccion = criterios_relevantes(doc, consulta)
        except Exception as exc:
            logger.warning(f"[mini_grafo] No se pudieron resolver criterios: {exc}")

    # COHERENCIA con el grafo grande: si ya hay un TEXTO CORREGIDO de esta sección (de una
    # revisión previa o de una mejora del chat), parte de ÉL — no del original — para no
    # reinventar ni contradecir lo que la red grande ya decidió.
    tesis = ""
    base_corregida = ""
    if doc is not None and seccion:
        m = (getattr(doc, "mejoras", None) or {}).get(seccion)
        if m and m.get("texto"):
            base_corregida = m["texto"]

    if base_corregida:
        tesis = base_corregida
        logger.info(f"[mini_grafo] Partiendo del texto corregido de «{seccion}» (coherencia con la red).")
    elif doc is not None and getattr(doc, "vector_store", None) is not None:
        from backend.rag import recuperar_con_vecinos, limpiar_marcas_rag
        try:
            crudo = recuperar_con_vecinos(
                doc.vector_store, consulta, seccion=seccion, k=5, ventana=1
            )
            tesis = limpiar_marcas_rag(crudo)
        except Exception as exc:
            logger.warning(f"[mini_grafo] RAG tesis con vecinos falló: {exc}")

    enfoque, tipo_declarado = "", False
    estado = _estado_proyecto(doc)
    if doc is not None:
        try:
            from .tipo_investigacion import obtener_tipo_diseno
            from backend.enfoque import bloque_enfoque
            tipo, diseno = obtener_tipo_diseno(doc)
            enfoque = bloque_enfoque(tipo, diseno)
            tipo_declarado = bool((diseno or "").strip())
        except Exception as exc:
            logger.warning(f"[mini_grafo] No se pudo detectar el tipo: {exc}")

    _similares = tesis_similares(f"{consulta} {tesis[:400]}")
    _motivo = requiere_resguardo_etico(consulta, tesis)
    logger.info(
        f"[mini_grafo] Recuperación lista | sección: {seccion or '—'} | "
        f"rúbrica: {'sí' if criterios else 'no'} | tesis: {len(tesis)} chars"
    )
    from .ficha import bloque_ficha, faltantes as _faltantes_ficha

    ficha = state.get("ficha") or {}

    return {
        "ficha_txt": bloque_ficha(ficha),
        "faltantes": _faltantes_ficha(ficha),
        "contexto_libros": libros or "(sin fragmentos de libros recuperados)",
        "contexto_tesis": tesis or "(sin fragmentos de la tesis — el proyecto no está cargado o no trata de esto)",
        "criterios_rubrica": criterios or "(el estudiante no cargó una rúbrica; usa la rúbrica UPAO estándar y criterios metodológicos)",
        "seccion": seccion or "",
        "enfoque": enfoque,
        "estado_proyecto": estado,
        "aviso_no_aplica": nota_no_aplica(seccion),
        "tipo_declarado": tipo_declarado,
        # Coteja la idea del estudiante contra las tesis REALES ya aprobadas del programa,
        # para poder avisarle si está a punto de duplicar una.
        "tesis_similares": bloque_tesis_similares(_similares),
        "tesis_similares_lista": _similares,
        # Patrón «tengo la tecnología, busco dónde aplicarla»: se detecta de forma
        # determinista para que la reconducción no dependa de que el LLM se acuerde.
        "aviso_solucion_primero": (
            AVISO_SOLUCION_PRIMERO if detectar_solucion_primero(consulta) else ""
        ),
        # El estudiante dijo «no sé» a algo determinante: hay que ensenarle, no seguir de largo.
        "aviso_no_se": AVISO_NO_SE if detectar_no_se(consulta) else "",
        # Personas o datos sensibles -> Art. 71: comite de etica y consentimiento informado.
        "aviso_etico": (aviso_etico(_motivo) if _motivo else ""),
        "debate_memory": [],
        "problemas": [],
        "advertencias": [],
        "intentos": 0,
    }


def _historial_txt(historial: list[dict] | None, turnos: int = 8) -> str:
    """Rinde la conversación para los prompts SIN mutilar al estudiante.

    Antes se truncaba todo a 200 caracteres, y como las respuestas del estudiante
    son largas («1. …Respuesta: …» × 7), lo que llegaba al modelo era el arranque
    de la lista de preguntas del propio mentor: parecía que no había contestado
    nada. Los turnos del ESTUDIANTE son la fuente de datos y van íntegros; los del
    mentor son contexto y se recortan, que además son los que inflan el prompt.
    """
    lineas = []
    for t in (historial or [])[-turnos:]:
        contenido = (t.get("contenido") or "").strip()
        if not contenido:
            continue
        if t.get("rol") == "user":
            lineas.append(f"Estudiante: {contenido[:2000]}")
        else:
            lineas.append(f"MentorIA: {contenido[:300]}")
    return "\n".join(lineas) or "(sin turnos previos)"


def _nodo_triaje(state: EstadoDebate) -> dict:
    """Decide la ruta: aclarar duda, preguntar antes de redactar, o redactar."""
    from .ficha import es_meta_pregunta, hay_base_para_redactar

    consulta = state.get("consulta", "")
    ficha = state.get("ficha") or {}
    previas = state.get("elicitaciones_previas", 0)

    # ATAJO DETERMINISTA. «¿sabes lo que te dije?» es justo el turno en que el
    # estudiante ya perdió la confianza: no puede depender de que el LLM acierte
    # la clasificación. Se le devuelve su ficha, sin panel y sin preguntas.
    if es_meta_pregunta(consulta):
        logger.info("[mini_grafo/triaje] Meta-pregunta detectada → modo 'memoria'")
        return {"modo": "memoria", "justificacion_triaje": "pregunta por lo ya dicho"}

    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_TRIAJE),
        ("human", "Clasifica qué necesita el estudiante."),
    ]) | llm_rapido(temperatura=0.0).with_structured_output(Triaje)

    inputs = {
        "consulta": consulta,
        "seccion": state.get("seccion") or "(no resuelta)",
        "ficha_txt": state.get("ficha_txt", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "estado_proyecto": state.get("estado_proyecto", ""),
        "historial_txt": _historial_txt(state.get("historial")),
    }
    try:
        out = _invocar(chain, inputs)
        modo, just = out.modo, out.justificacion
    except Exception as exc:
        logger.warning(f"[mini_grafo/triaje] Falló: {exc}")
        # Degradación segura: sin base útil preferimos preguntar antes que inventar.
        # La ficha cuenta como base tanto como el texto recuperado del PDF.
        base = state.get("contexto_tesis") or ""
        modo = (
            "redaccion"
            if len(base) > _MIN_BASE_UTIL or hay_base_para_redactar(ficha)
            else "elicitacion"
        )
        just = "(triaje por defecto)"

    # CORTACIRCUITOS. Dos tandas de preguntas seguidas y el estudiante sigue sin
    # su entregable: insistir una tercera vez no le va a sacar más información,
    # solo lo va a hartar. Se redacta con lo que hay y lo que falte se marca como
    # asunción explícita, que él puede corregir en una línea.
    if modo == "elicitacion" and previas >= _MAX_ELICITACIONES_SEGUIDAS:
        logger.info(
            f"[mini_grafo/triaje] {previas} elicitaciones seguidas → fuerzo 'redaccion' "
            "con asunciones explícitas (cortacircuitos anti-bucle)."
        )
        modo = "redaccion"
        just = f"cortacircuitos: ya se le preguntó {previas} veces seguidas"

    # La ficha ya alcanza para redactar: no se vuelve a preguntar aunque el
    # clasificador se haya puesto exigente.
    elif modo == "elicitacion" and hay_base_para_redactar(ficha):
        logger.info("[mini_grafo/triaje] La ficha ya da base → 'redaccion' en vez de repreguntar.")
        modo = "redaccion"
        just = "la ficha del proyecto ya tiene base suficiente"

    logger.info(f"[mini_grafo/triaje] modo={modo} | {just}")
    return {"modo": modo, "justificacion_triaje": just}


def _ruta_triaje(state: EstadoDebate) -> str:
    modo = state.get("modo", "duda")
    if modo == "memoria":
        return "memoria"
    if modo == "ideacion":
        return "ideador"
    if modo == "elicitacion":
        return "elicitador"
    if modo == "redaccion":
        return "redactor_metodologico"
    return "asesor"


def _nodo_memoria(state: EstadoDebate) -> dict:
    """Responde «¿sabes lo que te dije?» devolviéndole su ficha, sin LLM.

    Es determinista a propósito: no puede inventar un dato que el estudiante no
    dio ni olvidar uno que sí dio, que es exactamente lo que se le está
    reprochando al sistema en ese turno.
    """
    from .ficha import resumen_para_estudiante

    contenido = resumen_para_estudiante(state.get("ficha"))
    logger.info("[mini_grafo/memoria] Devuelvo la ficha registrada (sin llamada al LLM).")
    return {"respuesta_final": contenido, "texto_sintetizado": "", "recomendaciones": contenido}


def _nodo_elicitador(state: EstadoDebate) -> dict:
    """Sin base suficiente: pregunta con criterio en vez de inventar."""
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_ELICITADOR),
        ("human", "Elabora las preguntas que necesitas para poder redactarlo bien."),
    ]) | llm_rapido(temperatura=0.3).with_structured_output(Elicitacion)

    inputs = {
        "marco": marco_para("elicitador"),
        "enfoque": state.get("enfoque", "") or "(el estudiante aún no declaró tipo ni diseño de investigación)",
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        # Sin estos dos el elicitador redactaba las preguntas a ciegas y repetía
        # las mismas siete tanda tras tanda, aunque el estudiante ya las hubiera
        # contestado en el turno anterior.
        "ficha_txt": state.get("ficha_txt", ""),
        "historial_txt": _historial_txt(state.get("historial")),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
    }
    try:
        out = _invocar(chain, inputs)
        preguntas = _garantizar_tipo_y_diseno(list(out.preguntas or []), state)
        contenido = _formatear_elicitacion(out, preguntas)
    except Exception as exc:
        logger.warning(f"[mini_grafo/elicitador] Falló: {exc}")
        contenido = ""
    memoria = list(state.get("debate_memory") or [])
    memoria.append({"agente": "elicitador", "contenido": contenido})
    # La elicitación NO produce texto de tesis: solo preguntas.
    return {"debate_memory": memoria, "texto_sintetizado": "", "recomendaciones": contenido}


def _garantizar_tipo_y_diseno(preguntas: list, state: EstadoDebate) -> list:
    """Si el estudiante no declaró tipo/diseño, asegura que se le pregunten POR SEPARADO.

    El modelo tiende a fundirlas en una sola pregunta («¿aplicada, experimental,
    descriptiva?»), y entonces el estudiante contesta «aplicada» y se queda sin
    declarar el diseño — que es lo que decide si necesita hipótesis y medición
    pre/post. Como no se puede confiar en el prompt para esto, se comprueba aquí.

    ⚠️ Pero la inyección solo procede si el dato NO está ya en la ficha. Antes esto
    era una segunda fuente de repetición, independiente del LLM: el estudiante
    escribía «Tipo: Aplicada. Diseño: Cuasi-experimental» y este bloque le volvía a
    preguntar las dos cosas, porque solo miraba el PDF (`tipo_declarado`).
    """
    ficha = state.get("ficha") or {}
    tipo_en_ficha = bool((ficha.get("tipo_investigacion") or "").strip())
    diseno_en_ficha = bool((ficha.get("diseno") or "").strip())

    if state.get("tipo_declarado") or (tipo_en_ficha and diseno_en_ficha):
        return preguntas

    texto = " ".join(f"{p.pregunta} {p.opciones}" for p in preguntas).lower()
    texto = _sin_tildes_local(texto)

    if not diseno_en_ficha and not re.search(r"dise[nñ]o|pre-?experimental|cuasi|correlacional", texto):
        preguntas.append(PreguntaElicitacion(**PREGUNTA_DISENO))
        logger.info("[mini_grafo/elicitador] Inyectada la pregunta de DISEÑO (faltaba).")
    if not tipo_en_ficha and not re.search(r"aplicada|b[áa]sica|orientaci[óo]n|finalidad", texto):
        preguntas.append(PreguntaElicitacion(**PREGUNTA_TIPO_INVESTIGACION))
        logger.info("[mini_grafo/elicitador] Inyectada la pregunta de TIPO (faltaba).")
    return preguntas


def _sin_tildes_local(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")


def _nodo_ideador(state: EstadoDebate) -> dict:
    """Sin tema (o solo con tecnologías): aterriza opciones reales del programa."""
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_IDEADOR),
        ("human", "Propón las líneas de proyecto concretas."),
    ]) | llm_rapido(temperatura=0.4).with_structured_output(Ideacion)

    inputs = {
        "marco": marco_para("ideador"),
        "aviso_solucion_primero": state.get("aviso_solucion_primero", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        # A propósito SIN `contexto_libros`: la biblioteca son libros de METODOLOGÍA, y
        # sus ejemplos (casi siempre de aula, docentes y rendimiento académico) no aportan
        # nada a la ideación de tema; solo contaminan y el modelo acaba creyendo que el
        # estudiante trabaja en educación.
        # El prompt lo lee como «LO QUE YA SE SABE DE ÉL», así que la ficha va aquí: es
        # justo lo que evita proponerle ideas de un dominio que no es el suyo.
        "contexto_tesis": (
            (state.get("ficha_txt", "") or "") + "\n\n" + (state.get("contexto_tesis", "") or "")
        ).strip(),
    }
    try:
        out = _invocar(chain, inputs)
        contenido = _formatear_ideacion(out)
    except Exception as exc:
        logger.warning(f"[mini_grafo/ideador] Falló: {exc}")
        contenido = ""
    memoria = list(state.get("debate_memory") or [])
    memoria.append({"agente": "ideador", "contenido": contenido})
    return {"debate_memory": memoria, "texto_sintetizado": "", "recomendaciones": contenido}


def _nodo_asesor(state: EstadoDebate) -> dict:
    """Consulta conceptual: explica y aconseja, fundamentado en los libros."""
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_ASESOR),
        ("human", "Responde la consulta del estudiante."),
    ]) | llm_rapido(temperatura=0.3)

    inputs = {
        "marco": marco_para("asesor"),
        "enfoque": state.get("enfoque", "") or "(el estudiante aún no declaró tipo ni diseño de investigación)",
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        "ficha_txt": state.get("ficha_txt", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "contexto_libros": state.get("contexto_libros", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
    }
    try:
        contenido = _invocar(chain, inputs)
    except Exception as exc:
        logger.warning(f"[mini_grafo/asesor] Falló: {exc}")
        contenido = ""
    memoria = list(state.get("debate_memory") or [])
    memoria.append({"agente": "asesor", "contenido": contenido})
    return {"debate_memory": memoria, "texto_sintetizado": "", "recomendaciones": contenido}


def _nodo_redactor_metodologico(state: EstadoDebate) -> dict:
    from backend.enfoque import especialista_metodologico

    doc = state.get("doc")
    tipo = "cuantitativa"
    if doc is not None and getattr(doc, "tipo_investigacion", None):
        tipo = doc.tipo_investigacion

    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_REDACTOR_METODOLOGICO),
        ("human", "Entrega tu propuesta de redacción."),
    ]) | llm_rapido(temperatura=0.2)

    inputs = {
        "especialista": especialista_metodologico(tipo),
        "marco": marco_para("redactor"),
        "enfoque": state.get("enfoque", ""),
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        "ficha_txt": state.get("ficha_txt", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "contexto_libros": state.get("contexto_libros", ""),
    }
    memoria = list(state.get("debate_memory") or [])
    try:
        contenido = _invocar(chain, inputs)
    except Exception as exc:
        logger.warning(f"[mini_grafo/redactor_metodologico] Falló: {exc}")
        contenido = "[El redactor metodólogo no pudo intervenir.]"
    memoria.append({"agente": "redactor_metodologico", "contenido": contenido})
    return {"debate_memory": memoria}


def _nodo_redactor_dominio(state: EstadoDebate) -> dict:
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_REDACTOR_DOMINIO),
        ("human", "Reacciona al metodólogo y entrega tu versión."),
    ]) | llm_rapido(temperatura=0.3)

    memoria = list(state.get("debate_memory") or [])
    inputs = {
        "marco": marco_para("redactor"),
        "enfoque": state.get("enfoque", ""),
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        "ficha_txt": state.get("ficha_txt", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "contexto_libros": state.get("contexto_libros", ""),
        "historial_panel": _formatear_memoria(memoria),
    }
    try:
        contenido = _invocar(chain, inputs)
    except Exception as exc:
        logger.warning(f"[mini_grafo/redactor_dominio] Falló: {exc}")
        contenido = "[El redactor de dominio no pudo intervenir.]"
    memoria.append({"agente": "redactor_dominio", "contenido": contenido})
    return {"debate_memory": memoria}


def _nodo_integrador(state: EstadoDebate) -> dict:
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_INTEGRADOR),
        ("human", "Resuelve el debate y entrega el texto y las recomendaciones."),
    ]) | llm_rapido(temperatura=0.3).with_structured_output(SintesisDebate)

    inputs = {
        "marco": marco_para("redactor"),
        "enfoque": state.get("enfoque", ""),
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "consulta": state.get("consulta", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "historial_panel": _formatear_memoria(state.get("debate_memory") or []),
    }
    try:
        out = _invocar(chain, inputs)
        texto = (out.texto_mejorado or "").strip()
        recs = (out.recomendaciones or "").strip()
    except Exception as exc:
        logger.warning(f"[mini_grafo/integrador] Falló: {exc}")
        texto, recs = "", ""
    return {"texto_sintetizado": texto, "recomendaciones": recs}


def _nodo_validador(state: EstadoDebate) -> dict:
    """Audita el entregable. Los chequeos deterministas entran como HECHOS."""
    seccion = state.get("seccion", "")
    texto = state.get("texto_sintetizado", "")
    ctx_tesis = state.get("contexto_tesis", "")
    ctx_libros = state.get("contexto_libros", "")

    # 1) Verificaciones que un LLM hace mal (contar palabras, cotejar apellidos).
    #    `duros` bloquea (regla escrita de la plantilla); `suaves` es consejo para el
    #    estudiante y NUNCA dispara una corrección — si no, el panel acabaría forzando
    #    cosas que las tesis aprobadas del programa tampoco cumplen (p. ej. el año en
    #    el título, ausente en el 41% de ellas).
    duros, suaves = chequeos_deterministas(seccion, texto, ctx_tesis, ctx_libros)
    # Las recomendaciones también pueden traer citas inventadas.
    if state.get("recomendaciones"):
        from backend.upao_tesis import citas_sin_respaldo
        inventadas = citas_sin_respaldo(state["recomendaciones"], ctx_tesis, ctx_libros)
        if inventadas:
            duros.append(
                "Las RECOMENDACIONES citan apellidos sin respaldo en el material real: "
                f"{', '.join(inventadas)}. Quítalos."
            )

    # Atribuirle al estudiante una línea o un tema que no es el suyo condiciona todo lo
    # que haga después, así que se comprueba de forma determinista sobre TODO lo que se
    # le va a entregar (texto + recomendaciones), no solo sobre el texto de tesis.
    entregable = f"{texto}\n{state.get('recomendaciones') or ''}"

    duros.extend(atribuciones_linea_invalidas(
        entregable, ctx_tesis, state.get("consulta", ""), state.get("estado_proyecto", ""),
    ))

    # Si el proyecto toca personas o datos sensibles, el aviso ético NO es opcional
    # (Art. 71). Es lo que tumba un proyecto antes de empezar, así que se comprueba
    # de forma determinista en vez de confiar en que el panel se acuerde.
    if state.get("aviso_etico") and not re.search(
        r"[ée]tic|consentimiento|comit[ée]|anonimiza|autorizaci[óo]n", entregable, re.I
    ):
        duros.append(
            "FALTA EL RESGUARDO ÉTICO: el proyecto involucra personas o datos sensibles y el "
            "entregable no menciona comité de ética, consentimiento informado ni autorización "
            "formal de la organización (Art. 71 del Reglamento UPAO). Añádelo en las "
            "recomendaciones y pregúntale si ya tiene ese acceso comprometido."
        )

    # Un «no sé» del estudiante no puede quedar tapado por un entregable que sigue de largo.
    if state.get("aviso_no_se") and not re.search(
        r"no\s+lo\s+sabes|a[úu]n\s+no|todav[íi]a|provisional|pendiente|debes?\s+(averiguar|confirmar|"
        r"consultar|verificar)|te\s+falta|queda\s+por", entregable, re.I
    ):
        duros.append(
            "EL ESTUDIANTE DIJO «NO SÉ» Y EL ENTREGABLE LO IGNORA: no se puede dar por resuelto lo "
            "que él declaró no saber. Señala explícitamente qué quedó pendiente, enséñale las "
            "opciones concretas de su dominio para que elija, y marca como PROVISIONAL lo que "
            "dependa de ese dato."
        )

    # 2) Auditoría de criterio.
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_VALIDADOR),
        ("human", "Emite tu veredicto."),
    ]) | llm_rapido(temperatura=0.0).with_structured_output(Veredicto)

    inputs = {
        "marco": marco_para("validador"),
        "enfoque": state.get("enfoque", ""),
        "aviso_no_aplica": state.get("aviso_no_aplica", ""),
        "aviso_no_se": state.get("aviso_no_se", ""),
        "aviso_etico": state.get("aviso_etico", ""),
        "tesis_similares": state.get("tesis_similares", ""),
        "chequeos_deterministas": _formatear_problemas(duros),
        "consulta": state.get("consulta", ""),
        "seccion": seccion or "(no resuelta)",
        "contexto_tesis": ctx_tesis,
        "contexto_libros": ctx_libros,
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "texto_sintetizado": texto or "(el panel no produjo texto de tesis en este turno)",
        "recomendaciones": state.get("recomendaciones") or "(sin recomendaciones)",
    }
    try:
        out = _invocar(chain, inputs)
        blandos = [p for p in (out.problemas or []) if (p or "").strip()]
        if out.aprobado and not duros:
            blandos = []
    except Exception as exc:
        logger.warning(f"[mini_grafo/validador] Falló: {exc}")
        blandos = []

    # Los deterministas mandan: si hay alguno, el entregable NO está aprobado.
    problemas = duros + [p for p in blandos if p not in duros]
    logger.info(
        f"[mini_grafo/validador] {'RECHAZA' if problemas else 'APRUEBA'} | "
        f"duros={len(duros)} | de criterio={len(blandos)} | advertencias={len(suaves)}"
    )
    return {"problemas": problemas, "advertencias": suaves}


def _ruta_validador(state: EstadoDebate) -> str:
    """Si hay problemas y quedan vueltas, corrige; si no, entrega."""
    problemas = state.get("problemas") or []
    intentos = state.get("intentos", 0)
    if problemas and intentos < _MAX_CORRECCIONES:
        return "corrector"
    if problemas:
        logger.warning(
            f"[mini_grafo] Se agotaron las {_MAX_CORRECCIONES} correcciones con "
            f"{len(problemas)} problema(s) abierto(s); se entrega con las observaciones."
        )
    return "estructurador"


def _nodo_corrector(state: EstadoDebate) -> dict:
    """Rehace el entregable corrigiendo lo que el validador marcó."""
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_CORRECTOR),
        ("human", "Entrega el entregable corregido."),
    ]) | llm_rapido(temperatura=0.2).with_structured_output(SintesisDebate)

    inputs = {
        "marco": marco_para("corrector"),
        "enfoque": state.get("enfoque", ""),
        "problemas": _formatear_problemas(state.get("problemas")),
        "consulta": state.get("consulta", ""),
        "contexto_tesis": state.get("contexto_tesis", ""),
        "contexto_libros": state.get("contexto_libros", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "texto_sintetizado": state.get("texto_sintetizado") or "(vacío)",
        "recomendaciones": state.get("recomendaciones") or "(vacío)",
    }
    intentos = state.get("intentos", 0) + 1
    try:
        out = _invocar(chain, inputs)
        texto = (out.texto_mejorado or "").strip()
        recs = (out.recomendaciones or "").strip()
    except Exception as exc:
        logger.warning(f"[mini_grafo/corrector] Falló: {exc}")
        return {"intentos": intentos}

    logger.info(f"[mini_grafo/corrector] Corrección {intentos}/{_MAX_CORRECCIONES} aplicada.")
    return {
        "texto_sintetizado": texto or state.get("texto_sintetizado", ""),
        "recomendaciones": recs or state.get("recomendaciones", ""),
        "intentos": intentos,
    }


def _nodo_estructurador(state: EstadoDebate) -> dict:
    """Entrega la respuesta de chat, adaptada al modo que decidió el triaje."""
    from .conversador import _historial_a_mensajes

    modo = state.get("modo", "duda")

    # ATAJO: la elicitación y la ideación YA vienen maquetadas desde su esquema
    # (preguntas con sus opciones, molde, campos de cada idea). Pasarlas por otro LLM
    # solo las degrada —descartaba el molde y desordenaba las listas de opciones,
    # dejándolas como si fueran preguntas nuevas— y cuesta una llamada de más.
    # Se entregan tal cual. Si hubo corrección, el texto ya no es el renderizado
    # original, así que en ese caso sí pasa por el redactor.
    if modo in ("elicitacion", "ideacion") and not state.get("intentos"):
        directo = (state.get("recomendaciones") or "").strip()
        if directo:
            logger.info(f"[mini_grafo/estructurador] Entrega directa ({modo}): sin reescritura.")
            return {"respuesta_final": _blindar_avisos(directo, state)}

    # Los problemas que el validador no logró cerrar se le trasladan al estudiante
    # como advertencias honestas, en vez de ocultarlos.
    recomendaciones = state.get("recomendaciones") or ""

    # Advertencias: criterios de rúbrica que NO son reglas escritas (p. ej. el año en el
    # título). No bloquean el entregable; se le explican al estudiante para que decida.
    suaves = state.get("advertencias") or []
    if suaves:
        recomendaciones += (
            "\n\nPARA QUE EL ESTUDIANTE DECIDA (no son errores, son criterios opcionales: "
            "preséntaselos como sugerencia razonada, NUNCA como algo que hizo mal):\n"
            + _formatear_problemas(suaves)
        )

    abiertos = state.get("problemas") or []
    if abiertos and state.get("intentos", 0) >= _MAX_CORRECCIONES:
        recomendaciones += (
            "\n\nPUNTOS QUE NO SE PUDIERON RESOLVER SIN INFORMACIÓN DEL ESTUDIANTE "
            "(dilos con transparencia, sin mencionar el mecanismo interno):\n"
            + _formatear_problemas(abiertos)
        )

    sistema = _PROMPT_ESTRUCTURADOR.format(
        modo=modo,
        texto_sintetizado=state.get("texto_sintetizado") or "(no se redactó texto de tesis en este turno)",
        recomendaciones=recomendaciones or "(sin recomendaciones)",
        criterios_rubrica=state.get("criterios_rubrica", ""),
        historial_panel=_formatear_memoria(state.get("debate_memory") or []),
        aviso_no_aplica=state.get("aviso_no_aplica", ""),
    )
    mensajes = [SystemMessage(content=sistema)]
    mensajes.extend(_historial_a_mensajes(state.get("historial") or []))
    mensajes.append(HumanMessage(content=state.get("consulta", "")))

    try:
        respuesta = llm_rapido(temperatura=0.3).invoke(mensajes).content.strip()
    except Exception as exc:
        logger.error(f"[mini_grafo/estructurador] Falló: {exc}")
        # Degradación: entrega lo que haya preparado el panel.
        respuesta = state.get("texto_sintetizado") or recomendaciones or _FALLBACK

    return {"respuesta_final": _blindar_avisos(respuesta, state)}


def _blindar_avisos(respuesta: str, state: EstadoDebate) -> str:
    """Anexa los avisos críticos que el redactor final haya podido descartar.

    El redactor final es un LLM y descarta con frecuencia el tramo final de sus
    instrucciones. Dos avisos son demasiado caros para dejarlos a su criterio: el
    resguardo ético (decide si el proyecto es viable) y la existencia de una tesis
    casi idéntica en el propio programa. Si no aparecen en la respuesta, se añaden
    aquí de forma determinista.
    """
    extras: list[str] = []

    if state.get("aviso_etico") and not re.search(
        r"[ée]tic|consentimiento|comit[ée]|anonimiza", respuesta, re.I
    ):
        extras.append(
            "⚠️ **Antes de seguir, un tema que decide si tu proyecto es viable.** Trabajarás con "
            "datos de personas, así que el Art. 71 del Reglamento de Investigación UPAO te exige "
            "aprobación (o exoneración) de un **Comité de Ética** y **consentimiento informado**, "
            "más la **autorización formal y por escrito** de la organización que custodia esos datos. "
            "Ese trámite toma tiempo y debe entrar en tu cronograma (sección 5.1). "
            "¿Ya tienes ese acceso comprometido, o todavía hay que gestionarlo?"
        )

    similares = state.get("tesis_similares_lista") or []
    if similares and not re.search(r"ya\s+exist|tesis\s+similar|repositorio|diferenci", respuesta, re.I):
        filas = "\n".join(f"- ({t.get('anio')}) {t.get('titulo')}" for t in similares[:3])
        extras.append(
            "📚 **Ojo con la duplicidad.** En el Repositorio Institucional UPAO ya hay tesis muy "
            f"parecidas a lo que planteas, del mismo programa:\n{filas}\n"
            "No es para desanimarte: es para que **diferencies** tu propuesta (otra población, otra "
            "organización, otra técnica, otra variable dependiente, o una comparación que ellas no "
            "hicieron). Un proyecto casi idéntico a uno ya sustentado es una observación segura del jurado."
        )

    if not extras:
        return respuesta
    logger.info(f"[mini_grafo/estructurador] Blindaje: se añadieron {len(extras)} aviso(s) críticos.")
    return respuesta.rstrip() + "\n\n---\n\n" + "\n\n".join(extras)


# ── Construcción del grafo (una sola vez) ────────────────────────────────────

def _construir_grafo():
    g = StateGraph(EstadoDebate)
    g.add_node("recuperacion", _nodo_recuperacion)
    g.add_node("triaje", _nodo_triaje)
    g.add_node("elicitador", _nodo_elicitador)
    g.add_node("memoria", _nodo_memoria)
    g.add_node("ideador", _nodo_ideador)
    g.add_node("asesor", _nodo_asesor)
    g.add_node("redactor_metodologico", _nodo_redactor_metodologico)
    g.add_node("redactor_dominio", _nodo_redactor_dominio)
    g.add_node("integrador", _nodo_integrador)
    g.add_node("validador", _nodo_validador)
    g.add_node("corrector", _nodo_corrector)
    g.add_node("estructurador", _nodo_estructurador)

    g.set_entry_point("recuperacion")
    g.add_edge("recuperacion", "triaje")

    # Enrutamiento por lo que el estudiante realmente necesita.
    g.add_conditional_edges("triaje", _ruta_triaje, {
        "elicitador": "elicitador",
        "memoria": "memoria",
        "ideador": "ideador",
        "asesor": "asesor",
        "redactor_metodologico": "redactor_metodologico",
    })

    # La elicitación no produce texto de tesis: no necesita auditoría de rúbrica.
    g.add_edge("elicitador", "estructurador")

    # La respuesta de memoria es la ficha literal del estudiante: no pasa por ningún
    # LLM, así que tampoco por el validador. Va directa a la salida.
    g.add_edge("memoria", END)

    # La ideación SÍ se audita: propone títulos y no debe inventar datasets ni citas.
    g.add_edge("ideador", "validador")

    # El asesor sí pasa por el validador (una explicación también puede alucinar citas).
    g.add_edge("asesor", "validador")

    # Debate de redacción → entregable.
    g.add_edge("redactor_metodologico", "redactor_dominio")
    g.add_edge("redactor_dominio", "integrador")
    g.add_edge("integrador", "validador")

    # Ciclo de control de calidad, acotado por `intentos`.
    g.add_conditional_edges("validador", _ruta_validador, {
        "corrector": "corrector",
        "estructurador": "estructurador",
    })
    g.add_edge("corrector", "validador")

    g.add_edge("estructurador", END)
    return g.compile()


_GRAFO = _construir_grafo()


def responder_mejora_rapida(
    mensaje: str,
    historial: list[dict],
    doc,
    biblioteca,
    ficha: dict | None = None,
) -> dict:
    """Punto de entrada: corre el mini-grafo multiagente.

    `ficha` es la memoria estructurada de la asesoría (ver `api/ficha.py`): lo que
    el estudiante ya declaró, venga o no de un PDF. Es lo que impide que el panel
    vuelva a preguntar lo que ya respondió.

    Devuelve `{"respuesta", "seccion", "texto_mejorado", "modo"}`. `seccion` y
    `texto_mejorado` permiten al API guardar la redacción como pendiente (para
    evaluarla luego con la red grande); vienen vacíos cuando el turno fue de
    elicitación o de consulta, porque ahí no se produjo texto de tesis.
    """
    from .ficha import elicitaciones_seguidas

    estado_inicial: EstadoDebate = {
        "consulta": mensaje,
        "historial": historial or [],
        "doc": doc,
        "biblioteca": biblioteca,
        "ficha": ficha or {},
        # Racha de tandas de preguntas seguidas, leída del propio historial: si ya
        # van dos, el triaje deja de preguntar y redacta con asunciones explícitas.
        "elicitaciones_previas": elicitaciones_seguidas(historial),
    }
    try:
        final = _GRAFO.invoke(estado_inicial)
    except Exception as exc:
        logger.error(f"[mini_grafo] Error ejecutando el grafo: {exc}")
        return {"respuesta": _FALLBACK, "seccion": None, "texto_mejorado": "", "modo": "duda"}

    return {
        "respuesta": (final.get("respuesta_final") or "").strip() or _FALLBACK,
        "seccion": (final.get("seccion") or "") or None,
        "texto_mejorado": (final.get("texto_sintetizado") or "").strip(),
        "modo": final.get("modo") or "duda",
    }
