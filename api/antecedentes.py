"""
Panel de ANTECEDENTES y MARCO TEÓRICO.

La regla que gobierna todo este módulo: **aquí no se redacta el contenido**. Un
antecedente es un estudio real, con autor, año, diseño y resultados reales. Un
modelo que "redacta antecedentes" produce referencias verosímiles e inexistentes,
y eso en una tesis no es un error de estilo: es falta académica. El jurado pide
el DOI y no existe.

Lo que sí puede hacer un asesor —y es lo que hace este panel— es dejar al
estudiante en condiciones de escribirlos él:

  1. ESTRATEGA DE BÚSQUEDA — de sus variables saca los términos en español y en
     inglés (sin los ingleses no hay Scopus), las cadenas booleanas listas para
     pegar, y a qué base ir para lo internacional, lo nacional y lo local.
  2. PLANIFICADOR DE ANTECEDENTES — dónde buscar los 8 más relevantes (de preferencia
     internacionales: el embudo es de la realidad problemática, no de los antecedentes) y
     la estructura de cada uno, con la plantilla en prosa APA 7 lista para rellenar.
  3. ARQUITECTO DEL MARCO TEÓRICO — qué constructos hay que definir, en qué orden
     y cuáles exigen fuente fundacional frente a fuente reciente.

Y un guardia determinista que rechaza cualquier cita con forma de APA que se
haya colado en la respuesta: si aparece «Ramírez (2023)» sin que el estudiante lo
haya aportado, la respuesta se limpia antes de salir.

Sobre el acceso a los artículos: se orienta hacia el acceso institucional de la
UPAO, los repositorios nacionales (ALICIA, RENATI), los regionales de acceso
abierto (SciELO, Redalyc, Latindex, DOAJ) y los localizadores legítimos de
copias abiertas (Unpaywall, CORE, OpenAlex, Google Scholar), además del correo
al autor de correspondencia, que funciona más de lo que parece.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from .llm import llm_rapido

logger = logging.getLogger(__name__)

_FALLBACK = (
    "No pude preparar la estrategia de búsqueda ahora mismo. Vuelve a pedírmelo en unos segundos."
)

# Nº de antecedentes que se recomienda reunir: los más relevantes, no los primeros.
ANTECEDENTES_RECOMENDADOS = 8


# ── Regla transversal: aquí no se inventan fuentes ──────────────────────────

_REGLA_NO_INVENTAR_FUENTES = """\
REGLA ABSOLUTA — NO ESCRIBAS NINGUNA CITA.
No inventes autores, años, títulos de artículos, revistas, DOIs ni resultados. Ni uno. Ni siquiera
«a modo de ejemplo». Un antecedente inventado no es un error de redacción: es falta académica, y al
estudiante lo hunde en la sustentación cuando el jurado pide el DOI y no existe.

Tú NO redactas los antecedentes: le das al estudiante lo que necesita para encontrarlos y escribirlos
él. Cuando muestres la forma que debe tener un antecedente, usa marcadores vacíos —[Autor, año],
[revista], [n = ], [resultado]— nunca nombres ni cifras plausibles.

