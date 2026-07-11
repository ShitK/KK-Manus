from pathlib import Path
import unittest


class GitHubRepoInterviewMemoryMigrationTest(unittest.TestCase):
    def test_memory_migration_uses_local_users_schema(self):
        migration = Path("supabase/migrations/20260703000000_github_repo_interview_memories.sql").read_text()

        self.assertIn("user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE", migration)
        self.assertIn("ON github_repo_interview_memories (user_id, memory_type, memory_value)", migration)
        self.assertIn("ON github_repo_interview_memories (user_id, status, updated_at DESC)", migration)
        self.assertIn("ALTER TABLE github_repo_interview_memories DISABLE ROW LEVEL SECURITY", migration)
        self.assertNotIn("basejump.accounts", migration)
        self.assertNotIn("basejump.has_role_on_account", migration)
        self.assertNotIn("account_id", migration)


if __name__ == "__main__":
    unittest.main()
