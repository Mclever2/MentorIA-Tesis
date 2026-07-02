-- ══════════════════════════════════════════════════════════════════════════
-- MentorIA — Esquema v4 (analítica de uso para la tesis)
-- Ejecutar DESPUÉS de schema.sql, schema_v2.sql y schema_v3.sql.
-- En: Supabase → SQL Editor → New query → Run.  Idempotente.
--
-- Captura cada "consulta" que hace un usuario, de qué tipo es y cuánto tardó.
-- A partir de este log se derivan: nº de consultas por usuario, consultas por
-- chat (con desglose de tipo) y el "tiempo de uso" (sesiones por huecos).
--
-- IMPORTANTE: la escritura la hace SOLO el backend con la SERVICE ROLE KEY,
-- llamando a la función public.registrar_evento (RPC). El cliente (navegador)
-- NO puede insertar eventos → los datos no se pueden falsear desde el frontend.
-- ══════════════════════════════════════════════════════════════════════════

create schema if not exists analytics;

-- ── 1. Log de eventos (una fila = una consulta) ─────────────────────────────
--   tipo: 'consulta_rapida'    → chat que responde rápido (modo conversación)
--         'mejora_rapida'      → mini-grafo de mejora/redacción (debate rápido)
--         'revision_secciones' → revisión por secciones (red de agentes)
--         'revision_completa'  → revisión completa (red de agentes)
create table if not exists analytics.eventos (
  id              bigint generated always as identity primary key,
  user_id         uuid not null,
  conversacion_id uuid,                       -- el "chat" (null si aún no hay)
  tipo            text not null,
  modo            text,                        -- modo crudo del run (completo/secciones)
  secciones       text[],                      -- qué secciones se pidieron (si aplica)
  duracion_ms     integer,                     -- runs: fin - inicio; null en consultas síncronas
  estado          text,                        -- runs: completado | cancelado | error
  payload         jsonb not null default '{}', -- extra libre (iteraciones, nº mensajes, etc.)
  created_at      timestamptz not null default now()
);

create index if not exists eventos_user_idx  on analytics.eventos (user_id, created_at);
create index if not exists eventos_conv_idx   on analytics.eventos (conversacion_id);
create index if not exists eventos_tipo_idx   on analytics.eventos (tipo);

-- ── 2. RLS: nadie lee/escribe vía API pública ───────────────────────────────
-- Sin políticas permisivas, anon/authenticated quedan bloqueados. La SERVICE
-- ROLE (backend) y una conexión Postgres directa (Looker Studio/Metabase con el
-- usuario de la BD) BYPASEAN RLS, así que sí pueden leer/escribir.
alter table analytics.eventos enable row level security;

-- ── 3. RPC de escritura (lo llama el backend con service-role) ──────────────
-- SECURITY DEFINER: corre con privilegios del dueño (postgres) e inserta en el
-- schema analytics sin necesidad de exponerlo en la API REST.
create or replace function public.registrar_evento(
  p_user_id         uuid,
  p_tipo            text,
  p_conversacion_id uuid    default null,
  p_modo            text    default null,
  p_secciones       text[]  default null,
  p_duracion_ms     integer default null,
  p_estado          text    default null,
  p_payload         jsonb   default '{}'
) returns bigint
language plpgsql
security definer
set search_path = analytics, public
as $$
declare
  nuevo_id bigint;
begin
  insert into analytics.eventos
    (user_id, conversacion_id, tipo, modo, secciones, duracion_ms, estado, payload)
  values
    (p_user_id, p_conversacion_id, p_tipo, p_modo, p_secciones,
     p_duracion_ms, p_estado, coalesce(p_payload, '{}'::jsonb))
  returning id into nuevo_id;
  return nuevo_id;
end;
$$;

-- Solo el backend (service_role) puede ejecutar el RPC. El navegador, no.
revoke all on function public.registrar_evento(uuid, text, uuid, text, text[], integer, text, jsonb) from public, anon, authenticated;
grant execute on function public.registrar_evento(uuid, text, uuid, text, text[], integer, text, jsonb) to service_role;

-- ══════════════════════════════════════════════════════════════════════════
-- VISTAS DE ANÁLISIS  (consúmelas desde Looker Studio / Metabase / SQL Editor)
-- ══════════════════════════════════════════════════════════════════════════

-- ── 4a. Consultas por usuario (con desglose por tipo) ───────────────────────
create or replace view analytics.consultas_por_usuario as
select
  user_id,
  count(*)                                              as total_consultas,
  count(*) filter (where tipo = 'consulta_rapida')     as consultas_rapidas,
  count(*) filter (where tipo = 'mejora_rapida')        as mejoras_rapidas,
  count(*) filter (where tipo = 'revision_secciones')  as revisiones_secciones,
  count(*) filter (where tipo = 'revision_completa')   as revisiones_completas,
  count(distinct conversacion_id)                       as chats_usados,
  min(created_at)                                       as primera_actividad,
  max(created_at)                                       as ultima_actividad
from analytics.eventos
group by user_id;

-- ── 4b. Consultas por chat (cuántas preguntas y de qué tipo en cada chat) ───
create or replace view analytics.consultas_por_chat as
select
  conversacion_id,
  user_id,
  count(*)                                              as total_consultas,
  count(*) filter (where tipo = 'consulta_rapida')     as consultas_rapidas,
  count(*) filter (where tipo = 'mejora_rapida')        as mejoras_rapidas,
  count(*) filter (where tipo = 'revision_secciones')  as revisiones_secciones,
  count(*) filter (where tipo = 'revision_completa')   as revisiones_completas,
  min(created_at)                                       as inicio,
  max(created_at)                                       as fin
from analytics.eventos
where conversacion_id is not null
group by conversacion_id, user_id;

-- ── 4c. Sesiones de uso = "tiempo de inicio a fin" ──────────────────────────
-- Sesionización por huecos: dos consultas del mismo usuario separadas por más
-- de 30 min pertenecen a sesiones distintas (técnica estándar tipo GA). La
-- duración es (fin - inicio) de cada sesión. No depende de un evento de "fin"
-- (que casi nunca llega porque la gente cierra la pestaña).
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
  count(*)                                              as consultas_en_sesion,
  extract(epoch from (max(created_at) - min(created_at))) as duracion_segundos
from numeradas
group by user_id, sesion_seq;

-- ── 4d. Resumen de tiempo de uso por usuario ────────────────────────────────
create or replace view analytics.tiempo_uso_por_usuario as
select
  user_id,
  count(*)                          as num_sesiones,
  sum(duracion_segundos)            as segundos_totales,
  round(sum(duracion_segundos)/60.0, 1) as minutos_totales,
  round(avg(duracion_segundos)/60.0, 1) as minutos_promedio_sesion,
  sum(consultas_en_sesion)          as consultas_totales
from analytics.sesiones
group by user_id;
