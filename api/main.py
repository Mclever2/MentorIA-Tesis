"""
API FastAPI — backend del frontend React (Cloud Run).

Endpoints:
  GET  /health                      — health check
  GET  /api/biblioteca              — libros indexados en la memoria RAG
  GET  /api/rubrica                 — rúbrica oficial UPAO (ítems + mapeo al proyecto)
  GET  /api/reglamento              — reglamento UPAO fijo (vigencia + puntos clave)
  POST /api/documentos              — sube PDF de tesis, vectoriza, devuelve estructura
  POST /api/chat                    — interpreta el mensaje; responde o crea un run
  GET  /api/runs/{id}/stream        — SSE con el progreso de los agentes
  POST /api/runs/{id}/cancelar      — botón de detener a los agentes
  POST /evaluar                     — endpoint legacy (compatibilidad)

La rúbrica y el reglamento son FIJOS (los oficiales UPAO): el estudiante ya no puede
subir ni reemplazar ninguno de los dos; solo consultarlos.
"""

import os
import json
import uuid
import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .auth import usuario_actual
from . import registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("PRELOAD_ON_STARTUP", "1") == "1":
        try:
            from .deps import precalentar
            precalentar()
        except Exception:
            logger.exception("[startup] Falló el precalentamiento (continuará lazy)")
    yield


