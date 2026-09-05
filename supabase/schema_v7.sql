-- ══════════════════════════════════════════════════════════════════════════
-- MentorIA — Esquema v7 (ficha del proyecto: memoria estructurada del chat)
-- Ejecutar DESPUÉS de schema_v6.sql.  En: Supabase → SQL Editor → Run. Idempotente.
--
-- Guarda los ~10 datos que gobiernan el proyecto (problema, cómo se mide hoy,
-- organización, artefacto, tipo, diseño, acceso a datos…) para que el panel deje
-- de preguntar lo que el estudiante YA respondió.
--
-- Vive en `conversaciones` y no en el documento a propósito: el caso que fallaba
-- era justamente el del estudiante que arranca de cero SIN PDF. Así también
-- sobrevive a los reinicios de Cloud Run, que vacían el registro en memoria.
-- ══════════════════════════════════════════════════════════════════════════

alter table public.conversaciones
  add column if not exists ficha jsonb not null default '{}'::jsonb;

comment on column public.conversaciones.ficha is
  'Ficha del proyecto: datos que el estudiante ya declaró en esta asesoría. '
  'La escribe el backend con la service role key (api/ficha.py). '
  'Semántica: el último valor gana; un campo vacío significa "aún no lo dijo".';

-- Las políticas RLS de `conversaciones` (schema.sql) ya cubren esta columna:
-- el usuario solo lee y actualiza sus propias filas. El backend escribe con la
-- service role key, que salta RLS, y filtra por id de conversación.
