"""
Corpus de títulos del Repositorio Institucional UPAO.

Lo cosecha `scripts/cosechar_titulos_upao.py` (OAI-PMH) en
`data/titulos_upao.jsonl`. Aquí se hacen tres cosas con él:

  1. `buscar_titulos_similares()` — recuperación semántica (Chroma + el mismo
     modelo de embeddings del resto del sistema): dado un tema, devuelve títulos
     REALES ya aprobados por la universidad. Es el ancla contra la alucinación:
     el proponente no inventa el patrón, lo lee.

  2. `estadisticas_delimitacion()` — cuántos de esos títulos reales llevan lugar
     y cuántos llevan año, por escuela profesional. Convierte «te falta la
     delimitación» en «el 84 % de las tesis aprobadas de tu escuela nombran la
     institución; la tuya no».

  3. `contexto_titulos()` — arma el bloque de evidencia listo para el prompt.

Todo degrada en silencio: si el corpus no está cosechado, las funciones devuelven
vacío y el panel sigue funcionando sin la evidencia (con menos precisión, pero sin
romperse).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS_JSONL = os.path.join(_ROOT, "data", "titulos_upao.jsonl")
TITULOS_CHROMA_PATH = os.path.join(_ROOT, "chroma_db", "titulos_upao")

_COLLECTION_NAME = "titulos_upao_e5"
_LOTE_INDEXADO = 500

# Solo interesan trabajos de investigación: el repositorio también guarda
# revistas, libros digitales y patentes, que no sirven de patrón de título.
_TIPOS_UTILES = re.compile(r"(thesis|tesis|trabajo)", re.IGNORECASE)

_lock = threading.Lock()
_corpus_cache: list[dict] | None = None
_store_cache = None


def _sin_acentos(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode("ascii").lower()


# ── Carga del corpus ────────────────────────────────────────────────────────

def corpus_disponible() -> bool:
    return os.path.exists(CORPUS_JSONL) and os.path.getsize(CORPUS_JSONL) > 0


def cargar_corpus(recargar: bool = False) -> list[dict]:
    """Lee el JSONL a memoria y se queda SOLO con la escuela de sistemas.

    El filtro se aplica aquí, al cargar, y no únicamente en la cosecha: así un
    corpus ya descargado del repositorio completo queda corregido sin volver a
    cosechar 16 000 registros, y cualquier JSONL que alguien deje en `data/`
    pasa por el mismo criterio. Sin esto, el panel anclaba las propuestas de
    título en tesis de Medicina, Civil o Derecho, que no le sirven de patrón a
    un estudiante de sistemas.
    """
    global _corpus_cache
    with _lock:
        if _corpus_cache is not None and not recargar:
            return _corpus_cache

        filas: list[dict] = []
        if corpus_disponible():
            from backend.programas import ESCUELA_OBJETIVO, es_programa_objetivo

            leidas = 0
            with open(CORPUS_JSONL, encoding="utf-8") as f:
                for linea in f:
                    try:
                        d = json.loads(linea)
                    except ValueError:
                        continue
                    if not d.get("titulo"):
                        continue
                    leidas += 1
                    if es_programa_objetivo(d):
                        filas.append(d)
            logger.info(
                f"[titulos_upao] Corpus cargado: {len(filas)} tesis de {ESCUELA_OBJETIVO} "
                f"({leidas - len(filas)} de otras escuelas descartadas)"
            )
            if not filas and leidas:
                logger.warning(
                    "[titulos_upao] El corpus no contiene ninguna tesis de la escuela de "
                    "sistemas: el panel de título irá sin evidencia del repositorio."
                )
        else:
            logger.info("[titulos_upao] Corpus no cosechado todavía — el panel irá sin evidencia")

        _corpus_cache = filas
        return filas


def _es_investigacion(fila: dict) -> bool:
    marcas = f"{fila.get('tipo', '')} {fila.get('renati_tipo', '')} {fila.get('grado', '')}"
    return bool(_TIPOS_UTILES.search(marcas)) or bool(fila.get("programa"))


def filtrar_corpus(
    programa: str | None = None,
    facultad: str | None = None,
    anio_min: int | None = None,
    solo_investigacion: bool = True,
) -> list[dict]:
    """Subconjunto del corpus. `programa` y `facultad` comparan sin acentos ni mayúsculas."""
    filas = cargar_corpus()
    prog = _sin_acentos(programa) if programa else None
    fac = _sin_acentos(facultad) if facultad else None

    out = []
    for f in filas:
        if solo_investigacion and not _es_investigacion(f):
            continue
        if anio_min and (f.get("anio") or 0) < anio_min:
            continue
        if prog:
            candidatos = _sin_acentos(
                " ".join([f.get("programa") or ""] + list(f.get("colecciones") or []))
            )
            # Todos los tokens significativos deben estar: con «cualquiera vale»,
            # «ingeniería de sistemas» arrastraba también civil, industrial y de minas.
            tokens = [p for p in prog.split() if len(p) > 4]
            if prog not in candidatos and not (tokens and all(p in candidatos for p in tokens)):
                continue
        if fac:
            if fac not in _sin_acentos(" ".join(f.get("facultades") or []) + " " + (f.get("otorgante") or "")):
                continue
        out.append(f)
    return out


# ── Índice vectorial ────────────────────────────────────────────────────────

def _texto_indexable(fila: dict) -> str:
    """Lo que se embebe: título + materias. El resumen entero enterraría el título."""
    materias = ", ".join((fila.get("materias") or [])[:6])
    return f"{fila['titulo']}\n{materias}" if materias else fila["titulo"]


def _metadatos(fila: dict) -> dict:
    """Chroma solo acepta escalares en metadatos."""
    return {
        "titulo":    fila.get("titulo", "")[:900],
        "anio":      int(fila.get("anio") or 0),
        "programa":  (fila.get("programa") or "")[:180],
        "facultad":  ((fila.get("facultades") or [""])[0])[:180],
        "grado":     (fila.get("grado") or "")[:180],
        "url":       (fila.get("url") or "")[:300],
        "handle":    (fila.get("handle") or "")[:80],
    }


def cargar_o_crear_indice(embeddings, reconstruir: bool = False, permitir_construir: bool = False):
    """Colección Chroma persistente con los títulos.

    `permitir_construir` está en False a propósito: embeber 16 000 títulos tarda
    minutos y no puede ocurrir dentro de una petición de chat. Lo construye el
    script `scripts/indexar_titulos.py`; en caliente solo se abre lo ya indexado.
    """
    global _store_cache
    if _store_cache is not None and not reconstruir:
        return _store_cache

    import chromadb
    from langchain_chroma import Chroma

    os.makedirs(TITULOS_CHROMA_PATH, exist_ok=True)
    cliente = chromadb.PersistentClient(path=TITULOS_CHROMA_PATH)

    if reconstruir:
        try:
            cliente.delete_collection(_COLLECTION_NAME)
        except Exception:                                # noqa: BLE001
            pass

    store = Chroma(
        client=cliente,
        collection_name=_COLLECTION_NAME,
        embedding_function=embeddings,
    )

    if store._collection.count() == 0 and permitir_construir:
        filas = [f for f in cargar_corpus() if _es_investigacion(f)]
        if filas:
            logger.info(f"[titulos_upao] Indexando {len(filas)} títulos (una sola vez)…")
            from langchain_core.documents import Document
            for i in range(0, len(filas), _LOTE_INDEXADO):
                lote = filas[i: i + _LOTE_INDEXADO]
                store.add_documents([
                    Document(page_content=_texto_indexable(f), metadata=_metadatos(f))
                    for f in lote
                ])
                logger.info(f"[titulos_upao] {min(i + _LOTE_INDEXADO, len(filas))}/{len(filas)}")
        else:
            logger.warning("[titulos_upao] Sin corpus que indexar.")

    logger.info(f"[titulos_upao] Índice listo: {store._collection.count()} títulos")
    _store_cache = store
    return store


def buscar_titulos_similares(
    embeddings,
    tema: str,
    k: int = 8,
    programa: str | None = None,
    anio_min: int | None = None,
) -> list[dict]:
    """Títulos reales del repositorio parecidos al tema. Vacío si no hay corpus."""
    if not corpus_disponible():
        return []
    try:
        store = cargar_o_crear_indice(embeddings)
        if store._collection.count() == 0:
            logger.warning(
                "[titulos_upao] El índice está vacío. Constrúyelo una vez con "
                "`python -m scripts.indexar_titulos`; hasta entonces el panel trabaja "
                "sin la evidencia del repositorio."
            )
            return []
        # Se pide de más y se filtra después: el filtro por programa en Chroma
        # exigiría igualdad exacta, y los nombres de escuela varían de registro a registro.
        docs = store.similarity_search(tema, k=min(k * 5, 60))
    except Exception as exc:                             # noqa: BLE001
        logger.warning(f"[titulos_upao] Búsqueda falló: {exc}")
        return []

    from backend.programas import es_programa_objetivo

    prog = _sin_acentos(programa) if programa else None
    preferidos, resto = [], []
    ajenos = 0
    for d in docs:
        m = d.metadata or {}
        # Guarda contra un índice construido antes de acotar el corpus: la
        # búsqueda va contra Chroma, no contra el JSONL, así que un índice
        # antiguo seguiría devolviendo tesis de Medicina o Derecho aunque el
        # corpus ya esté filtrado. Los metadatos (programa + grado) bastan para
        # reconocer la escuela.
        if not es_programa_objetivo(m):
            ajenos += 1
            continue
        if anio_min and int(m.get("anio") or 0) < anio_min:
            continue
        # El contenido indexado es «título\nmaterias»: las materias dicen con qué
        # técnicas y enfoques se resolvieron temas cercanos, que es justo lo que el
        # proponente necesita para sugerir algo viable y no una idea de laboratorio.
        partes = d.page_content.split("\n", 1)
        fila = {
            "titulo":   m.get("titulo") or partes[0],
            "anio":     int(m.get("anio") or 0) or None,
            "programa": m.get("programa") or "",
            "facultad": m.get("facultad") or "",
            "url":      m.get("url") or "",
            "materias": partes[1].strip() if len(partes) > 1 else "",
        }
        if prog and prog in _sin_acentos(fila["programa"]):
            preferidos.append(fila)
        else:
            resto.append(fila)

    if ajenos:
        logger.warning(
            f"[titulos_upao] {ajenos}/{len(docs)} resultados eran de otras escuelas y se "
            "descartaron: el índice se construyó con el repositorio completo. Recompílalo "
            "con `python -m scripts.indexar_titulos --reconstruir` para no perder recall."
        )

    return (preferidos + resto)[:k]


# ── Estadísticas de delimitación ────────────────────────────────────────────

@dataclass
class EstadisticaTitulos:
    n: int
    pct_espacio: float
    pct_tiempo: float
    pct_ambos: float
    palabras_mediana: int
    ambito: str

    def resumen(self) -> str:
        if not self.n:
            return "Sin datos del repositorio para este ámbito."
        return (
            f"Sobre {self.n} tesis de {self.ambito} en el repositorio UPAO: "
            f"{self.pct_espacio:.0f}% nombran el lugar o la institución, "
            f"{self.pct_tiempo:.0f}% incluyen el año o periodo, "
            f"{self.pct_ambos:.0f}% incluyen ambos. "
            f"Mediana de extensión: {self.palabras_mediana} palabras."
        )


def estadisticas_delimitacion(
    programa: str | None = None,
    facultad: str | None = None,
    anio_min: int | None = None,
) -> EstadisticaTitulos:
    """Cuánta delimitación traen de hecho los títulos aprobados del ámbito pedido.

    Es la evidencia que convierte una regla abstracta en un argumento verificable
    frente al jurado."""
    from ..titulo import contar_palabras_titulo, diagnosticar_titulo

    from backend.programas import ESCUELA_OBJETIVO

    filas = filtrar_corpus(programa=programa, facultad=facultad, anio_min=anio_min)
    # El corpus ya viene acotado a la escuela de sistemas, así que "sin filtro
    # adicional" significa esa escuela — no «todas», que daba a entender al
    # estudiante que el porcentaje salía de toda la universidad.
    ambito = programa or facultad or ESCUELA_OBJETIVO
    if not filas:
        return EstadisticaTitulos(0, 0.0, 0.0, 0.0, 0, ambito)

    n_esp = n_tmp = n_amb = 0
    palabras: list[int] = []
    for f in filas:
        d = diagnosticar_titulo(f["titulo"])
        n_esp += d.tiene_espacio
        n_tmp += d.tiene_tiempo
        n_amb += d.tiene_espacio and d.tiene_tiempo
        palabras.append(contar_palabras_titulo(f["titulo"]))

    palabras.sort()
    n = len(filas)
    return EstadisticaTitulos(
        n=n,
        pct_espacio=100.0 * n_esp / n,
        pct_tiempo=100.0 * n_tmp / n,
        pct_ambos=100.0 * n_amb / n,
        palabras_mediana=palabras[n // 2],
        ambito=ambito,
    )


# ── Bloque de evidencia para los prompts ────────────────────────────────────

def contexto_titulos(
    embeddings,
    tema: str,
    programa: str | None = None,
    facultad: str | None = None,
    k: int = 8,
    anio_min: int | None = None,
) -> str:
    """Evidencia del repositorio lista para inyectar: estadística + títulos reales."""
    if not corpus_disponible():
        return ""

    partes: list[str] = []
    try:
        est = estadisticas_delimitacion(programa=programa, facultad=facultad, anio_min=anio_min)
        if est.n:
            partes.append(est.resumen())
    except Exception as exc:                             # noqa: BLE001
        logger.warning(f"[titulos_upao] Estadística falló: {exc}")

    similares = buscar_titulos_similares(
        embeddings, tema, k=k, programa=programa, anio_min=anio_min
    )
    if similares:
        lineas = []
        for i, s in enumerate(similares, 1):
            sello = " · ".join(filter(None, [str(s["anio"]) if s["anio"] else "", s["programa"]]))
            linea = f"{i}. «{s['titulo']}»" + (f" ({sello})" if sello else "")
            if s.get("materias"):
                linea += f"\n   Enfoques/técnicas: {s['materias']}"
            lineas.append(linea)
        partes.append(
            "Títulos reales aprobados en el tema más cercano al del estudiante. Úsalos como "
            "PATRÓN de forma y como referencia de qué enfoques resultan viables en esta "
            "escuela; NO copies su contenido:\n" + "\n".join(lineas)
        )

    return "\n\n".join(partes)
