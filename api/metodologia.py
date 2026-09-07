"""
Panel de OPERACIONALIZACIÓN, MATRIZ DE CONSISTENCIA y MARCO METODOLÓGICO.

Es el tramo que decide si Tesis 1 se puede cerrar: aquí se fija qué se mide, con
qué instrumento y sobre quién. Los errores de este capítulo no se ven hasta que
el estudiante intenta recoger datos y descubre que su indicador no se puede
medir o que su instrumento necesita tres meses de validación.

Lo que gobierna el módulo:

  · LA CADENA MANDA. Las variables salen del TÍTULO, no de la imaginación: lo
    primero que hace el panel es leer el título y comprobar si la independiente
    y la dependiente están bien identificadas ahí. Si el título no las deja ver,
    ese es el hallazgo, y se dice antes de operacionalizar nada.
  · NO SE INVENTA LO QUE FALTA. Si le piden los objetivos específicos sin haber
    dado las preguntas específicas ni el título, el panel PIDE el contexto en
    vez de rellenarlo. Es la diferencia entre un asesor y un generador de texto.
  · PARSIMONIA CON COSTO EXPLÍCITO. Cada indicador arrastra un instrumento y
    cada instrumento con personas arrastra juicio de expertos y confiabilidad.
    Las métricas que calcula el propio sistema no: eso se separa de forma
    determinista en `backend.metodologia_reglas`.
  · LA MUESTRA SE CALCULA. Con la fórmula de población finita, 95 % de confianza
    y como máximo 10 % de error; el panel no estima un número «razonable».

Estructura y columnas según la Tabla 9 de «Metodología de la Investigación —
Guía para el Proyecto de Tesis» (libro indexado) y lo observado en los 11
proyectos REP_ISIA aprobados de la escuela.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from backend.metodologia_reglas import (
    COLUMNAS_MATRIZ,
    COLUMNAS_OPERACIONALIZACION,
    MARGEN_ERROR_MAXIMO,
    bloque_validacion,
    requiere_validacion_experta,
    tamano_muestra,
    verificar_matriz,
)
from .llm import llm_rapido

logger = logging.getLogger(__name__)

_FALLBACK = "No pude preparar esta parte ahora mismo. Vuelve a pedírmelo en unos segundos."


# ── Contexto mínimo: qué hace falta para poder responder sin inventar ───────

_REQUISITOS = {
    "operacionalizacion": ("el título o las variables", ("titulo", "variables")),
    "matriz":             ("el título, las preguntas y los objetivos", ("titulo", "preguntas", "objetivos")),
    "objetivos":          ("el título y tus preguntas específicas", ("titulo", "preguntas")),
    "poblacion":          ("a quién o a qué vas a medir", ("poblacion",)),
    "metodologico":       ("el título y los objetivos", ("titulo", "objetivos")),
}

_SENALES = {
    "titulo":    re.compile(r"t[ií]tulo|para (mejorar|optimizar|reducir|aumentar|disminuir)", re.I),
    "variables": re.compile(r"variable|independiente|dependiente|indicador", re.I),
    "preguntas": re.compile(r"[¿?]|pregunta", re.I),
    "objetivos": re.compile(r"objetivo|determinar|identificar|evaluar|analizar|implementar", re.I),
    "poblacion": re.compile(r"poblaci[oó]n|muestra|usuarios?|empleados?|registros?|equipos?|N\s*=", re.I),
}


def contexto_disponible(texto: str) -> set[str]:
    """Qué piezas del proyecto se pueden leer en lo que el estudiante ha dado."""
    return {clave for clave, rx in _SENALES.items() if rx.search(texto or "")}


def falta_contexto(tarea: str, texto: str) -> tuple[bool, str]:
    """¿Se puede responder esta tarea sin inventar? Devuelve (falta, qué falta)."""
    descripcion, requeridas = _REQUISITOS.get(tarea, ("", ()))
    if not requeridas:
        return False, ""
    disponibles = contexto_disponible(texto)
    if any(r in disponibles for r in requeridas):
        return False, ""
    return True, descripcion


# ── Contratos ───────────────────────────────────────────────────────────────

class LecturaTitulo(BaseModel):
    variable_independiente: str = Field(description="La VI tal como se lee EN EL TÍTULO.")
    variable_dependiente: str = Field(description="La VD tal como se lee EN EL TÍTULO.")
    bien_identificadas: bool = Field(
        description="False si el título no deja ver con claridad cuál es cada una."
    )
    problema_detectado: str = Field(
        default="",
        description="Si no están claras, qué falla: el título no dice qué se mide, confunde el medio "
                    "con el fin, o nombra dos dependientes. Vacío si está bien.",
    )
    correccion_titulo: str = Field(
        default="",
        description="Si hay problema, cómo debería quedar el título para que las variables se lean. "
                    "Vacío si está bien.",
    )


class FilaOperacionalizacion(BaseModel):
    variable: str
    tipo: Literal["independiente", "dependiente"]
    definicion_conceptual: str = Field(
        description="QUÉ ES la variable, según la teoría. DEBE ir con su cita: (Apellido, año). Si no "
                    "tienes la fuente real, escribe [cita pendiente: busca la definición de este "
                    "concepto] — nunca inventes el autor."
    )
    definicion_operacional: str = Field(
        description="CÓMO se va a medir: el procedimiento concreto. También se cita cuando se toma de "
                    "un autor; si es propia del estudio, se dice que es de elaboración propia."
    )
    dimensiones: list[str] = Field(
        description="Las facetas en que la teoría descompone la variable. SALEN DE LA DEFINICIÓN "
                    "CONCEPTUAL, no se inventan. Si la variable es simple, una sola dimensión."
    )
    indicadores: list[str] = Field(
        description="Lo observable y medible de cada dimensión, CON SU UNIDAD. Salen de la definición "
                    "operacional. Pocos y medibles."
    )
    escala: str = Field(description="Escala de medición: nominal, ordinal, de intervalo o de razón.")
    instrumento: str = Field(description="Con qué se recoge cada indicador.")


class SalidaOperacionalizacion(BaseModel):
    lectura: LecturaTitulo
    filas: list[FilaOperacionalizacion] = Field(
        description="Una fila para la VI y una para la VD. Van en TABLAS SEPARADAS."
    )
    advertencia_alcance: str = Field(
        default="",
        description="Si el número de indicadores obliga a muchos instrumentos, dilo aquí con el "
                    "costo concreto en validación. Vacío si el diseño es parsimonioso.",
    )


class FaseProcedimiento(BaseModel):
    fase: str = Field(description="Nombre de la fase.")
    objetivos_que_cubre: list[str] = Field(
        description="Qué objetivos específicos avanza esta fase. Pueden ser varios, y un objetivo "
                    "puede repartirse entre varias fases: no fuerces una fase por objetivo."
    )
    actividades: str = Field(description="Qué se hace en la fase, en concreto.")
    entregable: str = Field(description="Qué queda al terminarla, verificable.")


class SalidaMetodologico(BaseModel):
    tipo_investigacion: str = Field(
        description="Según finalidad (básica/aplicada), técnica de contrastación (preexperimental, "
                    "cuasiexperimental, experimental puro, descriptiva, correlacional) y nivel."
    )
    enfoque: str = Field(description="Cuantitativo, cualitativo o mixto, y por qué ese.")
    diseno: str = Field(description="Diseño y su esquema (p. ej. G.E.: O1 X O2 / G.C.: O3 - O4).")
    unidad_analisis: str = Field(description="A quién o a qué se mide. Es lo que define la población.")
    criterio_poblacion: str = Field(
        description="Cómo se delimita la población SEGÚN EL DISEÑO elegido, y si conviene censo o muestreo."
    )
    fases: list[FaseProcedimiento] = Field(description="Procedimiento de ejecución por fases.")
    tecnicas_recoleccion: list[str] = Field(description="Técnicas e instrumentos, emparejados a cada indicador.")
    tecnicas_procesamiento: list[str] = Field(
        description="Estadística que corresponde al diseño y a la escala: descriptiva, prueba de "
                    "normalidad, y la prueba de hipótesis que toca (t de Student pareada, Wilcoxon, "
                    "U de Mann-Whitney, ANOVA…), con el porqué."
    )


# ── Prompts ─────────────────────────────────────────────────────────────────

_REGLA_VOZ = """\
CÓMO ESCRIBES: le hablas al estudiante de TÚ. Nunca «el estudiante…» ni «el usuario…»."""

_REGLA_NO_INVENTAR = """\
NO INVENTES LO QUE NO TE HAN DADO. Ni citas, ni cifras, ni nombres de empresas, ni población, ni
resultados. Si para lo que te piden falta una pieza del proyecto (el título, las preguntas
específicas, la población), PÍDELA en vez de rellenarla: un objetivo específico deducido de la nada
desalinea toda la cadena y el estudiante ni se entera.
Para las citas que no tengas: [cita pendiente: qué concepto buscar]. Nunca un autor plausible."""

_PROMPT_OPERACIONALIZACION = """\
Eres el especialista en OPERACIONALIZACIÓN DE VARIABLES del panel.

