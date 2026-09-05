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
    """Estado + huella del código desplegado.

    `corpus_tesis` y `compuertas` permiten comprobar de un vistazo si un redeploy
    llevó realmente la versión nueva (si el corpus va en 0, el JSON no entró en la
    imagen y los avisos de duplicidad quedarían mudos sin dar error).
    """
    try:
        from backend.upao_tesis import corpus_tesis
        from api.debate_rapido import _GRAFO
        nodos = sorted(n for n in _GRAFO.get_graph().nodes if not n.startswith("__"))
        return {
            "status": "ok",
            "corpus_tesis": len(corpus_tesis()),
            "nodos_minigrafo": nodos,
        }
    except Exception as exc:  # nunca tumbar el health por el diagnóstico
        return {"status": "ok", "diagnostico_error": str(exc)[:200]}


@app.get("/api/biblioteca")
def biblioteca(_user: dict = Depends(usuario_actual)):
    from backend.rag import listar_libros
    from .deps import get_biblioteca

    libros = listar_libros(get_biblioteca())
    return {"libros": libros, "total_fragmentos": sum(l["fragmentos"] for l in libros)}



@app.post("/api/documentos")
async def subir_documento(
    archivo: UploadFile = File(...),
    memoria: str = Form(default=""),
    user: dict = Depends(usuario_actual),
):
    """
    Extrae texto del PDF (omitiendo el índice), vectoriza y devuelve la estructura.

    `memoria` (JSON opcional) llega en la rehidratación de un chat: reconstruye
    las secciones evaluadas y reaplica el texto corregido a la memoria RAG.
    La rúbrica y el reglamento NO viajan: son los oficiales UPAO, fijos en el
    backend. El mapeo rúbrica→secciones se resuelve contra el TOC real del
    proyecto en el momento de evaluar (determinístico, sin LLM).
    """
    import json as _json

    from backend.rag import (
        construir_vector_store,
        extraer_contenido_sin_indice,
        obtener_stats_secciones,
    )
    from backend.reglamento_upao import perfil_institucional_upao
    from .deps import get_embeddings
    from . import mejoras

    contenido = await archivo.read()
    pdf_hash = hashlib.md5(contenido).hexdigest()
    user_id = user.get("sub", "anon")

    memoria_dict = {}
    if memoria:
        try:
            memoria_dict = _json.loads(memoria)
        except Exception:
            logger.warning("[documentos] memoria malformada, se ignora")

    existente = registry.buscar_documento_por_hash(user_id, pdf_hash)
    if existente:
        # El vector store se reutiliza (mismo PDF ya indexado → no re-vectorizar),
        # PERO el estado de evaluación es POR CHAT: se reemplaza con la memoria de
        # ESTE chat (vacía si es nuevo) para no arrastrar lo evaluado en otra
        # conversación con el mismo proyecto.
        mejoras.reset_memoria(existente)
        if memoria_dict:
            mejoras.restaurar_memoria(existente, memoria_dict)
        return _documento_a_json(existente, ya_indexado=True)

    try:
        paginas, estructura_toc = extraer_contenido_sin_indice(contenido)
        total_chars = sum(len(t) for _, t in paginas)
        if total_chars < 100:
            raise ValueError(
                "El PDF parece vacío o es un escaneo sin texto seleccionable. "
                "Asegúrate de que el PDF sea nativo (no solo imágenes)."
            )

        vector_store = construir_vector_store(
            paginas, estructura_toc, get_embeddings(),
            collection_name=f"tesis_{pdf_hash[:8]}_{uuid.uuid4().hex[:6]}",
        )
        stats = obtener_stats_secciones(vector_store)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("[documentos] Error vectorizando")
        raise HTTPException(status_code=500, detail=f"Error procesando el PDF: {exc}")

    doc = registry.registrar_documento(
        user_id=user_id,
        nombre=archivo.filename or "tesis.pdf",
        pdf_hash=pdf_hash,
        vector_store=vector_store,
        estructura_toc=estructura_toc or {},
        stats=stats,
        # Perfil institucional FIJO: el reglamento UPAO modula la conducta de los
        # agentes en todos los proyectos (ya no hay reglamentos por usuario).
        universidad="UPAO",
        programa="ingeniería de sistemas",
        perfil_institucional=perfil_institucional_upao(),
    )

    if memoria_dict:
        mejoras.restaurar_memoria(doc, memoria_dict)

    logger.info(f"[documentos] '{doc.nombre}' indexado — {len(stats)} secciones")
    return _documento_a_json(doc)


