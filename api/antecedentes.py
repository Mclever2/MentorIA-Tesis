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
  2. PLANIFICADOR DE ANTECEDENTES — el reparto de los 8 más relevantes y la
     estructura de cada uno, con la plantilla en prosa APA 7 lista para rellenar.
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
        description="Qué hacer si un ámbito viene vacío. Deja claro que no es obligatorio que existan "
                    "antecedentes nacionales o locales, y cómo se justifica esa ausencia por escrito."
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
  4ª — ámbito nacional/regional: términos EN ESPAÑOL y el país, para ALICIA, RENATI o SciELO.
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

Se recomienda reunir {n} antecedentes, los MÁS RELEVANTES —no los primeros que aparezcan—, repartidos
entre lo internacional, lo nacional y lo local.

REGLA SOBRE LA COBERTURA: no es obligatorio que existan antecedentes nacionales ni locales. En temas
muy nuevos o muy específicos puede no haberlos, y forzarlos lleva a citar trabajos que no vienen a
cuento, lo que el jurado detecta enseguida. Si un ámbito viene vacío, se declara por escrito («no se
hallaron estudios nacionales que cruzaran ambas variables en el periodo revisado») y se compensa con
más peso en el ámbito que sí tiene literatura. Sé honesto sobre qué ámbito es probable que esté vacío
en ESTE tema.

Reparte los {n} con criterio y di, para cada ámbito, dónde buscar EN CONCRETO. Nombra las fuentes,
no las describas: «repositorios de universidades peruanas» no le sirve de nada, «RENATI» sí.

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

def _componer(est: dict, plan: dict, marco: dict, pedido: str, fuentes: list[str]) -> str:
    partes: list[str] = []

    partes.append(
        "## Por qué no te los redacto\n\n"
        "Un antecedente es un estudio real, con su autor, su muestra y sus resultados. Si te los "
        "escribo yo, salen referencias que suenan perfectas y no existen — y eso en tu sustentación "
        "no es un error de forma: es falta académica, y se descubre en cuanto el jurado pide el DOI. "
        "Lo que sí puedo hacer es dejarte la búsqueda hecha y la estructura lista, para que los "
        "escribas tú con estudios que sí existen."
    )

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
        filas = [
            f"## Cómo repartir los {ANTECEDENTES_RECOMENDADOS}",
            "",
            f"Se recomiendan {ANTECEDENTES_RECOMENDADOS}, los **más relevantes** — no los primeros "
            "que aparezcan.",
            "",
        ]
        for b in plan["reparto"]:
            filas.append(
                f"**{b.get('ambito','').capitalize()} — {b.get('cuantos','')}**\n\n"
                f"- *Dónde:* {', '.join(b.get('donde_buscar') or [])}\n"
                f"- *Qué esperar:* {b.get('que_esperar','')}"
            )
        if plan.get("nota_cobertura"):
            filas.append(f"\n{plan['nota_cobertura']}")
        partes.append("\n".join(filas))

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

def responder_antecedentes(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Estrategia de búsqueda, plan de antecedentes y mapa del marco teórico."""
    from .ideacion import _interes_del_hilo, _invocar, _libros
    from .planteamiento import _titulo_del_hilo

    contexto = _interes_del_hilo(mensaje, historial)
    titulo = _titulo_del_hilo(mensaje, historial, doc)
    proyecto = "\n".join(p for p in (f"TÍTULO: {titulo}" if titulo else "", contexto) if p)
    proyecto = proyecto or "(el estudiante aún no ha descrito su proyecto)"

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
    modelo = llm_rapido(temperatura=0.25)

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
        "Reparte los antecedentes entre internacional, nacional y local.",
    )
    m = _invocar(
        _PROMPT_MARCO.format(**base), modelo, SalidaMarcoTeorico,
        "Ordena los constructos del marco teórico de este proyecto.",
    )

    respuesta = _componer(
        e.model_dump() if e else {}, p.model_dump() if p else {},
        m.model_dump() if m else {}, mensaje, fuentes,
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
