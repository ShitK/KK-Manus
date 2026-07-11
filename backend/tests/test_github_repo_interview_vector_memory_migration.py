from pathlib import Path
import unittest


class VectorMemoryMigrationTest(unittest.TestCase):
    def test_migration_defines_user_scoped_exact_vector_retrieval(self):
        sql = Path(
            "supabase/migrations/20260710000000_github_repo_interview_text_memories.sql"
        ).read_text()

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS github_repo_interview_text_memories", sql)
        self.assertIn("embedding VECTOR(1024) NOT NULL", sql)
        self.assertIn("user_id, content_hash", sql)
        self.assertIn("match_github_repo_interview_text_memories", sql)
        self.assertIn("1 - (memory.embedding <=> p_query_embedding)", sql)
        self.assertIn("memory.user_id = p_user_id", sql)
        self.assertIn("memory.status = 'active'", sql)
        self.assertIn("memory.deleted_at IS NULL", sql)
        self.assertIn("ORDER BY memory.embedding <=> p_query_embedding ASC", sql)
        self.assertIn("memory.updated_at DESC", sql)
        self.assertIn("memory.id ASC", sql)
        self.assertIn("DISABLE ROW LEVEL SECURITY", sql)
        self.assertNotIn("REVOKE ALL ON TABLE", sql)
        self.assertNotIn("USING hnsw", sql)
        self.assertNotIn("USING ivfflat", sql)


if __name__ == "__main__":
    unittest.main()
