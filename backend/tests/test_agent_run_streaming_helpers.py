import unittest
import json

from agent.run import (
    _assistant_content_to_text,
    _github_interview_workflow_exception_result,
    _merge_recent_messages_with_tool_history,
)


class AgentRunStreamingHelperTest(unittest.TestCase):
    def test_assistant_content_to_text_keeps_string(self):
        self.assertEqual(_assistant_content_to_text("hello"), "hello")

    def test_assistant_content_to_text_extracts_text_parts(self):
        self.assertEqual(
            _assistant_content_to_text(
                [
                    {"type": "text", "text": "hello "},
                    {"type": "output_text", "text": "world"},
                    {"type": "tool_call", "id": "ignored"},
                ]
            ),
            "hello world",
        )

    def test_assistant_content_to_text_handles_content_parts(self):
        self.assertEqual(
            _assistant_content_to_text(
                [
                    {"content": "alpha"},
                    " beta",
                    {"type": "unknown", "text": 123},
                ]
            ),
            "alpha beta",
        )

    def test_assistant_content_to_text_handles_none(self):
        self.assertEqual(_assistant_content_to_text(None), "")

    def test_assistant_content_to_text_ignores_unknown_dict(self):
        self.assertEqual(_assistant_content_to_text({"role": "assistant", "reasoning": "hidden"}), "")

    def test_assistant_content_to_text_handles_nested_content_list(self):
        self.assertEqual(
            _assistant_content_to_text({"content": [{"text": "nested"}, {"id": "ignored"}]}),
            "nested",
        )

    def test_github_interview_workflow_exception_result_is_safe_for_ui(self):
        result = _github_interview_workflow_exception_result(
            {
                "stage": "coach_answer",
                "question_id": "Q1",
                "language": "zh",
                "user_answer": "这是不应该进入结果 payload 的用户回答原文",
                "previous_workflow_state": {
                    "data": {
                        "selected_question": {
                            "id": "Q1",
                            "question": "解释架构边界。",
                        }
                    }
                },
            },
            RuntimeError("secret backend detail"),
        )

        payload = json.loads(result.output)

        self.assertFalse(result.success)
        self.assertEqual(payload["tool"], "github_repo_interview_workflow")
        self.assertEqual(payload["input"]["stage"], "coach_answer")
        self.assertEqual(payload["input"]["question_id"], "Q1")
        self.assertEqual(payload["data"]["selected_question"]["id"], "Q1")
        self.assertEqual(payload["errors"][0]["code"], "workflow_execution_exception")
        self.assertIn("回答点评暂时没有成功生成", payload["errors"][0]["message"])
        self.assertNotIn("用户回答原文", result.output)
        self.assertNotIn("secret backend detail", result.output)

    def test_merge_recent_messages_with_tool_history_appends_missing_tool_payloads(self):
        recent_messages = [
            {"message_id": "status-1", "type": "status"},
            {"message_id": "tool-1", "type": "tool"},
        ]
        tool_messages = [
            {"message_id": "tool-1", "type": "tool"},
            {
                "message_id": "prep-1",
                "type": "tool",
                "content": {"tool_name": "github_repo_interview_prep"},
            },
        ]

        merged = _merge_recent_messages_with_tool_history(recent_messages, tool_messages)

        self.assertEqual([message["message_id"] for message in merged], ["status-1", "tool-1", "prep-1"])
        self.assertEqual(merged[-1]["content"]["tool_name"], "github_repo_interview_prep")


if __name__ == "__main__":
    unittest.main()
