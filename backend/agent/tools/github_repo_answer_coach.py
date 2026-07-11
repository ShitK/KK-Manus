import json
import re
from typing import Any, Dict, Optional

from services.llm import make_llm_api_call
from utils.config import config


ALLOWED_LANGUAGES = {"zh", "en"}
ALLOWED_COACH_STYLES = {"concise", "direct", "encouraging", "balanced"}
MAX_USER_ANSWER_CHARS = 4000
MAX_EVIDENCE_DETAILS = 3
MAX_EVIDENCE_TEXT_CHARS = 300
REQUIRED_FEEDBACK_ARRAY_FIELDS = (
    "strengths",
    "gaps",
    "evidence_missed",
    "suggested_answer_outline",
    "follow_up_questions",
    "grounding_notes",
)
DISALLOWED_JUDGMENT_PATTERN = re.compile(
    r"(\bscore\b|\bscored\b|\brank\b|\branking\b|\bpass\b|\bfail\b|评分|得分|通过率|通过/淘汰|通过淘汰|淘汰|应该通过|不通过)",
    re.IGNORECASE,
)
SYSTEM_GROUNDING_INSTRUCTIONS = """You are an interview answer coach for a GitHub repository question.
Use only the provided question, answer_direction, source_paths, evidence_refs, and evidence_details.
Do not use repository popularity, repository web links, full readme text, or outside knowledge.
Do not score, rank, or decide pass/fail.
Return only valid JSON with these keys: summary, strengths, gaps, evidence_missed, suggested_answer_outline, follow_up_questions, grounding_notes.
strengths, gaps, evidence_missed, suggested_answer_outline, follow_up_questions, and grounding_notes must always be arrays; use [] when empty.
Each evidence_missed item must reference an evidence_id from the provided evidence_details."""
COACH_STYLE_INSTRUCTIONS = {
    "concise": "concise: keep feedback short and focused on the highest-impact gap.",
    "direct": "direct: state the missing or weak parts plainly before suggesting a revision.",
    "encouraging": "encouraging: affirm one concrete strength before naming the gap to improve.",
    "balanced": "balanced: name one concrete strength and one concrete gap before suggesting a revision path.",
}


class AnswerCoachEngine:
    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


def _build_coach_messages(request: Dict[str, Any]) -> list[Dict[str, str]]:
    question = request.get("question") if isinstance(request.get("question"), dict) else {}
    compact_request = {
        "question": {
            "id": question.get("id"),
            "category": question.get("category"),
            "difficulty": question.get("difficulty"),
            "question": question.get("question"),
            "answer_direction": question.get("answer_direction"),
            "source_paths": question.get("source_paths") or [],
            "evidence_refs": question.get("evidence_refs") or [],
        },
        "evidence_details": (request.get("evidence_details") or [])[:MAX_EVIDENCE_DETAILS],
        "user_answer": request.get("user_answer"),
        "language": request.get("language"),
        "coach_style": request.get("coach_style"),
        "coach_style_instruction": request.get("coach_style_instruction"),
        "max_follow_ups": request.get("max_follow_ups"),
    }
    if isinstance(request.get("role"), dict):
        compact_request["role"] = request["role"]
    if isinstance(request.get("context_policy"), dict):
        compact_request["context_policy"] = request["context_policy"]
    return [
        {"role": "system", "content": SYSTEM_GROUNDING_INSTRUCTIONS},
        {"role": "user", "content": json.dumps(compact_request, ensure_ascii=False)},
    ]


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _extract_first_json_object(content: str) -> Optional[str]:
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]

    return None


