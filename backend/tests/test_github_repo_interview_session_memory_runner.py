import unittest
from unittest.mock import AsyncMock, patch

from agent.run import AgentConfig, AgentRunner


class GitHubRepoInterviewSessionMemoryRunnerTest(unittest.IsolatedAsyncioTestCase):
    def _runner(self) -> AgentRunner:
        runner = AgentRunner(
            AgentConfig(
                thread_id="11111111-1111-1111-1111-111111111111",
                project_id="project-1",
                stream=False,
                agent_run_id="run-1",
            )
        )
        runner.client = object()
        runner.account_id = "22222222-2222-2222-2222-222222222222"
        return runner

    async def test_session_memory_load_failure_is_non_fatal(self):
        runner = self._runner()
        with patch("agent.run.load_session_memory", new=AsyncMock(side_effect=RuntimeError("db unavailable"))):
            memory = await runner._load_github_interview_session_memory()

        self.assertEqual(memory, {})

    async def test_session_memory_upsert_uses_patch_and_agent_run_id(self):
        runner = self._runner()
        payload = {
            "data": {
                "session_memory_patch": {
                    "answered_question_ids": ["Q4"],
                    "summary_completed": True,
                },
                "workflow": {"current_stage": "summary_ready"},
            }
        }
        with patch("agent.run.upsert_session_memory", new=AsyncMock(return_value={})) as upsert:
            await runner._upsert_github_interview_session_memory(payload)

        upsert.assert_awaited_once_with(
            runner.client,
            "22222222-2222-2222-2222-222222222222",
            "11111111-1111-1111-1111-111111111111",
            {
                "answered_question_ids": ["Q4"],
                "summary_completed": True,
            },
            source_agent_run_id="run-1",
            updated_from_stage="summary_ready",
        )

    async def test_vector_retrieval_forwards_authenticated_account(self):
        runner = self._runner()
        expected = {"status": "matched", "context": [{"id": "memory-1"}]}
        with patch("agent.run.retrieve_vector_memories", new=AsyncMock(return_value=expected)) as retrieve:
            result = await runner._retrieve_github_interview_vector_memories(
                query_text="AgentLoop 如何处理工具循环失败",
                target_role="AI Agent 工程师",
                category="architecture",
            )

        self.assertEqual(result, expected)
        self.assertEqual(retrieve.await_args.kwargs["user_id"], runner.account_id)
        self.assertEqual(retrieve.await_args.kwargs["query_text"], "AgentLoop 如何处理工具循环失败")

    async def test_workflow_memory_loader_combines_all_three_memory_layers(self):
        runner = self._runner()
        runner._load_github_interview_session_memory = AsyncMock(
            return_value={
                "target_role": "AI Agent 工程师",
                "current_practice_category": "architecture",
            }
        )
        runner._load_github_interview_saved_memories = AsyncMock(
            return_value=[{"id": "structured-1"}]
        )
        runner._retrieve_github_interview_vector_memories = AsyncMock(
            return_value={"status": "matched", "context": [{"id": "vector-1"}]}
        )

        result = await runner._load_github_interview_workflow_memory_context(
            query_text="我开始回答 Q1：解释架构边界。",
            target_role=None,
            category=None,
        )

        self.assertEqual(result["session_memory_context"]["target_role"], "AI Agent 工程师")
        self.assertEqual(result["saved_memory_context"], [{"id": "structured-1"}])
        self.assertEqual(result["vector_memory_context"], [{"id": "vector-1"}])
        runner._retrieve_github_interview_vector_memories.assert_awaited_once_with(
            query_text="我开始回答 Q1：解释架构边界。",
            target_role="后端开发工程师",
            category="architecture",
        )

    async def test_workflow_memory_loader_normalizes_demo_filter_aliases(self):
        runner = self._runner()
        runner._load_github_interview_session_memory = AsyncMock(return_value={})
        runner._load_github_interview_saved_memories = AsyncMock(return_value=[])
        runner._retrieve_github_interview_vector_memories = AsyncMock(
            return_value={"status": "matched", "context": [{"id": "memory-1"}]}
        )

        await runner._load_github_interview_workflow_memory_context(
            query_text="miniclawd AI Agent 架构面试练习经验",
            target_role="AI Agent开发工程师",
            category="架构边界",
        )

        runner._retrieve_github_interview_vector_memories.assert_awaited_once_with(
            query_text="miniclawd AI Agent 架构面试练习经验",
            target_role="后端开发工程师",
            category="architecture",
        )


if __name__ == "__main__":
    unittest.main()
