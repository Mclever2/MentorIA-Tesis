"""
Panel de PLANTEAMIENTO — del título a la cadena problema → preguntas → objetivos.

Es la etapa siguiente al título y la que más silenciosamente se tuerce: el chat
genérico redactaba un problema inventado («los estudiantes carecen de las
herramientas necesarias», sin un solo dato) y luego derivaba preguntas
específicas que no eran partes de la general sino estudios distintos. El caso
típico: la pregunta general es «¿de qué manera X mejora Y?» y una específica
pregunta «¿qué diferencias hay en Y entre quienes usan X y quienes no?» — esa
responde ella sola la general, y con eso la lógica del proyecto se cae.

Cuatro agentes encadenados:

  1. REDACTOR DEL PROBLEMA — arma la realidad problemática con criterio y sin
     inventar: cada afirmación que necesita respaldo sale como hueco explícito
     con el dato que hay que conseguir y dónde buscarlo.
  2. DESCOMPONEDOR — pregunta general y específicas bajo dos reglas duras:
     ninguna específica puede responder la general por sí sola, y juntas deben
     cubrirla. Los niveles cognitivos escalan según la taxonomía de Bloom.
  3. ALINEADOR — objetivos 1:1 desde las preguntas (el verbo del objetivo sale
     del nivel de Bloom de su pregunta), enfoque por objetivo y reparto realista
     entre Tesis 1 y Tesis 2.
  4. VERIFICADOR DE RESPALDO — recorre los textos y marca lo que se afirma como
     hecho sin poder sostenerlo. Se le quitó el papel de auditar la estructura:
     en las pruebas sus sugerencias contradecían correcciones correctas (pedía
     ampliar preguntas acotadas a propósito, o decía que faltaba información que
     estaba escrita). Esa parte la cubren comprobaciones deterministas, y él se
     queda con lo único que puede verificar citando: las afirmaciones sin dato.

Sobre el reparto Tesis 1 / Tesis 2: el reglamento pide alcanzar la mitad de los
objetivos específicos en Tesis 1 y culminarlos en Tesis 2, sin prohibir
terminarlos todos antes. En la práctica el artefacto rara vez está terminado en
Tesis 1, así que el panel propone las tres salidas que sí funcionan: resultados
cuantitativos parciales, revisión sistemática de la literatura, o trabajo sobre
datos históricos.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .llm import llm_rapido

logger = logging.getLogger(__name__)

_K_LIBROS = 6
_MAX_CHARS_FRAG = 900

_FALLBACK = (
    "No pude armar el planteamiento en este momento. Vuelve a pedírmelo en unos segundos."
)


# ── Reglas de dominio (las que el chat genérico no aplicaba) ────────────────

_REGLA_VOZ = """\
CÓMO ESCRIBES: le hablas al estudiante de TÚ, en segunda persona. Lo que redactes lo lee él tal
cual. Nunca «el estudiante…», «el usuario…» ni «se observa que…»."""

_REGLA_SIN_INVENTAR = """\
NO INVENTES HECHOS. Ni cifras, ni porcentajes, ni estudios, ni autores, ni nombres de instituciones
que no te hayan dado. Un planteamiento con datos inventados es la forma más rápida de perder una
sustentación: el jurado pide la fuente y no existe.
Cuando una afirmación necesite respaldo y no lo tengas, el hueco va PEGADO a la afirmación, en el
mismo punto de la frase, nunca al final del párrafo:
    MAL:  «…lo que se traduce en un alto porcentaje de proyectos que no cumplen los estándares. […]
           [dato por conseguir: porcentaje de proyectos que cumplen — fuente: coordinación]»
           (se lee como un hecho ya establecido; el hueco al final no lo desmiente)
    BIEN: «…lo que se traduce en [dato por conseguir: porcentaje de proyectos que no cumplen los
           estándares — fuente: coordinación de la escuela] de los proyectos.»
El hueco SUSTITUYE al dato que no tienes; no lo acompaña. Una laguna bien señalada es correcta; una
afirmación cuantitativa sin respaldo («un alto porcentaje», «la mayoría», «con frecuencia») es una
falsedad aunque más abajo digas que falta el dato."""

_REGLA_BLOOM = """\
CÓMO SE DESCOMPONE UNA PREGUNTA GENERAL (esto es lo que casi todos hacen mal):

REGLA 1 — CADA ESPECÍFICA ES UNA PARTE, NUNCA EL TODO.
Ninguna pregunta específica puede responder por sí sola la pregunta general. Si al contestarla ya
tienes contestada la general, esa pregunta NO es específica: es la general disfrazada, y rompe la
lógica del proyecto.
  General:   «¿De qué manera un sistema multiagente mejora la calidad metodológica de los proyectos
              de tesis de Ingeniería de la UPAO, 2026?»
  MAL:       «¿Qué diferencias hay en la calidad metodológica entre proyectos que usan el sistema y
              los que no?»  → esto ES la general; responderla cierra el estudio.
  BIEN:      «¿Qué criterios de calidad metodológica son verificables de forma automática en un
              proyecto de tesis?» → es un peldaño necesario, y sola no responde la general.

REGLA 2 — JUNTAS CUBREN LA GENERAL.
Respondidas todas las específicas, la general queda contestada. Ni sobra ninguna (no abras un
estudio nuevo: «¿qué factores contextuales influyen…?» es otra tesis) ni falta un peldaño.

REGLA 3 — ESCALAN EN NIVEL COGNITIVO (TAXONOMÍA DE BLOOM).
Ordénalas de menor a mayor: primero identificar/describir lo que existe (comprender), luego
diseñar/aplicar la solución (aplicar), después analizar o comparar lo obtenido (analizar) y por
último evaluar el efecto (evaluar). Cada pregunta se apoya en la anterior.

