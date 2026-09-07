-- ══════════════════════════════════════════════════════════════════════════
-- MentorIA — Esquema v7 (alcance de evaluación por chat)
-- Ejecutar DESPUÉS de schema_v6.sql.  En: Supabase → SQL Editor → Run. Idempotente.
--
-- Un proyecto de tesis se escribe por partes durante meses. Hasta ahora el
-- sistema calificaba siempre los 33 ítems de la rúbrica, así que a quien solo
-- tenía título e hipótesis le ponía 0 en metodología, presupuesto y referencias
-- y le hundía una nota que no reflejaba su avance real.
--
-- El estudiante declara ahora QUÉ PARTES quiere que se evalúen. Esa decisión es
-- suya y debe sobrevivir al cierre del chat: sin persistirla, al reabrir la
-- conversación el sistema volvía a proponer un alcance automático y podía
-- calificar de más.
--
-- Forma del JSON:
--   {"modo": "auto" | "declarado",
--    "grupos": ["TÍTULO", "HIPÓTESIS Y VARIABLES"],
--    "items":  [1, 2, 3, 18, 19, 20, 21]}
-- ══════════════════════════════════════════════════════════════════════════

alter table public.conversaciones
  add column if not exists doc_alcance jsonb not null default '{}'::jsonb;

comment on column public.conversaciones.doc_alcance is
  'Alcance de evaluación declarado por el estudiante para el proyecto de este chat. '
  'Los ítems fuera de este alcance no se califican y no restan.';