def _documento_a_json(doc, ya_indexado: bool = False) -> dict:
    return {
        "doc_id":         doc.doc_id,
        "nombre":         doc.nombre,
        "hash":           doc.pdf_hash,
        "ya_indexado":    ya_indexado,
        "estructura_toc": doc.estructura_toc,
        "stats":          doc.stats,
    }


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
        SECCION_ITEMS_MAP,
        resolver_unidad_toc,
    )

    mapa_secciones: dict[str, list[int]] | None = None
    doc = registry.obtener_documento(doc_id) if doc_id else None
    if doc is not None and doc.user_id == user.get("sub", "anon") and doc.estructura_toc:
        # Ítems por sección real del TOC, con el MISMO resolver que usa la evaluación
        # (TOC-consciente: subsecciones con match débil heredan la unidad del padre).
        # Los encabezados de capítulo se omiten cuando el ítem ya tiene subsección.
        toc = list(doc.estructura_toc)
        por_item: dict[int, list[str]] = {}
        for sec in toc:
            unidad = resolver_unidad_toc(sec, toc)
            for n in SECCION_ITEMS_MAP.get(unidad or "", []):
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
    from concurrent.futures import ThreadPoolExecutor

    from .intent import interpretar_mensaje
    from . import ficha as ficha_mod
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

    # FICHA DEL PROYECTO. Se actualiza en un hilo aparte para que su llamada al LLM
    # corra EN PARALELO con la clasificación de intención en vez de sumarse a ella:
    # el turno no se hace más lento por tener memoria.
    ficha_previa = ficha_mod.cargar(req.conversacion_id)
    _pool = ThreadPoolExecutor(max_workers=1)
    _fut_ficha = _pool.submit(ficha_mod.extraer_ficha, req.mensaje, historial, ficha_previa)

    def _ficha_actual() -> dict:
        """La ficha ya actualizada. Si la extracción tarda o falla, sigue con la
        previa: perder un dato nuevo es recuperable, bloquear la respuesta no."""
        try:
            actualizada = _fut_ficha.result(timeout=25)
        except Exception:
            logger.warning("[chat] La extracción de ficha no llegó a tiempo; uso la previa.")
            return ficha_previa
        finally:
            _pool.shutdown(wait=False)
        ficha_mod.guardar(req.conversacion_id, actualizada)
        return actualizada

    intencion = interpretar_mensaje(
        mensaje=req.mensaje,
        toc_nombres=toc_nombres,
        contexto_previo=req.contexto_previo,
        hay_documento=doc is not None,
        historial=historial,
        vector_store=doc.vector_store if doc else None,
    )

    # Se resuelve SIEMPRE, sea cual sea la ruta: la ficha se alimenta también de los
    # turnos que acaban en revisión, y así el hilo de extracción siempre se cierra.
    ficha_actual = _ficha_actual()

    if intencion["modo"] == "conversacion":
        from .conversador import responder_consulta
        from .deps import get_biblioteca

        respuesta = responder_consulta(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
            # También en los turnos de charla: es donde el estudiante suele soltar
            # su tema y su problema por primera vez, y donde antes se perdían.
            ficha=ficha_actual,
        )
        analytics.registrar_evento(
            user_id, analytics.CONSULTA_RAPIDA,
            conversacion_id=req.conversacion_id,
            payload={
                "tiene_documento": doc is not None,
                "campos_ficha": len(ficha_mod.completos(ficha_actual)),
            },
        )
        return {"tipo": "conversacion", "respuesta": respuesta}

    if intencion["modo"] == "mejora":
        # Mini-grafo multiagente (aclarar dudas / preguntar antes de redactar / redactar
        # y mejorar). Devuelve una respuesta de chat simple, SIN el panel de la red de
        # evaluación. `modo` dice qué ruta tomó el triaje del grafo.
        from .debate_rapido import responder_mejora_rapida
        from .deps import get_biblioteca

        res = responder_mejora_rapida(
            mensaje=req.mensaje,
            historial=historial,
            doc=doc,
            biblioteca=get_biblioteca(),
            ficha=ficha_actual,
        )
        respuesta = res["respuesta"]
        sec = res.get("seccion")
        texto = (res.get("texto_mejorado") or "").strip()
        # Guarda la redacción de la sección como PENDIENTE (sin marcar evaluada): si luego
        # dices «evalúa mi <sección>», la red puede calificar TU versión en vez del original.
        # En los turnos de elicitación o de consulta no hay texto de tesis: no se guarda nada.
        guardada = doc is not None and bool(sec) and len(texto) > 200
        if guardada:
            mejoras.registrar_mejora_chat(doc, sec, texto)
            respuesta += (
                f"\n\n---\n💡 Guardé esta versión de **{sec}**. Si quieres que la "
                f"evaluación formal la use en lugar de tu texto original, dime «evalúa mi {sec}» "
                "y te preguntaré antes de aplicarla."
            )
        analytics.registrar_evento(
            user_id, analytics.MEJORA_RAPIDA,
            conversacion_id=req.conversacion_id,
            secciones=[sec] if sec else None,
            payload={
                "texto_mejorado": guardada,
                "modo_minigrafo": res.get("modo"),
                # Para medir en la analítica de la tesis si el bucle de elicitación
                # desaparece: cuántos datos tenía la ficha y cuántas tandas de
                # preguntas seguidas llevaba el estudiante en este turno.
                "campos_ficha": len(ficha_mod.completos(ficha_actual)),
                "elicitaciones_previas": ficha_mod.elicitaciones_seguidas(historial),
            },
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