Si te piden directamente «redáctame los antecedentes», explica en una frase por qué no se puede hacer
así y entrega la estrategia de búsqueda y la plantilla. No te disculpes de más ni des un sermón."""

_REGLA_VOZ = """\
CÓMO ESCRIBES: le hablas al estudiante de TÚ, en segunda persona. Nunca «el estudiante…» ni
«el usuario…». Lo que redactes lo lee él tal cual."""


# ── Contratos ───────────────────────────────────────────────────────────────

class CadenaBusqueda(BaseModel):
    base: str = Field(description="Base de datos o buscador donde se usa esta cadena.")
    cadena: str = Field(description="La cadena booleana lista para copiar y pegar, con comillas y operadores.")
    para_que: str = Field(description="Qué tipo de antecedente busca esta cadena. Una frase.")


class SalidaEstrategia(BaseModel):
    terminos_es: list[str] = Field(description="Términos clave en español, sacados de las variables del proyecto.")
    terminos_en: list[str] = Field(
        description="Los mismos términos en INGLÉS. Son imprescindibles: la literatura indexada en "
                    "Scopus y Web of Science está en inglés y sin ellos no aparece casi nada."
    )
    sinonimos: list[str] = Field(
        default_factory=list,
        description="Variantes y sinónimos que cambian los resultados (p. ej. «standby power», "
                    "«vampire power», «phantom load» para el mismo fenómeno).",
    )
    cadenas: list[CadenaBusqueda] = Field(description="3 a 5 cadenas booleanas listas para pegar.")
    criterios_inclusion: list[str] = Field(
        description="Criterios concretos: ventana de años, tipo de documento, idioma, cuartil mínimo."
    )
    criterios_exclusion: list[str] = Field(description="Qué descartar y por qué.")


class BloqueAntecedentes(BaseModel):
    ambito: Literal["internacional", "nacional", "local"]
    cuantos: int = Field(description="Cuántos antecedentes buscar en este ámbito.")
    donde_buscar: list[str] = Field(description="Fuentes concretas para este ámbito, en orden de utilidad.")
    que_esperar: str = Field(
        description="Qué es realista encontrar aquí. Si es probable que NO exista nada, dilo y explica "
                    "qué hacer entonces: no se fuerza un antecedente que no existe."
    )


class SalidaPlanAntecedentes(BaseModel):
    reparto: list[BloqueAntecedentes]
    nota_cobertura: str = Field(
        description="Una o dos frases: los nacionales y locales son opcionales; si su formato pide un "
                    "subapartado por ámbito y no hay estudios sólidos, cómo se declara esa ausencia."
    )


class ConstructoTeorico(BaseModel):
    constructo: str = Field(description="El concepto que hay que definir.")
    por_que: str = Field(description="Por qué este proyecto lo necesita. Una frase.")
    tipo_de_fuente: str = Field(
        description="Qué fuente le corresponde: fundacional (el autor que acuñó el concepto), "
                    "estado del arte reciente, o norma/estándar técnico."
    )
    donde_buscarlo: str = Field(description="Dónde encontrar esa fuente, concreto.")


class SalidaMarcoTeorico(BaseModel):
    orden: list[ConstructoTeorico] = Field(
        description="Los constructos en el ORDEN en que deben aparecer: de lo general del dominio a "
                    "lo específico de la solución, terminando por las métricas de la variable dependiente."
    )
    terminos_basicos: list[str] = Field(
        description="Términos que van en «Definición de términos básicos» y no en la base teórica: "
                    "los técnicos que el jurado podría no manejar."
    )


# ── Prompts ─────────────────────────────────────────────────────────────────

_PROMPT_ESTRATEGIA = """\
Eres el ESTRATEGA DE BÚSQUEDA BIBLIOGRÁFICA de un panel de asesoría de tesis.

{regla_voz}

{regla_no_inventar}

PROYECTO DEL ESTUDIANTE:
{proyecto}

FUNDAMENTO METODOLÓGICO (libros indexados del sistema):
{libros}

TU TRABAJO: convertir sus variables en una búsqueda que de verdad devuelva resultados.
- Saca los términos de la VARIABLE INDEPENDIENTE (la tecnología o intervención) y de la VARIABLE
  DEPENDIENTE (lo que se mide). Los antecedentes útiles son los que cruzan ambas.
- Da los términos en inglés SIEMPRE, y sus sinónimos reales: un mismo fenómeno tiene varios nombres
  en la literatura y buscar solo uno deja fuera la mitad.
- Las cadenas booleanas van listas para pegar, con comillas para las frases exactas, OR entre
  sinónimos y AND entre los dos bloques de variables.
- En los criterios: ventana de años realista (lo habitual es los últimos 5, ampliable a 10 si el
  tema es poco explorado), tipo de documento y cuartil.

NUNCA METAS LA CIUDAD NI EL PAÍS EN LA BÚSQUEDA INTERNACIONAL. Es el error que deja al estudiante con
cero resultados y creyendo que su tema no está investigado. Nadie en Scopus ha publicado sobre su
distrito: la delimitación local es de SU estudio, no un filtro de búsqueda. La geografía solo entra
en las cadenas de ámbito nacional (ALICIA, RENATI, SciELO), y ahí basta con el país.

LAS CADENAS SON UNA ESCALERA, DE MÁS ESTRICTA A MÁS ABIERTA, y cada una DISTINTA de las demás:
  1ª — cruce exacto de las dos variables. Es la ideal; puede devolver muy poco.
  2ª — si la anterior devuelve menos de 5 resultados: suelta el término más específico y deja el
       fenómeno con sus sinónimos.
  3ª — solo la variable dependiente con su métrica, para encontrar cómo la miden otros aunque usen
       otra tecnología.
  4ª — (opcional) ámbito nacional/regional: términos EN ESPAÑOL y el país, para ALICIA, RENATI o
       SciELO. Los antecedentes se aconsejan de preferencia internacionales: esta cadena es solo
       para sumar algún nacional sólido si existe.
Explica en `para_que` en qué caso usar cada una.

