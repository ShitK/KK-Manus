import json
import posixpath
import re
import tomllib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from agent.tools.github_repo_reader import ReadmeContent, RepoFileContent, RepoMetadata, RepoTreeEntry


MAX_MANIFEST_FILES = 3
MAX_SOURCE_FILES = 8
MAX_SUMMARY_CHARS = 800
MAX_SNIPPET_CHARS = 300
MAX_SELECTED_FILE_BYTES = 100_000

MANIFEST_PRIORITY = [
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "go.mod",
    "pom.xml",
    "Cargo.toml",
    "Dockerfile",
    "docker-compose.yml",
]

SKIP_DIRS = {
    ".git",
    ".next",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "tests",
    "test",
    "docs",
    "public",
    "assets",
    "__pycache__",
}

SKIP_SUFFIXES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".mov",
}

SOURCE_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".rb",
    ".php",
}

ENTRYPOINT_NAMES = {
    "main.py",
    "app.py",
    "api.py",
    "server.py",
    "index.ts",
    "index.tsx",
    "index.js",
    "main.ts",
    "main.go",
}

CORE_DIRS = ("src", "app", "backend", "frontend", "server", "api", "lib", "components")
STRUCTURE_SKIP_DIRS = {
    ".git",
    ".next",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}


@dataclass(frozen=True)
class RepoFileSelection:
    manifest_paths: List[str]
    source_paths: List[str]


def _path_parts(path: str) -> List[str]:
    return [part for part in path.split("/") if part]


def _is_skipped_path(path: str) -> bool:
    parts = _path_parts(path)
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return True
    basename = posixpath.basename(path).lower()
    if basename == ".env" or basename.startswith(".env."):
        return True
    lower_path = path.lower()
    return any(lower_path.endswith(suffix) for suffix in SKIP_SUFFIXES)


def _manifest_rank(path: str) -> Optional[int]:
    name = posixpath.basename(path)
    for index, candidate in enumerate(MANIFEST_PRIORITY):
        if name == candidate:
            return index
    return None


def _is_selectable_blob(entry: RepoTreeEntry) -> bool:
    return (
        entry.type == "blob"
        and not _is_skipped_path(entry.path)
        and (entry.size is None or entry.size <= MAX_SELECTED_FILE_BYTES)
    )


def _source_rank(path: str) -> Optional[tuple[int, int, int, str]]:
    if _is_skipped_path(path):
        return None
    name = posixpath.basename(path)
    suffix = posixpath.splitext(name)[1]
    if suffix not in SOURCE_SUFFIXES:
        return None

    parts = _path_parts(path)
    top_level = parts[0] if parts else ""
    entry_bonus = 0 if name in ENTRYPOINT_NAMES else 1
    core_bonus = CORE_DIRS.index(top_level) if top_level in CORE_DIRS else len(CORE_DIRS)
    depth = len(parts)
    return (entry_bonus, core_bonus, depth, path)


def select_repository_files(entries: List[RepoTreeEntry], primary_language: str = "") -> RepoFileSelection:
    """Select small manifest and source files; primary_language is reserved for later ranking refinement."""
    blobs = [entry.path for entry in entries if _is_selectable_blob(entry)]

    manifest_paths = sorted(
        [path for path in blobs if _manifest_rank(path) is not None],
        key=lambda path: (_manifest_rank(path) if _manifest_rank(path) is not None else 99, path.count("/"), path),
    )[:MAX_MANIFEST_FILES]

    ranked_sources = []
    for path in blobs:
        if path in manifest_paths or posixpath.basename(path).lower().startswith("readme"):
            continue
        rank = _source_rank(path)
        if rank is not None:
            ranked_sources.append((rank, path))

    source_paths = [path for _, path in sorted(ranked_sources, key=lambda item: item[0])[:MAX_SOURCE_FILES]]
    return RepoFileSelection(manifest_paths=manifest_paths, source_paths=source_paths)


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    return text[:limit]


def _top_level_dirs(entries: Iterable[RepoTreeEntry]) -> List[str]:
    dirs = sorted(
        {
            entry.path.split("/", 1)[0]
            for entry in entries
            if "/" in entry.path and entry.path.split("/", 1)[0] not in STRUCTURE_SKIP_DIRS
        }
    )
    return dirs[:20]


def _notable_paths(entries: Iterable[RepoTreeEntry]) -> List[str]:
    paths = []
    for entry in entries:
        if entry.type != "blob" or _is_skipped_path(entry.path):
            continue
        if _manifest_rank(entry.path) is not None or _source_rank(entry.path) is not None:
            paths.append(entry.path)
    return sorted(paths)[:30]


