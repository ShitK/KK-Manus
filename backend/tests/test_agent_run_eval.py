import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from agent import api as agent_api
from agent.agent_run_eval import build_agent_run_eval_report, list_agent_eval_runs


class FakeQuery:
    def __init__(self, table_name, data_by_table):
        self.table_name = table_name
        self.data_by_table = data_by_table
        self.filters = []
        self.in_filters = []
        self.limit_value = None

    def select(self, *args):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def in_(self, column, values):
        self.in_filters.append((column, set(values)))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def execute(self):
        rows = list(self.data_by_table.get(self.table_name, []))
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return SimpleNamespace(data=rows)


class FakeClient:
    def __init__(self, data_by_table):
        self.data_by_table = data_by_table

    def table(self, table_name):
        return FakeQuery(table_name, self.data_by_table)

    def schema(self, _schema_name):
        return self


class FakeRedis:
    async def llen(self, key):
        return 1

    async def scan_iter(self, match=None, count=None):
        if match and match.endswith("run-active"):
            yield "active_run:instance-1:run-active"


class FakeRedisFailing:
    async def llen(self, key):
        raise RuntimeError("redis unavailable")

    async def scan_iter(self, match=None, count=None):
        raise RuntimeError("redis unavailable")


def metric_by_id(report, metric_id):
    return next(metric for metric in report["metrics"] if metric["id"] == metric_id)


def base_data(
    *,
    run_status="completed",
    run_id="run-123",
    thread_id="thread-123",
    error=None,
    updated_at="2026-07-09T10:00:00+00:00",
    completed_at="2026-07-09T10:00:30+00:00",
    messages=None,
    events=None,
):
    return {
        "agent_runs": [
            {
                "id": 1,
                "agent_run_id": run_id,
                "thread_id": thread_id,
                "agent_id": "agent-123",
                "agent_version_id": None,
                "status": run_status,
                "started_at": "2026-07-09T09:59:00+00:00",
                "updated_at": updated_at,
                "completed_at": completed_at,
                "created_at": "2026-07-09T09:59:00+00:00",
                "error": error,
            }
        ],
        "threads": [
            {
                "thread_id": thread_id,
                "project_id": "project-123",
                "account_id": "user-123",
                "name": "Demo Thread",
                "updated_at": "2026-07-09T10:00:00+00:00",
            }
        ],
        "messages": messages
        if messages is not None
        else [
            {
                "message_id": "message-1",
                "thread_id": thread_id,
                "type": "assistant",
                "content": "本轮已经完成，我基于工具结果给出总结。",
                "metadata": {},
                "created_at": "2026-07-09T10:00:20+00:00",
            }
        ],
        "events": events if events is not None else [],
    }


