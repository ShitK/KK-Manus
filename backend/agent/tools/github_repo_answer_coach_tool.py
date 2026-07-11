import json
from typing import Any, Dict, Optional

from agent.tools.github_repo_answer_coach import (
    ALLOWED_COACH_STYLES,
    ALLOWED_LANGUAGES,
    MAX_USER_ANSWER_CHARS,
    AnswerCoachEngine,
    LLMAnswerCoachEngine,
    _error,
    _normalize_max_follow_ups,
    _sanitize_feedback,
    _valid_evidence_ids,
    _warning,
    build_coach_request,
    build_error_payload,
    build_success_payload,
)
from agentpress.tool import Tool, ToolResult


class GitHubRepoAnswerCoachTool(Tool):
    """Return grounded feedback for a Slice 4 GitHub repo interview question."""

    def __init__(self, engine: Optional[AnswerCoachEngine] = None):
        super().__init__()
        self.engine = engine or LLMAnswerCoachEngine()

    def _json_result(self, payload: Dict[str, Any], success: bool = True) -> ToolResult:
        return ToolResult(success=success, output=json.dumps(payload, ensure_ascii=False, indent=2))

    async def github_repo_answer_coach(
        self,
        question: Dict[str, Any],
        user_answer: str,
        language: str = "zh",
        coach_style: str = "concise",
        max_follow_ups: int = 3,
    ) -> ToolResult:
        """Coach a user's answer to one GitHub Repo Interview Prep question.

        For a multi-turn GitHub interview workflow, prefer
        github_repo_interview_workflow with stage="coach_answer" instead of this
        single-question helper. In particular, when the user says "点评我的回答",
        "回答如下", "第 X 题答案", or "QX 答案" after a GitHub interview workflow
        already exists, route to github_repo_interview_workflow so the workflow
        state and right-side panel stay consistent.

        Use this tool only after a GitHub Repo Interview Prep question already exists.
        The caller must pass the full question object, including evidence_details, and
        the user's answer. The tool gives evidence-grounded feedback using only the
        provided question evidence. coach_style must be one of concise, direct,
        encouraging, or balanced. It does not read GitHub, inspect local files,
        run code, score the user, persist answers, or manage multi-turn coaching
        state.
        """
        warnings = []
        errors = []
        question = question if isinstance(question, dict) else {}
        normalized_max_follow_ups = _normalize_max_follow_ups(max_follow_ups)
        stripped_answer = str(user_answer or "").strip()

        if not stripped_answer:
            errors.append(_error("invalid_user_answer", "user_answer must be a non-empty string."))
        elif len(stripped_answer) > MAX_USER_ANSWER_CHARS:
            stripped_answer = stripped_answer[:MAX_USER_ANSWER_CHARS]
            warnings.append(
                _warning(
                    "user_answer_truncated",
                    f"user_answer was truncated to {MAX_USER_ANSWER_CHARS} characters.",
                )
            )

        if language not in ALLOWED_LANGUAGES:
            errors.append(_error("invalid_question", "language must be one of: zh, en."))
        if coach_style not in ALLOWED_COACH_STYLES:
            errors.append(
                _error(
                    "invalid_question",
                    "coach_style must be one of: concise, direct, encouraging, balanced.",
                )
            )
        question_text = str(question.get("question") or "").strip()
        if not question_text:
            errors.append(_error("invalid_question", "question.question must be a non-empty string."))

        evidence_details = question.get("evidence_details")
        if not isinstance(evidence_details, list) or not evidence_details:
            errors.append(_error("invalid_question", "question.evidence_details must contain at least one item."))

        input_data = {
            "question_id": question.get("id"),
            "language": language,
            "coach_style": coach_style,
            "max_follow_ups": normalized_max_follow_ups,
        }
        if errors:
            return self._json_result(
                build_error_payload(
                    code=errors[0]["code"],
                    message=errors[0]["message"],
                    input_data=input_data,
                    warnings=warnings,
                    errors=errors,
                ),
                success=False,
            )

        request = build_coach_request(
            question,
            stripped_answer,
            language,
            coach_style,
            normalized_max_follow_ups,
        )
        valid_evidence_ids = _valid_evidence_ids(request["evidence_details"])
        if not valid_evidence_ids:
            return self._json_result(
                build_error_payload(
                    "invalid_question",
                    "question.evidence_details must include at least one evidence_id.",
                    input_data=input_data,
                    warnings=warnings,
                ),
                success=False,
            )

        try:
            feedback = await self.engine.generate_feedback(request)
        except Exception:
            return self._json_result(
                build_error_payload(
                    "coach_generation_failed",
                    "Answer coach feedback could not be generated.",
                    input_data=input_data,
                    warnings=warnings,
                ),
                success=False,
            )

        if not isinstance(feedback, dict):
            return self._json_result(
                build_error_payload(
                    "coach_generation_failed",
                    "Answer coach feedback could not be generated.",
                    input_data=input_data,
                    warnings=warnings,
                ),
                success=False,
            )

        sanitized_feedback, feedback_warnings, feedback_error = _sanitize_feedback(
            feedback,
            valid_evidence_ids,
            normalized_max_follow_ups,
        )
        warnings.extend(feedback_warnings)
        if feedback_error:
            return self._json_result(
                build_error_payload(
                    feedback_error["code"],
                    feedback_error["message"],
                    input_data=input_data,
                    warnings=warnings,
                ),
                success=False,
            )

        return self._json_result(build_success_payload(request, sanitized_feedback or {}, warnings))