app = FastAPI(
    title="MentorIA — API multiagente de mentoría de tesis",
    version="2.0.0",
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/biblioteca")
def biblioteca(_user: dict = Depends(usuario_actual)):
    from backend.rag import listar_libros
    from .deps import get_biblioteca

    libros = listar_libros(get_biblioteca())
    return {"libros": libros, "total_fragmentos": sum(l["fragmentos"] for l in libros)}



@app.post("/api/documentos")
async def subir_documento(
    archivo: UploadFile | None = File(default=None),
    texto: str = Form(default=""),
    enlace: str = Form(default=""),
    nombre: str = Form(default=""),
    memoria: str = Form(default=""),
    user: dict = Depends(usuario_actual),
):
    """
    Indexa el proyecto del estudiante venga como venga: archivo (PDF, Word,
    texto), texto pegado en el chat o enlace de un Google Doc compartido.

    El texto se extrae con la cascada de `backend.ingesta` y la estructura con
    la de `backend.rag.estructura`, de modo que un avance sin índice —o un PDF
    cuyas fuentes rompen a pdfplumber— ya no se queda sin secciones y, por
    tanto, sin nada que evaluar.

    `memoria` (JSON opcional) llega en la rehidratación de un chat: reconstruye
    las secciones evaluadas y reaplica el texto corregido a la memoria RAG.
    La rúbrica y el reglamento NO viajan: son los oficiales UPAO, fijos en el
    backend. El mapeo rúbrica→secciones se resuelve contra la estructura real
    del proyecto en el momento de evaluar (determinístico, sin LLM).
    """
    import json as _json

    from backend.ingesta import (
        FormatoNoSoportado,
        extraer_de_google_docs,
        extraer_de_texto,
        extraer_documento,
    )
    from backend.alcance import alcance_sugerido
    from backend.ingesta.gdocs import EnlaceInvalido
    from backend.rag import construir_vector_store, obtener_stats_secciones
    from backend.rag.estructura import resolver_estructura
    from backend.reglamento_upao import perfil_institucional_upao
    from .deps import get_embeddings
    from . import mejoras

    user_id = user.get("sub", "anon")

    # ── 1. Qué nos mandaron ──────────────────────────────────────────────────
    try:
        if archivo is not None:
            datos = await archivo.read()
            extraido = extraer_documento(nombre or archivo.filename or "", datos)
            huella = datos
        elif (texto or "").strip():
            extraido = extraer_de_texto(texto, nombre or "Texto pegado")
            huella = texto.encode("utf-8", "ignore")
        elif (enlace or "").strip():
            extraido = extraer_de_google_docs(enlace)
            huella = extraido.texto.encode("utf-8", "ignore")
        else:
            raise HTTPException(
                status_code=422,
                detail="No recibí ningún contenido: sube un archivo, pega el texto "
                       "de tu proyecto o comparte el enlace de tu Google Doc.",
            )
    except (FormatoNoSoportado, EnlaceInvalido, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[documentos] Error extrayendo el contenido")
        raise HTTPException(status_code=500, detail=f"Error leyendo el documento: {exc}")

    contenido_hash = hashlib.md5(huella).hexdigest()

    memoria_dict = {}
    if memoria:
        try:
            memoria_dict = _json.loads(memoria)
        except Exception:
            logger.warning("[documentos] memoria malformada, se ignora")

    existente = registry.buscar_documento_por_hash(user_id, contenido_hash)
    if existente:
        # El vector store se reutiliza (mismo contenido ya indexado → no
        # re-vectorizar), PERO el estado de evaluación es POR CHAT: se reemplaza
        # con la memoria de ESTE chat (vacía si es nuevo) para no arrastrar lo
        # evaluado en otra conversación con el mismo proyecto.
        mejoras.reset_memoria(existente)
        # El ALCANCE también es por chat: si el mismo proyecto se abrió en otra
        # conversación con un alcance distinto, arrastrarlo aquí calificaría de
        # más o de menos sin que el estudiante lo haya pedido en ESTE chat.
        existente.alcance = alcance_sugerido(existente)
        if memoria_dict:
            mejoras.restaurar_memoria(existente, memoria_dict)
        return _documento_a_json(existente, ya_indexado=True)

    # ── 2. Estructura + vectorización ────────────────────────────────────────
    try:
        embeddings = get_embeddings()
        estructura = resolver_estructura(extraido, embeddings=embeddings)
        vector_store = construir_vector_store(
            extraido.bloques, estructura.estructura, embeddings,
            collection_name=f"tesis_{contenido_hash[:8]}_{uuid.uuid4().hex[:6]}",
            grupos=estructura.grupos,
        )
        stats = obtener_stats_secciones(vector_store)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("[documentos] Error vectorizando")
        raise HTTPException(status_code=500, detail=f"Error procesando el documento: {exc}")

    doc = registry.registrar_documento(
        user_id=user_id,
        nombre=extraido.nombre or "proyecto",
        contenido_hash=contenido_hash,
        vector_store=vector_store,
        estructura_toc=estructura.estructura or {},
        stats=stats,
        formato=extraido.formato,
        origen_estructura=estructura.origen,
        avisos=[*extraido.avisos, *estructura.avisos],
        # Perfil institucional FIJO: el reglamento UPAO modula la conducta de los
        # agentes en todos los proyectos (ya no hay reglamentos por usuario).
        universidad="UPAO",
        programa="ingeniería de sistemas",
        perfil_institucional=perfil_institucional_upao(),
    )
    doc.alcance = alcance_sugerido(doc)

    if memoria_dict:
        mejoras.restaurar_memoria(doc, memoria_dict)

    logger.info(
        f"[documentos] '{doc.nombre}' ({doc.formato}) indexado — {len(stats)} secciones, "
        f"estructura por {estructura.origen}"
    )
    return _documento_a_json(doc)


def _documento_a_json(doc, ya_indexado: bool = False) -> dict:
    return {
        "doc_id":            doc.doc_id,
        "nombre":            doc.nombre,
        "hash":              doc.contenido_hash,
        "ya_indexado":       ya_indexado,
        "estructura_toc":    doc.estructura_toc,
        "stats":             doc.stats,
        "formato":           doc.formato,
        "origen_estructura": doc.origen_estructura,
        "avisos":            doc.avisos,
        "alcance":           doc.alcance,
    }


class FragmentoRequest(BaseModel):
    doc_id: str
    texto: str
    nombre: str = "Texto pegado"


@app.post("/api/fragmento")
def agregar_fragmento(req: FragmentoRequest, user: dict = Depends(usuario_actual)):
    """Texto pegado por el estudiante CUANDO ya tiene un proyecto indexado.

    No se toca el proyecto: se detecta a qué sección corresponde y se guarda
    como versión de trabajo pendiente, que es el mismo mecanismo que usan las
    mejoras del chat. Así, al evaluar, el sistema le pregunta si quiere usar
    ESTA versión en lugar de la de su documento, en vez de pisarla sin avisar.
    """
    from backend.rag import resolver_seccion_semantica
    from backend.rag.estructura import _pista_lexica
    from . import mejoras

    doc = _obtener_doc_o_404(req.doc_id, user)
    texto = (req.texto or "").strip()
    if len(texto) < 40:
        raise HTTPException(status_code=422, detail="El texto pegado es demasiado corto.")

    toc = list(doc.estructura_toc or {})
    seccion = None

    # Primero los marcadores inequívocos («objetivo general», «hipótesis»…), que
    # son mucho más precisos que la similitud pura; después el RAG del proyecto.
    pista = _pista_lexica(texto)
    if pista:
        seccion = pista if pista in toc else resolver_seccion_semantica(doc.vector_store, pista, toc)
    if not seccion and toc:
        seccion = resolver_seccion_semantica(doc.vector_store, texto[:600], toc)

    if not seccion:
        return {
            "seccion": None,
            "mensaje": (
                "Guardé tu texto, pero no logré ubicarlo en una sección concreta de tu "
                "proyecto. Dime a qué parte corresponde (por ejemplo «son mis objetivos») "
                "y lo asocio."
            ),
        }

    mejoras.registrar_mejora_chat(doc, seccion, texto)
    logger.info(f"[fragmento] Texto pegado asociado a «{seccion}» ({len(texto)} chars)")
    return {
        "seccion": seccion,
        "mensaje": (
            f"Indexé tu texto como versión de trabajo de **{seccion}**. Tu documento "
            f"original no se modificó: cuando pidas «evalúa mi {seccion}» te preguntaré "
            "si quieres que evalúe esta versión o la de tu archivo."
        ),
    }


class AlcanceRequest(BaseModel):
    doc_id: str
    grupos: list[str] | None = None
    todo: bool = False


@app.get("/api/alcance")
def catalogo_alcance(doc_id: str = "", user: dict = Depends(usuario_actual)):
    """Grupos evaluables y alcance actual del proyecto.

    El frontend lo usa para pintar el selector «¿qué quieres que evalúe?» con
    los grupos que el estudiante ya tiene escritos premarcados.
    """
    from backend.alcance import grupos_disponibles

    doc = registry.obtener_documento(doc_id) if doc_id else None
    if doc is not None and doc.user_id != user.get("sub", "anon"):
        doc = None

    cubiertos: dict[str, int] = {}
    if doc is not None:
        from backend.config import _buscar_items_seccion
        for stat in (doc.stats or []):
            for num in _buscar_items_seccion(stat.get("seccion", "")):
                cubiertos[str(num)] = max(cubiertos.get(str(num), 0), stat.get("chars", 0))

    return {
        "grupos":            grupos_disponibles(),
        "alcance":           (doc.alcance if doc else {}),
        "chars_por_item":    cubiertos,
    }


@app.post("/api/alcance")
def fijar_alcance(req: AlcanceRequest, user: dict = Depends(usuario_actual)):
    """El estudiante declara qué partes de su proyecto quiere que se evalúen."""
    from backend import alcance as alcance_mod

    doc = _obtener_doc_o_404(req.doc_id, user)
    doc.alcance = alcance_mod.completo() if req.todo else alcance_mod.normalizar(req.grupos, doc)
    logger.info(
        f"[alcance] '{doc.nombre}' → {', '.join(doc.alcance['grupos'])} "
        f"({len(doc.alcance['items'])} ítems)"
    )
    return {"alcance": doc.alcance}


def _es_encabezado_capitulo(nombre: str) -> bool:
    """Encabezado de capítulo ('1.', '2 MARCO…'): prefijo numérico de un solo nivel."""
    from backend.config import _prefijo_num
    pref = _prefijo_num(nombre)
    return bool(pref) and "." not in pref


@app.get("/api/rubrica")
def rubrica_oficial(doc_id: str = "", user: dict = Depends(usuario_actual)):
    """Rúbrica oficial UPAO (fija) para mostrar al estudiante.

    Si se pasa `doc_id` de un proyecto vivo, incluye `mapa_secciones`: a qué
    secciones REALES del TOC de ese proyecto se mapea cada ítem. El mapeo es el
    mismo que usan los agentes al evaluar (determinístico, sin LLM), así que lo
    que se muestra coincide con lo que se califica.
    """
    from backend.config import (
        ESCALA_ETIQUETAS_UPAO,
        ESCALA_MAX,
        RUBRICA_GRUPOS_UPAO,
        RUBRICA_ITEMS_UPAO,
        _buscar_items_seccion,
    )

    mapa_secciones: dict[str, list[int]] | None = None
    doc = registry.obtener_documento(doc_id) if doc_id else None
    if doc is not None and doc.user_id == user.get("sub", "anon") and doc.estructura_toc:
        # Ítems por sección real del TOC; los encabezados de capítulo se omiten
        # cuando el ítem ya tiene una subsección específica (evita duplicados).
        por_item: dict[int, list[str]] = {}
        for sec in doc.estructura_toc:
            for n in _buscar_items_seccion(sec):
                por_item.setdefault(n, []).append(sec)
        mapa_secciones = {}
        for n, secs in por_item.items():
            hojas = [s for s in secs if not _es_encabezado_capitulo(s)]
            for s in (hojas or secs):
                mapa_secciones.setdefault(s, [])
                if n not in mapa_secciones[s]:
                    mapa_secciones[s].append(n)

    return {
        "nombre":         "Ficha de evaluación de proyecto de tesis — UPAO (oficial)",
        "total_items":    len(RUBRICA_ITEMS_UPAO),
        "escala_max":     ESCALA_MAX,
        "escala":         {str(k): v for k, v in ESCALA_ETIQUETAS_UPAO.items()},
        "puntaje_maximo": len(RUBRICA_ITEMS_UPAO) * ESCALA_MAX,
        "grupos": [
            {"titulo": titulo,
             "items": [{"numero": n, "descripcion": RUBRICA_ITEMS_UPAO[n]} for n in nums]}
            for titulo, nums in RUBRICA_GRUPOS_UPAO
        ],
        "mapa_secciones": mapa_secciones,
    }


@app.get("/api/reglamento")
def reglamento_oficial(_user: dict = Depends(usuario_actual)):
    """Reglamento UPAO fijo: identificación, vigencia, puntos clave para el
    estudiante y el perfil con el que se modula la conducta de los agentes."""
    from backend.reglamento_upao import PERFIL_AGENTES_UPAO, REGLAMENTO_UPAO

    return {**REGLAMENTO_UPAO, "perfil_agentes": PERFIL_AGENTES_UPAO}


def _obtener_doc_o_404(doc_id: str, user: dict):
    doc = registry.obtener_documento(doc_id)
    if doc is None or doc.user_id != user.get("sub", "anon"):
        raise HTTPException(
            status_code=404,
            detail="Documento no disponible en el servidor (puede haberse reiniciado). "
                   "Vuelve a subir tu PDF para continuar.",
        )
    return doc


class TurnoChat(BaseModel):
    rol: str
    contenido: str


class ChatRequest(BaseModel):
    mensaje: str
    doc_id: str | None = None
    conversacion_id: str | None = None
    max_iteraciones: int = 2
    contexto_previo: str = ""
    historial: list[TurnoChat] = []
    confirmar_reevaluacion: bool = False
    decision_mejoras: str | None = None


class HeartbeatRequest(BaseModel):
    conversacion_id: str | None = None


@app.post("/api/heartbeat")
def heartbeat(req: HeartbeatRequest, user: dict = Depends(usuario_actual)):
    """Ping de presencia: el frontend lo manda cada ~60s mientras la pestaña está
    visible. Mide el TIEMPO DE USO real (no cuenta como consulta)."""
    from . import analytics
    analytics.registrar_evento(
        user.get("sub", "anon"), analytics.HEARTBEAT,
        conversacion_id=req.conversacion_id,
    )
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest, user: dict = Depends(usuario_actual)):
    from .intent import interpretar_mensaje
    from . import mejoras, analytics

    user_id = user.get("sub", "anon")

    doc = registry.obtener_documento(req.doc_id) if req.doc_id else None
    if doc is not None and doc.user_id != user.get("sub", "anon"):
        doc = None

    toc_nombres = sorted(
        (doc.estructura_toc or {}).items(), key=lambda x: x[1]
    ) if doc else []
    toc_nombres = [n for n, _ in toc_nombres]

    historial = [t.model_dump() for t in req.historial]

    intencion = interpretar_mensaje(
        mensaje=req.mensaje,
        toc_nombres=toc_nombres,
        contexto_previo=req.contexto_previo,
        hay_documento=doc is not None,
        historial=historial,
        vector_store=doc.vector_store if doc else None,
    )

    if intencion["modo"] == "conversacion":
        from .conversador import responder_consulta
        from .deps import get_biblioteca

        respuesta = responder_consulta(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
        )
        analytics.registrar_evento(
            user_id, analytics.CONSULTA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={"tiene_documento": doc is not None},
        )
        return {"tipo": "conversacion", "respuesta": respuesta}

    if intencion["modo"] == "ideacion":
        # El estudiante aún no tiene tema. Es el único modo que funciona SIN
        # proyecto indexado, y el que más aprovecha el corpus del repositorio.
        from .ideacion import responder_ideacion
        from .deps import get_biblioteca

        res = responder_ideacion(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
        )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={"panel": "ideacion", "propuso_titulo": bool(res.get("titulo"))},
        )
        return {"tipo": "conversacion", "respuesta": res["respuesta"]}

    if intencion["modo"] == "metodologia":
        # Operacionalización, matriz de consistencia y marco metodológico.
        from .metodologia import responder_metodologia
        from .deps import get_biblioteca

        res = responder_metodologia(
            mensaje=req.mensaje, historial=historial, doc=doc,
            biblioteca=get_biblioteca(),
        )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={"panel": "metodologia"},
        )
        return {"tipo": "conversacion", "respuesta": res["respuesta"]}

    if intencion["modo"] == "antecedentes":
        # Antecedentes y marco teórico: estrategia de búsqueda y estructura, nunca
        # el contenido — las citas las verifica y escribe el estudiante.
        from .antecedentes import responder_antecedentes
        from .deps import get_biblioteca

        res = responder_antecedentes(
            mensaje=req.mensaje, historial=historial, doc=doc,
            biblioteca=get_biblioteca(),
        )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={"panel": "antecedentes"},
        )
        return {"tipo": "conversacion", "respuesta": res["respuesta"]}

    if intencion["modo"] == "planteamiento":
        # Cadena problema → preguntas específicas (Bloom) → objetivos, con enfoque
        # por objetivo y reparto realista entre Tesis 1 y Tesis 2.
        from .planteamiento import responder_planteamiento
        from .deps import get_biblioteca

        res = responder_planteamiento(
            mensaje=req.mensaje, historial=historial, doc=doc,
            biblioteca=get_biblioteca(),
        )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={"panel": "planteamiento"},
        )
        return {"tipo": "conversacion", "respuesta": res["respuesta"]}

    if intencion["modo"] == "titulo":
        # Panel de título: proponente → verificador de anclaje → auditor.
        from .titulo_panel import responder_titulo
        from .deps import get_biblioteca

        res = responder_titulo(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
        )
        respuesta = res["respuesta"]
        titulo = (res.get("titulo") or "").strip()
        # El título es corto, así que no pasa el umbral de 200 chars del debate rápido;
        # se guarda igual para que «evalúa mi título» pueda calificar ESTA versión.
        if doc is not None and titulo and res.get("seccion"):
            mejoras.registrar_mejora_chat(doc, res["seccion"], titulo)
            respuesta += (
                f"\n\n---\n💡 Guardé este título como tu versión de trabajo. Si quieres la "
                "calificación formal, dime «evalúa mi título»."
            )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            secciones=[res.get("seccion")] if res.get("seccion") else None,
            payload={"panel": "titulo", "propuso_titulo": bool(titulo)},
        )
        return {"tipo": "conversacion", "respuesta": respuesta}

    if intencion["modo"] == "mejora":
        # Mini-grafo de debate rápido (mejorar/corregir/redactar). Devuelve una
        # respuesta de chat simple, SIN el panel de la red de evaluación.
        from .debate_rapido import responder_mejora_rapida
        from .deps import get_biblioteca

        res = responder_mejora_rapida(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
        )
        respuesta = res["respuesta"]
        sec = res.get("seccion")
        texto = (res.get("texto_mejorado") or "").strip()
        # Guarda la mejora de sección como PENDIENTE (sin marcar evaluada): si luego dices
        # «evalúa mi <sección>», la red puede calificar TU mejora en vez del texto original.
        if doc is not None and sec and len(texto) > 200:
            mejoras.registrar_mejora_chat(doc, sec, texto)
            respuesta += (
                f"\n\n---\n💡 Guardé esta versión mejorada de **{sec}**. Si quieres que la "
                f"evaluación formal la use en lugar de tu texto original, dime «evalúa mi {sec}» "
                "y te preguntaré antes de aplicarla."
            )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            secciones=[sec] if sec else None,
            payload={"texto_mejorado": bool(sec and len(texto) > 200)},
        )
        return {"tipo": "conversacion", "respuesta": respuesta}

    objetivo = intencion["secciones"] if intencion["modo"] == "secciones" else []

    ya_evaluadas = [s for s in objetivo if s in doc.evaluadas]
    if ya_evaluadas and not req.confirmar_reevaluacion:
        lista = ", ".join(f"**{s}**" for s in ya_evaluadas)
        return {
            "tipo": "confirmacion",
            "subtipo": "reevaluar",
            "secciones": ya_evaluadas,
            "mensaje": (
                f"La sección {lista} ya fue evaluada en esta asesoría. "
                "¿Quieres que la red de agentes la revise de nuevo?"
            ),
        }

    pend = mejoras.pendientes(doc)
    pend_otras = [s for s in pend if s not in objetivo]
    # Mejoras del CHAT para las secciones que se van a evaluar: si las aplico, la red
    # evalúa TU versión mejorada del chat (no el original). Las del propio grafo NO se
    # reaplican sobre su sección (la red las reescribe igual desde el original).
    pend_chat_obj = [
        s for s in pend
        if s in objetivo and (doc.mejoras.get(s, {}).get("origen") == "chat")
    ]
    pend_ofrecer = pend_otras + pend_chat_obj
    if pend_ofrecer and req.decision_mejoras is None:
        lista = ", ".join(f"**{s}**" for s in pend_ofrecer)
        return {
            "tipo": "confirmacion",
            "subtipo": "aplicar_mejoras",
            "secciones": pend_ofrecer,
            "mensaje": (
                f"Tengo texto mejorado de {lista} que aún no incorporé a mi memoria "
                "(de tu chat o de una revisión previa). ¿Lo uso en lugar del texto original "
                "de tu PDF para esta evaluación? (Tu PDF no se modifica — solo lo que yo "
                "recuerdo del proyecto. Se incorpora únicamente el texto corregido, no las sugerencias.)"
            ),
        }

    aplicadas: list[str] = []
    if req.decision_mejoras == "aplicar" and pend_ofrecer:
        aplicadas = mejoras.aplicar_pendientes(doc, pend_ofrecer)
        logger.info(f"[chat] Mejoras incorporadas a la memoria RAG: {aplicadas}")

    max_iter = max(1, min(3, req.max_iteraciones))
    # La revisión COMPLETA usa por defecto 1 iteración (el control del frontend arranca
    # en 1). Si el usuario SUBE el número, SOLO el núcleo del grafo itera hasta ese valor
    # (con corte al 90%); el barrido por ítem y el LLM-as-judge siguen siendo de 1 pasada.
    run = registry.registrar_run(
        user_id=user_id,
        doc_id=doc.doc_id,
        modo=intencion["modo"],
        secciones=intencion["secciones"],
        max_iteraciones=max_iter,
        conversacion_id=req.conversacion_id,
    )
    return {
        "tipo": "run",
        "run_id": run.run_id,
        "modo": run.modo,
        "secciones": run.secciones,
        "max_iteraciones": max_iter,
        "mejoras_aplicadas": aplicadas,
    }



