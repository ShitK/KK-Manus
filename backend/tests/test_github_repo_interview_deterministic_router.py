import json
import unittest

from agent.github_repo_interview_deterministic_router import (
    build_deterministic_answer_route,
    detect_answer_coach_intent,
    extract_event_text,
    render_workflow_feedback_markdown,
)


def sample_prep_payload():
    return {
        "tool": "github_repo_interview_prep",
        "type": "github_repo_interview_prep",
        "status": "success",
        "data": {
            "interview_questions": [
                {
                    "id": "Q1",
                    "category": "architecture",
                    "difficulty": "senior",
                    "question": "解释 miniclawd 的分层架构边界。",
                    "answer_direction": "先说明模块边界，再说明依赖方向。",
                    "source_paths": ["src/index.ts"],
                    "evidence_refs": ["source:src/index.ts"],
                    "evidence_details": [
                        {
                            "evidence_id": "source:src/index.ts",
                            "source_path": "src/index.ts",
                            "evidence_type": "source",
                            "summary": "CLI entrypoint.",
                            "why_it_matters": "用于解释入口如何串联架构。",
                            "confidence": "medium",
                        }
                    ],
                    "confidence": "medium",
                }
            ],
            "question_generation_summary": {
                "generated_count": 1,
                "has_evidence_details": True,
            },
        },
    }


def tool_message(tool_name, payload):
    return {
        "type": "tool",
        "content": {
            "tool_name": tool_name,
            "result": json.dumps(payload, ensure_ascii=False),
        },
        "metadata": {"tool_name": tool_name},
        "created_at": "2026-07-07T00:00:00+00:00",
    }


def sample_workflow_payload(question_id="Q1", with_answer_feedback=False, feedback_summary="回答覆盖了分层思路。"):
    payload = {
        "tool": "github_repo_interview_workflow",
        "type": "github_repo_interview_workflow",
        "status": "success",
        "data": {
            "selected_question": {
                "id": question_id,
                "question": "解释 miniclawd 的分层架构边界。",
            },
            "workflow": {"stage": "question_selected"},
        },
    }
    if with_answer_feedback:
        payload["data"]["answer_feedback"] = {
            "summary": feedback_summary,
            "strengths": ["说明了入口和 application 的边界。"],
            "gaps": ["还需要补充验证路径。"],
            "suggested_answer_outline": ["补充一个测试策略。"],
            "follow_up_questions": ["你会如何写集成测试验证调用链？"],
        }
        payload["data"]["workflow"] = {
            "stage": "coach_answer",
            "answer_coached": True,
            "follow_up_count": 0,
        }
    return payload


def sample_workflow_error_payload(question_id="Q1"):
    return {
        "tool": "github_repo_interview_workflow",
        "type": "github_repo_interview_workflow",
        "status": "error",
        "input": {"stage": "coach_answer", "question_id": question_id},
        "data": {
            "selected_question": {
                "id": question_id,
                "question": "解释 miniclawd 的分层架构边界。",
            },
            "workflow": {"stage": "coach_answer"},
        },
        "errors": [
            {
                "code": "coach_generation_failed",
                "message": "Answer coach feedback could not be generated.",
            }
        ],
    }