def _parse_json_object_content(content: str) -> Dict[str, Any]:
    candidates = [content.strip()]
    fenced_matches = re.findall(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(match.strip() for match in fenced_matches)
    first_object = _extract_first_json_object(content)
    if first_object:
        candidates.append(first_object)

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object.")
        return parsed

    raise ValueError("LLM response content was not valid JSON.")


def _extract_json_response(response: Any) -> Dict[str, Any]:
    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if not choices:
        raise ValueError("LLM response did not include choices.")

    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else getattr(first_choice, "message", None)
    content = _message_content(message)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response did not include message content.")

    return _parse_json_object_content(content)


class LLMAnswerCoachEngine(AnswerCoachEngine):
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or config.MODEL_TO_USE or "deepseek/deepseek-v4-flash"

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        response = await make_llm_api_call(
            messages=_build_coach_messages(request),
            model_name=self.model_name,
            temperature=0,
            max_tokens=1200,
            tools=None,
            tool_choice="none",
            stream=False,
        )
        return _extract_json_response(response)


def build_coach_request(
    question: Dict[str, Any],
    user_answer: str,
    language: str,
    coach_style: str,
    max_follow_ups: int,
) -> Dict[str, Any]:
    evidence_details = question.get("evidence_details") or []
    return {
        "question": {
            "id": question.get("id"),
            "category": question.get("category"),
            "difficulty": question.get("difficulty"),
            "question": question.get("question"),
            "answer_direction": question.get("answer_direction"),
            "source_paths": question.get("source_paths") or [],
            "evidence_refs": question.get("evidence_refs") or [],
        },
        "evidence_details": _sanitize_evidence_details(evidence_details),
        "user_answer": user_answer,
        "language": language,
        "coach_style": coach_style,
        "coach_style_instruction": COACH_STYLE_INSTRUCTIONS[coach_style],
        "max_follow_ups": max_follow_ups,
    }


def _truncate_text(value: Any, max_chars: int) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:max_chars]


