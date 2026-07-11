import json
import unittest

from agent.run import ToolManager
from agent.tools.github_repo_interview_tool import GitHubRepoInterviewPrepTool
from agent.tools.github_repo_reader import GitHubRepoError, ReadmeContent, RepoFileContent, RepoMetadata, RepoTreeEntry
from agentpress.tool import ToolResult


class FakeReader:
    def __init__(
        self,
        readme=None,
        metadata_error=None,
        readme_error=None,
        tree_error=None,
        file_errors=None,
        skipped_files=None,
        tree_truncated=False,
        is_private=False,
    ):
        self.readme = readme
        self.metadata_error = metadata_error
        self.readme_error = readme_error
        self.tree_error = tree_error
        self.file_errors = file_errors or {}
        self.skipped_files = set(skipped_files or [])
        self.tree_truncated = tree_truncated
        self.is_private = is_private
        self.readme_refs = []
        self.tree_refs = []
        self.file_refs = []

    def fetch_metadata(self, parsed):
        if self.metadata_error:
            raise self.metadata_error
        self.parsed = parsed
        metadata = RepoMetadata(
            owner=parsed.owner,
            repo=parsed.repo,
            full_name=f"{parsed.owner}/{parsed.repo}",
            default_branch="main",
            description="A demo repo",
            primary_language="Python",
            stars=42,
            html_url=f"https://github.com/{parsed.owner}/{parsed.repo}",
            is_private=self.is_private,
        )
        return metadata

    def fetch_readme(self, parsed, default_branch=None):
        self.readme_refs.append(default_branch)
        if self.readme_error:
            raise self.readme_error
        return self.readme

    def fetch_tree(self, parsed, ref):
        self.tree_refs.append(ref)
        if self.tree_error:
            raise self.tree_error
        return (
            [
                RepoTreeEntry(path="pyproject.toml", type="blob", size=100),
                RepoTreeEntry(path="src", type="tree"),
                RepoTreeEntry(path="src/app.py", type="blob", size=100),
            ],
            self.tree_truncated,
        )

    def fetch_file_content(self, parsed, path, ref):
        self.file_refs.append((path, ref))
        if path in self.file_errors:
            raise self.file_errors[path]
        if path in self.skipped_files:
            return RepoFileContent(
                path=path,
                size=101_000,
                encoding="base64",
                text_excerpt="",
                truncated=True,
                skipped=True,
                skip_reason="file_too_large",
            )
        if path == "pyproject.toml":
            return RepoFileContent(
                path=path,
                size=100,
                encoding="base64",
                text_excerpt='[project]\ndependencies = ["fastapi"]',
                truncated=False,
            )
        return RepoFileContent(
            path=path,
            size=100,
            encoding="base64",
            text_excerpt="from fastapi import FastAPI\napp = FastAPI()\n",
            truncated=False,
        )

    def make_readme_summary(self, readme):
        return {
            "summary": (readme.text_excerpt[:80] if readme else ""),
            "confidence": "medium" if readme else "low",
            "max_chars": 600,
        }


