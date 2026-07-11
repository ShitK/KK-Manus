import unittest

from agent.tools.github_repo_interview_multi_agent_trace import build_multi_agent_trace
from agent.tools.github_repo_interview_workflow import build_workflow_state


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
        "interview_questions": [sample_question()],
        "question_generation_summary": {
            "strategy": "deterministic_evidence_templates",
            "generated_count": 1,
            "has_evidence_details": True,
        },
    }


def workflow_state(stage="coach_answer"):
    return build_workflow_state(
        stage=stage,
        prep_questions_pack=sample_questions_pack(),
        question_id="Q3",
        language="zh",
    )


class GitHubRepoInterviewMultiAgentTraceTest(unittest.TestCase):
    def test_build_multi_agent_trace_describes_controlled_agent_chain(self):
        state = workflow_state()
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "summary": "回答提到了 pyproject.toml。",
                "strengths": ["能结合 manifest 说明依赖。"],
                "gaps": [],
                "evidence_missed": [],
                "suggested_answer_outline": [],
                "follow_up_questions": ["你会如何验证 entrypoint？"],
                "grounding_notes": ["仅基于 manifest:pyproject.toml。"],
            },
            "context_snapshot": {
                "repository_access": "no_new_repository_access",
                "tool_access": "none",
                "persists_user_answer": False,
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_hidden_source_content": False,
                    "includes_repo_evidence_text": False,
                },
            },
        }

        trace = build_multi_agent_trace(state, data, {"stage": "coach_answer"}, [], [])

        self.assertEqual(trace["version"], "v1")
        self.assertEqual(trace["mode"], "controlled_local_trace")
        self.assertEqual(trace["scope"], "request")
        self.assertEqual(trace["orchestrator"]["name"], "MainAgent")
        self.assertEqual(
            [agent["id"] for agent in trace["agents"]],
            ["repository_analyst", "interview_question", "answer_coach", "quality_reviewer"],
        )
        answer_agent = next(agent for agent in trace["agents"] if agent["id"] == "answer_coach")
        quality_agent = next(agent for agent in trace["agents"] if agent["id"] == "quality_reviewer")
        self.assertTrue(answer_agent["reads_user_answer"])
        self.assertFalse(quality_agent["reads_user_answer"])
        for agent in trace["agents"]:
            self.assertIn("input_sources", agent)
            self.assertIn("visible_context", agent)
            self.assertIn("forbidden_scope", agent)
            self.assertFalse(agent["persists_memory"])

    def test_trace_redacts_raw_answer_and_hidden_repo_payload(self):
        state = workflow_state()
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "summary": "SECRET_ANSWER should not be copied into trace.",
                "gaps": ["unknown.py should not survive."],
                "evidence_missed": [],
            },
            "context_snapshot": {
                "repository_access": "no_new_repository_access",
                "tool_access": "none",
                "persists_user_answer": False,
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_hidden_source_content": False,
                    "includes_repo_evidence_text": False,
                },
            },
            "repo_metadata": {"html_url": "https://github.com/pallets/flask"},
            "readme": {"text_excerpt": "FULL README SHOULD NOT REACH TRACE"},
            "project_context_pack": {"summary": "FULL CONTEXT SHOULD NOT REACH TRACE"},
            "markdown": "FULL MARKDOWN SHOULD NOT REACH TRACE",
        }

        trace = build_multi_agent_trace(
            state,
            data,
            {"stage": "coach_answer", "user_answer_excerpt": "SECRET_ANSWER"},
            [],
            [],
        )
        trace_text = str(trace)

        self.assertNotIn("SECRET_ANSWER", trace_text)
        self.assertNotIn("unknown.py", trace_text)
        self.assertNotIn("github.com/pallets/flask", trace_text)
        self.assertNotIn("FULL README SHOULD NOT REACH TRACE", trace_text)
        self.assertNotIn("FULL CONTEXT SHOULD NOT REACH TRACE", trace_text)
        self.assertNotIn("FULL MARKDOWN SHOULD NOT REACH TRACE", trace_text)

    def test_quality_signals_are_diagnostic_and_deterministic(self):
        state = workflow_state()
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "summary": "回答提到了 allowed evidence。",
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "需要补充 entrypoint。",
                    }
                ],
            },
            "context_snapshot": {
                "repository_access": "no_new_repository_access",
                "tool_access": "none",
                "persists_user_answer": False,
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_hidden_source_content": False,
                    "includes_repo_evidence_text": False,
                },
            },
        }
        warnings = [{"code": "filtered_hallucinated_references", "message": "filtered"}]

        trace = build_multi_agent_trace(state, data, {"stage": "coach_answer"}, warnings, [])

        self.assertEqual(trace["quality_signals"]["coverage"], "partial")
        self.assertEqual(trace["quality_signals"]["evidence_grounding"], "partial")
        self.assertEqual(trace["quality_signals"]["boundary_health"], "warning")
        self.assertEqual(trace["quality_signals"]["recommended_next_step"], "revise_with_evidence")
        self.assertNotIn("score", str(trace["quality_signals"]).lower())
        self.assertNotIn("pass", str(trace["quality_signals"]).lower())
        self.assertNotIn("rating", str(trace["quality_signals"]).lower())

    def test_question_selected_trace_recommends_answer_question(self):
        state = workflow_state(stage="select_question")
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }

        trace = build_multi_agent_trace(state, data, {"stage": "select_question"}, [], [])

        self.assertEqual(trace["quality_signals"]["coverage"], "not_started")
        self.assertEqual(trace["quality_signals"]["evidence_grounding"], "grounded")
        self.assertEqual(trace["quality_signals"]["boundary_health"], "clean")
        self.assertEqual(trace["quality_signals"]["recommended_next_step"], "answer_question")

    def test_invalid_question_evidence_downgrades_grounding(self):
        state = workflow_state()
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }
        errors = [{"code": "invalid_question_evidence", "message": "missing evidence"}]

        trace = build_multi_agent_trace(state, data, {"stage": "coach_answer"}, [], errors)

        self.assertEqual(trace["quality_signals"]["evidence_grounding"], "partial")
        self.assertEqual(trace["quality_signals"]["recommended_next_step"], "select_another_question")

    def test_trace_output_summaries_are_chinese_display_text(self):
        state = workflow_state()
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }

        trace = build_multi_agent_trace(state, data, {"stage": "coach_answer"}, [], [])
        summaries = " ".join(agent["output_summary"] for agent in trace["agents"])

        self.assertNotIn("allowlisted evidence", summaries)
        self.assertNotIn("metadata", summaries)
        self.assertIn("允许范围内的证据", summaries)


if __name__ == "__main__":
    unittest.main()
