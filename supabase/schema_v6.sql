-- ══════════════════════════════════════════════════════════════════════════
-- MentorIA — Esquema v6 (heartbeats: tiempo de uso real)
-- Ejecutar DESPUÉS de schema_v5.sql.  En: Supabase → SQL Editor → Run. Idempotente.
--
-- El frontend ahora manda un evento tipo 'heartbeat' cada ~60s mientras la
-- pestaña está visible. Eso permite medir el TIEMPO DE USO de inicio a fin
-- (no solo el lapso entre consultas). Estas vistas se corrigen para que el
-- heartbeat CUENTE en el tiempo/sesiones pero NO infle el nº de consultas.
--
-- Usa create-or-replace conservando los nombres/tipos de columna, así las
-- vistas panel_* (v5) que dependen de estas siguen funcionando sin recrearse.
-- ══════════════════════════════════════════════════════════════════════════

-- ── Consultas por usuario: total EXCLUYE heartbeats ─────────────────────────
create or replace view analytics.consultas_por_usuario as
select
  user_id,
  count(*) filter (where tipo <> 'heartbeat')          as total_consultas,
  count(*) filter (where tipo = 'consulta_rapida')     as consultas_rapidas,
  count(*) filter (where tipo = 'mejora_rapida')        as mejoras_rapidas,
  count(*) filter (where tipo = 'revision_secciones')  as revisiones_secciones,
  count(*) filter (where tipo = 'revision_completa')   as revisiones_completas,
  count(distinct conversacion_id)
    filter (where tipo <> 'heartbeat')                  as chats_usados,
  min(created_at)                                       as primera_actividad,
  max(created_at)                                       as ultima_actividad
from analytics.eventos
group by user_id;

-- ── Consultas por chat: total EXCLUYE heartbeats ────────────────────────────
create or replace view analytics.consultas_por_chat as
select
  conversacion_id,
  user_id,
  count(*) filter (where tipo <> 'heartbeat')          as total_consultas,
  count(*) filter (where tipo = 'consulta_rapida')     as consultas_rapidas,
  count(*) filter (where tipo = 'mejora_rapida')        as mejoras_rapidas,
  count(*) filter (where tipo = 'revision_secciones')  as revisiones_secciones,
  count(*) filter (where tipo = 'revision_completa')   as revisiones_completas,
  min(created_at)                                       as inicio,
  max(created_at)                                       as fin
from analytics.eventos
where conversacion_id is not null
group by conversacion_id, user_id;

-- ── Sesiones: el tiempo usa TODOS los eventos (incl. heartbeats) ────────────
-- La sesionización por huecos de 30 min ahora es precisa: con un latido por
-- minuto, (fin - inicio) refleja el tiempo realmente dentro de la app.
-- consultas_en_sesion sigue contando solo consultas reales (sin heartbeats).
create or replace view analytics.sesiones as
with marcados as (
  select
    user_id, created_at, tipo,
    case
      when lag(created_at) over (partition by user_id order by created_at) is null
        or created_at - lag(created_at) over (partition by user_id order by created_at)
           > interval '30 minutes'
      then 1 else 0
    end as nueva_sesion
  from analytics.eventos
),
numeradas as (
  select *,
    sum(nueva_sesion) over (partition by user_id order by created_at
                            rows between unbounded preceding and current row) as sesion_seq
  from marcados
)
select
  user_id,
  sesion_seq,
  min(created_at)                                       as inicio,
  max(created_at)                                       as fin,
  count(*) filter (where tipo <> 'heartbeat')          as consultas_en_sesion,
  extract(epoch from (max(created_at) - min(created_at))) as duracion_segundos
from numeradas
group by user_id, sesion_seq;
