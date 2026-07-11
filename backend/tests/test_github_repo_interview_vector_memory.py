import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agent.tools.github_repo_interview_vector_memory import (
    VECTOR_DIMENSIONS,
    LiteLLMVectorMemoryEmbeddingProvider,
    VectorMemoryConfig,
    VectorMemoryDimensionError,
    build_vector_memory_candidate,
    retrieve_vector_memories,
)


class VectorMemoryCandidateTest(unittest.TestCase):
    def test_candidate_is_deterministic_and_drops_raw_fields(self):
        state = {
            "target_role": "AI Agent 工程师",
            "current_practice_category": "architecture",
            "answered_question_ids": ["Q1", "Q2"],
            "next_practice_suggestion": "继续加强架构边界、故障恢复与证据引用的表达，并用具体源码符号说明设计取舍。",
            "user_answer": "raw answer must not appear",
        }
        first = build_vector_memory_candidate(
            session_memory=state,
            source_thread_id="thread-1",
            source_agent_run_id="run-1",
        )
        second = build_vector_memory_candidate(
            session_memory=state,
            source_thread_id="thread-1",
            source_agent_run_id="run-1",
        )

        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(len(first["content_hash"]), 64)
        self.assertEqual(first["id"], f'text-memory-candidate:{first["content_hash"][:16]}')
        self.assertNotIn("raw answer", str(first))
        self.assertFalse(first["persisted"])
        self.assertTrue(first["requires_user_confirmation"])

    def test_candidate_requires_enough_safe_text(self):
        candidate = build_vector_memory_candidate(
            session_memory={"target_role": "后端", "current_practice_category": "架构"},
            source_thread_id="thread-1",
        )
        self.assertEqual(candidate, {})


class VectorMemoryProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_qwen_defaults_use_calibrated_demo_threshold(self):
        config = VectorMemoryConfig()
        self.assertEqual(config.model, "openai/text-embedding-v4")
        self.assertEqual(config.match_threshold, 0.65)

    async def test_embedding_accepts_mapping_response(self):
        self.assertEqual(VECTOR_DIMENSIONS, 1024)
        vector = [0.1] * VECTOR_DIMENSIONS
        embedding_call = AsyncMock(return_value={"data": [{"embedding": vector}]})
        provider = LiteLLMVectorMemoryEmbeddingProvider(
            VectorMemoryConfig(),
            embedding_call=embedding_call,
        )
        self.assertEqual(await provider.embed_text("query"), vector)
        self.assertEqual(embedding_call.await_args.kwargs["model"], "openai/text-embedding-v4")
        self.assertEqual(embedding_call.await_args.kwargs["encoding_format"], "float")
        self.assertNotIn("dimensions", embedding_call.await_args.kwargs)
        self.assertEqual(
            embedding_call.await_args.kwargs["api_base"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    async def test_embedding_rejects_wrong_dimension(self):
        provider = LiteLLMVectorMemoryEmbeddingProvider(
            VectorMemoryConfig(),
            embedding_call=AsyncMock(return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])),
        )
        with self.assertRaises(VectorMemoryDimensionError):
            await provider.embed_text("query")


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class FakePool:
    def __init__(self, rows):
        self.connection = SimpleNamespace(fetch=AsyncMock(return_value=rows))

    def acquire(self):
        return FakeAcquire(self.connection)


class VectorMemoryRetrievalTest(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_retrieval_skips_provider(self):
        provider = SimpleNamespace(embed_text=AsyncMock())
        result = await retrieve_vector_memories(
            client=SimpleNamespace(pool=FakePool([])),
            provider=provider,
            config=VectorMemoryConfig(enabled=False),
            user_id="user-1",
            query_text="AgentLoop failure recovery",
        )
        self.assertEqual(result["status"], "disabled")
        provider.embed_text.assert_not_awaited()

    async def test_retrieval_reports_precise_filter_counts(self):
        rows = [
            {"id": "m1", "memory_text": "one", "similarity": 0.91},
            {"id": "m2", "memory_text": "two", "similarity": 0.82},
            {"id": "m3", "memory_text": "three", "similarity": 0.79},
            {"id": "m4", "memory_text": "four", "similarity": 0.50},
        ]
        provider = SimpleNamespace(embed_text=AsyncMock(return_value=[0.1] * VECTOR_DIMENSIONS))
        result = await retrieve_vector_memories(
            client=SimpleNamespace(pool=FakePool(rows)),
            provider=provider,
            config=VectorMemoryConfig(enabled=True, match_threshold=0.7, match_count=2),
            user_id="user-1",
            query_text="AgentLoop failure recovery",
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual([item["id"] for item in result["context"]], ["m1", "m2"])
        self.assertEqual(result["diagnostics"]["candidate_count"], 4)
        self.assertEqual(result["diagnostics"]["matched_count"], 3)
        self.assertEqual(result["diagnostics"]["applied_count"], 2)
        self.assertEqual(result["diagnostics"]["filtered_by_threshold"], 1)
        self.assertEqual(result["diagnostics"]["filtered_by_topk"], 1)
        self.assertEqual(result["diagnostics"]["filtered_count"], 2)
if __name__ == "__main__":
    unittest.main()
