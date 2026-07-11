import unittest

from agent.tools.github_repo_interview_session_memory import (
    build_session_memory_patch,
    load_session_memory,
    merge_session_memory,
    row_to_session_memory,
    sanitize_session_memory_state,
    upsert_session_memory,
)


class FakeResult:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, table):
        self.table = table
        self._single = False

    def select(self, *args):
        return self

    def eq(self, key, value):
        self.table.filters[key] = value
        return self

    def maybe_single(self):
        self._single = True
        return self

    def update(self, values):
        self.table.update_values = values
        return self

    def insert(self, values):
        self.table.insert_values = values
        return self

    async def execute(self):
        if self.table.update_values is not None:
            return FakeResult({**self.table.row, **self.table.update_values})
        if self.table.insert_values is not None:
            return FakeResult({**self.table.insert_values})
        return FakeResult(self.table.row)


class FakeTable:
    def __init__(self, row=None):
        self.row = row
        self.filters = {}
        self.update_values = None
        self.insert_values = None

    def select(self, *args):
        return FakeQuery(self).select(*args)

    def update(self, values):
        return FakeQuery(self).update(values)

    def insert(self, values):
        return FakeQuery(self).insert(values)


class FakeClient:
    def __init__(self, row=None):
        self.fake_table = FakeTable(row)

    def table(self, name):
        self.table_name = name
        return self.fake_table


