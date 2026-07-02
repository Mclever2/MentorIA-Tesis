"""
Captura de eventos de uso para la analítica de la tesis.

Cada "consulta" que hace un usuario se registra en analytics.eventos (Supabase)
llamando al RPC public.registrar_evento con la SERVICE ROLE KEY. Es el único
punto de verdad del TIPO de consulta (lo decide /api/chat), así que no se puede
falsear desde el navegador.

Diseño:
  • Fire-and-forget en un hilo de fondo → NO añade latencia a la respuesta.
  • Nunca lanza excepción hacia el request → si la analítica falla, la app sigue.
  • No-op si falta SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY → dev local sin Supabase.
"""

import os
import logging
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

_HABILITADO = bool(SUPABASE_URL and SERVICE_ROLE_KEY)

# Tipos de evento válidos (deben coincidir con las vistas de schema_v4.sql).
CONSULTA_RAPIDA    = "consulta_rapida"
MEJORA_RAPIDA      = "mejora_rapida"
REVISION_SECCIONES = "revision_secciones"
REVISION_COMPLETA  = "revision_completa"
HEARTBEAT          = "heartbeat"  # ping de presencia (mide tiempo de uso, no es consulta)

if not _HABILITADO:
    logger.info("[analytics] Deshabilitada (falta SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY).")


def registrar_evento(
    user_id: str,
    tipo: str,
    conversacion_id: Optional[str] = None,
    modo: Optional[str] = None,
    secciones: Optional[list] = None,
    duracion_ms: Optional[int] = None,
    estado: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """Registra un evento de uso sin bloquear el request (hilo de fondo)."""
    if not _HABILITADO:
        return
    if not user_id or user_id in ("anon", "dev-local"):
        # Sin usuario real autenticado no aporta dato a la tesis.
        return

    cuerpo = {
        "p_user_id": user_id,
        "p_tipo": tipo,
        "p_conversacion_id": conversacion_id,
        "p_modo": modo,
        "p_secciones": secciones,
        "p_duracion_ms": duracion_ms,
        "p_estado": estado,
        "p_payload": payload or {},
    }
    threading.Thread(target=_enviar, args=(cuerpo,), daemon=True).start()


def _enviar(cuerpo: dict) -> None:
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/registrar_evento",
            json=cuerpo,
            headers={
                "apikey": SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("[analytics] RPC devolvió %s: %s", resp.status_code, resp.text[:300])
    except Exception:
        logger.warning("[analytics] No se pudo registrar el evento", exc_info=True)
