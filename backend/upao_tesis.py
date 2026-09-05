"""
Conocimiento institucional UPAO del PROYECTO de tesis de Ingeniería — fuente única.

Este módulo NO evalúa ni redacta: expone (a) los hechos duros del formato oficial
y (b) verificaciones DETERMINISTAS que no pueden delegarse a un LLM (contar las
palabras de un título, detectar citas sin respaldo). Los agentes del mini-grafo lo
consumen para no alucinar reglas institucionales.

Fuentes:
  - «1. Formato de proyecto de tesis - Ingeniería.docx» (plantilla oficial UPAO).
  - RR N.° 1499-2025 / RV N.° 077-2025-VIN-UPAO — Líneas de Investigación
    Institucionales 2025 (Línea 03 y sus sublíneas).
  - Repositorio Institucional UPAO — patrones reales de títulos de los últimos
    2 años en Ing. de Computación y Sistemas.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

# ── 1. Estructura oficial del PROYECTO de tesis ──────────────────────────────
# Ámbito: es una PROPUESTA. Termina en aspectos administrativos: NO hay
# resultados, discusión ni conclusiones.

ESTRUCTURA_PROYECTO_UPAO = """\
I. GENERALIDADES (título, equipo, tipo de investigación, línea de investigación,
   unidad académica, institución/localidad, duración, horas)
II. PLAN DE INVESTIGACIÓN
 1. PLANTEAMIENTO DEL ESTUDIO
   1.1. Descripción y delimitación del problema
     1.1.1. Formulación del problema
     1.1.2. Problema central del estudio
   1.2. Objetivos (1.2.1. general — 1.2.2. específicos)
   1.3. Importancia del estudio
   1.4. Justificación del estudio (teórica, práctica, metodológica y social)
   1.5. Limitaciones del estudio
 2. MARCO TEÓRICO
   2.1. Marco histórico  ->  **NO APLICA** (así lo trae la plantilla oficial)
   2.2. Investigaciones antecedentes relacionadas con el tema
   2.3. Base teórica (variable independiente / variable dependiente)
   2.4. Definición de términos básicos
 3. HIPÓTESIS Y VARIABLES
   3.1. Supuestos básicos
   3.2. Hipótesis (3.2.1. general Hg — 3.2.2. específicas H1, H2, H3…)
   3.3. Variables (Tabla 1. Operacionalización: variable, definición conceptual,
        definición operacional, dimensiones, indicador, ítems, escala de medición)
   3.4. Matriz de consistencia (Tabla 2: título, problema general, objetivo general,
        hipótesis general, variables, indicadores, metodología —enfoque, tipo,
        diseño, población, muestra—, problemas/objetivos/hipótesis específicos)
 4. MARCO METODOLÓGICO
   4.1. Tipo de investigación   4.2. Método de investigación   4.3. Diseño del estudio
   4.4. Población y muestra     4.5. Técnicas e instrumentos de recolección de datos
   4.6. Procedimiento de ejecución del estudio
   4.7. Técnicas de procesamiento y análisis de datos
 5. ASPECTOS ADMINISTRATIVOS
   5.1. Cronograma de actividades
   5.2. Recursos (5.2.1. humanos — 5.2.2. materiales)
   5.3. Presupuesto (5.3.1. bienes — 5.3.2. servicios)
   5.4. Financiación (5.4.1. recursos propios — 5.4.2. recursos externos)
 6. REFERENCIAS BIBLIOGRÁFICAS
 7. ANEXOS"""

# Secciones que la plantilla oficial marca como no aplicables.
SECCIONES_NO_APLICA: dict[str, str] = {
    "2.1 Marco histórico": (
        "La plantilla oficial de Ingeniería UPAO trae «2.1. Marco histórico: NO APLICA». "
        "NO se redacta: se deja literalmente «NO APLICA». Nunca ofrezcas redactarlo ni "
        "sugieras que le falta al estudiante."
    ),
}


# ── 2. Reglas del TÍTULO (verificables) ──────────────────────────────────────

TITULO_MAX_PALABRAS = 20

REGLAS_TITULO = """\
REGLAS DURAS (están escritas en la plantilla oficial: incumplirlas es un error):
- Máximo **20 palabras**, contando TODAS: conectores y palabras cortas («y», «o», «de»,
  «la», «en», «para», «con», «del») cuentan igual que las demás. 21 ya incumple.
- Sin comillas.
- Solo con mayúscula la primera letra y los nombres propios (no title case, no MAYÚSCULAS).

CRITERIOS DE RÚBRICA (ítems 1-3) — oriéntalos, NO los impongas como si fueran obligatorios:
- El título debe reflejar fielmente el contenido y el propósito del estudio (ítem 1) y
  enmarcarse en la línea de investigación del programa (ítem 3).