def _sse(evento: dict) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


def _eventos_run(run, doc):
    """Generador síncrono: ejecuta el run y emite eventos (corre en threadpool)."""
    import time as _time
    from .grafo import ejecutar_seccion, informe_secciones_md
    from .full_review import ejecutar_revision_completa
    from . import analytics

    run.estado = "ejecutando"
    _t0 = _time.monotonic()
    yield {"tipo": "inicio", "modo": run.modo, "secciones": run.secciones}

    adquirido = registry.RUN_EXCLUSIVO.acquire(timeout=0.1)
    if not adquirido:
        yield {"tipo": "fase", "fase": "cola", "detalle": "Esperando a que termine otra revisión…"}
        registry.RUN_EXCLUSIVO.acquire()
        adquirido = True

    try:
        if run.modo == "completo":
            ultimo = None
            for evento in ejecutar_revision_completa(doc, run.max_iteraciones, run.cancelar):
                ultimo = evento
                yield evento
            run.estado = (
                "cancelado" if (ultimo or {}).get("tipo") == "cancelado"
                else "completado"
            )
            # El chat rápido recordará esta evaluación (no pierde el hilo).
            if run.estado == "completado" and (ultimo or {}).get("resumen_chat"):
                doc.ultima_revision = ultimo["resumen_chat"]
        else:
            from . import mejoras

            resumenes: list[dict] = []
            for seccion in run.secciones:
                thread_id = str(uuid.uuid4())
                for evento in ejecutar_seccion(
                    doc, seccion, run.max_iteraciones, thread_id, run.cancelar
                ):
                    if evento["tipo"] == "seccion_completada":
                        resumen = evento["resumen"] | {"seccion": seccion}
                        resumenes.append(resumen)
                        if not resumen.get("vacia"):
                            mejoras.registrar_resultado(doc, seccion, resumen)
                    elif evento["tipo"] == "cancelado":
                        run.estado = "cancelado"
                        yield evento
                        return
                    else:
                        yield evento
                if run.cancelar.is_set():
                    run.estado = "cancelado"
                    yield {"tipo": "cancelado"}
                    return

            informe = informe_secciones_md(resumenes)
            run.estado = "completado"

            # El chat rápido recordará esta revisión por secciones.
            _partes = []
            for r in resumenes:
                if r.get("vacia"):
                    continue
                p, mx = r.get("puntaje"), r.get("puntaje_max")
                nota = f"{round(p)}/{mx}" if (p is not None and mx) else "s/n"
                deb = "; ".join((r.get("puntos_debiles") or [])[:2])
                _partes.append(f"{r.get('seccion')}: {nota}" + (f" (falta: {deb})" if deb else ""))
            if _partes:
                doc.ultima_revision = {
                    "tipo": "secciones",
                    "texto": "Última revisión por secciones — " + " · ".join(_partes) + ".",
                }

            yield {"tipo": "resultado", "informe_md": informe,
                   "detalles": [r["detalle"] for r in resumenes if r.get("detalle")],
                   "resumen_chat": doc.ultima_revision or None,
                   "resumen": {"secciones": [r.get("seccion") for r in resumenes]}}
    except Exception as exc:
        logger.exception(f"[runs] Error en run {run.run_id}")
        run.estado = "error"
        yield {"tipo": "error", "detalle": f"[{type(exc).__name__}] {exc}"}
    finally:
        if adquirido:
            registry.RUN_EXCLUSIVO.release()
        tipo_evento = (
            analytics.REVISION_COMPLETA if run.modo == "completo"
            else analytics.REVISION_SECCIONES
        )
        analytics.registrar_evento(
            run.user_id, tipo_evento,
            conversacion_id=run.conversacion_id,
            modo=run.modo,
            secciones=run.secciones or None,
            duracion_ms=int((_time.monotonic() - _t0) * 1000),
            estado=run.estado,
            payload={"max_iteraciones": run.max_iteraciones},
        )

    yield {"tipo": "fin", "estado": run.estado}


