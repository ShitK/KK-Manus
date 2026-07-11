import json
import unittest
from unittest.mock import AsyncMock, patch

from agent.github_repo_interview_conversation_summary import (
    build_conversation_summary_assistant_response_end,
    build_conversation_summary_from_context,
    build_conversation_summary_payload,
    extract_conversation_turns,
    generate_conversation_summary,
    render_conversation_summary_markdown,
)


class GitHubRepoInterviewConversationSummaryTests(unittest.TestCase):
    def test_extracts_bounded_turns_from_events_and_messages(self):
        turns = extract_conversation_turns(
            messages=[
                {
                    "type": "assistant",
                    "content": {"role": "assistant", "content": "这是 Q4 测试策略的参考答案。"},
                    "created_at": "2026-07-09T10:00:03+00:00",
                },
                {
                    "type": "tool",
                    "content": {"tool_name": "github_repo_interview_workflow", "result": "{}"},
                    "created_at": "2026-07-09T10:00:04+00:00",
                },
            ],
            events=[
                {
                    "author": "user",
                    "content": {"role": "user", "parts": [{"text": "请总结我这一轮 GitHub 仓库面试练习"}]},
                    "timestamp": "2026-07-09T10:00:01+00:00",
                },
                {
                    "author": "kkmanus",
                    "content": json.dumps(
                        {
                            "role": "model",
                            "parts": [{"text": "我会基于当前对话总结这一轮。"}],
                        },
                        ensure_ascii=False,
                    ),
                    "timestamp": "2026-07-09T10:00:02+00:00",
                },
            ],
        )

        self.assertEqual([turn["role"] for turn in turns], ["user", "assistant", "assistant"])
        self.assertEqual(turns[0]["source"], "events")
        self.assertEqual(turns[1]["source"], "events")
        self.assertEqual(turns[2]["source"], "messages")
        self.assertIn("请总结", turns[0]["text"])
        self.assertIn("当前对话", turns[1]["text"])
        self.assertIn("Q4", turns[2]["text"])
        self.assertFalse(any("tool_name" in str(turn) for turn in turns))

    def test_builds_conversation_summary_payload_shape_without_workflow_history(self):
        payload = build_conversation_summary_payload(
            turns=[
                {"role": "user", "text": "Q4 应该怎么回答？", "source": "events"},
                {"role": "assistant", "text": "可以从单元测试和集成测试讲。", "source": "messages"},
            ],
            llm_summary={
                "overview": "本轮围绕 Q4 测试策略回答展开。",
                "discussed_questions": ["Q4"],
                "agent_help": ["给出测试策略回答框架"],
                "open_items": ["继续验证 summary 展示"],
                "practice_overview": {
                    "repository": "ShitK/miniclawd",
                    "role": "后端开发工程师",
                    "difficulty": "Senior",
                    "completed_items": ["Q4 测试策略简述"],
                    "unfinished_items": ["Q4 自动化测试细节"],
                },
                "performance_highlights": [
                    {"title": "测试分层意识", "detail": "能区分单测、集成测试和 smoke 测试。"}
                ],
                "improvement_areas": [
                    {
                        "weakness": "CI 运行策略不足",
                        "evidence": "回答中没有说明不同测试在 CI 中的运行频率。",
                        "suggestion": "补充 PR 必跑和 nightly 回归的区分。",
                    }
                ],
                "ability_profile": [
                    {
                        "dimension": "测试策略",
                        "score": 80,
                        "rationale": "分层意识清晰，但 CI 和 mock 策略还可补充。",
                    }
                ],
                "next_practice_steps": ["把 Q4 按完整 senior 面试表达重答一遍。"],
                "next_practice_suggestion": "继续用 Q4 做一次完整回答。",
            },
        )

        self.assertEqual(payload["tool"], "github_repo_interview_conversation_summary")
        self.assertEqual(payload["type"], "github_repo_interview_conversation_summary")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["summary_kind"], "conversation_summary")
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "summary_ready")
        self.assertEqual(payload["data"]["conversation_turn_count"], 2)
        self.assertEqual(payload["data"]["conversation_summary"]["discussed_questions"], ["Q4"])
        self.assertEqual(payload["data"]["conversation_summary"]["practice_overview"]["repository"], "ShitK/miniclawd")
        self.assertEqual(payload["data"]["conversation_summary"]["performance_highlights"][0]["title"], "测试分层意识")
        self.assertEqual(payload["data"]["conversation_summary"]["improvement_areas"][0]["weakness"], "CI 运行策略不足")
        self.assertEqual(payload["data"]["conversation_summary"]["ability_profile"][0]["score"], 80)
        self.assertEqual(payload["data"]["conversation_summary"]["next_practice_steps"], ["把 Q4 按完整 senior 面试表达重答一遍。"])
        self.assertEqual(
            payload["data"]["session_summary"]["workflow_completion"]["summary_scope"],
            "thread_dialogue",
        )

    def test_empty_turns_produce_partial_fallback_payload(self):
        payload = build_conversation_summary_payload(turns=[], llm_summary=None)

        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["data"]["summary_kind"], "conversation_summary")
        self.assertEqual(payload["data"]["conversation_summary"]["discussed_questions"], [])
        self.assertTrue(
            any(warning["code"] == "conversation_summary_fallback_used" for warning in payload["warnings"])
        )
        markdown = render_conversation_summary_markdown(payload)
        self.assertIn("整轮面试练习总结", markdown)
        self.assertIn("暂无足够可见对话", markdown)

    def test_conversation_summary_payload_includes_session_memory_patch(self):
        payload = build_conversation_summary_payload(
            turns=[{"role": "user", "text": "请总结 Q4", "source": "events"}],
            llm_summary={
                "overview": "本轮围绕 Q4 测试策略展开。",
                "discussed_questions": ["Q4"],
                "agent_help": ["给出测试策略框架"],
                "open_items": [],
                "next_practice_steps": ["把 Q4 按 senior 面试表达重答一遍。"],
                "next_practice_suggestion": "继续完整回答 Q4。",
            },
        )

        patch = payload["data"]["session_memory_patch"]
        self.assertEqual(patch["answered_question_ids"], ["Q4"])
        self.assertEqual(patch["last_question_id"], "Q4")
        self.assertEqual(patch["next_practice_suggestion"], "继续完整回答 Q4。")
        self.assertTrue(patch["summary_completed"])
        self.assertNotIn("请总结 Q4", json.dumps(patch, ensure_ascii=False))

    def test_payload_boundary_does_not_copy_raw_turns_into_context_or_workflow(self):
        sentinel = "RAW_SECRET_ANSWER_SHOULD_NOT_BE_IN_METADATA"
        payload = build_conversation_summary_payload(
            turns=[
                {
                    "role": "user",
                    "text": f"我的原始回答包含 {sentinel}",
                    "source": "events",
                }
            ],
            llm_summary={
                "overview": "本轮用户请求总结 GitHub 面试练习对话。",
                "discussed_questions": [],
                "agent_help": [],
                "open_items": [],
                "next_practice_suggestion": "继续选择题目练习。",
            },
        )

        self.assertNotIn(sentinel, json.dumps(payload["data"]["context_snapshot"], ensure_ascii=False))
        self.assertNotIn(sentinel, json.dumps(payload["data"]["workflow"], ensure_ascii=False))
        self.assertNotIn(sentinel, json.dumps(payload["input"], ensure_ascii=False))

    def test_render_conversation_summary_markdown(self):
        payload = build_conversation_summary_payload(
            turns=[{"role": "user", "text": "Q1 怎么打磨？", "source": "events"}],
            llm_summary={
                "overview": "本轮主要打磨 Q1 回答，并围绕 LLM 超时降级展开追问。",
                "discussed_questions": ["Q1"],
                "agent_help": ["提供可逐字参考的答案"],
                "open_items": ["继续补充 evidence"],
                "practice_overview": {
                    "repository": "ShitK/miniclawd",
                    "role": "后端开发工程师",
                    "difficulty": "Senior",
                    "completed_items": ["Q1 架构边界", "追问1 LLM 超时降级"],
                    "unfinished_items": ["Q2 实现细节"],
                },
                "performance_highlights": [
                    {"title": "生产化思维", "detail": "能把 timeout 转成结构化 failure event。"}
                ],
                "improvement_areas": [
                    {
                        "weakness": "证据锚定偏弱",
                        "evidence": "回答中提到文件路径，但缺少具体源码符号。",
                        "suggestion": "用具体函数或行号锚定论点。",
                    }
                ],
                "ability_profile": [
                    {"dimension": "架构理解", "score": 80, "rationale": "分层清晰，权衡可再展开。"}
                ],
                "next_practice_steps": ["按架构层重新组织追问回答。"],
                "next_practice_suggestion": "继续回答追问。",
            },
        )

        markdown = render_conversation_summary_markdown(payload)

        self.assertIn("## 整轮面试练习总结", markdown)
        self.assertIn("一、练习概况", markdown)
        self.assertIn("ShitK/miniclawd", markdown)
        self.assertIn("二、你的表现亮点", markdown)
        self.assertIn("生产化思维", markdown)
        self.assertIn("三、需要持续打磨的方面", markdown)
        self.assertIn("证据锚定偏弱", markdown)
        self.assertIn("四、能力画像", markdown)
        self.assertIn("架构理解", markdown)
        self.assertIn("80%", markdown)
        self.assertIn("五、后续练习建议", markdown)

    def test_builds_assistant_response_end_with_summary_usage(self):
        payload = build_conversation_summary_payload(
            turns=[{"role": "user", "text": "请总结", "source": "events"}],
            llm_summary={
                "overview": "本轮完成总结。",
                "_llm_metadata": {
                    "model": "deepseek/deepseek-v4-flash",
                    "usage": {
                        "prompt_tokens": 300,
                        "completion_tokens": 120,
                        "total_tokens": 420,
                    },
                    "usage_source": "provider",
                },
                "next_practice_suggestion": "继续练习。",
            },
        )

        content = build_conversation_summary_assistant_response_end(
            payload,
            final_text="## 整轮面试练习总结",
            fallback_model="fallback/model",
        )

        self.assertEqual(content["model"], "deepseek/deepseek-v4-flash")
        self.assertEqual(content["usage"]["prompt_tokens"], 300)
        self.assertEqual(content["usage"]["completion_tokens"], 120)
        self.assertEqual(content["usage"]["total_tokens"], 420)
        self.assertEqual(content["usage_source"], "provider")


class GitHubRepoInterviewConversationSummaryAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_summary_requests_json_object_response(self):
        fake_response = {
            "model": "deepseek/deepseek-v4-flash",
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "total_tokens": 168,
            },
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "overview": "本轮围绕 Q4 测试策略展开。",
                                "discussed_questions": ["Q4"],
                                "agent_help": ["给出测试分层"],
                                "open_items": [],
                                "next_practice_suggestion": "继续完整回答 Q4。",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        with patch(
            "agent.github_repo_interview_conversation_summary.make_llm_api_call",
            new=AsyncMock(return_value=fake_response),
        ) as fake_call:
            result = await generate_conversation_summary(
                [{"role": "user", "text": "Q4 怎么测 Agent Loop？", "source": "events"}],
                model_name="deepseek/deepseek-v4-flash",
            )

        self.assertEqual(result["overview"], "本轮围绕 Q4 测试策略展开。")
        self.assertEqual(result["_llm_metadata"]["model"], "deepseek/deepseek-v4-flash")
        self.assertEqual(result["_llm_metadata"]["usage"]["total_tokens"], 168)
        self.assertEqual(fake_call.await_args.kwargs["response_format"], {"type": "json_object"})
        self.assertGreaterEqual(fake_call.await_args.kwargs["max_tokens"], 1800)
        system_prompt = fake_call.await_args.kwargs["messages"][0]["content"]
        self.assertIn("整轮面试练习总结", system_prompt)
        self.assertIn("performance_highlights", system_prompt)
        self.assertNotIn("Do not score the user", system_prompt)

    async def test_generate_summary_retries_without_json_response_format_when_unsupported(self):
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "overview": "本轮继续总结 GitHub 面试练习。",
                                "discussed_questions": ["Q1", "Q4"],
                                "agent_help": ["整理回答打磨建议"],
                                "open_items": ["继续补证据"],
                                "next_practice_suggestion": "继续按题目复盘。",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        with patch(
            "agent.github_repo_interview_conversation_summary.make_llm_api_call",
            new=AsyncMock(side_effect=[RuntimeError("unsupported response_format"), fake_response]),
        ) as fake_call:
            result = await generate_conversation_summary(
                [{"role": "user", "text": "请总结我这一轮 GitHub 仓库面试练习", "source": "events"}],
                model_name="deepseek/deepseek-v4-flash",
            )

        self.assertEqual(result["discussed_questions"], ["Q1", "Q4"])
        self.assertEqual(fake_call.await_count, 2)
        self.assertEqual(fake_call.await_args_list[0].kwargs["response_format"], {"type": "json_object"})
        self.assertIsNone(fake_call.await_args_list[1].kwargs["response_format"])

    async def test_generate_summary_accepts_rich_markdown_when_json_is_unavailable(self):
        rich_report = "## 整轮面试练习总结\n\n### 一、练习概况\n\n本轮回答了 Q1，并继续打磨追问。"
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": rich_report,
                    }
                }
            ]
        }
        with patch(
            "agent.github_repo_interview_conversation_summary.make_llm_api_call",
            new=AsyncMock(return_value=fake_response),
        ):
            result = await generate_conversation_summary(
                [{"role": "user", "text": "请总结我这一轮 GitHub 仓库面试练习", "source": "events"}],
                model_name="deepseek/deepseek-v4-flash",
            )

        self.assertEqual(result["raw_report"], rich_report)
        payload = build_conversation_summary_payload(
            turns=[{"role": "user", "text": "Q1", "source": "events"}],
            llm_summary=result,
        )
        self.assertEqual(payload["status"], "success")
        self.assertIn("本轮回答了 Q1", render_conversation_summary_markdown(payload))

    async def test_context_fallback_marks_exception_reason_without_raw_error(self):
        with patch(
            "agent.github_repo_interview_conversation_summary.generate_conversation_summary",
            new=AsyncMock(side_effect=RuntimeError("provider secret-value failed")),
        ):
            payload = await build_conversation_summary_from_context(
                messages=[],
                events=[
                    {
                        "author": "user",
                        "content": {"role": "user", "parts": [{"text": "Q4 应该怎么回答？"}]},
                        "timestamp": "2026-07-09T10:00:01+00:00",
                    }
                ],
            )

        self.assertEqual(payload["status"], "partial")
        warning_codes = [warning["code"] for warning in payload["warnings"]]
        self.assertIn("conversation_summary_fallback_used", warning_codes)
        self.assertIn("conversation_summary_llm_error", warning_codes)
        self.assertNotIn("secret-value", json.dumps(payload, ensure_ascii=False))

    async def test_context_fallback_marks_unparseable_llm_output(self):
        with patch(
            "agent.github_repo_interview_conversation_summary.generate_conversation_summary",
            new=AsyncMock(return_value=None),
        ):
            payload = await build_conversation_summary_from_context(
                messages=[],
                events=[
                    {
                        "author": "user",
                        "content": {"role": "user", "parts": [{"text": "Q2 怎么打磨？"}]},
                        "timestamp": "2026-07-09T10:00:01+00:00",
                    }
                ],
            )

        warning_codes = [warning["code"] for warning in payload["warnings"]]
        self.assertIn("conversation_summary_llm_unavailable", warning_codes)


if __name__ == "__main__":
    unittest.main()
