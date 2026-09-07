"""
Alcance de evaluación: qué partes del proyecto quiere que se le evalúen.

Un proyecto de tesis se escribe por partes, durante meses. El sistema, en
cambio, calificaba siempre los 33 ítems de la rúbrica: al estudiante que solo
tenía título e hipótesis le exigía metodología, presupuesto y referencias, le
marcaba 0 en todo lo que aún no había escrito y hundía la nota por trabajo que
todavía no le tocaba entregar. Eso desinforma y desmotiva.

Con el alcance, el estudiante declara en qué está trabajando y:

  · el barrido solo lee y califica las unidades declaradas (menos tokens);
  · los ítems fuera del alcance quedan «no evaluados» y NO cuentan para el
    máximo, así que no restan;
  · un ítem RELACIONAL cuyo referente aún no existe (p. ej. «el objetivo guarda
    relación con el problema» sin problema escrito) no se penaliza: se convierte
    en una observación formativa;
  · los agentes reciben instrucciones explícitas de no exigir lo no declarado.

La nota se informa entonces sobre lo declarado, acompañada del avance real
sobre la rúbrica completa, para que el alumno nunca confunda «16 sobre lo que
entregué» con «16 en la sustentación».
"""

from __future__ import annotations

import logging

from backend.config import (
    RUBRICA_GRUPOS_UPAO,
    RUBRICA_ITEMS_UPAO,
    _buscar_items_seccion,
)

logger = logging.getLogger(__name__)

# Contenido mínimo para dar una sección por "empezada". Ajustado a la longitud
# real de las secciones más cortas de un proyecto: un título de tesis completo
# ronda los 100-180 caracteres y una hipótesis bien redactada ~160. Umbrales más
# altos las daban por inexistentes y dejaban fuera del alcance justo lo que el
# alumno acababa de escribir. Por debajo de esto sí es un encabezado suelto (el
# índice ya descarta las secciones de menos de 45).
_MIN_CHARS_SECCION = 80

TODOS_LOS_GRUPOS: list[str] = [nombre for nombre, _ in RUBRICA_GRUPOS_UPAO]
_ITEMS_POR_GRUPO: dict[str, list[int]] = {n: list(items) for n, items in RUBRICA_GRUPOS_UPAO}


def grupos_disponibles() -> list[dict]:
    """Catálogo de grupos evaluables para pintar el selector en el frontend."""
    return [
        {
            "grupo": nombre,
            "items": list(items),
            "descripcion": RUBRICA_ITEMS_UPAO.get(items[0], "")[:120] if items else "",
        }
        for nombre, items in RUBRICA_GRUPOS_UPAO
    ]


def items_de_grupos(grupos: list[str]) -> set[int]:
    seleccion: set[int] = set()
    for grupo in grupos or []:
        seleccion.update(_ITEMS_POR_GRUPO.get(grupo, []))
    return seleccion


def grupos_de_items(items: set[int]) -> list[str]:
    """Grupos tocados por un conjunto de ítems (para el camino inverso)."""
    return [
        nombre for nombre, nums in RUBRICA_GRUPOS_UPAO
        if any(n in items for n in nums)
    ]


def _items_con_contenido(doc) -> set[int]:
    """Ítems de rúbrica cuya sección existe en el proyecto CON contenido real."""
    cubiertos: set[int] = set()
    for stat in (getattr(doc, "stats", None) or []):
        if stat.get("chars", 0) < _MIN_CHARS_SECCION:
            continue
        cubiertos.update(_buscar_items_seccion(stat.get("seccion", "")))
    return cubiertos


