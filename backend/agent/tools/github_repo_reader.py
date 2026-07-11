import base64
import binascii
import json
import os
import posixpath
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


GITHUB_HOST = "github.com"
API_HOST = "api.github.com"
USER_AGENT = "KKManus-GitHubInterviewPrep/1.0"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 200_000
MAX_TREE_RESPONSE_BYTES = 1_000_000
MAX_TREE_ENTRIES = 1_000
MAX_FILE_BYTES = 100_000
MAX_FILE_EXCERPT_CHARS = 8_000
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,150}$")
MAX_URL_LENGTH = 2000
MAX_PATH_LENGTH = 500


class GitHubRepoError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class ParsedGitHubUrl:
    owner: str
    repo: str
    ref: Optional[str] = None
    path: Optional[str] = None
    source_kind: str = "repo"


@dataclass(frozen=True)
class RepoMetadata:
    owner: str
    repo: str
    full_name: str
    default_branch: str
    description: str
    primary_language: str
    stars: int
    html_url: str
    is_private: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadmeContent:
    path: str
    size: int
    encoding: str
    text_excerpt: str
    truncated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepoTreeEntry:
    path: str
    type: str
    size: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepoFileContent:
    path: str
    size: int
    encoding: str
    text_excerpt: str
    truncated: bool
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitHubRepoError(
            "redirect_not_allowed",
            "GitHub API redirects are not followed in this tool.",
            retryable=False,
        )


def looks_like_binary(content: bytes) -> bool:
    if not content:
        return False
    if b"\x00" in content:
        return True
    sample = content[:4096]
    control_count = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    return control_count / len(sample) > 0.05


def map_http_error(error: HTTPError, resource_type: str = "repo") -> GitHubRepoError:
    if error.code == 404:
        if resource_type == "readme":
            return GitHubRepoError(
                "readme_not_found",
                "README was not found in this public GitHub repository.",
                retryable=False,
            )
        return GitHubRepoError(
            "repo_not_found",
            "Repository was not found, is private, or is not accessible as a public GitHub repo.",
            retryable=False,
        )
    if error.code in {403, 429}:
        return GitHubRepoError(
            "rate_limited",
            "GitHub rate limit or access limit was reached. Please retry later.",
            retryable=True,
        )
    return GitHubRepoError(
        "github_request_failed",
        f"GitHub request failed with HTTP {error.code}.",
        retryable=True,
    )


def default_get_json(url: str, resource_type: str = "repo") -> Dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    request = Request(
        url,
        headers=headers,
        method="GET",
    )
    opener = build_opener(NoRedirectHandler)
    try:
        with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            response_limit = MAX_TREE_RESPONSE_BYTES if resource_type == "tree" else MAX_RESPONSE_BYTES
            raw_body = response.read(response_limit + 1)
            if len(raw_body) > response_limit:
                raise GitHubRepoError(
                    "file_too_large",
                    "GitHub response exceeded the response size limit.",
                    retryable=False,
                )
            body = raw_body.decode("utf-8")
    except GitHubRepoError:
        raise
    except HTTPError as error:
        raise map_http_error(error, resource_type=resource_type) from error
    except URLError as error:
        raise GitHubRepoError(
            "network_timeout",
            f"GitHub request failed or timed out: {error.reason}",
            retryable=True,
        ) from error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise GitHubRepoError(
            "invalid_github_response",
            "GitHub returned a response that could not be parsed.",
            retryable=True,
        ) from error

    if not isinstance(parsed, dict):
        raise GitHubRepoError(
            "invalid_github_response",
            "GitHub returned an unexpected response shape.",
            retryable=True,
        )
    return parsed


def _reject(message: str) -> None:
    raise GitHubRepoError("invalid_github_url", message, retryable=False)


def _clean_segment(value: str, field_name: str) -> str:
    decoded = unquote(value or "").strip()
    if not decoded or any(ord(char) < 32 for char in decoded):
        _reject(f"{field_name} is invalid.")
    return decoded


def _validate_name(value: str, field_name: str) -> str:
    cleaned = _clean_segment(value, field_name)
    if cleaned in {".", ".."} or not NAME_RE.match(cleaned):
        _reject(f"{field_name} must be a valid GitHub name.")
    if not cleaned[0].isalnum() or not cleaned[-1].isalnum():
        _reject(f"{field_name} must start and end with a letter or number.")
    return cleaned


