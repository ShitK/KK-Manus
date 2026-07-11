import unittest
from unittest.mock import AsyncMock, patch

from agent.github_repo_interview_memory_api import (
    ConfirmMemoryRequest,
    confirm_memory,
    delete_memory,
    list_memories,
)


class FakeDB:
    @property
    async def client(self):
        return object()


VALID_CANDIDATE = {
    "id": "language_preference_hint:zh",
    "type": "language_preference_hint",
    "value": "zh",
    "label": "本次请求的候选语言偏好。",
    "source_stage": "coach_answer",
    "source_fields": ["input.language"],
    "requires_user_confirmation": True,
    "status": "candidate_only",
    "persisted": False,
    "privacy": {
        "includes_user_answer": False,
        "includes_follow_up_answer": False,
        "includes_repo_evidence_text": False,
    },
}


class GitHubRepoInterviewMemoryApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_memories_uses_authenticated_user(self):
        expected = [{"id": "m1", "type": "language_preference_hint", "value": "zh"}]
        with patch("agent.github_repo_interview_memory_api.db", FakeDB()), patch(
            "agent.github_repo_interview_memory_api.list_active_memories",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            response = await list_memories(user_id="user-1")

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.args[1], "user-1")
        self.assertEqual(response["memories"], expected)

    async def test_confirm_memory_persists_candidate_for_authenticated_user(self):
        expected = {"id": "m1", "type": "language_preference_hint", "value": "zh", "persisted": True}
        with patch("agent.github_repo_interview_memory_api.db", FakeDB()), patch(
            "agent.github_repo_interview_memory_api.save_memory_candidate",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            response = await confirm_memory(
                ConfirmMemoryRequest(candidate=VALID_CANDIDATE),
                user_id="user-1",
            )

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.args[1], "user-1")
        self.assertEqual(response, expected)

    async def test_confirm_memory_accepts_candidate_without_client_label(self):
        candidate = dict(VALID_CANDIDATE)
        candidate.pop("label")
        expected = {"id": "m1", "type": "language_preference_hint", "value": "zh", "persisted": True}
        with patch("agent.github_repo_interview_memory_api.db", FakeDB()), patch(
            "agent.github_repo_interview_memory_api.save_memory_candidate",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            response = await confirm_memory(
                ConfirmMemoryRequest(candidate=candidate),
                user_id="user-1",
            )

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.args[1], "user-1")
        self.assertNotIn("label", mocked.await_args.args[2])
        self.assertEqual(response, expected)

    async def test_delete_memory_soft_deletes_authenticated_user_memory(self):
        expected = {"id": "m1", "status": "deleted", "persisted": False}
        with patch("agent.github_repo_interview_memory_api.db", FakeDB()), patch(
            "agent.github_repo_interview_memory_api.soft_delete_memory",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            response = await delete_memory("m1", user_id="user-1")

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.args[1], "user-1")
        self.assertEqual(mocked.await_args.args[2], "m1")
        self.assertEqual(response, expected)


if __name__ == "__main__":
    unittest.main()