{regla_voz}

{regla_no_inventar}

PROYECTO DEL ESTUDIANTE:
{proyecto}

FUNDAMENTO METODOLÓGICO (libros indexados — apóyate en ellos y cítalos por su título):
{libros}

PRIMERO, LEE EL TÍTULO. Las variables se sacan del título, no se inventan: la independiente es lo que
se construye o manipula (la tecnología, el artefacto) y la dependiente es lo que se mide para saber
si mejoró. Comprueba si el título las deja ver:
  · Si el título dice «para mejorar la gestión», la dependiente NO está bien: «gestión» no se mide.
    Debe apuntar a algo con unidad (tiempo, tasa de error, exactitud).
  · Si el título nombra dos cosas que se miden, hay dos dependientes y eso multiplica el trabajo.
  · Si el medio y el fin están confundidos, dilo.
Si las variables no se leen bien, ESE es el primer hallazgo y hay que corregir el título antes de
seguir: operacionalizar sobre un título ambiguo produce una tabla que no defiende nada.

LAS COLUMNAS son estas y en este orden: {columnas}.

DE DÓNDE SALE CADA COSA (esto lo dicen los libros, no es criterio tuyo):
  · La DEFINICIÓN CONCEPTUAL dice QUÉ ES la variable, según la teoría, y VA CITADA.
  · Las DIMENSIONES salen de la definición conceptual: son las facetas en que la teoría descompone el
    concepto. «Las dimensiones e indicadores son formuladas bajo una revisión exhaustiva de la teoría;
    no deben redactarse de forma deliberada.» Si la teoría no descompone la variable, es simple: una
    sola dimensión, y se dice.
  · La DEFINICIÓN OPERACIONAL dice CÓMO se medirá, y de ella salen los INDICADORES, que son lo
    observable y medible. También se cita cuando se toma de un autor.
  · La VARIABLE INDEPENDIENTE no se mide, pero sí aparece en la tabla: su indicador suele ser su
    presencia/ausencia, en escala nominal.