class GitHubRepoInterviewDeterministicRouterTests(unittest.TestCase):
    def test_extract_event_text_from_adk_user_parts(self):
        content = {
            "role": "user",
            "parts": [{"text": "第 1 题答案：我会解释分层架构。"}],
        }

        self.assertEqual(extract_event_text(content), "第 1 题答案：我会解释分层架构。")

    def test_detects_chinese_question_answer_intent(self):
        intent = detect_answer_coach_intent("第 1 题答案：我会解释 core 和 infrastructure。")

        self.assertIsNotNone(intent)
        self.assertEqual(intent["question_id"], "Q1")

    def test_detects_expanded_question_answer_intents(self):
        examples = [
            ("第 1 题我这样答：我会先说入口。", "Q1"),
            ("第一题我的回答是：我会解释模块边界。", "Q1"),
            ("Q1 我的回答：我会从 core 讲起。", "Q1"),
            ("q1 我准备这样说：先讲分层。", "Q1"),
        ]

        for text, expected_question_id in examples:
            with self.subTest(text=text):
                intent = detect_answer_coach_intent(text)
                self.assertIsNotNone(intent)
                self.assertEqual(intent["question_id"], expected_question_id)

    def test_detects_expanded_generic_feedback_intents(self):
        examples = [
            "帮我看看这版回答",
            "这样回答行不行？",
            "请按刚才问题点评",
            "我的回答是：我会解释模块边界。",
            "我会这么回答：先讲 CLI，再讲 application。",
            "我准备这样说：核心边界是 core 和 infrastructure。",
        ]

        for text in examples:
            with self.subTest(text=text):
                intent = detect_answer_coach_intent(text)
                self.assertIsNotNone(intent)
                self.assertNotIn("question_id", intent)

    def test_builds_coach_answer_route_from_existing_prep_payload(self):
        user_text = "第 1 题答案：我会解释 core / application / infrastructure 的职责。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message("github_repo_interview_prep", sample_prep_payload())
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["stage"], "coach_answer")
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(route["user_answer"], user_text)
        self.assertEqual(route["language"], "zh")
        self.assertEqual(route["coach_style"], "balanced")
        self.assertEqual(
            route["prep_questions_pack"]["data"]["interview_questions"][0]["id"],
            "Q1",
        )

    def test_does_not_route_without_existing_github_prep_payload(self):
        route = build_deterministic_answer_route(
            latest_user_text="第 1 题答案：我会解释架构。",
            historical_messages=[],
        )

        self.assertIsNone(route)

    def test_builds_generic_feedback_route_from_current_workflow_question(self):
        user_text = "帮我看看这版回答：我会解释 core / application / infrastructure 的职责。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message("github_repo_interview_workflow", sample_workflow_payload("Q1")),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(route["stage"], "coach_answer")

    def test_builds_follow_up_route_after_answer_feedback_exists(self):
        user_text = "我的回答是：我会 mock infrastructure，并验证入口到 application 的调用链。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(route["stage"], "coach_follow_up")
        self.assertEqual(route["follow_up_answer"], user_text)
        self.assertNotIn("user_answer", route)

    def test_builds_follow_up_route_from_explicit_follow_up_answer_prefix(self):
        user_text = "我回答追问1: 我会沿着 import 调用链做最小闭环排查。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(route["stage"], "coach_follow_up")
        self.assertEqual(route["follow_up_answer"], "我会沿着 import 调用链做最小闭环排查。")
        self.assertNotIn("user_answer", route)

    def test_follow_up_route_uses_last_answer_feedback_when_latest_workflow_failed(self):
        user_text = "我的回答是：我会 mock infrastructure，并验证入口到 application 的调用链。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message("github_repo_interview_workflow", sample_workflow_error_payload("Q1")),
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["stage"], "coach_follow_up")
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(
            route["previous_workflow_state"]["data"]["answer_feedback"]["summary"],
            "回答覆盖了分层思路。",
        )

    def test_builds_summary_route_from_existing_practice_context(self):
        user_text = "请总结我这一轮 GitHub 仓库面试练习。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["kind"], "conversation_summary")
        self.assertEqual(route["tool_name"], "github_repo_interview_conversation_summary")
        self.assertEqual(route["summary_scope"], "thread_dialogue")
        self.assertEqual(route["language"], "zh")
        self.assertNotIn("user_answer", route)
        self.assertNotIn("follow_up_answer", route)
        self.assertNotIn("previous_workflow_state", route)

    def test_summary_route_does_not_depend_on_session_practice_history(self):
        user_text = "请总结我这一轮 GitHub 仓库面试练习。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q2", with_answer_feedback=True, feedback_summary="Q2 回答覆盖了实现细节。"),
                ),
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True, feedback_summary="Q1 回答覆盖了架构边界。"),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["kind"], "conversation_summary")
        self.assertEqual(route["summary_scope"], "thread_dialogue")
        self.assertNotIn("previous_workflow_state", route)
        self.assertNotIn("question_id", route)

    def test_summary_route_ignores_failed_workflow_payloads(self):
        user_text = "帮我复盘一下本轮面试练习。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message("github_repo_interview_workflow", sample_workflow_error_payload("Q1")),
                tool_message(
                    "github_repo_interview_workflow",
                    sample_workflow_payload("Q1", with_answer_feedback=True),
                ),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["kind"], "conversation_summary")
        self.assertEqual(route["tool_name"], "github_repo_interview_conversation_summary")
        self.assertNotIn("previous_workflow_state", route)

    def test_summary_route_works_without_any_workflow_payloads(self):
        route = build_deterministic_answer_route(
            latest_user_text="请总结我这一轮 GitHub 仓库面试练习。",
            historical_messages=[
                {
                    "type": "assistant",
                    "content": {"role": "assistant", "content": "我们刚才讨论了 Q4 的测试策略回答。"},
                    "metadata": {},
                    "created_at": "2026-07-09T00:00:00+00:00",
                },
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["kind"], "conversation_summary")
        self.assertEqual(route["tool_name"], "github_repo_interview_conversation_summary")
        self.assertEqual(route["summary_scope"], "thread_dialogue")

    def test_generic_answer_route_uses_failed_workflow_input_question_id(self):
        user_text = "我的回答是：我会解释 core / application / infrastructure 的职责。"
        route = build_deterministic_answer_route(
            latest_user_text=user_text,
            historical_messages=[
                tool_message("github_repo_interview_workflow", sample_workflow_error_payload("Q1")),
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNotNone(route)
        self.assertEqual(route["stage"], "coach_answer")
        self.assertEqual(route["question_id"], "Q1")
        self.assertEqual(route["user_answer"], user_text)

    def test_does_not_route_generic_feedback_without_current_workflow_question(self):
        route = build_deterministic_answer_route(
            latest_user_text="帮我看看这版回答：我会解释架构。",
            historical_messages=[
                tool_message("github_repo_interview_prep", sample_prep_payload()),
            ],
        )

        self.assertIsNone(route)

    def test_renders_feedback_markdown_without_user_answer_text(self):
        payload = {
            "status": "success",
            "data": {
                "selected_question": {
                    "id": "Q1",
                    "question": "解释 miniclawd 的分层架构边界。",
                },
                "answer_feedback": {
                    "summary": "回答覆盖了分层思路。",
                    "strengths": ["说明了入口和 application 的边界。"],
                    "gaps": ["还需要补充 core 与 infrastructure 的依赖方向。"],
                    "suggested_answer_outline": ["先讲入口，再讲应用层，再讲外部依赖。"],
                    "follow_up_questions": ["如果替换模型 provider，会改哪一层？"],
                },
            },
        }

        markdown = render_workflow_feedback_markdown(payload)

        self.assertIn("Q1", markdown)
        self.assertIn("回答覆盖了分层思路", markdown)
        self.assertIn("说明了入口", markdown)
        self.assertIn("还需要补充", markdown)
        self.assertNotIn("第 1 题答案", markdown)

    def test_renders_follow_up_feedback_markdown(self):
        payload = {
            "status": "success",
            "input": {"stage": "coach_follow_up"},
            "data": {
                "selected_question": {
                    "id": "Q1",
                    "question": "解释 miniclawd 的分层架构边界。",
                },
                "follow_up": {
                    "feedback": ["追问回答补充了测试边界。"],
                    "questions": ["如果 mock 失败，你会如何定位？"],
                },
                "other_questions": [
                    {
                        "id": "Q2",
                        "category": "testing and automation",
                        "difficulty": "senior",
                        "question": "你会如何评估测试自动化准备度？",
                    }
                ],
            },
        }

        markdown = render_workflow_feedback_markdown(payload)

        self.assertIn("追问点评：Q1", markdown)
        self.assertIn("追问回答补充了测试边界", markdown)
        self.assertIn("如果 mock 失败", markdown)
        self.assertIn("回答其他问题", markdown)
        self.assertIn("Q2", markdown)
        self.assertIn("测试与自动化", markdown)
        self.assertIn("高级", markdown)
        self.assertIn("你会如何评估测试自动化准备度", markdown)
        self.assertNotIn("testing and automation", markdown)
        self.assertNotIn("senior", markdown)

    def test_renders_session_summary_markdown(self):
        payload = {
            "status": "success",
            "input": {"stage": "summarize"},
            "data": {
                "selected_question": {
                    "id": "Q1",
                    "question": "解释 miniclawd 的分层架构边界。",
                },
                "workflow": {
                    "practice_history": [
                        {
                            "question_id": "Q1",
                            "question": "解释 miniclawd 的分层架构边界。",
                            "answer_feedback": {"summary": "Q1 回答覆盖了入口层。"},
                        },
                        {
                            "question_id": "Q2",
                            "question": "解释 Agent Loop 的实现细节。",
                            "answer_feedback": {"summary": "Q2 回答覆盖了实现细节。"},
                        },
                    ],
                },
                "session_summary": {
                    "covered_evidence": ["src:src/index.ts#snippet-1"],
                    "missed_evidence": ["src:src/application/index.ts#snippet-1"],
                    "practice_notes": ["回答已经覆盖入口层，但 application 层证据还可以更具体。"],
                    "next_practice_suggestion": "下一题继续练习实现细节。",
                    "workflow_completion": {
                        "answer_coached": True,
                        "follow_up_completed": False,
                        "summary_scope": "answer_feedback_only",
                        "answered_question_ids": ["Q1", "Q2"],
                    },
                },
            },
        }

        markdown = render_workflow_feedback_markdown(payload)

        self.assertIn("练习总结：Q1 + Q2", markdown)
        self.assertIn("已练习题目", markdown)
        self.assertIn("Q1 回答覆盖了入口层", markdown)
        self.assertIn("Q2 回答覆盖了实现细节", markdown)
        self.assertIn("解释 miniclawd", markdown)
        self.assertIn("已覆盖证据", markdown)
        self.assertIn("src:src/index.ts#snippet-1", markdown)
        self.assertIn("还可补充证据", markdown)
        self.assertIn("src:src/application/index.ts#snippet-1", markdown)
        self.assertIn("回答已经覆盖入口层", markdown)
        self.assertIn("下一题继续练习实现细节", markdown)
        self.assertIn("回答点评已完成", markdown)
        self.assertIn("追问未完成", markdown)


if __name__ == "__main__":
    unittest.main()
