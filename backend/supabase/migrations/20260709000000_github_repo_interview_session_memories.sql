BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS github_repo_interview_session_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  thread_id VARCHAR(128) NOT NULL REFERENCES public.threads(thread_id) ON DELETE CASCADE,
  workflow_name TEXT NOT NULL DEFAULT 'github_repo_interview_workflow',
  memory_state JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_agent_run_id TEXT,
  updated_from_stage TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT github_repo_interview_session_memories_status_check
    CHECK (status IN ('active', 'deleted')),
  CONSTRAINT github_repo_interview_session_memories_workflow_check
    CHECK (workflow_name = 'github_repo_interview_workflow'),
  CONSTRAINT github_repo_interview_session_memories_state_object_check
    CHECK (jsonb_typeof(memory_state) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_github_repo_interview_session_memories_unique
  ON github_repo_interview_session_memories (user_id, thread_id, workflow_name)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_github_repo_interview_session_memories_user_updated
  ON github_repo_interview_session_memories (user_id, updated_at DESC)
  WHERE status = 'active';

ALTER TABLE github_repo_interview_session_memories DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE github_repo_interview_session_memories IS
  'Thread-scoped short-term memory for GitHub Repo Interview workflow. Stores sanitized structured state only.';

COMMENT ON COLUMN github_repo_interview_session_memories.memory_state IS
  'Sanitized session memory: target role, practiced question ids, evidence ids, and next practice suggestion. No raw answers.';

COMMIT;