- El ítem 2 pide que el título articule VARIABLES, ESPACIO y TIEMPO. Ojo con cómo lo aplicas,
  porque en la práctica del programa NO es absoluto (medido sobre las tesis aprobadas de
  Ing. de Computación y Sistemas en el Repositorio UPAO, 2022-2026, n=101):
    · las VARIABLES aparecen siempre (el artefacto y el proceso que mejora);
    · el ESPACIO (organización o lugar) aparece en el **87%** — es la norma de facto;
    · el TIEMPO (año o periodo) aparece solo en el **59%**: el 41% de las tesis APROBADAS
      no lleva año en el título y son perfectamente válidas.
  Por tanto: **NUNCA rechaces ni marques como error un título por no llevar año.** Sugiere
  añadirlo solo cuando tenga sentido para ESE estudio: si el trabajo se circunscribe a un
  periodo concreto (datos de un año, medición pre/post en una ventana temporal, cohorte de
  un ciclo), el año refuerza el ítem 2. Si es la evaluación de un artefacto sin ventana
  temporal definida (p. ej. comparar arquitecturas de un modelo), omitirlo es correcto y
  forzarlo queda artificial. Explícale el criterio y deja que decida."""


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")


_RE_TOKEN = re.compile(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")


def contar_palabras(texto: str) -> int:
    """Cuenta palabras como lo haría un jurado: todo token separado por espacios que
    contenga al menos un carácter alfanumérico. Los conectores CUENTAN."""
    limpio = re.sub(r"[«»\"'`´]", " ", texto or "")
    return sum(1 for t in limpio.split() if _RE_TOKEN.search(t))


def limpiar_titulo(texto: str) -> str:
    """Extrae el título de una respuesta que puede venir con markdown/etiquetas."""
    t = (texto or "").strip()
    t = re.sub(r"^\s*#{1,6}\s*", "", t)                       # encabezados markdown
    t = re.sub(r"^\s*(t[íi]tulo|propuesta)\s*(propuesto|sugerido)?\s*:\s*", "", t, flags=re.I)
    t = t.replace("**", "").replace("*", "").strip()
    primera = next((l.strip() for l in t.split("\n") if l.strip()), "")
    return primera.strip(" .")


# Proxy de ESPACIO: organización, entidad o lugar concreto en el título.
_RE_ESPACIO = re.compile(
    r"\b(empresa|compa[ñn]\w*|s\.?a\.?c|s\.?a\.?a|s\.?r\.?l|e\.?i\.?r\.?l|hospital|cl[ií]nica|"
    r"municipalidad|instituci[oó]n|colegio|universidad|facultad|gerencia|direcci[oó]n|"
    r"red de salud|corte|contralor[ií]a|banco|entidad|centro|laboratorio|agencia|tienda|"
    r"trujillo|lima|piura|cajamarca|chimbote|la libertad|per[uú]|distrito|regi[oó]n)\b",
    re.I,
)
_RE_SIGLA = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{3,}\b")


def validar_titulo(titulo: str) -> tuple[list[str], list[str]]:
    """Chequeos DETERMINISTAS del título.

    Devuelve `(problemas, advertencias)`:
      - `problemas`   → incumplen una regla ESCRITA en la plantilla oficial. Bloquean:
                        el entregable no puede salir así.
      - `advertencias`→ criterios de rúbrica que conviene revisar, pero que las tesis
                        aprobadas del programa incumplen con frecuencia. NO bloquean:
                        se le trasladan al estudiante como consejo para que decida.
    """
    t = limpiar_titulo(titulo)
    problemas: list[str] = []
    advertencias: list[str] = []
    if not t:
        return problemas, advertencias

    # ── Reglas duras (plantilla oficial) ──
    n = contar_palabras(t)
    if n > TITULO_MAX_PALABRAS:
        problemas.append(
            f"El título tiene {n} palabras y el máximo de la plantilla UPAO es "
            f"{TITULO_MAX_PALABRAS} (los conectores «y/o/de/la/en/para» también cuentan). "
            f"Sobran {n - TITULO_MAX_PALABRAS}: recorta sin perder las variables."
        )
    if re.search(r"[\"«»]", titulo or ""):
        problemas.append("El título lleva comillas; la plantilla oficial las prohíbe.")

    letras = [c for c in t if c.isalpha()]
    if letras and all(c.isupper() for c in letras):
        problemas.append("El título está en MAYÚSCULAS; va solo con mayúscula inicial y nombres propios.")

    # Title Case: varias palabras «llenas» capitalizadas (los conectores no cuentan).
    menores = {"de", "del", "la", "las", "el", "los", "y", "o", "en", "para", "con",
               "por", "a", "al", "un", "una", "su", "sus", "e", "u"}
    palabras = [p for p in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", t)][1:]
    capitalizadas = [p for p in palabras
                     if p[:1].isupper() and _sin_tildes(p).lower() not in menores]
    if len(palabras) >= 6 and len(capitalizadas) >= max(3, len(palabras) // 2):
        problemas.append(
            "El título está en Title Case (varias palabras con mayúscula inicial). La plantilla "
            "pide mayúscula SOLO en la primera letra y en los nombres propios."
        )

    # ── Advertencias (criterios de rúbrica, no reglas escritas) ──
    if not (_RE_ESPACIO.search(t) or _RE_SIGLA.search(t)):
        advertencias.append(
            "El título no nombra el ESPACIO (organización, institución o lugar). No es un error "
            "formal, pero el 87% de las tesis aprobadas del programa lo incluye y el ítem 2 de la "
            "rúbrica lo valora: si tu estudio se hace en una organización concreta, nómbrala."
        )
    if not re.search(r"\b(19|20)\d{2}\b", t):
        advertencias.append(
            "El título no declara TIEMPO (año o periodo). NO es obligatorio: el 41% de las tesis "
            "aprobadas del programa tampoco lo lleva. Añádelo solo si tu estudio se circunscribe a "
            "un periodo concreto (datos de un año, medición pre/post en una ventana definida); si "
            "evalúas un artefacto sin ventana temporal, es correcto omitirlo."
        )
    return problemas, advertencias


# ── 3. Línea de investigación (RR 1499-2025) ─────────────────────────────────

LINEA_INVESTIGACION_SISTEMAS = "Robótica, automatización avanzada y sistemas inteligentes"

# Sublíneas oficiales de la Línea 03 (las que aplican a Ing. de Computación y
# Sistemas / Ing. de Sistemas e Inteligencia Artificial van primero).
SUBLINEAS_LINEA_03: list[tuple[str, str]] = [
    ("Inteligencia artificial",
     "Modelos de IA/ML/DL: predicción, clasificación, visión por computador, NLP, LLM."),
    ("Sistemas inteligentes",
     "Sistemas que perciben, razonan o deciden: recomendadores, agentes, sistemas expertos, chatbots."),
    ("Ingeniería de software",
     "Construcción de software con método: arquitecturas, metodologías (Scrum, XP), calidad, DevOps, pruebas."),
    ("Sistemas de información",
     "Sistemas y aplicaciones que soportan procesos de negocio: web, móvil, ERP, integraciones."),
    ("Gestión de datos e información",
     "Datos e inteligencia de negocio: BI, dashboards, data warehouse/lakehouse, analítica, ETL."),
    ("Comunicación, tecnología de la información e innovación",
     "Redes, IoT, ciberseguridad, infraestructura, cloud y transformación digital."),
    ("Sistemas cognitivos",
     "Sistemas de automatización y control que emulan capacidades cognitivas."),
    ("Robótica y automatización avanzada",
     "Robótica, control automático y automatización de procesos físicos."),
    ("Nanomateriales funcionales",
     "Nanotecnología y nanoprocesos (no aplica a proyectos de software)."),
]


def bloque_linea_investigacion() -> str:
    subs = "\n".join(f"  - **{n}**: {d}" for n, d in SUBLINEAS_LINEA_03)
    return (
        "## LÍNEA DE INVESTIGACIÓN (RR N.° 1499-2025-R-UPAO)\n"
        f"Para Ingeniería de Computación y Sistemas / Ingeniería de Sistemas e Inteligencia "
        f"Artificial la línea institucional es UNA sola: **{LINEA_INVESTIGACION_SISTEMAS}** "
        "(Línea 03). El estudiante NO elige entre varias líneas: elige la SUBLÍNEA donde encaja "
        "su proyecto.\n"
        f"Sublíneas vigentes de la Línea 03:\n{subs}\n"
        "Si el estudiante pregunta en qué se diferencian, explícalo con estos alcances y ubícalo "
        "en la sublínea que corresponda a SU proyecto; si su idea encaja en dos, dile cuál pesa "
        "más según su variable independiente (el artefacto que construye)."
    )


# ── 4. Tipo de investigación (Generalidades del formato) ─────────────────────

TIPOS_INVESTIGACION_UPAO = """\
## TIPO DE INVESTIGACIÓN (el formato UPAO lo pide en dos ejes)
1. **Según su orientación o finalidad**: básica o **aplicada**.
   En Ingeniería de Computación y Sistemas es **aplicada en la práctica totalidad de los casos**:
   se construye o adapta un artefacto para resolver un problema real de una organización.
