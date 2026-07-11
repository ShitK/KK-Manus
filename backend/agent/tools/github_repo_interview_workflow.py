from typing import Any, Dict, List, Optional

from agent.tools.github_repo_interview_intent import normalize_question_category
from agent.tools.github_repo_interview_workflow_context import context_policy_for_state
from agent.tools.github_repo_interview_workflow_roles import (
    active_role_for_stage,
    workflow_role_contracts,
)


MAX_WORKFLOW_EVIDENCE_DETAILS = 3


WORKFLOW_STEPS = (
    ("prep", "Prep"),
    ("question", "Question"),
    ("answer_coach", "Answer Coach"),
    ("follow_up", "Follow-up"),
    ("summary", "Summary"),
)

ACTION_TO_STATE = {
    "select_question": "question_selected",
    "coach_answer": "answer_coached",
    "coach_follow_up": "follow_up_ready",
    "summarize": "summary_ready",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _items(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _error(code: str, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message, "retryable": False}


def _base_error_state(code: str, message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "partial": False,
        "workflow": {
            "current_stage": "error",
            "steps": _workflow_steps("error"),
        },
        "warnings": [],
        "errors": [_error(code, message)],
    }


def _workflow_steps(current_stage: str) -> List[Dict[str, str]]:
    statuses = {
        "prep": "success",
        "question": "pending",
        "answer_coach": "pending",
        "follow_up": "pending",
        "summary": "pending",
    }
    if current_stage in {
        "question_selected",
        "answer_coached",
        "follow_up_ready",
        "follow_up_answered",
        "summary_ready",
    }:
        statuses["question"] = "success"
    if current_stage in {"answer_coached", "follow_up_ready", "follow_up_answered", "summary_ready"}:
        statuses["answer_coach"] = "success"
    if current_stage in {"follow_up_ready", "summary_ready"}:
        statuses["follow_up"] = "ready"
    if current_stage in {"follow_up_answered", "summary_ready"}:
        statuses["follow_up"] = "success"
    if current_stage == "summary_ready":
        statuses["summary"] = "success"
    if current_stage == "error":
        statuses["question"] = "error"

    return [
        {"id": step_id, "label": label, "status": statuses[step_id]}
        for step_id, label in WORKFLOW_STEPS
    ]


def _extract_questions_pack(prep_questions_pack: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(prep_questions_pack, dict):
        return {}
    if isinstance(prep_questions_pack.get("data"), dict):
        source = prep_questions_pack["data"]
    else:
        source = prep_questions_pack
    return {
        "interview_questions": _items(source.get("interview_questions")),
        "question_generation_summary": (
            source.get("question_generation_summary")
            if isinstance(source.get("question_generation_summary"), dict)
            else {}
        ),
    }


def _find_question(questions: List[Any], question_id: str) -> Dict[str, Any]:
    normalized_id = _text(question_id)
    for question in questions:
        if isinstance(question, dict) and _text(question.get("id")) == normalized_id:
            return question
    return {}


def _find_question_by_category(questions: List[Any], category: str) -> Dict[str, Any]:
    normalized_category, _ = normalize_question_category(category)
    if not normalized_category:
        return {}
    for question in questions:
        if isinstance(question, dict) and _text(question.get("category")).lower() == normalized_category:
            return question
    return {}


def _previous_selected_question_id(previous_workflow_state: Optional[Dict[str, Any]]) -> str:
    if not isinstance(previous_workflow_state, dict):
        return ""
    selected = previous_workflow_state.get("selected_question")
    if not isinstance(selected, dict):
        return ""
    return _text(selected.get("id"))


def _sanitize_evidence_details(evidence_details: Any) -> List[Dict[str, Any]]:
    sanitized = []
    seen = set()
    for detail in _items(evidence_details):
        if len(sanitized) >= MAX_WORKFLOW_EVIDENCE_DETAILS:
            break
        if not isinstance(detail, dict):
            continue
        item: Dict[str, Any] = {}
        for key in ("evidence_id", "source_path", "evidence_type", "why_it_matters", "confidence"):
            value = _text(detail.get(key))
            if value:
                item[key] = value
        for key in ("summary", "snippet"):
            value = _text(detail.get(key))
            if value:
                item[key] = value[:300]

        evidence_id = item.get("evidence_id")
        has_required_metadata = all(
            item.get(key)
            for key in ("evidence_id", "source_path", "evidence_type", "why_it_matters")
        )
        has_readable_content = bool(item.get("summary") or item.get("snippet"))
        if not evidence_id or evidence_id in seen or not has_required_metadata or not has_readable_content:
            continue
        seen.add(evidence_id)
        sanitized.append(item)
    return sanitized


def _selected_question(question: Dict[str, Any]) -> Dict[str, Any]:
    selected = {}
    for key in (
        "id",
        "category",
        "difficulty",
        "question",
        "answer_direction",
        "confidence",
    ):
        value = _text(question.get(key))
        if value:
            selected[key] = value
    for key in ("source_paths", "evidence_refs"):
        values = [_text(item) for item in _items(question.get(key)) if _text(item)]
        if values:
            selected[key] = values
    return selected


def build_workflow_state(
    stage: str,
    prep_questions_pack: Dict[str, Any],
    question_id: str,
    previous_workflow_state: Optional[Dict[str, Any]] = None,
    language: str = "zh",
    preferred_question_category: str = "",
    follow_up_answer: str = "",
) -> Dict[str, Any]:
    """Build deterministic workflow state from a whitelisted Slice 4 question pack.

    The function accepts a full Slice 4 payload for caller convenience, but it only
    extracts interview_questions and question_generation_summary. Full repository
    metadata, README, project_context_pack, markdown, and thread history are never
    forwarded into the returned workflow state.
    """
    del language

    questions_pack = _extract_questions_pack(prep_questions_pack)
    questions = questions_pack.get("interview_questions") or []
    if not questions:
        return _base_error_state(
            "invalid_prep_questions_pack",
            "prep_questions_pack.interview_questions must contain at least one question.",
        )

    requested_question_id = _text(question_id)
    question = _find_question(questions, requested_question_id)
    if not question and not requested_question_id and preferred_question_category:
        question = _find_question_by_category(questions, preferred_question_category)
    if not question and not requested_question_id and not preferred_question_category:
        inherited_question_id = _previous_selected_question_id(previous_workflow_state)
        question = _find_question(questions, inherited_question_id)
    if not question:
        return _base_error_state(
            "question_not_found",
            "question_id must exactly match one interview_questions[].id, or preferred_question_category must match an available category.",
        )

    question_text = _text(question.get("question"))
    if not question_text:
        return _base_error_state(
            "invalid_question",
            "selected question must include question text.",
        )

    evidence_details = _sanitize_evidence_details(question.get("evidence_details"))
    if not evidence_details:
        return _base_error_state(
            "invalid_question_evidence",
            "selected question must include readable evidence_details.",
        )

    current_stage = ACTION_TO_STATE.get(_text(stage), "question_selected")
    if _text(stage) == "coach_follow_up" and _text(follow_up_answer):
        current_stage = "follow_up_answered"
    allowed_evidence_ids = [detail["evidence_id"] for detail in evidence_details]
    active_role = active_role_for_stage(stage)

    state = {
        "status": "success",
        "partial": False,
        "workflow": {
            "current_stage": current_stage,
            "steps": _workflow_steps(current_stage),
            "active_role": active_role,
            "roles": workflow_role_contracts(),
        },
        "selected_question": _selected_question(question),
        "evidence_policy": {
            "source": "selected_question.evidence_details",
            "allowed_evidence_ids": allowed_evidence_ids,
            "max_evidence_details": MAX_WORKFLOW_EVIDENCE_DETAILS,
            "repository_access": "no_new_repository_access",
        },
        "evidence_details": evidence_details,
        "question_generation_summary": questions_pack.get("question_generation_summary") or {},
        "warnings": [],
        "errors": [],
    }
    state["context_policy"] = context_policy_for_state(state, active_role)
    return state
