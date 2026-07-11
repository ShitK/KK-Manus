import json
import unittest
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import services.llm as llm_service
from agent.run import ToolManager
from agent.tools.github_repo_answer_coach import (
    LLMAnswerCoachEngine,
    _build_coach_messages,
    _extract_json_response,
    build_coach_request,
)
from agent.tools.github_repo_answer_coach_tool import GitHubRepoAnswerCoachTool
from agentpress.tool import ToolResult
from utils.constants import FREE_TIER_MODELS, MODEL_NAME_ALIASES


class FakeAnswerCoachEngine:
    def __init__(self, feedback: Any):
        self.feedback = feedback
        self.requests = []

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(request)
        return self.feedback


class FailingAnswerCoachEngine:
    def __init__(self, error: Exception):
        self.error = error

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise self.error


def sample_question() -> Dict[str, Any]:
    return {
        "id": "Q3",
        "category": "dependency and packaging",
        "difficulty": "senior",
        "question": "你会如何根据 pallets/flask 的配置文件解释它的技术栈和工程化方式？",
        "answer_direction": "先结合 pyproject.toml 说明当前证据支持的设计边界，再讨论权衡、故障模式和演进路径。",
        "source_paths": ["pyproject.toml"],
        "evidence_refs": ["manifest:pyproject.toml"],
        "evidence_details": [
            {
                "evidence_id": "manifest:pyproject.toml",
                "source_path": "pyproject.toml",
                "evidence_type": "manifest",
                "summary": "python manifest with 6 detected dependencies; entrypoints/scripts: flask",
                "why_it_matters": "用于解释 packaging、dependency、entrypoint 等工程化证据如何支撑这道题。",
                "confidence": "medium",
            }
        ],
        "confidence": "medium",
    }


def sample_llm_feedback_json() -> str:
    return json.dumps(
        {
            "summary": "ok",
            "strengths": [],
            "gaps": [],
            "evidence_missed": [],
            "suggested_answer_outline": [],
            "follow_up_questions": [],
            "grounding_notes": [],
        },
        ensure_ascii=False,
    )


class GitHubRepoAnswerCoachToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_build_coach_messages_includes_compact_grounded_prompt(self):
        question = sample_question()
        question["project_context_pack"] = {
            "repo_metadata": {
                "description": "Full repository description must not be sent.",
                "stars": 12345,
                "html_url": "https://github.com/pallets/flask",
            },
            "readme": "FULL README CONTENT SHOULD NOT APPEAR",
        }
        question["evidence_details"] = [
            {
                "evidence_id": f"evidence:{index}",
                "source_path": f"file{index}.py",
                "evidence_type": "source",
                "summary": f"summary {index}",
                "why_it_matters": f"why {index}",
            }
            for index in range(5)
        ]
        request = build_coach_request(
            question=question,
            user_answer="我会从依赖、入口和验证方式回答。",
            language="zh",
            coach_style="encouraging",
            max_follow_ups=2,
        )

        messages = _build_coach_messages(request)

        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        prompt_text = "\n".join(message["content"] for message in messages)
        self.assertIn(question["question"], prompt_text)
        self.assertIn(question["answer_direction"], prompt_text)
        self.assertIn("我会从依赖、入口和验证方式回答。", prompt_text)
        self.assertIn("summary 0", prompt_text)
        self.assertIn("summary 2", prompt_text)
        self.assertNotIn("summary 3", prompt_text)
        self.assertIn(
            "Use only the provided question, answer_direction, source_paths, evidence_refs, and evidence_details.",
            prompt_text,
        )
        self.assertIn("encouraging: affirm one concrete strength before naming the gap to improve.", prompt_text)
        self.assertNotIn("project_context_pack", prompt_text)
        self.assertNotIn("repo_metadata", prompt_text)
        self.assertNotIn("Full repository description must not be sent.", prompt_text)
        self.assertNotIn("12345", prompt_text)
        self.assertNotIn("https://github.com/pallets/flask", prompt_text)
        self.assertNotIn("FULL README CONTENT SHOULD NOT APPEAR", prompt_text)

    async def test_build_coach_messages_includes_context_policy_when_provided(self):
        request = build_coach_request(
            question=sample_question(),
            user_answer="我会从 pyproject.toml 解释依赖。",
            language="zh",
            coach_style="concise",
            max_follow_ups=2,
        )
        request["context_policy"] = {
            "mode": "role_scoped",
            "active_role": "answer_coach",
            "role_kind": "llm",
            "source": "selected_question.evidence_details",
            "visible_sources": ["selected_question", "evidence_details"],
            "hidden_sources": ["repo_metadata", "readme", "project_context_pack"],
            "allowed_evidence_ids": ["manifest:pyproject.toml"],
            "allowed_source_paths": ["pyproject.toml"],
            "repository_access": "no_new_repository_access",
            "tool_access": "none",
            "persists_user_answer": False,
        }
        request["role"] = {
            "id": "answer_coach",
            "kind": "llm",
            "stage": "coach_answer",
            "evidence_scope": "selected_question.evidence_details",
            "repository_access": "no_new_repository_access",
        }

        messages = _build_coach_messages(request)

        user_payload = json.loads(messages[1]["content"])
        self.assertEqual(user_payload["role"]["id"], "answer_coach")
        self.assertEqual(user_payload["role"]["repository_access"], "no_new_repository_access")
        self.assertEqual(user_payload["context_policy"]["active_role"], "answer_coach")
        self.assertEqual(user_payload["context_policy"]["repository_access"], "no_new_repository_access")
        self.assertEqual(user_payload["context_policy"]["tool_access"], "none")
        self.assertIn("repo_metadata", user_payload["context_policy"]["hidden_sources"])
        self.assertNotIn("FULL README", messages[1]["content"])

    async def test_extract_json_response_from_model_response_shape(self):
        response = type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Message",
                                (),
                                {"content": sample_llm_feedback_json()},
                            )()
                        },
                    )()
                ]
            },
        )()

        parsed = _extract_json_response(response)

        self.assertEqual(parsed["summary"], "ok")

    async def test_extract_json_response_from_dict_shape(self):
        response = {"choices": [{"message": {"content": sample_llm_feedback_json()}}]}

        parsed = _extract_json_response(response)

        self.assertEqual(parsed["summary"], "ok")

    async def test_extract_json_response_from_fenced_json_content(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": f"```json\n{sample_llm_feedback_json()}\n```"
                    }
                }
            ]
        }

        parsed = _extract_json_response(response)

        self.assertEqual(parsed["summary"], "ok")

    async def test_extract_json_response_from_text_wrapped_json_content(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": f"下面是反馈 JSON：\n{sample_llm_feedback_json()}\n请参考。"
                    }
                }
            ]
        }

        parsed = _extract_json_response(response)

        self.assertEqual(parsed["summary"], "ok")

    async def test_tool_handles_non_json_llm_response(self):
        tool = GitHubRepoAnswerCoachTool(engine=FakeAnswerCoachEngine("not json"))

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "coach_generation_failed")
        self.assertFalse(payload["errors"][0]["retryable"])

    async def test_tool_normalizes_feedback_missing_required_array_fields(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "缺少数组字段。",
                "strengths": "not a list",
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["answer_feedback"]["strengths"], ["not a list"])
        self.assertTrue(any(warning["code"] == "feedback_schema_normalized" for warning in payload["warnings"]))

    async def test_tool_rejects_feedback_that_scores_or_pass_fails_user(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "这份回答得分 80，应该通过。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "coach_generation_failed")

    async def test_tool_sanitizes_evidence_details_before_prompt(self):
        question = sample_question()
        question["evidence_details"] = [
            {
                "evidence_id": "manifest:pyproject.toml",
                "source_path": "pyproject.toml",
                "evidence_type": "manifest",
                "summary": "s" * 350,
                "snippet": "n" * 350,
                "why_it_matters": "relevant",
                "confidence": "medium",
                "repo_metadata": {"stars": 123},
                "unexpected": "must not be sent",
            }
        ]
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=question, user_answer="我会解释依赖。")

        self.assertTrue(result.success)
        detail = engine.requests[0]["evidence_details"][0]
        self.assertEqual(len(detail["summary"]), 300)
        self.assertEqual(len(detail["snippet"]), 300)
        self.assertNotIn("repo_metadata", detail)
        self.assertNotIn("unexpected", detail)

    async def test_llm_answer_coach_engine_calls_llm_service_with_expected_params(self):
        request = build_coach_request(
            question=sample_question(),
            user_answer="我会解释依赖。",
            language="zh",
            coach_style="direct",
            max_follow_ups=1,
        )
        response = {"choices": [{"message": {"content": sample_llm_feedback_json()}}]}

        with patch(
            "agent.tools.github_repo_answer_coach.make_llm_api_call",
            new=AsyncMock(return_value=response),
        ) as make_call:
            feedback = await LLMAnswerCoachEngine(model_name="test/model").generate_feedback(request)

        self.assertEqual(feedback["summary"], "ok")
        make_call.assert_awaited_once()
        call_kwargs = make_call.await_args.kwargs
        self.assertEqual(call_kwargs["model_name"], "test/model")
        self.assertEqual(call_kwargs["temperature"], 0)
        self.assertEqual(call_kwargs["max_tokens"], 1200)
        self.assertIsNone(call_kwargs["tools"])
        self.assertEqual(call_kwargs["tool_choice"], "none")
        self.assertFalse(call_kwargs["stream"])
        self.assertEqual(call_kwargs["messages"], _build_coach_messages(request))

    async def test_make_llm_api_call_passes_requested_model_name_to_prepare_params(self):
        captured = {}

        def fake_prepare_params(**kwargs):
            captured.update(kwargs)
            return {
                "model": kwargs["model_name"],
                "messages": kwargs["messages"],
                "stream": kwargs["stream"],
            }

        with patch.object(llm_service, "prepare_params", side_effect=fake_prepare_params), patch.object(
            llm_service.litellm,
            "acompletion",
            new=AsyncMock(return_value={"choices": [{"message": {"content": "ok"}}]}),
        ):
            await llm_service.make_llm_api_call(
                messages=[{"role": "user", "content": "ping"}],
                model_name="test/model",
                stream=False,
            )

        self.assertEqual(captured["model_name"], "test/model")

    async def test_tool_returns_grounded_feedback_with_fake_engine(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "回答已经提到 dependency，但缺少 entrypoint 证据。",
                "strengths": ["识别到了 pyproject.toml 和依赖管理的关系。"],
                "gaps": ["没有说明 entrypoints/scripts: flask 如何支撑命令行入口。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "这条证据能支撑 packaging / dependency / entrypoint 的回答。",
                    }
                ],
                "suggested_answer_outline": ["先讲 pyproject.toml，再讲 dependency，最后讲验证。"],
                "follow_up_questions": ["如果 dependency 冲突，你会如何定位？"],
                "grounding_notes": ["反馈仅基于提供的 evidence_details。"],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(
            question=sample_question(),
            user_answer="我会从 pyproject.toml 解释依赖。",
            language="zh",
        )

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["tool"], "github_repo_answer_coach")
        self.assertEqual(payload["type"], "github_repo_answer_coach")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["input"]["question_id"], "Q3")
        self.assertEqual(payload["input"]["user_answer_excerpt"], "我会从 pyproject.toml 解释依赖。")
        self.assertEqual(payload["data"]["question"]["id"], "Q3")
        self.assertEqual(
            payload["data"]["answer_feedback"]["evidence_missed"][0]["evidence_id"],
            "manifest:pyproject.toml",
        )
        self.assertIn("markdown", payload["data"])
        self.assertEqual(engine.requests[0]["user_answer"], "我会从 pyproject.toml 解释依赖。")
        self.assertEqual(engine.requests[0]["evidence_details"][0]["source_path"], "pyproject.toml")

    async def test_tool_rejects_missing_user_answer(self):
        tool = GitHubRepoAnswerCoachTool(engine=FakeAnswerCoachEngine({}))

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="   ")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["code"], "invalid_user_answer")

    async def test_tool_rejects_question_without_evidence_details(self):
        question = sample_question()
        question["evidence_details"] = []
        tool = GitHubRepoAnswerCoachTool(engine=FakeAnswerCoachEngine({}))

        result = await tool.github_repo_answer_coach(question=question, user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "invalid_question")

    async def test_tool_rejects_question_with_unreadable_evidence_details(self):
        question = sample_question()
        question["evidence_details"] = [{"evidence_id": "manifest:pyproject.toml"}]
        engine = FakeAnswerCoachEngine({})
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=question, user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "invalid_question")
        self.assertEqual(engine.requests, [])

    async def test_tool_rejects_question_without_question_text(self):
        question = sample_question()
        question["question"] = "   "
        tool = GitHubRepoAnswerCoachTool(engine=FakeAnswerCoachEngine({}))

        result = await tool.github_repo_answer_coach(question=question, user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "invalid_question")

    async def test_tool_rejects_invalid_language_and_coach_style(self):
        tool = GitHubRepoAnswerCoachTool(engine=FakeAnswerCoachEngine({}))

        result = await tool.github_repo_answer_coach(
            question=sample_question(),
            user_answer="我会解释依赖。",
            language="fr",
            coach_style="verbose",
        )

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["status"], "error")
        self.assertEqual([error["code"] for error in payload["errors"]], ["invalid_question", "invalid_question"])

    async def test_tool_normalizes_max_follow_ups_and_includes_coach_style_instruction(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": ["问题 1", "问题 2", "问题 3", "问题 4"],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(
            question=sample_question(),
            user_answer="我会解释依赖。",
            coach_style="direct",
            max_follow_ups=99,
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["input"]["max_follow_ups"], 3)
        self.assertEqual(engine.requests[0]["max_follow_ups"], 3)
        self.assertIn("direct", engine.requests[0]["coach_style_instruction"])
        self.assertEqual(payload["data"]["answer_feedback"]["follow_up_questions"], ["问题 1", "问题 2", "问题 3"])

    async def test_tool_accepts_balanced_coach_style_from_llm_tool_call(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": ["回答覆盖了核心 manifest。"],
                "gaps": ["还需要说明验证方式。"],
                "evidence_missed": [],
                "suggested_answer_outline": ["先讲依赖，再讲入口，最后讲验证。"],
                "follow_up_questions": [],
                "grounding_notes": ["仅基于提供的 evidence_details。"],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(
            question=sample_question(),
            user_answer="我会解释依赖和入口。",
            coach_style="balanced",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["input"]["coach_style"], "balanced")
        self.assertEqual(engine.requests[0]["coach_style"], "balanced")
        self.assertIn("balanced", engine.requests[0]["coach_style_instruction"])

    async def test_tool_normalizes_common_llm_schema_variations(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": "回答覆盖了核心 manifest。",
                "gaps": "还需要说明验证方式。",
                "suggested_answer_outline": "先讲依赖，再讲入口，最后讲验证。",
                "grounding_notes": "仅基于提供的 evidence_details。",
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(
            question=sample_question(),
            user_answer="我会解释依赖和入口。",
            coach_style="balanced",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        feedback = payload["data"]["answer_feedback"]
        self.assertEqual(feedback["strengths"], ["回答覆盖了核心 manifest。"])
        self.assertEqual(feedback["gaps"], ["还需要说明验证方式。"])
        self.assertEqual(feedback["evidence_missed"], [])
        self.assertTrue(any(warning["code"] == "feedback_schema_normalized" for warning in payload["warnings"]))

    async def test_tool_truncates_long_user_answer_and_warns(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="答" * 4001)

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(len(engine.requests[0]["user_answer"]), 4000)
        self.assertTrue(any(warning["code"] == "user_answer_truncated" for warning in payload["warnings"]))

    async def test_tool_limits_evidence_details_to_three(self):
        question = sample_question()
        question["evidence_details"] = [
            {
                "evidence_id": f"evidence:{index}",
                "source_path": f"file{index}.py",
                "evidence_type": "source",
                "summary": str(index),
                "why_it_matters": f"why {index}",
            }
            for index in range(5)
        ]
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈简短。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [
                    {"evidence_id": "evidence:2", "source_path": "file2.py", "reason": "有效。"},
                    {"evidence_id": "evidence:4", "source_path": "file4.py", "reason": "被截断。"},
                ],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=question, user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual([item["evidence_id"] for item in engine.requests[0]["evidence_details"]], ["evidence:0", "evidence:1", "evidence:2"])
        self.assertEqual(
            [item["evidence_id"] for item in payload["data"]["answer_feedback"]["evidence_missed"]],
            ["evidence:2"],
        )
        self.assertTrue(any(warning["code"] == "invalid_evidence_reference" for warning in payload["warnings"]))

    async def test_tool_filters_or_rejects_unknown_evidence_id_from_engine(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈引用了未知证据。",
                "strengths": [],
                "gaps": ["缺少有效证据引用。"],
                "evidence_missed": [
                    {"evidence_id": "src:unknown.py#snippet-1", "source_path": "unknown.py", "reason": "invalid"}
                ],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "coach_generation_failed")
        self.assertNotIn("src:unknown.py#snippet-1", result.output)

    async def test_tool_filters_invalid_evidence_missed_and_warns(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈包含一个有效证据和一个无效证据。",
                "strengths": ["识别到了 pyproject.toml。"],
                "gaps": ["缺少入口验证说明。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "有效证据。",
                    },
                    {"evidence_id": "src:unknown.py#snippet-1", "source_path": "unknown.py", "reason": "invalid"},
                ],
                "suggested_answer_outline": ["先讲 pyproject.toml。"],
                "follow_up_questions": [],
                "grounding_notes": ["仅基于提供证据。"],
            }
        )
        tool = GitHubRepoAnswerCoachTool(engine=engine)

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        missed = payload["data"]["answer_feedback"]["evidence_missed"]
        self.assertEqual([item["evidence_id"] for item in missed], ["manifest:pyproject.toml"])
        self.assertTrue(any(warning["code"] == "invalid_evidence_reference" for warning in payload["warnings"]))

    async def test_tool_returns_error_when_engine_fails_without_traceback(self):
        tool = GitHubRepoAnswerCoachTool(engine=FailingAnswerCoachEngine(RuntimeError("secret boom")))

        result = await tool.github_repo_answer_coach(question=sample_question(), user_answer="我会解释依赖。")

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "coach_generation_failed")
        self.assertNotIn("Traceback", result.output)
        self.assertNotIn("secret boom", result.output)