2. **Según la técnica de contrastación**: descriptiva, correlacional, explicativa,
   **experimental** (pre-experimental, cuasi-experimental o experimental puro) o aplicada/tecnológica.
   - **Pre-experimental** (un solo grupo, pre-test / post-test) es el más frecuente cuando se mide
     el proceso ANTES y DESPUÉS de implantar el sistema. No hay grupo de control.
   - **Cuasi-experimental**: hay grupo de comparación pero sin asignación aleatoria.
   - **Descriptiva / correlacional**: no se manipula la variable independiente.
También se declara el **enfoque**: cuantitativo, cualitativo o mixto. En estos proyectos suele ser
cuantitativo (se miden indicadores del proceso: tiempo, costo, exactitud, satisfacción).

REGLA DE CONDUCTA: si el estudiante todavía NO ha declarado su tipo/diseño, PREGÚNTASELO antes de
redactar hipótesis, variables o metodología — de eso depende si necesita hipótesis, grupo de control,
pre/post test y qué prueba estadística usará. No lo elijas por él: ofrécele las opciones con su
implicancia y deja que decida.

ATENCIÓN — SON DOS PREGUNTAS DISTINTAS, NUNCA LAS MEZCLES EN UNA:
  (a) la ORIENTACIÓN o finalidad (básica / aplicada), y
  (b) el DISEÑO o técnica de contrastación (pre-experimental / cuasi-experimental / experimental /
      descriptiva / correlacional).
Si las juntas, el estudiante contesta solo una —normalmente «aplicada»— y se queda sin declarar el
diseño, que es justo lo que decide si necesita hipótesis y medición pre/post."""


# Molde vacío del título: se le entrega SIEMPRE al cerrar una elicitación, para que
# el estudiante vea la forma del entregable sin que se le proponga un tema concreto.
MOLDE_TITULO = (
    "«<artefacto o técnica> para <mejorar / optimizar / predecir> <proceso o indicador> "
    "en <organización>, <ciudad> <año, solo si tu estudio se ciñe a un periodo>»"
)

# Preguntas canónicas de tipo y diseño. Van por separado a propósito (ver arriba) y
# se inyectan de forma determinista si el elicitador se olvida de alguna.
PREGUNTA_TIPO_INVESTIGACION = {
    "pregunta": "¿Tu investigación es aplicada o básica?",
    "opciones": (
        "En Ingeniería de Computación y Sistemas es **aplicada** casi siempre: construyes o adaptas "
        "un artefacto para resolver un problema real de una organización. Sería básica solo si tu "
        "aporte fuese puramente teórico, sin implantación."
    ),
    "por_que_importa": (
        "Va en las Generalidades del formato y marca todo el enfoque; si es aplicada, el jurado "
        "esperará un artefacto y una organización concreta."
    ),
}

PREGUNTA_DISENO = {
    "pregunta": "¿Qué diseño usarás para contrastar el resultado?",
    "opciones": (
        "**Pre-experimental** (un solo grupo, mides el proceso antes y después de implantar tu "
        "sistema; el más frecuente) · **Cuasi-experimental** (hay grupo de comparación, sin "
        "asignación aleatoria) · **Descriptiva o correlacional** (no manipulas nada, solo observas "
        "o relacionas variables)."
    ),
    "por_que_importa": (
        "De esto depende si necesitas hipótesis, si necesitas grupo de control, si debes medir "
        "pre/post y qué prueba estadística aplicarás. Es la decisión que más condiciona tu capítulo 4."
    ),
}


# ── 5. Patrones reales del Repositorio Institucional UPAO ────────────────────
# Extraídos de tesis de Ing. de Computación y Sistemas de los últimos 2 años.
# Sirven para dar IDEAS de alcance, no para copiar.

PATRON_TITULOS_REPOSITORIO = """\
## ALCANCE REAL DE LOS PROYECTOS (Repositorio Institucional UPAO, últimos 2 años)
Los títulos aprobados en el programa siguen casi siempre esta forma:
  «<artefacto o técnica> para <mejorar/optimizar/predecir> <proceso o variable dependiente>
   en <organización>, <ciudad> <año>»
Ejemplos reales del repositorio (patrones, NO para copiar):
- Aplicación web que integra técnicas de Machine Learning para evaluar el riesgo de TEA en niños de Trujillo 2025
- Sistema web de reconocimiento facial para evaluación emocional en el Centro de Empleo del Gobierno Regional - La Libertad, 2023
- Modelo predictivo basado en datos históricos para el pronóstico de la demanda farmacéutica en la Red de Salud Virú, 2024
- Sistema de gestión logística basado en la nube para optimizar el monitoreo y predicción de demanda en Rodrich SRL, 2024
- Implementación de arquitectura LakeHouse en Microsoft Fabric para trazabilidad e inteligencia comercial en Camposol
- Sistema recomendador de rutas basado en Scrum y el algoritmo KD-Tree para transporte público en Trujillo, 2023
- Marco de ciberseguridad para identificar y mitigar vulnerabilidades en la infraestructura de red de la empresa G.T.
- Chatbot inteligente para la atención a los estudiantes de la Universidad Católica de Trujillo, 2024

