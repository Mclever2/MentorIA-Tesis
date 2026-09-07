"""
Panel de TÍTULO — tres agentes con roles opuestos, no un LLM disfrazado de tres.

Motivo: un solo modelo que propone y se autoevalúa tiende a validar lo que acaba
de escribir, y ahí es donde se colaban los títulos sin delimitar, o con una empresa
y un año inventados para «cumplir la rúbrica». Aquí cada rol tiene un incentivo
distinto y trabaja sobre evidencia que el anterior no controla:

  1. PROPONENTE  — escribe 3 candidatos. Ve el proyecto (RAG), la política de
     delimitación de ESTE estudio y títulos REALES del repositorio UPAO.
  2. ATERRIZADOR — no propone nada: verifica. Cada dato del título (institución,
     periodo, variables, artefacto) tiene que estar en el proyecto. Lo que no
     esté, lo marca como INVENTADO. Es el que aterriza al proponente.
  3. AUDITOR     — cierra. Recibe el conteo de palabras y el diagnóstico de
     delimitación MEDIDOS (no estimados por un LLM) y falla contra los ítems 1, 2
     y 3 de la ficha. Puede devolver el trabajo al proponente una vez.

Entre agente y agente corre un chequeo determinista (`backend.titulo`): las
palabras se cuentan, no se opinan. Así el auditor no puede equivocarse en lo
verificable y se concentra en lo que sí requiere criterio.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from backend.citas import bloque_regla_citas
from backend.titulo import (
    MAX_PALABRAS_UPAO,
    datos_no_respaldados,
    diagnosticar_titulo,
    limpiar_titulo,
    politica_delimitacion,
)

from .llm import llm_rapido

logger = logging.getLogger(__name__)

MAX_RONDAS = 2
SECCION_TITULO = "1. Título del proyecto"

_FALLBACK = (
    "Disculpa, no pude completar el análisis de tu título. Vuelve a pedírmelo en unos segundos."
)


# ── Contratos de salida de cada agente ──────────────────────────────────────

class Candidato(BaseModel):
    titulo: str = Field(description="El título propuesto, en una sola línea, sin la etiqueta «Título:».")
    variables: str = Field(description="Qué variables/artefacto y qué dimensión de mejora se leen en él.")
    espacio: str = Field(default="", description="Qué delimitación espacial lleva, o por qué no lleva.")
    tiempo: str = Field(default="", description="Qué delimitación temporal lleva, o por qué no lleva.")
    razon: str = Field(default="", description="Por qué este título encaja con el proyecto. Una o dos frases.")


class PropuestaTitulos(BaseModel):
    candidatos: list[Candidato] = Field(description="Exactamente 3 candidatos, del más recomendable al menos.")
    faltantes: str = Field(
        default="",
        description=(
            "Datos que el proyecto NO da y harían falta para delimitar bien "
            "(institución, periodo, tamaño de muestra). Vacío si no falta nada."
        ),
    )


class HallazgoAnclaje(BaseModel):
    titulo: str = Field(description="El candidato revisado, tal cual.")
    inventado: str = Field(
        default="",
        description=(
            "Dato del título que NO aparece en el proyecto (empresa, año, población, "
            "técnica). Vacío si todo está respaldado."
        ),
    )
    promesa_incumplida: str = Field(
        default="",
        description="Lo que el título promete y los objetivos/metodología NO hacen. Vacío si no hay.",
    )
    veredicto: str = Field(description="«anclado», «con reparos» o «no anclado».")


class VerificacionAnclaje(BaseModel):
    hallazgos: list[HallazgoAnclaje]
    evidencia: str = Field(
        default="",
        description="Fragmentos del proyecto en que te apoyas (parafraseados y breves).",
    )


class DictamenTitulo(BaseModel):
    veredicto: str = Field(description="«aprobado» si hay un título entregable; «observado» si ninguno sirve todavía.")
    titulo_final: str = Field(default="", description="El título que se entrega al estudiante. Vacío si observado.")
    alternativas: list[str] = Field(default_factory=list, description="Hasta 2 títulos alternativos válidos.")
    justificacion: str = Field(description="Por qué gana ese título, ítem por ítem (1, 2 y 3 de la ficha).")
    observaciones: str = Field(
        default="",
        description=(
            "Si es «observado»: qué debe corregir el proponente. Si es «aprobado»: "
            "qué debe confirmar el estudiante (p. ej. el nombre exacto de la institución)."
        ),
    )


# ── Estado del panel ────────────────────────────────────────────────────────

class EstadoTitulo(TypedDict, total=False):
    consulta: str
    historial: list
    doc: Any
    biblioteca: Any
    # contexto
    proyecto: str
    titulo_actual: str
    tema: str
    programa: str
    politica: str
    evidencia_corpus: str
    criterios_rubrica: str
    enfoque: str
    regla_citas: str
    # ciclo
    ronda: int
    observaciones_auditor: str
    candidatos: list[dict]
    medidas: str
    anclaje: str
    # salida
    dictamen: dict
    respuesta_final: str


# ── Prompts ─────────────────────────────────────────────────────────────────

_PROMPT_PROPONENTE = """\
Eres el PROPONENTE de títulos del panel metodológico. Escribes 3 candidatos de título para el \
proyecto de ESTE estudiante. No evalúas: propones.

