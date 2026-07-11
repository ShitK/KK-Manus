BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS github_repo_interview_text_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  memory_type TEXT NOT NULL DEFAULT 'practice_experience_summary',
  memory_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding VECTOR(1024) NOT NULL,
  embedding_model TEXT NOT NULL,
  target_role TEXT,
  category TEXT,
  source_thread_id VARCHAR(128) REFERENCES public.threads(thread_id) ON DELETE SET NULL,
  source_agent_run_id TEXT,
  source_stage TEXT NOT NULL DEFAULT 'summarize',
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  privacy JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT github_repo_interview_text_memories_type_check
    CHECK (memory_type = 'practice_experience_summary'),
  CONSTRAINT github_repo_interview_text_memories_status_check
    CHECK (status IN ('active', 'deleted')),
  CONSTRAINT github_repo_interview_text_memories_length_check
    CHECK (char_length(memory_text) BETWEEN 80 AND 600)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_github_repo_interview_text_memories_active_hash
  ON github_repo_interview_text_memories (user_id, content_hash)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_github_repo_interview_text_memories_user_active
  ON github_repo_interview_text_memories (user_id, status, updated_at DESC)
  WHERE deleted_at IS NULL;

ALTER TABLE github_repo_interview_text_memories DISABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION match_github_repo_interview_text_memories(
  p_user_id UUID,
  p_query_embedding VECTOR(1024),
  p_candidate_count INTEGER,
  p_target_role TEXT DEFAULT NULL,
  p_category TEXT DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  memory_type TEXT,
  memory_text TEXT,
  target_role TEXT,
  category TEXT,
  source_thread_id VARCHAR,
  source_agent_run_id TEXT,
  source_stage TEXT,
  provenance JSONB,
  privacy JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  similarity DOUBLE PRECISION
)
LANGUAGE SQL
STABLE
AS $$
  SELECT
    memory.id,
    memory.memory_type,
    memory.memory_text,
    memory.target_role,
    memory.category,
    memory.source_thread_id,
    memory.source_agent_run_id,
    memory.source_stage,
    memory.provenance,
    memory.privacy,
    memory.created_at,
    memory.updated_at,
    1 - (memory.embedding <=> p_query_embedding) AS similarity
  FROM github_repo_interview_text_memories AS memory
  WHERE memory.user_id = p_user_id
    AND memory.status = 'active'
    AND memory.deleted_at IS NULL
    AND (p_target_role IS NULL OR memory.target_role IS NULL OR memory.target_role = p_target_role)
    AND (p_category IS NULL OR memory.category IS NULL OR memory.category = p_category)
  ORDER BY memory.embedding <=> p_query_embedding ASC,
           memory.updated_at DESC,
           memory.id ASC
  LIMIT LEAST(GREATEST(COALESCE(p_candidate_count, 1), 1), 20);
$$;

COMMENT ON TABLE github_repo_interview_text_memories IS
  'User-confirmed sanitized text memories for GitHub Repo Interview semantic retrieval.';

COMMIT;
