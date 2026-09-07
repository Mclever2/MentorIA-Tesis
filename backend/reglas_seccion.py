"""
Reglas de dominio POR SECCIÓN, compartidas por el grafo evaluador y los paneles.

Existe porque los paneles de asesoría (ideación, planteamiento, antecedentes,
metodología) acumularon reglas que el grafo evaluador no conocía. Eso produce la
peor contradicción posible para el estudiante: el panel le dice que no se
inventan citas y que un título no pasa de 20 palabras, y luego el redactor de la
red le reescribe los antecedentes con referencias inventadas y un título de 24.

Aquí vive una sola versión de cada regla. El redactor la recibe para no romperla
al reescribir, y el auditor para no exigir lo contrario al calificar.

La regla más importante es la de antecedentes: el redactor REESCRIBE secciones, y
si le toca el marco teórico producirá referencias verosímiles e inexistentes. Eso
no es un defecto de estilo — en una tesis es falta académica.
"""

from __future__ import annotations

import re
import unicodedata


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


# Familias de sección a las que aplican reglas distintas.
_FAMILIAS: list[tuple[str, re.Pattern]] = [
    ("titulo",            re.compile(r"\btitulo\b")),
    ("antecedentes",      re.compile(r"antecedent|marco teorico|base teorica|estado del arte|"
                                     r"definicion de terminos|referencia")),
    ("preguntas",         re.compile(r"formulacion|problema central|pregunta")),
    ("objetivos",         re.compile(r"objetivo")),
    ("operacionalizacion", re.compile(r"operacionaliz|variable")),
    ("matriz",            re.compile(r"matriz de consistencia")),
    ("poblacion",         re.compile(r"poblacion|muestra")),
    ("procedimiento",     re.compile(r"procedimiento")),
    ("analisis",          re.compile(r"analisis de datos|procesamiento")),
    ("hipotesis",         re.compile(r"hipotesis|supuesto")),
]


def familia_de(seccion: str) -> str:
    """A qué familia de reglas pertenece esta sección del proyecto."""
    n = _norm(seccion)
    for familia, patron in _FAMILIAS:
        if patron.search(n):
            return familia
    return "general"


# ── Las reglas ──────────────────────────────────────────────────────────────