{enfoque}

{politica}

{regla_citas}

CRITERIOS DE LA RÚBRICA PARA EL TÍTULO:
{criterios_rubrica}

PROYECTO DEL ESTUDIANTE (esto es lo único real; todo lo que pongas en el título debe salir de aquí):
{proyecto}

TÍTULO ACTUAL (puede estar vacío si aún no tiene):
{titulo_actual}

EVIDENCIA DEL REPOSITORIO UPAO — títulos reales ya aprobados y cómo delimitan:
{evidencia_corpus}

OBSERVACIONES DEL AUDITOR DE LA RONDA ANTERIOR (si las hay, corrígelas TODAS):
{observaciones_auditor}

CÓMO TRABAJAS:
- Los 3 candidatos deben ser DISTINTOS entre sí en enfoque, no tres redacciones del mismo.
- Respeta la política de delimitación de arriba al pie de la letra: lo EXIGIDO va; lo OPCIONAL \
solo si el proyecto lo respalda; lo que NO aplica no se inventa.
- Si falta un dato que la política exige (no se sabe la empresa, el periodo), escribe un marcador \
explícito entre corchetes — «[institución]», «[periodo]» — y anótalo en `faltantes`. NUNCA rellenes \
con un nombre o un año plausible: eso es una falsedad que el jurado detecta.
- Usa los títulos reales del repositorio como PATRÓN de forma (cómo nombran el lugar, cómo colocan \
el año), NO como contenido a copiar.
- Máximo {max_palabras} palabras por título. Cuéntalas una por una antes de entregar.
- Nada de dos puntos decorativos ni subtítulos largos: una sola línea legible."""

_PROMPT_ATERRIZADOR = """\
Eres el VERIFICADOR DE ANCLAJE del panel. NO propones títulos y NO reescribes: tu único trabajo es \
comprobar que cada candidato está respaldado por el proyecto real del estudiante.

{enfoque}

PROYECTO DEL ESTUDIANTE (la única fuente de verdad):
{proyecto}

POLÍTICA DE DELIMITACIÓN QUE APLICA A ESTE ESTUDIO:
{politica}

CANDIDATOS DEL PROPONENTE:
{candidatos}

MEDICIONES DETERMINISTAS DE CADA CANDIDATO (conteo real, no lo recalcules):
{medidas}