def alcance_sugerido(doc) -> dict:
    """Alcance premarcado según lo que el estudiante REALMENTE tiene escrito.

    Se propone, no se impone: el selector llega con estos grupos marcados y el
    estudiante añade o quita antes de evaluar. Un grupo entra si al menos un
    tercio de sus ítems tiene contenido, para no proponer un capítulo entero
    porque se coló una frase suelta.
    """
    cubiertos = _items_con_contenido(doc)
    sugeridos = [
        nombre for nombre, items in RUBRICA_GRUPOS_UPAO
        if items and len([n for n in items if n in cubiertos]) >= max(1, len(items) // 3)
    ]
    if not sugeridos:
        # Nunca dejamos el alcance vacío: sin nada que evaluar no hay respuesta
        # útil que dar. Con lo poco que haya, se propone su grupo.
        sugeridos = grupos_de_items(cubiertos) or [TODOS_LOS_GRUPOS[0]]

    alcance = {
        "modo":   "auto",
        "grupos": sugeridos,
        "items":  sorted(items_de_grupos(sugeridos)),
    }
    logger.info(f"[alcance] Sugerido automáticamente: {', '.join(sugeridos)}")
    return alcance


def normalizar(grupos: list[str] | None, doc=None) -> dict:
    """Alcance declarado por el estudiante, saneado."""
    validos = [g for g in (grupos or []) if g in _ITEMS_POR_GRUPO]
    if not validos:
        validos = list(TODOS_LOS_GRUPOS)
    return {
        "modo":   "declarado",
        "grupos": validos,
        "items":  sorted(items_de_grupos(validos)),
    }


def completo() -> dict:
    """Alcance = proyecto entero (comportamiento histórico)."""
    return {
        "modo":   "declarado",
        "grupos": list(TODOS_LOS_GRUPOS),
        "items":  sorted(RUBRICA_ITEMS_UPAO.keys()),
    }


# Secciones de las rúbricas POR TIPO (cuanti/cuali/mixto/tecnológico/innovación)
# que no tienen equivalente literal en la plantilla UPAO y que el emparejador
# semántico no resuelve. Sin esta tabla, la métrica complementaria seguía
# calificando el plan de evaluación del artefacto o el marco teórico de un
# proyecto cualitativo aunque el estudiante no los hubiera declarado: el informe
# se contradecía consigo mismo, porque la nota oficial sí respetaba el alcance.
#
# Se mapean a GRUPOS de la rúbrica UPAO (no a ítems) porque la correspondencia
# es de área temática, no de criterio: lo único que se decide aquí es si la
# sección cae dentro de lo que el estudiante pidió evaluar.
_GRUPO_POR_SECCION_TIPO: dict[str, str] = {
    # Delimitación y supuestos → van con el planteamiento del problema.
    "limitaciones del estudio":                        "PLANTEAMIENTO DEL PROBLEMA",
    "limitaciones y alcance del estudio":              "PLANTEAMIENTO DEL PROBLEMA",
    "limitaciones y supuestos del entorno":            "PLANTEAMIENTO DEL PROBLEMA",
    "preguntas de investigacion":                      "PLANTEAMIENTO DEL PROBLEMA",
    "preguntas de investigacion cualitativas":         "PLANTEAMIENTO DEL PROBLEMA",
    # Marco teórico con sus variantes por tipo (el emparejador falla por la
    # concordancia de género: «teórico» frente a «base teórica»).
    "marco teorico":                                   "MARCO TEÓRICO",
    "marco teorico referencial":                       "MARCO TEÓRICO",
    # Lo que en un estudio cualitativo hace de hipótesis.
    "supuestos de investigacion y categorias aprioristicas": "HIPÓTESIS Y VARIABLES",
    # Diseño, ejecución y evaluación del artefacto o de la solución.
    "requisitos y especificacion del artefacto":       "MARCO METODOLÓGICO",
    "estrategia de demostracion":                      "MARCO METODOLÓGICO",
    "plan de evaluacion del artefacto":                "MARCO METODOLÓGICO",
    "participantes escenario y muestreo cualitativo":  "MARCO METODOLÓGICO",
    "lean canvas modelo de negocio":                   "MARCO METODOLÓGICO",
    "metricas aprendizaje validado y criterios de pivote": "MARCO METODOLÓGICO",
    "segmento de clientes early adopters y muestreo de validacion": "MARCO METODOLÓGICO",
    # Difusión del resultado: es parte del plan de ejecución del proyecto.
    "comunicacion y difusion de la contribucion":      "ASPECTOS ADMINISTRATIVOS",
}


def _normalizar_titulo(titulo: str) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode().lower()
    # Se recorta lo que va entre paréntesis: las rúbricas añaden ahí matices
    # («(modelos de innovación y emprendimiento)») que no cambian el área.
    t = re.sub(r"\([^)]*\)", " ", t)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip()


def seccion_tipo_en_alcance(doc, titulo: str) -> bool:
    """¿La sección de la rúbrica POR TIPO entra en el alcance declarado?

    Devuelve True cuando no se puede determinar: ante la duda se evalúa, que es
    menos dañino que ocultarle al estudiante una parte que sí había declarado.
    """
    if es_total(doc):
        return True

    permitidos = items_en_alcance(doc)
    items = set(_buscar_items_seccion(titulo or ""))
    if items:
        return bool(items & permitidos)

    grupo = _GRUPO_POR_SECCION_TIPO.get(_normalizar_titulo(titulo))
    if grupo:
        return bool(set(_ITEMS_POR_GRUPO.get(grupo, [])) & permitidos)

    logger.info(
        f"[alcance] Sección de rúbrica por tipo sin equivalencia conocida: "
        f"«{titulo}» — se evalúa por defecto."
    )
    return True


def items_en_alcance(doc) -> set[int]:
    """Ítems que SÍ se califican. Sin alcance declarado, se califica todo."""
    alcance = getattr(doc, "alcance", None) or {}
    items = alcance.get("items")
    if not items:
        return set(RUBRICA_ITEMS_UPAO.keys())
    return {int(n) for n in items}


def es_total(doc) -> bool:
    """True si el alcance cubre la rúbrica completa (no hay nada que filtrar)."""
    return items_en_alcance(doc) >= set(RUBRICA_ITEMS_UPAO.keys())


def seccion_en_alcance(doc, seccion: str) -> bool:
    """¿Esta sección del proyecto contiene algún ítem del alcance declarado?"""
    if es_total(doc):
        return True
    items_seccion = set(_buscar_items_seccion(seccion or ""))
    if not items_seccion:
        # Sección que no mapea a ningún ítem (anexos, carátula): no estorba, se
        # deja pasar para que siga sirviendo de contexto de coherencia.
        return True
    return bool(items_seccion & items_en_alcance(doc))


def bloque_prompt(doc) -> str:
    """Instrucción de alcance para inyectar en los prompts de los agentes.

    Es el texto que evita el daño real: sin él, los agentes piden metodología a
    quien apenas está formulando su problema y lo califican por no tenerla.
    """
    if es_total(doc):
        return ""

    alcance = getattr(doc, "alcance", None) or {}
    declarados = ", ".join(alcance.get("grupos") or []) or "(sin declarar)"
    fuera = [g for g in TODOS_LOS_GRUPOS if g not in (alcance.get("grupos") or [])]

    return (
        "ALCANCE DECLARADO POR EL ESTUDIANTE — el proyecto está EN CURSO y solo "
        f"estas partes se someten a evaluación: {declarados}.\n"
        f"Partes NO declaradas (aún en desarrollo): {', '.join(fuera) or 'ninguna'}.\n"
        "Reglas obligatorias:\n"
        "- NO evalúes, NO exijas ni descuentes puntaje por las partes no declaradas: "
        "el estudiante no ha dicho que estén terminadas.\n"
        "- Si un criterio depende de una parte NO declarada (por ejemplo, coherencia "
        "del objetivo con un problema que aún no redacta), márcalo \"aplica\": false y "
        "explica en la razón, en tono formativo, qué deberá verificar cuando la escriba. "
        "No lo trates como error ni le bajes la nota por eso.\n"
        "- Puedes mencionar en una línea qué le tocará desarrollar después, como "
        "orientación, nunca como falta."
    )