REGLA 4 — UN CONSTRUCTO POR PREGUNTA.
No cambies de objeto a mitad de camino. Si la general habla de calidad metodológica, una específica
sobre «percepción de los estudiantes» introduce otro constructo (percepción ≠ calidad): solo cabe si
la general ya lo contenía, y entonces hay que decirlo y medirlo aparte."""

_REGLA_OBJETIVOS = """\
DE LAS PREGUNTAS SALEN LOS OBJETIVOS, NO AL REVÉS.
Cada pregunta específica genera UN objetivo específico, en el mismo orden y con el MISMO alcance. El
verbo del objetivo lo fija el nivel de Bloom de su pregunta: identificar/describir para comprender;
diseñar/implementar/aplicar para aplicar; analizar/comparar para analizar; evaluar/determinar para
evaluar. Un objetivo cuyo verbo esté por encima o por debajo de su pregunta desalinea la cadena.
El objetivo general es el espejo de la pregunta general, en infinitivo."""

_REGLA_ENFOQUE = """\
ENFOQUE POR OBJETIVO.
Di para CADA objetivo si se resuelve con datos cuantitativos, cualitativos o ambos, y con qué se
mide. Para Ingeniería lo recomendable es mantener el estudio CUANTITATIVO o MIXTO: son los que
permiten demostrar mejora con una medición comparable, que es lo que se espera de un proyecto de
ingeniería. Un objetivo puramente cualitativo puede acompañar (por ejemplo para caracterizar
criterios o requisitos), pero si TODOS lo son, el proyecto pierde la capacidad de demostrar efecto:
adviértelo."""

_REGLA_TESIS12 = """\
REPARTO REALISTA ENTRE TESIS 1 Y TESIS 2.
En Tesis 1 se pide alcanzar la MITAD de los objetivos específicos y en Tesis 2 culminarlos. Nada
prohíbe terminarlos todos en Tesis 1, y si el estudiante puede, mejor. Pero sé honesto con la
realidad: en Tesis 1 el artefacto casi nunca está terminado, así que comprometer resultados finales
ahí suele terminar en un objetivo incumplido.
Marca qué objetivos son alcanzables en Tesis 1 y, si el que produce resultados no lo es, recomienda
una de estas tres salidas —que sí funcionan y son aceptadas—:
  a) RESULTADOS CUANTITATIVOS PARCIALES: medir sobre un módulo o un subproceso ya terminado, no
     sobre el sistema completo.
  b) REVISIÓN SISTEMÁTICA DE LA LITERATURA: convertir un objetivo temprano en una RSL con protocolo
     explícito (criterios de inclusión, fuentes, periodo), que da resultados publicables sin artefacto.
  c) DATOS HISTÓRICOS: trabajar sobre registros ya existentes en la organización en lugar de esperar
     a que el sistema opere, lo que adelanta el análisis sin depender del desarrollo."""


# ── Contratos de salida ─────────────────────────────────────────────────────

class Problema(BaseModel):
    realidad: str = Field(
        description="La realidad problemática, 2-3 párrafos: qué ocurre, a quién afecta, con qué "
                    "magnitud y qué consecuencia tiene. Los datos que no tengas van como hueco "
                    "explícito [dato por conseguir: … — fuente: …]. Redactado en segunda persona "
                    "para que el estudiante lo pueda usar como base."
    )
    evidencia_a_conseguir: list[str] = Field(
        default_factory=list,
        description="Lista de los datos concretos que el estudiante debe conseguir para sostener la "
                    "realidad problemática, cada uno con dónde buscarlo.",
    )
    brecha: str = Field(description="Qué vacío deja la literatura o la práctica y que justifica el estudio.")


class PreguntaEspecifica(BaseModel):
    pregunta: str = Field(description="La pregunta específica, en una línea.")
    nivel_bloom: str = Field(description="Nivel de Bloom: comprender | aplicar | analizar | evaluar.")
    por_que_es_parte: str = Field(
        description="Por qué es una PARTE de la general y no la responde por sí sola. Una frase."
    )


class SalidaDescomposicion(BaseModel):
    pregunta_general: str = Field(description="La pregunta general, en una línea, coherente con el título.")
    especificas: list[PreguntaEspecifica] = Field(description="3 o 4 preguntas específicas, en orden creciente de Bloom.")
    cobertura: str = Field(
        description="Por qué respondidas todas queda contestada la general. Una o dos frases."
    )
    descartadas: list[str] = Field(
        default_factory=list,
        description="Preguntas que consideraste y descartaste por responder la general o por abrir "
                    "otro estudio, con el motivo. Ayuda al estudiante a no reintroducirlas.",
    )


class RevisionPregunta(BaseModel):
    pregunta: str = Field(description="La pregunta específica revisada, copiada tal cual la recibiste.")
    responde_la_general: bool = Field(
        description="True si respondiendo SOLO esta pregunta ya queda contestada la general."
    )
    cambia_de_constructo: bool = Field(
        default=False,
        description="True si la pregunta mide un objeto DISTINTO al de la general (p. ej. la general "
                    "es sobre calidad metodológica y esta pregunta es sobre percepción o satisfacción).",
    )
    motivo: str = Field(description="Por qué sí o por qué no. Una frase.")
    reemplazo: str = Field(
        default="",
        description="Si responde la general, la pregunta CORREGIDA que la sustituye: mismo nivel de "
                    "Bloom, pero acotada a una parte. Vacío si la original estaba bien.",
    )
    por_que_el_reemplazo_es_parte: str = Field(
        default="",
        description="Justificación de por qué el REEMPLAZO sí es una parte y no responde la general. "
                    "Una frase, en positivo. Vacío si no hubo reemplazo.",
    )


class SalidaVerificacion(BaseModel):
    revisiones: list[RevisionPregunta]


class ObjetivoEspecifico(BaseModel):
    objetivo: str = Field(description="El objetivo específico en infinitivo, derivado de su pregunta.")
    de_que_pregunta: str = Field(description="La pregunta específica de la que sale, copiada.")
    verbo_y_nivel: str = Field(description="Verbo elegido y nivel de Bloom que le corresponde.")
    enfoque: str = Field(description="cuantitativo | cualitativo | mixto, y con qué se mide.")
    tesis_1: bool = Field(description="¿Es alcanzable en Tesis 1?")
    justificacion_etapa: str = Field(description="Por qué cae en Tesis 1 o en Tesis 2.")


class SalidaAlineacion(BaseModel):
    objetivo_general: str = Field(description="Objetivo general en infinitivo, espejo de la pregunta general.")
    especificos: list[ObjetivoEspecifico]
    enfoque_global: str = Field(
        description="Enfoque recomendado para todo el proyecto (cuantitativo/mixto para ingeniería) "
                    "y por qué, dado el reparto de objetivos."
    )
    estrategia_tesis1: str = Field(
        description="Si en Tesis 1 no habrá artefacto terminado, cuál de las tres salidas conviene "
                    "(resultados parciales / revisión sistemática / datos históricos) y cómo aplicarla aquí."
    )


class Hallazgo(BaseModel):
    donde: str = Field(description="Dónde aparece: «planteamiento», «pregunta general», «objetivo N»…")
    problema_detectado: str = Field(
        description="La afirmación sin respaldo, CITADA ENTRE COMILLAS tal como está escrita."
    )
    correccion: str = Field(
        description="El hueco de dato que debe sustituirla, con la fuente donde conseguirlo."
    )


class SalidaAuditor(BaseModel):
    cadena_coherente: bool = Field(description="True si no queda ninguna afirmación sin respaldo.")
    hallazgos: list[Hallazgo] = Field(default_factory=list)
    veredicto: str = Field(description="Una o dos frases sobre qué falta respaldar antes de entregar.")


# ── Prompts ─────────────────────────────────────────────────────────────────

_PROMPT_PROBLEMA = """\
Eres el REDACTOR DEL PROBLEMA de un panel metodológico. Armas la realidad problemática del proyecto.

