import unittest
from datetime import datetime

from agent.tools.github_repo_interview_memory import (
    list_active_memories,
    row_to_memory,
    save_memory_candidate,
    sanitize_memory_candidate,
    select_workflow_memory_context,
    soft_delete_memory,
)


VALID_CANDIDATE = {
    "id": "practice_weakness_tag:missing_evidence",
    "type": "practice_weakness_tag",
    "value": "missing_evidence",
    "label": "候选练习弱项标签：missing_evidence。",
    "source_stage": "summarize",
    "source_fields": ["answer_feedback.evidence_missed", "session_summary.missed_evidence"],
    "requires_user_confirmation": True,
    "status": "candidate_only",
    "persisted": False,
    "privacy": {
        "includes_user_answer": False,
        "includes_follow_up_answer": False,
        "includes_repo_evidence_text": False,
    },
}


class GitHubRepoInterviewMemorySanitizerTest(unittest.TestCase):
    def test_sanitizes_allowed_candidate(self):
        memory = sanitize_memory_candidate(VALID_CANDIDATE)

        self.assertEqual(memory["memory_type"], "practice_weakness_tag")
        self.assertEqual(memory["memory_value"], "missing_evidence")
        self.assertEqual(memory["label"], "候选练习弱项标签：missing_evidence。")
        self.assertEqual(memory["source_stage"], "summarize")
        self.assertEqual(
            memory["source_fields"],
            ["answer_feedback.evidence_missed", "session_summary.missed_evidence"],
        )
        self.assertEqual(memory["provenance"]["candidate_id"], "practice_weakness_tag:missing_evidence")
        self.assertEqual(
            memory["privacy"],
            {
                "includes_user_answer": False,
                "includes_follow_up_answer": False,
                "includes_repo_evidence_text": False,
            },
        )

    def test_rejects_user_answer_text_and_urls(self):
        for bad_text in [
            "user_answer: 我原文回答",
            "follow_up_answer: 原文",
            "https://github.com/example/repo",
            "README 原文内容",
            "evidence_details snippet",
        ]:
            candidate = {**VALID_CANDIDATE, "source_stage": bad_text}
            with self.assertRaises(ValueError):
                sanitize_memory_candidate(candidate)

    def test_ignores_client_label_and_uses_server_label(self):
        candidate = {**VALID_CANDIDATE, "label": "HTTPS://example.com ReadMe 用户回答原文"}
        memory = sanitize_memory_candidate(candidate)

        self.assertEqual(memory["label"], "候选练习弱项标签：missing_evidence。")
        self.assertNotIn("HTTPS", memory["label"])
        self.assertNotIn("ReadMe", memory["label"])

    def test_rejects_forbidden_text_before_length_truncation(self):
        padding = "x" * 170
        candidate = {**VALID_CANDIDATE, "source_stage": f"{padding}USER_ANSWER 原文"}

        with self.assertRaises(ValueError):
            sanitize_memory_candidate(candidate)

    def test_rejects_unsafe_source_fields(self):
        candidate = {**VALID_CANDIDATE, "source_fields": ["user_answer", "README"]}

        with self.assertRaises(ValueError):
            sanitize_memory_candidate(candidate)

    def test_candidate_id_is_derived_from_sanitized_type_and_value(self):
        candidate = {**VALID_CANDIDATE, "id": "https://github.com/example/repo/raw"}
        memory = sanitize_memory_candidate(candidate)

        self.assertEqual(
            memory["provenance"]["candidate_id"],
            "practice_weakness_tag:missing_evidence",
        )

    def test_rejects_unconfirmed_or_already_persisted_candidate(self):
        with self.assertRaises(ValueError):
            sanitize_memory_candidate({**VALID_CANDIDATE, "requires_user_confirmation": False})
        with self.assertRaises(ValueError):
            sanitize_memory_candidate({**VALID_CANDIDATE, "persisted": True})
        with self.assertRaises(ValueError):
            sanitize_memory_candidate({**VALID_CANDIDATE, "status": "active"})

    def test_rejects_value_outside_allowlist(self):
        with self.assertRaises(ValueError):
            sanitize_memory_candidate({**VALID_CANDIDATE, "value": "raw free form text"})

    def test_row_to_memory_decodes_json_fields_from_database(self):
        memory = row_to_memory(
            {
                "id": "m1",
                "memory_type": "language_preference_hint",
                "memory_value": "zh",
                "label": "本次请求的候选语言偏好。",
                "source_stage": "coach_answer",
                "source_fields": '["input.language"]',
                "privacy": (
                    '{"includes_user_answer": false, '
                    '"includes_follow_up_answer": false, '
                    '"includes_repo_evidence_text": false}'
                ),
                "status": "active",
                "deleted_at": None,
            }
        )

        self.assertEqual(memory["source_fields"], ["input.language"])
        self.assertEqual(memory["privacy"]["includes_user_answer"], False)
        self.assertTrue(memory["persisted"])

    def test_select_workflow_memory_context_is_small_active_and_redacted(self):
        memories = [
            {
                "id": "m1",
                "type": "language_preference_hint",
                "value": "zh",
                "label": "本次请求的候选语言偏好。",
                "source_stage": "coach_answer",
                "source_fields": ["input.language"],
                "persisted": True,
                "status": "active",
            },
            {
                "id": "m2",
                "type": "practice_weakness_tag",
                "value": "missing_evidence",
                "label": "候选练习弱项标签：missing_evidence。",
                "source_stage": "summarize",
                "source_fields": ["session_summary.missed_evidence"],
                "persisted": True,
                "status": "active",
            },
            {
                "id": "candidate-only",
                "type": "feedback_preference_hint",
                "value": "concise",
                "label": "本次请求的候选反馈风格偏好。",
                "source_stage": "coach_answer",
                "source_fields": ["input.coach_style"],
                "status": "candidate_only",
                "persisted": False,
            },
            {
                "id": "deleted",
                "type": "feedback_preference_hint",
                "value": "balanced",
                "label": "本次请求的候选反馈风格偏好。",
                "source_stage": "coach_answer",
                "source_fields": ["input.coach_style"],
                "status": "deleted",
                "persisted": True,
            },
            {
                "id": "polluted",
                "type": "practice_weakness_tag",
                "value": "missing_evidence",
                "label": "user_answer 原文",
                "source_stage": "summarize",
                "source_fields": ["user_answer"],
                "persisted": True,
                "status": "active",
            },
        ]

        context = select_workflow_memory_context(memories, limit=3)

        self.assertEqual(len(context), 2)
        self.assertEqual(context[0]["type"], "language_preference_hint")
        self.assertTrue(all(item["persisted"] is True for item in context))
        self.assertNotIn("user_answer", str(context))
        self.assertNotIn("snippet", str(context))

class FakeQueryResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, data_store, table_name):
        self.data_store = data_store
        self.table_name = table_name
        self.filters = []
        self.limit_count = None
        self.maybe_single_requested = False
        self.order_by = None

    def select(self, fields="*"):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def is_(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, column, desc=False):
        self.order_by = (column, desc)
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def maybe_single(self):
        self.maybe_single_requested = True
        return self

    def _matches(self, row):
        return all(row.get(column) == value for column, value in self.filters)

    async def execute(self):
        rows = [row for row in self.data_store if self._matches(row)]
        if self.order_by:
            column, desc = self.order_by
            rows = sorted(rows, key=lambda row: row.get(column) or "", reverse=desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        if self.maybe_single_requested:
            return FakeQueryResult(rows[0] if rows else None)
        return FakeQueryResult(rows)

    async def insert(self, data):
        row = {"id": f"m{len(self.data_store) + 1}", "deleted_at": None, **data}
        self.data_store.append(row)
        return FakeQueryResult([row])

    async def update(self, data):
        rows = [row for row in self.data_store if self._matches(row)]
        for row in rows:
            row.update(data)
        if self.maybe_single_requested:
            return FakeQueryResult(rows[0] if rows else None)
        return FakeQueryResult(rows)


class FakeClient:
    def __init__(self, rows=None):
        self.rows = rows or []

    def table(self, table_name):
        return FakeTable(self.rows, table_name)


class GitHubRepoInterviewMemoryRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_save_memory_candidate_serializes_json_fields(self):
        client = FakeClient()

        memory = await save_memory_candidate(client, "user-1", VALID_CANDIDATE)

        self.assertEqual(memory["id"], "m1")
        row = client.rows[0]
        self.assertEqual(row["user_id"], "user-1")
        self.assertIsInstance(row["source_fields"], str)
        self.assertIsInstance(row["provenance"], str)
        self.assertIsInstance(row["privacy"], str)
        self.assertEqual(memory["source_fields"], ["answer_feedback.evidence_missed", "session_summary.missed_evidence"])

    async def test_save_memory_candidate_reactivates_deleted_row_for_same_account(self):
        client = FakeClient(
            [
                {
                    "id": "m1",
                    "user_id": "user-1",
                    "memory_type": "practice_weakness_tag",
                    "memory_value": "missing_evidence",
                    "label": "旧标签",
                    "source_stage": "summarize",
                    "source_fields": '["session_summary.missed_evidence"]',
                    "provenance": "{}",
                    "privacy": (
                        '{"includes_user_answer": false, '
                        '"includes_follow_up_answer": false, '
                        '"includes_repo_evidence_text": false}'
                    ),
                    "status": "deleted",
                    "deleted_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T00:00:00+00:00",
                }
            ]
        )

        memory = await save_memory_candidate(client, "user-1", VALID_CANDIDATE)

        self.assertEqual(memory["id"], "m1")
        self.assertTrue(memory["persisted"])
        self.assertEqual(client.rows[0]["status"], "active")
        self.assertIsNone(client.rows[0]["deleted_at"])
        self.assertIsInstance(client.rows[0]["updated_at"], datetime)

    async def test_list_active_memories_filters_account_and_deleted_rows(self):
        safe_privacy = (
            '{"includes_user_answer": false, '
            '"includes_follow_up_answer": false, '
            '"includes_repo_evidence_text": false}'
        )
        client = FakeClient(
            [
                {
                    "id": "m1",
                    "user_id": "user-1",
                    "memory_type": "language_preference_hint",
                    "memory_value": "zh",
                    "label": "本次请求的候选语言偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": '["input.language"]',
                    "privacy": safe_privacy,
                    "status": "active",
                    "deleted_at": None,
                    "updated_at": "2026-07-03T10:00:00+00:00",
                },
                {
                    "id": "m2",
                    "user_id": "user-2",
                    "memory_type": "language_preference_hint",
                    "memory_value": "en",
                    "label": "本次请求的候选语言偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": '["input.language"]',
                    "privacy": safe_privacy,
                    "status": "active",
                    "deleted_at": None,
                    "updated_at": "2026-07-03T11:00:00+00:00",
                },
                {
                    "id": "m3",
                    "user_id": "user-1",
                    "memory_type": "feedback_preference_hint",
                    "memory_value": "direct",
                    "label": "本次请求的候选反馈风格偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": '["input.coach_style"]',
                    "privacy": safe_privacy,
                    "status": "deleted",
                    "deleted_at": "2026-07-03T00:00:00+00:00",
                    "updated_at": "2026-07-03T12:00:00+00:00",
                },
            ]
        )

        memories = await list_active_memories(client, "user-1")

        self.assertEqual([memory["id"] for memory in memories], ["m1"])

    async def test_soft_delete_memory_filters_by_account(self):
        client = FakeClient(
            [
                {"id": "m1", "user_id": "user-1", "status": "active", "deleted_at": None},
                {"id": "m2", "user_id": "user-2", "status": "active", "deleted_at": None},
            ]
        )

        deleted = await soft_delete_memory(client, "user-1", "m1")

        self.assertEqual(deleted["id"], "m1")
        self.assertFalse(deleted["persisted"])
        self.assertEqual(client.rows[0]["status"], "deleted")
        self.assertIsInstance(client.rows[0]["deleted_at"], datetime)
        self.assertIsInstance(client.rows[0]["updated_at"], datetime)
        self.assertEqual(client.rows[1]["status"], "active")


if __name__ == "__main__":
    unittest.main()