USA LA SINTAXIS DE CADA BASE: en Scopus se antepone el campo — TITLE-ABS-KEY("…") AND TITLE-ABS-KEY("…");
en Web of Science se usa TS=("…") AND TS=("…"); en Google Scholar y en los repositorios en español va
la cadena simple con comillas. No repitas la misma cadena en las tres.
"""

_PROMPT_PLAN = """\
Eres el PLANIFICADOR DE ANTECEDENTES del panel.

{regla_voz}

{regla_no_inventar}

PROYECTO DEL ESTUDIANTE:
{proyecto}

Se recomienda reunir {n} antecedentes, los MÁS RELEVANTES —no los primeros que aparezcan—, y se
aconseja que sean DE PREFERENCIA INTERNACIONALES: los mejores estudios del tema (revistas Q1/Q2, los
más citados), porque son los que le permiten al estudiante comparar sus resultados y guiarse en su
diseño. Es un consejo, no una obligación.

REGLA DEL REPARTO: lo internacional va SIEMPRE primero y se lleva la gran mayoría (idealmente los {n}).
Lo nacional y lo local son OPCIONALES: `cuantos` = 0 es válido, y entre ambos nunca más de 2. Súmalos
solo si en ESTE tema es probable que existan estudios sólidos que crucen sus variables; forzarlos lleva
a citar trabajos que no vienen a cuento, y el jurado lo detecta enseguida. Sé honesto sobre qué es
probable encontrar. NO uses la técnica del embudo aquí: esa va en la realidad problemática.

Di, para cada ámbito, dónde buscar EN CONCRETO. Nombra las fuentes, no las describas: «repositorios de
universidades peruanas» no le sirve de nada, «RENATI» sí.

FUENTES POR ÁMBITO (usa estas, en este orden):
  · INTERNACIONAL — Scopus y Web of Science (vía el acceso institucional de la UPAO), IEEE Xplore
    para lo de ingeniería, ScienceDirect, SpringerLink, ACM Digital Library, y Google Scholar para
    rastrear la copia abierta de lo que aparezca de pago.
  · NACIONAL (Perú) — ALICIA (Concytec), que agrega la producción científica peruana; RENATI
    (Sunedu), que agrega TODAS las tesis sustentadas en el país y es la fuente natural de un
    antecedente nacional; SciELO Perú; Redalyc y Latindex para lo iberoamericano.
  · LOCAL — el repositorio institucional de la UPAO y los de las otras universidades de Trujillo o de
    la región. Aquí es donde más habitual es no encontrar nada, y hay que decirlo sin rodeos.
"""

_PROMPT_MARCO = """\
Eres el ARQUITECTO DEL MARCO TEÓRICO del panel.

{regla_voz}

{regla_no_inventar}

PROYECTO DEL ESTUDIANTE:
{proyecto}

FUNDAMENTO METODOLÓGICO (libros indexados):
{libros}

TU TRABAJO: decir QUÉ hay que definir y en qué orden, no definirlo tú.
- El orden va de lo general del dominio a lo específico de la solución, y termina en las métricas con
  las que se medirá la variable dependiente: si el marco teórico no llega hasta la métrica, la
  medición del capítulo 4 queda sin sustento.
- Distingue el constructo que necesita FUENTE FUNDACIONAL (quien acuñó el concepto; no se sustituye
  por un artículo reciente que lo cite de pasada) del que necesita ESTADO DEL ARTE RECIENTE (las
  técnicas, que envejecen), y del que se apoya en NORMA O ESTÁNDAR técnico.
- Separa lo que va en la base teórica de lo que va en «Definición de términos básicos»: allí van los
  términos técnicos que el jurado podría no manejar, definidos en una o dos líneas.