{regla_voz}

{regla_sin_inventar}

TÍTULO DEL PROYECTO:
{titulo}

LO QUE EL ESTUDIANTE HA CONTADO:
{contexto}

FUNDAMENTO METODOLÓGICO (libros indexados; apóyate en ellos para la estructura del planteamiento):
{libros}

TESIS REALES APROBADAS EN SU ESCUELA (para calibrar el nivel y el tipo de evidencia que se exige):
{evidencia_corpus}

CÓMO TRABAJAS — con criterio, no por rellenar:
- La realidad problemática NO es una opinión general sobre el tema: es la descripción de algo que
  ocurre, a quién le ocurre, cuánto y con qué consecuencia. Si no puedes cuantificar, di qué dato
  haría falta y dónde se consigue.
- Ordena: (1) contexto y qué se hace hoy, (2) qué falla y a quién afecta, (3) magnitud o síntoma
  medible, (4) consecuencia si sigue así, (5) qué vacío deja lo que ya existe.
- Que cada afirmación fuerte sea verificable o esté marcada como hueco. Prefiere tres frases
  sostenibles a dos párrafos que suenan bien y no se pueden defender."""

_PROMPT_DESCOMPOSICION = """\
Eres el DESCOMPONEDOR del panel. Del título y el problema sacas la pregunta general y las específicas.

{regla_voz}

{regla_bloom}

{regla_sin_inventar}

TÍTULO:
{titulo}

REALIDAD PROBLEMÁTICA YA REDACTADA:
{problema}

LO QUE EL ESTUDIANTE HA CONTADO:
{contexto}

CÓMO TRABAJAS:
- La pregunta general debe leerse como el título convertido en pregunta, sin ampliar el alcance.
- 3 o 4 específicas. Antes de entregar cada una, hazte la prueba: «si respondo SOLO esta, ¿queda
  contestada la general?». Si la respuesta es sí, deséchala y anótala en `descartadas`.
- Anota también las que descartes por abrir otro estudio o por cambiar de constructo."""

_PROMPT_VERIFICACION = """\
Eres el VERIFICADOR DE DESCOMPOSICIÓN. Tienes UNA sola tarea y no haces ninguna otra: comprobar,
pregunta por pregunta, si alguna específica responde por sí sola a la general. No opinas sobre
redacción, ni sobre claridad, ni sobre nada más.

LA PRUEBA, aplícala literalmente a cada una:
«Imagina que consigues los datos y respondes SOLO esta pregunta específica, y ninguna otra del
listado. ¿Queda ya contestada la pregunta general?»
  · Si la respuesta es SÍ → viola la regla. Marca `responde_la_general` en true y escribe el reemplazo.
  · Si la respuesta es NO → pasa a la segunda comprobación.