class FakeThreadManager:
    def __init__(self):
        self.registered = []

    def add_tool(self, tool_class, **kwargs):
        self.registered.append((tool_class, kwargs))


class GitHubRepoAnswerCoachToolRoutingHintTest(unittest.TestCase):
    def test_answer_coach_docstring_deprioritizes_multi_turn_workflow(self):
        doc = GitHubRepoAnswerCoachTool.github_repo_answer_coach.__doc__ or ""

        self.assertIn("github_repo_interview_workflow", doc)
        self.assertIn('stage="coach_answer"', doc)
        self.assertIn("multi-turn GitHub interview workflow", doc)
        self.assertIn("prefer", doc)


class GitHubRepoAnswerCoachRegistrationTest(unittest.TestCase):
    def test_deepseek_v4_flash_model_alias_is_available(self):
        self.assertIn("deepseek/deepseek-v4-flash", FREE_TIER_MODELS)
        self.assertEqual(MODEL_NAME_ALIASES["deepseek-v4-flash"], "deepseek/deepseek-v4-flash")
        self.assertEqual(MODEL_NAME_ALIASES["deepseek-chat"], "deepseek/deepseek-v4-flash")
        self.assertEqual(MODEL_NAME_ALIASES["DeepSeek/DeepSeek-chat"], "deepseek/deepseek-v4-flash")

    def test_tool_manager_does_not_register_answer_coach_tool_by_default(self):
        fake_thread_manager = FakeThreadManager()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
        )

        manager.register_all_tools()

        registered = [tool_class for tool_class, _kwargs in fake_thread_manager.registered]
        self.assertNotIn(GitHubRepoAnswerCoachTool, registered)

    def test_answer_coach_tool_remains_available_as_direct_tool_class(self):
        fake_thread_manager = FakeThreadManager()
        fake_thread_manager.add_tool(
            GitHubRepoAnswerCoachTool,
            engine=LLMAnswerCoachEngine(model_name="deepseek/deepseek-v4-flash"),
        )

        registered = [tool_class for tool_class, _kwargs in fake_thread_manager.registered]
        self.assertIn(GitHubRepoAnswerCoachTool, registered)
        engine = fake_thread_manager.registered[0][1]["engine"]
        self.assertIsInstance(engine, LLMAnswerCoachEngine)
        self.assertEqual(engine.model_name, "deepseek/deepseek-v4-flash")