QUÉ BUSCAS, EN ESTE ORDEN:
1. DATOS INVENTADOS: toda institución, ciudad, año, población, técnica o herramienta del título \
tiene que aparecer en el proyecto. Si el proyecto no la menciona, es INVENTADA — dilo aunque suene \
razonable. Un marcador explícito como «[institución]» NO es un invento: es una laguna bien señalada, \
y así debes tratarlo.
2. PROMESA INCUMPLIDA: si el título anuncia algo que los objetivos o la metodología no hacen \
(«evaluación del impacto» cuando el estudio solo describe; «sistema» cuando solo hay un modelo), \
márcalo.
3. DELIMITACIÓN SOBRANTE: si el título mete un año o un lugar que la política marca como OPCIONAL o \
NO APLICA y el proyecto no lo respalda, es ruido que resta precisión — márcalo igual que un invento.

Sé literal y verificable. Cita en `evidencia` los fragmentos del proyecto en que te apoyas. Si un \
candidato está limpio, dilo: tu trabajo no es encontrar fallos a la fuerza."""

_PROMPT_AUDITOR = """\
Eres el AUDITOR del panel. Cierras el caso: eliges el título que se entrega o devuelves el trabajo.

{enfoque}

CRITERIOS DE LA RÚBRICA (ítems 1, 2 y 3):
{criterios_rubrica}

POLÍTICA DE DELIMITACIÓN DE ESTE ESTUDIO:
{politica}

CANDIDATOS:
{candidatos}

MEDICIONES DETERMINISTAS (verificadas fuera del modelo — NO las discutas ni las recalcules):
{medidas}

INFORME DEL VERIFICADOR DE ANCLAJE:
{anclaje}

RONDA {ronda} de {max_rondas}.

CÓMO FALLAS:
- Un candidato con un dato INVENTADO queda descartado. Sin excepción: es el error más caro ante un jurado.
- Un candidato que excede las {max_palabras} palabras queda descartado (el conteo te lo dan medido).
- Un candidato al que le falta una delimitación EXIGIDA queda descartado; si le falta una \
RECOMENDADA, se puede aprobar señalándolo en `observaciones`.
- Un candidato con un marcador «[institución]» / «[periodo]» SÍ puede aprobarse: se entrega con el \
marcador y se le pide al estudiante que lo complete. Es preferible a inventar el dato.
- Entre los que sobreviven, gana el que mejor articula variables + delimitación en menos palabras.
- Si NINGUNO sobrevive y quedan rondas, veredicto «observado» y escribe en `observaciones` \
instrucciones CONCRETAS para el proponente (qué quitar, qué añadir, con qué dato del proyecto).
- Si es la última ronda, elige el menos malo, apruébalo y deja escrito con claridad qué le falta.
- En `justificacion` argumenta ítem por ítem (1: claridad y fidelidad; 2: variables/espacio/tiempo; \
3: línea de investigación). Sin relleno."""

_PROMPT_ENTREGA = """\
Eres MentorIA, mentor metodológico. Un análisis interno ya resolvió el título del estudiante; tú \
entregas la respuesta de chat, en español y markdown.

Estructura la respuesta así:
1. **Tu título propuesto** — el título final, en negrita, en su propia línea.
2. **Por qué este** — 3 o 4 viñetas cortas: qué variables/artefacto se leen, qué delimita y qué no, \
y por qué eso es lo correcto PARA SU TIPO de estudio. Si alguna delimitación no aplica, explícalo \
en una línea para que pueda defenderlo ante el jurado.
3. **Alternativas** — si las hay, en lista.
4. **Lo que debes completar** — si el título lleva un marcador «[institución]» o «[periodo]», pídeselo \
de forma directa. Si el análisis detectó datos que faltan, enuméralos aquí.

REGLAS:
- NO menciones el mecanismo interno: nada de «agentes», «panel», «auditor», «rondas».
- NO inventes datos que no estén en el análisis.
- Si el análisis dice que un dato falta, PÍDESELO; no lo rellenes tú.
- Sé breve: el estudiante quiere el título, no un ensayo.

