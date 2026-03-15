-- Migração 001: Campos adicionais para rastreio de progresso e preview
-- Execute no Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql

ALTER TABLE extraction_jobs
  ADD COLUMN IF NOT EXISTS progress_pct      INTEGER   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS records_extracted INTEGER   DEFAULT 0,
  ADD COLUMN IF NOT EXISTS preview_rows      JSONB     DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS result_url        TEXT;

-- Habilita Realtime para que o frontend receba atualizações via websocket
-- (substitui polling a cada 3s por notificação instantânea)
ALTER PUBLICATION supabase_realtime ADD TABLE extraction_jobs;

-- Índice para buscas rápidas por usuário + status (usado em /recent-schemas e History)
CREATE INDEX IF NOT EXISTS idx_extraction_jobs_user_status
  ON extraction_jobs (user_id, status, created_at DESC);