def _manifest_ecosystem(path: str) -> str:
    name = posixpath.basename(path)
    if name in {"pyproject.toml", "requirements.txt"}:
        return "python"
    if name == "package.json":
        return "node"
    if name == "go.mod":
        return "go"
    if name == "pom.xml":
        return "java"
    if name == "Cargo.toml":
        return "rust"
    if name in {"Dockerfile", "docker-compose.yml"}:
        return "container"
    return "unknown"


def _manifest_dependencies(file_content: RepoFileContent) -> List[str]:
    # Slice 2 parses package.json, pyproject.toml, and requirements.txt only.
    text = file_content.text_excerpt
    name = posixpath.basename(file_content.path)
    try:
        if name == "package.json":
            payload = json.loads(text)
            deps = []
            for field in ("dependencies", "devDependencies"):
                value = payload.get(field)
                if isinstance(value, dict):
                    deps.extend(str(item) for item in value.keys())
            return deps[:20]
        if name == "pyproject.toml":
            payload = tomllib.loads(text)
            project = payload.get("project") if isinstance(payload, dict) else {}
            deps = project.get("dependencies") if isinstance(project, dict) else []
            return [str(item).split(" ", 1)[0] for item in deps[:20] if isinstance(item, str)]
        if name == "requirements.txt":
            deps = []
            for line in text.splitlines():
                cleaned = line.strip()
                if cleaned and not cleaned.startswith("#") and not cleaned.startswith("-") and "://" not in cleaned:
                    deps.append(re.split(r"[<>=~!]", cleaned, maxsplit=1)[0].strip())
            return deps[:20]
    except Exception:
        return []
    return []


def _manifest_scripts_or_entrypoints(file_content: RepoFileContent) -> List[str]:
    text = file_content.text_excerpt
    name = posixpath.basename(file_content.path)
    try:
        if name == "package.json":
            payload = json.loads(text)
            scripts = payload.get("scripts")
            if isinstance(scripts, dict):
                return [str(item) for item in list(scripts.keys())[:5]]
        if name == "pyproject.toml":
            payload = tomllib.loads(text)
            project = payload.get("project") if isinstance(payload, dict) else {}
            scripts = project.get("scripts") if isinstance(project, dict) else {}
            if isinstance(scripts, dict):
                return [str(item) for item in list(scripts.keys())[:5]]
    except Exception:
        return []
    return []


