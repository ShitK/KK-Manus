import unittest

from agent.tools.github_repo_context import build_project_context_pack, select_repository_files
from agent.tools.github_repo_reader import ReadmeContent, RepoFileContent, RepoMetadata, RepoTreeEntry


class GitHubRepoContextSelectionTest(unittest.TestCase):
    def test_selects_manifest_and_source_files_with_limits(self):
        entries = [
            RepoTreeEntry(path="package-lock.json", type="blob", size=10),
            RepoTreeEntry(path="pyproject.toml", type="blob", size=500),
            RepoTreeEntry(path="requirements.txt", type="blob", size=120),
            RepoTreeEntry(path="Dockerfile", type="blob", size=200),
            RepoTreeEntry(path=".env.example", type="blob", size=100),
            RepoTreeEntry(path="node_modules/ignored.js", type="blob", size=100),
            RepoTreeEntry(path="src/app.py", type="blob", size=1000),
            RepoTreeEntry(path="src/routes.py", type="blob", size=1000),
            RepoTreeEntry(path="tests/test_app.py", type="blob", size=1000),
            RepoTreeEntry(path="README.md", type="blob", size=1000),
        ]

        selection = select_repository_files(entries, primary_language="Python")

        self.assertEqual(selection.manifest_paths, ["pyproject.toml", "requirements.txt", "Dockerfile"])
        self.assertIn("src/app.py", selection.source_paths)
        self.assertIn("src/routes.py", selection.source_paths)
        self.assertNotIn("tests/test_app.py", selection.source_paths)
        self.assertNotIn("node_modules/ignored.js", selection.source_paths)
        self.assertNotIn(".env.example", selection.manifest_paths)
        self.assertNotIn(".env.example", selection.source_paths)

    def test_excludes_oversized_manifest_and_source_entries(self):
        entries = [
            RepoTreeEntry(path="pyproject.toml", type="blob", size=100_001),
            RepoTreeEntry(path="package.json", type="blob", size=100_000),
            RepoTreeEntry(path="src/app.py", type="blob", size=100_001),
            RepoTreeEntry(path="src/routes.py", type="blob", size=100_000),
        ]

        selection = select_repository_files(entries, primary_language="Python")

        self.assertEqual(selection.manifest_paths, ["package.json"])
        self.assertNotIn("pyproject.toml", selection.manifest_paths)
        self.assertIn("src/routes.py", selection.source_paths)
        self.assertNotIn("src/app.py", selection.source_paths)

    def test_requirements_summary_skips_options_and_urls(self):
        metadata = RepoMetadata(
            owner="owner",
            repo="repo",
            full_name="owner/repo",
            default_branch="main",
            description="Demo",
            primary_language="Python",
            stars=42,
            html_url="https://github.com/owner/repo",
        )
        files = [
            RepoFileContent(
                path="requirements.txt",
                size=120,
                encoding="base64",
                text_excerpt="\n".join(
                    [
                        "fastapi==0.110.0",
                        "-r dev-requirements.txt",
                        "--extra-index-url https://packages.example/simple",
                        "git+https://github.com/example/private-package.git",
                        "pydantic>=2",
                    ]
                ),
                truncated=False,
            )
        ]

        pack = build_project_context_pack(
            metadata=metadata,
            readme=None,
            tree_entries=[],
            tree_truncated=False,
            files=files,
            read_errors=[],
        )

        dependencies = pack["manifest_summary"][0]["dependencies"]
        self.assertEqual(dependencies, ["fastapi", "pydantic"])

    def test_context_pack_contains_directory_manifest_file_and_evidence_sections(self):
        metadata = RepoMetadata(
            owner="owner",
            repo="repo",
            full_name="owner/repo",
            default_branch="main",
            description="Demo",
            primary_language="Python",
            stars=42,
            html_url="https://github.com/owner/repo",
        )
        readme = ReadmeContent(
            path="README.md",
            size=30,
            encoding="base64",
            text_excerpt="# Demo\nA FastAPI service",
            truncated=False,
        )
        tree_entries = [
            RepoTreeEntry(path="pyproject.toml", type="blob", size=100),
            RepoTreeEntry(path="docs", type="tree"),
            RepoTreeEntry(path="docs/usage.md", type="blob", size=100),
            RepoTreeEntry(path="src", type="tree"),
            RepoTreeEntry(path="src/app.py", type="blob", size=100),
        ]
        files = [
            RepoFileContent(
                path="pyproject.toml",
                size=100,
                encoding="base64",
                text_excerpt='[project]\ndependencies = ["fastapi", "pydantic"]\n[project.scripts]\napi = "demo:main"',
                truncated=False,
            ),
            RepoFileContent(
                path="src/app.py",
                size=100,
                encoding="base64",
                text_excerpt="from fastapi import FastAPI\napp = FastAPI()\n",
                truncated=False,
            ),
        ]

        pack = build_project_context_pack(
            metadata=metadata,
            readme=readme,
            tree_entries=tree_entries,
            tree_truncated=False,
            files=files,
            read_errors=[],
            language="zh",
        )

        self.assertEqual(pack["repo_metadata"]["full_name"], "owner/repo")
        self.assertEqual(pack["directory_summary"]["top_level_dirs"], ["docs", "src"])
        self.assertEqual(pack["manifest_summary"][0]["path"], "pyproject.toml")
        self.assertIn("fastapi", pack["manifest_summary"][0]["dependencies"])
        self.assertEqual(pack["manifest_summary"][0]["scripts_or_entrypoints"], ["api"])
        self.assertEqual(pack["file_summaries"][0]["path"], "src/app.py")
        self.assertIn("src/app.py 是应用或包入口", pack["file_summaries"][0]["summary"])
        self.assertNotIn("from fastapi import FastAPI", pack["file_summaries"][0]["summary"])
        self.assertEqual(pack["evidence_map"][0]["source_path"], "src/app.py")
        self.assertLessEqual(len(pack["evidence_map"][0]["snippet"]), 300)
