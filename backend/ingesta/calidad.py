"""
Métricas de calidad del texto extraído.

Un extractor de PDF puede "tener éxito" y devolver basura: las fuentes *subset*
sin `/ToUnicode` (típicas de LaTeX y de varios exportadores) producen mojibake
CID, y algunos motores devuelven la página vacía en vez de fallar. Sin una
medida de calidad, la cascada de extractores se detendría en el primero que no
lanza excepción, que es justo el bug que dejaba proyectos "en blanco".
"""

import re
import unicodedata

# Palabras funcionales del español: si un texto largo no contiene NINGUNA,
# casi con seguridad es mojibake (o no es español, que aquí da igual: no se
# podrá evaluar contra la rúbrica).
_FUNCIONALES = {
    "de", "la", "el", "que", "en", "y", "los", "del", "se", "las", "por",
    "un", "para", "con", "no", "una", "su", "al", "es", "lo", "como", "más",
    "the", "of", "and",          # tolera resúmenes/abstract en inglés
}

_RE_ALFA = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]")
_RE_TOKEN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{1,}")

# Umbral de caracteres por debajo del cual una página no aporta nada evaluable
# (un número de página suelto, un encabezado corrido, una figura sin texto).
MIN_CHARS_PAGINA = 40


def ratio_alfabetico(texto: str) -> float:
    """Fracción de caracteres que son letras. El mojibake CID baja mucho aquí."""
    visibles = [c for c in texto if not c.isspace()]
    if not visibles:
        return 0.0
    return sum(1 for c in visibles if _RE_ALFA.match(c)) / len(visibles)


def ratio_funcionales(texto: str) -> float:
    """Fracción de tokens que son palabras funcionales. ~0 en texto corrupto."""
    tokens = [t.lower() for t in _RE_TOKEN.findall(texto)]
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in _FUNCIONALES) / len(tokens)


def ratio_reemplazo(texto: str) -> float:
    """Fracción de caracteres de reemplazo/uso privado (señal directa de CID roto)."""
    if not texto:
        return 0.0
    malos = sum(
        1 for c in texto
        if c == "�" or unicodedata.category(c) in ("Co", "Cn")
    )
    return malos / len(texto)


def puntuar(texto: str) -> float:
    """Calidad del texto en 0..1. Se usa para comparar extractores entre sí."""
    texto = (texto or "").strip()
    if len(texto) < MIN_CHARS_PAGINA:
        return 0.0
    alfa = ratio_alfabetico(texto)
    func = ratio_funcionales(texto)
    malo = ratio_reemplazo(texto)
    # Las funcionales pesan más: distinguen español legible de ruido con forma
    # de letras. `malo` penaliza de forma dura porque solo aparece si algo se
    # decodificó mal de verdad.
    score = (0.35 * min(alfa / 0.70, 1.0)) + (0.65 * min(func / 0.18, 1.0))
    return max(0.0, score - (malo * 3.0))


def es_utilizable(texto: str) -> bool:
    """¿Esta página aporta texto real que un agente pueda leer?"""
    return puntuar(texto) >= 0.45


def resumen_calidad(paginas: list[tuple[int, str]]) -> dict:
    """Diagnóstico agregado para los avisos que ve el estudiante."""
    utiles = [(n, t) for n, t in paginas if es_utilizable(t)]
    return {
        "paginas":        len(paginas),
        "paginas_utiles": len(utiles),
        "chars":          sum(len(t) for _, t in utiles),
        "sin_texto":      [n for n, t in paginas if not es_utilizable(t)],
    }
