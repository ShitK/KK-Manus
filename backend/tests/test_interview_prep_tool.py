import json
import unittest

from agent.run import ToolManager
from agent.tools.github_repo_interview_tool import GitHubRepoInterviewPrepTool
from agent.tools.github_repo_interview_workflow_tool import GitHubRepoInterviewWorkflowTool
from agent.tools.interview_prep_tool import InterviewPrepTool
from agent.tools.simple_test_tool import SimpleTestTool
from agent.tools.task_list_tool import TaskListTool
from agentpress.tool import ToolResult
from agentpress.tool_registry import ToolRegistry


class InterviewPrepToolTest(unittest.IsolatedAsyncioTestCase):
    def assert_tool_failure(self, result, expected_text):
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.success)
        self.assertIn(expected_text, result.output)
        self.assertNotIn("Traceback", result.output)

    async def test_create_interview_plan_returns_task_suggestions(self):
        tool = InterviewPrepTool()

        result = await tool.create_interview_plan(
            target_role="AI Agent 后端工程师",
            prep_days=7,
            project_name="KKManus",
            tech_stack=["FastAPI", "PostgreSQL", "Redis", "Google ADK"],
            focus_areas=["Agent run 生命周期", "工具系统"],
            daily_minutes=90,
        )

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["tool"], "interview_prep")
        self.assertEqual(payload["type"], "interview_plan")
        self.assertEqual(payload["input"]["target_role"], "AI Agent 后端工程师")
        self.assertEqual(payload["input"]["prep_days"], 7)
        self.assertGreaterEqual(len(payload["daily_schedule"]), 1)
        self.assertIn("suggested_task_sections", payload)
        self.assertGreaterEqual(len(payload["suggested_task_sections"][0]["tasks"]), 1)

    async def test_generate_project_story_returns_star_sections(self):
        tool = InterviewPrepTool()

        result = await tool.generate_project_story(
            project_name="KKManus",
            project_summary="基于 Suna / FuFanManus 课程项目继续工程化的通用 AI Agent 项目",
            tech_stack=["Next.js", "FastAPI", "PostgreSQL", "Redis", "Google ADK"],
            personal_contribution="修复核心 demo 链路、补 Agent Run diagnostics、梳理工具注册边界",
            challenges=["工具系统运行时注册和配置展示不一致", "ADK events 与 messages 边界容易混淆"],
            target_role="AI Agent 后端工程师",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["type"], "project_story")
        self.assertIn("star", payload)
        self.assertIn("situation", payload["star"])
        self.assertIn("action", payload["star"])
        self.assertIn("two_minute_script", payload)
        self.assertTrue(any("KKManus" in item["talk_track"] for item in payload["highlights"]))

    async def test_generate_mock_questions_respects_count_and_shape(self):
        tool = InterviewPrepTool()

        result = await tool.generate_mock_questions(
            target_role="全栈工程师",
            project_name="KKManus",
            tech_stack=["Next.js", "FastAPI", "Redis"],
            difficulty="mid",
            question_count=5,
            focus_areas=["前后端链路", "Redis/Worker"],
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["type"], "mock_questions")
        self.assertEqual(len(payload["questions"]), 5)
        self.assertIn("question", payload["questions"][0])
        self.assertIn("assesses", payload["questions"][0])
        self.assertIn("answer_direction", payload["questions"][0])

    async def test_create_interview_plan_rejects_invalid_numeric_inputs(self):
        tool = InterviewPrepTool()

        cases = [
            {"prep_days": 0, "daily_minutes": 90, "expected": "prep_days"},
            {"prep_days": None, "daily_minutes": 90, "expected": "prep_days"},
            {"prep_days": "7", "daily_minutes": 90, "expected": "prep_days"},
            {"prep_days": 7, "daily_minutes": None, "expected": "daily_minutes"},
            {"prep_days": 7, "daily_minutes": "90", "expected": "daily_minutes"},
        ]

        for case in cases:
            with self.subTest(case=case):
                result = await tool.create_interview_plan(
                    target_role="AI Agent 后端工程师",
                    prep_days=case["prep_days"],
                    daily_minutes=case["daily_minutes"],
                )

                self.assert_tool_failure(result, case["expected"])

    async def test_generate_project_story_rejects_invalid_inputs_without_tracebacks(self):
        tool = InterviewPrepTool()

        cases = [
            {"project_name": "", "project_summary": "项目摘要", "expected": "project_name"},
            {"project_name": "KKManus", "project_summary": None, "expected": "project_summary"},
            {"project_name": "KKManus", "project_summary": "项目摘要", "tone": "verbose", "expected": "tone"},
        ]

        for case in cases:
            with self.subTest(case=case):
                result = await tool.generate_project_story(
                    project_name=case["project_name"],
                    project_summary=case["project_summary"],
                    tone=case.get("tone", "concise"),
                )

                self.assert_tool_failure(result, case["expected"])

    async def test_generate_mock_questions_rejects_invalid_inputs_without_tracebacks(self):
        tool = InterviewPrepTool()

        cases = [
            {"target_role": "", "question_count": 5, "expected": "target_role"},
            {"target_role": "全栈工程师", "question_count": 0, "expected": "question_count"},
            {"target_role": "全栈工程师", "question_count": None, "expected": "question_count"},
            {"target_role": "全栈工程师", "question_count": "5", "expected": "question_count"},
        ]

        for case in cases:
            with self.subTest(case=case):
                result = await tool.generate_mock_questions(
                    target_role=case["target_role"],
                    question_count=case["question_count"],
                )

                self.assert_tool_failure(result, case["expected"])

    async def test_optional_text_none_is_normalized_without_tracebacks(self):
        tool = InterviewPrepTool()

        plan_result = await tool.create_interview_plan(
            target_role="AI Agent 后端工程师",
            prep_days=1,
            project_name=None,
        )
        self.assertTrue(plan_result.success)
        self.assertEqual(json.loads(plan_result.output)["input"]["project_name"], "KKManus")

        story_result = await tool.generate_project_story(
            project_name="KKManus",
            project_summary="项目摘要",
            personal_contribution=None,
            target_role=None,
        )
        self.assertTrue(story_result.success)
        self.assertEqual(json.loads(story_result.output)["input"]["target_role"], "")

        questions_result = await tool.generate_mock_questions(
            target_role="全栈工程师",
            project_name=None,
            question_count=1,
        )
        self.assertTrue(questions_result.success)
        self.assertEqual(json.loads(questions_result.output)["input"]["project_name"], "KKManus")

    async def test_string_list_inputs_are_normalized_as_single_items(self):
        tool = InterviewPrepTool()

        plan_result = await tool.create_interview_plan(
            target_role="AI Agent 后端工程师",
            prep_days=1,
            tech_stack="FastAPI",
            focus_areas="Agent run 生命周期",
        )
        self.assertTrue(plan_result.success)
        plan_payload = json.loads(plan_result.output)
        self.assertEqual(plan_payload["input"]["tech_stack"], ["FastAPI"])
        self.assertEqual(plan_payload["input"]["focus_areas"], ["Agent run 生命周期"])

        story_result = await tool.generate_project_story(
            project_name="KKManus",
            project_summary="项目摘要",
            challenges="ADK events 与 messages 边界",
        )
        self.assertTrue(story_result.success)
        story_payload = json.loads(story_result.output)
        self.assertEqual(
            story_payload["star"]["action"][1:],
            ["ADK events 与 messages 边界"],
        )

    async def test_non_list_scalar_inputs_are_normalized_without_tracebacks(self):
        tool = InterviewPrepTool()

        result = await tool.generate_mock_questions(
            target_role="全栈工程师",
            tech_stack=123,
            focus_areas=456,
            question_count=1,
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["input"]["tech_stack"], ["123"])
        self.assertEqual(payload["input"]["focus_areas"], ["456"])

    async def test_long_plan_mentions_schedule_preview_limit(self):
        tool = InterviewPrepTool()

        result = await tool.create_interview_plan(
            target_role="AI Agent 后端工程师",
            prep_days=30,
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(len(payload["daily_schedule"]), 14)
        self.assertIn("schedule_note", payload)
        self.assertIn("14", payload["schedule_note"])
        self.assertIn("30", payload["schedule_note"])


class FakeThreadManager:
    def __init__(self):
        self.registered = []

    def add_tool(self, tool_class, **kwargs):
        self.registered.append((tool_class, kwargs))


class InterviewPrepRegistrationTest(unittest.TestCase):
    def test_tool_manager_does_not_register_general_interview_or_test_tools_by_default(self):
        fake_thread_manager = FakeThreadManager()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
        )

        manager.register_all_tools()

        registered_classes = [item[0] for item in fake_thread_manager.registered]
        self.assertNotIn(SimpleTestTool, registered_classes)
        self.assertNotIn(InterviewPrepTool, registered_classes)
        self.assertIn(TaskListTool, registered_classes)
        self.assertIn(GitHubRepoInterviewPrepTool, registered_classes)
        self.assertIn(GitHubRepoInterviewWorkflowTool, registered_classes)
        self.assertEqual(
            registered_classes,
            [TaskListTool, GitHubRepoInterviewPrepTool, GitHubRepoInterviewWorkflowTool],
        )


class InterviewPrepToolRegistryTest(unittest.TestCase):
    def test_registry_exposes_only_public_interview_prep_functions(self):
        registry = ToolRegistry()
        registry.register_tool(InterviewPrepTool)

        functions = registry.get_available_functions()

        self.assertEqual(
            set(functions),
            {
                "create_interview_plan",
                "generate_project_story",
                "generate_mock_questions",
            },
        )
        self.assertNotIn("_success_json", functions)
        self.assertNotIn("_clean_list", functions)
        self.assertNotIn("_clean_text", functions)


if __name__ == "__main__":
    unittest.main()
