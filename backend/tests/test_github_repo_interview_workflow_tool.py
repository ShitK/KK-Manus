import unittest
from typing import Any, Dict
import json
from unittest.mock import AsyncMock

from agent.run import ToolManager
from agent.tools.github_repo_interview_workflow import build_workflow_state
from agent.tools.github_repo_interview_workflow_tool import (
    GitHubRepoInterviewWorkflowTool,
    LLMWorkflowStageEngine,
)
from agent.tools.github_repo_interview_workflow_roles import (
    EvidenceGatekeeper,
    active_role_for_stage,
    role_contract,
)


def sample_question():
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


def sample_questions_pack():
    return {
        "interview_questions": [
            {
                **sample_question(),
                "id": "Q1",
                "category": "architecture",
                "question": "你会如何解释这个仓库的架构边界？",
            },
            sample_question(),
        ],
        "question_generation_summary": {
            "strategy": "deterministic_evidence_templates",
            "generated_count": 2,
            "has_evidence_details": True,
        },
    }


def full_slice_4_payload():
    return {
        "tool": "github_repo_interview_prep",
        "data": {
            **sample_questions_pack(),
            "repo_metadata": {
                "stars": 12345,
                "html_url": "https://github.com/pallets/flask",
            },
            "readme": {
                "text_excerpt": "FULL README SHOULD NOT REACH WORKFLOW REQUEST",
            },
            "project_context_pack": {
                "repo_metadata": {
                    "description": "Full repository description must not be forwarded.",
                },
                "source_evidence": [
                    {
                        "path": "src/unknown.py",
                        "snippet": "Unknown source evidence must not be forwarded.",
                    }
                ],
            },
            "markdown": "full markdown should not be forwarded",
        },
    }


def questions_pack_with_target_role(target_role: str):
    return {
        "tool": "github_repo_interview_prep",
        "input": {"target_role": target_role},
        "data": {
            **sample_questions_pack(),
        },
    }


class GitHubRepoInterviewWorkflowStateTest(unittest.TestCase):
    def test_build_workflow_state_selects_question_by_exact_id(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertEqual(state["workflow"]["current_stage"], "question_selected")
        self.assertEqual(state["selected_question"]["id"], "Q3")
        self.assertEqual(state["selected_question"]["question"], sample_question()["question"])
        self.assertEqual(state["evidence_policy"]["source"], "selected_question.evidence_details")
        self.assertEqual(state["evidence_policy"]["allowed_evidence_ids"], ["manifest:pyproject.toml"])
        self.assertEqual(state["evidence_policy"]["repository_access"], "no_new_repository_access")
        self.assertEqual(len(state["evidence_details"]), 1)
        self.assertEqual(state["evidence_details"][0]["source_path"], "pyproject.toml")
        self.assertEqual([step["id"] for step in state["workflow"]["steps"]], [
            "prep",
            "question",
            "answer_coach",
            "follow_up",
            "summary",
        ])

    def test_build_workflow_state_selects_question_by_preferred_category(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="",
            preferred_question_category="架构设计",
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertEqual(state["selected_question"]["id"], "Q1")
        self.assertEqual(state["selected_question"]["category"], "architecture")

    def test_build_workflow_state_returns_error_when_preferred_category_has_no_match(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="",
            preferred_question_category="测试验证",
            language="zh",
        )

        self.assertEqual(state["status"], "error")
        self.assertEqual(state["errors"][0]["code"], "question_not_found")

    def test_build_workflow_state_includes_role_contracts(self):
        state = build_workflow_state(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertEqual(state["workflow"]["active_role"], "answer_coach")
        roles = state["workflow"]["roles"]
        self.assertEqual(
            [role["id"] for role in roles],
            [
                "workflow_orchestrator",
                "question_selector",
                "evidence_gatekeeper",
                "answer_coach",
                "follow_up_coach",
                "session_summarizer",
            ],
        )
        answer_role = next(role for role in roles if role["id"] == "answer_coach")
        self.assertEqual(answer_role["kind"], "llm")
        self.assertEqual(answer_role["stage"], "coach_answer")
        self.assertEqual(answer_role["evidence_scope"], "selected_question.evidence_details")
        self.assertEqual(answer_role["repository_access"], "no_new_repository_access")

    def test_context_policy_for_state_describes_role_scoped_visibility(self):
        from agent.tools.github_repo_interview_workflow_context import context_policy_for_state

        state = build_workflow_state(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )

        policy = context_policy_for_state(state, "answer_coach")

        self.assertEqual(policy["mode"], "role_scoped")
        self.assertEqual(policy["active_role"], "answer_coach")
        self.assertEqual(policy["role_kind"], "llm")
        self.assertEqual(policy["source"], "selected_question.evidence_details")
        self.assertEqual(policy["allowed_evidence_ids"], ["manifest:pyproject.toml"])
        self.assertEqual(policy["allowed_source_paths"], ["pyproject.toml"])
        self.assertEqual(policy["repository_access"], "no_new_repository_access")
        self.assertEqual(policy["tool_access"], "none")
        self.assertFalse(policy["persists_user_answer"])
        self.assertIn("selected_question", policy["visible_sources"])
        self.assertIn("evidence_details", policy["visible_sources"])
        self.assertIn("project_context_pack", policy["hidden_sources"])
        self.assertIn("thread_history", policy["hidden_sources"])

    def test_build_workflow_state_includes_context_policy_for_active_role(self):
        state = build_workflow_state(
            stage="coach_answer",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            language="zh",
        )

        policy = state["context_policy"]

        self.assertEqual(policy["active_role"], "answer_coach")
        self.assertEqual(policy["allowed_evidence_ids"], ["manifest:pyproject.toml"])
        self.assertIn("project_context_pack", policy["hidden_sources"])
        policy_text = str(policy)
        self.assertNotIn("FULL README SHOULD NOT REACH WORKFLOW REQUEST", policy_text)
        self.assertNotIn("github.com/pallets/flask", policy_text)
        self.assertNotIn("Unknown source evidence must not be forwarded", policy_text)

    def test_build_workflow_state_maps_active_role_by_stage(self):
        cases = {
            "select_question": "question_selector",
            "coach_answer": "answer_coach",
            "coach_follow_up": "follow_up_coach",
            "summarize": "session_summarizer",
        }

        for stage, expected_role in cases.items():
            with self.subTest(stage=stage):
                state = build_workflow_state(
                    stage=stage,
                    prep_questions_pack=sample_questions_pack(),
                    question_id="Q3",
                    language="zh",
                )

                self.assertEqual(state["status"], "success")
                self.assertEqual(state["workflow"]["active_role"], expected_role)

    def test_active_role_for_stage_defaults_to_question_selector_for_unknown_stage(self):
        self.assertEqual(active_role_for_stage("unknown_stage"), "question_selector")

    def test_build_workflow_state_marks_answered_follow_up_as_completed(self):
        state = build_workflow_state(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会用 CLI smoke test 验证入口到 AgentLoop。",
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertEqual(state["workflow"]["current_stage"], "follow_up_answered")
        follow_up_step = next(step for step in state["workflow"]["steps"] if step["id"] == "follow_up")
        summary_step = next(step for step in state["workflow"]["steps"] if step["id"] == "summary")
        self.assertEqual(follow_up_step["status"], "success")
        self.assertEqual(summary_step["status"], "pending")

    def test_build_workflow_state_inherits_selected_question_id_for_summary(self):
        previous = {
            "selected_question": {
                "id": "Q3",
                "question": sample_question()["question"],
            },
            "workflow": {
                "current_stage": "answer_coached",
            },
        }

        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="",
            previous_workflow_state=previous,
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertEqual(state["workflow"]["current_stage"], "summary_ready")
        self.assertEqual(state["selected_question"]["id"], "Q3")

    def test_role_contract_returns_empty_for_unknown_role(self):
        self.assertEqual(role_contract("nonexistent_role"), {})

    def test_build_workflow_state_rejects_missing_questions_pack(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack={},
            question_id="Q3",
            language="zh",
        )

        self.assertEqual(state["status"], "error")
        self.assertEqual(state["errors"][0]["code"], "invalid_prep_questions_pack")

    def test_build_workflow_state_rejects_unknown_question_id_without_guessing(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q",
            language="zh",
        )

        self.assertEqual(state["status"], "error")
        self.assertEqual(state["errors"][0]["code"], "question_not_found")
        self.assertNotIn("selected_question", state)

    def test_build_workflow_state_rejects_question_without_readable_evidence_details(self):
        pack = sample_questions_pack()
        pack["interview_questions"][1]["evidence_details"] = [
            {"evidence_id": "manifest:pyproject.toml"}
        ]

        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=pack,
            question_id="Q3",
            language="zh",
        )

        self.assertEqual(state["status"], "error")
        self.assertEqual(state["errors"][0]["code"], "invalid_question_evidence")

    def test_build_workflow_state_sanitizes_full_slice_4_payload_input(self):
        full_payload = {
            "tool": "github_repo_interview_prep",
            "data": {
                **sample_questions_pack(),
                "repo_metadata": {
                    "stars": 12345,
                    "html_url": "https://github.com/pallets/flask",
                },
                "readme": {
                    "text_excerpt": "FULL README SHOULD NOT REACH WORKFLOW STATE",
                },
                "project_context_pack": {
                    "repo_metadata": {
                        "description": "Full repository description must not be forwarded.",
                    }
                },
                "markdown": "full markdown should not be forwarded",
            },
        }

        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=full_payload,
            question_id="Q3",
            language="zh",
        )

        self.assertEqual(state["status"], "success")
        self.assertNotIn("repo_metadata", state)
        self.assertNotIn("project_context_pack", state)
        self.assertNotIn("readme", state)
        self.assertNotIn("markdown", state)
        self.assertNotIn("repo_metadata", state["selected_question"])
        self.assertNotIn("project_context_pack", state["selected_question"])
        self.assertNotIn("repo_metadata", state["evidence_details"][0])
        self.assertNotIn("readme", state["evidence_details"][0])

    def test_evidence_gatekeeper_filters_prior_state_unknown_references(self):
        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        warnings = []
        gatekeeper = EvidenceGatekeeper(state)
        previous_state = {
            "answer_feedback": {
                "summary": "回答提到了 pyproject.toml。",
                "gaps": [
                    "需要补充 pyproject.toml。",
                    "不要引用 unknown.py。",
                    "不要使用 https://example.com。",
                ],
                "follow_up_questions": ["你会如何验证 pyproject.toml？", "unknown.py 里有什么？"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "有效。",
                    },
                    {
                        "evidence_id": "src:unknown.py#snippet-1",
                        "source_path": "unknown.py",
                        "reason": "invalid",
                    },
                ],
            },
            "follow_up": {
                "questions": ["你会如何验证 pyproject.toml？", "unknown.py 中有哪些证据？"],
                "feedback": ["追问回答仍基于 pyproject.toml。", "还提到了 https://example.com。"],
                "grounding_notes": ["仅基于 allowed evidence。", "不要引用 src:unknown.py#snippet-1。"],
            },
        }

        feedback = gatekeeper.filter_prior_feedback(previous_state, warnings)
        follow_up = gatekeeper.filter_prior_follow_up(previous_state, warnings)

        self.assertEqual(feedback["gaps"], ["需要补充 pyproject.toml。"])
        self.assertEqual(feedback["follow_up_questions"], ["你会如何验证 pyproject.toml？"])
        self.assertEqual(feedback["evidence_missed"][0]["evidence_id"], "manifest:pyproject.toml")
        self.assertEqual(follow_up["questions"], ["你会如何验证 pyproject.toml？"])
        self.assertEqual(follow_up["feedback"], ["追问回答仍基于 pyproject.toml。"])
        self.assertEqual(follow_up["grounding_notes"], ["仅基于 allowed evidence。"])
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in warnings))

    def test_evidence_gatekeeper_filters_follow_up_response_unknown_references(self):
        state = build_workflow_state(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        warnings = []
        gatekeeper = EvidenceGatekeeper(state)

        follow_up = gatekeeper.filter_follow_up_response(
            {
                "questions": [
                    "你会如何验证 pyproject.toml？",
                    "unknown.py 中有哪些证据？",
                    "第二个合法问题仍然基于 pyproject.toml。",
                ],
                "feedback": [
                    "继续基于 pyproject.toml。",
                    "参考 https://example.com。",
                ],
                "grounding_notes": [
                    "仅基于 pyproject.toml。",
                    "不要引用 src:unknown.py#snippet-1。",
                ],
            },
            max_follow_ups=2,
            warnings=warnings,
        )

        self.assertEqual(follow_up["questions"], [
            "你会如何验证 pyproject.toml？",
            "第二个合法问题仍然基于 pyproject.toml。",
        ])
        self.assertEqual(follow_up["feedback"], ["继续基于 pyproject.toml。"])
        self.assertEqual(follow_up["grounding_notes"], ["仅基于 pyproject.toml。"])
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in warnings))

    def test_evidence_gatekeeper_filters_summary_response_unknown_references(self):
        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        warnings = []
        gatekeeper = EvidenceGatekeeper(state)

        summary = gatekeeper.filter_summary_response(
            {
                "covered_evidence": [
                    "manifest:pyproject.toml",
                    "src:unknown.py#snippet-1",
                ],
                "missed_evidence": [
                    "manifest:pyproject.toml",
                    "readme:README.md",
                ],
                "practice_notes": [
                    "回答基于 pyproject.toml。",
                    "不要提 unknown.py。",
                ],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            },
            warnings=warnings,
        )

        self.assertEqual(summary["covered_evidence"], ["manifest:pyproject.toml"])
        self.assertEqual(summary["missed_evidence"], ["manifest:pyproject.toml"])
        self.assertEqual(summary["practice_notes"], ["回答基于 pyproject.toml。"])
        self.assertEqual(summary["next_practice_suggestion"], "继续练习 evidence grounding。")
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in warnings))