def _important_symbols(text: str) -> List[str]:
    symbols = []
    patterns = [
        r"^class\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^export\s+(?:default\s+)?(?:function|class|const)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^function\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for line in text.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line.strip())
            if match and match.group(1) not in symbols:
                symbols.append(match.group(1))
        if len(symbols) >= 8:
            break
    return symbols


def _file_role(path: str) -> str:
    name = posixpath.basename(path)
    if name in ENTRYPOINT_NAMES:
        return "application or package entrypoint"
    if "api" in path.lower():
        return "api boundary"
    if "component" in path.lower():
        return "frontend component"
    return "source file"


def _file_role_label(role: str, language: str) -> str:
    if language != "zh":
        return role
    labels = {
        "application or package entrypoint": "应用或包入口",
        "api boundary": "API 边界",
        "frontend component": "前端组件",
        "source file": "source file",
    }
    return labels.get(role, role)


def _file_summary(
    path: str,
    role: str,
    symbols: List[str],
    size: int,
    truncated: bool,
    language: str = "en",
) -> str:
    if language == "zh":
        symbol_text = "、".join(symbols[:4]) if symbols else "未检测到顶层符号"
        size_text = f"{size} 字节" if size else "大小未知"
        truncation_text = " 获取到的 excerpt 已截断。" if truncated else ""
        return _truncate(
            f"{path} 是{_file_role_label(role, language)}（{size_text}），识别到 {symbol_text}。{truncation_text}",
            MAX_SUMMARY_CHARS,
        )

    symbol_text = ", ".join(symbols[:4]) if symbols else "no top-level symbols detected"
    size_text = f"{size} bytes" if size else "unknown size"
    article = "an" if role[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
    truncation_text = " The fetched excerpt was truncated." if truncated else ""
    return _truncate(
        f"{path} is {article} {role} ({size_text}) with {symbol_text}.{truncation_text}",
        MAX_SUMMARY_CHARS,
    )


def build_project_context_pack(
    metadata: RepoMetadata,
    readme: Optional[ReadmeContent],
    tree_entries: List[RepoTreeEntry],
    tree_truncated: bool,
    files: List[RepoFileContent],
    read_errors: List[Dict[str, Any]],
    language: str = "en",
) -> Dict[str, Any]:
    is_zh = language == "zh"
    manifest_files = [file for file in files if _manifest_rank(file.path) is not None and not file.skipped]
    source_files = [file for file in files if _manifest_rank(file.path) is None and not file.skipped]

    manifest_summary = []
    for file in manifest_files:
        deps = _manifest_dependencies(file)
        scripts_or_entrypoints = _manifest_scripts_or_entrypoints(file)
        manifest_summary.append(
            {
                "path": file.path,
                "ecosystem": _manifest_ecosystem(file.path),
                "dependencies": deps,
                "scripts_or_entrypoints": scripts_or_entrypoints,
                "summary": _truncate(
                    (
                        f"{_manifest_ecosystem(file.path)} manifest，检测到 {len(deps)} 个依赖。"
                        if is_zh
                        else f"{_manifest_ecosystem(file.path)} manifest with {len(deps)} detected dependencies."
                    ),
                    MAX_SUMMARY_CHARS,
                ),
            }
        )

    evidence_map = []
    file_summaries = []
    for file in source_files[:MAX_SOURCE_FILES]:
        snippet = _truncate(file.text_excerpt, MAX_SNIPPET_CHARS)
        evidence_id = f"src:{file.path}#snippet-1"
        role = _file_role(file.path)
        symbols = _important_symbols(file.text_excerpt)
        evidence_map.append(
            {
                "id": evidence_id,
                "claim": (
                    f"{file.path} 包含面试相关源码。"
                    if is_zh
                    else f"{file.path} contains interview-relevant source code."
                ),
                "source_type": "source",
                "source_path": file.path,
                "snippet": snippet,
                "confidence": "medium",
            }
        )
        file_summaries.append(
            {
                "path": file.path,
                "role": role,
                "important_symbols": symbols,
                "summary": _file_summary(file.path, role, symbols, file.size, file.truncated, language),
                "evidence_snippets": [{"id": evidence_id, "text": snippet}],
                "interview_relevance": (
                    ["架构证据", "实现细节"]
                    if is_zh
                    else ["architecture evidence", "implementation detail"]
                ),
                "confidence": "medium",
            }
        )

    architecture_signals = [
        {
            "claim": (
                f"仓库主要语言是 {metadata.primary_language or 'unknown'}。"
                if is_zh
                else f"Repository primary language is {metadata.primary_language or 'unknown'}."
            ),
            "evidence_refs": [],
            "confidence": "medium" if metadata.primary_language else "low",
        }
    ]
    if evidence_map:
        architecture_signals.append(
            {
                "claim": (
                    "已选 source file 为后续面试分析提供实现证据。"
                    if is_zh
                    else "Selected source files provide implementation evidence for later interview analysis."
                ),
                "evidence_refs": [evidence_map[0]["id"]],
                "confidence": "medium",
            }
        )

    open_questions = [
        (
            "Slice 2 使用确定性启发式规则，尚未进行 LLM 架构分析。"
            if is_zh
            else "Slice 2 uses deterministic heuristics and has not performed LLM architecture analysis yet."
        )
    ]
    if tree_truncated:
        open_questions.append(
            "GitHub tree 响应被截断，文件选择可能不完整。"
            if is_zh
            else "GitHub tree response was truncated; file selection may be incomplete."
        )
    for error in read_errors:
        code = error.get("code")
        path = error.get("path")
        if code and path:
            open_questions.append(
                f"无法读取 {path}: {code}。"
                if is_zh
                else f"Could not read {path}: {code}."
            )

    return {
        "repo_metadata": metadata.to_dict(),
        "readme_summary": {
            "summary": _truncate(readme.text_excerpt, 1200) if readme else "",
            "confidence": "medium" if readme else "low",
            "max_chars": 1200,
        },
        "manifest_summary": manifest_summary,
        "directory_summary": {
            "top_level_dirs": _top_level_dirs(tree_entries),
            "notable_paths": _notable_paths(tree_entries),
            "total_entries": len(tree_entries),
            "truncated": tree_truncated,
            "summary": _truncate(
                (
                    f"仓库目录树包含 {len(tree_entries)} 个条目和 {len(_top_level_dirs(tree_entries))} 个顶层源码/文档区域。"
                    if is_zh
                    else f"Repository tree includes {len(tree_entries)} entries and {len(_top_level_dirs(tree_entries))} top-level source/documentation areas."
                ),
                MAX_SUMMARY_CHARS,
            ),
        },
        "file_summaries": file_summaries,
        "architecture_signals": architecture_signals[:12],
        "evidence_map": evidence_map[:40],
        "open_questions": open_questions,
    }