_REGLAS: dict[str, str] = {
    "antecedentes": """\
NO ESCRIBAS NINGUNA CITA QUE NO ESTÉ YA EN EL TEXTO DEL ESTUDIANTE.
Esta sección se apoya en estudios reales. Si la reescribes añadiendo «Ramírez (2023) demostró…»,
estás fabricando una referencia: el jurado pide el DOI, no existe, y eso es falta académica, no un
error de redacción. Puedes reordenar, mejorar la prosa y completar la estructura de los antecedentes
que YA ESTÁN, pero no añadir estudios nuevos.
Si la sección está vacía o le faltan antecedentes, NO la rellenes: deja el hueco marcado como
[antecedente pendiente: qué buscar] y explica en `recomendaciones` qué debe buscar y dónde.

ESTRUCTURA DE CADA ANTECEDENTE (para ordenar los que ya tiene, en prosa y APA 7): cita, título del
estudio (opcional), problema que abordó, objetivo general, diseño de investigación con su muestra,
resultados CUANTITATIVOS, e implicancias para ESTE proyecto —qué se toma de ese estudio—. La
implicancia es lo que distingue un antecedente de un resumen, y es lo que más se omite.
Al cierre debe haber una SÍNTESIS Y BRECHA: qué resuelven en conjunto, qué queda abierto y por qué
eso justifica el estudio.""",

    "titulo": """\
MÁXIMO 20 PALABRAS, contando TODO: los conectores (y, de, por, en, para, con, la, el) y el año o
periodo. Cuéntalas antes de entregar.
NO INVENTES el año ni la institución. Si el proyecto no dice el periodo, va «[periodo]»; si no dice
la empresa, va «[institución]». Un año plausible es una falsedad, no un relleno.
El título debe dejar leer la variable independiente (lo que se construye) y la dependiente (lo que se
mide). Si la dependiente no es medible —«mejorar la gestión»— eso se señala en `recomendaciones`.""",

    "preguntas": """\
NINGUNA PREGUNTA ESPECÍFICA PUEDE RESPONDER POR SÍ SOLA A LA GENERAL. Si al contestar una sola ya
queda contestada la general, no es específica: es la general disfrazada y rompe la lógica del
proyecto. El caso que más se cuela: «¿qué diferencias hay en Y entre quienes usan X y quienes no?»
cuando la general pregunta por el efecto de X sobre Y.
Las específicas escalan en nivel cognitivo (Bloom): comprender → aplicar → analizar → evaluar, y
juntas cubren la general sin abrir un estudio nuevo.
UN CONSTRUCTO POR PREGUNTA: si la general habla de calidad, una pregunta sobre «percepción» cambia
de objeto de estudio.""",

    "objetivos": """\
CADA OBJETIVO ESPECÍFICO SALE DE UNA PREGUNTA ESPECÍFICA, en el mismo orden y con el mismo alcance.
El verbo lo fija el nivel de Bloom de su pregunta: identificar/describir (comprender),
diseñar/implementar/aplicar (aplicar), analizar/comparar (analizar), evaluar/determinar (evaluar).
El objetivo general es el espejo de la pregunta general, en infinitivo.
NO INVENTES OBJETIVOS SI NO HAY PREGUNTAS: si el proyecto no tiene las preguntas específicas
redactadas, no las deduzcas — señálalo en `recomendaciones`.
En una tesis de ingeniería, un objetivo de construir o implementar el artefacto SÍ es un objetivo
específico legítimo: no lo marques como «no es de investigación».""",

    "operacionalizacion": """\
COLUMNAS: Variable · Definición conceptual · Definición operacional · Dimensiones · Indicadores ·
Escala de medición. Se recomienda una tabla para la variable independiente y otra para la dependiente.
DE DÓNDE SALE CADA COSA: la definición CONCEPTUAL dice qué ES la variable según la teoría y VA
CITADA; las DIMENSIONES salen de esa definición conceptual (las formula la teoría, no se redactan de
forma deliberada); la definición OPERACIONAL dice cómo se medirá y de ella salen los INDICADORES, que
llevan su unidad. La variable independiente no se mide, pero aparece en la tabla: su indicador suele
ser presencia/ausencia en escala nominal.
NO INVENTES LA CITA de la definición conceptual: si no está, va [cita pendiente: concepto a buscar].
PARSIMONIA CON COSTO: cada indicador arrastra un instrumento, y cada instrumento que recoja el juicio
de una persona exige juicio de expertos (3-5) y confiabilidad (alfa de Cronbach). No inflar
dimensiones no es un capricho: son semanas de trabajo.
EXCEPCIÓN IMPORTANTE: las métricas que calcula el propio sistema —exactitud, F1, MAPE, tiempo de
respuesta, consumo en watts— NO necesitan juicio de expertos; su validez está en su definición
matemática. Lo que se documenta ahí es el procedimiento de medición. No exijas validar un cronómetro.""",

    "matriz": """\
LA MATRIZ DE CONSISTENCIA NO INTRODUCE CONTENIDO NUEVO: coloca lo que ya está definido en las
secciones anteriores y muestra que encaja. Cada fila cruza problema específico → objetivo específico
→ hipótesis específica (si el enfoque las exige) → variable → indicadores.
Si al armarla aparece algo que no estaba antes, ese es el hallazgo: significa que una sección previa
está incompleta. Dilo en `recomendaciones` en vez de rellenar la celda.
Si el número de problemas, objetivos e hipótesis no coincide, es una incoherencia de la cadena, no un
problema de formato.""",

    "poblacion": """\
LA POBLACIÓN DEPENDE DEL DISEÑO Y DE LA UNIDAD DE ANÁLISIS. Si lo que se mide son registros, equipos
o transacciones, la población son esos, no las personas.
· Preexperimental: un solo grupo, medición antes y después.
· Cuasiexperimental: grupo experimental y de control sin asignación aleatoria; hay que decir en qué
  son comparables.
· Experimental puro: exige asignación aleatoria, que en una organización casi nunca es viable;
  prometerla sin poder cumplirla es un problema que hay que señalar.
LA MUESTRA SE CALCULA con la fórmula de población finita: n = (N·z²·p·q) / (e²·(N−1) + z²·p·q), con
95 % de confianza (z = 1.96) y p = q = 0.5. El margen de error estándar es 5 % y el MÁXIMO admisible
es 10 %. Con poblaciones pequeñas (≤60) conviene censo. NO estimes un número «razonable».""",

    "procedimiento": """\
LAS FASES SE ALINEAN A LOS OBJETIVOS ESPECÍFICOS, pero NO una por una: una fase puede cubrir varios
objetivos y un objetivo puede repartirse entre varias fases. Lo que no puede haber es un objetivo que
ninguna fase avance, ni una fase que no sirva a ningún objetivo.
Cada fase necesita un entregable verificable.""",

    "analisis": """\
LAS TÉCNICAS SE DERIVAN DEL DISEÑO Y DE LA ESCALA, no de la costumbre: descriptiva primero; prueba de
normalidad (Shapiro-Wilk con muestras pequeñas) para decidir entre paramétrica y no paramétrica; y la
prueba que corresponda —dos medidas del mismo grupo piden t de Student pareada o Wilcoxon; dos grupos
independientes piden t independiente o U de Mann-Whitney—. Cada elección va con su porqué.""",

    "hipotesis": """\
Las hipótesis solo se exigen si el enfoque las requiere. En un estudio cualitativo se habla de
supuestos o categorías apriorísticas, no de hipótesis estadísticas.
Cada hipótesis específica se corresponde con un objetivo específico y se enuncia de forma
contrastable, con la dirección del efecto.""",
}

