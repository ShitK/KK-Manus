import unittest

from agent.tools.github_repo_interview_workflow import build_workflow_state
from agent.tools.github_repo_interview_workflow_snapshot import (
    attach_context_snapshot,
    build_context_snapshot,
    build_memory_candidates,
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
                "snippet": "FULL SNIPPET SHOULD NOT REACH SNAPSHOT",
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


class GitHubRepoInterviewWorkflowSnapshotTest(unittest.TestCase):
    def test_context_snapshot_is_request_level_and_redacted(self):
        state = build_workflow_state(
            stage="coach_answer",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "summary": "用户回答原文 SECRET_ANSWER 不应进入 snapshot。",
                "gaps": ["需要补充架构取舍。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "missing evidence",
                    }
                ],
            },
            "follow_up": {
                "mode": "question_prompt",
                "feedback": [],
            },
        }
        snapshot = build_context_snapshot(
            state,
            data,
            {
                "stage": "coach_answer",
                "language": "zh",
                "coach_style": "direct",
                "user_answer_excerpt": "SECRET_ANSWER",
            },
        )

        self.assertEqual(snapshot["version"], "v1")
        self.assertEqual(snapshot["scope"], "request")
        self.assertEqual(snapshot["persistence"], "not_persisted")
        self.assertEqual(snapshot["current_stage"], "answer_coached")
        self.assertEqual(snapshot["active_role"], "answer_coach")
        self.assertEqual(snapshot["repository_access"], "no_new_repository_access")
        self.assertEqual(snapshot["tool_access"], "none")
        self.assertFalse(snapshot["persists_user_answer"])
        self.assertEqual(snapshot["allowed_evidence_ids"], ["manifest:pyproject.toml"])
        self.assertEqual(snapshot["allowed_source_paths"], ["pyproject.toml"])
        self.assertIn("project_context_pack", snapshot["hidden_sources"])
        self.assertNotIn("user_answer", snapshot["visible_sources"])
        self.assertNotIn("follow_up_answer", snapshot["visible_sources"])
        self.assertTrue(snapshot["answer_state"]["has_answer_feedback"])
        self.assertFalse(snapshot["answer_state"]["has_follow_up_feedback"])
        self.assertEqual(snapshot["answer_state"]["follow_up_mode"], "question_prompt")
        self.assertFalse(snapshot["redaction_policy"]["includes_user_answer"])
        self.assertFalse(snapshot["redaction_policy"]["includes_follow_up_answer"])
        self.assertFalse(snapshot["redaction_policy"]["includes_hidden_source_content"])
        self.assertFalse(snapshot["redaction_policy"]["includes_repo_evidence_text"])

        snapshot_text = str(snapshot)
        self.assertNotIn("SECRET_ANSWER", snapshot_text)
        self.assertNotIn("FULL SNIPPET SHOULD NOT REACH SNAPSHOT", snapshot_text)
        self.assertNotIn("python manifest with 6 detected dependencies", snapshot_text)

    def test_memory_candidates_are_candidate_only_and_do_not_include_answer_text(self):
        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "gaps": ["需要补充架构取舍和测试验证。"],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "SECRET_ANSWER should not appear",
                    }
                ],
            },
            "session_summary": {
                "missed_evidence": ["manifest:pyproject.toml"],
                "practice_notes": ["用户回答原文 SECRET_ANSWER 不应进入 candidate。"],
                "workflow_completion": {
                    "answer_coached": True,
                    "follow_up_completed": False,
                    "summary_scope": "answer_feedback_only",
                },
            },
        }
        candidates = build_memory_candidates(
            state,
            data,
            {
                "stage": "summarize",
                "language": "zh",
                "coach_style": "direct",
                "user_answer_excerpt": "SECRET_ANSWER",
            },
        )

        candidate_ids = {candidate["id"] for candidate in candidates}
        self.assertIn("language_preference_hint:zh", candidate_ids)
        self.assertIn("feedback_preference_hint:direct", candidate_ids)
        self.assertIn("recent_practice_category:dependency and packaging", candidate_ids)
        self.assertIn("practice_weakness_tag:missing_evidence", candidate_ids)
        self.assertIn("practice_weakness_tag:weak_architecture_tradeoff", candidate_ids)
        self.assertIn("practice_weakness_tag:unclear_testing_story", candidate_ids)

        for candidate in candidates:
            self.assertTrue(candidate["requires_user_confirmation"])
            self.assertEqual(candidate["status"], "candidate_only")
            self.assertFalse(candidate["persisted"])
            self.assertFalse(candidate["privacy"]["includes_user_answer"])
            self.assertFalse(candidate["privacy"]["includes_follow_up_answer"])
            self.assertFalse(candidate["privacy"]["includes_repo_evidence_text"])

        self.assertNotIn("SECRET_ANSWER", str(candidates))

    def test_attach_context_snapshot_returns_new_data_without_mutating_input(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }

        enriched = attach_context_snapshot(
            data,
            {"stage": "select_question", "language": "zh", "coach_style": "concise"},
        )

        self.assertNotIn("context_snapshot", data)
        self.assertIn("context_snapshot", enriched)
        self.assertIn("memory_candidates", enriched)
        self.assertEqual(enriched["context_snapshot"]["scope"], "request")

    def test_context_snapshot_includes_saved_memory_source_when_present(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }
        data["saved_memory_context"] = [
            {
                "id": "m1",
                "type": "language_preference_hint",
                "value": "zh",
                "label": "本次请求的候选语言偏好。",
                "source_stage": "coach_answer",
                "source_fields": ["input.language"],
                "persisted": True,
            }
        ]

        snapshot = build_context_snapshot(
            state,
            data,
            {"stage": "select_question", "language": "zh", "coach_style": "concise"},
        )

        self.assertIn("saved_memories", snapshot["visible_sources"])
        self.assertEqual(snapshot["saved_memory_count"], 1)
        self.assertNotIn("SECRET_ANSWER", str(snapshot))

    def test_context_snapshot_includes_session_memory_counts_only(self):
        state = build_workflow_state(
            stage="select_question",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }
        data["session_memory_context"] = {
            "target_role": "AI Agent 工程师",
            "answered_question_ids": ["Q1", "Q2"],
            "missed_evidence_ids": ["manifest:pyproject.toml"],
            "user_answer": "SECRET_ANSWER",
        }

        snapshot = build_context_snapshot(
            state,
            data,
            {"stage": "select_question", "language": "zh", "coach_style": "concise"},
        )

        self.assertIn("session_memory", snapshot["visible_sources"])
        self.assertEqual(
            snapshot["session_memory"],
            {
                "has_target_role": True,
                "answered_question_count": 2,
                "missed_evidence_count": 1,
            },
        )
        self.assertNotIn("SECRET_ANSWER", str(snapshot))

    def test_memory_candidates_drop_polluted_stage_and_category(self):
        question = {
            **sample_question(),
            "category": "SECRET_ANSWER https://github.com/example/repo 通过排名",
        }
        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack={"interview_questions": [question]},
            question_id="Q3",
            language="zh",
        )
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "missing evidence",
                    }
                ],
            },
        }

        candidates = build_memory_candidates(
            state,
            data,
            {
                "stage": "SECRET_ANSWER https://github.com/example/repo",
                "language": "zh",
                "coach_style": "direct",
            },
        )

        candidate_text = str(candidates)
        candidate_types = {candidate["type"] for candidate in candidates}
        self.assertNotIn("recent_practice_category", candidate_types)
        self.assertNotIn("SECRET_ANSWER", candidate_text)
        self.assertNotIn("https://github.com/example/repo", candidate_text)
        self.assertNotIn("通过排名", candidate_text)
        self.assertTrue({candidate["source_stage"] for candidate in candidates} <= {"summarize"})

    def test_memory_candidates_do_not_emit_text_from_feedback_gaps(self):
        state = build_workflow_state(
            stage="summarize",
            prep_questions_pack=sample_questions_pack(),
            question_id="Q3",
            language="zh",
        )
        data = {
            **{
                key: value
                for key, value in state.items()
                if key not in {"status", "partial", "warnings", "errors"}
            },
            "answer_feedback": {
                "gaps": ["SECRET_ANSWER should not appear, but architecture tradeoff should tag."],
            },
        }

        candidates = build_memory_candidates(
            state,
            data,
            {
                "stage": "summarize",
                "language": "zh",
                "coach_style": "direct",
            },
        )

        candidate_ids = {candidate["id"] for candidate in candidates}
        self.assertIn("practice_weakness_tag:weak_architecture_tradeoff", candidate_ids)
        self.assertNotIn("SECRET_ANSWER", str(candidates))


if __name__ == "__main__":
    unittest.main()