"""


# ── Guardia determinista contra citas inventadas ────────────────────────────

# «Ramírez (2023)», «Ramírez y Chen (2022)», «(Ramírez, 2023)», «Chen et al. (2021)».
_RE_CITA_APA = re.compile(
    r"(?<![\[\w])"
    r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}"
    r"(?:\s+(?:y|&|and)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}|\s+et\s+al\.?)?"
    r"\s*\(\s*(?:19|20)\d{2}[a-z]?\s*\)"
    r"|\(\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+(?:y|&|and)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}|\s+et\s+al\.?)?"
    r"\s*,\s*(?:19|20)\d{2}[a-z]?\s*\))"
)

# Marcadores legítimos: son huecos, no citas.
_RE_MARCADOR = re.compile(r"\[\s*(autor|apellido|año|anio|revista|doi|n\s*=|resultado)[^\]]*\]", re.I)


def citas_inventadas(texto: str, permitidas: set[str] | None = None) -> list[str]:
    """Citas con forma APA que el panel no debería haber escrito.

    Es la última barrera y la más importante del módulo: una referencia
    inventada en una tesis es falta académica, y ningún prompt garantiza al 100 %
    que el modelo no deslice una «a modo de ejemplo».
    """
    permitidas = permitidas or set()
    encontradas = []
    for m in _RE_CITA_APA.finditer(texto or ""):
        cita = m.group(0).strip()
        if cita in permitidas:
            continue
        # Un marcador entre corchetes no es una cita.
        inicio = max(0, m.start() - 1)
        if texto[inicio : m.start()] == "[":
            continue
        encontradas.append(cita)
    return list(dict.fromkeys(encontradas))


def _limpiar_citas(texto: str, permitidas: set[str] | None = None) -> tuple[str, list[str]]:
    """Sustituye por un marcador toda cita que el panel no debía escribir."""
    inventadas = citas_inventadas(texto, permitidas)
    if not inventadas:
        return texto, []
    limpio = texto
    for cita in inventadas:
        limpio = limpio.replace(cita, "[Autor, año — busca la fuente real]")
    logger.warning(
        f"[antecedentes] {len(inventadas)} cita(s) inventada(s) sustituidas por marcador: "
        f"{', '.join(inventadas[:4])}"
    )
    return limpio, inventadas


# ── Guía de acceso (fija, no la genera el modelo) ───────────────────────────

_GUIA_ACCESO = """\
## Cómo conseguir los artículos que encuentres

El orden importa: cada paso es más barato que el siguiente.

1. **Acceso institucional UPAO.** Entra a las bases desde la biblioteca de la universidad o con tu
   cuenta institucional. Buena parte de lo que aparece de pago en Google te sale completo desde ahí.
2. **Busca la versión abierta antes de rendirte.** Muchos artículos de pago tienen una copia legal
   depositada por sus propios autores:
   - **Unpaywall** (extensión de navegador) — te avisa si hay versión abierta del DOI que estás viendo.
   - **CORE** y **OpenAlex** — buscadores de repositorios abiertos de todo el mundo.
   - **Google Scholar** — el enlace «[PDF]» a la derecha suele ser la copia del repositorio del autor.
3. **Repositorios en abierto de la región**, donde además está lo que necesitas para lo nacional:
   - **ALICIA (Concytec)** y **RENATI (Sunedu)** — producción científica y tesis peruanas.
   - **SciELO**, **Redalyc**, **Latindex**, **DOAJ** — revistas iberoamericanas de acceso abierto.
   - **Repositorio institucional UPAO** — tesis de tu propia escuela.
4. **Escríbele al autor de correspondencia.** Está en el propio artículo y suele responder: un correo
   de tres líneas diciendo que eres tesista y para qué lo necesitas funciona más de lo que parece.
5. **ResearchGate / Academia.edu** — pide el texto completo con el botón de solicitud."""

_GUIA_CUARTILES = """\
## Cómo saber si la revista sirve

Prioriza **Q1 y Q2**; **Q3** vale para completar, sobre todo en temas poco explorados.

- Comprueba el cuartil en **SJR (Scimago Journal Rank)**: busca la revista y mira el cuartil por
  categoría, no el general — una revista puede ser Q1 en una categoría y Q3 en otra, y la que cuenta
  es la de tu tema.
- En Scopus, filtra por año y ordena por citas: un artículo de 2019 con 200 citas suele pesar más
  ante un jurado que uno de 2024 con dos.
- Desconfía de revistas que prometen publicación en días o cobran sin revisión por pares: citar una
  depredadora resta credibilidad a todo tu marco teórico."""


_GUIA_BASE_TEORICA = """\
## Cómo se redacta la base teórica

La base teórica **no es un resumen de estudios previos** (eso son los antecedentes): es la teoría que
sostiene tus variables — qué son, de qué se componen y cómo se miden.

1. **Organízala por variables.** Un subtítulo por variable —primero la independiente (lo que
   construyes o aplicas), luego la dependiente (lo que mides)— y, dentro de cada una, sus dimensiones.
2. **En cada concepto: define, contrasta y toma postura.** Presenta cómo lo definen dos o tres
   autores, señala en qué coinciden o difieren y cierra con la definición que adoptas «para efectos de
   esta investigación». De ahí sale la definición conceptual de tu cuadro de operacionalización.
3. **Prosa propia con cita APA 7.** Parafrasea y cita al autor; deja las citas textuales para cuando la
   formulación exacta importa. Nada de párrafos sin fuente ni de definiciones copiadas en lista.
4. **La fuente según el concepto:** la fundacional para los conceptos (quien lo acuñó, aunque sea
   antigua), libros y artículos indexados recientes para técnicas y herramientas, y la norma o el
   estándar cuando lo haya (ISO, IEEE…). Ni blogs ni Wikipedia.