_REGLA_TESIS_12 = """\
REPARTO TESIS 1 / TESIS 2: en Tesis 1 se alcanza la mitad de los objetivos específicos y en Tesis 2
se culminan; terminarlos todos antes no está prohibido. Como el artefacto rara vez está listo en
Tesis 1, no marques como deficiencia que los resultados finales no estén: lo que corresponde es
recomendar resultados parciales sobre un módulo, una revisión sistemática de la literatura, o trabajo
sobre datos históricos."""

_REGLA_NO_INVENTAR = """\
NO INVENTES DATOS QUE EL PROYECTO NO TENGA: ni cifras, ni porcentajes, ni nombres de empresas, ni
años, ni citas. Lo que falte va como marcador explícito —[dato por conseguir: … — fuente: …]— y la
orientación va en `recomendaciones`. Una afirmación cuantitativa sin respaldo («un alto porcentaje»,
«la mayoría») es una falsedad aunque suene bien."""


_REGLA_NO_TOCAR_LO_QUE_CUMPLE = """\
NO REESCRIBAS LO QUE YA ESTÁ BIEN. Cada cambio tuyo tiene que cerrar una brecha concreta de la
rúbrica; si no cierra ninguna, no lo hagas. Cambiar «a través del» por «mediante», reordenar una
frase correcta o «simplificar» una definición que ya cumplía no mejora la nota, le borra al
estudiante su propia voz y le hace revisar de nuevo un texto que ya tenía cerrado.
Y NO CAMBIES DECISIONES DE MEDICIÓN de pasada: la escala (nominal, ordinal, intervalo, razón), los
indicadores, las dimensiones, el número de objetivos o el diseño no se tocan salvo que la brecha
sea exactamente esa — y entonces explicas por qué el valor anterior estaba mal. Un tiempo o una tasa
son escala de RAZÓN; degradarlos a intervalo invalida los estadísticos que el alumno tenía previstos.
Si ves algo mejorable que NO es la brecha que te toca cerrar, va en `recomendaciones`, no en el texto."""


def reglas_para(seccion: str) -> str:
    """Bloque de reglas aplicable a la sección que se va a reescribir o calificar."""
    familia = familia_de(seccion)
    partes = [_REGLA_NO_INVENTAR]
    if familia in _REGLAS:
        partes.append(_REGLAS[familia])
    if familia in ("objetivos", "procedimiento", "analisis"):
        partes.append(_REGLA_TESIS_12)
    return "\n\n".join(partes)


# El núcleo reescribe cinco familias a la vez (título · problema · objetivos ·
# hipótesis · variables). Resolverlo con `familia_de` daba solo las reglas del
# TÍTULO —es la primera palabra del nombre de la sección—, así que al reescribir
# la operacionalización nadie le recordaba de dónde salen las dimensiones ni que
# la escala no se cambia. El resultado observado: dimensiones inventadas
# («implementación, funcionalidad, usabilidad») y la escala de razón convertida en
# intervalo, dos decisiones de medición alteradas sin que nadie lo pidiera.
_FAMILIAS_NUCLEO = ("titulo", "preguntas", "objetivos", "hipotesis", "operacionalizacion")


def reglas_de_nucleo() -> str:
    """Reglas de las cinco familias que el núcleo reescribe en una sola pasada."""
    partes = [_REGLA_NO_INVENTAR, _REGLA_NO_TOCAR_LO_QUE_CUMPLE]
    partes += [_REGLAS[f] for f in _FAMILIAS_NUCLEO if f in _REGLAS]
    partes.append(_REGLA_TESIS_12)
    return "\n\n".join(partes)


def es_seccion_de_fuentes(seccion: str) -> bool:
    """¿Reescribir esta sección puede producir referencias inventadas?"""
    return familia_de(seccion) == "antecedentes"
