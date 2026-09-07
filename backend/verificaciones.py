"""
Hechos MEDIDOS sobre un texto, para dárselos ya resueltos a cualquier agente.

Un LLM falla de forma sistemática en dos operaciones que aquí son decisivas:
contar (las palabras de un título, los años de las citas) y aplicar una regla
condicional sin desviarse (qué delimitación exige ESTE tipo de estudio y cuál no).
Cuando el agente las estima, aparecen las dos caras del mismo error: aprueba un
título de 24 palabras sin lugar ni periodo, o exige un año a un estudio donde el
año no delimita nada.

`mediciones_de_seccion()` resuelve eso fuera del modelo y devuelve un bloque de
texto que los prompts inyectan con la instrucción de darlo por cierto. Es el único
sitio donde vive esa lógica: lo usan el auditor del grafo grande, el barrido de la
revisión completa y el debate rápido.
"""

from __future__ import annotations

import re
import unicodedata


def es_seccion_titulo(seccion: str) -> bool:
    s = (seccion or "").lower()
    return "título" in s or "titulo" in s or "title" in s


def mediciones_de_seccion(
    seccion: str,
    texto: str,
    tipo_investigacion: str | None = None,
    diseno: str | None = None,
    contexto_proyecto: str = "",
    incluir_citas: bool = True,
) -> str:
    """Bloque de mediciones aplicables a `seccion`.

    Devuelve siempre algo legible: si no hay nada que medir, lo dice, para que el
    prompt no quede con un hueco que el modelo intente rellenar.
    """
    from .citas import analizar_vigencia, bloque_regla_citas
    from .titulo import diagnosticar_titulo, politica_delimitacion

    partes: list[str] = []

    if es_seccion_titulo(seccion):
        diag = diagnosticar_titulo(texto)
        pol = politica_delimitacion(tipo_investigacion, diseno, contexto_proyecto or texto)
        partes.append(
            "### Título — medición\n"
            f"«{diag.titulo}»\n{diag.resumen()}\n\n"
            "### Título — qué delimitación exige ESTE estudio\n"
            f"{pol.bloque()}\n"
            "NO penalices la ausencia de una delimitación marcada OPCIONAL o NO APLICA: en ese caso "
            "el ítem del título se cumple igual, y exigirla empujaría al estudiante a inventar un "
            "lugar o un año. SÍ penaliza la ausencia de una EXIGIDA, y penaliza también un lugar o "
            "un año que el proyecto no respalde."
        )

    if incluir_citas:
        vig = analizar_vigencia(texto)
        if vig.total:
            partes.append(
                "### Vigencia de las fuentes citadas\n" + bloque_regla_citas(diagnostico=vig)
            )

    return "\n\n".join(partes) or "(no hay mediciones aplicables a esta sección)"


# ── Contradicciones con una medición ────────────────────────────────────────
#
# Decirle al modelo «da estas mediciones por ciertas» no basta. Se observó al
# auditor calificar «no se delimita el contexto geográfico ni temporal» sobre un
# título que dice «…de empresas Trujillo 2026», con la medición delante diciendo
# que ambas delimitaciones están. Eso son 5 puntos que el alumno pierde por algo
# que su título SÍ tiene, y es el peor error posible: sanciona lo que está bien.
# Aquí se detecta esa contradicción para poder devolvérsela al modelo y que
# recalifique ese ítem, en vez de corregirle la nota por nuestra cuenta.

# «ni» es su propio ancla de negación, no solo la cola de un «no» anterior: en
# «no menciona las variables (independiente y dependiente) ni delimita el contexto
# temporal» el «no» queda a más de la ventana de distancia del hecho negado, así
# que sin este ancla la contradicción medida se colaba entera.
_NEGACION = r"(?:no\s+(?:se\s+)?\w*|ni\s+\w*|sin|falta[n]?|carece[n]?|ausencia|omite|omisi[oó]n)"

_MARCAS_CONTRADICCION = {
    "espacio": r"(?:espacial|geogr[aá]fic\w*|lugar|localidad|ciudad|[aá]mbito territorial)",
    "tiempo":  r"(?:temporal|periodo|per[ií]odo|\ba[nñ]o\b|marco temporal)",
}

# Cuánto texto puede haber entre la negación y aquello que se niega para seguir
# siendo la misma afirmación. «no articula las variables, espacio y tiempo» cabe;
# dos frases seguidas que hablan de cosas distintas, no.
_VENTANA_NEGACION = 90

_RE_SOBRE_FUENTES = re.compile(r"(cita|referencia|fuente|autor|bibliograf|public)")


def contradicciones_titulo(razon: str, titulo: str) -> list[str]:
    """Hechos del título que `razon` niega y la medición desmiente.

    Devuelve frases listas para devolvérselas al evaluador. Vacío si la
    justificación no contradice nada medido —que es el caso normal—.
    """
    from .titulo import diagnosticar_titulo

    texto = unicodedata.normalize("NFKD", razon or "").encode("ascii", "ignore").decode().lower()
    if not texto.strip():
        return []
    # Una justificación que habla de las fuentes y no del título no se toca: ahí el
    # año que falta es el de la cita, no el del periodo de estudio.
    if _RE_SOBRE_FUENTES.search(texto) and "titul" not in texto:
        return []

    diag = diagnosticar_titulo(titulo)
    presentes = {
        "espacio": (diag.tiene_espacio, "la delimitación ESPACIAL",
                    ", ".join(diag.marcas_espacio) if getattr(diag, "marcas_espacio", None) else ""),
        "tiempo":  (diag.tiene_tiempo, "la delimitación TEMPORAL",
                    ", ".join(diag.marcas_tiempo) if getattr(diag, "marcas_tiempo", None) else ""),
    }

    hallazgos: list[str] = []
    for clave, (esta, etiqueta, marcas) in presentes.items():
        if not esta:
            continue
        marca = _MARCAS_CONTRADICCION[clave]
        patron = re.compile(
            rf"{_NEGACION}\b.{{0,{_VENTANA_NEGACION}}}?{marca}", re.S)
        m = patron.search(texto)
        # «las citas no indican el año» habla de las fuentes, no del título: el año
        # que falta ahí es otro y corregirlo sería silenciar una observación válida.
        if m and not _RE_SOBRE_FUENTES.search(m.group(0)):
            detalle = f" («{marcas}»)" if marcas else ""
            hallazgos.append(
                f"Dijiste que falta {etiqueta} en el título, pero la medición verificada la "
                f"encuentra{detalle}. Corrige esa afirmación y vuelve a puntuar el ítem sin ese motivo."
            )
    return hallazgos