class GitHubRepoInterviewSessionMemoryHelperTest(unittest.TestCase):
    def test_build_patch_extracts_minimal_practice_state(self):
        patch = build_session_memory_patch(
            input_data={"target_role": "AI Agent 工程师", "stage": "summarize"},
            workflow_data={
                "selected_question": {"id": "Q1", "category": "architecture"},
                "session_summary": {
                    "missed_evidence": ["manifest:pyproject.toml"],
                    "next_practice_suggestion": "继续练习证据引用。",
                },
            },
            existing_memory={},
        )

        self.assertEqual(patch["target_role"], "AI Agent 工程师")
        self.assertEqual(patch["target_role_source"], "user_selected")
        self.assertEqual(patch["answered_question_ids"], ["Q1"])
        self.assertEqual(patch["last_question_id"], "Q1")
        self.assertEqual(patch["current_practice_category"], "architecture")
        self.assertEqual(patch["missed_evidence_ids"], ["manifest:pyproject.toml"])
        self.assertEqual(patch["next_practice_suggestion"], "继续练习证据引用。")

    def test_merge_dedupes_questions_and_evidence(self):
        merged = merge_session_memory(
            {"answered_question_ids": ["Q1"], "missed_evidence_ids": ["manifest:pyproject.toml"]},
            {
                "answered_question_ids": ["Q1", "Q2"],
                "missed_evidence_ids": ["manifest:pyproject.toml", "src:src/index.ts#snippet-1"],
            },
        )

        self.assertEqual(merged["answered_question_ids"], ["Q1", "Q2"])
        self.assertEqual(merged["missed_evidence_ids"], ["manifest:pyproject.toml", "src:src/index.ts#snippet-1"])

    def test_merge_preserves_scalar_fields_not_in_patch(self):
        merged = merge_session_memory(
            {"target_role": "AI Agent 工程师", "answered_question_ids": ["Q1"]},
            {"answered_question_ids": ["Q1", "Q2"], "summary_completed": True},
        )

        self.assertEqual(merged["target_role"], "AI Agent 工程师")
        self.assertEqual(merged["answered_question_ids"], ["Q1", "Q2"])
        self.assertTrue(merged["summary_completed"])

    def test_sanitize_drops_unknown_and_raw_text_fields(self):
        state = sanitize_session_memory_state(
            {
                "target_role": "后端工程师",
                "user_answer": "RAW ANSWER SHOULD BE DROPPED",
                "follow_up_answer": "RAW FOLLOW UP SHOULD BE DROPPED",
                "next_practice_suggestion": "继续练习。",
                "unsafe_url": "https://example.com/private",
            }
        )

        text = str(state)
        self.assertEqual(state["target_role"], "后端工程师")
        self.assertIn("继续练习", state["next_practice_suggestion"])
        self.assertNotIn("RAW ANSWER", text)
        self.assertNotIn("RAW FOLLOW UP", text)
        self.assertNotIn("https://", text)

    def test_sanitize_keeps_legitimate_text_that_mentions_answer_field_names(self):
        state = sanitize_session_memory_state(
            {
                "target_role": "raw_answer processing expert",
                "next_practice_suggestion": "继续说明 user_answer 字段为什么不应该持久化。",
            }
        )

        self.assertEqual(state["target_role"], "raw_answer processing expert")
        self.assertIn("user_answer", state["next_practice_suggestion"])

    def test_sanitize_drops_secret_and_traceback_markers_case_insensitively(self):
        state = sanitize_session_memory_state(
            {
                "target_role": "Api_Key handler",
                "next_practice_suggestion": "避免把 TRACEBACK 写入会话记忆。",
            }
        )

        self.assertNotIn("target_role", state)
        self.assertNotIn("next_practice_suggestion", state)

    def test_target_role_falls_back_to_existing_memory(self):
        patch = build_session_memory_patch(
            input_data={},
            workflow_data={"selected_question": {"id": "Q2"}},
            existing_memory={"target_role": "AI Agent 工程师"},
        )

        self.assertEqual(patch["target_role"], "AI Agent 工程师")
        self.assertEqual(patch["target_role_source"], "carried_from_session")

    def test_build_patch_handles_missing_session_summary(self):
        patch = build_session_memory_patch(
            input_data={},
            workflow_data={"selected_question": {"id": "Q3", "category": "testing and automation"}},
            existing_memory={},
        )

        self.assertEqual(patch["answered_question_ids"], ["Q3"])
        self.assertEqual(patch["last_question_id"], "Q3")
        self.assertEqual(patch["current_practice_category"], "testing and automation")

    def test_row_to_session_memory_decodes_memory_state(self):
        memory = row_to_session_memory(
            {
                "thread_id": "thread-1",
                "memory_state": '{"target_role":"AI Agent 工程师","answered_question_ids":["Q1"]}',
                "updated_from_stage": "summarize",
            }
        )

        self.assertEqual(memory["thread_id"], "thread-1")
        self.assertEqual(memory["target_role"], "AI Agent 工程师")
        self.assertEqual(memory["answered_question_ids"], ["Q1"])
        self.assertEqual(memory["updated_from_stage"], "summarize")


class GitHubRepoInterviewSessionMemoryDbTest(unittest.IsolatedAsyncioTestCase):
    async def test_load_session_memory_returns_empty_state_when_no_row(self):
        memory = await load_session_memory(FakeClient(row=None), "user-1", "thread-1")

        self.assertEqual(memory, {})

    async def test_upsert_session_memory_updates_existing_active_row(self):
        client = FakeClient(
            row={
                "memory_state": {"target_role": "AI Agent 工程师", "answered_question_ids": ["Q1"]},
                "thread_id": "thread-1",
            }
        )

        result = await upsert_session_memory(
            client,
            "user-1",
            "thread-1",
            {"answered_question_ids": ["Q2"], "summary_completed": True},
            source_agent_run_id="run-1",
            updated_from_stage="summarize",
        )

        self.assertEqual(result["target_role"], "AI Agent 工程师")
        self.assertEqual(result["answered_question_ids"], ["Q1", "Q2"])
        self.assertTrue(result["summary_completed"])
        self.assertEqual(client.fake_table.update_values["source_agent_run_id"], "run-1")
        self.assertEqual(client.fake_table.update_values["updated_from_stage"], "summarize")


if __name__ == "__main__":
    unittest.main()
