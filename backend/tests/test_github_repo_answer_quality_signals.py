import unittest

from agent.tools.github_repo_answer_quality_signals import build_answer_quality_signals


class AnswerQualitySignalsTest(unittest.TestCase):
    def test_builds_missing_evidence_and_grounding_signals(self):
        data = {
            "selected_question": {"id": "q1", "question": "How is testing wired?"},
            "evidence_policy": {"allowed_evidence_ids": ["manifest:pyproject.toml"]},
            "answer_feedback": {
                "summary": "回答有方向，但缺少证据。",
                "grounding_notes": ["Feedback used selected_question.evidence_details."],
                "evidence_missed": [
                    {
                        "evidence_id": "manifest:pyproject.toml",
                        "source_path": "pyproject.toml",
                        "reason": "没有说明测试命令。",
                    }
                ],
                "gaps": ["需要补充 architecture tradeoff。"],
                "suggested_answer_outline": ["补一个取舍和验证步骤。"],
            },
            "session_summary": {
                "missed_evidence": ["manifest:pyproject.toml"],
                "practice_notes": ["补充 tradeoff。"],
            },
            "context_snapshot": {
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_hidden_source_content": False,
                    "includes_repo_evidence_text": False,
                }
            },
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["evidence_grounding"]["status"], "needs_attention")
        self.assertEqual(by_id["completeness_missing_evidence"]["status"], "needs_attention")
        self.assertEqual(by_id["architecture_understanding"]["status"], "needs_attention")
        self.assertEqual(by_id["tradeoff_awareness"]["status"], "needs_attention")
        self.assertEqual(by_id["privacy_boundary"]["status"], "supported")
        self.assertNotIn("没有说明测试命令。", str(signals))

    def test_marks_hallucination_risk_as_guarded_from_warning_code(self):
        data = {
            "selected_question": {"id": "q1"},
            "evidence_policy": {"allowed_evidence_ids": ["src:app.py#snippet-1"]},
            "answer_feedback": {"summary": "ok"},
        }
        warnings = [
            {
                "code": "filtered_hallucinated_references",
                "message": "1 text item(s) with unknown source paths, URLs, or evidence references were removed.",
            }
        ]

        signals = build_answer_quality_signals(data, warnings=warnings, errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["hallucination_risk"]["status"], "guarded")
        self.assertEqual(by_id["hallucination_risk"]["severity"], "warning")
        self.assertEqual(by_id["hallucination_risk"]["basis_fields"], ["warnings.filtered_hallucinated_references"])
        self.assertNotIn("unknown source paths", str(signals))

    def test_hallucination_risk_uses_allowed_evidence_presence_without_emitting_source_ref(self):
        data = {
            "selected_question": {"id": "q1"},
            "evidence_policy": {"allowed_evidence_ids": ["src:app.py#snippet-1"]},
            "answer_feedback": {"summary": "ok"},
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["hallucination_risk"]["status"], "supported")
        self.assertNotIn("src:app.py#snippet-1", str(signals))

    def test_preserves_safe_snippet_evidence_ids_without_source_content(self):
        data = {
            "selected_question": {"id": "q1"},
            "answer_feedback": {
                "summary": "回答有方向，但缺少证据。",
                "evidence_missed": [
                    {
                        "evidence_id": "src:app.py#snippet-1",
                        "source_path": "app.py",
                        "reason": "raw reason should stay out",
                    }
                ],
            },
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["evidence_grounding"]["evidence_refs"], ["src:app.py#snippet-1"])
        self.assertEqual(by_id["completeness_missing_evidence"]["evidence_refs"], ["src:app.py#snippet-1"])
        self.assertNotIn("raw reason should stay out", str(signals))
        self.assertNotIn("source_path", str(signals))

    def test_does_not_emit_user_answer_excerpt_or_raw_feedback_text(self):
        data = {
            "selected_question": {"id": "q1"},
            "evidence_policy": {"allowed_evidence_ids": ["src:app.py#snippet-1"]},
            "answer_feedback": {
                "summary": "SECRET_USER_ANSWER",
                "gaps": ["SECRET_USER_ANSWER"],
                "evidence_missed": [
                    {
                        "evidence_id": "src:app.py#snippet-1",
                        "source_path": "secret/source.py",
                        "reason": "SECRET_USER_ANSWER",
                    }
                ],
            },
            "context_snapshot": {
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_hidden_source_content": False,
                    "includes_repo_evidence_text": False,
                }
            },
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])

        self.assertNotIn("SECRET_USER_ANSWER", str(signals))
        self.assertNotIn("secret/source.py", str(signals))

    def test_missing_evidence_with_filtered_ref_still_needs_attention(self):
        data = {
            "selected_question": {"id": "q1"},
            "answer_feedback": {
                "summary": "回答有方向，但缺少证据。",
                "evidence_missed": [
                    {
                        "evidence_id": "https://github.com/acme/repo/blob/main/README.md",
                        "reason": "raw reason should stay out",
                    }
                ],
            },
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["evidence_grounding"]["status"], "needs_attention")
        self.assertEqual(by_id["completeness_missing_evidence"]["status"], "needs_attention")
        self.assertEqual(by_id["evidence_grounding"]["evidence_refs"], [])
        self.assertNotIn("https://", str(signals))
        self.assertNotIn("README", str(signals))

    def test_positive_architecture_and_tradeoff_context_is_supported_not_attention(self):
        data = {
            "selected_question": {"id": "q1"},
            "evidence_policy": {"allowed_evidence_ids": ["manifest:pyproject.toml"]},
            "answer_feedback": {
                "summary": "候选人说明了架构分层和 tradeoff。",
                "gaps": ["已经覆盖 architecture tradeoff，表达清楚。"],
                "suggested_answer_outline": ["可以继续沿用该取舍表达。"],
            },
        }

        signals = build_answer_quality_signals(data, warnings=[], errors=[])
        by_id = {signal["id"]: signal for signal in signals}

        self.assertEqual(by_id["architecture_understanding"]["status"], "supported")
        self.assertEqual(by_id["tradeoff_awareness"]["status"], "supported")


if __name__ == "__main__":
    unittest.main()
