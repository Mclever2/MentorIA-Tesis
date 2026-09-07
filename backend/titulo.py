"""
Reglas del TÍTULO de un proyecto de investigación (ítems 1, 2 y 3 de la ficha UPAO).

El ítem 2 de la rúbrica dice: «El título articula las variables, espacio y tiempo
de la investigación». Interpretarlo como «todo título debe llevar lugar y año» es
un error: hay estudios en los que el tiempo no delimita nada (un modelo entrenado
sobre un dataset público versionado, una revisión sistemática, un desarrollo de
software validado en laboratorio) y forzarlo produce títulos falsos.

Este módulo separa las dos preguntas que el sistema confundía:

  1. ¿QUÉ delimitación exige ESTE estudio?  → `politica_delimitacion()`
     Decide, según el tipo/diseño y el origen de los datos, si el espacio y el
     tiempo son EXIGIDOS, RECOMENDADOS u OPCIONALES, y con qué argumento.

  2. ¿EL TÍTULO ACTUAL la cumple?           → `diagnosticar_titulo()`
     Chequeo determinista (sin LLM) de lo que se puede verificar sin opinar:
     número de palabras, presencia de marca temporal, de marca espacial y de
     conectores de relación entre variables.

Lo determinista NO reemplaza a los agentes: les da el terreno firme sobre el que
discutir, para que el panel no invente que «falta el año» cuando el año no aplica,
ni lo dé por bueno cuando sí hacía falta.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from .enfoque import normalizar_tipo

# UPAO: el título no puede exceder 20 palabras (conectores, artículos y fechas incluidos).
MAX_PALABRAS_UPAO = 20
# Por debajo de esto casi nunca caben variables + unidad de análisis.
MIN_PALABRAS_RAZONABLE = 8

Exigencia = Literal["exigida", "recomendada", "opcional", "no_aplica"]


# ── Detectores deterministas ────────────────────────────────────────────────

_RE_ANIO = re.compile(r"\b(19|20)\d{2}\b")
_RE_RANGO_ANIOS = re.compile(r"\b(19|20)\d{2}\s*[-–—/aA]\s*(19|20)\d{2}\b")
_RE_PERIODO = re.compile(
    r"\b(periodo|período|durante|semestre|trimestre|bienio|quinquenio|campa[nñ]a|"
    r"a[nñ]o\s+(?:acad[eé]mico|lectivo|fiscal)|enero|febrero|marzo|abril|mayo|junio|"
    r"julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)

# Marcas de lugar: institución concreta, tipo de organización o territorio.
_RE_INSTITUCION = re.compile(
    r"\b(empresa|compa[nñ][ií]a|corporaci[oó]n|hospital|cl[ií]nica|centro\s+de\s+salud|"
    r"puesto\s+de\s+salud|essalud|minsa|instituci[oó]n\s+educativa|i\.?\s?e\.?\b|colegio|"
    r"universidad|facultad|escuela\s+profesional|municipalidad|gerencia|direcci[oó]n\s+regional|"
    r"ministerio|banco|caja\s+municipal|cooperativa|mype|pyme|planta|f[aá]brica|"
    r"agencia|sucursal|almac[eé]n|tienda|mercado|asociaci[oó]n|comunidad|"
    r"laboratorio|consultorio|farmacia|bot[ií]ca|hotel|restaurante)\b",
    re.IGNORECASE,
)
_RE_TERRITORIO = re.compile(
    r"\b(distrito|provincia|regi[oó]n|departamento|ciudad|localidad|caser[ií]o|"
    r"centro\s+poblado|valle|cuenca|sector|zona|urbanizaci[oó]n|urb\.|a\.?\s?h\.?\b)\b",
    re.IGNORECASE,
)
# Topónimos frecuentes en el ámbito de la UPAO (Trujillo y su zona de influencia).
_RE_TOPONIMO = re.compile(
    r"\b(trujillo|la\s+libertad|per[uú]|lima|piura|chiclayo|lambayeque|cajamarca|"
    r"[aá]ncash|chimbote|huanchaco|moche|laredo|v[ií]ru|chepen|pacasmayo|otuzco|"
    r"santiago\s+de\s+chuco|s[aá]nchez\s+carri[oó]n|ascope|gran\s+chim[uú]|julcan|"
    r"boliv[aá]r|pataz|arequipa|cusco|piura|tumbes|amazonas|loreto|ucayali|jun[ií]n)\b",
    re.IGNORECASE,
)

# Conectores que articulan dos constructos (indicio de que el título nombra variables).
_RE_RELACION = re.compile(
    r"\b(influencia\s+de|efecto\s+de|impacto\s+de|relaci[oó]n\s+entre|asociaci[oó]n\s+entre|"
    r"incidencia\s+de|correlaci[oó]n\s+entre|comparaci[oó]n\s+entre|"
    r"para\s+(?:mejorar|optimizar|reducir|incrementar|aumentar|disminuir|automatizar|"
    r"predecir|detectar|clasificar|estimar)|"
    r"\bpara\s+la\s+(?:mejora|optimizaci[oó]n|reducci[oó]n|detecci[oó]n|predicci[oó]n))\b",
    re.IGNORECASE,
)

# En titulos tecnologicos el par se articula distinto: ARTEFACTO + medio + PROPOSITO
# ("Sistema ... basado en vision artificial para la deteccion de ...").
_RE_RELACION_TECNO = re.compile(
    r"\b(mediante|utilizando|usando|aplicando|basad[oa]s?\s+en|a\s+trav[eé]s\s+de|"
    r"con\s+el\s+uso\s+de|empleando|apoyad[oa]\s+en)\b",
    re.IGNORECASE,
)

# Datos que NO provienen de una población situada: el «espacio» es el corpus.
_RE_DATOS_SECUNDARIOS = re.compile(
    r"\b(dataset|data\s?set|corpus|banco\s+de\s+im[aá]genes|base\s+de\s+datos\s+p[uú]blica|"
    r"repositorio\s+p[uú]blico|kaggle|imagenet|ham10000|isic|mimic|uci|open\s?data|"
    r"datos\s+abiertos|datos\s+secundarios|benchmark|simulaci[oó]n|revisi[oó]n\s+sistem[aá]tica|"
    r"revisi[oó]n\s+de\s+literatura|metaan[aá]lisis|meta-?an[aá]lisis)\b",
    re.IGNORECASE,
)


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")


def contar_palabras_titulo(texto: str) -> int:
    """Palabras del título, descartando una etiqueta inicial tipo «Título: …»."""
    t = (texto or "").strip()
    t = re.sub(r"(?i)^\s*t[íi]tulo[^\n:]*[:\n]", " ", t, count=1)
    t = t.split("\n")[0] if t.count("\n") else t
    return len(re.findall(r"\S+", t))


def limpiar_titulo(texto: str) -> str:
    """Primera línea útil, sin la etiqueta «Título:» ni comillas de adorno."""
    t = (texto or "").strip()
    t = re.sub(r"(?i)^\s*t[íi]tulo[^\n:]*:", "", t, count=1).strip()
    t = t.split("\n")[0].strip()
    return t.strip(" \"'«»*_#").strip()


@dataclass
class DiagnosticoTitulo:
    """Lo que se puede afirmar del título SIN opinar."""
    titulo: str
    n_palabras: int
    excede_limite: bool
    demasiado_corto: bool
    tiene_tiempo: bool
    tiene_espacio: bool
    marcas_tiempo: list[str] = field(default_factory=list)
    marcas_espacio: list[str] = field(default_factory=list)
    tiene_conector_relacion: bool = False
    menciona_datos_secundarios: bool = False

    def resumen(self) -> str:
        partes = [
            f"{self.n_palabras} palabras"
            + (f" (excede el máximo UPAO de {MAX_PALABRAS_UPAO})" if self.excede_limite else ""),
            f"delimitación temporal: {'sí — ' + ', '.join(self.marcas_tiempo) if self.tiene_tiempo else 'NO detectada'}",
            f"delimitación espacial: {'sí — ' + ', '.join(self.marcas_espacio) if self.tiene_espacio else 'NO detectada'}",
            f"conector que articula variables: {'sí' if self.tiene_conector_relacion else 'no detectado'}",
        ]
        if self.menciona_datos_secundarios:
            partes.append("el título apunta a datos secundarios / dataset (el «espacio» sería el corpus)")
        return "; ".join(partes)


def diagnosticar_titulo(titulo: str) -> DiagnosticoTitulo:
    """Chequeo determinista del título. No juzga el contenido: solo lo verificable."""
    t = limpiar_titulo(titulo)
    n = contar_palabras_titulo(t)

    marcas_t: list[str] = []
    if _RE_RANGO_ANIOS.search(t):
        marcas_t.append(f"rango de años «{_RE_RANGO_ANIOS.search(t).group(0)}»")
    elif _RE_ANIO.search(t):
        marcas_t.append(f"año «{_RE_ANIO.search(t).group(0)}»")
    m_periodo = _RE_PERIODO.search(t)
    if m_periodo:
        marcas_t.append(f"periodo «{m_periodo.group(0)}»")

    marcas_e: list[str] = []
    for regex, etiqueta in (
        (_RE_INSTITUCION, "institución"),
        (_RE_TERRITORIO, "ámbito territorial"),
        (_RE_TOPONIMO, "topónimo"),
    ):
        m = regex.search(t)
        if m:
            marcas_e.append(f"{etiqueta} «{m.group(0)}»")

    return DiagnosticoTitulo(
        titulo=t,
        n_palabras=n,
        excede_limite=n > MAX_PALABRAS_UPAO,
        demasiado_corto=0 < n < MIN_PALABRAS_RAZONABLE,
        tiene_tiempo=bool(marcas_t),
        tiene_espacio=bool(marcas_e),
        marcas_tiempo=marcas_t,
        marcas_espacio=marcas_e,
        tiene_conector_relacion=bool(_RE_RELACION.search(t) or _RE_RELACION_TECNO.search(t)),
        menciona_datos_secundarios=bool(_RE_DATOS_SECUNDARIOS.search(t)),
    )


# ── ¿Qué del título NO está respaldado por el proyecto? ─────────────────────

# Palabras que van en mayúscula por posición o convención, no por ser un nombre propio.
_NO_PROPIAS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "y", "e", "o", "u", "para",
    "por", "con", "sin", "sobre", "entre", "su", "sus", "al", "a", "que", "se", "como",
    "analisis", "estudio", "modelo", "sistema", "propuesta", "diseno", "aplicacion",
    "evaluacion", "relacion", "influencia", "impacto", "efecto", "implementacion",
    "desarrollo", "gestion", "mejora", "deteccion", "clasificacion", "prediccion",
}


def datos_no_respaldados(titulo: str, proyecto: str) -> list[str]:
    """Datos del título que NO aparecen en el texto del proyecto.

    Detecta el error más caro del panel: para «cumplir» la delimitación, el
    proponente añade una ciudad o un año verosímiles que el proyecto nunca dijo, y
    el estudiante se lleva un título que no puede defender. Solo se miran cosas
    verificables por presencia literal — años y nombres propios —, no matices de
    significado; de eso se ocupa el agente verificador.
    """
    t = limpiar_titulo(titulo)
    if not t or not (proyecto or "").strip():
        return []

    ref = _sin_acentos(proyecto)
    sospechosos: list[str] = []

    for anio in dict.fromkeys(m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", t)):
        if anio not in ref:
            sospechosos.append(f"el año «{anio}» no aparece en el proyecto")

    # Nombres propios: mayúscula inicial fuera de la primera palabra y no marcador «[…]».
    palabras = re.findall(r"[«»\"'\[\]()]*([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ\-]{2,})", t)
    primera = t.split()[0].strip("«»\"'[]()") if t.split() else ""
    vistos: set[str] = set()
    for p in palabras:
        if p == primera:
            continue
        plano = _sin_acentos(p)
        if plano in _NO_PROPIAS or plano in vistos:
            continue
        vistos.add(plano)
        if plano not in ref:
            sospechosos.append(f"«{p}» no aparece en el proyecto")

    return sospechosos


# ── Política: ¿qué delimitación exige ESTE estudio? ─────────────────────────

@dataclass
class PoliticaDelimitacion:
    espacio: Exigencia
    tiempo: Exigencia
    variables: Exigencia
    motivo_espacio: str
    motivo_tiempo: str
    motivo_variables: str

    def bloque(self) -> str:
        etiqueta = {
            "exigida":     "EXIGIDA",
            "recomendada": "RECOMENDADA",
            "opcional":    "OPCIONAL",
            "no_aplica":   "NO APLICA",
        }
        return (
            f"- Variables en el título: **{etiqueta[self.variables]}** — {self.motivo_variables}\n"
            f"- Delimitación ESPACIAL (unidad de análisis / contexto): **{etiqueta[self.espacio]}** — {self.motivo_espacio}\n"
            f"- Delimitación TEMPORAL (periodo de referencia): **{etiqueta[self.tiempo]}** — {self.motivo_tiempo}"
        )


_MOTIVO_VARIABLES = {
    "cuantitativa": (
        "el ítem 2 exige que se lean las variables; en un estudio cuantitativo deben "
        "reconocerse la independiente y la dependiente (o la única variable, si es descriptivo)"
    ),
    "cualitativa": (
        "en cualitativa no hay «variables» sino categorías/fenómeno: el título debe nombrar "
        "el fenómeno estudiado y los sujetos, no forzar un par VI–VD"
    ),
    "mixta": "deben leerse tanto las variables de la fase cuantitativa como el fenómeno de la cualitativa",
    "tecnologica": (
        "el título debe nombrar el ARTEFACTO (qué se construye) y la dimensión que mejora "
        "(qué problema resuelve): eso hace las veces de par variable independiente–dependiente"
    ),
    "innovacion": (
        "el título debe nombrar la propuesta/solución y el beneficio o problema que atiende"
    ),
}


def politica_delimitacion(
    tipo_investigacion: str | None,
    diseno: str | None = None,
    contexto_proyecto: str = "",
) -> PoliticaDelimitacion:
    """
    Decide qué debe llevar el título de ESTE proyecto y por qué.

    `contexto_proyecto` es texto libre del proyecto (problema, objetivos, población,
    metodología). Se usa solo para detectar señales duras: si los datos son
    secundarios/públicos o si hay una población situada en el tiempo.
    """
    tipo = normalizar_tipo(tipo_investigacion)
    ctx = _sin_acentos(f"{contexto_proyecto} {diseno or ''}").lower()
    dis = _sin_acentos(diseno or "").lower()

    datos_secundarios = bool(_RE_DATOS_SECUNDARIOS.search(ctx))
    poblacion_situada = bool(
        re.search(r"\b(poblacion|muestra|participantes|encuestad|entrevistad|pacientes|"
                  r"estudiantes|trabajadores|colaboradores|usuarios|clientes|docentes)\b", ctx)
    )
    serie_historica = bool(
        re.search(r"\b(historic|retrospectiv|longitudinal|serie de tiempo|series de tiempo|"
                  r"periodo|registros de|expedientes|historias clinicas|datos de los anos)\b", ctx)
    )
    es_experimental = "experimental" in dis or "cuasi" in dis
    es_revision = bool(re.search(r"\b(revision sistematica|metaanalisis|meta-analisis|documental)\b", ctx))

    # ── ESPACIO ──
    if es_revision:
        espacio: Exigencia = "opcional"
        motivo_e = (
            "es un estudio documental: no hay un lugar donde se recojan datos. Lo que delimita "
            "aquí es el alcance de las fuentes (bases consultadas, idioma, ámbito geográfico de "
            "los estudios incluidos), y eso va en la delimitación, no necesariamente en el título"
        )
    elif datos_secundarios and not poblacion_situada:
        espacio = "recomendada"
        motivo_e = (
            "los datos no vienen de una población situada sino de un dataset/corpus: el «espacio» "
            "del ítem 2 lo cumple NOMBRAR ESA FUENTE (p. ej. «sobre el dataset ISIC 2019»), no un "
            "distrito. Si además se valida en una institución real, esa institución sí va en el título"
        )
    elif tipo in ("cuantitativa", "cualitativa", "mixta"):
        espacio = "exigida"
        motivo_e = (
            "el estudio recoge datos de una población concreta; sin la unidad de análisis "
            "(institución, sector o ámbito territorial) el título no delimita a quién se estudia "
            "y el ítem 2 se pierde"
        )
    else:  # tecnológica / innovación con validación en campo
        espacio = "exigida" if poblacion_situada else "recomendada"
        motivo_e = (
            "la solución se implanta y valida en una organización concreta: nombrarla delimita el "
            "alcance del artefacto"
            if poblacion_situada else
            "si el artefacto se valida en una organización o entorno concreto, nómbralo; si solo se "
            "valida en laboratorio o sobre un dataset, nombra ese entorno en su lugar y no inventes "
            "una empresa"
        )

    # ── TIEMPO ──
    if serie_historica:
        tiempo: Exigencia = "exigida"
        motivo_t = (
            "los datos tienen un periodo de referencia (registros/serie histórica): sin ese rango "
            "el estudio no es replicable ni acotado — el título debe llevarlo"
        )
    elif es_revision:
        tiempo = "exigida"
        motivo_t = (
            "en una revisión la ventana de búsqueda ES parte del objeto de estudio; debe aparecer "
            "el rango de años cubierto"
        )
    elif tipo in ("cuantitativa", "mixta") or poblacion_situada:
        tiempo = "recomendada"
        motivo_t = (
            "el trabajo de campo ocurre en un periodo determinado; el año de aplicación acota el "
            "estudio y es la práctica dominante en el repositorio UPAO. Ponlo salvo que el fenómeno "
            "sea deliberadamente atemporal — y en ese caso decláralo en la delimitación"
        )
    elif tipo == "cualitativa" and not datos_secundarios:
        tiempo = "recomendada"
        motivo_t = (
            "el trabajo de campo cualitativo también ocurre en un periodo; si el fenómeno se estudia "
            "en un momento concreto, indícalo"
        )
    elif es_experimental and not datos_secundarios:
        tiempo = "recomendada"
        motivo_t = "el periodo de aplicación del experimento acota los resultados"
    else:  # tecnológica / innovación sobre dataset o laboratorio
        tiempo = "opcional"
        motivo_t = (
            "un artefacto validado sobre un dataset versionado o en laboratorio NO se delimita por "
            "año: forzar «2026» en el título añade una falsedad. El año va en el cronograma y, si "
            "el dataset tiene versión/año, ese año sí es informativo (p. ej. «ISIC 2019»)"
        )

    return PoliticaDelimitacion(
        espacio=espacio,
        tiempo=tiempo,
        variables="exigida",
        motivo_espacio=motivo_e,
        motivo_tiempo=motivo_t,
        motivo_variables=_MOTIVO_VARIABLES.get(tipo, _MOTIVO_VARIABLES["cuantitativa"]),
    )


# ── Bloque para inyectar en los prompts ─────────────────────────────────────

def bloque_regla_titulo(
    tipo_investigacion: str | None,
    diseno: str | None = None,
    contexto_proyecto: str = "",
    universidad: str = "",
    titulo_actual: str = "",
    evidencia_corpus: str = "",
) -> str:
    """Bloque completo de reglas del título, listo para un prompt de agente."""
    pol = politica_delimitacion(tipo_investigacion, diseno, contexto_proyecto)
    es_upao = "upao" in _sin_acentos(universidad).lower() or "antenor" in _sin_acentos(universidad).lower()

    partes = ["## REGLAS DEL TÍTULO (ítems 1, 2 y 3 de la ficha)"]

    if es_upao or not universidad:
        partes.append(
            f"- LÍMITE DURO: máximo {MAX_PALABRAS_UPAO} palabras, contando artículos, preposiciones, "
            "conectores, siglas y fechas. Cuéntalas antes de entregar."
        )
    partes.append(
        "- El título es una PROMESA: lo que anuncia debe estar en los objetivos y en la metodología. "
        "No prometas lo que el proyecto no hace."
    )
    partes.append("\n### Qué debe delimitar ESTE proyecto (no es igual para todos)")
    partes.append(pol.bloque())
    partes.append(
        "\nSi una delimitación está marcada OPCIONAL o NO APLICA, NO la inventes para «cumplir la "
        "rúbrica»: un lugar o un año falsos son un error más grave que su ausencia. En ese caso "
        "explica en una línea por qué no corresponde, para que el estudiante pueda defenderlo ante el jurado."
    )
    partes.append(
        "Si está marcada EXIGIDA o RECOMENDADA y el proyecto NO da el dato (no se sabe la empresa, "
        "el periodo), NO lo inventes: deja un marcador explícito «[institución]» / «[periodo]» y pídeselo al estudiante."
    )

    if titulo_actual:
        diag = diagnosticar_titulo(titulo_actual)
        partes.append(f"\n### Diagnóstico del título actual (verificado, no opinión)\n«{diag.titulo}»\n{diag.resumen()}")

    if evidencia_corpus:
        partes.append(f"\n### Títulos reales aprobados en el repositorio UPAO (úsalos como patrón, no los copies)\n{evidencia_corpus}")

    return "\n".join(partes)