@app.get("/api/runs/{run_id}/stream")
def stream_run(run_id: str, user: dict = Depends(usuario_actual)):
    run = registry.obtener_run(run_id)
    if run is None or run.user_id != user.get("sub", "anon"):
        raise HTTPException(status_code=404, detail="Run no encontrado.")
    if run.estado != "pendiente":
        raise HTTPException(status_code=409, detail=f"Run ya está en estado '{run.estado}'.")

    doc = _obtener_doc_o_404(run.doc_id, user)

    def gen():
        for evento in _eventos_run(run, doc):
            yield _sse(evento)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/runs/{run_id}/cancelar")
def cancelar_run(run_id: str, user: dict = Depends(usuario_actual)):
    run = registry.obtener_run(run_id)
    if run is None or run.user_id != user.get("sub", "anon"):
        raise HTTPException(status_code=404, detail="Run no encontrado.")
    run.cancelar.set()
    return {"ok": True, "estado": run.estado}



def _extraer_texto_pdf(contenido: bytes, seccion: str) -> str:
    import io
    import pdfplumber

    texto_completo = []
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text()
            if t:
                texto_completo.append(t)
    return "\n\n".join(texto_completo)


@app.post("/evaluar")
async def evaluar_tesis(
    archivo_pdf: UploadFile = File(...),
    universidad: str = Form(...),
    programa: str = Form(...),
    seccion: str = Form(..., description="Nombre de la sección a evaluar"),
    modalidad: str = Form(default="tesis"),
):
    """Versión legacy síncrona: PDF completo como contexto, sin RAG ni streaming."""
    from backend.graph.workflow import create_graph, get_run_config
    from .grafo import construir_estado_inicial

    run_id = str(uuid.uuid4())
    try:
        contenido_pdf = await archivo_pdf.read()
        texto_seccion = _extraer_texto_pdf(contenido_pdf, seccion)

        from config import Config

        estado_inicial = construir_estado_inicial(
            run_id=run_id,
            seccion=seccion,
            contexto_tesis=texto_seccion,
            contexto_dependencias="",
            contexto_teorico="",
            rubrica_dinamica=None,
            max_iteraciones=Config.MAX_ITERATIONS,
            universidad=universidad,
            programa=programa,
            modalidad=modalidad,
        )

        graph = create_graph()
        run_config = get_run_config(thread_id=run_id)
        estado_final = graph.invoke(estado_inicial, config=run_config)

        ruta_json = f"./outputs/run_{run_id}.json"
        from evaluator.evaluator import evaluar_desde_archivo
        metricas = evaluar_desde_archivo(ruta_json)

        return JSONResponse(content={
            "run_id":             run_id,
            "texto_mejorado":     estado_final.get("texto_iterado"),
            "puntaje_final":      estado_final.get("puntaje_estimado"),
            "metricas":           metricas["metricas"],
            "resultado_consenso": estado_final.get("resultado_consenso"),
        })
    except Exception as exc:
        logger.exception(f"[API] Error en run_id={run_id}")
        raise HTTPException(status_code=500, detail=str(exc))
