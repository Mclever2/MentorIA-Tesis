-- ══════════════════════════════════════════════════════════════════════════
-- MentorIA — Esquema v5 (vistas de analítica IDENTIFICADAS por usuario)
-- Ejecutar DESPUÉS de schema_v4.sql.  En: Supabase → SQL Editor → Run.  Idempotente.
--
-- v4 agrupaba por user_id (un UUID anónimo). Aquí cruzamos con auth.users para
-- ver el EMAIL de cada usuario y juntamos consultas + tiempo de uso en una sola
-- tabla "ancha" lista para Looker Studio / Metabase, sin escribir queries.
--
-- Nota de privacidad para la tesis: el email es dato personal. Úsalo solo en tu
-- panel privado; en anexos/publicación reemplázalo por un código (P1, P2, …).
-- ══════════════════════════════════════════════════════════════════════════

-- ── 1. Panel maestro: una fila por usuario, TODO junto ──────────────────────
create or replace view analytics.panel_usuarios as
select
  u.email,
  c.user_id,
  c.total_consultas,
  c.consultas_rapidas,
  c.mejoras_rapidas,
  c.revisiones_secciones,
  c.revisiones_completas,
  c.chats_usados,
  coalesce(t.num_sesiones, 0)              as num_sesiones,
  coalesce(t.minutos_totales, 0)           as minutos_totales,
  coalesce(t.minutos_promedio_sesion, 0)   as minutos_promedio_sesion,
  c.primera_actividad,
  c.ultima_actividad
from analytics.consultas_por_usuario c
left join analytics.tiempo_uso_por_usuario t on t.user_id = c.user_id
left join auth.users u                       on u.id      = c.user_id
order by c.total_consultas desc;

-- ── 2. Consultas por chat, con el email del dueño ───────────────────────────
create or replace view analytics.panel_chats as
select
  u.email,
  ch.conversacion_id,
  conv.titulo                              as titulo_chat,
  ch.total_consultas,
  ch.consultas_rapidas,
  ch.mejoras_rapidas,
  ch.revisiones_secciones,
  ch.revisiones_completas,
  ch.inicio,
  ch.fin,
  round(extract(epoch from (ch.fin - ch.inicio))/60.0, 1) as minutos_span
from analytics.consultas_por_chat ch
left join auth.users u            on u.id  = ch.user_id
left join public.conversaciones conv on conv.id = ch.conversacion_id
order by ch.total_consultas desc;

-- ── 3. Sesiones de uso, con email (cada periodo de actividad continuo) ───────
create or replace view analytics.panel_sesiones as
select
  u.email,
  s.user_id,
  s.sesion_seq,
  s.inicio,
  s.fin,
  s.consultas_en_sesion,
  round(s.duracion_segundos/60.0, 1) as duracion_minutos
from analytics.sesiones s
left join auth.users u on u.id = s.user_id
order by s.inicio desc;

-- ── 4. Línea de uso por día (para gráfico de actividad en el tiempo) ─────────
create or replace view analytics.panel_uso_diario as
select
  u.email,
  date_trunc('day', e.created_at)::date as dia,
  count(*)                              as consultas,
  count(distinct e.conversacion_id)     as chats_activos
from analytics.eventos e
left join auth.users u on u.id = e.user_id
group by u.email, date_trunc('day', e.created_at)::date
order by dia desc;
