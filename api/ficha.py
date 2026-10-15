"""
FICHA DEL PROYECTO — memoria estructurada de la asesoría.

Por qué existe
──────────────
El panel de mentoría era amnésico por construcción: todo lo que "sabía" venía
del PDF (RAG) o de un historial truncado a 200 caracteres por turno. Un
estudiante SIN PDF —el caso más común al arrancar de cero— no tenía dónde se
acumulara nada, así que respondía las mismas preguntas una y otra vez.

La ficha son los ~10 datos que gobiernan TODO el proyecto (problema, cómo se
mide hoy, organización, artefacto, tipo, diseño, acceso a datos…). Son pocos,
acotados y hacen falta en TODOS los turnos, así que se INYECTAN siempre en vez
de recuperarse: recuperar algo que siempre necesitas solo añade una probabilidad
de fallo. Y como son DECISIONES que el estudiante cambia sobre la marcha, la
semántica correcta es «el último valor gana» — algo que una búsqueda por
similitud no sabe hacer (devolvería la versión vieja y la nueva con el mismo
peso, sin saber cuál anuló a cuál).

Persistencia
────────────
`public.conversaciones.ficha` (jsonb) en Supabase — ver `supabase/schema_v7.sql`.
Vive en la conversación, NO en el documento: así sobrevive sin PDF y a los
reinicios de Cloud Run, que es justo donde se perdía. Delante hay una caché en
memoria para no pagar el viaje en cada turno; si Supabase no está configurado
(dev local) la caché es el único almacén y todo sigue funcionando.
"""

import logging
import os
import re
import threading

import requests
from pydantic import BaseModel, Field

from .llm import llm_rapido

logger = logging.getLogger(__name__)

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
_PERSISTE = bool(SUPABASE_URL and SERVICE_ROLE_KEY)

if not _PERSISTE:
    logger.info("[ficha] Sin Supabase: la ficha vivirá solo en memoria de proceso.")


# ── Campos de la ficha ──────────────────────────────────────────────────────
# El orden importa: es el orden en que se le muestran al estudiante y el orden
# de prioridad con que el elicitador debe preguntar lo que falte.
CAMPOS: list[tuple[str, str]] = [
    ("tema",             "Tema / dominio"),
    ("problema",         "Problema real que se aborda"),
    ("medicion_actual",  "Cómo se mide hoy (variable dependiente)"),
    ("indicadores",      "Indicadores"),
    ("artefacto",        "Artefacto propuesto (variable independiente)"),
    ("organizacion",     "Organización / lugar"),
    ("anio",             "Año o periodo"),
    ("tipo_investigacion", "Tipo de investigación (aplicada/básica)"),
    ("diseno",           "Diseño (pre-exp., cuasi-exp., descriptivo, correlacional)"),
    ("acceso_datos",     "Acceso real a datos y a la organización"),
    ("titulo",           "Título acordado"),
]

_CLAVES = [c for c, _ in CAMPOS]
_ETIQUETAS = dict(CAMPOS)

# Campos SIN los cuales no se puede redactar nada con rigor. `titulo`, `anio` e
# `indicadores` no entran: son consecuencia de los demás, no requisito.
_ESENCIALES = [
    "problema", "medicion_actual", "artefacto",
    "organizacion", "tipo_investigacion", "diseno",
]


class Ficha(BaseModel):
    """Extracción incremental. Vacío = el estudiante NO lo ha dicho todavía."""
    tema: str = Field(default="", description="Dominio o tecnología: «cáncer de piel con deep learning».")
    problema: str = Field(default="", description="Qué proceso falla y a quién afecta. NO la solución.")
    medicion_actual: str = Field(default="", description="Cómo se mide hoy ese problema en la organización.")
    indicadores: str = Field(default="", description="Métricas concretas con las que se evaluará.")
    artefacto: str = Field(default="", description="Lo que va a construir: sistema, modelo, app.")
    organizacion: str = Field(default="", description="Empresa, hospital, red o institución concreta.")
    anio: str = Field(default="", description="Año o periodo al que se ciñe el estudio.")
    tipo_investigacion: str = Field(default="", description="Solo si lo DECIDIÓ: «aplicada» o «básica».")
    diseno: str = Field(default="", description="Solo si lo DECIDIÓ: pre-experimental, cuasi-experimental, descriptivo, correlacional.")
    acceso_datos: str = Field(default="", description="Qué datos tiene y si tiene permiso real para usarlos.")
    titulo: str = Field(default="", description="El título, solo si ya quedó acordado con el estudiante.")