class GitHubRepoInterviewToolTest(unittest.IsolatedAsyncioTestCase):
    async def test_tool_returns_success_envelope(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="AI Agent backend engineer",
            difficulty="senior",
            question_count=5,
        )

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["tool"], "github_repo_interview_prep")
        self.assertEqual(payload["type"], "github_repo_interview_prep")
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["partial"])
        self.assertEqual(payload["data"]["repo_metadata"]["full_name"], "owner/repo")
        self.assertEqual(payload["data"]["readme"]["path"], "README.md")
        self.assertEqual(payload["steps"][-1]["status"], "success")

    async def test_tool_returns_partial_when_readme_missing(self):
        tool = GitHubRepoInterviewPrepTool(reader=FakeReader(readme=None))

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["partial"])
        readme_step = next(step for step in payload["steps"] if step["id"] == "read_readme")
        self.assertEqual(readme_step["status"], "partial")
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["warnings"][0]["code"], "readme_not_found")
        self.assertIn("Slice 2", payload["warnings"][0]["message"])

    async def test_tool_rejects_invalid_inputs_without_traceback(self):
        tool = GitHubRepoInterviewPrepTool(reader=FakeReader())

        result = await tool.github_repo_interview_prep(
            github_url="https://evil.example/owner/repo",
            question_count=5,
        )

        self.assertFalse(result.success)
        self.assertIn("invalid_github_url", result.output)
        self.assertNotIn("Traceback", result.output)

    async def test_tool_accepts_numeric_question_count_string(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            question_count="5",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["input"]["question_count"], 5)

    async def test_tool_accepts_chinese_language_alias(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            language="请用中文展示",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["input"]["language"], "zh")

    async def test_tool_defaults_to_available_template_count(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["input"]["question_count"], 4)
        self.assertEqual(payload["data"]["question_generation_summary"]["requested_count"], 4)
        self.assertEqual(payload["data"]["question_generation_summary"]["generated_count"], 4)

    async def test_tool_returns_slice_2_context_pack_sections(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="AI Agent backend engineer",
            difficulty="senior",
            question_count=5,
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        pack = payload["data"]["project_context_pack"]
        self.assertEqual(payload["status"], "success")
        self.assertIn("manifest_summary", pack)
        self.assertIn("directory_summary", pack)
        self.assertIn("file_summaries", pack)
        self.assertIn("architecture_signals", pack)
        self.assertIn("evidence_map", pack)
        self.assertIn("build_context_pack", [step["id"] for step in payload["steps"]])

    async def test_tool_includes_evidence_backed_interview_questions(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        payload = json.loads(result.output)
        questions = payload["data"]["interview_questions"]
        summary = payload["data"]["question_generation_summary"]
        step_ids = [step["id"] for step in payload["steps"]]

        self.assertEqual(result.success, True)
        self.assertIn("generate_questions", step_ids)
        self.assertEqual(summary["requested_count"], 3)
        self.assertEqual(summary["generated_count"], 3)
        self.assertEqual(summary["available_template_count"], 4)
        self.assertEqual(summary["strategy"], "deterministic_evidence_templates")
        self.assertEqual(summary["difficulty"], "mid")
        self.assertTrue(summary["has_source_evidence"])
        self.assertEqual([question["id"] for question in questions], ["Q1", "Q2", "Q3"])
        self.assertTrue(all(question["question"] for question in questions))
        self.assertTrue(all(question["answer_direction"] for question in questions))
        self.assertTrue(all(question["evidence_refs"] for question in questions))
        self.assertIn("模拟面试问题（基于仓库内容）", result.output)
        self.assertIn("基于已读取的仓库源码证据", result.output)

    async def test_tool_payload_includes_evidence_details(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        question = payload["data"]["interview_questions"][0]
        self.assertTrue(question["evidence_details"])
        self.assertIn("has_evidence_details", payload["data"]["question_generation_summary"])
        for detail in question["evidence_details"]:
            self.assertTrue(detail["evidence_id"])
            self.assertTrue(detail["source_path"])
            self.assertTrue(detail["evidence_type"])
            self.assertTrue(detail["why_it_matters"])
            self.assertTrue(detail.get("snippet") or detail.get("summary"))

    async def test_markdown_includes_readable_evidence_details(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        markdown = payload["data"]["markdown"]
        self.assertIn("证据详情", markdown)
        self.assertIn("pyproject.toml", markdown)
        self.assertIn("python manifest", markdown)
        self.assertIn("为什么相关", markdown)

    async def test_tool_uses_english_markdown_when_language_is_en(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                )
            )
        )

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo",
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=2,
            language="en",
        )

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        markdown = payload["data"]["markdown"]
        self.assertIn("Mock Interview Questions (Repository Evidence)", markdown)
        self.assertIn("Direction:", markdown)
        self.assertIn("Evidence:", markdown)
        self.assertNotIn("模拟面试问题", markdown)

    async def test_tool_returns_partial_when_selected_file_read_fails(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                ),
                file_errors={"src/app.py": GitHubRepoError("github_request_failed", "file read failed", True)},
            )
        )

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["errors"], [])
        self.assertTrue(any(warning["code"] == "github_request_failed" for warning in payload["warnings"]))
        self.assertIn("src/app.py", payload["warnings"][0]["message"])
        self.assertIn("project_context_pack", payload["data"])

    async def test_tool_returns_partial_when_selected_file_is_skipped(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                ),
                skipped_files={"src/app.py"},
            )
        )

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["errors"], [])
        self.assertTrue(any(warning["code"] == "file_too_large" for warning in payload["warnings"]))
        open_questions = payload["data"]["project_context_pack"]["open_questions"]
        self.assertTrue(any("src/app.py" in question and "file_too_large" in question for question in open_questions))

    async def test_tool_rejects_private_repo_before_slice_2_reads(self):
        reader = FakeReader(
            readme=ReadmeContent(
                path="README.md",
                size=20,
                encoding="base64",
                text_excerpt="# Private",
                truncated=False,
            ),
            is_private=True,
        )
        tool = GitHubRepoInterviewPrepTool(reader=reader)

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertFalse(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["partial"])
        self.assertEqual(payload["errors"][0]["code"], "private_repo_not_supported")
        self.assertNotIn("Traceback", result.output)
        self.assertNotIn("token", result.output.lower())
        self.assertEqual(reader.readme_refs, [])
        self.assertEqual(reader.tree_refs, [])
        self.assertEqual(reader.file_refs, [])

    async def test_tool_uses_url_ref_for_readme_tree_and_file_reads(self):
        reader = FakeReader(
            readme=ReadmeContent(
                path="README.md",
                size=20,
                encoding="base64",
                text_excerpt="# Demo\nA project",
                truncated=False,
            )
        )
        tool = GitHubRepoInterviewPrepTool(reader=reader)

        result = await tool.github_repo_interview_prep(
            github_url="https://github.com/owner/repo/tree/feature-branch/src"
        )

        self.assertTrue(result.success)
        self.assertEqual(reader.readme_refs, ["feature-branch"])
        self.assertEqual(reader.tree_refs, ["feature-branch"])
        self.assertTrue(reader.file_refs)
        self.assertTrue(all(ref == "feature-branch" for _path, ref in reader.file_refs))

    async def test_tool_returns_partial_when_tree_read_fails(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                ),
                tree_error=GitHubRepoError("github_request_failed", "tree read failed", True),
            )
        )

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["partial"])
        self.assertTrue(any(error.get("step") == "inspect_tree" for error in payload["errors"]))
        self.assertIn("project_context_pack", payload["data"])

    async def test_tool_warns_when_tree_is_truncated(self):
        tool = GitHubRepoInterviewPrepTool(
            reader=FakeReader(
                readme=ReadmeContent(
                    path="README.md",
                    size=20,
                    encoding="base64",
                    text_excerpt="# Demo\nA project",
                    truncated=False,
                ),
                tree_truncated=True,
            )
        )

        result = await tool.github_repo_interview_prep(github_url="https://github.com/owner/repo")

        self.assertTrue(result.success)
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["errors"], [])
        self.assertTrue(any(warning["code"] == "tree_truncated" for warning in payload["warnings"]))
        self.assertIn("project_context_pack", payload["data"])

    async def test_tool_returns_safe_error_for_unexpected_reader_exception(self):
        tool = GitHubRepoInterviewPrepTool(reader=FakeReader(metadata_error=ValueError("boom")))

        with self.assertLogs("agent.tools.github_repo_interview_tool", level="ERROR") as logs:
            result = await tool.github_repo_interview_prep(
                github_url="https://github.com/owner/repo",
            )

        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.success)
        self.assertTrue(any("Unexpected error in github_repo_interview_prep" in item for item in logs.output))
        payload = json.loads(result.output)
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["partial"])
        self.assertEqual(payload["errors"][0]["code"], "github_request_failed")
        self.assertNotIn("Traceback", result.output)
        self.assertNotIn("boom", result.output)


class FakeThreadManager:
    def __init__(self):
        self.registered = []

    def add_tool(self, tool_class, **kwargs):
        self.registered.append((tool_class, kwargs))


class GitHubRepoInterviewRegistrationTest(unittest.TestCase):
    def test_tool_manager_registers_github_repo_interview_tool(self):
        fake_thread_manager = FakeThreadManager()
        manager = ToolManager(
            thread_manager=fake_thread_manager,
            project_id="project-123",
            thread_id="thread-123",
        )

        manager.register_all_tools()

        registered_tools = [tool_class for tool_class, _kwargs in fake_thread_manager.registered]
        self.assertIn(GitHubRepoInterviewPrepTool, registered_tools)
