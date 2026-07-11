import base64
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from agent.tools.github_repo_reader import (
    GitHubRepoReader,
    GitHubRepoError,
    NoRedirectHandler,
    RepoFileContent,
    RepoTreeEntry,
    default_get_json,
    parse_github_url,
    normalize_repo_path,
)


class GitHubRepoUrlParserTest(unittest.TestCase):
    def test_parse_plain_repo_url(self):
        parsed = parse_github_url("https://github.com/tiangolo/fastapi")

        self.assertEqual(parsed.owner, "tiangolo")
        self.assertEqual(parsed.repo, "fastapi")
        self.assertIsNone(parsed.ref)
        self.assertIsNone(parsed.path)
        self.assertEqual(parsed.source_kind, "repo")

    def test_parse_tree_url_with_simple_branch(self):
        parsed = parse_github_url("https://github.com/owner/repo/tree/main")

        self.assertEqual(parsed.owner, "owner")
        self.assertEqual(parsed.repo, "repo")
        self.assertEqual(parsed.ref, "main")
        self.assertIsNone(parsed.path)
        self.assertEqual(parsed.source_kind, "tree")

    def test_parse_blob_url_with_path(self):
        parsed = parse_github_url("https://github.com/owner/repo/blob/main/README.md")

        self.assertEqual(parsed.owner, "owner")
        self.assertEqual(parsed.repo, "repo")
        self.assertEqual(parsed.ref, "main")
        self.assertEqual(parsed.path, "README.md")
        self.assertEqual(parsed.source_kind, "blob")

    def test_rejects_non_https(self):
        with self.assertRaises(GitHubRepoError) as context:
            parse_github_url("http://github.com/owner/repo")

        self.assertEqual(context.exception.code, "invalid_github_url")
        self.assertIn("https", context.exception.message)

    def test_rejects_non_github_host(self):
        with self.assertRaises(GitHubRepoError) as context:
            parse_github_url("https://evil.example/owner/repo")

        self.assertEqual(context.exception.code, "invalid_github_url")

    def test_rejects_missing_repo(self):
        with self.assertRaises(GitHubRepoError) as context:
            parse_github_url("https://github.com/owner")

        self.assertEqual(context.exception.code, "invalid_github_url")

    def test_rejects_invalid_owner_or_repo_boundaries(self):
        for value in ("https://github.com/-owner/repo", "https://github.com/owner/repo-"):
            with self.subTest(value=value):
                with self.assertRaises(GitHubRepoError) as context:
                    parse_github_url(value)

                self.assertEqual(context.exception.code, "invalid_github_url")

    def test_rejects_path_traversal_even_when_encoded(self):
        for value in ("../secret", "src/%2e%2e/secret", "/absolute/path"):
            with self.subTest(value=value):
                with self.assertRaises(GitHubRepoError) as context:
                    normalize_repo_path(value, "path")

                self.assertEqual(context.exception.code, "invalid_github_url")

    def test_rejects_control_characters(self):
        with self.assertRaises(GitHubRepoError) as context:
            parse_github_url("https://github.com/owner/repo%0aevil")

        self.assertEqual(context.exception.code, "invalid_github_url")