SEGUNDA COMPROBACIÓN — ¿MIDE OTRA COSA?
La pregunta debe versar sobre el MISMO objeto que la general. Si la general trata de la calidad
metodológica y la específica pregunta por la PERCEPCIÓN, la SATISFACCIÓN o la OPINIÓN de alguien,
está midiendo otro constructo: percepción no es calidad, y mezclarlos deja el proyecto sin poder
demostrar lo que promete el título. Marca `cambia_de_constructo` en true y reescríbela sobre el
objeto de la general, conservando el nivel de Bloom. (Solo se admite si la general ya nombraba ese
otro constructo, cosa que casi nunca ocurre.)

EL CASO QUE MÁS SE ESCAPA: la pregunta comparativa global. Si la general pregunta por el EFECTO de X
sobre Y, una específica del tipo «¿qué diferencias hay en Y entre quienes usan X y quienes no?» o
«¿qué mejoras en Y se observan al usar X?» ES la general con otras palabras. Responderla cierra el
estudio, así que hay que sustituirla.

CÓMO SE CORRIGE (ejes válidos para acotar sin perder el nivel de Bloom):
  · por DIMENSIÓN del constructo: en vez del efecto sobre Y entero, el comportamiento de UNA
    dimensión de Y.
  · por COMPONENTE de la solución: el aporte de una parte concreta de X, no de X completo.
  · por SUBPROCESO o etapa: el efecto dentro de un tramo del proceso, no del proceso entero.
  · por CONDICIÓN: bajo qué circunstancias se comporta de una u otra forma.
El reemplazo conserva el MISMO nivel de Bloom que la pregunta original.

EL REEMPLAZO DEBE NOMBRAR LO QUE ACOTA. Decir «una dimensión específica», «un componente
específico» o «un aspecto específico» NO acota nada: es la misma pregunta general con una muletilla,
y se rechaza igual que la original. Nombra la dimensión, el componente o la etapa concretos.
  MAL:  «¿Qué efectos tienen los sistemas multiagente en la calidad metodológica de una dimensión
         específica de los proyectos?»
  BIEN: «¿Qué efectos tiene la verificación automática de coherencia sobre la alineación entre
         objetivos y preguntas de investigación?»

PREGUNTA GENERAL:
{pregunta_general}

PREGUNTAS ESPECÍFICAS A VERIFICAR:
{especificas}

Las marcadas con «← YA MARCADA COMO VIOLACIÓN» han sido detectadas por una comprobación
independiente: NO las absuelvas. Para esas, `responde_la_general` es true y DEBES escribir el
reemplazo, aunque a ti te parezcan aceptables.

Devuelve una revisión por cada pregunta, en el mismo orden."""

_PROMPT_ALINEACION = """\
Eres el ALINEADOR del panel. Conviertes las preguntas en objetivos y decides enfoque y etapa.

{regla_voz}

{regla_objetivos}

{regla_enfoque}

{regla_tesis12}

TÍTULO:
{titulo}

PREGUNTA GENERAL Y ESPECÍFICAS:
{preguntas}

LO QUE EL ESTUDIANTE HA CONTADO (incluye si tendrá o no el sistema terminado):
{contexto}

CÓMO TRABAJAS:
- Un objetivo por pregunta, en el mismo orden. Nada de objetivos huérfanos ni preguntas sin objetivo.
- Marca la etapa con criterio: lo que exige el artefacto funcionando rara vez cabe en Tesis 1.
- Si el objetivo que produce resultados cae en Tesis 2, propón explícitamente la salida que permita
  tener resultados defendibles ya en Tesis 1."""

_PROMPT_AUDITOR = """\
Eres el VERIFICADOR DE RESPALDO del panel. No juzgas la estructura del proyecto: compruebas que todo
lo que se afirma como un hecho pueda sostenerse ante un jurado.

{regla_voz}

CADENA A AUDITAR:

TÍTULO: {titulo}

PROBLEMA:
{problema}

PREGUNTAS:
{preguntas}

OBJETIVOS:
{objetivos}

TU ÚNICA TAREA: encontrar AFIRMACIONES DE HECHO SIN RESPALDO en los textos de arriba.

Son las que un jurado convierte en «¿de dónde sacó ese dato?» y no hay respuesta:
  · cuantificadores vagos presentados como hechos: «un alto porcentaje», «la mayoría», «un número
    considerable», «con frecuencia», «la mayor parte»;
  · cifras, porcentajes o tendencias sin fuente;
  · afirmaciones sobre lo que ocurre en la institución o el sector que nadie ha medido aquí;
  · referencias a estudios o autores que no se citan.
Un hueco ya marcado como [dato por conseguir: … — fuente: …] NO es un hallazgo: está bien resuelto.

TAMPOCO SON HALLAZGOS las PREGUNTAS ni los OBJETIVOS. Una pregunta de investigación no afirma nada:
pregunta. Un objetivo declara lo que se va a hacer, no un hecho ya ocurrido. Ninguno de los dos
necesita una fuente que lo respalde —eso es justamente lo que el proyecto va a averiguar—. Busca
solo en el PLANTEAMIENTO y en el texto descriptivo.

CÓMO REPORTAS — obligatorio anclar:
En `problema_detectado` CITA ENTRE COMILLAS el fragmento exacto, copiado literal del texto de arriba.
Si no puedes citarlo porque no está escrito, el hallazgo no existe: no lo reportes. En `correccion`
escribe el hueco que debe sustituirlo, con la fuente concreta donde conseguir el dato.

QUÉ NO REPORTAS — NADA DE ESTRUCTURA. No opines sobre si las preguntas se derivan bien, si el
objetivo general refleja la pregunta, si algo «debería ser más específico» ni sobre redacción o
estilo. Esa parte ya la verificó otro paso del panel con comprobaciones deterministas, y en las
pruebas tus sugerencias estructurales contradecían correcciones correctas: pediste ampliar preguntas
que se habían acotado a propósito y afirmaste que faltaba información que estaba escrita. Limítate a
las afirmaciones sin respaldo, que es lo que sí puedes verificar citando.