Qué enseña esto (úsalo para orientar, no para imponer):
- El artefacto es la VARIABLE INDEPENDIENTE; el proceso que mejora es la DEPENDIENTE.
- Casi siempre hay una organización real y un año: por eso el título cumple «espacio y tiempo».
- El alcance es acotado y ejecutable por 1-2 tesistas en un ciclo: un proceso concreto de UNA
  organización, no una plataforma nacional ni un modelo de investigación básica.
- Tecnologías típicas: web/móvil, ML/DL, BI y dashboards, IoT, ciberseguridad, cloud, RPA, chatbots/LLM."""


# ── 6. Conducta del mentor: no complacer, enseñar ────────────────────────────

MENTALIDAD_PROBLEMA_PRIMERO = """\
## PROBLEMA PRIMERO, NUNCA SOLUCIÓN PRIMERO
Muchos estudiantes llegan con la tecnología decidida («quiero hacer algo con IA / blockchain»)
y luego buscan dónde aplicarla. Ese orden está invertido y el jurado lo detecta.
Si detectas ese patrón, NO lo dejes pasar: dilo con respeto y reconduce.
- Pregunta primero: ¿qué proceso falla?, ¿de quién es el dolor?, ¿cómo se mide hoy?,
  ¿qué evidencia tienes de que existe (indicadores, tiempos, costos, quejas)?
- La tecnología se elige DESPUÉS, como la alternativa que mejor resuelve ese problema medido.
- Un proyecto sin problema medible no tiene variable dependiente, y sin ella no hay hipótesis
  ni operacionalización posibles.
Excepción legítima: un proyecto **tecnológico puro** (construir/evaluar un artefacto) es válido
bajo el Art. 37.f del Reglamento UPAO. En ese caso NO fuerces el molde cuantitativo clásico, pero
SÍ advierte al estudiante qué le va a exigir igual la rúbrica (problema, objetivos, variables,
población/muestra de pruebas, instrumentos de validación) para que decida con información."""

NO_COMPLACENCIA = """\
## NO SEAS COMPLACIENTE (esto es lo que te diferencia de un chatbot)
- Si el estudiante te pide redactar algo para lo que NO tienes base suficiente, NO lo inventes:
  dile qué le falta y pregúntaselo. Es preferible una pregunta buena a un párrafo inventado.
- **Antecedentes (2.2)**: JAMÁS los redactes de tu cabeza. Un antecedente es un estudio REAL,
  citable y verificable. Puedes enseñarle CÓMO buscarlos, qué estructura debe tener cada uno
  (autor, año, objetivo, metodología, resultado, y en qué se relaciona con SU estudio) y darle
  la plantilla vacía para que la llene con lo que encuentre. Nunca fabriques autores, años,
  revistas ni resultados.
- **Base teórica (2.3)**: cada afirmación teórica necesita fuente. Si tu material recuperado no
  la respalda, dilo y pídele la fuente en vez de rellenar.
- **Hipótesis / variables**: si solo te dio el título, puedes DERIVAR una propuesta coherente,
  pero explícale de dónde sale cada parte y qué decisiones suyas faltan (dirección del efecto,
  indicadores, escala). No presentes como hecho lo que es una inferencia tuya.
- **Instrumentos (4.5)**: recuérdale que necesita instrumentos VALIDADOS o validarlos él
  (juicio de expertos + confiabilidad, p. ej. alfa de Cronbach). No des por hecho que existe
  un instrumento si no lo has visto.
- **Datos, acceso y presupuesto**: no asumas que tiene acceso a los datos, a la organización
  ni al dinero. Pregúntaselo y que lo CONFIRME: una tesis se cae ahí, no en la redacción.
- Si te pide que le des la razón, dásela solo si la tiene. Señalar un problema a tiempo vale
  más que un elogio."""

CONSEJOS_PRACTICOS = """\
## CONSEJOS PRÁCTICOS QUE SÍ SIRVEN (dalos cuando vengan al caso)
- **Buscar literatura**: Google Scholar, Scopus, Web of Science, IEEE Xplore, ScienceDirect,
  Redalyc, SciELO, ALICIA/CONCYTEC y el propio Repositorio UPAO (para ver tesis aprobadas del
  programa). Filtra por últimos 5 años y por revistas indexadas.
- **Acceder a un paper de pago**: pídelo por correo al autor (suelen enviarlo), busca el
  preprint en arXiv/ResearchGate, usa el acceso institucional de la biblioteca UPAO; si nada
  de eso funciona, existen Sci-Hub y Anna's Archive — muchos investigadores los usan, aunque
  su estatus legal es discutido y la cita debe hacerse siempre a la fuente original.
- **Gestor de referencias**: Zotero o Mendeley desde el primer día, con el estilo APA 7.ª
  configurado. Ahorra el ítem 33 de la rúbrica (referencias conforme a norma).
- **Instrumentos validados**: búscalos en tesis previas del repositorio y en los anexos de
  papers; si adaptas uno, cita al autor original y valida la adaptación (juicio de expertos +
  alfa de Cronbach). Si lo construyes desde cero, planifica esa validación en el cronograma.