class FakeAnswerCoachEngine:
    def __init__(self, feedback: Any):
        self.feedback = feedback
        self.requests = []

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(request)
        return self.feedback


class SequenceAnswerCoachEngine:
    def __init__(self, feedbacks: list[Any]):
        self.feedbacks = feedbacks
        self.requests = []

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.feedbacks) - 1)
        return self.feedbacks[index]


class RaisingWorkflowStageEngine:
    def __init__(self):
        self.requests = []

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        self.requests.append(request)
        raise RuntimeError("LLM unavailable")


class GitHubRepoInterviewWorkflowToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_prep_target_role_is_used_for_first_memory_retrieval_and_session_patch(self):
        loader = AsyncMock(
            return_value={
                "session_memory_context": {},
                "saved_memory_context": [],
                "vector_memory_context": [],
                "vector_memory_retrieval": {"status": "no_match"},
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(memory_context_loader=loader)

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=questions_pack_with_target_role("AI Agent开发工程师"),
            question_id="Q1",
        )

        payload = json.loads(result.output)
        loader.assert_awaited_once_with(
            query_text="你会如何解释这个仓库的架构边界？",
            target_role="AI Agent开发工程师",
            category="architecture",
        )
        self.assertEqual(payload["input"]["target_role"], "AI Agent开发工程师")
        self.assertEqual(
            payload["data"]["session_memory_patch"]["target_role"],
            "AI Agent开发工程师",
        )

    async def test_existing_session_target_role_takes_precedence_over_prep_role(self):
        loader = AsyncMock(
            return_value={
                "session_memory_context": {"target_role": "资深后端开发工程师"},
                "saved_memory_context": [],
                "vector_memory_context": [],
                "vector_memory_retrieval": {"status": "no_match"},
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(memory_context_loader=loader)

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=questions_pack_with_target_role("AI Agent开发工程师"),
            question_id="Q1",
            session_memory_context={"target_role": "资深后端开发工程师"},
        )

        payload = json.loads(result.output)
        loader.assert_awaited_once_with(
            query_text="你会如何解释这个仓库的架构边界？",
            target_role="资深后端开发工程师",
            category="architecture",
        )
        self.assertEqual(payload["input"]["target_role"], "资深后端开发工程师")
        self.assertEqual(
            payload["data"]["session_memory_patch"]["target_role"],
            "资深后端开发工程师",
        )

    async def test_unsafe_or_oversized_prep_target_role_is_not_propagated(self):
        for target_role in ("", "https://example.com/role", "A" * 81):
            with self.subTest(target_role=target_role):
                tool = GitHubRepoInterviewWorkflowTool()

                result = await tool.github_repo_interview_workflow(
                    stage="select_question",
                    prep_questions_pack=questions_pack_with_target_role(target_role),
                    question_id="Q1",
                )

                payload = json.loads(result.output)
                self.assertNotIn("target_role", payload["input"])
                self.assertNotIn("target_role", payload["data"]["session_memory_patch"])

    async def test_model_tool_call_automatically_loads_vector_memory_context(self):
        loader = AsyncMock(
            return_value={
                "session_memory_context": {
                    "target_role": "后端开发工程师",
                    "current_practice_category": "architecture",
                },
                "saved_memory_context": [],
                "vector_memory_context": [
                    {
                        "id": "memory-1",
                        "text": "此前架构练习需要继续说明入口、application 编排、core 接口与 infrastructure 实现之间的边界。",
                        "similarity": 0.82,
                        "persisted": True,
                        "provenance": {"kind": "demo_fixture"},
                    }
                ],
                "vector_memory_retrieval": {
                    "status": "matched",
                    "diagnostics": {
                        "model": "openai/text-embedding-v4",
                        "threshold": 0.65,
                        "top_k": 3,
                        "candidate_count": 1,
                        "matched_count": 1,
                        "applied_count": 1,
                    },
                },
            }
        )
        answer_engine = FakeAnswerCoachEngine(
            {
                "summary": "回答覆盖了基本分层边界。",
                "strengths": ["说明了 core 与 infrastructure 的分工。"],
                "gaps": ["需要补充入口调用链。"],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": ["仅基于允许的题目证据。"],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=answer_engine,
            memory_context_loader=loader,
        )
        user_answer = "我开始回答 Q1：入口负责启动，application 编排流程，core 定义接口。"

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q1",
            user_answer=user_answer,
        )

        payload = json.loads(result.output)
        loader.assert_awaited_once_with(
            query_text=user_answer,
            target_role=None,
            category="architecture",
        )
        self.assertEqual(payload["data"]["vector_memory_retrieval"]["status"], "matched")
        self.assertEqual(payload["data"]["vector_memory_context"][0]["similarity"], 0.82)
        self.assertEqual(
            answer_engine.requests[0]["memory_context"]["semantic"][0]["provenance"],
            {"kind": "demo_fixture"},
        )

    async def test_injected_loader_overrides_untrusted_memory_arguments(self):
        loader = AsyncMock(
            return_value={
                "session_memory_context": {},
                "saved_memory_context": [],
                "vector_memory_context": [
                    {
                        "id": "trusted-memory",
                        "text": "这是服务端按当前认证账号召回的可信练习记忆，用于继续加强架构边界和验证方法的表达。",
                        "similarity": 0.79,
                        "persisted": True,
                        "provenance": {"kind": "demo_fixture"},
                    }
                ],
                "vector_memory_retrieval": {
                    "status": "matched",
                    "diagnostics": {"threshold": 0.65, "applied_count": 1},
                },
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(memory_context_loader=loader)

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q1",
            vector_memory_context=[
                {
                    "id": "forged-memory",
                    "text": "这是模型参数伪造的记忆，不应该进入工作流上下文或前端展示。",
                    "similarity": 1.0,
                    "persisted": True,
                }
            ],
            vector_memory_retrieval={"status": "matched"},
            saved_memory_context=[],
            session_memory_context={},
        )

        payload = json.loads(result.output)
        loader.assert_awaited_once()
        self.assertEqual(payload["data"]["vector_memory_context"][0]["id"], "trusted-memory")
        self.assertNotIn("forged-memory", result.output)

    async def test_select_question_stage_returns_success_without_llm(self):
        answer_engine = FakeAnswerCoachEngine({})
        follow_up_engine = FakeAnswerCoachEngine({})
        summary_engine = FakeAnswerCoachEngine({})
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=answer_engine,
            follow_up_engine=follow_up_engine,
            summary_engine=summary_engine,
        )

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "question_selected")
        self.assertEqual(payload["data"]["selected_question"]["id"], "Q3")
        self.assertNotIn("answer_feedback", payload["data"])
        self.assertNotIn("follow_up", payload["data"])
        self.assertNotIn("session_summary", payload["data"])
        self.assertNotIn("answer_quality_signals", payload["data"])
        self.assertEqual(answer_engine.requests, [])
        self.assertEqual(follow_up_engine.requests, [])
        self.assertEqual(summary_engine.requests, [])

    async def test_vector_memory_context_is_sanitized_and_visible_in_snapshot(self):
        tool = GitHubRepoInterviewWorkflowTool()
        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q1",
            vector_memory_context=[
                {
                    "id": "memory-1",
                    "text": "此前练习中已识别 AgentLoop 的边界，需要继续补充失败恢复、测试断言和架构取舍的表达。",
                    "similarity": 1.5,
                    "persisted": True,
                    "embedding": [0.1, 0.2],
                    "provenance": {"kind": "demo_fixture", "secret": "drop"},
                }
            ],
            vector_memory_retrieval={
                "status": "matched",
                "diagnostics": {
                    "model": "openai/text-embedding-v4",
                    "threshold": 0.65,
                    "top_k": 3,
                    "candidate_count": 2,
                    "matched_count": 1,
                    "applied_count": 1,
                },
            },
        )

        payload = json.loads(result.output)
        context = payload["data"]["vector_memory_context"][0]
        self.assertEqual(context["similarity"], 1.0)
        self.assertNotIn("embedding", context)
        self.assertEqual(context["provenance"], {"kind": "demo_fixture"})
        self.assertIn("vector_memories", payload["data"]["context_snapshot"]["visible_sources"])
        self.assertEqual(payload["data"]["context_snapshot"]["vector_memory"]["matched_count"], 1)

    async def test_select_question_stage_includes_controlled_multi_agent_trace(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
        )
        payload = json.loads(result.output)

        self.assertTrue(result.success)
        trace = payload["data"]["multi_agent_trace"]
        self.assertEqual(trace["mode"], "controlled_local_trace")
        self.assertEqual(
            [agent["id"] for agent in trace["agents"]],
            ["repository_analyst", "interview_question", "answer_coach", "quality_reviewer"],
        )
        self.assertEqual(trace["quality_signals"]["recommended_next_step"], "answer_question")
        trace_text = str(trace)
        self.assertNotIn("FULL README SHOULD NOT REACH WORKFLOW REQUEST", trace_text)
        self.assertNotIn("github.com/pallets/flask", trace_text)
        self.assertNotIn("Unknown source evidence must not be forwarded", trace_text)

    async def test_workflow_accepts_chinese_coach_style_alias(self):
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=FakeAnswerCoachEngine(
                {
                    "summary": "回答已经提到 manifest，但缺少入口验证。",
                    "strengths": ["说明了 pyproject.toml。"],
                    "gaps": ["需要补充验证方式。"],
                    "evidence_missed": [],
                    "suggested_answer_outline": [],
                    "follow_up_questions": [],
                    "grounding_notes": ["反馈仅使用 manifest:pyproject.toml。"],
                }
            )
        )

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            user_answer="我会先说明 manifest 和入口文件。",
            language="中文",
            coach_style="平衡一点",
        )
        payload = json.loads(result.output)

        self.assertTrue(result.success)
        self.assertEqual(payload["input"]["language"], "zh")
        self.assertEqual(payload["input"]["coach_style"], "balanced")
        self.assertEqual(payload["data"]["normalized_intent"]["language"]["raw"], "中文")
        self.assertEqual(payload["data"]["normalized_intent"]["language"]["normalized"], "zh")
        self.assertEqual(payload["data"]["normalized_intent"]["coach_style"]["raw"], "平衡一点")
        self.assertEqual(payload["data"]["normalized_intent"]["coach_style"]["normalized"], "balanced")

    async def test_workflow_selects_question_by_preferred_chinese_category_when_question_id_missing(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            preferred_question_category="架构设计",
            language="中文",
        )
        payload = json.loads(result.output)

        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["selected_question"]["id"], "Q1")
        self.assertEqual(payload["data"]["selected_question"]["category"], "architecture")
        self.assertEqual(payload["input"]["preferred_question_category"], "architecture")
        self.assertEqual(
            payload["data"]["normalized_intent"]["preferred_question_category"]["raw"],
            "架构设计",
        )

    async def test_workflow_question_id_takes_precedence_over_preferred_category(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            preferred_question_category="架构设计",
            language="zh",
        )
        payload = json.loads(result.output)

        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["selected_question"]["id"], "Q3")

    async def test_workflow_returns_error_when_preferred_category_has_no_match(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            preferred_question_category="测试验证",
            language="zh",
        )
        payload = json.loads(result.output)

        self.assertFalse(result.success)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["errors"][0]["code"], "question_not_found")

    async def test_workflow_payload_includes_context_snapshot_and_memory_candidates_without_answer_text(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈不应把用户回答 SECRET_ANSWER 写入 snapshot。",
                "strengths": [],
                "gaps": ["需要补充架构取舍和测试验证。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "没有引用这条 evidence。",
                    }
                ],
                "suggested_answer_outline": ["补充一个 validation step。"],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            user_answer="SECRET_ANSWER 我会从 pyproject.toml 解释依赖。",
            language="zh",
            coach_style="direct",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertIn("context_snapshot", payload["data"])
        self.assertIn("memory_candidates", payload["data"])
        self.assertIn("multi_agent_trace", payload["data"])
        self.assertIn("answer_quality_signals", payload["data"])
        snapshot = payload["data"]["context_snapshot"]
        self.assertEqual(snapshot["scope"], "request")
        self.assertEqual(snapshot["persistence"], "not_persisted")
        self.assertEqual(snapshot["active_role"], "answer_coach")
        self.assertFalse(snapshot["persists_user_answer"])
        self.assertFalse(snapshot["redaction_policy"]["includes_user_answer"])
        self.assertFalse(snapshot["redaction_policy"]["includes_repo_evidence_text"])
        candidate_ids = {candidate["id"] for candidate in payload["data"]["memory_candidates"]}
        self.assertIn("language_preference_hint:zh", candidate_ids)
        self.assertIn("feedback_preference_hint:direct", candidate_ids)
        self.assertIn("practice_weakness_tag:missing_evidence", candidate_ids)
        self.assertIn("practice_weakness_tag:weak_architecture_tradeoff", candidate_ids)
        self.assertIn("practice_weakness_tag:unclear_testing_story", candidate_ids)
        signal_by_id = {signal["id"]: signal for signal in payload["data"]["answer_quality_signals"]}
        self.assertEqual(signal_by_id["evidence_grounding"]["status"], "needs_attention")
        self.assertEqual(signal_by_id["completeness_missing_evidence"]["evidence_refs"], ["manifest:pyproject.toml"])
        self.assertEqual(signal_by_id["architecture_understanding"]["status"], "needs_attention")
        self.assertEqual(signal_by_id["tradeoff_awareness"]["status"], "needs_attention")
        self.assertEqual(signal_by_id["privacy_boundary"]["status"], "supported")

        for candidate in payload["data"]["memory_candidates"]:
            self.assertFalse(candidate["persisted"])
            self.assertTrue(candidate["requires_user_confirmation"])
            self.assertEqual(candidate["status"], "candidate_only")

        payload_text = str(payload["data"]["context_snapshot"]) + str(payload["data"]["memory_candidates"])
        self.assertNotIn("SECRET_ANSWER", payload_text)
        self.assertNotIn("FULL README SHOULD NOT REACH WORKFLOW REQUEST", payload_text)
        self.assertNotIn("github.com/pallets/flask", payload_text)
        self.assertNotIn("Unknown source evidence must not be forwarded", payload_text)
        self.assertNotIn("SECRET_ANSWER", str(payload["data"]["answer_quality_signals"]))
        trace = payload["data"]["multi_agent_trace"]
        answer_agent = next(agent for agent in trace["agents"] if agent["id"] == "answer_coach")
        quality_agent = next(agent for agent in trace["agents"] if agent["id"] == "quality_reviewer")
        self.assertTrue(answer_agent["reads_user_answer"])
        self.assertFalse(quality_agent["reads_user_answer"])
        self.assertEqual(trace["quality_signals"]["coverage"], "partial")
        self.assertEqual(trace["quality_signals"]["recommended_next_step"], "revise_with_evidence")
        self.assertNotIn("SECRET_ANSWER", str(trace))

    async def test_workflow_accepts_only_explicit_active_saved_memory_context(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            saved_memory_context=[
                {
                    "id": "m1",
                    "type": "language_preference_hint",
                    "value": "zh",
                    "label": "本次请求的候选语言偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": ["input.language"],
                    "status": "active",
                    "persisted": True,
                },
                {
                    "id": "bad",
                    "type": "practice_weakness_tag",
                    "value": "raw free form text",
                    "label": "user_answer 原文",
                    "source_stage": "summarize",
                    "source_fields": ["user_answer"],
                    "status": "active",
                    "persisted": True,
                },
                {
                    "id": "candidate-only-memory",
                    "type": "feedback_preference_hint",
                    "value": "balanced",
                    "label": "本次请求的候选反馈风格偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": ["input.coach_style"],
                    "status": "candidate_only",
                    "persisted": False,
                },
                {
                    "id": "deleted-memory",
                    "type": "feedback_preference_hint",
                    "value": "direct",
                    "label": "本次请求的候选反馈风格偏好。",
                    "source_stage": "coach_answer",
                    "source_fields": ["input.coach_style"],
                    "status": "deleted",
                    "persisted": True,
                },
            ],
        )
        payload = json.loads(result.output)

        self.assertTrue(result.success)
        self.assertEqual(len(payload["data"]["saved_memory_context"]), 1)
        self.assertEqual(payload["data"]["saved_memory_context"][0]["type"], "language_preference_hint")
        self.assertIn("saved_memories", payload["data"]["context_snapshot"]["visible_sources"])
        self.assertEqual(payload["data"]["context_snapshot"]["saved_memory_count"], 1)

    async def test_workflow_accepts_session_memory_context_without_raw_text(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈已经生成。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            user_answer="RAW USER ANSWER SHOULD NOT LEAK",
            session_memory_context={
                "target_role": "AI Agent 工程师",
                "answered_question_ids": ["Q1"],
                "user_answer": "RAW SESSION ANSWER SHOULD NOT LEAK",
            },
        )

        payload = json.loads(result.output)
        payload_text = json.dumps(payload["data"], ensure_ascii=False)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["session_memory_context"]["target_role"], "AI Agent 工程师")
        self.assertEqual(payload["data"]["session_memory_context"]["answered_question_ids"], ["Q1"])
        self.assertNotIn("RAW USER ANSWER SHOULD NOT LEAK", payload_text)
        self.assertNotIn("RAW SESSION ANSWER SHOULD NOT LEAK", payload_text)

    async def test_select_question_uses_session_memory_to_avoid_answered_questions(self):
        tool = GitHubRepoInterviewWorkflowTool()

        result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="",
            session_memory_context={
                "answered_question_ids": ["Q1"],
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["selected_question"]["id"], "Q3")
        self.assertEqual(payload["data"]["session_memory_context"]["answered_question_ids"], ["Q1"])

    async def test_workflow_emits_session_memory_patch_after_summary(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": ["manifest:pyproject.toml"],
                "practice_notes": ["继续围绕 evidence 作答。"],
                "next_practice_suggestion": "继续练习证据引用。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": [],
                    "evidence_missed": [],
                },
            },
            session_memory_context={"target_role": "后端工程师"},
        )

        payload = json.loads(result.output)
        patch = payload["data"]["session_memory_patch"]
        self.assertTrue(result.success)
        self.assertEqual(patch["target_role"], "后端工程师")
        self.assertEqual(patch["answered_question_ids"], ["Q3"])
        self.assertEqual(patch["last_question_id"], "Q3")
        self.assertTrue(patch["summary_completed"])
        self.assertNotIn("user_answer 原文", result.output)

    async def test_full_workflow_chain_consumes_previous_stage_data(self):
        answer_engine = FakeAnswerCoachEngine(
            {
                "summary": "回答已经提到 manifest，但缺少入口验证。",
                "strengths": ["识别到了 pyproject.toml。"],
                "gaps": ["还需要说明 entrypoints/scripts。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "这条证据能支撑入口说明。",
                    }
                ],
                "suggested_answer_outline": ["先讲 manifest，再讲 entrypoint。"],
                "follow_up_questions": ["你会如何验证 entrypoint？"],
                "grounding_notes": ["仅基于提供的 evidence_details。"],
            }
        )
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml 中的 entrypoint？"],
                "feedback": ["追问回答仍基于 pyproject.toml。"],
                "grounding_notes": ["仅基于 allowed evidence。"],
            }
        )
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答和追问都围绕 pyproject.toml 展开。"],
                "next_practice_suggestion": "继续练习如何把 pyproject.toml 证据讲成工程取舍。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=answer_engine,
            follow_up_engine=follow_up_engine,
            summary_engine=summary_engine,
        )

        select_result = await tool.github_repo_interview_workflow(
            stage="select_question",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
        )
        select_payload = json.loads(select_result.output)
        self.assertTrue(select_result.success)
        self.assertEqual(select_payload["data"]["workflow"]["current_stage"], "question_selected")
        self.assertEqual(select_payload["data"]["selected_question"]["id"], "Q3")
        for forbidden in ("repo_metadata", "readme", "project_context_pack", "markdown"):
            self.assertNotIn(forbidden, select_payload["data"])

        answer_result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            user_answer="我会先从 pyproject.toml 解释依赖和入口点。",
            previous_workflow_state=select_payload["data"],
        )
        answer_payload = json.loads(answer_result.output)
        self.assertTrue(answer_result.success)
        self.assertEqual(answer_payload["data"]["workflow"]["current_stage"], "answer_coached")
        self.assertEqual(answer_payload["data"]["answer_feedback"]["summary"], "回答已经提到 manifest，但缺少入口验证。")
        self.assertIn("answer_quality_signals", answer_payload["data"])

        follow_up_result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml 里 scripts 或 entrypoints 的配置。",
            previous_workflow_state=answer_payload["data"],
        )
        follow_up_payload = json.loads(follow_up_result.output)
        self.assertTrue(follow_up_result.success)
        self.assertEqual(follow_up_payload["data"]["workflow"]["current_stage"], "follow_up_answered")
        self.assertEqual(follow_up_engine.requests[0]["answer_feedback"]["summary"], "回答已经提到 manifest，但缺少入口验证。")
        self.assertEqual(
            follow_up_engine.requests[0]["answer_feedback"]["evidence_missed"][0]["evidence_id"],
            "manifest:pyproject.toml",
        )
        self.assertEqual(follow_up_payload["data"]["follow_up"]["questions"], ["你会如何验证 pyproject.toml 中的 entrypoint？"])
        self.assertIn("answer_quality_signals", follow_up_payload["data"])

        summary_result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=full_slice_4_payload(),
            question_id="",
            previous_workflow_state=follow_up_payload["data"],
        )
        summary_payload = json.loads(summary_result.output)
        self.assertTrue(summary_result.success)
        self.assertEqual(summary_payload["data"]["workflow"]["current_stage"], "summary_ready")
        self.assertEqual(summary_engine.requests[0]["answer_feedback"]["summary"], "回答已经提到 manifest，但缺少入口验证。")
        self.assertEqual(summary_engine.requests[0]["follow_up"]["feedback"], ["追问回答仍基于 pyproject.toml。"])
        self.assertEqual(summary_payload["data"]["session_summary"]["covered_evidence"], ["manifest:pyproject.toml"])
        self.assertIn("answer_quality_signals", summary_payload["data"])
        self.assertNotIn("answer_feedback", summary_payload["data"])

        combined_request_text = str(answer_engine.requests + follow_up_engine.requests + summary_engine.requests)
        for request in (answer_engine.requests[0], follow_up_engine.requests[0], summary_engine.requests[0]):
            self.assertIn("repo_metadata", request["context_policy"]["hidden_sources"])
            self.assertIn("project_context_pack", request["context_policy"]["hidden_sources"])
        for forbidden in (
            "FULL README SHOULD NOT REACH WORKFLOW REQUEST",
            "github.com/pallets/flask",
            "full markdown should not be forwarded",
            "Unknown source evidence must not be forwarded",
        ):
            self.assertNotIn(forbidden, combined_request_text)

    async def test_workflow_tool_coach_answer_uses_selected_question_and_allowed_evidence_only(self):
        full_payload = {
            "tool": "github_repo_interview_prep",
            "data": {
                **sample_questions_pack(),
                "repo_metadata": {
                    "stars": 12345,
                    "html_url": "https://github.com/pallets/flask",
                },
                "readme": {
                    "text_excerpt": "FULL README SHOULD NOT REACH COACH REQUEST",
                },
                "project_context_pack": {
                    "repo_metadata": {
                        "description": "Full repository description must not be forwarded.",
                    }
                },
            },
        }
        engine = FakeAnswerCoachEngine(
            {
                "summary": "回答已经提到 manifest，但缺少入口验证。",
                "strengths": ["识别到了 pyproject.toml。"],
                "gaps": ["还需要说明 entrypoints/scripts。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "这条证据能支撑入口说明。",
                    }
                ],
                "suggested_answer_outline": ["先讲 manifest，再讲 entrypoint。"],
                "follow_up_questions": ["你会如何验证 entrypoint？"],
                "grounding_notes": ["仅基于提供的 evidence_details。"],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=full_payload,
            question_id="Q3",
            user_answer="我会从 pyproject.toml 解释依赖。",
            language="zh",
        )

        self.assertTrue(result.success)
        self.assertEqual(len(engine.requests), 1)
        request_text = str(engine.requests[0])
        self.assertIn("manifest:pyproject.toml", request_text)
        self.assertIn("我会从 pyproject.toml 解释依赖。", request_text)
        self.assertIn("project_context_pack", engine.requests[0]["context_policy"]["hidden_sources"])
        self.assertIn("repo_metadata", engine.requests[0]["context_policy"]["hidden_sources"])
        self.assertNotIn("FULL README", request_text)
        self.assertNotIn("12345", request_text)
        payload = json.loads(result.output)
        self.assertEqual(payload["tool"], "github_repo_interview_workflow")
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "answer_coached")
        self.assertEqual(payload["data"]["answer_feedback"]["evidence_missed"][0]["evidence_id"], "manifest:pyproject.toml")

    async def test_llm_stage_requests_include_role_contracts_without_full_payload(self):
        answer_engine = FakeAnswerCoachEngine(
            {
                "summary": "回答已经提到 manifest。",
                "strengths": ["识别到了 pyproject.toml。"],
                "gaps": ["需要补充 pyproject.toml。"],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": ["你会如何验证 pyproject.toml？"],
                "grounding_notes": ["仅基于 allowed evidence。"],
            }
        )
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": ["继续基于 pyproject.toml。"],
                "grounding_notes": [],
            }
        )
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=answer_engine,
            follow_up_engine=follow_up_engine,
            summary_engine=summary_engine,
        )

        answer_result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            user_answer="我会从 pyproject.toml 解释依赖。",
        )
        answer_payload = json.loads(answer_result.output)
        self.assertTrue(answer_result.success)

        follow_up_result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            follow_up_answer="我会继续检查 pyproject.toml。",
            previous_workflow_state=answer_payload["data"],
        )
        follow_up_payload = json.loads(follow_up_result.output)
        self.assertTrue(follow_up_result.success)

        summary_result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            previous_workflow_state=follow_up_payload["data"],
        )
        self.assertTrue(summary_result.success)

        self.assertEqual(answer_engine.requests[0]["role"]["id"], "answer_coach")
        self.assertEqual(follow_up_engine.requests[0]["role"]["id"], "follow_up_coach")
        self.assertEqual(summary_engine.requests[0]["role"]["id"], "session_summarizer")
        for request in (answer_engine.requests[0], follow_up_engine.requests[0], summary_engine.requests[0]):
            self.assertEqual(request["role"]["evidence_scope"], "selected_question.evidence_details")
            self.assertEqual(request["role"]["repository_access"], "no_new_repository_access")
            self.assertEqual(request["context_policy"]["repository_access"], "no_new_repository_access")
            self.assertIn("repo_metadata", request["context_policy"]["hidden_sources"])
            self.assertIn("readme", request["context_policy"]["hidden_sources"])
            self.assertIn("project_context_pack", request["context_policy"]["hidden_sources"])
            request_text = str(request)
            self.assertNotIn("FULL README SHOULD NOT REACH WORKFLOW REQUEST", request_text)
            self.assertNotIn("github.com/pallets/flask", request_text)

    async def test_llm_stage_requests_include_context_policy_without_full_payload(self):
        answer_engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈基于 pyproject.toml。",
                "strengths": [],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=answer_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            user_answer="我会从 pyproject.toml 解释依赖和入口。",
        )

        self.assertTrue(result.success)
        request = answer_engine.requests[0]
        self.assertEqual(request["context_policy"]["active_role"], "answer_coach")
        self.assertEqual(request["context_policy"]["repository_access"], "no_new_repository_access")
        self.assertEqual(request["context_policy"]["allowed_evidence_ids"], ["manifest:pyproject.toml"])

        request_text = str(request)
        self.assertIn("context_policy", request_text)
        self.assertIn("repo_metadata", request["context_policy"]["hidden_sources"])
        self.assertIn("project_context_pack", request["context_policy"]["hidden_sources"])
        self.assertNotIn("FULL README SHOULD NOT REACH WORKFLOW REQUEST", request_text)
        self.assertNotIn("github.com/pallets/flask", request_text)
        self.assertNotIn("Unknown source evidence must not be forwarded", request_text)

    async def test_follow_up_and_summarize_do_not_forward_polluted_previous_state(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": ["继续基于 pyproject.toml。"],
                "grounding_notes": [],
            }
        )
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(
            follow_up_engine=follow_up_engine,
            summary_engine=summary_engine,
        )
        polluted_previous_state = {
            "workflow": {"follow_up_count": 0},
            "answer_feedback": {
                "summary": "回答提到了 pyproject.toml。",
                "gaps": ["需要补充 pyproject.toml。"],
                "evidence_missed": [],
                "follow_up_questions": [],
            },
            "repo_metadata": {"stars": 9999, "html_url": "https://github.com/pallets/flask"},
            "readme": {"text_excerpt": "FULL README SHOULD NOT REACH FOLLOWUP REQUEST"},
            "project_context_pack": {"source_evidence": [{"path": "src/unknown.py"}]},
            "markdown": "full markdown should not be forwarded",
        }

        follow_up_result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            follow_up_answer="我会继续检查 pyproject.toml。",
            previous_workflow_state=polluted_previous_state,
        )
        self.assertTrue(follow_up_result.success)

        summary_previous_state = {
            **polluted_previous_state,
            "follow_up": {"feedback": ["追问回答仍基于 pyproject.toml。"]},
        }
        summary_result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=full_slice_4_payload(),
            question_id="Q3",
            previous_workflow_state=summary_previous_state,
        )
        self.assertTrue(summary_result.success)

        request_text = str(follow_up_engine.requests + summary_engine.requests)
        self.assertIn("pyproject.toml", request_text)
        for request in (follow_up_engine.requests[0], summary_engine.requests[0]):
            self.assertIn("repo_metadata", request["context_policy"]["hidden_sources"])
            self.assertIn("readme", request["context_policy"]["hidden_sources"])
            self.assertIn("project_context_pack", request["context_policy"]["hidden_sources"])
            self.assertIn("markdown", request["context_policy"]["hidden_sources"])
        for forbidden in (
            "FULL README",
            "9999",
            "github.com/pallets/flask",
            "src/unknown.py",
            "full markdown should not be forwarded",
        ):
            self.assertNotIn(forbidden, request_text)

    async def test_workflow_tool_truncates_long_user_answer_and_warns(self):
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
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            user_answer="答" * 4001,
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(len(engine.requests[0]["user_answer"]), 4000)
        self.assertEqual(payload["input"]["user_answer_excerpt"], "答" * 300)
        self.assertTrue(any(warning["code"] == "user_answer_truncated" for warning in payload["warnings"]))

    async def test_workflow_tool_falls_back_when_answer_feedback_references_unknown_evidence_id(self):
        engine = FakeAnswerCoachEngine(
            {
                "summary": "反馈引用了未知证据。",
                "strengths": [],
                "gaps": ["缺少有效证据引用。"],
                "evidence_missed": [
                    {
                        "evidence_id": "src:unknown.py#snippet-1",
                        "source_path": "unknown.py",
                        "reason": "invalid",
                    }
                ],
                "suggested_answer_outline": [],
                "follow_up_questions": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            user_answer="我会解释依赖。",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "answer_coached")
        self.assertEqual(
            payload["data"]["answer_feedback"]["evidence_missed"][0]["evidence_id"],
            "manifest:pyproject.toml",
        )
        self.assertTrue(any(warning["code"] == "answer_coach_fallback_used" for warning in payload["warnings"]))
        self.assertIn("answer_quality_signals", payload["data"])
        self.assertNotIn("src:unknown.py#snippet-1", str(payload["data"]["answer_quality_signals"]))
        self.assertNotIn("src:unknown.py#snippet-1", result.output)

    async def test_workflow_tool_uses_bounded_answer_fallback_when_coach_engine_fails(self):
        tool = GitHubRepoInterviewWorkflowTool(answer_coach_engine=RaisingWorkflowStageEngine())

        result = await tool.github_repo_interview_workflow(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            user_answer="我会解释分层边界。",
            language="zh",
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        feedback = payload["data"]["answer_feedback"]
        self.assertIn("受控兜底点评", feedback["summary"])
        self.assertEqual(feedback["evidence_missed"][0]["evidence_id"], "manifest:pyproject.toml")
        self.assertTrue(any(warning["code"] == "answer_coach_fallback_used" for warning in payload["warnings"]))
        self.assertNotIn("Answer coach feedback could not be generated", result.output)

    async def test_follow_up_engine_receives_filtered_feedback_without_hallucinated_paths(self):
        answer_engine = FakeAnswerCoachEngine({})
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml 中的 entrypoint？"],
                "feedback": ["继续基于 manifest 证据回答。"],
                "grounding_notes": ["仅基于 allowed evidence。"],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(
            answer_coach_engine=answer_engine,
            follow_up_engine=follow_up_engine,
        )
        previous_state = {
            "answer_feedback": {
                "summary": "提到了 pyproject.toml，但也幻觉引用了 unknown.py 和 https://example.com。",
                "gaps": [
                    "需要补充 pyproject.toml 的 entrypoint。",
                    "不要引用 unknown.py。",
                ],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "有效。",
                    },
                    {
                        "evidence_id": "src:unknown.py#snippet-1",
                        "source_path": "unknown.py",
                        "reason": "invalid",
                    },
                ],
                "follow_up_questions": [
                    "你会如何验证 pyproject.toml？",
                    "unknown.py 里还有什么？",
                ],
            }
        }

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml 的 scripts。",
            previous_workflow_state=previous_state,
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        request_text = str(follow_up_engine.requests[0])
        self.assertIn("pyproject.toml", request_text)
        self.assertNotIn("unknown.py", request_text)
        self.assertNotIn("https://example.com", request_text)
        self.assertNotIn("src:unknown.py#snippet-1", request_text)
        self.assertEqual(payload["data"]["follow_up"]["questions"], ["你会如何验证 pyproject.toml 中的 entrypoint？"])
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in payload["warnings"]))

    async def test_follow_up_request_includes_output_contract_to_reduce_fallback(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": ["继续基于 pyproject.toml。"],
                "grounding_notes": ["仅基于 pyproject.toml。"],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={
                "workflow": {"follow_up_count": 0},
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"]},
            },
        )

        self.assertTrue(result.success)
        request = follow_up_engine.requests[0]
        self.assertEqual(request["output_contract"]["format"], "json_object")
        self.assertEqual(request["output_contract"]["required_keys"], ["questions", "feedback", "grounding_notes"])
        self.assertIn("allowed_evidence_only", request["output_contract"]["rules"])
        self.assertIn("no_scores_or_pass_fail", request["output_contract"]["rules"])

    async def test_workflow_rejects_follow_up_beyond_max_follow_ups(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何继续？"],
                "feedback": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={
                "workflow": {"follow_up_count": 2},
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"]},
            },
            max_follow_ups=2,
        )

        payload = json.loads(result.output)
        self.assertFalse(result.success)
        self.assertEqual(payload["errors"][0]["code"], "follow_up_limit_reached")
        self.assertEqual(follow_up_engine.requests, [])

    async def test_follow_up_stage_returns_filtered_questions_and_increments_count(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": [
                    "你会如何验证 pyproject.toml 中的 entrypoint？",
                    "unknown.py 中还有哪些证据？",
                    "第二个合法问题仍然基于 pyproject.toml。",
                ],
                "feedback": [
                    "继续基于 pyproject.toml 回答。",
                    "不要使用 https://example.com 的信息。",
                ],
                "grounding_notes": ["仅基于 allowed evidence。"],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={
                "workflow": {"follow_up_count": 1},
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"]},
            },
            max_follow_ups=2,
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["workflow"]["follow_up_count"], 2)
        self.assertEqual(payload["data"]["follow_up"]["mode"], "answer_feedback")
        self.assertEqual(payload["data"]["follow_up"]["questions"], [
            "你会如何验证 pyproject.toml 中的 entrypoint？",
            "第二个合法问题仍然基于 pyproject.toml。",
        ])
        self.assertEqual(payload["data"]["follow_up"]["feedback"], ["继续基于 pyproject.toml 回答。"])
        self.assertEqual(
            payload["data"]["other_questions"],
            [
                {
                    "id": "Q1",
                    "category": "architecture",
                    "difficulty": "senior",
                    "question": "你会如何解释这个仓库的架构边界？",
                }
            ],
        )
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in payload["warnings"]))

    async def test_follow_up_stage_filters_grounding_notes_from_engine_response(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": ["继续基于 pyproject.toml。"],
                "grounding_notes": [
                    "仅基于 pyproject.toml。",
                    "不要引用 unknown.py。",
                    "不要使用 https://example.com。",
                ],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"]},
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["follow_up"]["grounding_notes"], ["仅基于 pyproject.toml。"])
        output_text = str(payload["data"]["follow_up"])
        self.assertNotIn("unknown.py", output_text)
        self.assertNotIn("https://example.com", output_text)
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in payload["warnings"]))

    async def test_follow_up_truncates_prior_feedback_reason(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={
                "answer_feedback": {
                    "evidence_missed": [
                        {
                            "evidence_id": "manifest:pyproject.toml",
                            "source_path": "pyproject.toml",
                            "reason": "理" * 1000,
                        }
                    ]
                }
            },
        )

        self.assertTrue(result.success)
        reason = follow_up_engine.requests[0]["answer_feedback"]["evidence_missed"][0]["reason"]
        self.assertEqual(reason, "理" * 300)

    async def test_summary_filters_unknown_paths_from_previous_follow_up_state(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答仍然基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml，但也幻觉引用了 https://example.com。",
                    "gaps": [
                        "需要补充 pyproject.toml。",
                        "不要讨论 unknown.py。",
                    ],
                    "evidence_missed": [
                        {
                            "evidence_id": "manifest:pyproject.toml",
                            "source_path": "pyproject.toml",
                            "reason": "有效。",
                        },
                        {
                            "evidence_id": "src:unknown.py#snippet-1",
                            "source_path": "unknown.py",
                            "reason": "invalid",
                        },
                    ],
                    "follow_up_questions": ["unknown.py 里还有什么？"],
                },
                "follow_up": {
                    "questions": [
                        "你会如何验证 pyproject.toml？",
                        "unknown.py 中有哪些证据？",
                    ],
                    "feedback": [
                        "追问回答仍基于 pyproject.toml。",
                        "还提到了 https://example.com。",
                    ],
                    "grounding_notes": ["仅基于 allowed evidence。"],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        request_text = str(summary_engine.requests[0])
        self.assertIn("pyproject.toml", request_text)
        self.assertIn("追问回答仍基于 pyproject.toml。", request_text)
        self.assertNotIn("unknown.py", request_text)
        self.assertNotIn("https://example.com", request_text)
        self.assertNotIn("src:unknown.py#snippet-1", request_text)
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in payload["warnings"]))

    async def test_missing_previous_feedback_degrades_to_empty_follow_up_request(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["你会如何验证 pyproject.toml？"],
                "feedback": [],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={"workflow": {"follow_up_count": 0}},
        )

        self.assertTrue(result.success)
        self.assertEqual(follow_up_engine.requests[0]["answer_feedback"]["gaps"], [])
        self.assertEqual(follow_up_engine.requests[0]["answer_feedback"]["follow_up_questions"], [])
        self.assertEqual(follow_up_engine.requests[0]["answer_feedback"]["evidence_missed"], [])
        payload = json.loads(result.output)
        self.assertNotIn("answer_quality_signals", payload["data"])

    async def test_follow_up_without_answer_returns_prompt_from_prior_feedback_without_llm(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": ["LLM should not be called."],
                "feedback": ["LLM should not be called."],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "workflow": {"follow_up_count": 0},
                "answer_feedback": {
                    "summary": "回答提到了 pyproject.toml。",
                    "gaps": ["需要补充 pyproject.toml 的 entrypoint。"],
                    "follow_up_questions": ["你会如何验证 pyproject.toml 中的 entrypoint？"],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(follow_up_engine.requests, [])
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "follow_up_ready")
        self.assertEqual(payload["data"]["workflow"]["active_role"], "follow_up_coach")
        self.assertEqual(payload["data"]["workflow"]["follow_up_count"], 0)
        self.assertEqual(payload["data"]["follow_up"]["mode"], "question_prompt")
        self.assertEqual(
            payload["data"]["follow_up"]["questions"],
            ["你会如何验证 pyproject.toml 中的 entrypoint？"],
        )
        self.assertEqual(payload["data"]["follow_up"]["feedback"], [])
        self.assertIn("follow_up_answer", payload["next_step"])

    async def test_follow_up_without_answer_uses_selected_evidence_fallback_question(self):
        follow_up_engine = FakeAnswerCoachEngine({})
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "workflow": {"follow_up_count": 0},
                "answer_feedback": {
                    "summary": "回答较短。",
                    "gaps": [],
                    "follow_up_questions": [],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(follow_up_engine.requests, [])
        self.assertEqual(payload["data"]["follow_up"]["mode"], "question_prompt")
        self.assertEqual(len(payload["data"]["follow_up"]["questions"]), 1)
        self.assertIn("pyproject.toml", payload["data"]["follow_up"]["questions"][0])
        self.assertNotIn("unknown.py", str(payload["data"]["follow_up"]))
        self.assertTrue(
            any(warning["code"] == "follow_up_question_fallback_used" for warning in payload["warnings"])
        )

    async def test_follow_up_without_answer_does_not_call_raising_engine(self):
        follow_up_engine = RaisingWorkflowStageEngine()
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "workflow": {"follow_up_count": 0},
                "answer_feedback": {
                    "follow_up_questions": ["你会如何验证 pyproject.toml？"],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(follow_up_engine.requests, [])
        self.assertEqual(payload["data"]["follow_up"]["questions"], ["你会如何验证 pyproject.toml？"])

    async def test_follow_up_answer_uses_safe_fallback_when_engine_fails(self):
        follow_up_engine = RaisingWorkflowStageEngine()
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml 的 scripts 配置。",
            previous_workflow_state={
                "workflow": {"follow_up_count": 0},
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"], "follow_up_questions": []},
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(len(follow_up_engine.requests), 1)
        self.assertEqual(payload["data"]["workflow"]["follow_up_count"], 1)
        self.assertEqual(payload["data"]["follow_up"]["mode"], "answer_feedback_fallback")
        self.assertIn("pyproject.toml", str(payload["data"]["follow_up"]))
        self.assertNotIn("LLM unavailable", result.output)
        self.assertTrue(
            any(warning["code"] == "follow_up_feedback_fallback_used" for warning in payload["warnings"])
        )

    async def test_follow_up_answer_fallback_reflects_validation_terms_without_raw_answer(self):
        follow_up_engine = RaisingWorkflowStageEngine()
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)
        follow_up_answer = (
            "我会看 src/index.ts 是否只负责 createProgram、parse 参数和启动 CLI，"
            "再写集成测试，mock application 层方法。"
        )

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer=follow_up_answer,
            previous_workflow_state={
                "workflow": {"follow_up_count": 1},
                "answer_feedback": {"gaps": ["需要补充 pyproject.toml。"], "follow_up_questions": []},
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        feedback_text = "\n".join(payload["data"]["follow_up"]["feedback"])
        question_text = "\n".join(payload["data"]["follow_up"]["questions"])
        self.assertIn("CLI", feedback_text)
        self.assertIn("集成测试", feedback_text)
        self.assertIn("mock", feedback_text)
        self.assertIn("失败", question_text)
        self.assertIn("application", question_text)
        self.assertNotIn("围绕 pyproject.toml，你会用什么具体验证来证明这个判断？", question_text)
        self.assertNotIn("下一版请继续锚定", feedback_text)
        self.assertNotIn(follow_up_answer, result.output)

    async def test_missing_previous_follow_up_degrades_to_empty_summary_request(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "gaps": ["需要补充 pyproject.toml。"],
                    "follow_up_questions": [],
                    "evidence_missed": [],
                }
            },
        )

        self.assertTrue(result.success)
        self.assertEqual(summary_engine.requests[0]["follow_up"]["questions"], [])
        self.assertEqual(summary_engine.requests[0]["follow_up"]["feedback"], [])
        self.assertEqual(summary_engine.requests[0]["follow_up"]["grounding_notes"], [])
        self.assertEqual(summary_engine.requests[0]["answer_feedback"]["gaps"], ["需要补充 pyproject.toml。"])

    async def test_follow_up_discards_scoring_output_and_returns_safe_fallback(self):
        follow_up_engine = FakeAnswerCoachEngine(
            {
                "questions": [],
                "feedback": ["这轮回答得分 80，应该通过。"],
                "grounding_notes": [],
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(follow_up_engine=follow_up_engine)

        result = await tool.github_repo_interview_workflow(
            stage="coach_follow_up",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            follow_up_answer="我会检查 pyproject.toml。",
            previous_workflow_state={"answer_feedback": {"gaps": ["需要补充 pyproject.toml。"]}},
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["follow_up"]["mode"], "answer_feedback_fallback")
        self.assertNotIn("得分", result.output)
        self.assertNotIn("通过", result.output)
        self.assertTrue(
            any(warning["code"] == "follow_up_feedback_fallback_used" for warning in payload["warnings"])
        )

    async def test_summary_marks_follow_up_incomplete_when_only_question_prompt_exists(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": [],
                    "evidence_missed": [],
                    "follow_up_questions": ["你会如何验证 pyproject.toml？"],
                },
                "follow_up": {
                    "mode": "question_prompt",
                    "questions": ["你会如何验证 pyproject.toml？"],
                    "feedback": [],
                    "grounding_notes": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertFalse(payload["data"]["session_summary"]["workflow_completion"]["follow_up_completed"])
        self.assertEqual(
            payload["data"]["session_summary"]["workflow_completion"]["summary_scope"],
            "answer_feedback_only",
        )
        self.assertTrue(
            any(warning["code"] == "follow_up_not_completed" for warning in payload["warnings"])
        )
        self.assertNotIn("all stages completed", payload["next_step"].lower())

    async def test_summary_marks_follow_up_complete_when_feedback_exists(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答和追问都基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": [],
                    "evidence_missed": [],
                },
                "follow_up": {
                    "mode": "answer_feedback",
                    "questions": ["你会如何继续验证？"],
                    "feedback": ["追问回答仍基于 pyproject.toml。"],
                    "grounding_notes": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertTrue(payload["data"]["session_summary"]["workflow_completion"]["follow_up_completed"])
        self.assertEqual(
            payload["data"]["session_summary"]["workflow_completion"]["summary_scope"],
            "answer_and_follow_up",
        )
        self.assertNotIn("workflow_completion", summary_engine.requests[0])

    async def test_summary_accepts_previous_tool_payload_wrapper(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["回答和追问都基于 pyproject.toml。"],
                "next_practice_suggestion": "继续练习 evidence grounding。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "tool": "github_repo_interview_workflow",
                "type": "github_repo_interview_workflow",
                "status": "success",
                "input": {"stage": "coach_follow_up", "question_id": "Q3"},
                "data": {
                    "answer_feedback": {
                        "summary": "回答覆盖了 pyproject.toml。",
                        "gaps": [],
                        "evidence_missed": [],
                    },
                    "follow_up": {
                        "mode": "answer_feedback",
                        "questions": ["你会如何继续验证？"],
                        "feedback": ["追问回答仍基于 pyproject.toml。"],
                        "grounding_notes": [],
                    },
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(summary_engine.requests[0]["answer_feedback"]["summary"], "回答覆盖了 pyproject.toml。")
        self.assertEqual(summary_engine.requests[0]["follow_up"]["feedback"], ["追问回答仍基于 pyproject.toml。"])
        self.assertTrue(payload["data"]["session_summary"]["workflow_completion"]["answer_coached"])
        self.assertTrue(payload["data"]["session_summary"]["workflow_completion"]["follow_up_completed"])

    async def test_summary_request_includes_session_practice_history_without_raw_answers(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["整轮总结覆盖了 Q1 和 Q3。"],
                "next_practice_suggestion": "继续练习把证据讲成验证步骤。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "selected_question": {"id": "Q3", "question": "解释 pyproject.toml 的工程化取舍。"},
                "workflow": {
                    "practice_history": [
                        {
                            "question_id": "Q1",
                            "question": "解释 miniclawd 的架构边界。",
                            "answer_feedback": {"summary": "Q1 回答覆盖了架构边界。"},
                        },
                        {
                            "question_id": "Q3",
                            "question": "解释 pyproject.toml 的工程化取舍。",
                            "answer_feedback": {"summary": "Q3 回答覆盖了工程化取舍。"},
                        },
                    ],
                    "answered_question_ids": ["Q1", "Q3"],
                },
                "answer_feedback": {
                    "summary": "Q3 回答覆盖了工程化取舍。",
                    "gaps": [],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        request_history = summary_engine.requests[0]["practice_history"]
        self.assertEqual([item["question_id"] for item in request_history], ["Q1", "Q3"])
        self.assertEqual(request_history[0]["answer_feedback"]["summary"], "Q1 回答覆盖了架构边界。")
        self.assertNotIn("user_answer", str(request_history))
        self.assertEqual(
            payload["data"]["session_summary"]["workflow_completion"]["answered_question_ids"],
            ["Q1", "Q3"],
        )

    async def test_summary_uses_demo_relaxed_output_when_filtered_output_is_empty(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["src:unknown.py#snippet-1"],
                "missed_evidence": [],
                "practice_notes": ["不要提 unknown.py。"],
                "next_practice_suggestion": "",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml 的工程化证据。",
                    "gaps": ["需要补一个验证步骤。"],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        summary = payload["data"]["session_summary"]
        self.assertEqual(summary["covered_evidence"], [])
        self.assertEqual(summary["missed_evidence"], [])
        self.assertEqual(summary["practice_notes"], ["不要提 unknown.py。"])
        self.assertEqual(summary["next_practice_suggestion"], "继续选择下一题练习。")
        self.assertTrue(summary["demo_relaxed_validation"])
        self.assertTrue(any(warning["code"] == "summary_demo_relaxed_validation_used" for warning in payload["warnings"]))
        self.assertFalse(any(warning["code"] == "summary_fallback_used" for warning in payload["warnings"]))

    async def test_summary_does_not_retry_when_demo_relaxed_output_has_content(self):
        summary_engine = SequenceAnswerCoachEngine(
            [
                {
                    "covered_evidence": ["src:unknown.py#snippet-1"],
                    "missed_evidence": [],
                    "practice_notes": ["不要提 unknown.py。"],
                    "next_practice_suggestion": "",
                },
                {
                    "covered_evidence": ["manifest:pyproject.toml"],
                    "missed_evidence": [],
                    "practice_notes": ["第二次输出只使用允许证据。"],
                    "next_practice_suggestion": "继续练习 evidence grounding。",
                },
            ]
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml 的工程化证据。",
                    "gaps": [],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(len(summary_engine.requests), 1)
        summary = payload["data"]["session_summary"]
        self.assertEqual(summary["covered_evidence"], [])
        self.assertEqual(summary["practice_notes"], ["不要提 unknown.py。"])
        self.assertTrue(summary["demo_relaxed_validation"])
        self.assertFalse(any(warning["code"] == "summary_fallback_used" for warning in payload["warnings"]))
        self.assertFalse(any(warning["code"] == "summary_retry_used" for warning in payload["warnings"]))
        self.assertTrue(any(warning["code"] == "summary_demo_relaxed_validation_used" for warning in payload["warnings"]))

    async def test_summary_accepts_scoring_or_ranking_output_in_demo_relaxed_mode(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml"],
                "missed_evidence": [],
                "practice_notes": ["你的回答排名较低。"],
                "next_practice_suggestion": "先练简单题。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": [],
                    "evidence_missed": [],
                },
                "follow_up": {
                    "feedback": ["追问回答仍基于 pyproject.toml。"],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        summary = payload["data"]["session_summary"]
        self.assertEqual(summary["practice_notes"], ["你的回答排名较低。"])
        self.assertEqual(summary["next_practice_suggestion"], "先练简单题。")
        self.assertTrue(summary["demo_relaxed_validation"])
        self.assertTrue(any(warning["code"] == "summary_demo_relaxed_validation_used" for warning in payload["warnings"]))

    async def test_summary_accepts_plain_text_output_in_demo_relaxed_mode(self):
        summary_engine = FakeAnswerCoachEngine("这一轮练习已经完成，整体回答能展示主要架构理解。")
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": [],
                    "evidence_missed": [],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        summary = payload["data"]["session_summary"]
        self.assertEqual(summary["practice_notes"], ["这一轮练习已经完成，整体回答能展示主要架构理解。"])
        self.assertTrue(summary["demo_relaxed_validation"])
        self.assertTrue(any(warning["code"] == "summary_demo_relaxed_validation_used" for warning in payload["warnings"]))

    async def test_summarize_stage_returns_filtered_summary(self):
        summary_engine = FakeAnswerCoachEngine(
            {
                "covered_evidence": ["manifest:pyproject.toml", "src:unknown.py#snippet-1"],
                "missed_evidence": ["manifest:pyproject.toml", "readme:unknown"],
                "practice_notes": [
                    "回答已经围绕 pyproject.toml 展开。",
                    "不要补充 unknown.py 中不存在的细节。",
                ],
                "next_practice_suggestion": "继续练习如何把 pyproject.toml 证据讲成架构取舍。",
            }
        )
        tool = GitHubRepoInterviewWorkflowTool(summary_engine=summary_engine)

        result = await tool.github_repo_interview_workflow(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            previous_workflow_state={
                "answer_feedback": {
                    "summary": "回答覆盖了 pyproject.toml。",
                    "gaps": ["需要补充 pyproject.toml。"],
                    "evidence_missed": [],
                },
                "follow_up": {
                    "feedback": ["追问回答仍基于 pyproject.toml。"],
                },
            },
        )

        payload = json.loads(result.output)
        self.assertTrue(result.success)
        self.assertEqual(payload["data"]["workflow"]["current_stage"], "summary_ready")
        self.assertEqual(payload["data"]["session_summary"]["covered_evidence"], ["manifest:pyproject.toml"])
        self.assertEqual(payload["data"]["session_summary"]["missed_evidence"], ["manifest:pyproject.toml"])
        self.assertEqual(payload["data"]["session_summary"]["practice_notes"], ["回答已经围绕 pyproject.toml 展开。"])
        self.assertIn("next_practice_suggestion", payload["data"]["session_summary"])
        self.assertIn("answer_quality_signals", payload["data"])
        summary_signals = {signal["id"]: signal for signal in payload["data"]["answer_quality_signals"]}
        self.assertEqual(summary_signals["completeness_missing_evidence"]["status"], "needs_attention")
        self.assertEqual(summary_signals["completeness_missing_evidence"]["evidence_refs"], ["manifest:pyproject.toml"])
        self.assertNotIn("answer_feedback", payload["data"])
        for signal in payload["data"]["answer_quality_signals"]:
            self.assertFalse(
                any(field.startswith("answer_feedback") for field in signal["basis_fields"]),
                f"summary signal {signal['id']} should not point at hidden answer_feedback fields",
            )
        self.assertTrue(any(warning["code"] == "filtered_hallucinated_references" for warning in payload["warnings"]))


class FakeThreadManager:
    def __init__(self):
        self.registered = []

    def add_tool(self, tool_class, **kwargs):
        self.registered.append((tool_class, kwargs))


class GitHubRepoInterviewWorkflowRoutingHintTest(unittest.TestCase):
    def test_workflow_tool_usage_example_routes_chinese_answers_to_coach_answer(self):
        tool = GitHubRepoInterviewWorkflowTool()
        schemas = tool.get_schemas().get("github_repo_interview_workflow", [])
        examples = [
            getattr(schema, "schema", {}).get("example", "")
            for schema in schemas
            if getattr(getattr(schema, "schema_type", None), "value", "") == "usage_example"
        ]
        combined = "\n".join(examples)

        self.assertIn("github_repo_interview_workflow", combined)
        self.assertIn("coach_answer", combined)
        self.assertIn("prep_questions_pack", combined)
        self.assertIn("previous_workflow_state", combined)
        self.assertIn("第 X 题答案", combined)
        self.assertIn("QX 答案", combined)
        self.assertIn("点评我的回答", combined)
        self.assertIn("不要重新读取 GitHub", combined)
        self.assertNotIn("github_repo_answer_coach", combined)


class GitHubRepoInterviewWorkflowRegistrationTest(unittest.TestCase):
    def test_internal_memory_loader_is_not_exposed_as_a_model_tool(self):
        fake_thread_manager = FakeThreadManager()
        memory_context_loader = AsyncMock()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
            workflow_memory_context_loader=memory_context_loader,
        )

        manager.register_all_tools()

        workflow_class, workflow_kwargs = next(
            registration
            for registration in fake_thread_manager.registered
            if registration[0] is GitHubRepoInterviewWorkflowTool
        )
        workflow_tool = workflow_class(**workflow_kwargs)
        public_callables = {
            name
            for name in dir(workflow_tool)
            if not name.startswith("_") and callable(getattr(workflow_tool, name))
        }
        self.assertNotIn("memory_context_loader", public_callables)

    def test_tool_manager_registers_workflow_tool_without_high_risk_tools(self):
        fake_thread_manager = FakeThreadManager()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
        )

        manager.register_all_tools()

        registered_names = [tool_class.__name__ for tool_class, _kwargs in fake_thread_manager.registered]
        self.assertIn("GitHubRepoInterviewWorkflowTool", registered_names)
        high_risk_names = [
            name
            for name in registered_names
            if any(token in name for token in ("Sandbox", "WebSearch", "Files", "Browser", "Deploy", "Mcp", "MCP"))
        ]
        self.assertEqual(high_risk_names, [])

    def test_tool_manager_passes_current_model_to_workflow_engines(self):
        fake_thread_manager = FakeThreadManager()
        memory_context_loader = AsyncMock()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
            model_name="deepseek/deepseek-v4-flash",
            workflow_memory_context_loader=memory_context_loader,
        )

        manager.register_all_tools()

        workflow_registration = next(
            kwargs
            for tool_class, kwargs in fake_thread_manager.registered
            if tool_class is GitHubRepoInterviewWorkflowTool
        )
        self.assertEqual(workflow_registration["answer_coach_engine"].model_name, "deepseek/deepseek-v4-flash")
        self.assertIsInstance(workflow_registration["follow_up_engine"], LLMWorkflowStageEngine)
        self.assertIsInstance(workflow_registration["summary_engine"], LLMWorkflowStageEngine)
        self.assertEqual(workflow_registration["follow_up_engine"].model_name, "deepseek/deepseek-v4-flash")
        self.assertEqual(workflow_registration["summary_engine"].model_name, "deepseek/deepseek-v4-flash")
        self.assertIs(workflow_registration["memory_context_loader"], memory_context_loader)

if __name__ == "__main__":
    unittest.main()