def normalize_repo_path(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    decoded = unquote(value).strip()
    if not decoded:
        return None
    if len(decoded) > MAX_PATH_LENGTH or any(ord(char) < 32 for char in decoded):
        _reject(f"{field_name} is invalid.")
    if decoded.startswith("/"):
        _reject(f"{field_name} must be relative.")

    parts = [part for part in decoded.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        _reject(f"{field_name} cannot contain path traversal.")

    normalized = posixpath.normpath("/".join(parts))
    if normalized == "." or normalized.startswith("../") or normalized == "..":
        _reject(f"{field_name} cannot escape the repository.")
    return normalized


def _validate_ref(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = normalize_repo_path(value, "ref")
    if cleaned is None:
        return None
    if not REF_RE.match(cleaned):
        _reject("ref contains unsupported characters.")
    return cleaned


def parse_github_url(raw_url: str) -> ParsedGitHubUrl:
    cleaned_url = str(raw_url or "").strip()
    if len(cleaned_url) > MAX_URL_LENGTH:
        _reject("GitHub URL is too long.")
    parsed = urlparse(cleaned_url)
    if parsed.scheme != "https":
        _reject("Only https GitHub URLs are supported.")
    if parsed.netloc.lower() != GITHUB_HOST:
        _reject("Only github.com repository URLs are supported.")

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        _reject("Expected https://github.com/{owner}/{repo}.")

    owner = _validate_name(segments[0], "owner")
    repo = _validate_name(segments[1].removesuffix(".git"), "repo")

    if len(segments) == 2:
        return ParsedGitHubUrl(owner=owner, repo=repo)

    source_kind = _clean_segment(segments[2], "source_kind")
    if source_kind not in {"tree", "blob"}:
        _reject("Only repository, tree, or blob GitHub URLs are supported.")
    if len(segments) < 4:
        _reject(f"{source_kind} URL must include a branch or ref.")

    ref = _validate_ref(segments[3])
    repo_path = normalize_repo_path("/".join(segments[4:]), "path")
    return ParsedGitHubUrl(
        owner=owner,
        repo=repo,
        ref=ref,
        path=repo_path,
        source_kind=source_kind,
    )


class GitHubRepoReader:
    def __init__(
        self,
        get_json: Callable[[str, str], Dict[str, Any]] = default_get_json,
        readme_excerpt_chars: int = 1800,
        summary_chars: int = 600,
    ):
        self.get_json = get_json
        self.readme_excerpt_chars = readme_excerpt_chars
        self.summary_chars = summary_chars

    @staticmethod
    def repo_api_url(parsed: ParsedGitHubUrl) -> str:
        owner = quote(parsed.owner, safe="")
        repo = quote(parsed.repo, safe="")
        return f"https://{API_HOST}/repos/{owner}/{repo}"

    @staticmethod
    def readme_api_url(parsed: ParsedGitHubUrl, ref: str) -> str:
        owner = quote(parsed.owner, safe="")
        repo = quote(parsed.repo, safe="")
        safe_ref = quote(ref, safe="")
        return f"https://{API_HOST}/repos/{owner}/{repo}/readme?ref={safe_ref}"

    @staticmethod
    def tree_api_url(parsed: ParsedGitHubUrl, ref: str) -> str:
        owner = quote(parsed.owner, safe="")
        repo = quote(parsed.repo, safe="")
        safe_ref = quote(ref, safe="")
        return f"https://{API_HOST}/repos/{owner}/{repo}/git/trees/{safe_ref}?recursive=1"

    @staticmethod
    def content_api_url(parsed: ParsedGitHubUrl, path: str, ref: str) -> str:
        owner = quote(parsed.owner, safe="")
        repo = quote(parsed.repo, safe="")
        safe_path = quote(normalize_repo_path(path, "path") or "", safe="/")
        safe_ref = quote(ref, safe="")
        return f"https://{API_HOST}/repos/{owner}/{repo}/contents/{safe_path}?ref={safe_ref}"

    @staticmethod
    def map_http_error(error: HTTPError, resource_type: str = "repo") -> GitHubRepoError:
        return map_http_error(error, resource_type=resource_type)

    def fetch_metadata(self, parsed: ParsedGitHubUrl) -> RepoMetadata:
        payload = self.get_json(self.repo_api_url(parsed), "repo")
        owner = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
        return RepoMetadata(
            owner=str(owner.get("login") or parsed.owner),
            repo=str(payload.get("name") or parsed.repo),
            full_name=str(payload.get("full_name") or f"{parsed.owner}/{parsed.repo}"),
            default_branch=str(payload.get("default_branch") or parsed.ref or "main"),
            description=str(payload.get("description") or ""),
            primary_language=str(payload.get("language") or ""),
            stars=int(payload.get("stargazers_count") or 0),
            html_url=str(payload.get("html_url") or f"https://github.com/{parsed.owner}/{parsed.repo}"),
            is_private=bool(payload.get("private")),
        )

    def fetch_readme(self, parsed: ParsedGitHubUrl, default_branch: Optional[str] = None) -> Optional[ReadmeContent]:
        ref = parsed.ref or default_branch or "main"
        try:
            payload = self.get_json(self.readme_api_url(parsed, ref), "readme")
        except GitHubRepoError as error:
            if error.code == "readme_not_found":
                return None
            raise

        encoding = str(payload.get("encoding") or "")
        content = str(payload.get("content") or "")
        if encoding != "base64" or not content:
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub README response did not include base64 content.",
                retryable=True,
            )

        clean_content = "".join(content.split())
        try:
            decoded = base64.b64decode(clean_content.encode("ascii"), validate=True)
        except (binascii.Error, ValueError) as error:
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub README response contained invalid base64 content.",
                retryable=True,
            ) from error

        text = decoded.decode("utf-8", errors="replace")
        excerpt = text[: self.readme_excerpt_chars]
        return ReadmeContent(
            path=str(payload.get("path") or "README"),
            size=int(payload.get("size") or len(text)),
            encoding=encoding,
            text_excerpt=excerpt,
            truncated=len(text) > len(excerpt),
        )

    def fetch_tree(self, parsed: ParsedGitHubUrl, ref: str) -> Tuple[List[RepoTreeEntry], bool]:
        payload = self.get_json(self.tree_api_url(parsed, ref), "tree")
        raw_entries = payload.get("tree")
        if not isinstance(raw_entries, list):
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub tree response did not include a tree list.",
                retryable=True,
            )

        raw_truncated = bool(payload.get("truncated"))
        limited_entries = raw_entries[:MAX_TREE_ENTRIES]
        entries: List[RepoTreeEntry] = []
        for item in limited_entries:
            if not isinstance(item, dict):
                continue
            path = normalize_repo_path(str(item.get("path") or ""), "path")
            entry_type = str(item.get("type") or "")
            if not path or entry_type not in {"blob", "tree"}:
                continue
            size = item.get("size")
            entries.append(
                RepoTreeEntry(
                    path=path,
                    type=entry_type,
                    size=int(size) if isinstance(size, int) else None,
                )
            )
        return entries, raw_truncated or len(raw_entries) > MAX_TREE_ENTRIES

    def fetch_file_content(self, parsed: ParsedGitHubUrl, path: str, ref: str) -> RepoFileContent:
        normalized_path = normalize_repo_path(path, "path")
        if not normalized_path:
            raise GitHubRepoError("invalid_github_url", "file path is required.", retryable=False)

        payload = self.get_json(self.content_api_url(parsed, normalized_path, ref), "file")
        if payload.get("type") != "file":
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub content response did not describe a file.",
                retryable=True,
            )

        size = int(payload.get("size") or 0)
        if size > MAX_FILE_BYTES:
            return RepoFileContent(
                path=str(payload.get("path") or normalized_path),
                size=size,
                encoding=str(payload.get("encoding") or ""),
                text_excerpt="",
                truncated=True,
                skipped=True,
                skip_reason="file_too_large",
            )

        encoding = str(payload.get("encoding") or "")
        content = str(payload.get("content") or "")
        if encoding != "base64" or not content:
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub file response did not include base64 content.",
                retryable=True,
            )

        clean_content = "".join(content.split())
        try:
            decoded = base64.b64decode(clean_content.encode("ascii"), validate=True)
        except (binascii.Error, ValueError) as error:
            raise GitHubRepoError(
                "invalid_github_response",
                "GitHub file response contained invalid base64 content.",
                retryable=True,
            ) from error

        if looks_like_binary(decoded):
            return RepoFileContent(
                path=str(payload.get("path") or normalized_path),
                size=size or len(decoded),
                encoding=encoding,
                text_excerpt="",
                truncated=False,
                skipped=True,
                skip_reason="non_text_file",
            )

        text = decoded.decode("utf-8", errors="replace")
        excerpt = text[:MAX_FILE_EXCERPT_CHARS]
        return RepoFileContent(
            path=str(payload.get("path") or normalized_path),
            size=size or len(text),
            encoding=encoding,
            text_excerpt=excerpt,
            truncated=len(text) > len(excerpt),
        )

    def make_readme_summary(self, readme: Optional[ReadmeContent]) -> Dict[str, Any]:
        if readme is None:
            return {
                "summary": "",
                "confidence": "low",
                "max_chars": self.summary_chars,
            }
        return {
            "summary": readme.text_excerpt[: self.summary_chars],
            "confidence": "medium",
            "max_chars": self.summary_chars,
        }