- **Antiplagio**: la UPAO usa control de similitud; parafrasear sin citar sigue siendo plagio.
- **Presupuesto**: usa costos reales y locales (soles), separa bienes de servicios y considera
  depreciación de los equipos que ya tienes, tal como pide la plantilla."""


# ── 7. Anti-alucinación determinista: citas sin respaldo ─────────────────────

_RE_CITA_PAREN = re.compile(
    r"\(\s*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’-]{2,}(?:\s+(?:et\s+al\.?|y|&|and)\s+"
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’-]{2,})*)\s*,?\s*(\d{4})[a-z]?\s*\)"
)
_RE_CITA_NARRATIVA = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’-]{2,})(?:\s+(?:et\s+al\.?|y|&)\s+"
    r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’-]{2,})?\s*\(\s*(\d{4})[a-z]?\s*\)"
)

# Palabras que el regex confunde con apellidos al inicio de oración.
_NO_APELLIDOS = {
    "el", "la", "los", "las", "un", "una", "este", "esta", "estos", "estas", "su", "sus",
    "en", "para", "por", "con", "segun", "desde", "hasta", "durante", "entre", "sobre",
    "ademas", "asimismo", "tambien", "sin", "embargo", "tanto", "figura", "tabla",
    "anexo", "capitulo", "seccion", "peru", "trujillo", "upao", "lima", "resolucion",
    "universidad", "ley", "norma", "iso", "ieee", "apa", "scrum", "python", "java",
}


def _apellidos_citados(texto: str) -> set[str]:
    encontrados: set[str] = set()
    for rx in (_RE_CITA_PAREN, _RE_CITA_NARRATIVA):
        for m in rx.finditer(texto or ""):
            primero = _sin_tildes(m.group(1).split()[0]).lower()
            if primero and primero not in _NO_APELLIDOS and len(primero) > 2:
                encontrados.add(primero)
    return encontrados


def citas_sin_respaldo(texto_generado: str, *contextos: str) -> list[str]:
    """Apellidos citados en el texto GENERADO que no aparecen en ningún contexto real.

    Es la red anti-alucinación más importante del mini-grafo: si un agente escribe
    «(Ramírez, 2023)» y ese apellido no está ni en el proyecto del estudiante ni en los
    libros indexados, casi con seguridad se lo inventó.
    """
    if not (texto_generado or "").strip():
        return []
    respaldo = _sin_tildes(" ".join(c or "" for c in contextos)).lower()
    return sorted(a for a in _apellidos_citados(texto_generado) if a not in respaldo)


# ── 8. Chequeos deterministas por sección ────────────────────────────────────

_RE_SEC_TITULO = re.compile(r"t[íi]tulo", re.I)
_RE_SEC_ANTECEDENTES = re.compile(r"antecedent|2\.2", re.I)
_RE_SEC_MARCO_HIST = re.compile(r"marco\s+hist[óo]rico|2\.1", re.I)

# Umbral mínimo: el sistema no debe devolver «un par de palabras» cuando se le
# pide redactar una sección de desarrollo.
_MIN_CHARS_DESARROLLO = 350
_SECCIONES_BREVES = re.compile(r"t[íi]tulo|hip[óo]tesis|objetivo|formulaci[óo]n|pregunta", re.I)


def chequeos_deterministas(
    seccion: str,
    texto_generado: str,
    contexto_tesis: str = "",
    contexto_libros: str = "",
) -> tuple[list[str], list[str]]:
    """Verificaciones que NO dependen del criterio de un LLM.

    Devuelve `(problemas, advertencias)`. El nodo validador las recibe ya resueltas,
    así no tiene que «contar palabras» (algo que los LLM hacen mal). Solo los
    `problemas` bloquean el entregable; las `advertencias` viajan al estudiante como
    consejo, porque son criterios que las tesis aprobadas incumplen a menudo.
    """
    problemas: list[str] = []
    advertencias: list[str] = []
    sec = seccion or ""
    texto = (texto_generado or "").strip()
    if not texto:
        return problemas, advertencias

    if _RE_SEC_TITULO.search(sec):
        p, a = validar_titulo(texto)
        problemas.extend(p)
        advertencias.extend(a)

    if _RE_SEC_MARCO_HIST.search(sec) and "NO APLICA" not in texto.upper():
        problemas.append(
            "En la plantilla oficial UPAO el «2.1 Marco histórico» va como NO APLICA: "
            "no debe redactarse contenido ahí."
        )

    inventadas = citas_sin_respaldo(texto, contexto_tesis, contexto_libros)
    if inventadas:
        problemas.append(
            "CITAS SIN RESPALDO — estos apellidos aparecen citados pero no están ni en el texto "
            f"del estudiante ni en los libros recuperados: {', '.join(inventadas)}. "
            "Elimínalas o sustitúyelas por una indicación de qué debe buscar el estudiante. "
            "NUNCA inventes autores, años ni resultados."
        )

    if _RE_SEC_ANTECEDENTES.search(sec) and inventadas:
        problemas.append(
            "Los ANTECEDENTES no pueden redactarse con estudios inventados: entrega la ESTRUCTURA "
            "que debe llenar (autor, año, objetivo, metodología, resultado, relación con su estudio) "
            "y enséñale dónde buscarlos."
        )

    # Solo se exige extensión cuando SABEMOS que es una sección de desarrollo. Si la
    # sección no se pudo resolver, no se puede afirmar que el texto sea corto: un
    # título o una hipótesis legítimos caben en dos líneas y se marcarían en falso.
    if (sec.strip()
            and len(texto) < _MIN_CHARS_DESARROLLO
            and not _SECCIONES_BREVES.search(sec)
            and not _RE_SEC_MARCO_HIST.search(sec)):
        problemas.append(
            f"El texto entregado es demasiado breve ({len(texto)} caracteres) para una sección de "
            "desarrollo. Amplíalo con el contenido que la rúbrica exige, sin relleno y sin inventar datos."
        )
    return problemas, advertencias


# ── 10. Corpus real de tesis del programa (Repositorio UPAO) ─────────────────
# Se usa para dos cosas: dar IDEAS con alcance realista y AVISAR al estudiante
# cuando su idea ya existe casi igual en su propio programa.

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "data", "titulos_upao.json")
_CORPUS: list[dict] | None = None

_STOPWORDS = {
    # gramaticales
    "de", "del", "la", "las", "el", "los", "y", "o", "en", "para", "con", "por", "a", "al",
    "un", "una", "su", "sus", "e", "u", "que", "se", "mediante", "basado", "basada", "uso",
    "utilizando", "traves", "sobre", "the", "of", "and", "for",
    # verbos y sustantivos genéricos de cualquier título de ingeniería
    "desarrollo", "implementacion", "sistema", "aplicacion", "mejorar", "optimizar",
    "proceso", "gestion", "ano", "anos", "modelo", "solucion", "herramienta",
    # ⚠️ VOCABULARIO DE TRÁMITE ACADÉMICO. Sin esto, «elabórame un título para mi tesis»
    # engancha con las tesis que hablan SOBRE tesis (hay varias en el repositorio) y el
    # sistema avisa de una duplicidad inexistente antes de que el estudiante tenga tema.
    "tesis", "titulo", "proyecto", "proyectos", "investigacion", "universidad", "privada",
    "antenor", "orrego", "upao", "escuela", "profesional", "programa", "estudio", "estudios",
    "bachiller", "bachilleres", "facultad", "ingenieria", "trabajo", "tema", "grado",
    # verbos de petición del estudiante
    "elaborame", "elabora", "elaborar", "ayudame", "ayuda", "dame", "quiero", "necesito",
    "hacer", "haz", "puedes", "podrias", "redacta", "redactar", "mejora", "mejorar",
}

# Una consulta con menos términos de contenido que esto no dice nada del TEMA: buscar
# duplicados con ella solo produce ruido.
_MIN_TOKENS_CONSULTA = 3
# Y un solape de un solo término tampoco es señal de duplicidad.
_MIN_SOLAPE = 2


def _tokens(texto: str) -> set[str]:
    limpio = _sin_tildes(texto or "").lower()
    return {t for t in re.findall(r"[a-z]{3,}", limpio) if t not in _STOPWORDS}


def corpus_tesis() -> list[dict]:
    """Tesis reales del programa (título + año). Se carga una vez y se cachea."""
    global _CORPUS
    if _CORPUS is None:
        try:
            with open(_CORPUS_PATH, encoding="utf-8") as fh:
                _CORPUS = json.load(fh)
        except Exception:
            _CORPUS = []
    return _CORPUS


def tesis_similares(texto: str, n: int = 4, umbral: float = 0.16) -> list[dict]:
    """Tesis del programa parecidas a `texto`, por solapamiento de términos.

    Sirve para que el mentor pueda decir «ojo, ya existe algo casi igual en tu propio
    programa: diferénciate» en vez de proponer una idea duplicada.
    """
    consulta = _tokens(texto)
    # Sin tema todavía no hay nada que comparar: avisar de «duplicidad» aquí es ruido
    # que además desanima al estudiante antes de que haya propuesto nada.
    if len(consulta) < _MIN_TOKENS_CONSULTA:
        return []
    puntuadas = []
    for t in corpus_tesis():
        tks = _tokens(t.get("titulo", ""))
        if not tks:
            continue
        comunes = consulta & tks
        # Solapamiento relativo a la consulta (no Jaccard puro: los títulos son largos),
        # pero exigiendo también un mínimo ABSOLUTO: un solo término compartido no es señal.
        score = len(comunes) / len(consulta)
        if score >= umbral and len(comunes) >= _MIN_SOLAPE:
            puntuadas.append((score, t))
    puntuadas.sort(key=lambda x: (-x[0], x[1].get("anio", "")))
    return [dict(t, score=round(s, 2)) for s, t in puntuadas[:n]]


def bloque_tesis_similares(texto_o_lista, n: int = 4) -> str:
    """Bloque listo para el prompt con las tesis del programa parecidas a la idea.

    Acepta el texto a buscar, o una lista ya calculada por `tesis_similares` (para
    no repetir la búsqueda cuando el estado también necesita la lista cruda).
    """
    sim = texto_o_lista if isinstance(texto_o_lista, list) else tesis_similares(texto_o_lista, n=n)
    if not sim:
        return ""
    filas = "\n".join(f"  - ({t['anio']}) {t['titulo']}" for t in sim)
    return (
        "## TESIS YA APROBADAS EN ESTE MISMO PROGRAMA PARECIDAS A LO QUE PLANTEA\n"
        f"{filas}\n"
        "DEBES avisárselo al estudiante de forma explícita y útil: no para desanimarlo, sino para "
        "que DIFERENCIE su propuesta (otra población, otra organización, otra técnica, otra "
        "variable dependiente, o una comparación que las anteriores no hicieron). Un proyecto "
        "casi idéntico a uno ya sustentado en su facultad es una observación segura del jurado. "
        "Cita estos títulos tal cual: son reales, salen del Repositorio Institucional UPAO."
    )


# ── 11. Detección determinista de «solución primero» ─────────────────────────

# Tecnologías y dominios que los estudiantes traen ya decididos.
_RE_TECNOLOGIA = re.compile(
    r"\b(deep\s*learning|machine\s*learning|transfer\s*learning|redes?\s+neuronal\w*|"
    r"inteligencia\s+artificial|\bia\b|\bml\b|\bdl\b|blockchain|iot|internet\s+de\s+las\s+cosas|"
    r"realidad\s+(aumentada|virtual)|big\s*data|chatbot|\bllm\b|gpt|vision\s+computacional|"
    r"procesamiento\s+de\s+im[aá]genes|\bcnn\b|\brpa\b|cloud|business\s+intelligence|\bbi\b|"
    r"data\s*(warehouse|lake|lakehouse)|python|tensorflow|pytorch|yolo|resnet|mobilenet)\b",
    re.I,
)
# Señales de que SÍ hay un problema pensado (proceso que falla, medición, dolor).
_RE_PROBLEMA = re.compile(
    r"\b(problema|demora|retras\w*|error\w*|p[eé]rdida|costo\w*|tiempo\s+de|ineficien\w*|"
    r"deficien\w*|falla\w*|no\s+cuenta\s+con|carec\w*|dificulta\w*|queja\w*|insatisfac\w*|"
    r"manual\w*|reproces\w*|sobrecarga|cuello\s+de\s+botella|indicador\w*|tasa\s+de|"
    r"porcentaje|se\s+mide|actualmente)\b",
    re.I,
)
# Señales de contexto organizacional (dónde ocurre).
_RE_CONTEXTO = _RE_ESPACIO


def detectar_solucion_primero(mensaje: str) -> bool:
    """True si el estudiante nombra tecnologías/dominios pero ningún problema ni contexto.

    Es el patrón «tengo la solución, busco dónde aplicarla». Se detecta de forma
    determinista para que el mentor lo reconduzca SIEMPRE, y no solo cuando el LLM
    se acuerda de la regla.
    """
    m = mensaje or ""
    if not _RE_TECNOLOGIA.search(m):
        return False
    return not (_RE_PROBLEMA.search(m) or _RE_CONTEXTO.search(m))


# ── 11b. «No sé»: respuestas que el estudiante deja sin resolver ─────────────

_RE_NO_SE = re.compile(
    r"(?:^|[\s.,;:\d)\-])\s*(?:no\s+s[eé]|no\s+lo\s+s[eé]|ni\s+idea|no\s+tengo\s+idea|"
    r"no\s+estoy\s+seguro|todav[íi]a\s+no|a[úu]n\s+no|no\s+he\s+(?:pensado|decidido|visto)|"
    r"no\s+sabr[íi]a|cualquiera|lo\s+que\s+sea|t[úu]\s+dime|como\s+veas)\b",
    re.I,
)


def detectar_no_se(mensaje: str) -> bool:
    """True si el estudiante declara NO SABER algo que se le preguntó.

    Es el momento más delicado del acompañamiento: si el sistema sigue de largo y
    entrega igual el entregable, le está tapando un hueco que el jurado va a abrir.
    """
    return bool(_RE_NO_SE.search(mensaje or ""))


AVISO_NO_SE = """\
⚠️ EL ESTUDIANTE RESPONDIÓ «NO SÉ» A ALGO QUE SE LE PREGUNTÓ
PROHIBIDO seguir de largo y entregar el resultado como si el hueco no existiera. Un «no sé» no se
rellena con una suposición tuya ni se ignora: se ENSEÑA. Obligatorio en esta respuesta:
1. Di explícitamente qué quedó sin resolver y por qué es determinante (qué parte del proyecto
   depende de ello: hipótesis, operacionalización, análisis estadístico, viabilidad).