_PROMPT_EXTRACTOR = """\
Eres un EXTRACTOR de datos de una asesoría de tesis. NO redactas, NO opinas, NO \
aconsejas: solo registras lo que el ESTUDIANTE ya dijo.

REGLAS ABSOLUTAS
1. Solo rellenas un campo si el ESTUDIANTE lo afirmó. Nunca lo que propuso MentorIA, \
nunca lo que se infiere «por lógica», nunca lo que sería razonable suponer.
2. Si un dato no aparece, déjalo VACÍO (""). Un campo vacío es una respuesta correcta; \
inventarlo corrompe toda la asesoría.
3. Si el estudiante CAMBIÓ de opinión, vale lo ÚLTIMO que dijo.
4. Si el estudiante responde a una lista de preguntas de MentorIA (con formato \
«1. …Respuesta: …», «Título: …», «Diseño: …» o similar), esas respuestas SÍ son suyas: \
extráelas todas.
5. Copia el contenido de forma compacta (máximo ~200 caracteres por campo), en las \
palabras del estudiante, sin adornar.

FICHA ACTUAL (lo ya registrado; devuélvelo igual salvo que el estudiante lo corrija o \
lo amplíe):
{ficha_actual}

CONVERSACIÓN A ANALIZAR:
{texto}"""


# ── Caché en memoria (y único almacén si no hay Supabase) ───────────────────
_CACHE: dict[str, dict] = {}
_lock = threading.Lock()


def vacia() -> dict:
    return {c: "" for c in _CLAVES}


def fusionar(previa: dict | None, nueva: dict | None) -> dict:
    """Mezcla dos fichas: el valor NUEVO no vacío gana (last-write-wins).

    Un campo que llega vacío NUNCA borra lo que ya había: la extracción es
    incremental y el turno actual no tiene por qué repetir lo de antes.
    """
    out = vacia()
    out.update({k: (v or "").strip() for k, v in (previa or {}).items() if k in out})
    for k, v in (nueva or {}).items():
        if k in out and (v or "").strip():
            out[k] = v.strip()
    return out


def faltantes(ficha: dict | None) -> list[str]:
    """Etiquetas legibles de los campos ESENCIALES que siguen vacíos."""
    f = ficha or {}
    return [_ETIQUETAS[c] for c in _ESENCIALES if not (f.get(c) or "").strip()]


def completos(ficha: dict | None) -> list[str]:
    f = ficha or {}
    return [c for c in _CLAVES if (f.get(c) or "").strip()]


def hay_base_para_redactar(ficha: dict | None) -> bool:
    """True si la ficha basta para redactar sin inventar.

    Criterio: el problema (variable dependiente) más al menos tres esenciales
    más. Es deliberadamente laxo — con esto, el panel redacta marcando lo que
    falte como asunción explícita, que es mucho más útil que volver a preguntar.
    """
    f = ficha or {}
    if not (f.get("problema") or "").strip():
        return False
    return sum(1 for c in _ESENCIALES if (f.get(c) or "").strip()) >= 4


def bloque_ficha(ficha: dict | None) -> str:
    """Renderiza la ficha para inyectarla en los prompts del panel."""
    f = ficha or {}
    lineas = [f"- {_ETIQUETAS[c]}: {f[c].strip()}" for c in _CLAVES if (f.get(c) or "").strip()]
    if not lineas:
        return ("(el estudiante todavía no ha declarado ningún dato de su proyecto "
                "en esta asesoría)")
    txt = "\n".join(lineas)
    pend = faltantes(f)
    if pend:
        txt += "\n\nTODAVÍA NO HA DICHO: " + "; ".join(pend) + "."
    return txt