class AgentRunEvalTest(unittest.IsolatedAsyncioTestCase):
    async def test_lists_recent_user_runs_with_active_status_first(self):
        client = FakeClient(
            {
                "threads": [
                    {"thread_id": "thread-active", "account_id": "user-123", "name": "Active"},
                    {"thread_id": "thread-done", "account_id": "user-123", "name": "Done"},
                ],
                "agent_runs": [
                    {
                        "id": 2,
                        "agent_run_id": "run-done",
                        "thread_id": "thread-done",
                        "status": "completed",
                        "started_at": "2026-07-09T10:00:00+00:00",
                        "updated_at": "2026-07-09T10:01:00+00:00",
                        "completed_at": "2026-07-09T10:01:00+00:00",
                        "created_at": "2026-07-09T10:00:00+00:00",
                        "error": None,
                    },
                    {
                        "id": 1,
                        "agent_run_id": "run-active",
                        "thread_id": "thread-active",
                        "status": "running",
                        "started_at": "2026-07-09T09:59:00+00:00",
                        "updated_at": "2026-07-09T09:59:30+00:00",
                        "completed_at": None,
                        "created_at": "2026-07-09T09:59:00+00:00",
                        "error": None,
                    },
                ],
                "messages": [],
                "events": [],
            }
        )

        result = await list_agent_eval_runs(client, FakeRedis(), "user-123")

        self.assertEqual(result["runs"][0]["agent_run_id"], "run-active")
        self.assertTrue(result["runs"][0]["is_active"])
        self.assertEqual(result["runs"][1]["agent_run_id"], "run-done")

    async def test_builds_healthy_report_for_completed_run_with_final_message(self):
        report = await build_agent_run_eval_report(
            FakeClient(base_data()),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(report["overall"]["status"], "healthy")
        self.assertEqual(metric_by_id(report, "run_liveness")["status"], "pass")
        self.assertEqual(metric_by_id(report, "final_output_explainability")["status"], "pass")

    async def test_report_uses_only_messages_for_selected_agent_run(self):
        target_payload = {
            "tool": "github_repo_interview_workflow",
            "data": {
                "workflow": {"stage": "coach_answer"},
                "context_snapshot": {
                    "redaction_policy": {
                        "includes_user_answer": False,
                        "includes_follow_up_answer": False,
                        "includes_repo_evidence_text": False,
                        "includes_hidden_source_content": False,
                    }
                },
                "evidence_policy": {
                    "allowed_evidence_ids": ["src:src/index.ts#snippet-1"],
                },
            },
        }
        other_run_payload = {
            "tool": "github_repo_interview_workflow",
            "data": {
                "workflow": {},
                "errors": [{"code": "tool_failed"}],
            },
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    run_id="run-target",
                    messages=[
                        {
                            "message_id": "target-workflow",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(target_payload),
                            "metadata": {"thread_run_id": "run-target"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "other-workflow",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(other_run_payload),
                            "metadata": {"thread_run_id": "run-other"},
                            "created_at": "2026-07-09T10:00:25+00:00",
                        },
                    ],
                )
            ),
            FakeRedis(),
            "run-target",
            "user-123",
        )

        self.assertEqual(metric_by_id(report, "tool_reliability")["status"], "pass")
        self.assertEqual(metric_by_id(report, "workflow_progress")["status"], "pass")
        self.assertEqual(report["observations"]["workflow_payload_count"], 1)

    async def test_warns_for_running_run_without_recent_progress(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    run_status="running",
                    updated_at="2026-07-09T10:00:00+00:00",
                    completed_at=None,
                    messages=[],
                    events=[],
                )
            ),
            FakeRedisFailing(),
            "run-123",
            "user-123",
            now=datetime(2026, 7, 9, 10, 5, tzinfo=timezone.utc),
        )

        self.assertEqual(metric_by_id(report, "run_liveness")["status"], "warn")
        self.assertEqual(report["overall"]["status"], "attention")

    async def test_detects_workflow_warning_without_returning_raw_payload(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "data": {
                "workflow": {"stage": "coach_answer"},
                "warnings": [{"code": "feedback_schema_normalized", "message": "normalized"}],
                "context_snapshot": {
                    "redaction_policy": {
                        "includes_user_answer": False,
                        "includes_follow_up_answer": False,
                        "includes_repo_evidence_text": False,
                    }
                },
                "evidence_policy": {
                    "allowed_evidence_ids": ["src:src/index.ts#snippet-1"]
                },
            },
        }
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "workflow-message",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_payload),
                            "metadata": {},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["overall"]["status"], "attention")
        self.assertEqual(metric_by_id(report, "workflow_progress")["status"], "warn")
        self.assertIn("feedback_schema_normalized", serialized)
        self.assertNotIn(json.dumps(workflow_payload, ensure_ascii=False), serialized)

    async def test_sanitizes_workflow_warning_message_before_report(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "data": {
                "workflow": {"stage": "coach_answer"},
                "warnings": [
                    {
                        "code": "feedback_schema_normalized",
                        "message": "user said: actual answer text here",
                    }
                ],
            },
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "workflow-message",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_payload),
                            "metadata": {},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("actual answer text here", serialized)
        self.assertIn("feedback_schema_normalized", serialized)

    async def test_detects_traceback_before_sanitizing_report_text(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    run_status="failed",
                    error=(
                        "Traceback (most recent call last):\n"
                        "  File /Users/kk/KK-Manus/backend/.env, line 1, in <module>\n"
                        "RuntimeError: api_key=secret-value"
                    ),
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(metric_by_id(report, "tool_reliability")["status"], "fail")
        self.assertNotIn("/Users/kk/KK-Manus/backend/.env", serialized)
        self.assertNotIn("secret-value", serialized)

    async def test_missing_workflow_dependency_fields_degrade_without_crashing(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "data": {"workflow": {"stage": "coach_answer"}},
        }
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "workflow-message",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_payload),
                            "metadata": {},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertIn(metric_by_id(report, "context_boundary")["status"], {"warn", "not_applicable"})
        self.assertEqual(metric_by_id(report, "evidence_grounding")["status"], "not_applicable")

    async def test_user_answer_failure_words_do_not_create_tool_failure_signal(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "answer-feedback",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": (
                                "你的回答提到了 LLM 调用 timeout、failure event "
                                "和 exception 降级策略，这是合理的设计点。"
                            ),
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(metric_by_id(report, "tool_reliability")["status"], "not_applicable")

    async def test_workflow_progress_accepts_input_stage(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "input": {"stage": "coach_follow_up"},
            "data": {
                "answer_feedback": {"summary": "已点评"},
            },
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "workflow-message",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_payload),
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        workflow_metric = metric_by_id(report, "workflow_progress")
        self.assertEqual(workflow_metric["status"], "pass")
        self.assertIn("coach_follow_up", json.dumps(workflow_metric, ensure_ascii=False))

    async def test_workflow_progress_uses_recent_available_stage(self):
        workflow_with_stage = {
            "tool": "github_repo_interview_workflow",
            "data": {"workflow": {"stage": "coach_answer"}},
        }
        workflow_without_stage = {
            "tool": "github_repo_interview_workflow",
            "data": {"answer_feedback": {"summary": "已点评"}},
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "workflow-with-stage",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_with_stage),
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "workflow-without-stage",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": json.dumps(workflow_without_stage),
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:25+00:00",
                        },
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        workflow_metric = metric_by_id(report, "workflow_progress")
        self.assertEqual(workflow_metric["status"], "pass")
        self.assertIn("coach_answer", json.dumps(workflow_metric, ensure_ascii=False))

    async def test_conversation_summary_payload_does_not_count_as_workflow_payload(self):
        summary_payload = {
            "tool": "github_repo_interview_conversation_summary",
            "type": "github_repo_interview_conversation_summary",
            "status": "success",
            "data": {
                "summary_kind": "conversation_summary",
                "workflow": {"current_stage": "summary_ready"},
                "conversation_summary": {"overview": "本轮总结当前对话。"},
                "session_summary": {
                    "workflow_completion": {"summary_scope": "thread_dialogue"},
                },
            },
            "warnings": [],
            "errors": [],
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "summary-tool",
                            "thread_id": "thread-123",
                            "type": "tool",
                            "content": {
                                "tool_name": "github_repo_interview_conversation_summary",
                                "result": json.dumps(summary_payload, ensure_ascii=False),
                            },
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "summary-final",
                            "thread_id": "thread-123",
                            "type": "assistant",
                            "content": "## 对话总结\n\n本轮总结当前对话。",
                            "metadata": {"thread_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:25+00:00",
                        },
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(metric_by_id(report, "workflow_progress")["status"], "not_applicable")
        self.assertEqual(metric_by_id(report, "final_output_explainability")["status"], "pass")
        self.assertEqual(report["observations"]["workflow_payload_count"], 0)

    async def test_eval_unwraps_adk_function_response_workflow_summary_payload(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "type": "github_repo_interview_workflow",
            "status": "success",
            "partial": False,
            "input": {"stage": "summarize"},
            "data": {
                "workflow": {"current_stage": "summary_ready"},
                "session_summary": {"workflow_completion": {"answer_coached": True, "follow_up_completed": False}},
                "context_snapshot": {
                    "redaction_policy": {
                        "includes_user_answer": False,
                        "includes_follow_up_answer": False,
                        "includes_repo_evidence_text": False,
                        "includes_hidden_source_content": False,
                    }
                },
            },
            "warnings": [{"code": "follow_up_not_completed", "message": "Follow-up was not completed."}],
            "errors": [],
        }
        event_content = {
            "role": "model",
            "parts": [
                {
                    "function_response": {
                        "name": "github_repo_interview_workflow",
                        "response": {"result": json.dumps(workflow_payload)},
                    }
                }
            ],
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[],
                    events=[
                        {
                            "id": "event-workflow-summary",
                            "session_id": "thread-123",
                            "author": "kkmanus",
                            "content": event_content,
                            "timestamp": "2026-07-09T10:00:20+00:00",
                        }
                    ],
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        workflow_metric = metric_by_id(report, "workflow_progress")
        self.assertEqual(report["overall"]["status"], "attention")
        self.assertEqual(workflow_metric["status"], "warn")
        self.assertIn("summary_ready", json.dumps(workflow_metric, ensure_ascii=False))
        self.assertEqual(metric_by_id(report, "context_boundary")["status"], "pass")
        self.assertEqual(report["observations"]["workflow_payload_count"], 1)

    async def test_eval_unwraps_tool_result_like_workflow_response_output(self):
        workflow_payload = {
            "tool": "github_repo_interview_workflow",
            "type": "github_repo_interview_workflow",
            "status": "success",
            "partial": False,
            "input": {"stage": "summarize"},
            "data": {
                "workflow": {"current_stage": "summary_ready"},
                "context_snapshot": {
                    "redaction_policy": {
                        "includes_user_answer": False,
                        "includes_follow_up_answer": False,
                        "includes_repo_evidence_text": False,
                        "includes_hidden_source_content": False,
                    }
                },
            },
            "warnings": [],
            "errors": [],
        }
        event_content = {
            "role": "model",
            "parts": [
                {
                    "functionResponse": {
                        "name": "github_repo_interview_workflow",
                        "response": {
                            "result": {
                                "success": True,
                                "output": json.dumps(workflow_payload),
                            }
                        },
                    }
                }
            ],
        }

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[],
                    events=[
                        {
                            "id": "event-tool-result-summary",
                            "session_id": "thread-123",
                            "author": "kkmanus",
                            "content": event_content,
                            "timestamp": "2026-07-09T10:00:20+00:00",
                        }
                    ],
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(metric_by_id(report, "workflow_progress")["status"], "pass")
        self.assertEqual(metric_by_id(report, "context_boundary")["status"], "pass")
        self.assertEqual(report["observations"]["workflow_payload_count"], 1)

    async def test_final_output_accepts_model_event_text_for_plain_chat(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[],
                    events=[
                        {
                            "id": "event-1",
                            "session_id": "thread-123",
                            "author": "kkmanus",
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "text": (
                                            "好，我直接给你一个可逐字参考的打磨版答案，"
                                            "然后拆解每一处为什么这么改。"
                                        )
                                    }
                                ],
                            },
                            "timestamp": "2026-07-09T10:00:20+00:00",
                        }
                    ],
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        final_metric = metric_by_id(report, "final_output_explainability")
        self.assertEqual(final_metric["status"], "pass")
        self.assertIn("events.content", final_metric["basis"])

    async def test_report_sums_only_exact_agent_run_usage(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "msg-1",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {
                                "model": "openai/gpt-4.1-mini",
                                "usage": {
                                    "prompt_tokens": 100,
                                    "completion_tokens": 40,
                                    "total_tokens": 140,
                                },
                            },
                            "metadata": {"agent_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "msg-2",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {
                                "model": "openai/gpt-4.1-mini",
                                "usage": {
                                    "prompt_tokens": 999,
                                    "completion_tokens": 999,
                                    "total_tokens": 1998,
                                },
                            },
                            "metadata": {"agent_run_id": "run-other"},
                            "created_at": "2026-07-09T10:00:21+00:00",
                        },
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(report["token_usage"]["attribution"], "exact")
        self.assertTrue(report["token_usage"]["available"])
        self.assertEqual(report["token_usage"]["prompt_tokens"], 100)
        self.assertEqual(report["token_usage"]["completion_tokens"], 40)
        self.assertEqual(report["token_usage"]["total_tokens"], 140)
        self.assertEqual(report["token_usage"]["message_count"], 1)

    async def test_report_does_not_time_window_estimate_legacy_usage(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "legacy-msg",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {
                                "usage": {
                                    "prompt_tokens": 100,
                                    "completion_tokens": 40,
                                    "total_tokens": 140,
                                },
                            },
                            "metadata": {"thread_run_id": "legacy-thread-run"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(report["token_usage"]["attribution"], "none")
        self.assertFalse(report["token_usage"]["available"])
        self.assertEqual(report["token_usage"]["total_tokens"], 0)

    async def test_report_sums_multiple_usage_rows_for_same_run(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "msg-1",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
                            "metadata": {"agent_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "msg-2",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {"usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}},
                            "metadata": {"agent_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:21+00:00",
                        },
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(report["token_usage"]["message_count"], 2)
        self.assertEqual(report["token_usage"]["prompt_tokens"], 30)
        self.assertEqual(report["token_usage"]["completion_tokens"], 15)
        self.assertEqual(report["token_usage"]["total_tokens"], 45)

    async def test_token_usage_ignores_raw_non_streaming_content(self):
        raw_prompt = "RAW_PROMPT_SHOULD_NOT_LEAK"
        raw_answer = "RAW_ASSISTANT_TEXT_SHOULD_NOT_LEAK"

        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "msg-1",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {
                                "model": "openai/gpt-4.1-mini",
                                "usage": {
                                    "prompt_tokens": 100,
                                    "completion_tokens": 40,
                                    "total_tokens": 140,
                                },
                                "messages": [{"role": "user", "content": raw_prompt}],
                                "choices": [{"message": {"role": "assistant", "content": raw_answer}}],
                            },
                            "metadata": {"agent_run_id": "run-123"},
                            "created_at": "2026-07-09T10:00:20+00:00",
                        }
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )
        rendered = json.dumps(report["token_usage"], ensure_ascii=False)

        self.assertEqual(report["token_usage"]["total_tokens"], 140)
        self.assertNotIn(raw_prompt, rendered)
        self.assertNotIn(raw_answer, rendered)

    async def test_token_usage_ignores_malformed_metadata_without_crashing(self):
        report = await build_agent_run_eval_report(
            FakeClient(
                base_data(
                    messages=[
                        {
                            "message_id": "msg-1",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {"usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}},
                            "metadata": "not-json",
                            "created_at": "2026-07-09T10:00:20+00:00",
                        },
                        {
                            "message_id": "msg-2",
                            "thread_id": "thread-123",
                            "type": "assistant_response_end",
                            "content": {"usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140}},
                            "metadata": None,
                            "created_at": "2026-07-09T10:00:21+00:00",
                        },
                    ]
                )
            ),
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertFalse(report["token_usage"]["available"])
        self.assertEqual(report["token_usage"]["total_tokens"], 0)

    async def test_rejects_report_for_non_owner_run(self):
        client = FakeClient(
            {
                "agent_runs": [
                    {
                        "id": 1,
                        "agent_run_id": "run-123",
                        "thread_id": "thread-123",
                        "status": "running",
                    }
                ],
                "threads": [
                    {
                        "thread_id": "thread-123",
                        "account_id": "owner-user",
                    }
                ],
            }
        )

        with patch("agent.api.verify_thread_access", side_effect=HTTPException(status_code=403, detail="Forbidden")):
            with self.assertRaises(HTTPException) as context:
                await build_agent_run_eval_report(client, FakeRedis(), "run-123", "other-user")

        self.assertEqual(context.exception.status_code, 403)


class AgentRunEvalRouteRegistrationTest(unittest.TestCase):
    def test_agent_eval_routes_are_registered(self):
        paths = {route.path for route in agent_api.router.routes}
        self.assertIn("/developer/agent-evals/runs", paths)
        self.assertIn("/developer/agent-evals/runs/{agent_run_id}", paths)


if __name__ == "__main__":
    unittest.main()