{bloque_validacion}

Devuelve una fila para la VI y otra para la VD: van en TABLAS SEPARADAS, que es lo recomendado."""

_PROMPT_METODOLOGICO = """\
Eres el especialista en MARCO METODOLÓGICO del panel.

{regla_voz}

{regla_no_inventar}

PROYECTO DEL ESTUDIANTE:
{proyecto}

FUNDAMENTO METODOLÓGICO (libros indexados — de aquí sacas las técnicas, no de tu memoria):
{libros}

REGLAS QUE APLICAS:

1. ENFOQUE. Para Ingeniería, cuantitativo o mixto por encima de cualitativo: son los que permiten
   demostrar mejora con una medición comparable. Un componente cualitativo puede acompañar para
   caracterizar requisitos, pero el peso demostrativo tiene que ser cuantitativo.

2. POBLACIÓN SEGÚN EL DISEÑO. La población no es «los usuarios» a secas: depende de qué diseño se
   eligió y de cuál es la unidad de análisis.
   · Preexperimental (un solo grupo, antes y después): la población son las unidades sobre las que se
     mide el indicador — pueden ser personas, pero también registros, equipos, transacciones o
     sesiones. Si la unidad de análisis es un registro, la población son los registros, no la gente.
   · Cuasiexperimental (grupo experimental y de control sin asignación aleatoria): hacen falta dos
     grupos comparables y hay que decir en qué se parecen.
   · Experimental puro: exige asignación aleatoria; en un contexto organizacional casi nunca es
     viable, y prometerlo sin poder cumplirlo es un problema. Dilo si es el caso.