MATERIAL DEL ANÁLISIS INTERNO:
- TÍTULO FINAL: {titulo_final}
- ALTERNATIVAS: {alternativas}
- JUSTIFICACIÓN: {justificacion}
- OBSERVACIONES / DATOS QUE FALTAN: {observaciones}
- DELIMITACIÓN QUE APLICA A ESTE ESTUDIO: {politica}
- EVIDENCIA DEL REPOSITORIO UPAO (puedes citarla como referencia de cómo titulan en su escuela):
{evidencia_corpus}
"""


# ── Utilidades ──────────────────────────────────────────────────────────────

def _formatear_candidatos(candidatos: list[dict]) -> str:
    if not candidatos:
        return "(el proponente no entregó candidatos)"
    partes = []
    for i, c in enumerate(candidatos, 1):
        partes.append(
            f"{i}. «{c.get('titulo', '')}»\n"
            f"   - Variables/artefacto: {c.get('variables', '—')}\n"
            f"   - Espacio: {c.get('espacio') or '—'}\n"
            f"   - Tiempo: {c.get('tiempo') or '—'}\n"
            f"   - Razón: {c.get('razon') or '—'}"
        )
    return "\n".join(partes)


def _medir_candidatos(candidatos: list[dict], proyecto: str = "") -> str:
    """Chequeo determinista de cada candidato.

    Impide que el auditor se equivoque contando palabras o «vea» un año que no está,
    y — lo más importante — señala por presencia literal los datos que el título
    afirma y el proyecto nunca dijo. Ese es el fallo caro: para cumplir la
    delimitación, el proponente añade una ciudad o un año verosímiles pero falsos.
    """
    if not candidatos:
        return "(sin candidatos que medir)"
    lineas = []
    for i, c in enumerate(candidatos, 1):
        titulo = c.get("titulo", "")
        d = diagnosticar_titulo(titulo)
        estado = "EXCEDE EL LÍMITE" if d.excede_limite else "dentro del límite"
        linea = f"{i}. «{d.titulo}» → {d.n_palabras} palabras ({estado}); {d.resumen()}"
        sospechosos = datos_no_respaldados(titulo, proyecto) if proyecto else []
        if sospechosos:
            linea += (
                "\n   ⚠ SIN RESPALDO EN EL PROYECTO: " + "; ".join(sospechosos)
                + ". Trátalo como dato inventado salvo que el proyecto lo diga con otras palabras."
            )
        lineas.append(linea)
    return "\n".join(lineas)


def _invocar(chain, inputs):
    from backend.graph.nodes._utils import invocar_con_backoff
    salida = invocar_con_backoff(chain, inputs)
    if hasattr(salida, "content"):
        return salida.content.strip()
    return salida


# ── Nodos ───────────────────────────────────────────────────────────────────

def _enfoque_con_alcance(enfoque: str, doc) -> str:
    """Añade al bloque de enfoque el alcance declarado por el estudiante."""
    if doc is None:
        return enfoque
    try:
        from backend.alcance import bloque_prompt
        bloque = bloque_prompt(doc)
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[titulo_panel] No se pudo aplicar el alcance: {exc}")
        return enfoque
    return "\n\n".join(p for p in (enfoque, bloque) if p)


def _nodo_contexto(state: EstadoTitulo) -> dict:
    """Reúne todo lo que el panel necesita: proyecto, política, evidencia del repositorio."""
    from backend.enfoque import bloque_enfoque
    from backend.rag import limpiar_marcas_rag
    from .rubrica_chat import criterios_relevantes

    doc = state.get("doc")
    consulta = state.get("consulta", "")

    proyecto = ""
    titulo_actual = ""
    if doc is not None and getattr(doc, "vector_store", None) is not None:
        from backend.rag import recuperar_contexto
        # Un título solo se puede juzgar contra el NÚCLEO completo: prometer algo que
        # los objetivos no hacen es el error más común, y no se ve mirando el título solo.
        for consulta_rag in (
            "título del proyecto",
            "problema central formulación del problema realidad problemática",
            "objetivo general objetivos específicos",
            "variables independiente dependiente dimensiones indicadores",
            "tipo de investigación diseño método población muestra",
        ):
            try:
                trozo = limpiar_marcas_rag(recuperar_contexto(doc.vector_store, consulta_rag))
            except Exception as exc:                      # noqa: BLE001
                logger.warning(f"[titulo_panel] RAG falló en «{consulta_rag}»: {exc}")
                continue
            if trozo.strip():
                proyecto += f"\n\n### {consulta_rag}\n{trozo[:2000]}"
                if consulta_rag == "título del proyecto" and not titulo_actual:
                    titulo_actual = limpiar_titulo(trozo)
        proyecto = proyecto.strip()

    tipo, diseno = "cuantitativa", ""
    if doc is not None:
        try:
            from .tipo_investigacion import obtener_tipo_diseno
            tipo, diseno = obtener_tipo_diseno(doc)
        except Exception as exc:                          # noqa: BLE001
            logger.warning(f"[titulo_panel] No se pudo detectar el tipo: {exc}")

    pol = politica_delimitacion(tipo, diseno, proyecto)
    politica = (
        "## QUÉ DEBE DELIMITAR ESTE PROYECTO (no es igual para todos)\n"
        f"{pol.bloque()}\n"
        "Lo marcado OPCIONAL o NO APLICA no se inventa para «cumplir la rúbrica»: un lugar o un año "
        "falsos son peor error que su ausencia."
    )

    # Evidencia del repositorio: títulos reales de la misma escuela y tema.
    evidencia = ""
    programa = getattr(doc, "programa", "") or "" if doc is not None else ""
    try:
        from backend.rag.titulos_store import contexto_titulos
        from .deps import get_embeddings
        tema = (consulta + " " + (titulo_actual or "") + " " + proyecto[:600]).strip()
        evidencia = contexto_titulos(
            get_embeddings(), tema=tema, programa=programa or None, k=8
        )
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"[titulo_panel] Sin evidencia del repositorio: {exc}")

    criterios, _sec = criterios_relevantes(doc, "título del proyecto variables espacio tiempo")

    logger.info(
        f"[titulo_panel] Contexto listo | tipo={tipo} | proyecto={len(proyecto)} chars | "
        f"evidencia={'sí' if evidencia else 'no'} | título actual={'sí' if titulo_actual else 'no'}"
    )
    return {
        "proyecto":          proyecto or "(no se recuperó texto del proyecto)",
        "titulo_actual":     titulo_actual or "(el estudiante aún no tiene título)",
        "programa":          programa,
        "politica":          politica,
        "evidencia_corpus":  evidencia or "(el corpus del repositorio no está disponible en este momento)",
        "criterios_rubrica": criterios or "(sin rúbrica cargada; aplica los ítems 1, 2 y 3 estándar)",
        # Enfoque + alcance declarado: el panel del título tampoco debe exigirle
        # coherencia con capítulos que el estudiante aún no ha escrito.
        "enfoque":           _enfoque_con_alcance(bloque_enfoque(tipo, diseno), doc),
        "regla_citas":       bloque_regla_citas(),
        "ronda":             1,
        "observaciones_auditor": "(primera ronda: aún no hay observaciones)",
    }


def _nodo_proponente(state: EstadoTitulo) -> dict:
    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_PROPONENTE),
        ("human", "Entrega tus 3 candidatos de título."),
    ]) | llm_rapido(temperatura=0.6).with_structured_output(PropuestaTitulos)

    inputs = {
        "enfoque":               state.get("enfoque", ""),
        "politica":              state.get("politica", ""),
        "regla_citas":           state.get("regla_citas", ""),
        "criterios_rubrica":     state.get("criterios_rubrica", ""),
        "proyecto":              state.get("proyecto", ""),
        "titulo_actual":         state.get("titulo_actual", ""),
        "evidencia_corpus":      state.get("evidencia_corpus", ""),
        "observaciones_auditor": state.get("observaciones_auditor", ""),
        "max_palabras":          MAX_PALABRAS_UPAO,
    }
    try:
        out: PropuestaTitulos = _invocar(chain, inputs)
        candidatos = [c.model_dump() for c in out.candidatos][:3]
        for c in candidatos:
            c["titulo"] = limpiar_titulo(c.get("titulo", ""))
        faltantes = (out.faltantes or "").strip()
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"[titulo_panel/proponente] Falló: {exc}")
        candidatos, faltantes = [], ""

    logger.info(f"[titulo_panel] Proponente: {len(candidatos)} candidatos (ronda {state.get('ronda', 1)})")
    return {
        "candidatos": candidatos,
        "medidas": _medir_candidatos(candidatos, state.get("proyecto", "")),
        "faltantes_proponente": faltantes,
    }


def _nodo_aterrizador(state: EstadoTitulo) -> dict:
    if not state.get("candidatos"):
        return {"anclaje": "(sin candidatos que verificar)"}

    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_ATERRIZADOR),
        ("human", "Verifica el anclaje de cada candidato contra el proyecto."),
    ]) | llm_rapido(temperatura=0.0).with_structured_output(VerificacionAnclaje)

    inputs = {
        "enfoque":     state.get("enfoque", ""),
        "proyecto":    state.get("proyecto", ""),
        "politica":    state.get("politica", ""),
        "candidatos":  _formatear_candidatos(state.get("candidatos") or []),
        "medidas":     state.get("medidas", ""),
    }
    try:
        out: VerificacionAnclaje = _invocar(chain, inputs)
        lineas = []
        for h in out.hallazgos:
            lineas.append(
                f"- «{h.titulo}» → {h.veredicto.upper()}"
                + (f" | INVENTADO: {h.inventado}" if h.inventado else "")
                + (f" | PROMESA INCUMPLIDA: {h.promesa_incumplida}" if h.promesa_incumplida else "")
            )
        anclaje = "\n".join(lineas)
        if out.evidencia:
            anclaje += f"\n\nEvidencia citada del proyecto:\n{out.evidencia}"
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"[titulo_panel/aterrizador] Falló: {exc}")
        anclaje = "(el verificador de anclaje no pudo intervenir en esta ronda)"

    logger.info("[titulo_panel] Aterrizador emitió su informe")
    return {"anclaje": anclaje}


def _nodo_auditor(state: EstadoTitulo) -> dict:
    ronda = int(state.get("ronda") or 1)

    if not state.get("candidatos"):
        return {
            "dictamen": {
                "veredicto": "observado",
                "titulo_final": "",
                "alternativas": [],
                "justificacion": "",
                "observaciones": "No se pudieron generar candidatos de título.",
            },
            "ronda": ronda + 1,
        }

    chain = ChatPromptTemplate.from_messages([
        ("system", _PROMPT_AUDITOR),
        ("human", "Emite tu dictamen."),
    ]) | llm_rapido(temperatura=0.0).with_structured_output(DictamenTitulo)

    inputs = {
        "enfoque":           state.get("enfoque", ""),
        "criterios_rubrica": state.get("criterios_rubrica", ""),
        "politica":          state.get("politica", ""),
        "candidatos":        _formatear_candidatos(state.get("candidatos") or []),
        "medidas":           state.get("medidas", ""),
        "anclaje":           state.get("anclaje", ""),
        "ronda":             ronda,
        "max_rondas":        MAX_RONDAS,
        "max_palabras":      MAX_PALABRAS_UPAO,
    }
    try:
        out: DictamenTitulo = _invocar(chain, inputs)
        dictamen = out.model_dump()
        dictamen["titulo_final"] = limpiar_titulo(dictamen.get("titulo_final", ""))
    except Exception as exc:                              # noqa: BLE001
        logger.warning(f"[titulo_panel/auditor] Falló: {exc}")
        primero = (state.get("candidatos") or [{}])[0]
        dictamen = {
            "veredicto": "aprobado",
            "titulo_final": primero.get("titulo", ""),
            "alternativas": [c.get("titulo", "") for c in (state.get("candidatos") or [])[1:3]],
            "justificacion": "",
            "observaciones": "",
        }

    candidatos = state.get("candidatos") or []
    ultima_ronda = ronda >= MAX_RONDAS

    # En la última ronda hay que entregar algo. El auditor tiende a quedarse en
    # «observado» cuando los candidatos llevan marcadores «[institución]», aunque el
    # prompt diga que son aprobables; sin esto el estudiante se queda sin título y
    # con la explicación colgando. Se elige el mejor candidato de forma determinista
    # y se conservan las observaciones para que sepa qué completar.
    proyecto = state.get("proyecto", "")
    if ultima_ronda and dictamen.get("veredicto") != "aprobado" and not dictamen.get("titulo_final"):
        validos = [c for c in candidatos if c.get("titulo")]
        dentro = [c for c in validos if not diagnosticar_titulo(c["titulo"]).excede_limite]
        # Se prefiere el que no afirma nada que el proyecto no diga: entregar un título
        # con una ciudad inventada es peor que entregar uno más pobre pero defendible.
        limpios = [c for c in dentro if not datos_no_respaldados(c["titulo"], proyecto)]
        elegido = (limpios or dentro or validos or [{}])[0]
        if elegido.get("titulo"):
            dictamen["veredicto"] = "aprobado"
            dictamen["titulo_final"] = elegido["titulo"]
            dictamen["observaciones"] = (
                "Este título aún necesita ajustes: " + (dictamen.get("observaciones") or "")
            ).strip()
            logger.info("[titulo_panel] Última ronda sin veredicto: se entrega el mejor candidato")

    # Alternativas: si el auditor no las dejó, se completan con los otros candidatos.
    # Se descartan las que afirman datos ausentes del proyecto: ofrecerlas como
    # opción sería volver a poner sobre la mesa el título inventado que acabamos de descartar.
    if not dictamen.get("alternativas"):
        dictamen["alternativas"] = [
            c["titulo"] for c in candidatos
            if c.get("titulo")
            and c["titulo"] != dictamen.get("titulo_final")
            and not datos_no_respaldados(c["titulo"], proyecto)
        ][:2]
    else:
        dictamen["alternativas"] = [
            a for a in dictamen["alternativas"] if not datos_no_respaldados(a, proyecto)
        ][:2]

    # Red de seguridad determinista: el auditor no puede aprobar un título que
    # excede el límite duro, por más bien que lo argumente.
    final = dictamen.get("titulo_final") or ""
    if final:
        d = diagnosticar_titulo(final)
        if d.excede_limite and ronda < MAX_RONDAS:
            logger.info(f"[titulo_panel] Título aprobado con {d.n_palabras} palabras → se devuelve al proponente")
            dictamen["veredicto"] = "observado"
            dictamen["observaciones"] = (
                f"El título elegido tiene {d.n_palabras} palabras y el máximo es {MAX_PALABRAS_UPAO}. "
                "Recórtalo conservando variables y delimitación. "
            ) + (dictamen.get("observaciones") or "")
        elif d.excede_limite:
            dictamen["observaciones"] = (
                f"⚠️ El título tiene {d.n_palabras} palabras y UPAO exige un máximo de "
                f"{MAX_PALABRAS_UPAO}: hay que recortarlo. "
            ) + (dictamen.get("observaciones") or "")

    # Si el título entregado afirma algo que el proyecto no dice, se avisa siempre:
    # el estudiante tiene que confirmarlo o cambiarlo antes de presentarlo.
    if final:
        sin_respaldo = datos_no_respaldados(final, proyecto)
        if sin_respaldo:
            dictamen["observaciones"] = (
                "⚠️ Confirma estos datos antes de usar el título — no aparecen en tu proyecto: "
                + "; ".join(sin_respaldo)
                + ". Si no corresponden, reemplázalos por los reales o quítalos.\n"
            ) + (dictamen.get("observaciones") or "")
            logger.info(f"[titulo_panel] Título final con {len(sin_respaldo)} dato(s) sin respaldo")

    faltantes = (state.get("faltantes_proponente") or "").strip()
    if faltantes:
        dictamen["observaciones"] = (dictamen.get("observaciones") or "") + f"\nDatos que faltan en el proyecto: {faltantes}"

    logger.info(f"[titulo_panel] Auditor: {dictamen.get('veredicto')} (ronda {ronda})")
    return {
        "dictamen": dictamen,
        "ronda": ronda + 1,
        "observaciones_auditor": dictamen.get("observaciones") or "(el auditor no dejó observaciones)",
    }


def _ruta_tras_auditor(state: EstadoTitulo) -> str:
    dictamen = state.get("dictamen") or {}
    if dictamen.get("veredicto") == "observado" and int(state.get("ronda") or 1) <= MAX_RONDAS:
        return "proponente"
    return "entrega"


def _nodo_entrega(state: EstadoTitulo) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    from .conversador import _historial_a_mensajes

    dictamen = state.get("dictamen") or {}
    alternativas = dictamen.get("alternativas") or []

    sistema = _PROMPT_ENTREGA.format(
        titulo_final=dictamen.get("titulo_final") or "(no se logró un título entregable)",
        alternativas="; ".join(a for a in alternativas if a) or "(ninguna)",
        justificacion=dictamen.get("justificacion") or "(sin justificación)",
        observaciones=dictamen.get("observaciones") or "(sin observaciones)",
        politica=state.get("politica", ""),
        evidencia_corpus=state.get("evidencia_corpus", ""),
    )
    mensajes = [SystemMessage(content=sistema)]
    mensajes.extend(_historial_a_mensajes(state.get("historial") or []))
    mensajes.append(HumanMessage(content=state.get("consulta", "")))

    try:
        respuesta = llm_rapido(temperatura=0.3).invoke(mensajes).content.strip()
    except Exception as exc:                              # noqa: BLE001
        logger.error(f"[titulo_panel/entrega] Falló: {exc}")
        titulo = dictamen.get("titulo_final") or ""
        respuesta = f"**{titulo}**\n\n{dictamen.get('justificacion') or ''}" if titulo else _FALLBACK

    return {"respuesta_final": respuesta}


# ── Grafo ───────────────────────────────────────────────────────────────────

def _construir_grafo():
    g = StateGraph(EstadoTitulo)
    g.add_node("contexto", _nodo_contexto)
    g.add_node("proponente", _nodo_proponente)
    g.add_node("aterrizador", _nodo_aterrizador)
    g.add_node("auditor", _nodo_auditor)
    g.add_node("entrega", _nodo_entrega)

    g.set_entry_point("contexto")
    g.add_edge("contexto", "proponente")
    g.add_edge("proponente", "aterrizador")
    g.add_edge("aterrizador", "auditor")
    g.add_conditional_edges("auditor", _ruta_tras_auditor, {
        "proponente": "proponente",
        "entrega": "entrega",
    })
    g.add_edge("entrega", END)
    return g.compile()


_GRAFO = _construir_grafo()


def responder_titulo(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Punto de entrada del panel de título.

    Devuelve `{"respuesta", "seccion", "texto_mejorado", "titulo", "alternativas"}`.
    """
    estado: EstadoTitulo = {
        "consulta": mensaje,
        "historial": historial or [],
        "doc": doc,
        "biblioteca": biblioteca,
    }
    try:
        final = _GRAFO.invoke(estado)
    except Exception as exc:                              # noqa: BLE001
        logger.error(f"[titulo_panel] Error ejecutando el panel: {exc}")
        return {"respuesta": _FALLBACK, "seccion": None, "texto_mejorado": "", "titulo": "", "alternativas": []}

    dictamen = final.get("dictamen") or {}
    titulo = dictamen.get("titulo_final") or ""
    return {
        "respuesta":      (final.get("respuesta_final") or "").strip() or _FALLBACK,
        "seccion":        SECCION_TITULO if titulo else None,
        "texto_mejorado": titulo,
        "titulo":         titulo,
        "alternativas":   [a for a in (dictamen.get("alternativas") or []) if a],
    }