Máximo 3 hallazgos, los más graves. Si no hay ninguno, dilo en una frase y no listes nada."""


# ── Composición de la respuesta ─────────────────────────────────────────────

def _componer(problema: dict, desc: dict, alin: dict, aud: dict, fuentes: list[str], n_rep: int) -> str:
    partes: list[str] = []

    if problema:
        partes.append("## Planteamiento del problema\n\n" + problema.get("realidad", ""))
        if problema.get("brecha"):
            partes.append(f"**El vacío que justifica tu estudio:** {problema['brecha']}")
        if problema.get("evidencia_a_conseguir"):
            partes.append(
                "### Los datos que tienes que conseguir para sostenerlo\n\n"
                "No los inventé a propósito: cada uno de estos es lo que el jurado te va a pedir.\n\n"
                + "\n".join(f"- {e}" for e in problema["evidencia_a_conseguir"])
            )

    if desc:
        partes.append(f"## Pregunta general\n\n**{desc.get('pregunta_general','')}**")
        esp = desc.get("especificas") or []
        if esp:
            bloque = [
                "## Preguntas específicas",
                "",
                "Cada una es una **parte** de la general y ninguna la responde sola: por eso escalan "
                "en nivel cognitivo (Bloom). Son también las que generan tus objetivos específicos.",
                "",
            ]
            for i, p in enumerate(esp, 1):
                bloque.append(
                    f"**{i}. {p.get('pregunta','')}**\n\n"
                    f"- *Nivel de Bloom:* {p.get('nivel_bloom','')}\n"
                    f"- *Por qué es una parte y no el todo:* {p.get('por_que_es_parte','')}"
                )
            if desc.get("cobertura"):
                bloque.append(f"*Por qué juntas cubren la general:* {desc['cobertura']}")
            partes.append("\n".join(bloque))
        if desc.get("descartadas"):
            partes.append(
                "### Preguntas que descarté (y por qué no las reintroduzcas)\n\n"
                + "\n".join(f"- {d}" for d in desc["descartadas"])
            )

    if alin:
        bloque = [
            "## Objetivos",
            "",
            f"**Objetivo general:** {alin.get('objetivo_general','')}",
            "",
            "Cada objetivo específico sale de su pregunta, en el mismo orden y con el verbo que le "
            "corresponde por nivel:",
            "",
        ]
        for i, o in enumerate(alin.get("especificos") or [], 1):
            etapa = "Tesis 1" if o.get("tesis_1") else "Tesis 2"
            bloque.append(
                f"**{i}. {o.get('objetivo','')}**\n\n"
                f"- *Sale de:* «{o.get('de_que_pregunta','')}»\n"
                f"- *Verbo y nivel:* {o.get('verbo_y_nivel','')}\n"
                f"- *Enfoque:* {o.get('enfoque','')}\n"
                f"- *Etapa realista:* **{etapa}** — {o.get('justificacion_etapa','')}"
            )
        partes.append("\n".join(bloque))

        if alin.get("enfoque_global"):
            partes.append(f"## Enfoque del proyecto\n\n{alin['enfoque_global']}")
        if alin.get("estrategia_tesis1"):
            partes.append(
                "## Cómo llegar a Tesis 1 con resultados\n\n"
                "En Tesis 1 se te pide alcanzar la mitad de tus objetivos específicos y culminarlos "
                "en Tesis 2. Terminarlos todos antes no está prohibido, pero el sistema rara vez "
                "está listo a tiempo, así que conviene planificarlo:\n\n"
                + alin["estrategia_tesis1"]
            )

    if aud and aud.get("hallazgos"):
        bloque = ["## Revisión de coherencia de la cadena", ""]
        if aud.get("veredicto"):
            bloque.append(aud["veredicto"] + "\n")
        for h in aud["hallazgos"]:
            bloque.append(
                f"- **{h.get('donde','')}:** {h.get('problema_detectado','')} "
                f"*Corrección:* {h.get('correccion','')}"
            )
        partes.append("\n".join(bloque))
    elif aud and aud.get("veredicto"):
        partes.append(f"## Revisión de coherencia de la cadena\n\n{aud['veredicto']}")

    if fuentes or n_rep:
        detalle = []
        if n_rep:
            detalle.append(f"{n_rep} tesis aprobadas de tu escuela en el repositorio UPAO")
        if fuentes:
            plural = "libros" if len(fuentes) > 1 else "libro"
            detalle.append(f"{len(fuentes)} {plural} de metodología: {', '.join(fuentes)}")
        partes.append("---\n\n_Consulté " + " y ".join(detalle) + "._")

    return "\n\n".join(p for p in partes if p).strip()


# ── Entrada pública ─────────────────────────────────────────────────────────

def responder_planteamiento(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Del título a la cadena problema → preguntas → objetivos, auditada."""
    from .ideacion import _historial_texto, _interes_del_hilo, _invocar, _libros

    contexto = _interes_del_hilo(mensaje, historial)
    titulo = _titulo_del_hilo(mensaje, historial, doc)
    programa = (getattr(doc, "programa", "") or "") if doc is not None else ""

    # Sin título ni descripción del proyecto NO se redacta nada. Pedir «dame mis
    # objetivos específicos» en frío llevaba a inventar un problema completo
    # —instituciones públicas, datos que nadie mencionó— y el estudiante no tiene
    # cómo notar que toda su cadena salió de la nada.
    if not titulo and len((contexto or "").strip()) < 60:
        return {
            "respuesta": (
                "Para esto necesito tu **título** o, si aún no lo tienes cerrado, una descripción "
                "de tu proyecto: qué construyes, qué problema resuelve y dónde.\n\n"
                "Sin eso tendría que inventármelo, y un objetivo deducido de la nada desalinea "
                "toda tu cadena problema → preguntas → objetivos sin que lo notes hasta la "
                "sustentación.\n\n"
                "Pégame lo que tengas, aunque esté a medias, y sigo desde ahí. Si todavía no "
                "tienes tema, dime «no sé qué tema hacer» y lo trabajamos primero."
            ),
            "titulo": "", "seccion": None,
        }

    evidencia, n_rep = _evidencia(titulo or contexto, programa)
    libros_txt, fuentes = _libros(
        biblioteca,
        "planteamiento del problema realidad problemática formulación pregunta de investigación "
        "objetivos generales y específicos taxonomía de Bloom enfoque cuantitativo cualitativo mixto",
    )

    base = {
        "regla_voz": _REGLA_VOZ,
        "regla_sin_inventar": _REGLA_SIN_INVENTAR,
        "titulo": titulo or "(el estudiante aún no ha fijado un título)",
        "contexto": contexto or "(sin contexto adicional)",
        "libros": libros_txt or "(sin fragmentos disponibles)",
        "evidencia_corpus": evidencia or "(el repositorio no está disponible)",
    }
    modelo = llm_rapido(temperatura=0.3)

    prob = _invocar(
        _PROMPT_PROBLEMA.format(**base), modelo, Problema,
        "Redacta la realidad problemática de este proyecto, sin inventar datos.",
    )
    problema_d = prob.model_dump() if prob else {}

    desc = _invocar(
        _PROMPT_DESCOMPOSICION.format(
            regla_voz=_REGLA_VOZ, regla_bloom=_REGLA_BLOOM,
            regla_sin_inventar=_REGLA_SIN_INVENTAR,
            titulo=base["titulo"], contexto=base["contexto"],
            problema=problema_d.get("realidad", "(aún no redactada)"),
        ),
        modelo, SalidaDescomposicion,
        "Formula la pregunta general y las específicas respetando las cuatro reglas.",
    )
    desc_d = desc.model_dump() if desc else {}
    desc_d = _verificar_hasta_limpiar(modelo, desc_d)

    alin_d = {}
    if desc_d.get("especificas"):
        alin = _invocar(
            _PROMPT_ALINEACION.format(
                regla_voz=_REGLA_VOZ, regla_objetivos=_REGLA_OBJETIVOS,
                regla_enfoque=_REGLA_ENFOQUE, regla_tesis12=_REGLA_TESIS12,
                titulo=base["titulo"], contexto=base["contexto"],
                preguntas=_texto_preguntas(desc_d),
            ),
            modelo, SalidaAlineacion,
            "Deriva los objetivos, asigna enfoque y reparte entre Tesis 1 y Tesis 2.",
        )
        alin_d = alin.model_dump() if alin else {}

    aud_d = {}
    if desc_d and alin_d:
        aud = _invocar(
            _PROMPT_AUDITOR.format(
                regla_voz=_REGLA_VOZ, titulo=base["titulo"],
                problema=problema_d.get("realidad", ""),
                preguntas=_texto_preguntas(desc_d),
                objetivos=_texto_objetivos(alin_d),
            ),
            modelo, SalidaAuditor,
            "Audita la coherencia de la cadena completa.",
        )
        aud_d = aud.model_dump() if aud else {}

    respuesta = _componer(problema_d, desc_d, alin_d, aud_d, fuentes, n_rep)
    if not respuesta:
        return {"respuesta": _FALLBACK, "titulo": "", "seccion": None}

    logger.info(
        f"[planteamiento] {len(desc_d.get('especificas') or [])} preguntas, "
        f"{len(alin_d.get('especificos') or [])} objetivos, "
        f"{len(aud_d.get('hallazgos') or [])} hallazgos de coherencia"
    )
    return {"respuesta": respuesta, "titulo": titulo, "seccion": None}