5. **Que llegue hasta la medición:** cada dimensión e indicador de tu operacionalización tiene que
   estar sustentado aquí; si un indicador no aparece en la base teórica, el jurado preguntará de dónde
   salió.
6. **Lo puntual va aparte:** los términos que solo necesitan una o dos líneas van en «Definición de
   términos básicos», no en la base teórica."""


def _estructura_antecedente() -> str:
    """La forma que debe tener CADA antecedente, en prosa y APA 7."""
    return """\
## Cómo se redacta cada antecedente

Cada uno va en **prosa corrida** (no en viñetas) y con **norma APA 7**. En un solo párrafo tienen que
estar estos siete elementos, en este orden:

1. **La cita** — `Apellido (año)` si el autor es el sujeto de la frase, o `(Apellido, año)` al cierre.
2. **El título del estudio** — opcional, solo si aporta claridad; si el párrafo ya se entiende, sobra.
3. **El problema que abordó** — qué situación motivó ese estudio.
4. **Su objetivo general** — qué se propuso lograr.
5. **Su diseño de investigación** — tipo, diseño, población y muestra. Es lo que más se olvida y lo
   primero que pregunta el jurado.
6. **Sus resultados cuantitativos** — las cifras concretas: porcentajes de mejora, tiempos, p-valores,
   tamaño de efecto. Un antecedente sin números no te sirve para justificar tu propia medición.
7. **Las implicancias para TU proyecto** — y esto es lo que separa un antecedente de un resumen: en
   qué te apoyas de ese estudio. Que su instrumento te sirve de base, que su diseño te confirma que la
   variable se puede medir así, que su resultado te da el rango esperable, o que su limitación es
   justamente la brecha que tú vas a cubrir.

**Plantilla para que la rellenes** (los corchetes son huecos que tú completas al leer el estudio):

> [Apellido, año] investigó [problema que abordó] en [contexto/país]. Su objetivo fue [objetivo
> general del estudio]. Empleó un diseño [tipo y diseño] con una muestra de [n = ], aplicando
> [instrumento o técnica]. Obtuvo [resultados cuantitativos: cifras concretas]. Este estudio aporta a
> mi investigación [implicancia: qué tomas de él — el instrumento, el rango esperable, la brecha que
> deja abierta].