class GitHubRepoReaderTest(unittest.TestCase):
    def test_fetch_metadata_maps_github_response(self):
        calls = []

        def fake_get_json(url, resource_type="repo"):
            calls.append((url, resource_type))
            return {
                "name": "fastapi",
                "full_name": "tiangolo/fastapi",
                "owner": {"login": "tiangolo"},
                "default_branch": "master",
                "description": "FastAPI framework",
                "language": "Python",
                "stargazers_count": 90000,
                "html_url": "https://github.com/tiangolo/fastapi",
                "private": False,
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        metadata = reader.fetch_metadata(parse_github_url("https://github.com/tiangolo/fastapi"))

        self.assertEqual(calls, [("https://api.github.com/repos/tiangolo/fastapi", "repo")])
        self.assertEqual(metadata.owner, "tiangolo")
        self.assertEqual(metadata.repo, "fastapi")
        self.assertEqual(metadata.default_branch, "master")
        self.assertEqual(metadata.primary_language, "Python")
        self.assertEqual(metadata.stars, 90000)
        self.assertFalse(metadata.is_private)

    def test_fetch_metadata_carries_private_repo_flag(self):
        def fake_get_json(url, resource_type="repo"):
            return {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
                "default_branch": "main",
                "private": True,
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        metadata = reader.fetch_metadata(parse_github_url("https://github.com/owner/repo"))

        self.assertTrue(metadata.is_private)
        self.assertTrue(metadata.to_dict()["is_private"])

    def test_fetch_readme_decodes_base64_and_truncates_excerpt(self):
        readme_text = "# Demo\n" + ("hello " * 600)

        def fake_get_json(url, resource_type="repo"):
            self.assertEqual(url, "https://api.github.com/repos/owner/repo/readme?ref=main")
            self.assertEqual(resource_type, "readme")
            return {
                "path": "README.md",
                "size": len(readme_text),
                "encoding": "base64",
                "content": base64.b64encode(readme_text.encode("utf-8")).decode("ascii"),
            }

        reader = GitHubRepoReader(get_json=fake_get_json, readme_excerpt_chars=1800)
        readme = reader.fetch_readme(parse_github_url("https://github.com/owner/repo"), default_branch="main")

        self.assertIsNotNone(readme)
        self.assertEqual(readme.path, "README.md")
        self.assertLessEqual(len(readme.text_excerpt), 1800)
        self.assertTrue(readme.truncated)
        self.assertIn("# Demo", readme.text_excerpt)

    def test_fetch_readme_returns_none_for_missing_readme(self):
        def fake_get_json(url, resource_type="repo"):
            raise GitHubRepoError("readme_not_found", "README not found", retryable=False)

        reader = GitHubRepoReader(get_json=fake_get_json)
        readme = reader.fetch_readme(parse_github_url("https://github.com/owner/repo"), default_branch="main")

        self.assertIsNone(readme)

    def test_fetch_tree_maps_recursive_tree_entries(self):
        def fake_get_json(url, resource_type="repo"):
            self.assertEqual(url, "https://api.github.com/repos/owner/repo/git/trees/main?recursive=1")
            self.assertEqual(resource_type, "tree")
            return {
                "truncated": False,
                "tree": [
                    {"path": "pyproject.toml", "type": "blob", "size": 500},
                    {"path": "src", "type": "tree"},
                    {"path": "src/app.py", "type": "blob", "size": 1200},
                ],
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        entries, truncated = reader.fetch_tree(parse_github_url("https://github.com/owner/repo"), ref="main")

        self.assertFalse(truncated)
        self.assertEqual([entry.path for entry in entries], ["pyproject.toml", "src", "src/app.py"])
        self.assertEqual(entries[0].type, "blob")
        self.assertEqual(entries[0].size, 500)

    def test_fetch_tree_locally_truncates_after_max_entries(self):
        tree = [
            {"path": f"src/module_{index}.py", "type": "blob", "size": index}
            for index in range(1001)
        ]

        def fake_get_json(url, resource_type="repo"):
            return {
                "truncated": False,
                "tree": tree,
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        entries, truncated = reader.fetch_tree(parse_github_url("https://github.com/owner/repo"), ref="main")

        self.assertEqual(len(entries), 1000)
        self.assertTrue(truncated)
        self.assertEqual(entries[-1].path, "src/module_999.py")

    def test_default_get_json_accepts_tree_response_above_generic_response_limit(self):
        tree = [
            {
                "path": f"src/packages/{index:04d}/" + ("nested_module_name/" * 3) + "implementation.py",
                "mode": "100644",
                "type": "blob",
                "sha": "a" * 40,
                "size": 1234,
                "url": f"https://api.github.com/repos/owner/repo/git/blobs/{index:04d}",
            }
            for index in range(1000)
        ]
        body = json.dumps({"truncated": False, "tree": tree}).encode("utf-8")
        self.assertGreater(len(body), 200_000)

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return body[:size]

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse()

        with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
            payload = default_get_json("https://api.github.com/repos/owner/repo/git/trees/main?recursive=1", "tree")

        self.assertEqual(len(payload["tree"]), 1000)

    def test_fetch_file_content_decodes_base64_and_truncates(self):
        content = "from fastapi import FastAPI\n" + ("app = FastAPI()\n" * 700)

        def fake_get_json(url, resource_type="repo"):
            self.assertEqual(url, "https://api.github.com/repos/owner/repo/contents/src/app.py?ref=main")
            self.assertEqual(resource_type, "file")
            return {
                "path": "src/app.py",
                "type": "file",
                "size": len(content),
                "encoding": "base64",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        file_content = reader.fetch_file_content(
            parse_github_url("https://github.com/owner/repo"),
            path="src/app.py",
            ref="main",
        )

        self.assertEqual(file_content.path, "src/app.py")
        self.assertIn("from fastapi", file_content.text_excerpt)
        self.assertTrue(file_content.truncated)
        self.assertFalse(file_content.skipped)

    def test_fetch_file_content_skips_oversized_files_before_decode(self):
        def fake_get_json(url, resource_type="repo"):
            return {
                "path": "src/large.py",
                "type": "file",
                "size": 100_001,
                "encoding": "base64",
                "content": "",
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        file_content = reader.fetch_file_content(
            parse_github_url("https://github.com/owner/repo"),
            path="src/large.py",
            ref="main",
        )

        self.assertTrue(file_content.skipped)
        self.assertEqual(file_content.skip_reason, "file_too_large")
        self.assertEqual(file_content.text_excerpt, "")

    def test_fetch_file_content_skips_binary_file_disguised_as_source(self):
        binary_content = b"\x00\x01\x02\x03not really python"

        def fake_get_json(url, resource_type="repo"):
            return {
                "path": "src/app.py",
                "type": "file",
                "size": len(binary_content),
                "encoding": "base64",
                "content": base64.b64encode(binary_content).decode("ascii"),
            }

        reader = GitHubRepoReader(get_json=fake_get_json)
        file_content = reader.fetch_file_content(
            parse_github_url("https://github.com/owner/repo"),
            path="src/app.py",
            ref="main",
        )

        self.assertTrue(file_content.skipped)
        self.assertEqual(file_content.skip_reason, "non_text_file")
        self.assertEqual(file_content.text_excerpt, "")

    def test_fetch_file_content_rejects_directory_response(self):
        def fake_get_json(url, resource_type="repo"):
            return {"path": "src", "type": "dir"}

        reader = GitHubRepoReader(get_json=fake_get_json)

        with self.assertRaises(GitHubRepoError) as context:
            reader.fetch_file_content(
                parse_github_url("https://github.com/owner/repo"),
                path="src",
                ref="main",
            )

        self.assertEqual(context.exception.code, "invalid_github_response")

    def test_http_errors_are_mapped_to_user_safe_codes(self):
        error = HTTPError(
            url="https://api.github.com/repos/owner/repo",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        mapped = GitHubRepoReader.map_http_error(error, resource_type="repo")

        self.assertEqual(mapped.code, "repo_not_found")
        self.assertFalse(mapped.retryable)
        self.assertIn("public", mapped.message)

    def test_readme_404_maps_to_readme_not_found(self):
        error = HTTPError(
            url="https://api.github.com/repos/owner/repo/readme?ref=main",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

        mapped = GitHubRepoReader.map_http_error(error, resource_type="readme")

        self.assertEqual(mapped.code, "readme_not_found")
        self.assertFalse(mapped.retryable)

    def test_invalid_base64_is_rejected(self):
        def fake_get_json(url, resource_type="repo"):
            return {
                "path": "README.md",
                "size": 20,
                "encoding": "base64",
                "content": "not valid base64!!",
            }

        reader = GitHubRepoReader(get_json=fake_get_json)

        with self.assertRaises(GitHubRepoError) as context:
            reader.fetch_readme(parse_github_url("https://github.com/owner/repo"), default_branch="main")

        self.assertEqual(context.exception.code, "invalid_github_response")

    def test_rate_limit_http_errors_are_retryable(self):
        for status_code in (403, 429):
            with self.subTest(status_code=status_code):
                error = HTTPError(
                    url="https://api.github.com/repos/owner/repo",
                    code=status_code,
                    msg="Rate Limited",
                    hdrs=None,
                    fp=None,
                )

                mapped = GitHubRepoReader.map_http_error(error, resource_type="repo")

                self.assertEqual(mapped.code, "rate_limited")
                self.assertTrue(mapped.retryable)

    def test_redirect_handler_rejects_redirects(self):
        handler = NoRedirectHandler()

        with self.assertRaises(GitHubRepoError) as context:
            handler.redirect_request(None, None, 302, "Found", {}, "https://api.github.com/redirected")

        self.assertEqual(context.exception.code, "redirect_not_allowed")
        self.assertFalse(context.exception.retryable)

    def test_default_get_json_rejects_oversized_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b"{" + (b" " * 200_000) + b"}"

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse()

        with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
            with self.assertRaises(GitHubRepoError) as context:
                default_get_json("https://api.github.com/repos/owner/repo")

        self.assertEqual(context.exception.code, "file_too_large")

    def test_default_get_json_rejects_invalid_json_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b"not json"

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse()

        with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
            with self.assertRaises(GitHubRepoError) as context:
                default_get_json("https://api.github.com/repos/owner/repo")

        self.assertEqual(context.exception.code, "invalid_github_response")

    def test_default_get_json_maps_url_errors_to_network_timeout(self):
        class FakeOpener:
            def open(self, request, timeout):
                raise URLError("timed out")

        with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
            with self.assertRaises(GitHubRepoError) as context:
                default_get_json("https://api.github.com/repos/owner/repo")

        self.assertEqual(context.exception.code, "network_timeout")
        self.assertTrue(context.exception.retryable)

    def test_default_get_json_uses_github_token_when_configured(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b'{"ok": true}'

        class FakeOpener:
            def open(self, request, timeout):
                captured_requests.append(request)
                return FakeResponse()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_demo_token"}):
            with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
                default_get_json("https://api.github.com/repos/owner/repo")

        self.assertEqual(captured_requests[0].get_header("Authorization"), "Bearer ghp_demo_token")

    def test_default_get_json_omits_authorization_without_token(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, size=-1):
                return b'{"ok": true}'

        class FakeOpener:
            def open(self, request, timeout):
                captured_requests.append(request)
                return FakeResponse()

        with patch.dict(os.environ, {}, clear=True):
            with patch("agent.tools.github_repo_reader.build_opener", return_value=FakeOpener()):
                default_get_json("https://api.github.com/repos/owner/repo")

        self.assertIsNone(captured_requests[0].get_header("Authorization"))