2. NO le devuelvas la pregunta tal cual. DALE las opciones concretas y típicas de SU caso, en
   lenguaje llano, para que pueda elegir o verificar. Si es «cómo se mide el problema», enumera
   los indicadores que se usan realmente en ese dominio y de dónde se obtiene cada uno.
3. Dile qué tiene que hacer para averiguarlo (a quién preguntar en la organización, qué registro
   revisar, qué reporte pedir, qué paper mirar).
4. Puedes entregar igualmente un borrador PROVISIONAL, pero marcándolo como provisional y dejando
   claro qué parte cambiará cuando lo resuelva. Nunca lo presentes como cerrado."""


# ── 11c. Resguardo ético y de datos (Art. 71 del Reglamento UPAO) ────────────

_FAMILIAS_ETICAS: dict[str, tuple[str, ...]] = {
    "datos clínicos o de salud de personas": (
        "paciente", "clinic", "hospital", "historia clinica", "diagnostic", "melanoma",
        "cancer", "enfermedad", "sintoma", "tratamiento", "dermatolog", "radiograf",
        "tomograf", "salud mental", "psicolog", "farmac", "receta", "triaje",
    ),
    "datos biométricos o de identificación": (
        "biometr", "facial", "rostro", "huella", "iris", "voz de", "reconocimiento de personas",
    ),
    "menores de edad": ("menor de edad", "menores", "nino", "nina", "infantil", "escolar", "adolescent"),
    "datos personales de participantes": (
        "encuesta", "entrevista", "cuestionario", "consentimiento", "participante",
        "datos personales", "expediente", "nomina", "curriculum", "candidato",
    ),
}


def requiere_resguardo_etico(*textos: str) -> str | None:
    """Devuelve el motivo si el proyecto toca personas o datos sensibles; si no, None.

    El Art. 71 del Reglamento UPAO exige comité de ética y consentimiento informado
    cuando hay seres humanos de por medio. Es de las cosas que tumban un proyecto
    ANTES de empezar, así que el sistema nunca debe callárselo.
    """
    blob = _sin_tildes(" ".join(t or "" for t in textos)).lower()
    for motivo, stems in _FAMILIAS_ETICAS.items():
        if any(s in blob for s in stems):
            return motivo
    return None


def aviso_etico(motivo: str) -> str:
    return (
        "⚠️ ESTE PROYECTO TOCA " + motivo.upper() + "\n"
        "Es OBLIGATORIO que se lo adviertas al estudiante en esta respuesta, con claridad y sin "
        "alarmismo, porque condiciona si su proyecto es viable:\n"
        "- Art. 71 del Reglamento de Investigación UPAO: requiere aprobación (o exoneración) de un "
        "Comité de Ética y consentimiento informado de los participantes.\n"
        "- Necesita además autorización FORMAL y por escrito de la organización que custodia esos "
        "datos, y un plan de anonimización antes de usarlos.\n"
        "- Pregúntale explícitamente si ya tiene ese acceso comprometido. NO des por hecho que lo "
        "tiene solo porque nombró una organización: es la causa nº 1 de proyectos que se caen.\n"
        "- Dile que el trámite toma tiempo y que debe entrar en su cronograma (sección 5.1)."
    )


AVISO_SOLUCION_PRIMERO = """\
⚠️ PATRÓN «SOLUCIÓN PRIMERO» DETECTADO EN ESTE MENSAJE
El estudiante nombró tecnologías o un dominio, pero NINGÚN problema medible ni organización.
Es obligatorio que reconduzcas, con respeto y sin sermonear:
1. Reconoce lo que aporta su interés (la tecnología es una buena pista de POR DÓNDE mirar).
2. Explícale en dos líneas por qué el orden correcto es problema → solución, y qué le pasa en
   la sustentación si lo hace al revés (sin variable dependiente medible no hay hipótesis).