def resumen_para_estudiante(ficha: dict | None) -> str:
    """Respuesta directa a «¿sabes lo que te dije?»: se le devuelve su propia ficha.

    Es determinista a propósito: no pasa por ningún LLM, así que no puede
    inventarse un dato que el estudiante no dio ni olvidar uno que sí dio.
    """
    f = ficha or {}
    puestos = [(c, f[c].strip()) for c in _CLAVES if (f.get(c) or "").strip()]
    if not puestos:
        return (
            "Todavía no tengo ningún dato de tu proyecto registrado en esta asesoría. "
            "Cuéntame de qué trata y lo voy anotando."
        )
    partes = ["Esto es lo que tengo registrado de tu proyecto hasta ahora:", ""]
    partes += [f"- **{_ETIQUETAS[c]}:** {v}" for c, v in puestos]
    pend = faltantes(f)
    if pend:
        partes += ["", "Me falta que decidas: " + "; ".join(f"**{p}**" for p in pend) + "."]
    else:
        partes += ["", "Con esto tengo base suficiente para redactar. Dime qué parte quieres."]
    return "\n".join(partes)


# ── Detectores deterministas ────────────────────────────────────────────────

# «¿sabes lo que te dije?», «ya te dije mi problema», «no me estás escuchando».
# Se detecta con regex y no con el LLM porque es justo el turno en el que el
# estudiante ya perdió la confianza: no puede depender de que el modelo acierte.
#
# La frase «lo que te dije» va como alternativa SUELTA, sin exigir el verbo que la
# precede: en ese turno el estudiante escribe rápido y con erratas —el caso real
# que motivó esto fue «solo quiero saber si DABES lo que te dije»— y perseguir
# cada typo del verbo con regex es una carrera perdida. La frase basta.
_RE_META = re.compile(
    r"(ya\s+te\s+(lo\s+)?(dije|dij[eé]|cont[eé]|conte|expliqu[eé]|habl[eé]|mencion[eé])|"
    r"te\s+(lo\s+)?acabo\s+de\s+(decir|contar|explicar)|"
    r"(sab[eé]s|recuerdas?|te\s+acuerdas?)\s+(lo\s+)?(qu[eé]|cu[aá]l)|"
    r"lo\s+que\s+te\s+(dije|dij[eé]|cont[eé]|expliqu[eé]|habl[eé]|mencion[eé])|"
    r"no\s+me\s+(est[aá]s\s+)?(escuchas?|escuchando|entiendes?|lees?|prestas)|"
    r"me\s+est[aá]s\s+preguntando\s+lo\s+mismo|"
    r"(otra\s+vez|de\s+nuevo|siempre)\s+(las?\s+)?mismas?\s+preguntas?|"
    r"(qu[eé]|cu[aá]l(es)?)\s+(fue|era|es)\s+lo\s+que\s+te\s+dije|"
    r"volviste?\s+a\s+preguntar)",
    re.I,
)

# «haz lo que te dije», «aplica lo que te conté» NO son quejas de memoria: son
# órdenes de redactar. Sin esta excepción, ampliar la frase suelta de arriba las
# desviaría a la ruta de memoria y el estudiante se quedaría sin su entregable.
_RE_META_ES_ORDEN = re.compile(
    r"\b(haz|hazlo|has|aplica|usa|utiliza|redacta|escribe|sigue|olvida|ignora|borra)\b"
    r"[\w\s,]{0,30}\blo\s+que\s+te\s+(dije|dij[eé]|cont[eé]|expliqu[eé])",
    re.I,
)

# Firma del render de elicitación (`_formatear_elicitacion` siempre la emite).
# Permite contar cuántas tandas de preguntas seguidas lleva el estudiante SIN
# guardar estado extra: se lee del propio historial.
_RE_FIRMA_ELICITACION = re.compile(r"molde\s+vac[ií]o,?\s+no\s+una\s+propuesta", re.I)


def es_meta_pregunta(mensaje: str) -> bool:
    """True si el estudiante está preguntando por lo que YA dijo, no pidiendo algo nuevo."""
    texto = mensaje or ""
    if _RE_META_ES_ORDEN.search(texto):
        return False
    return bool(_RE_META.search(texto))


def elicitaciones_seguidas(historial: list[dict] | None) -> int:
    """Cuántas tandas de preguntas consecutivas ha recibido, mirando hacia atrás.

    Se corta en cuanto aparece un turno del mentor que NO fue elicitación: lo que
    interesa es la racha actual, no el total histórico.
    """
    n = 0
    for turno in reversed(historial or []):
        if turno.get("rol") != "assistant":
            continue
        if _RE_FIRMA_ELICITACION.search(turno.get("contenido") or ""):
            n += 1
        else:
            break
    return n


