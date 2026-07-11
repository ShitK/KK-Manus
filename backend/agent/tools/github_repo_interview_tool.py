import json
import logging
from typing import Any, Dict, Optional

from agent.tools.github_repo_context import build_project_context_pack, select_repository_files
from agent.tools.github_repo_interview_intent import normalize_language
from agent.tools.github_repo_questions import build_interview_questions
from agent.tools.github_repo_reader import GitHubRepoError, GitHubRepoReader, parse_github_url
from agentpress.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


class GitHubRepoInterviewPrepTool(Tool):
    """Prepare interview context from a public GitHub repository.

    The tool is intentionally read-only and low-risk: it parses a public GitHub URL,
    reads repository metadata, README, tree, and selected small files through GitHub
    API, and returns a structured envelope for the right-side tool panel. It does
    not clone, execute code, read local files, or persist data.
    """

    def __init__(self, reader: Optional[GitHubRepoReader] = None):
        super().__init__()
        self.reader = reader or GitHubRepoReader()

    def _json_result(self, payload: Dict[str, Any], success: bool = True) -> ToolResult:
        return ToolResult(success=success, output=json.dumps(payload, ensure_ascii=False, indent=2))

    def _step(self, step_id: str, label: str, status: str, detail: str = "") -> Dict[str, str]:
        return {"id": step_id, "label": label, "status": status, "detail": detail}

    def _error(self, error: GitHubRepoError) -> Dict[str, Any]:
        return {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        }

    def _question_markdown(
        self,
        questions: list[Dict[str, Any]],
        has_source_evidence: bool,
        language: str,
    ) -> str:
        if language == "en":
            evidence_note = (
                "Generated deterministically from repository source evidence, manifests, and directory context."
                if has_source_evidence
                else "Generated deterministically from repository metadata, manifests, and directory context; source evidence is limited."
            )
            lines = [
                "## Mock Interview Questions (Repository Evidence)",
                "",
                f"{evidence_note} These questions are not a full multi-agent analysis or LLM deep architecture review.",
            ]
            direction_label = "Direction"
            evidence_label = "Evidence"
            evidence_detail_label = "Evidence details"
            why_label = "Why it matters"
        else:
            evidence_note = (
                "基于已读取的仓库源码证据、manifest 和目录信息确定性生成。"
                if has_source_evidence
                else "基于已读取的仓库元数据、manifest 和目录信息确定性生成；源码证据不足。"
            )
            lines = [
                "## 模拟面试问题（基于仓库内容）",
                "",
                f"{evidence_note}这些问题不是完整多智能体分析或 LLM 深度架构审查结果。",
            ]
            direction_label = "答题方向"
            evidence_label = "证据"
            evidence_detail_label = "证据详情"
            why_label = "为什么相关"

        for question in questions:
            refs = ", ".join(question.get("evidence_refs") or question.get("source_paths") or [])
            lines.extend(
                [
                    "",
                    f"### {question.get('id')}. {question.get('question')}",
                    f"- {direction_label}: {question.get('answer_direction')}",
                    f"- {evidence_label}: {refs or 'limited repository context'}",
                ]
            )
            details = question.get("evidence_details") or []
            if details:
                lines.append(f"- {evidence_detail_label}:")
                for detail in details[:3]:
                    source_path = detail.get("source_path") or "repository evidence"
                    evidence_type = detail.get("evidence_type") or "evidence"
                    readable = detail.get("summary") or detail.get("snippet") or ""
                    why = detail.get("why_it_matters") or ""
                    lines.append(f"  - {source_path} ({evidence_type}): {readable}")
                    if why:
                        lines.append(f"    {why_label}: {why}")
        return "\n".join(lines)

    def _base_payload(
        self,
        github_url: str,
        target_role: str,
        difficulty: str,
        question_count: Any,
        language: str,
    ) -> Dict[str, Any]:
        return {
            "tool": "github_repo_interview_prep",
            "type": "github_repo_interview_prep",
            "version": "v1",
            "status": "success",
            "partial": False,
            "steps": [],
            "input": {
                "github_url": str(github_url or "").strip(),
                "target_role": str(target_role or "").strip(),
                "difficulty": difficulty,
                "question_count": question_count,
                "language": language,
            },
            "data": {},
            "errors": [],
            "warnings": [],
        }

    def _validation_failure(self, payload: Dict[str, Any], code: str, message: str) -> ToolResult:
        error = GitHubRepoError(code, message, retryable=False)
        payload["status"] = "error"
        payload["partial"] = False
        payload["errors"].append(self._error(error))
        return self._json_result(payload, success=False)

    def _validate_inputs(self, payload: Dict[str, Any]) -> Optional[ToolResult]:
        if not payload["input"]["github_url"]:
            return self._validation_failure(payload, "invalid_github_url", "github_url is required.")
        if payload["input"]["difficulty"] not in {"junior", "mid", "senior"}:
            return self._validation_failure(
                payload,
                "invalid_difficulty",
                "difficulty must be one of: junior, mid, senior.",
            )
        try:
            normalized_question_count = int(payload["input"]["question_count"])
        except (TypeError, ValueError):
            return self._validation_failure(
                payload,
                "invalid_question_count",
                "question_count must be an integer between 1 and 10.",
            )
        if normalized_question_count < 1 or normalized_question_count > 10:
            return self._validation_failure(
                payload,
                "invalid_question_count",
                "question_count must be an integer between 1 and 10.",
            )
        payload["input"]["question_count"] = normalized_question_count
        if payload["input"]["language"] not in {"zh", "en"}:
            return self._validation_failure(payload, "invalid_language", "language must be one of: zh, en.")
        return None

    async def github_repo_interview_prep(
        self,
        github_url: str,
        target_role: str = "software engineer",
        difficulty: str = "mid",
        question_count: int = 4,
        language: str = "zh",
    ) -> ToolResult:
        """Read public GitHub repo context and generate evidence-backed interview questions.

        The tool reads metadata, README, repository tree, selected manifest files,
        and selected small source files to build a bounded project context pack,
        then generates structured, evidence-backed interview questions from that
        context pack.

        Args:
            github_url: Public GitHub repository URL.
            target_role: Target interview role.
            difficulty: One of "junior", "mid", "senior"; affects wording and answer direction.
            question_count: Desired question count, 1-10.
            language: Output language, "zh" or "en"; common aliases like "中文" are normalized to "zh".

        Returns:
            ToolResult with a structured JSON envelope for the tool panel.
        """
        normalized_language, _ = normalize_language(language)
        language = normalized_language or language
        payload = self._base_payload(github_url, target_role, difficulty, question_count, language)
        validation_error = self._validate_inputs(payload)
        if validation_error:
            return validation_error

        metadata = None
        tree_entries = []
        tree_truncated = False
        selected_files = []
        read_errors = []
        try:
            parsed = parse_github_url(github_url)
            payload["steps"].append(
                self._step("parse_url", "Parse GitHub URL", "success", f"{parsed.owner}/{parsed.repo}")
            )
            metadata = self.reader.fetch_metadata(parsed)
            snapshot_ref = parsed.ref or metadata.default_branch
            payload["steps"].append(
                self._step(
                    "fetch_metadata",
                    "Fetch repository metadata",
                    "success",
                    f"default branch: {metadata.default_branch}",
                )
            )
            if getattr(metadata, "is_private", False):
                error = GitHubRepoError(
                    "private_repo_not_supported",
                    "This tool only supports public GitHub repositories.",
                    retryable=False,
                )
                payload["status"] = "error"
                payload["partial"] = False
                payload["steps"].append(
                    self._step("enforce_public_repo", "Enforce public repository boundary", "error", error.message)
                )
                payload["errors"].append(self._error(error))
                return self._json_result(payload, success=False)

            readme = self.reader.fetch_readme(parsed, default_branch=snapshot_ref)

            try:
                tree_entries, tree_truncated = self.reader.fetch_tree(parsed, ref=snapshot_ref)
            except GitHubRepoError as tree_error:
                payload["status"] = "partial"
                payload["partial"] = True
                payload["errors"].append(
                    {
                        "code": tree_error.code,
                        "message": tree_error.message,
                        "retryable": tree_error.retryable,
                        "step": "inspect_tree",
                    }
                )
                tree_entries = []
                tree_truncated = False
            payload["steps"].append(
                self._step(
                    "inspect_tree",
                    "Inspect repository tree",
                    "partial" if tree_truncated or not tree_entries else "success",
                    f"{len(tree_entries)} entries" if tree_entries else "tree unavailable",
                )
            )

            selection = select_repository_files(tree_entries, primary_language=metadata.primary_language)
            selected_paths = selection.manifest_paths + selection.source_paths
            payload["steps"].append(
                self._step(
                    "select_files",
                    "Select interview-relevant files",
                    "success",
                    f"{len(selection.manifest_paths)} manifests, {len(selection.source_paths)} source files",
                )
            )

            for path in selected_paths:
                try:
                    file_content = self.reader.fetch_file_content(parsed, path=path, ref=snapshot_ref)
                    if file_content.skipped:
                        read_errors.append(
                            {
                                "path": path,
                                "code": file_content.skip_reason or "file_skipped",
                                "message": "Selected file was skipped by the reader.",
                                "retryable": False,
                            }
                        )
                    else:
                        selected_files.append(file_content)
                except GitHubRepoError as file_error:
                    read_errors.append(
                        {
                            "path": path,
                            "code": file_error.code,
                            "message": file_error.message,
                            "retryable": file_error.retryable,
                        }
                    )

            payload["steps"].append(
                self._step(
                    "read_selected_files",
                    "Read selected files",
                    "partial" if read_errors else "success",
                    f"{len(selected_files)} files read",
                )
            )
        except GitHubRepoError as error:
            if not payload["steps"]:
                payload["steps"].append(self._step("parse_url", "Parse GitHub URL", "error", error.message))
            else:
                step_id = "read_readme" if metadata is not None else "fetch_metadata"
                label = "Read README" if metadata is not None else "Fetch repository metadata"
                payload["steps"].append(self._step(step_id, label, "error", error.message))
            payload["status"] = "error"
            payload["partial"] = False
            payload["errors"].append(self._error(error))
            return self._json_result(payload, success=False)
        except Exception:
            logger.exception("Unexpected error in github_repo_interview_prep")
            error = GitHubRepoError(
                "github_request_failed",
                "An unexpected error occurred while reading the GitHub repository.",
                retryable=False,
            )
            if not payload["steps"]:
                payload["steps"].append(self._step("parse_url", "Parse GitHub URL", "error", error.message))
            else:
                step_id = "read_readme" if metadata is not None else "fetch_metadata"
                label = "Read README" if metadata is not None else "Fetch repository metadata"
                payload["steps"].append(self._step(step_id, label, "error", error.message))
            payload["status"] = "error"
            payload["partial"] = False
            payload["errors"].append(self._error(error))
            return self._json_result(payload, success=False)

        if readme is None:
            missing_readme = GitHubRepoError(
                "readme_not_found",
                "README was not found; Slice 2 can continue with metadata, tree, and selected file context.",
                retryable=False,
            )
            payload["status"] = "partial"
            payload["partial"] = True
            payload["steps"].append(self._step("read_readme", "Read README", "partial", missing_readme.message))
            payload["warnings"].append(self._error(missing_readme))
        else:
            payload["steps"].append(self._step("read_readme", "Read README", "success", readme.path))

        repo_metadata = metadata.to_dict()
        project_context_pack = build_project_context_pack(
            metadata=metadata,
            readme=readme,
            tree_entries=tree_entries,
            tree_truncated=tree_truncated,
            files=selected_files,
            read_errors=read_errors,
            language=payload["input"]["language"],
        )
        question_result = build_interview_questions(
            project_context_pack=project_context_pack,
            target_role=payload["input"]["target_role"],
            difficulty=payload["input"]["difficulty"],
            question_count=payload["input"]["question_count"],
            language=payload["input"]["language"],
        )
        generated_count = question_result["summary"]["generated_count"]
        question_step_status = "success" if question_result["summary"]["has_source_evidence"] else "partial"
        question_step_detail = (
            f"{generated_count} evidence-backed questions"
            if question_result["summary"]["has_source_evidence"]
            else f"{generated_count} questions generated with limited source evidence"
        )

        if read_errors or tree_truncated:
            payload["status"] = "partial"
            payload["partial"] = True
            if tree_truncated:
                payload["warnings"].append(
                    {
                        "code": "tree_truncated",
                        "message": "Repository tree was truncated; some paths may not be considered.",
                        "retryable": True,
                    }
                )
            for read_error in read_errors:
                payload["warnings"].append(
                    {
                        "code": read_error["code"],
                        "message": f"{read_error['path']}: {read_error['message']}",
                        "retryable": read_error["retryable"],
                    }
                )

        payload["steps"].append(
            self._step(
                "build_context_pack",
                "Build context pack",
                "partial" if payload["partial"] else "success",
                "manifest, directory, source evidence ready",
            )
        )
        payload["steps"].append(
            self._step(
                "generate_questions",
                "Generate interview questions",
                question_step_status,
                question_step_detail,
            )
        )

        payload["data"] = {
            "repo_metadata": repo_metadata,
            "readme": readme.to_dict() if readme else None,
            "project_context_pack": project_context_pack,
            "interview_questions": question_result["questions"],
            "question_generation_summary": question_result["summary"],
            "markdown": self._question_markdown(
                question_result["questions"],
                question_result["summary"]["has_source_evidence"],
                payload["input"]["language"],
            ),
        }
        payload["next_step"] = "Next slice can add answer refinement and follow-up coaching based on these questions."
        return self._json_result(payload, success=True)