_RE_COMPARATIVA = re.compile(
    r"(en comparacion|comparacion con|frente a|diferencias? entre|diferencias? en|"
    r"que no (lo )?(utilizan|usan|emplean)|con y sin|versus| vs )"
)
_STOP_KW = set(
    "de la el los las un una y o en para con que se su sus del al es son por a como "
    "cual cuales cuanto esta este cuando donde "
    # Demostrativos y pronombres: no son contenido. Sin ellos, «aquellos que no lo
    # utilizan» aportaba «aquello» como si fuera un término propio y salvaba a un
    # clon de la pregunta general.
    "aquel aquella aquello aquellos aquellas ese esa eso esos esas estos estas "
    "otro otra otros otras mismo misma mismos mismas quien quienes cuyo cuya "
    "todo toda todos todas alguno alguna algunos algunas".split()
)


def _norm_kw(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip()


def _palabras_clave(texto: str) -> set[str]:
    """Palabras significativas, uniendo singular y plural.

    Sin el recorte de la «s» final, «sistema» y «sistemas» contaban como
    términos distintos y una reformulación de la general en singular se colaba
    como si aportara vocabulario propio.
    """
    palabras = set()
    for w in _norm_kw(texto).split():
        if len(w) > 3 and w not in _STOP_KW:
            palabras.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return palabras


# Relación de efecto: si la pregunta la enuncia sobre el mismo objeto que la
# general y sin acotar, es la general con otras palabras.
_RE_EFECTO = re.compile(
    r"(impacto|influ|efecto|de que manera|en que medida|contribuye|mejora[sn]?\b|incide)"
)
# Acotadores que convierten un efecto global en una parte legítima.
# El acotador tiene que NOMBRAR qué acota. «Un componente específico» o «una
# dimensión específica» no delimitan nada: son la pregunta general con una
# muletilla, y así se colaba de nuevo el clon de la general.
_RE_ACOTADOR = re.compile(
    r"(de las dimensiones|del componente \w+|del modulo \w+|de la etapa \w+|"
    r"subproceso de|bajo (que |la )?condicion|en el caso de|"
    r"(dimension|componente|modulo|etapa|criterio|indicador) de \w+)"
)


# «Una dimensión específica», «un componente específico»: acotan de boquilla sin
# decir cuál. Con un verbo de efecto delante, siguen siendo la pregunta general.
# Vocabulario que NO acota: comparación, efecto y muletillas. Una pregunta cuyos
# términos nuevos son todos de esta lista no aporta nada que la general no diga.
_VOCABULARIO_GENERICO = set(
    "diferencia diferencias observan observa presenta presentan mejora mejoras efecto efectos "
    "impacto influye influencia manera medida contribuye incide utilizan utiliza usan usa "
    "emplean emplea aplican aplica comparacion frente entre especifico especifica especificos "
    "especificas dimension dimensiones componente componentes aspecto aspectos elemento "
    "elementos criterio criterios modulo modulos parte partes cual cuales cuanto respecto "
    "relacion relacionado resultado resultados nivel niveles grado "
    "usar utilizar emplear aplicar medir evaluar analizar determinar identificar observar "
    "comparar mejorar lograr obtener tener hacer existe existen".split()
)

_RE_MULETILLA = re.compile(
    r"(un|una)\s+(dimension|componente|aspecto|modulo|criterio|elemento)\s+especific"
)


def _comparativa_global(general: str, especifica: str) -> bool:
    """¿Esta pregunta específica es la general con otras palabras?

    Comprobación determinista del error más grave del planteamiento. El
    verificador LLM lo caza casi siempre pero no de forma fiable —en las pruebas
    absolvió una idéntica al ejemplo prohibido— y este eslabón no admite azar: si
    entra mal, los objetivos se derivan de una pregunta mal puesta y la lógica
    del proyecto se cae entera.

    El criterio NO es que compare o que hable de efecto: es si la pregunta APORTA
    UN TÉRMINO PROPIO o solo repite el vocabulario de la general con muletillas.

        CLON:    «¿Qué diferencias en la CALIDAD METODOLÓGICA hay entre los que
                  usan X y los que no?» — no nombra nada que la general no diga.
        LEGÍTIMA: «¿Qué diferencias hay en la ALINEACIÓN ENTRE OBJETIVOS Y
                  PREGUNTAS entre los que usan X y los que no?» — acota a una
                  dimensión nombrada; responderla no cierra el estudio.

    Sin esta distinción se marcaba como clon una pregunta correctamente acotada,
    que es un falso positivo caro: el panel la reescribía y empeoraba la cadena.
    """
    texto = _norm_kw(especifica)
    if not (_RE_COMPARATIVA.search(texto) or _RE_EFECTO.search(texto)):
        return False

    kg = _palabras_clave(general)
    ke = _palabras_clave(especifica)
    if not kg or not ke:
        return False

    # Términos propios: lo que la pregunta añade y no es vocabulario de
    # comparación, de efecto ni una muletilla de acotación.
    propios = {p for p in (ke - kg) if p not in _VOCABULARIO_GENERICO}
    if propios:
        return False

    # Sin términos propios, solo es una pregunta específica si además se aleja
    # del vocabulario de la general; si lo comparte, es la general reformulada.
    return len(kg & ke) / len(kg) >= 0.25


def _verificar_descomposicion(modelo, desc: dict) -> dict:
    """Sustituye las preguntas específicas que responden por sí solas a la general.

    Va en un paso aparte porque el descomponedor, aunque tenga la regla delante,
    reincide en la pregunta comparativa global («¿qué mejoras se observan al usar
    X frente a no usarlo?»), que es la general con otras palabras. Y el auditor
    final no sirve para esto: llega cuando los objetivos ya se derivaron de una
    pregunta mal puesta, y en las pruebas la daba por buena.
    """
    from .ideacion import _invocar

    especificas = desc.get("especificas") or []
    if not especificas or not desc.get("pregunta_general"):
        return desc

    general = desc["pregunta_general"]
    # Comprobación determinista previa: lo que caiga aquí no lo puede absolver el
    # modelo (ver `_comparativa_global`).
    sospechosas = [
        i for i, p in enumerate(especificas, 1)
        if _comparativa_global(general, p.get("pregunta", ""))
    ]
    listado = "\n".join(
        f"{i}. {p.get('pregunta','')}  [nivel: {p.get('nivel_bloom','')}]"
        + ("   ← YA MARCADA COMO VIOLACIÓN, no la absuelvas" if i in sospechosas else "")
        for i, p in enumerate(especificas, 1)
    )
    if sospechosas:
        logger.info(
            f"[planteamiento] La comprobación determinista marcó las preguntas {sospechosas} "
            "como comparativas globales"
        )
    salida = _invocar(
        _PROMPT_VERIFICACION.format(pregunta_general=general, especificas=listado),
        modelo, SalidaVerificacion,
        "Aplica la prueba a cada pregunta específica y corrige las que respondan la general.",
    )
    if salida is None:
        return desc

    corregidas, n = list(especificas), 0
    for i, rev in enumerate(salida.revisiones[: len(corregidas)]):
        # Lo marcado por la comprobación determinista no se puede absolver: si el
        # modelo dijo que estaba bien, se ignora su veredicto y se exige reemplazo.
        viola = (
            rev.responde_la_general
            or rev.cambia_de_constructo
            or (i + 1) in sospechosas
        )
        if viola and rev.reemplazo.strip():
            original = corregidas[i].get("pregunta", "")
            # La justificación del reemplazo, NO el motivo del descarte: copiar el
            # motivo dejaba la contradicción de una pregunta cuya explicación decía
            # «esta pregunta responde a la general».
            corregidas[i] = {
                **corregidas[i],
                "pregunta": rev.reemplazo.strip(),
                "por_que_es_parte": (
                    rev.por_que_el_reemplazo_es_parte.strip()
                    or corregidas[i].get("por_que_es_parte", "")
                ),
            }
            n += 1
            motivo = (
                "medía un constructo distinto al de la pregunta general"
                if rev.cambia_de_constructo and not rev.responde_la_general
                else "respondía por sí sola la pregunta general"
            )
            desc.setdefault("descartadas", []).append(
                f"«{original}» — {motivo}, así que la sustituí por «{rev.reemplazo.strip()}»."
            )
    if n:
        desc["especificas"] = corregidas
        logger.info(f"[planteamiento] {n} pregunta(s) específica(s) corregidas por responder la general")
    return desc


def _verificar_hasta_limpiar(modelo, desc: dict, rondas: int = 2) -> dict:
    """Re-verifica lo sustituido: el reemplazo también puede ser un clon.

    Ocurría de hecho — el verificador cambiaba «¿cómo se mide el impacto de X en
    Y?» por «¿qué efectos tiene X en una dimensión específica de Y?», que es la
    misma pregunta con una muletilla. Como la sustitución era de una sola pasada,
    nadie revisaba el resultado.
    """
    for ronda in range(rondas):
        desc = _verificar_descomposicion(modelo, desc)
        general = desc.get("pregunta_general", "")
        quedan = [
            p.get("pregunta", "") for p in (desc.get("especificas") or [])
            if _comparativa_global(general, p.get("pregunta", ""))
        ]
        if not quedan:
            return desc
        logger.info(
            f"[planteamiento] Ronda {ronda + 1}: {len(quedan)} reemplazo(s) siguen replicando la general"
        )
    return desc


def _texto_ya_corregidas(desc: dict) -> str:
    """Preguntas que el verificador ya acotó, para que el auditor no las revierta.

    Sin esto el auditor pedía «relaciónala más directamente con el efecto de X
    sobre Y» justo sobre la pregunta que se acababa de acotar por responder ella
    sola a la general: seguir esa corrección deshace el arreglo.
    """
    corregidas = [
        d for d in (desc.get("descartadas") or []) if "la sustituí por" in d
    ]
    if not corregidas:
        return "(ninguna)"
    return "\n".join(f"- {c}" for c in corregidas)


def _texto_preguntas(desc: dict) -> str:
    filas = [f"GENERAL: {desc.get('pregunta_general','')}"]
    for i, p in enumerate(desc.get("especificas") or [], 1):
        filas.append(f"{i}. {p.get('pregunta','')}  [nivel: {p.get('nivel_bloom','')}]")
    return "\n".join(filas)


def _texto_objetivos(alin: dict) -> str:
    filas = [f"GENERAL: {alin.get('objetivo_general','')}"]
    for i, o in enumerate(alin.get("especificos") or [], 1):
        etapa = "Tesis 1" if o.get("tesis_1") else "Tesis 2"
        filas.append(
            f"{i}. {o.get('objetivo','')}  [de: {o.get('de_que_pregunta','')}] "
            f"[{o.get('enfoque','')}] [{etapa}]"
        )
    return "\n".join(filas)


def _evidencia(tema: str, programa: str) -> tuple[str, int]:
    try:
        from backend.rag.titulos_store import buscar_titulos_similares, contexto_titulos
        from .deps import get_embeddings

        emb = get_embeddings()
        return (
            contexto_titulos(emb, tema=tema, programa=programa or None, k=6),
            len(buscar_titulos_similares(emb, tema, k=6, programa=programa or None)),
        )
    except Exception as exc:                                   # noqa: BLE001
        logger.warning(f"[planteamiento] Evidencia del repositorio no disponible: {exc}")
        return "", 0


def _titulo_del_hilo(mensaje: str, historial: list[dict] | None, doc) -> str:
    """Busca el título: el del proyecto indexado, o el que el estudiante pegó en el chat."""
    if doc is not None and getattr(doc, "vector_store", None) is not None:
        try:
            from backend.rag import limpiar_marcas_rag, recuperar_contexto

            texto = limpiar_marcas_rag(recuperar_contexto(doc.vector_store, "1. Título del proyecto"))
            primera = next((l.strip() for l in (texto or "").split("\n") if len(l.strip()) > 30), "")
            if primera:
                return primera[:300]
        except Exception:                                      # noqa: BLE001
            pass

    # Sin proyecto: el título suele venir pegado en el propio mensaje o en uno previo.
    from .llm import llm_rapido as _llm

    candidatos = [mensaje] + [
        t.get("contenido", "") for t in reversed(historial or []) if t.get("rol") == "user"
    ]
    for c in candidatos:
        for linea in (c or "").split("\n"):
            limpio = linea.strip(" .\"'«»")
            # Un título de tesis es una línea larga sin signos de pregunta.
            if 40 < len(limpio) < 300 and "?" not in limpio and "¿" not in limpio:
                return limpio
    return ""