3. NO te limites a decírselo: DALE el camino. Propón 3-4 problemas REALES y concretos donde esa
   tecnología encaja, cada uno con: dónde ocurre (tipo de organización), qué se mide hoy y con
   qué indicador, y qué artefacto sería la variable independiente.
4. Pregúntale a cuál tiene acceso real (organización, datos, permisos) — eso decide, no el gusto."""


# ── 9. Bloque de marco institucional para los prompts ────────────────────────

_IDENTIDAD = (
    "## MARCO INSTITUCIONAL UPAO (hechos duros: no los contradigas ni los inventes)\n"
    "Acompañas a un estudiante de **Ingeniería de Computación y Sistemas / Ingeniería de "
    "Sistemas e Inteligencia Artificial de la UPAO (Trujillo, Perú)** en su **PROYECTO** de "
    "tesis: la PROPUESTA, sin resultados, discusión ni conclusiones (esa etapa es posterior)."
)


def _bloques() -> dict[str, str]:
    return {
        "identidad": _IDENTIDAD,
        "estructura": "### Estructura oficial del proyecto\n" + ESTRUCTURA_PROYECTO_UPAO,
        "titulo": "### Reglas del título\n" + REGLAS_TITULO,
        "linea": bloque_linea_investigacion(),
        "tipos": TIPOS_INVESTIGACION_UPAO,
        "problema_primero": MENTALIDAD_PROBLEMA_PRIMERO,
        "no_complacencia": NO_COMPLACENCIA,
        "consejos": CONSEJOS_PRACTICOS,
        "repositorio": PATRON_TITULOS_REPOSITORIO,
    }


# Qué parte del marco necesita CADA rol. Inyectarlo entero a todos diluye las
# instrucciones propias del agente (que son las que definen su salida) y hace que
# el modelo las ignore: cada rol recibe solo lo que usa.
_PERFILES: dict[str, list[str]] = {
    "ideador":    ["identidad", "linea", "repositorio", "problema_primero", "no_complacencia"],
    "elicitador": ["identidad", "titulo", "linea", "tipos", "problema_primero", "no_complacencia"],
    "asesor":     ["identidad", "estructura", "linea", "tipos", "no_complacencia", "consejos"],
    "redactor":   ["identidad", "estructura", "titulo", "tipos", "no_complacencia"],
    "corrector":  ["identidad", "titulo", "no_complacencia"],
    # El validador audita TODO, así que necesita el marco completo.
    "validador":  ["identidad", "estructura", "titulo", "linea", "tipos",
                   "problema_primero", "no_complacencia", "repositorio"],
}


def marco_para(rol: str) -> str:
    """Marco institucional recortado al rol que lo va a usar."""
    b = _bloques()
    claves = _PERFILES.get(rol) or list(b.keys())
    return "\n\n".join(b[k] for k in claves if k in b)


def bloque_marco_upao(incluir_repositorio: bool = True) -> str:
    """Marco institucional COMPLETO (lo usa el conversador general)."""
    b = _bloques()
    orden = ["identidad", "estructura", "titulo", "linea", "tipos",
             "problema_primero", "no_complacencia", "consejos"]
    if incluir_repositorio:
        orden.append("repositorio")
    return "\n\n".join(b[k] for k in orden)


# ── 12. Afirmaciones falsas sobre el proyecto del estudiante ─────────────────

# Frases con las que un agente le atribuye al estudiante una línea, un tema o un sector.
_RE_ATRIBUYE = re.compile(
    r"(?:tu|su)\s+(?:l[íi]nea|subl[íi]nea|[áa]rea|campo|tema|proyecto|investigaci[óo]n|tesis)"
    r"(?:\s+de\s+investigaci[óo]n)?[^.\n;:]{0,140}",
    re.I,
)

# Familias de DOMINIO de aplicación. La línea UPAO es tecnológica y NO fija dominio:
# el sector (educación, salud, agro…) lo decide el estudiante. Si un agente se lo
# atribuye sin que conste, se lo está inventando.
_FAMILIAS_DOMINIO: dict[str, tuple[str, ...]] = {
    "educación":     ("educa", "escolar", "aula", "docent", "pedagog", "aprendizaje",
                      "colegio", "alumno", "ensenan", "academic", "aula"),
    "salud":         ("salud", "medic", "clinic", "hospital", "enferm", "paciente",
                      "farmac", "odontolog", "psicolog"),
    "agro":          ("agric", "agro", "agrari", "cultivo", "cosech", "vivero", "ganader"),
    "finanzas":      ("financ", "banc", "credit", "contab", "tributar", "seguro"),
    "comercio":      ("comerc", "retail", "venta", "market", "cliente"),
    "logística":     ("logistic", "almacen", "inventar", "transport", "distribu"),
    "manufactura":   ("manufactur", "produccion", "planta", "industrial", "minero", "mineria"),
    "turismo":       ("turism", "hotel", "restaurant"),
    "legal":         ("juridic", "legal", "judicial", "notarial"),
    "ambiente":      ("ambient", "ecolog", "residuo", "energet"),
    "construcción":  ("construc", "inmobiliar", "obra civil"),
    "sector público": ("municipal", "gubernament", "estatal", "ciudadan"),
}


def atribuciones_linea_invalidas(texto: str, *contextos: str) -> list[str]:
    """Detecta que el texto le atribuya al estudiante una línea o un DOMINIO que no es suyo.

    La línea del programa es UNA y está fijada por resolución, y es puramente tecnológica:
    no dice nada del sector de aplicación. Si un agente escribe «tu línea de investigación
    sobre inteligencia artificial y educación», se está inventando dos cosas: que existe esa
    línea, y que el estudiante trabaja en educación. Es grave porque condiciona todo lo que
    el estudiante haga después, y ocurre cuando el RAG mete ejemplos temáticos del libro de
    metodología (llenos de aula y rendimiento académico) y el modelo los toma por su contexto.
    """
    problemas: list[str] = []
    if not (texto or "").strip():
        return problemas

    oficial = _sin_tildes(
        LINEA_INVESTIGACION_SISTEMAS + " " + " ".join(n for n, _ in SUBLINEAS_LINEA_03)
    ).lower()
    respaldo = _sin_tildes(" ".join(c or "" for c in contextos)).lower()

    vistos: set[str] = set()
    for m in _RE_ATRIBUYE.finditer(texto):
        frase = m.group(0).strip()
        frase_norm = _sin_tildes(frase).lower()
        for dominio, stems in _FAMILIAS_DOMINIO.items():
            if dominio in vistos:
                continue
            # ¿La frase le atribuye este dominio?
            if not any(s in frase_norm for s in stems):
                continue
            # ¿Está respaldado por la línea oficial o por lo que el estudiante SÍ dijo?
            if any(s in oficial or s in respaldo for s in stems):
                continue
            vistos.add(dominio)
            problemas.append(
                f"ATRIBUCIÓN INVENTADA sobre el proyecto del estudiante: «{frase[:110]}». "
                f"En ninguna parte consta que su proyecto sea del sector «{dominio}». Su línea es "
                f"UNA, fija y puramente tecnológica («{LINEA_INVESTIGACION_SISTEMAS}»): NO determina "
                "el sector de aplicación, que lo elige él. Elimina esa atribución; si aún no tiene "
                "tema, dilo y ofrécele opciones de varios dominios distintos."
            )
    return problemas


def nota_no_aplica(seccion: str | None) -> str:
    """Aviso si la sección pedida es una de las que la plantilla marca NO APLICA."""
    if not seccion:
        return ""
    if _RE_SEC_MARCO_HIST.search(seccion):
        for clave, aviso in SECCIONES_NO_APLICA.items():
            if _RE_SEC_MARCO_HIST.search(clave):
                return f"⚠️ ATENCIÓN — «{clave}»: {aviso}"
    return ""