3. PROCEDIMIENTO POR FASES ALINEADAS A LOS OBJETIVOS. Las fases se derivan de los objetivos
   específicos, pero NO es uno por fase: una fase puede cubrir varios objetivos y un objetivo puede
   repartirse entre varias fases. Lo que no puede haber es un objetivo que ninguna fase avance, ni
   una fase que no sirva a ningún objetivo.

4. TÉCNICAS DE RECOLECCIÓN. Empareja cada indicador con su técnica e instrumento, apoyándote en los
   libros. Si el indicador lo calcula el sistema, el «instrumento» es la ficha de registro con el
   procedimiento de medición, no un cuestionario.

5. TÉCNICAS DE PROCESAMIENTO. Se derivan del diseño y de la escala, no se eligen por costumbre:
   estadística descriptiva primero; prueba de normalidad (Shapiro-Wilk con muestras pequeñas) para
   decidir entre paramétrica y no paramétrica; y la prueba que corresponda al diseño — dos medidas del
   mismo grupo piden t de Student pareada o Wilcoxon; dos grupos independientes piden t independiente
   o U de Mann-Whitney. Di el porqué de cada elección."""


# ── Composición ─────────────────────────────────────────────────────────────

def _tabla(fila: dict) -> str:
    dims = "; ".join(fila.get("dimensiones") or []) or "—"
    inds = "; ".join(fila.get("indicadores") or []) or "—"
    return (
        f"| Campo | Contenido |\n|---|---|\n"
        f"| **Variable** | {fila.get('variable','')} |\n"
        f"| **Definición conceptual** | {fila.get('definicion_conceptual','')} |\n"
        f"| **Definición operacional** | {fila.get('definicion_operacional','')} |\n"
        f"| **Dimensiones** | {dims} |\n"
        f"| **Indicadores** | {inds} |\n"
        f"| **Escala de medición** | {fila.get('escala','')} |\n"
        f"| **Instrumento** | {fila.get('instrumento','')} |"
    )


def _bloque_validacion_por_indicador(filas: list[dict]) -> str:
    """Separa, indicador a indicador, lo que necesita juicio de expertos."""
    con, sin = [], []
    for f in filas:
        inst = f.get("instrumento", "")
        for ind in (f.get("indicadores") or []):
            (con if requiere_validacion_experta(ind, inst) else sin).append(f"{ind} ({inst})")
    partes = ["## Qué tendrás que validar y qué no", ""]
    if sin:
        partes.append(
            "**No necesitan juicio de expertos** — los calcula el propio sistema y su validez está en "
            "su definición matemática. Lo que sí documentas es el procedimiento de medición (misma "
            "máquina, mismas condiciones, mismo periodo):\n"
            + "\n".join(f"- {x}" for x in sin)
        )
    if con:
        partes.append(
            "**Sí necesitan validación** — recogen el juicio o la percepción de una persona, así que "
            "hay que demostrar que miden lo que dicen medir: juicio de 3 a 5 expertos con su ficha de "
            "validación, y alfa de Cronbach si es una escala:\n"
            + "\n".join(f"- {x}" for x in con)
            + "\n\nAntes de construir uno tuyo, busca en la literatura un instrumento **ya validado** "
            "para ese constructo: si lo encuentras, lo citas y te ahorras el proceso entero."
        )
    if not con:
        partes.append(
            "Ninguno de tus indicadores necesita panel de expertos. Eso es una ventaja real de "
            "tiempo: aprovéchala y no montes un cuestionario que no te piden."
        )
    return "\n\n".join(partes)


def _componer_operacionalizacion(datos: dict, fuentes: list[str]) -> str:
    partes: list[str] = []
    lec = datos.get("lectura") or {}

    if lec:
        bloque = ["## Lo que dice tu título", ""]
        bloque.append(f"- **Variable independiente:** {lec.get('variable_independiente','')}")
        bloque.append(f"- **Variable dependiente:** {lec.get('variable_dependiente','')}")
        if not lec.get("bien_identificadas", True):
            bloque.append(
                f"\n⚠️ **Las variables no se leen bien en tu título.** {lec.get('problema_detectado','')}"
            )
            if lec.get("correccion_titulo"):
                bloque.append(
                    f"\n*Cómo debería quedar:* «{lec['correccion_titulo']}»\n\n"
                    "Corrige el título antes de operacionalizar: una tabla construida sobre un título "
                    "ambiguo no defiende nada, y tendrás que rehacerla."
                )
        partes.append("\n".join(bloque))

    filas = datos.get("filas") or []
    for f in filas:
        titulo = "independiente" if f.get("tipo") == "independiente" else "dependiente"
        partes.append(f"## Operacionalización de la variable {titulo}\n\n{_tabla(f)}")

    if filas:
        partes.append(
            "Van en **dos tablas separadas** — es lo recomendado. Fundirlas en una no invalida el "
            "trabajo, pero separadas se lee mejor cuál es el rol de cada variable. De los 11 "
            "proyectos aprobados de tu escuela que revisé, los 11 usan una sola tabla: no es un "
            "error, pero separarlas te distingue."
        )
        partes.append(_bloque_validacion_por_indicador(filas))

    if datos.get("advertencia_alcance"):
        partes.append(f"## Sobre el alcance que estás asumiendo\n\n{datos['advertencia_alcance']}")

    if fuentes:
        plural = "libros" if len(fuentes) > 1 else "libro"
        partes.append(f"---\n\n_Consulté {len(fuentes)} {plural} de metodología: {', '.join(fuentes)}._")
    return "\n\n".join(partes).strip()


def _componer_metodologico(d: dict, muestra: dict | None, fuentes: list[str]) -> str:
    partes = [
        "## Tipo, enfoque y diseño",
        f"- **Tipo de investigación:** {d.get('tipo_investigacion','')}\n"
        f"- **Enfoque:** {d.get('enfoque','')}\n"
        f"- **Diseño:** {d.get('diseno','')}",
        "## Población y muestra",
        f"- **Unidad de análisis:** {d.get('unidad_analisis','')}\n"
        f"- **Cómo se delimita:** {d.get('criterio_poblacion','')}",
    ]

    if muestra:
        partes.append(
            "### Cálculo del tamaño de muestra\n\n"
            f"Población (N) = **{muestra['poblacion']}** · Confianza = **{muestra['confianza']:.0f} %** "
            f"(z = {muestra['z']}) · Margen de error = **{muestra['margen_error']:.0f} %** · p = q = 0.5\n\n"
            f"```\n{muestra['formula']}\n{muestra['sustitucion']}\n```\n\n"
            f"**Muestra = {muestra['muestra']}**"
            + (
                "\n\n> Con una población tan pequeña conviene trabajar con **censo** (medir a todos) "
                "en vez de muestrear: te ahorras justificar el muestreo y ganas potencia estadística."
                if muestra.get("censo_recomendado") else ""
            )
        )
    else:
        partes.append(
            f"### Cálculo del tamaño de muestra\n\n"
            f"Dime **cuántas unidades tiene tu población** (personas, registros, equipos… lo que sea "
            f"tu unidad de análisis) y te lo calculo con la fórmula de población finita: 95 % de "
            f"confianza y un margen de error de 5 %, que es el estándar. El máximo admisible es "
            f"{MARGEN_ERROR_MAXIMO:.0f} %; por encima de eso la muestra deja de representar."
        )

    if d.get("fases"):
        filas = [
            "## Procedimiento de ejecución",
            "",
            "Las fases se alinean a tus objetivos específicos, pero no una por una: una fase puede "
            "cubrir varios objetivos y un objetivo puede repartirse entre fases. Lo que no puede "
            "haber es un objetivo que ninguna fase avance.",
            "",
        ]
        for i, f in enumerate(d["fases"], 1):
            filas.append(
                f"**Fase {i} — {f.get('fase','')}**\n\n"
                f"- *Objetivos que avanza:* {', '.join(f.get('objetivos_que_cubre') or []) or '—'}\n"
                f"- *Actividades:* {f.get('actividades','')}\n"
                f"- *Entregable:* {f.get('entregable','')}"
            )
        partes.append("\n".join(filas))

    if d.get("tecnicas_recoleccion"):
        partes.append(
            "## Técnicas e instrumentos de recolección\n\n"
            + "\n".join(f"- {t}" for t in d["tecnicas_recoleccion"])
        )
    if d.get("tecnicas_procesamiento"):
        partes.append(
            "## Técnicas de procesamiento y análisis\n\n"
            + "\n".join(f"- {t}" for t in d["tecnicas_procesamiento"])
        )

    if fuentes:
        plural = "libros" if len(fuentes) > 1 else "libro"
        partes.append(f"---\n\n_Consulté {len(fuentes)} {plural} de metodología: {', '.join(fuentes)}._")
    return "\n\n".join(partes).strip()


# ── Matriz de consistencia ──────────────────────────────────────────────────

_RE_ENUMERADO = re.compile(r"^\s*(?:\d+[.)]|[-*•]|[a-z][.)])\s+", re.M)


def _contar_elementos(texto: str, marcador: re.Pattern) -> list[str]:
    """Extrae los elementos enumerados que siguen a un rótulo del proyecto."""
    m = marcador.search(texto or "")
    if not m:
        return []
    resto = texto[m.end(): m.end() + 1800]
    corte = re.search(r"\n\s*(?:problemas?|preguntas?|hip[oó]tesis|objetivos?|variables?|metodolog|poblaci)", resto, re.I)
    if corte:
        resto = resto[: corte.start()]
    return [l.strip() for l in _RE_ENUMERADO.split(resto) if len(l.strip()) > 15]


def _componer_matriz(proyecto: str) -> str:
    """La matriz solo coloca lo ya definido: si algo falta, ese ES el hallazgo."""
    preguntas = _contar_elementos(proyecto, re.compile(r"problemas?\s+espec[ií]fic|preguntas?\s+espec[ií]fic", re.I))
    objetivos = _contar_elementos(proyecto, re.compile(r"objetivos?\s+espec[ií]fic", re.I))
    hipotesis = _contar_elementos(proyecto, re.compile(r"hip[oó]tesis\s+espec[ií]fic", re.I))
    exige = not re.search(r"cualitativ", proyecto or "", re.I)

    hallazgos = verificar_matriz(preguntas, objetivos, hipotesis, exige_hipotesis=exige)

    partes = [
        "## Matriz de consistencia",
        "",
        "La matriz **no introduce contenido nuevo**: coloca lo que ya definiste y demuestra que "
        "encaja. Por eso, si al armarla te falta rellenar una celda, el problema no es la tabla — es "
        "que la sección de donde sale esa celda está incompleta.",
        "",
        "**Columnas:** " + " · ".join(COLUMNAS_MATRIZ),
        "",
        f"Detecté en tu proyecto: **{len(preguntas)}** problema(s) específico(s), "
        f"**{len(objetivos)}** objetivo(s) específico(s) y **{len(hipotesis)}** hipótesis específica(s).",
    ]
    if hallazgos:
        partes.append(
            "### Lo que hay que cerrar antes de armarla\n\n"
            + "\n".join(f"- {h}" for h in hallazgos)
        )
    else:
        partes.append(
            "### Cuadra\n\nLos tres bloques tienen el mismo número de elementos, así que la matriz "
            "se puede armar fila a fila: cada problema específico con su objetivo, su hipótesis, la "
            "variable que toca y sus indicadores, en el mismo orden en que los redactaste. Revisa "
            "solo que el orden se respete: una fila cruzada es el error que más se ve."
        )
    partes.append(
        "> Si tu enfoque no exige hipótesis (cualitativo), esa columna se omite y se declara por qué, "
        "en vez de dejarla vacía."
    )
    return "\n\n".join(partes)


# ── Detección de la población en el mensaje ─────────────────────────────────

_RE_POBLACION = re.compile(
    r"(?:poblaci[oó]n\s+(?:de\s+|es\s+de\s+|:\s*)?|N\s*=\s*|son\s+|hay\s+|tengo\s+|de\s+)"
    r"(\d{1,7})\s*"
    r"(?:personas?|usuarios?|empleados?|trabajadores?|estudiantes?|registros?|equipos?|"
    r"transacciones|documentos?|clientes?|m[aá]quinas?|sesiones?|casos?)?",
    re.I,
)


def _poblacion_declarada(texto: str) -> int | None:
    m = _RE_POBLACION.search(texto or "")
    if not m:
        return None
    try:
        n = int(m.group(1))
    except (TypeError, ValueError):
        return None
    return n if 1 < n <= 5_000_000 else None


# ── Entrada pública ─────────────────────────────────────────────────────────

def responder_metodologia(mensaje: str, historial: list[dict], doc, biblioteca) -> dict:
    """Operacionalización, matriz de consistencia o marco metodológico."""
    from .ideacion import _interes_del_hilo, _invocar, _libros
    from .planteamiento import _titulo_del_hilo

    contexto = _interes_del_hilo(mensaje, historial)
    titulo = _titulo_del_hilo(mensaje, historial, doc)
    proyecto = "\n".join(p for p in (f"TÍTULO: {titulo}" if titulo else "", contexto) if p)

    quiere_matriz = bool(re.search(r"matriz de consistencia", mensaje, re.I))
    quiere_metodologico = bool(re.search(
        r"metodol[oó]gic|poblaci[oó]n|muestra|dise[ñn]o|procedimiento|"
        r"t[eé]cnicas?\s+de\s+(recolecci|procesamiento)|instrumento",
        mensaje, re.I,
    ))
    tarea = "matriz" if quiere_matriz else ("metodologico" if quiere_metodologico else "operacionalizacion")

    falta, que_falta = falta_contexto(tarea, proyecto)
    if falta:
        # Pedir en vez de inventar: es lo que separa a un asesor de un generador.
        return {
            "respuesta": (
                f"Para esto necesito {que_falta}. Sin eso tendría que inventármelo, y un "
                "eslabón inventado aquí desalinea toda tu cadena sin que lo notes hasta la "
                "sustentación.\n\nPégame lo que ya tengas —aunque esté a medias— y seguimos."
            ),
            "titulo": titulo, "seccion": None,
        }

    libros_txt, fuentes = _libros(
        biblioteca,
        "operacionalización de variables definición conceptual operacional dimensiones indicadores "
        "escala de medición población y muestra diseño de investigación técnicas e instrumentos de "
        "recolección procesamiento y análisis de datos prueba de hipótesis",
    )
    modelo = llm_rapido(temperatura=0.25)
    base = {
        "regla_voz": _REGLA_VOZ, "regla_no_inventar": _REGLA_NO_INVENTAR,
        "proyecto": proyecto or "(sin contexto)", "libros": libros_txt or "(sin fragmentos)",
    }

    if tarea == "matriz":
        respuesta = _componer_matriz(proyecto)
        logger.info("[metodologia] Matriz de consistencia")
    elif tarea == "metodologico":
        d = _invocar(
            _PROMPT_METODOLOGICO.format(**base), modelo, SalidaMetodologico,
            "Arma el marco metodológico de este proyecto.",
        )
        if d is None:
            return {"respuesta": _FALLBACK, "titulo": titulo, "seccion": None}
        n = _poblacion_declarada(proyecto)
        muestra = None
        if n:
            try:
                muestra = tamano_muestra(n)
            except ValueError as exc:                          # noqa: BLE001
                logger.warning(f"[metodologia] Cálculo muestral no aplicable: {exc}")
        respuesta = _componer_metodologico(d.model_dump(), muestra, fuentes)
        logger.info(f"[metodologia] Marco metodológico | población detectada: {n}")
    else:
        o = _invocar(
            _PROMPT_OPERACIONALIZACION.format(
                **base, columnas=" · ".join(COLUMNAS_OPERACIONALIZACION),
                bloque_validacion=bloque_validacion(),
            ),
            modelo, SalidaOperacionalizacion,
            "Lee el título, verifica las variables y opera­cionalízalas.",
        )
        if o is None:
            return {"respuesta": _FALLBACK, "titulo": titulo, "seccion": None}
        respuesta = _componer_operacionalizacion(o.model_dump(), fuentes)
        logger.info(
            f"[metodologia] Operacionalización | variables bien identificadas: "
            f"{o.lectura.bien_identificadas}"
        )

    # Ninguna cita inventada sale de aquí (mismo guardia que en antecedentes).
    from .antecedentes import _limpiar_citas

    respuesta, inventadas = _limpiar_citas(respuesta)
    if inventadas:
        respuesta += (
            "\n\n> ⚠️ Sustituí por marcadores algunas referencias que se me colaron. Las "
            "definiciones conceptuales tienes que citarlas con fuentes que verifiques tú."
        )
    return {"respuesta": respuesta, "titulo": titulo, "seccion": None}
