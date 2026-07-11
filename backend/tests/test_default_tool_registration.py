import unittest

from agent.run import ToolManager
from agent.tools.github_repo_interview_tool import GitHubRepoInterviewPrepTool
from agent.tools.github_repo_interview_workflow_tool import GitHubRepoInterviewWorkflowTool
from agent.tools.github_repo_answer_coach_tool import GitHubRepoAnswerCoachTool
from agent.tools.interview_prep_tool import InterviewPrepTool
from agent.tools.simple_test_tool import SimpleTestTool


class FakeThreadManager:
    def __init__(self):
        self.registered_tools = []

    def add_tool(self, tool_class, **kwargs):
        self.registered_tools.append(tool_class)


class DefaultToolRegistrationTest(unittest.TestCase):
    def test_default_registration_keeps_github_workflow_without_legacy_single_point_tools(self):
        thread_manager = FakeThreadManager()
        manager = ToolManager(
            thread_manager=thread_manager,
            project_id="project-id",
            thread_id="thread-id",
            model_name="test/model",
        )

        manager.register_all_tools()

        self.assertIn(GitHubRepoInterviewPrepTool, thread_manager.registered_tools)
        self.assertIn(GitHubRepoInterviewWorkflowTool, thread_manager.registered_tools)
        self.assertNotIn(SimpleTestTool, thread_manager.registered_tools)
        self.assertNotIn(InterviewPrepTool, thread_manager.registered_tools)
        self.assertNotIn(GitHubRepoAnswerCoachTool, thread_manager.registered_tools)


if __name__ == "__main__":
    unittest.main()
