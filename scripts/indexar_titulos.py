"""
Indexa el corpus de títulos UPAO en Chroma (una sola vez).

Se hace aquí y no dentro de la API porque embeber ~16 000 títulos tarda minutos:
si ocurriera durante una petición de chat, el estudiante vería la respuesta
colgada. El índice queda en `chroma_db/titulos_upao/` y se reutiliza entre
arranques.

Requisito previo:
    venv\\Scripts\\python -m scripts.cosechar_titulos_upao

Uso:
    venv\\Scripts\\python -m scripts.indexar_titulos
    venv\\Scripts\\python -m scripts.indexar_titulos --reconstruir
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("indexar_titulos")


def main() -> int:
    ap = argparse.ArgumentParser(description="Construye el índice vectorial de títulos UPAO.")
    ap.add_argument("--reconstruir", action="store_true", help="Borra el índice existente y lo rehace.")
    args = ap.parse_args()

    from backend.rag import cargar_modelo_embeddings
    from backend.rag.titulos_store import (
        cargar_corpus,
        cargar_o_crear_indice,
        corpus_disponible,
        estadisticas_delimitacion,
    )

    if not corpus_disponible():
        logger.error(
            "No hay corpus que indexar. Ejecuta primero:\n"
            "    venv\\Scripts\\python -m scripts.cosechar_titulos_upao"
        )
        return 1

    filas = cargar_corpus()
    logger.info(f"Corpus: {len(filas)} registros")

    logger.info("Cargando el modelo de embeddings…")
    embeddings = cargar_modelo_embeddings()

    inicio = time.time()
    store = cargar_o_crear_indice(embeddings, reconstruir=args.reconstruir, permitir_construir=True)
    n = store._collection.count()
    logger.info(f"Índice listo: {n} títulos en {time.time() - inicio:.0f}s")

    est = estadisticas_delimitacion(anio_min=2020)
    logger.info(est.resumen())
    return 0


if __name__ == "__main__":
    sys.exit(main())
