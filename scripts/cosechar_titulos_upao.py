"""
Cosechador del Repositorio Institucional UPAO (OAI-PMH) — escuela de sistemas.

Descarga los METADATOS públicos de todo el repositorio
(https://repositorio.upao.edu.pe) usando su interfaz OAI-PMH — el protocolo
estándar que los repositorios exponen justamente para ser cosechados. No
descarga PDFs ni scrapea el sitio: solo pide metadatos, paginados, con pausa
entre peticiones.

El resultado es `data/titulos_upao.jsonl`: un JSON por línea con el título, el
año, la escuela profesional, la facultad, el grado, el tipo y el resumen de cada
tesis. Ese corpus es lo que el panel de título consulta para proponer títulos
ANCLADOS en títulos reales aprobados por la universidad, en vez de inventarlos.

Se GUARDAN solo las tesis de la escuela de sistemas (ver `backend/programas.py`).
El repositorio hay que recorrerlo entero —OAI-PMH no permite filtrar por escuela
en la petición— pero de sus ~16 000 registros se conservan las ~270 que sirven de
patrón a un estudiante de sistemas. Guardar el resto era contraproducente: anclaba
las propuestas de título en tesis de Medicina, Civil o Derecho.
Con `--todas-las-escuelas` se guarda el repositorio completo (solo para análisis;
la aplicación filtra igualmente al cargar el corpus).

Datos personales: se descartan a propósito DNI, ORCID y la lista de jurados. Se
conservan autor(es) y asesor porque son metadatos bibliográficos públicos que un
estudiante necesita para citar la tesis.

Uso:
    venv\\Scripts\\python -m scripts.cosechar_titulos_upao
    venv\\Scripts\\python -m scripts.cosechar_titulos_upao --reanudar
    venv\\Scripts\\python -m scripts.cosechar_titulos_upao --limite 500

Es reanudable: guarda el `resumptionToken` en un archivo de estado, así que si
se corta la conexión basta con volver a lanzarlo con --reanudar.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import xml.etree.ElementTree as ET
from typing import Iterator
from urllib.parse import urlencode

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cosecha_upao")

BASE_OAI = "https://repositorio.upao.edu.pe/backend/oai/request"
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA_JSONL = os.path.join(_ROOT, "data", "titulos_upao.jsonl")
SALIDA_SETS = os.path.join(_ROOT, "data", "titulos_upao_sets.json")
ESTADO = os.path.join(_ROOT, "data", ".cosecha_estado.json")

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dim": "http://www.dspace.org/xmlns/dspace/dim",
}

_PAUSA_SEG = 0.7          # cortesía entre peticiones
_TIMEOUT = 90
_REINTENTOS = 4
_ABSTRACT_MAX = 1200      # el resumen completo no aporta al corpus de títulos

_UA = (
    "MentorIA-UPAO/1.0 (cosecha OAI-PMH para asesoría metodológica interna; "
    "contacto: biblio_repositorio@upao.edu.pe)"
)


# ── Transporte ──────────────────────────────────────────────────────────────

def _pedir(params: dict) -> ET.Element:
    """GET al endpoint OAI con reintentos y respeto de Retry-After."""
    url = f"{BASE_OAI}?{urlencode(params)}"
    ultimo_error: Exception | None = None

    for intento in range(1, _REINTENTOS + 1):
        try:
            r = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
            if r.status_code == 503:
                espera = int(r.headers.get("Retry-After", "20") or 20)
                logger.warning(f"503 del repositorio; esperando {espera}s")
                time.sleep(min(espera, 120))
                continue
            r.raise_for_status()
            return ET.fromstring(r.content)
        except Exception as exc:                       # noqa: BLE001
            ultimo_error = exc
            espera = 3 * intento
            logger.warning(f"Intento {intento}/{_REINTENTOS} falló ({exc}); reintento en {espera}s")
            time.sleep(espera)

    raise RuntimeError(f"No se pudo obtener {url}: {ultimo_error}")


# ── Sets (comunidades y colecciones) ────────────────────────────────────────

def cosechar_sets() -> dict[str, str]:
    """Mapa setSpec → nombre legible. Es lo que traduce 'com_20.500.12759_52'
    a 'FACULTAD DE INGENIERÍA'."""
    sets: dict[str, str] = {}
    token: str | None = None

    while True:
        params = {"verb": "ListSets"} if token is None else {"verb": "ListSets", "resumptionToken": token}
        raiz = _pedir(params)
        for s in raiz.iterfind(".//oai:set", NS):
            spec = (s.findtext("oai:setSpec", default="", namespaces=NS) or "").strip()
            nombre = (s.findtext("oai:setName", default="", namespaces=NS) or "").strip()
            if spec:
                sets[spec] = nombre
        tok_el = raiz.find(".//oai:resumptionToken", NS)
        token = (tok_el.text or "").strip() if tok_el is not None and tok_el.text else ""
        logger.info(f"Sets acumulados: {len(sets)}")
        if not token:
            break
        time.sleep(_PAUSA_SEG)

    return sets


# ── Registros ───────────────────────────────────────────────────────────────

def _campos_dim(registro: ET.Element) -> dict[str, list[str]]:
    """Aplana los <dim:field> de un registro a {'dc.title': [...], ...}."""
    campos: dict[str, list[str]] = {}
    for f in registro.iterfind(".//dim:field", NS):
        partes = [f.get("mdschema") or "", f.get("element") or ""]
        if f.get("qualifier"):
            partes.append(f.get("qualifier") or "")
        clave = ".".join(p for p in partes if p)
        valor = (f.text or "").strip()
        if valor:
            campos.setdefault(clave, []).append(valor)
    return campos


def _uno(campos: dict[str, list[str]], clave: str) -> str:
    v = campos.get(clave) or []
    return v[0] if v else ""


def _anio(campos: dict[str, list[str]]) -> int | None:
    """Año de publicación: dc.date.issued suele ser '2024' o '2024-03-15'."""
    import re
    for clave in ("dc.date.issued", "dc.date.available", "dc.date.accessioned"):
        for bruto in campos.get(clave, []):
            m = re.search(r"(19|20)\d{2}", bruto)
            if m:
                return int(m.group(0))
    return None


def _limpiar_titulo(t: str) -> str:
    import re
    t = re.sub(r"\s+", " ", (t or "")).strip()
    return t.strip(" .;,")


def _registro_a_dict(registro: ET.Element, sets: dict[str, str]) -> dict | None:
    cabecera = registro.find("oai:header", NS)
    if cabecera is None or (cabecera.get("status") or "").lower() == "deleted":
        return None

    identificador = (cabecera.findtext("oai:identifier", default="", namespaces=NS) or "").strip()
    especificaciones = [
        (e.text or "").strip()
        for e in cabecera.iterfind("oai:setSpec", NS)
        if (e.text or "").strip()
    ]
    campos = _campos_dim(registro)

    titulo = _limpiar_titulo(_uno(campos, "dc.title"))
    if not titulo:
        return None

    handle = identificador.split(":")[-1] if identificador else ""
    comunidades = [sets.get(s, "") for s in especificaciones if s.startswith("com_")]
    colecciones = [sets.get(s, "") for s in especificaciones if s.startswith("col_")]

    resumenes = campos.get("dc.description.abstract") or []
    resumen = resumenes[0][:_ABSTRACT_MAX] if resumenes else ""

    return {
        "handle":     handle,
        "url":        _uno(campos, "dc.identifier.uri") or (f"https://hdl.handle.net/{handle}" if handle else ""),
        "titulo":     titulo,
        "anio":       _anio(campos),
        "tipo":       _uno(campos, "dc.type"),
        "renati_tipo":  _uno(campos, "renati.type"),
        "renati_nivel": _uno(campos, "renati.level"),
        "grado":      _uno(campos, "thesis.degree.name"),
        "programa":   _uno(campos, "thesis.degree.discipline") or _uno(campos, "renati.discipline"),
        "otorgante":  _uno(campos, "thesis.degree.grantor"),
        "facultades": [c for c in comunidades if c],
        "colecciones": [c for c in colecciones if c],
        "materias":   campos.get("dc.subject", [])[:12],
        "ocde":       campos.get("dc.subject.ocde", [])[:4],
        "cobertura_espacial": campos.get("dc.coverage.spatial", [])[:3],
        "autores":    campos.get("dc.contributor.author", [])[:6],
        "asesor":     _uno(campos, "dc.contributor.advisor"),
        "idioma":     _uno(campos, "dc.language.iso"),
        "resumen":    resumen,
    }


def cosechar_registros(sets: dict[str, str], limite: int | None, token_inicial: str | None) -> Iterator[dict]:
    token = token_inicial
    total = 0
    completo: str | None = None

    while True:
        if token:
            params = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params = {"verb": "ListRecords", "metadataPrefix": "dim"}

        raiz = _pedir(params)

        error = raiz.find("oai:error", NS)
        if error is not None:
            codigo = error.get("code", "")
            if codigo == "noRecordsMatch":
                logger.info("El repositorio no devolvió más registros.")
                return
            raise RuntimeError(f"OAI error [{codigo}]: {error.text}")

        for registro in raiz.iterfind(".//oai:record", NS):
            fila = _registro_a_dict(registro, sets)
            if fila:
                total += 1
                yield fila
                if limite and total >= limite:
                    logger.info(f"Límite de {limite} alcanzado.")
                    return

        tok_el = raiz.find(".//oai:resumptionToken", NS)
        if completo is None and tok_el is not None:
            completo = tok_el.get("completeListSize")
            if completo:
                logger.info(f"El repositorio declara {completo} registros en total.")

        token = (tok_el.text or "").strip() if tok_el is not None and tok_el.text else ""
        _guardar_estado(token, total)
        logger.info(f"Cosechados {total}{' / ' + completo if completo else ''}")

        if not token:
            return
        time.sleep(_PAUSA_SEG)


# ── Estado reanudable ───────────────────────────────────────────────────────

def _guardar_estado(token: str, total: int) -> None:
    try:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump({"resumptionToken": token, "total": total}, f)
    except OSError as exc:
        logger.warning(f"No se pudo guardar el estado: {exc}")


def _leer_estado() -> tuple[str | None, int]:
    try:
        with open(ESTADO, encoding="utf-8") as f:
            d = json.load(f)
        return (d.get("resumptionToken") or None), int(d.get("total") or 0)
    except (OSError, ValueError):
        return None, 0


# ── Programa principal ──────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Cosecha metadatos del repositorio UPAO vía OAI-PMH.")
    ap.add_argument("--limite", type=int, default=None, help="Máximo de registros (para pruebas).")
    ap.add_argument("--reanudar", action="store_true", help="Continúa desde el último resumptionToken.")
    ap.add_argument("--salida", default=SALIDA_JSONL)
    ap.add_argument(
        "--todas-las-escuelas",
        action="store_true",
        help="Guarda TODO el repositorio, no solo la escuela de sistemas (análisis).",
    )
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.salida), exist_ok=True)

    logger.info("Cosechando el catálogo de comunidades y colecciones…")
    sets = cosechar_sets()
    with open(SALIDA_SETS, "w", encoding="utf-8") as f:
        json.dump(sets, f, ensure_ascii=False, indent=1)
    logger.info(f"{len(sets)} sets guardados en {SALIDA_SETS}")

    token, previos = (_leer_estado() if args.reanudar else (None, 0))
    modo = "a" if (args.reanudar and previos) else "w"
    if modo == "a":
        logger.info(f"Reanudando: {previos} registros ya en el archivo.")

    vistos: set[str] = set()
    if modo == "a" and os.path.exists(args.salida):
        with open(args.salida, encoding="utf-8") as f:
            for linea in f:
                try:
                    vistos.add(json.loads(linea)["handle"])
                except (ValueError, KeyError):
                    continue

    from backend.programas import ESCUELA_OBJETIVO, es_programa_objetivo

    escritos = 0
    descartados = 0
    with open(args.salida, modo, encoding="utf-8") as f:
        for fila in cosechar_registros(sets, args.limite, token):
            if fila["handle"] and fila["handle"] in vistos:
                continue
            vistos.add(fila["handle"])
            # El repositorio se recorre entero (OAI-PMH no deja filtrar por
            # escuela en la petición), pero solo se guarda lo que sirve de patrón
            # a un tesista de sistemas.
            if not args.todas_las_escuelas and not es_programa_objetivo(fila):
                descartados += 1
                continue
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            escritos += 1
            if escritos % 100 == 0:
                f.flush()

    ambito = "todas las escuelas" if args.todas_las_escuelas else ESCUELA_OBJETIVO
    logger.info(
        f"Listo: {escritos} registros de {ambito} en {args.salida}"
        + (f" ({descartados} de otras escuelas descartados)." if descartados else ".")
    )
    if os.path.exists(ESTADO):
        os.remove(ESTADO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