Cierra la sección con una **síntesis y brecha de investigación**: dos o tres párrafos que digan qué
resuelven en conjunto los antecedentes, qué queda sin resolver y por qué eso justifica tu estudio. De
los proyectos aprobados que he visto, es la parte que casi nadie incluye y la que más peso da al
marco teórico."""


# ── Composición ─────────────────────────────────────────────────────────────

# De qué trata el pedido. «¿Y la base teórica?» recibía el reparto de los 8
# antecedentes y su plantilla: el estudiante preguntó tres veces y las tres le
# llegó lo mismo.
_RE_FOCO_MARCO = re.compile(
    r"(bases?\s+te[oó]ric|marco\s+te[oó]ric|marco\s+conceptual|definici[oó]n\s+de\s+t[eé]rminos|teor[ií]as?\b)",
    re.I,
)
_RE_FOCO_ANTECEDENTES = re.compile(
    r"(antecedent|estado\s+del\s+arte|revisi[oó]n\s+(de\s+|de\s+la\s+)?literatura|art[ií]culos?|paper|"
    r"scopus|scielo|estudios\s+previos)",
    re.I,
)
# Solo cuando PIDE que se los escriban tiene sentido explicar por qué no.
_RE_PIDE_REDACTAR = re.compile(
    r"\b(?<!\bse\s)(redact|escrib|h[aá]z|hac|gener|d[aá]me|arm|elabor|complet|constru)\w*\s+(\w+\s+){0,4}"
    r"(antecedent|marco|bases?\s+te[oó]ric|estado\s+del\s+arte)",
    re.I,
)


_ORDEN_AMBITO = {"internacional": 0, "nacional": 1, "local": 2}
_MAX_NO_INTERNACIONALES = 2


def _normalizar_reparto(reparto: list[dict], n: int) -> list[dict]:
    """Internacional primero y con la gran mayoría; nacional y local, como mucho 2 entre ambos.

    El consejo es que los antecedentes sean de preferencia internacionales. El modelo
    tendía a repartir 4/3/1 «para cubrir los tres ámbitos», que es justo lo que el
    asesor no recomienda; el reparto se fija aquí en vez de confiarlo al prompt."""
    bloques = sorted(
        (dict(b) for b in reparto if b.get("ambito") in _ORDEN_AMBITO),
        key=lambda b: _ORDEN_AMBITO[b["ambito"]],
    )
    restantes = _MAX_NO_INTERNACIONALES
    for b in bloques:
        if b["ambito"] != "internacional":
            b["cuantos"] = max(0, min(int(b.get("cuantos") or 0), restantes))
            restantes -= b["cuantos"]
    otros = sum(b["cuantos"] for b in bloques if b["ambito"] != "internacional")
    if not any(b["ambito"] == "internacional" for b in bloques):
        bloques.insert(0, {"ambito": "internacional", "donde_buscar": [
            "Scopus", "Web of Science", "IEEE Xplore", "ScienceDirect", "Google Scholar"],
            "que_esperar": "Es donde está la literatura más sólida de tu tema."})
    bloques[0]["cuantos"] = n - otros
    return bloques


def _foco(pedido: str) -> str:
    """"marco" si pide la base / el marco teórico y no los antecedentes; si no, "antecedentes"."""
    if _RE_FOCO_MARCO.search(pedido or "") and not _RE_FOCO_ANTECEDENTES.search(pedido or ""):
        return "marco"
    return "antecedentes"


def _componer(
    est: dict, plan: dict, marco: dict, pedido: str, fuentes: list[str], foco: str = "antecedentes",
) -> str:
    partes: list[str] = []

    if _RE_PIDE_REDACTAR.search(pedido or ""):
        if foco == "marco":
            partes.append(
                "## Por qué no te la redacto\n\n"
                "La base teórica se sostiene en autores reales que tú lees y citas. Si te la escribo "
                "yo, salen definiciones con citas que suenan perfectas y no existen — y ante el jurado "
                "eso no es un error de forma: es falta académica. Lo que sí hago es dejarte claro qué "
                "definir, en qué orden y de qué tipo de fuente sacar cada concepto."
            )
        else:
            partes.append(
                "## Por qué no te los redacto\n\n"
                "Un antecedente es un estudio real, con su autor, su muestra y sus resultados. Si te los "
                "escribo yo, salen referencias que suenan perfectas y no existen — y eso en tu sustentación "
                "no es un error de forma: es falta académica, y se descubre en cuanto el jurado pide el DOI. "
                "Lo que sí puedo hacer es dejarte la búsqueda hecha y la estructura lista, para que los "
                "escribas tú con estudios que sí existen."
            )

    if foco == "marco":
        partes.append(_GUIA_BASE_TEORICA)

    if est:
        bloque = ["## Con qué buscar", ""]
        if est.get("terminos_es"):
            bloque.append("**En español:** " + ", ".join(est["terminos_es"]))
        if est.get("terminos_en"):
            bloque.append(
                "**En inglés (imprescindibles):** " + ", ".join(est["terminos_en"])
                + "\n\nSin estos no encontrarás casi nada: lo que está indexado en Scopus y Web of "
                  "Science está en inglés."
            )
        if est.get("sinonimos"):
            bloque.append("**Sinónimos que cambian los resultados:** " + ", ".join(est["sinonimos"]))
        partes.append("\n\n".join(bloque))

        if est.get("cadenas"):
            filas = ["## Cadenas listas para pegar", ""]
            for c in est["cadenas"]:
                filas.append(
                    f"**{c.get('base','')}** — {c.get('para_que','')}\n\n```\n{c.get('cadena','')}\n```"
                )
            partes.append("\n\n".join(filas))

        crit = []
        if est.get("criterios_inclusion"):
            crit.append("**Incluye:**\n" + "\n".join(f"- {c}" for c in est["criterios_inclusion"]))
        if est.get("criterios_exclusion"):
            crit.append("**Descarta:**\n" + "\n".join(f"- {c}" for c in est["criterios_exclusion"]))
        if crit:
            partes.append("## Criterios de selección\n\n" + "\n\n".join(crit))

    if plan and plan.get("reparto"):
        n = ANTECEDENTES_RECOMENDADOS
        filas = [
            f"## Dónde buscar los {n}",
            "",
            f"Se recomiendan {n}, los **más relevantes** — no los primeros que aparezcan — y se "
            "aconseja que sean **de preferencia internacionales**: los mejores estudios de tu tema "
            "(revistas Q1/Q2, los más citados), que son los que te permiten comparar tus resultados y "
            "guiarte en tu diseño. Los nacionales o locales no son obligatorios: súmalos solo si existen "
            "y cruzan tus variables. (La técnica del embudo —de lo internacional a lo local— es para tu "
            "realidad problemática, no para los antecedentes.)",
            "",
        ]
        for b in _normalizar_reparto(plan["reparto"], n):
            cuantos = b.get("cuantos", 0)
            if b.get("ambito") == "internacional":
                etiqueta = f"{cuantos} (prioridad)"
            else:
                etiqueta = f"opcional — hasta {cuantos}" if cuantos else "opcional"
            filas.append(
                f"**{b.get('ambito','').capitalize()} — {etiqueta}**\n\n"
                f"- *Dónde:* {', '.join(b.get('donde_buscar') or [])}\n"
                f"- *Qué esperar:* {b.get('que_esperar','')}"
            )
        if plan.get("nota_cobertura"):
            filas.append(f"\n{plan['nota_cobertura']}")
        partes.append("\n".join(filas))

    if foco == "antecedentes":
        partes.append(_estructura_antecedente())

    if marco and marco.get("orden"):
        filas = [
            "## Tu marco teórico: qué definir y en qué orden",
            "",
            "De lo general del dominio a lo específico de tu solución, terminando en las métricas con "
            "las que vas a medir. Si el marco no llega hasta la métrica, tu capítulo de metodología "
            "queda sin sustento.",
            "",
        ]
        for i, c in enumerate(marco["orden"], 1):
            filas.append(
                f"**{i}. {c.get('constructo','')}**\n\n"
                f"- *Por qué lo necesitas:* {c.get('por_que','')}\n"
                f"- *Qué fuente le toca:* {c.get('tipo_de_fuente','')}\n"
                f"- *Dónde buscarla:* {c.get('donde_buscarlo','')}"
            )
        if marco.get("terminos_basicos"):
            filas.append(
                "\n**A «Definición de términos básicos» (una o dos líneas cada uno):** "
                + ", ".join(marco["terminos_basicos"])
            )
        partes.append("\n".join(filas))

    partes.append(_GUIA_CUARTILES)
    partes.append(_GUIA_ACCESO)

    if fuentes:
        plural = "libros" if len(fuentes) > 1 else "libro"
        partes.append(f"---\n\n_Consulté {len(fuentes)} {plural} de metodología: {', '.join(fuentes)}._")

    return "\n\n".join(p for p in partes if p).strip()


# ── Entrada pública ─────────────────────────────────────────────────────────

class SalidaTema(BaseModel):
    tema: str = Field(
        default="",
        description="El tema de SU investigación en una frase, con sus palabras; vacío si no lo dijo.",
    )


_PROMPT_TEMA = """\
Lees los mensajes que un estudiante le escribió a su asesor de tesis y extraes SOLO el tema de SU
investigación.