def _sanitize_evidence_details(evidence_details: Any) -> list[Dict[str, Any]]:
    if not isinstance(evidence_details, list):
        return []

    sanitized = []
    for detail in evidence_details[:MAX_EVIDENCE_DETAILS]:
        if not isinstance(detail, dict):
            continue
        item: Dict[str, Any] = {}
        for key in ("evidence_id", "source_path", "evidence_type", "why_it_matters", "confidence"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                item[key] = value.strip()
        for key in ("summary", "snippet"):
            value = _truncate_text(detail.get(key), MAX_EVIDENCE_TEXT_CHARS)
            if value:
                item[key] = value
        has_required_metadata = all(item.get(key) for key in ("evidence_id", "source_path", "evidence_type", "why_it_matters"))
        has_readable_content = bool(item.get("summary") or item.get("snippet"))
        if has_required_metadata and has_readable_content:
            sanitized.append(item)
    return sanitized


def _feedback_list(feedback: Dict[str, Any], key: str) -> list[Any]:
    value = feedback.get(key)
    return value if isinstance(value, list) else []


def _normalize_feedback_array(value: Any) -> tuple[list[Any], bool]:
    if isinstance(value, list):
        return value, False
    if value is None:
        return [], True
    if isinstance(value, str):
        stripped = value.strip()
        return ([stripped] if stripped else []), True
    return [value], True


def build_feedback_markdown(feedback: Dict[str, Any]) -> str:
    lines = ["## Answer Coach Feedback"]
    summary = feedback.get("summary")
    if summary:
        lines.extend(["", "### Summary", str(summary)])

    sections = [
        ("Strengths", _feedback_list(feedback, "strengths")),
        ("Gaps", _feedback_list(feedback, "gaps")),
        ("Evidence Missed", _feedback_list(feedback, "evidence_missed")),
        ("Suggested Answer Outline", _feedback_list(feedback, "suggested_answer_outline")),
        ("Follow-up Questions", _feedback_list(feedback, "follow_up_questions")),
        ("Grounding Notes", _feedback_list(feedback, "grounding_notes")),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend(["", f"### {title}"])
        for item in items:
            if isinstance(item, dict):
                source_path = item.get("source_path")
                reason = item.get("reason") or item.get("summary") or item.get("evidence_id")
                prefix = f"{source_path}: " if source_path else ""
                lines.append(f"- {prefix}{reason}")
            else:
                lines.append(f"- {item}")
    return "\n".join(lines)


def build_success_payload(
    request: Dict[str, Any],
    feedback: Dict[str, Any],
    warnings: Optional[list[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    question = request["question"]
    return {
        "tool": "github_repo_answer_coach",
        "type": "github_repo_answer_coach",
        "version": "v1",
        "status": "success",
        "partial": False,
        "input": {
            "question_id": question.get("id"),
            "language": request["language"],
            "coach_style": request["coach_style"],
            "max_follow_ups": request["max_follow_ups"],
            "user_answer_excerpt": request["user_answer"][:300],
        },
        "data": {
            "question": {
                "id": question.get("id"),
                "category": question.get("category"),
                "difficulty": question.get("difficulty"),
                "question": question.get("question"),
            },
            "answer_feedback": feedback,
            "markdown": build_feedback_markdown(feedback),
        },
        "warnings": warnings or [],
        "errors": [],
        "next_step": "Pick one gap and revise your answer in 3-5 sentences.",
    }


def build_error_payload(
    code: str,
    message: str,
    input_data: Optional[Dict[str, Any]] = None,
    warnings: Optional[list[Dict[str, Any]]] = None,
    errors: Optional[list[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "tool": "github_repo_answer_coach",
        "type": "github_repo_answer_coach",
        "version": "v1",
        "status": "error",
        "partial": False,
        "input": input_data or {},
        "data": {},
        "warnings": warnings or [],
        "errors": errors or [{"code": code, "message": message, "retryable": False}],
        "next_step": "Fix the input and call github_repo_answer_coach again.",
    }


def _warning(code: str, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message, "retryable": False}


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message, "retryable": False}


def _coach_generation_error(message: str) -> Dict[str, str]:
    return {"code": "coach_generation_failed", "message": message}


def _normalize_max_follow_ups(max_follow_ups: Any) -> int:
    try:
        value = int(max_follow_ups)
    except (TypeError, ValueError):
        value = 3
    return min(3, max(1, value))


def _valid_evidence_ids(evidence_details: list[Any]) -> set[str]:
    ids = set()
    for item in evidence_details:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("evidence_id")
        if isinstance(evidence_id, str) and evidence_id.strip():
            ids.add(evidence_id)
    return ids


def _sanitize_feedback(
    feedback: Dict[str, Any],
    valid_evidence_ids: set[str],
    max_follow_ups: int,
) -> tuple[Optional[Dict[str, Any]], list[Dict[str, Any]], Optional[Dict[str, str]]]:
    sanitized = dict(feedback)
    warnings = []
    for key in REQUIRED_FEEDBACK_ARRAY_FIELDS:
        normalized, changed = _normalize_feedback_array(feedback.get(key))
        sanitized[key] = normalized
        if changed:
            warnings.append(
                _warning(
                    "feedback_schema_normalized",
                    "Coach feedback array fields were normalized to match the expected schema.",
                )
            )

    if _contains_disallowed_judgment(sanitized):
        return None, warnings, _coach_generation_error(
            "Coach feedback included scoring or pass/fail judgment."
        )

    evidence_missed = _feedback_list(sanitized, "evidence_missed")
    valid_missed = []
    invalid_reference_count = 0
    malformed_count = 0
    for item in evidence_missed:
        if not isinstance(item, dict):
            malformed_count += 1
            continue
        evidence_id = item.get("evidence_id")
        if evidence_id in valid_evidence_ids:
            valid_missed.append(item)
        else:
            invalid_reference_count += 1

    if invalid_reference_count or malformed_count:
        if invalid_reference_count and not valid_missed:
            return None, warnings, _coach_generation_error(
                "Coach feedback did not include valid evidence references."
            )
        warnings.append(
            _warning(
                "invalid_evidence_reference",
                "Some evidence_missed entries were invalid or referenced evidence ids outside the provided evidence_details and were omitted.",
            )
        )

    sanitized["evidence_missed"] = valid_missed
    sanitized["follow_up_questions"] = _feedback_list(sanitized, "follow_up_questions")[:max_follow_ups]
    for key in ("strengths", "gaps", "suggested_answer_outline", "grounding_notes"):
        sanitized[key] = _feedback_list(sanitized, key)
    if "summary" in sanitized and sanitized["summary"] is not None:
        sanitized["summary"] = str(sanitized["summary"])

    return sanitized, warnings, None


def _contains_disallowed_judgment(value: Any) -> bool:
    if isinstance(value, str):
        return bool(DISALLOWED_JUDGMENT_PATTERN.search(value))
    if isinstance(value, list):
        return any(_contains_disallowed_judgment(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_disallowed_judgment(item) for item in value.values())
    return False
