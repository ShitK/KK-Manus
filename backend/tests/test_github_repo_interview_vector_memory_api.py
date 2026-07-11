import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from agent.github_repo_interview_vector_memory_api import (
    ConfirmVectorMemoryRequest,
    VectorMemoryCandidateRequest,
    confirm_text_memory,
    delete_text_memory,
    list_text_memories,
)
from agent.tools.github_repo_interview_vector_memory import (
    SAFE_PRIVACY,
    VectorMemoryEmbeddingError,
    build_vector_memory_candidate,
)


SESSION = {
    "target_role": "AI Agent 工程师",
    "current_practice_category": "architecture",
    "answered_question_ids": ["Q1"],
    "next_practice_suggestion": "继续加强架构边界、故障恢复与证据引用的表达，并用具体源码符号说明设计取舍。",
}
CANDIDATE = build_vector_memory_candidate(session_memory=SESSION, source_thread_id="thread-1")


class FakeDb:
    @property
    async def client(self):
        return object()


class VectorMemoryApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_rebuilds_candidate_for_authenticated_user(self):
        request = ConfirmVectorMemoryRequest(
            candidate=VectorMemoryCandidateRequest(**CANDIDATE),
            source_thread_id="thread-1",
        )
        with (
            patch("agent.github_repo_interview_vector_memory_api.db", FakeDb()),
            patch(
                "agent.github_repo_interview_vector_memory_api.load_session_memory",
                AsyncMock(return_value=SESSION),
            ),
            patch(
                "agent.github_repo_interview_vector_memory_api.save_vector_memory",
                AsyncMock(return_value={"id": "memory-1", "text": CANDIDATE["text"], "persisted": True}),
            ) as save,
        ):
            result = await confirm_text_memory(request, user_id="user-1")

        self.assertEqual(result["id"], "memory-1")
        self.assertEqual(save.await_args.kwargs["user_id"], "user-1")
        self.assertEqual(save.await_args.kwargs["canonical_candidate"]["content_hash"], CANDIDATE["content_hash"])

    async def test_stale_candidate_returns_409_with_refreshed_candidate(self):
        request = ConfirmVectorMemoryRequest(
            candidate=VectorMemoryCandidateRequest(**CANDIDATE),
            source_thread_id="thread-1",
        )
        changed = {**SESSION, "next_practice_suggestion": "继续加强测试分层、CI 反馈速度和 AgentLoop 状态流转验证，并补充失败路径与边界条件。"}
        with (
            patch("agent.github_repo_interview_vector_memory_api.db", FakeDb()),
            patch(
                "agent.github_repo_interview_vector_memory_api.load_session_memory",
                AsyncMock(return_value=changed),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await confirm_text_memory(request, user_id="user-1")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "vector_memory_candidate_stale")
        self.assertIn("candidate", raised.exception.detail)

    async def test_embedding_failure_is_retryable_503(self):
        request = ConfirmVectorMemoryRequest(
            candidate=VectorMemoryCandidateRequest(**CANDIDATE),
            source_thread_id="thread-1",
        )
        with (
            patch("agent.github_repo_interview_vector_memory_api.db", FakeDb()),
            patch(
                "agent.github_repo_interview_vector_memory_api.load_session_memory",
                AsyncMock(return_value=SESSION),
            ),
            patch(
                "agent.github_repo_interview_vector_memory_api.save_vector_memory",
                AsyncMock(side_effect=VectorMemoryEmbeddingError("secret provider detail")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await confirm_text_memory(request, user_id="user-1")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["code"], "vector_memory_embedding_unavailable")
        self.assertTrue(raised.exception.detail["retryable"])
        self.assertNotIn("secret", str(raised.exception.detail))

    async def test_list_and_delete_forward_authenticated_user(self):
        with (
            patch("agent.github_repo_interview_vector_memory_api.db", FakeDb()),
            patch(
                "agent.github_repo_interview_vector_memory_api.list_vector_memories",
                AsyncMock(return_value=[]),
            ) as list_mock,
            patch(
                "agent.github_repo_interview_vector_memory_api.soft_delete_vector_memory",
                AsyncMock(return_value={"id": "memory-1", "status": "deleted"}),
            ) as delete_mock,
        ):
            self.assertEqual(await list_text_memories(user_id="user-1"), {"memories": []})
            await delete_text_memory("memory-1", user_id="user-1")

        self.assertEqual(list_mock.await_args.kwargs["user_id"], "user-1")
        self.assertEqual(delete_mock.await_args.kwargs["user_id"], "user-1")


if __name__ == "__main__":
    unittest.main()
