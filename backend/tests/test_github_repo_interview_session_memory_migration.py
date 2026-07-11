from pathlib import Path
import unittest


class GitHubRepoInterviewSessionMemoryMigrationTest(unittest.TestCase):
    def test_session_memory_migration_uses_thread_scoped_schema(self):
        migration = Path(
            "supabase/migrations/20260709000000_github_repo_interview_session_memories.sql"
        ).read_text()

        self.assertIn("CREATE TABLE IF NOT EXISTS github_repo_interview_session_memories", migration)
        self.assertIn("user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE", migration)
        self.assertIn("thread_id VARCHAR(128) NOT NULL REFERENCES public.threads(thread_id) ON DELETE CASCADE", migration)
        self.assertIn("memory_state JSONB NOT NULL DEFAULT '{}'::jsonb", migration)
        self.assertIn("(user_id, thread_id, workflow_name)", migration)
        self.assertIn("WHERE status = 'active'", migration)
        self.assertIn("ALTER TABLE github_repo_interview_session_memories DISABLE ROW LEVEL SECURITY", migration)
        self.assertNotIn("raw_answer", migration)
        self.assertNotIn("answer_text", migration)


if __name__ == "__main__":
    unittest.main()
