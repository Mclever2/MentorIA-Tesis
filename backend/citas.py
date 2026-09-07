"""
Vigencia de las fuentes citadas.

Regla que el sistema debe aplicar y explicar: en un proyecto de investigación las
fuentes deben ser ACTUALES. El criterio operativo es

  - ≤ 3 años  → recomendado (es lo que un jurado espera del grueso de antecedentes)
  - ≤ 5 años  → aceptable (límite superior)
  - > 5 años  → desfasada, salvo excepción justificada

La excepción importa tanto como la regla: las obras SEMINALES (la teoría que
fundamenta el estudio), los textos de metodología, las normas técnicas y la
legislación se citan por su valor fundacional o por su vigencia legal, no por su
fecha. Penalizar a un estudiante por citar a Bandura (1977) en sus bases teóricas
sería un falso positivo, y es justo el error que este módulo evita.

`analizar_vigencia()` es determinista: extrae los años que aparecen en citas y
referencias y los clasifica. Los agentes reciben el conteo, no una impresión.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

VENTANA_RECOMENDADA = 3   # años
VENTANA_MAXIMA = 5        # años

# Antigüedad a partir de la cual ni siquiera cuenta como «reciente pero justificable».
_MUY_ANTIGUA = 15

# Citas en el cuerpo: «(Apellido, 2021)», «Apellido (2021)», «(Apellido et al., 2020)».
_RE_CITA_PARENTESIS = re.compile(r"\(\s*[^()]{0,120}?,\s*((?:19|20)\d{2})[a-z]?\s*(?:,\s*p+\.\s*[\d\-–]+)?\s*\)")
_RE_CITA_NARRATIVA = re.compile(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'’\-]+(?:\s+(?:et\s+al\.|y|&|and)\s+[\wÁÉÍÓÚÑáéíóúñ'’\-]+)?\s*\(\s*((?:19|20)\d{2})[a-z]?\s*\)")
# Referencias APA: «Apellido, N. (2021).»
_RE_REFERENCIA = re.compile(r"^\s*[^\n]{5,200}?\(\s*((?:19|20)\d{2})[a-z]?\s*\)\s*[.—-]", re.MULTILINE)

# Marcadores de fuente que legítimamente puede ser antigua.
_RE_EXCEPCION = re.compile(
    r"\b(norma|ntp\b|iso\s*\d|iec\b|ieee\s*\d|astm|din\b|une\b|reglamento\s+nacional|"
    r"ley\s+n|decreto|resoluci[oó]n|constituci[oó]n|c[oó]digo\s+(?:civil|penal|procesal)|"
    r"hern[aá]ndez[- ]sampieri|sampieri|kerlinger|bunge|creswell|yin\b|popper|kuhn|"
    r"teor[ií]a\s+(?:de|del|general)|modelo\s+seminal|obra\s+seminal|cl[aá]sico)\b",
    re.IGNORECASE,
)


def anio_actual() -> int:
    return date.today().year


@dataclass
class VigenciaFuentes:
    anio_referencia: int
    anios: list[int] = field(default_factory=list)
    recomendadas: list[int] = field(default_factory=list)   # ≤ 3 años
    aceptables: list[int] = field(default_factory=list)     # 4-5 años
    desfasadas: list[int] = field(default_factory=list)     # > 5 años
    posibles_seminales: int = 0

    @property
    def total(self) -> int:
        return len(self.anios)

    @property
    def pct_vigentes(self) -> float:
        """% dentro de la ventana máxima (≤ 5 años)."""
        if not self.anios:
            return 0.0
        return 100.0 * (len(self.recomendadas) + len(self.aceptables)) / len(self.anios)

    @property
    def pct_recomendadas(self) -> float:
        if not self.anios:
            return 0.0
        return 100.0 * len(self.recomendadas) / len(self.anios)

    def resumen(self) -> str:
        if not self.anios:
            return "No se detectaron años de cita en el texto analizado."
        antiguas = sorted(set(self.desfasadas))
        detalle = (
            f"{self.total} citas fechadas: {len(self.recomendadas)} de los últimos "
            f"{VENTANA_RECOMENDADA} años ({self.pct_recomendadas:.0f}%), "
            f"{len(self.aceptables)} de {VENTANA_RECOMENDADA + 1}–{VENTANA_MAXIMA} años, "
            f"{len(self.desfasadas)} con más de {VENTANA_MAXIMA} años "
            f"({100 - self.pct_vigentes:.0f}%)."
        )
        if antiguas:
            muestra = ", ".join(str(a) for a in antiguas[:12])
            detalle += f" Años fuera de ventana: {muestra}."
        if self.posibles_seminales:
            detalle += (
                f" {self.posibles_seminales} de ellas están junto a marcas de obra seminal, "
                "norma o texto de metodología: esas NO se penalizan."
            )
        return detalle

    def veredicto(self) -> str:
        if not self.anios:
            return "sin_datos"
        if self.pct_vigentes >= 80:
            return "vigente"
        if self.pct_vigentes >= 60:
            return "mejorable"
        return "desfasado"


def extraer_anios_citados(texto: str) -> list[int]:
    """Años que aparecen como cita o referencia. No cuenta años del texto corrido
    («en 2019 la empresa creció») para no inflar el diagnóstico."""
    t = texto or ""
    anios: list[int] = []
    for regex in (_RE_CITA_PARENTESIS, _RE_CITA_NARRATIVA, _RE_REFERENCIA):
        anios.extend(int(m) for m in regex.findall(t))
    return anios


def analizar_vigencia(texto: str, anio: int | None = None) -> VigenciaFuentes:
    """Clasifica las citas fechadas del texto según la ventana de vigencia."""
    ref = anio or anio_actual()
    v = VigenciaFuentes(anio_referencia=ref)

    for a in extraer_anios_citados(texto):
        if a > ref + 1:          # año imposible: probablemente no es una cita
            continue
        v.anios.append(a)
        antiguedad = ref - a
        if antiguedad <= VENTANA_RECOMENDADA:
            v.recomendadas.append(a)
        elif antiguedad <= VENTANA_MAXIMA:
            v.aceptables.append(a)
        else:
            v.desfasadas.append(a)

    # Cuántas citas viejas están rodeadas de una marca de excepción legítima.
    if v.desfasadas:
        for m in re.finditer(r"(?:19|20)\d{2}", texto or ""):
            a = int(m.group(0))
            if a in v.desfasadas:
                ventana = (texto or "")[max(0, m.start() - 110): m.end() + 60]
                if _RE_EXCEPCION.search(ventana):
                    v.posibles_seminales += 1

    return v


def bloque_regla_citas(anio: int | None = None, diagnostico: VigenciaFuentes | None = None) -> str:
    """Bloque para inyectar en cualquier prompt de agente."""
    ref = anio or anio_actual()
    texto = (
        "## VIGENCIA DE LAS FUENTES (aplícala siempre)\n"
        f"- Año en curso: {ref}.\n"
        f"- RECOMENDADO: la mayoría de los antecedentes y las fuentes empíricas deben tener "
        f"**{VENTANA_RECOMENDADA} años o menos** ({ref - VENTANA_RECOMENDADA}–{ref}).\n"
        f"- LÍMITE: no deberían superar los **{VENTANA_MAXIMA} años** ({ref - VENTANA_MAXIMA}–{ref}). "
        f"Más antiguas que eso, se consideran desfasadas.\n"
        "- EXCEPCIONES legítimas, que NO se penalizan y NO debes pedir reemplazar: obras SEMINALES "
        "que fundan la teoría del estudio, textos de metodología (p. ej. Hernández-Sampieri), normas "
        "técnicas (ISO, NTP, IEEE), legislación vigente y datos históricos que son el objeto mismo del "
        "análisis. Al citarlas, conviene acompañarlas de una fuente reciente que muestre su vigencia.\n"
        "- Cuando propongas o exijas antecedentes, pide explícitamente que sean de los últimos "
        f"{VENTANA_MAXIMA} años y prioriza los últimos {VENTANA_RECOMENDADA}.\n"
        "- NUNCA inventes una referencia para «actualizar» la bibliografía: si hace falta una fuente "
        "reciente y no la tienes, dilo y describe qué habría que buscar."
    )
    if diagnostico is not None and diagnostico.total:
        texto += f"\n\n### Diagnóstico de las citas del proyecto (medido, no estimado)\n{diagnostico.resumen()}"
    return texto
