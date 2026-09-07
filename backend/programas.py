"""
Escuelas profesionales a las que sirve el sistema.

MentorIA asesora ÚNICAMENTE a estudiantes de la escuela de sistemas de la UPAO,
que a lo largo de los años ha usado varios nombres:

    · Ingeniería de Computación y Sistemas   (el nombre con el que está la
      inmensa mayoría del repositorio)
    · Ingeniería de Sistemas                 (posgrado y denominación histórica)
    · Ingeniería de Sistemas e Inteligencia Artificial  (denominación actual)

Por qué importa filtrar: el corpus de títulos se cosecha del repositorio
institucional COMPLETO (~16 000 tesis de Medicina, Civil, Derecho, Psicología…).
Ese corpus es lo que ancla las propuestas de título del panel — le enseña qué
forma tiene un título aprobado de verdad. Con títulos de otras facultades dentro,
el ancla apunta al sitio equivocado: a un estudiante de sistemas se le proponen
patrones de una tesis clínica o de un expediente técnico de obra, que no le
sirven de nada.

El filtro mira el programa, el grado y las colecciones, porque el repositorio no
es consistente: hay registros sin `programa` cuya escuela solo aparece en la
colección, y variantes con y sin tilde e incluso con erratas del propio
repositorio ("Ingenierio de Compuatción y Sistemas").
"""

from __future__ import annotations

import re
import unicodedata

# Familia de sistemas: se acepta cualquier denominación que combine ingeniería
# con computación/sistemas/software, más la mención de posgrado en sistemas de
# información. Escrito sobre texto ya normalizado (sin acentos, en minúsculas).
_PATRONES_OBJETIVO = [
    re.compile(r"comput\w*\s+y\s+sistemas"),          # Ingeniería de Computación y Sistemas
    re.compile(r"compuatcion\s+y\s+sistemas"),        # errata real del repositorio
    re.compile(r"ingenier\w*\s+de\s+sistemas"),       # Ingeniería de Sistemas (y … e IA)
    re.compile(r"ingenier\w*\s+en\s+sistemas"),
    re.compile(r"sistemas\s+e\s+inteligencia\s+artificial"),
    re.compile(r"ingenier\w*\s+de\s+software"),       # misma escuela y mismo dominio
    re.compile(r"sistemas\s+de\s+informacion"),       # mención de la maestría en sistemas
]

# Falsos positivos que comparten vocabulario pero son de OTRA facultad. Se
# comprueban primero: "Licenciada en Educación Secundaria, Especialidad en
# Computación e Informática" es de Educación, no de Ingeniería.
_PATRONES_EXCLUIDOS = [
    re.compile(r"educacion"),
    re.compile(r"computacion\s+e\s+informatica"),
]

# Etiqueta canónica para mostrar en informes y estadísticas.
ESCUELA_OBJETIVO = "Ingeniería de Sistemas / Computación y Sistemas"


def _norm(texto: str) -> str:
    sin_acentos = (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", sin_acentos)).strip()


def es_programa_objetivo(fila: dict) -> bool:
    """¿Este registro del repositorio es de la escuela de sistemas?

    `fila` es un registro cosechado (`data/titulos_upao.jsonl`).
    """
    campos = " ".join(
        [
            fila.get("programa") or "",
            fila.get("grado") or "",
            *(fila.get("colecciones") or []),
        ]
    )
    texto = _norm(campos)
    if not texto:
        return False
    if any(p.search(texto) for p in _PATRONES_EXCLUIDOS):
        return False
    return any(p.search(texto) for p in _PATRONES_OBJETIVO)


def filtrar_a_escuela(filas: list[dict]) -> list[dict]:
    """Deja solo los registros de la escuela de sistemas."""
    return [f for f in filas if es_programa_objetivo(f)]