# ── Extracción ──────────────────────────────────────────────────────────────

def _texto_conversacion(mensaje: str, historial: list[dict] | None, completo: bool) -> str:
    """Arma el texto a analizar.

    En modo incremental basta el mensaje nuevo (lo anterior ya está en la ficha).
    En modo bootstrap —ficha vacía con historial ya andando, p. ej. tras un
    reinicio del proceso— se relee toda la conversación para recuperar lo perdido.
    """
    if not completo:
        return f"Estudiante: {mensaje}"
    lineas = []
    for t in (historial or [])[-12:]:
        contenido = (t.get("contenido") or "").strip().replace("\n", " ")
        if not contenido:
            continue
        if t.get("rol") == "user":
            # Los turnos del estudiante van ÍNTEGROS: son la fuente de los datos.
            lineas.append(f"Estudiante: {contenido[:2000]}")
        else:
            # Los del mentor van recortados y solo como contexto de a qué responde.
            lineas.append(f"MentorIA (contexto, NO es fuente de datos): {contenido[:200]}")
    lineas.append(f"Estudiante: {mensaje}")
    return "\n".join(lineas)


def extraer_ficha(mensaje: str, historial: list[dict] | None, previa: dict | None) -> dict:
    """Actualiza la ficha con lo que el estudiante haya dicho en este turno."""
    previa = previa or vacia()
    bootstrap = not completos(previa) and bool(historial)
    texto = _texto_conversacion(mensaje, historial, completo=bootstrap)

    chain = llm_rapido(temperatura=0.0).with_structured_output(Ficha)
    try:
        out = chain.invoke(
            _PROMPT_EXTRACTOR.format(ficha_actual=bloque_ficha(previa), texto=texto)
        )
        nueva = out.model_dump() if isinstance(out, Ficha) else dict(out or {})
    except Exception as exc:
        logger.warning(f"[ficha] Extracción falló, conservo la ficha previa: {exc}")
        return previa

    fusionada = fusionar(previa, nueva)
    nuevos = [k for k in _CLAVES if fusionada.get(k) and not (previa.get(k) or "").strip()]
    if nuevos:
        logger.info(f"[ficha] Campos nuevos registrados: {', '.join(nuevos)}")
    return fusionada


# ── Persistencia ────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "apikey": SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def cargar(conversacion_id: str | None) -> dict:
    """Lee la ficha: caché primero, Supabase si no estaba."""
    if not conversacion_id:
        return vacia()
    with _lock:
        if conversacion_id in _CACHE:
            return dict(_CACHE[conversacion_id])
    if not _PERSISTE:
        return vacia()
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/conversaciones",
            params={"id": f"eq.{conversacion_id}", "select": "ficha"},
            headers=_headers(),
            timeout=8,
        )
        if resp.status_code >= 300:
            logger.warning("[ficha] GET devolvió %s: %s", resp.status_code, resp.text[:200])
            return vacia()
        filas = resp.json() or []
        guardada = (filas[0].get("ficha") if filas else None) or {}
        ficha = fusionar(vacia(), guardada)
    except Exception:
        logger.warning("[ficha] No se pudo cargar de Supabase", exc_info=True)
        return vacia()
    with _lock:
        _CACHE[conversacion_id] = dict(ficha)
    return ficha


def guardar(conversacion_id: str | None, ficha: dict) -> None:
    """Persiste la ficha. La caché se actualiza YA; el viaje a Supabase va en
    segundo plano para no añadir latencia a la respuesta del chat."""
    if not conversacion_id:
        return
    with _lock:
        _CACHE[conversacion_id] = dict(ficha)
    if not _PERSISTE:
        return
    threading.Thread(
        target=_guardar_remoto, args=(conversacion_id, dict(ficha)), daemon=True
    ).start()


def _guardar_remoto(conversacion_id: str, ficha: dict) -> None:
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/conversaciones",
            params={"id": f"eq.{conversacion_id}"},
            json={"ficha": ficha},
            headers={**_headers(), "Prefer": "return=minimal"},
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("[ficha] PATCH devolvió %s: %s", resp.status_code, resp.text[:200])
    except Exception:
        logger.warning("[ficha] No se pudo guardar en Supabase", exc_info=True)