MENSAJES DEL ESTUDIANTE (del más antiguo al más reciente):
{mensajes}

Cuenta como tema lo que el estudiante dice que VA A INVESTIGAR, CONSTRUIR o MEDIR, con su contexto
(p. ej. «identificar factores de riesgo de corrupción en entidades públicas del Perú»).
NO son su tema las dudas sobre cómo se escribe la tesis: «base teórica», «antecedentes», «variables»,
«hipótesis», «operacionalización», «síntesis y brecha», «técnica del embudo», «extensión», «citar»…
Si los mensajes no dicen de qué trata su investigación, devuelve `tema` vacío. No inventes ni completes."""


def _tema_del_hilo(mensaje: str, historial: list[dict] | None, modelo) -> str:
    """El tema de la tesis según lo que contó el estudiante, o "" si no lo dijo.

    Antes se le pasaban al estratega sus últimos mensajes tal cual, y cuando eran
    preguntas («¿cómo redacto la base teórica?») las cadenas de búsqueda salían
    con «base teórica, redacción, consideraciones» como si fueran sus variables.
    """
    from .ideacion import _invocar

    mensajes = [
        (t.get("contenido") or "").strip()[:600]
        for t in (historial or []) if t.get("rol") == "user"
    ] + [(mensaje or "").strip()[:600]]
    mensajes = [m for m in mensajes if m][-10:]
    if not mensajes:
        return ""
    salida = _invocar(
        _PROMPT_TEMA.format(mensajes="\n".join(f"- {m}" for m in mensajes)),
        modelo, SalidaTema, "¿De qué trata su investigación?",
    )
    return (salida.tema or "").strip() if salida else ""


def _pedir_tema(foco: str) -> str:
    if foco == "marco":
        que, como = "las fuentes de tu base teórica", "se redacta la base teórica"
    else:
        que = f"tus antecedentes (los {ANTECEDENTES_RECOMENDADOS}, de preferencia internacionales)"
        como = "se redactan los antecedentes"
    return (
        f"Para prepararte la búsqueda de {que} necesito saber de qué trata tu tesis, y en lo que me "
        "has escrito no lo encuentro. Pégame tu **título** —o dime qué vas a construir o aplicar, qué "
        "vas a medir y dónde— y te armo los términos en español e inglés y las cadenas listas para "
        "pegar en Scopus y SciELO.\n\n"
        f"Si lo que quieres es saber **cómo se redacta** esa parte, pregúntamelo así («¿cómo {como}?») "
        "y te lo explico paso a paso."
    )


def responder_antecedentes(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Estrategia de búsqueda, plan de antecedentes y mapa del marco teórico."""
    from .ideacion import _invocar, _libros
    from .intent import parte_pedido
    from .planteamiento import _cadena_redactada, _titulo_del_hilo

    pedido = parte_pedido(mensaje)
    foco = _foco(pedido)
    # «Mi título es: …» en respuesta a «pégame tu título»: el foco es el del pedido
    # original (antecedentes o base teórica), que está en un mensaje anterior.
    if not (_RE_FOCO_MARCO.search(pedido) or _RE_FOCO_ANTECEDENTES.search(pedido)):
        previo = next((
            (t.get("contenido") or "") for t in reversed(historial or [])
            if t.get("rol") == "user"
            and (_RE_FOCO_MARCO.search(t.get("contenido") or "")
                 or _RE_FOCO_ANTECEDENTES.search(t.get("contenido") or ""))
        ), "")
        if previo:
            foco = _foco(previo)
    modelo = llm_rapido(temperatura=0.25)

    # El proyecto sale de su título, de lo que ya escribió o de lo que contó de su
    # tema; NUNCA de sus preguntas. Sin nada de eso, se le pide el tema.
    titulo = _titulo_del_hilo(mensaje, historial, doc)
    escrito = _cadena_redactada(doc, max_chars=2500) if doc is not None else ""
    tema = "" if (titulo or escrito) else _tema_del_hilo(mensaje, historial, modelo)
    if not (titulo or escrito or tema):
        logger.info("[antecedentes] Sin título ni tema identificable → se pide el tema")
        return {"respuesta": _pedir_tema(foco), "titulo": "", "seccion": None}
    proyecto = "\n".join(p for p in (
        f"TÍTULO: {titulo}" if titulo else "",
        f"LO QUE YA ESCRIBIÓ:\n{escrito}" if escrito else "",
        f"TEMA (según lo que contó el estudiante): {tema}" if tema else "",
    ) if p)

    libros_txt, fuentes = _libros(
        biblioteca,
        "antecedentes investigaciones previas revisión de literatura marco teórico bases teóricas "
        "definición de términos búsqueda bibliográfica criterios de inclusión",
    )
    base = {
        "regla_voz": _REGLA_VOZ,
        "regla_no_inventar": _REGLA_NO_INVENTAR_FUENTES,
        "proyecto": proyecto,
        "libros": libros_txt or "(sin fragmentos disponibles)",
    }

    # Con foco en la base teórica sobran la búsqueda de antecedentes y su reparto.
    e = p = None
    if foco == "antecedentes":
        e = _invocar(
            _PROMPT_ESTRATEGIA.format(**base), modelo, SalidaEstrategia,
            "Arma la estrategia de búsqueda bibliográfica de este proyecto.",
        )
        p = _invocar(
            _PROMPT_PLAN.format(
                regla_voz=_REGLA_VOZ, regla_no_inventar=_REGLA_NO_INVENTAR_FUENTES,
                proyecto=proyecto, n=ANTECEDENTES_RECOMENDADOS,
            ),
            modelo, SalidaPlanAntecedentes,
            "Planifica los antecedentes: de preferencia internacionales; nacional y local, opcionales.",
        )
    m = _invocar(
        _PROMPT_MARCO.format(**base), modelo, SalidaMarcoTeorico,
        "Ordena los constructos del marco teórico de este proyecto.",
    )

    respuesta = _componer(
        e.model_dump() if e else {}, p.model_dump() if p else {},
        m.model_dump() if m else {}, pedido, fuentes, foco=foco,
    )
    if not respuesta:
        return {"respuesta": _FALLBACK, "titulo": "", "seccion": None}

    # Última barrera: ninguna cita con forma de APA sale de aquí.
    respuesta, inventadas = _limpiar_citas(respuesta)
    if inventadas:
        respuesta += (
            "\n\n> ⚠️ Detecté que se me había colado alguna referencia con forma de cita y la "
            "sustituí por un marcador. No uses ninguna cita que no hayas verificado tú en la "
            "base de datos."
        )

    logger.info(
        f"[antecedentes] {len(e.terminos_en) if e else 0} términos EN, "
        f"{len(e.cadenas) if e else 0} cadenas, "
        f"{len(m.orden) if m else 0} constructos, {len(inventadas)} citas limpiadas"
    )
    return {"respuesta": respuesta, "titulo": titulo, "seccion": None}
