BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS github_repo_interview_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  memory_type TEXT NOT NULL,
  memory_value TEXT NOT NULL,
  label TEXT NOT NULL,
  source_stage TEXT NOT NULL,
  source_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
  provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
  privacy JSONB NOT NULL DEFAULT '{
    "includes_user_answer": false,
    "includes_follow_up_answer": false,
    "includes_repo_evidence_text": false
  }'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ NULL,
  CONSTRAINT github_repo_interview_memories_type_check CHECK (
    memory_type IN (
      'language_preference_hint',
      'feedback_preference_hint',
      'recent_practice_category',
      'practice_weakness_tag'
    )
  ),
  CONSTRAINT github_repo_interview_memories_stage_check CHECK (
    source_stage IN ('select_question', 'coach_answer', 'coach_follow_up', 'summarize')
  ),
  CONSTRAINT github_repo_interview_memories_status_check CHECK (
    status IN ('active', 'deleted')
  ),
  CONSTRAINT github_repo_interview_memories_privacy_check CHECK (
    privacy = '{
      "includes_user_answer": false,
      "includes_follow_up_answer": false,
      "includes_repo_evidence_text": false
    }'::jsonb
  ),
  CONSTRAINT github_repo_interview_memories_label_length_check CHECK (
    char_length(label) BETWEEN 1 AND 160
  ),
  CONSTRAINT github_repo_interview_memories_value_length_check CHECK (
    char_length(memory_value) BETWEEN 1 AND 80
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_github_repo_interview_memories_active_unique
  ON github_repo_interview_memories (user_id, memory_type, memory_value)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_github_repo_interview_memories_user_active
  ON github_repo_interview_memories (user_id, status, updated_at DESC)
  WHERE deleted_at IS NULL;

ALTER TABLE github_repo_interview_memories DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE github_repo_interview_memories IS
  'User-confirmed lightweight memory records for GitHub Repo Interview workflow demo. Stores sanitized preference/tag values only. Access is enforced by backend JWT user_id checks.';

COMMENT ON COLUMN github_repo_interview_memories.label IS
  'Short display label derived from an allowed memory candidate. Must not contain user answer text or repo evidence text.';

COMMIT;
