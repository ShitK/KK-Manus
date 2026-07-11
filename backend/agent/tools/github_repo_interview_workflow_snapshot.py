"""Request-level context snapshot and memory candidate preview helpers.

This module emits bounded metadata for GitHub Repo Interview Workflow demo
surfaces. It does not persist memory, read databases or local files, or include
user answer text, follow-up answer text, hidden source content, or repo
evidence text.

Weakness tags are derived from workflow fields that must already be sanitized by
the workflow gatekeeper. This module only emits fixed tag identifiers and labels,
never the source feedback text.
"""

from copy import deepcopy
from typing import Any, Dict, List

from agent.tools.github_repo_interview_session_memory import sanitize_session_memory_state


ALLOWED_CANDIDATE_TYPES = {
    "language_preference_hint",
    "feedback_preference_hint",
    "recent_practice_category",
    "practice_weakness_tag",
}

ALLOWED_WEAKNESS_TAGS = {
    "missing_evidence",
    "weak_architecture_tradeoff",
    "unclear_testing_story",
}

SNAPSHOT_FORBIDDEN_SOURCE_NAMES = {
    "user_answer",
    "follow_up_answer",
    "user_answer_excerpt",
}

SAFE_PRACTICE_CATEGORIES = {
    "architecture",
    "dependency and packaging",
    "implementation detail",
    "testing and automation",
}

STAGE_TO_CANDIDATE_SOURCE = {
    "select_question": "select_question",
    "coach_answer": "coach_answer",
    "coach_follow_up": "coach_follow_up",
    "summarize": "summarize",
    "question_selected": "select_question",
    "answer_coached": "coach_answer",
    "follow_up_ready": "coach_follow_up",
    "summary_ready": "summarize",
}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_string(item) for item in value if _string(item)]


def _snapshot_sources(value: Any) -> List[str]:
    return [item for item in _string_list(value) if item not in SNAPSHOT_FORBIDDEN_SOURCE_NAMES]


def _candidate_source_stage(input_data: Dict[str, Any], data: Dict[str, Any]) -> str:
    raw_stage = _string(input_data.get("stage"))
    if raw_stage in STAGE_TO_CANDIDATE_SOURCE:
        return STAGE_TO_CANDIDATE_SOURCE[raw_stage]
    workflow = data.get("workflow") if isinstance(data.get("workflow"), dict) else {}
    current_stage = _string(workflow.get("current_stage"))
    return STAGE_TO_CANDIDATE_SOURCE.get(current_stage, "select_question")


def _safe_practice_category(value: Any) -> str:
    category = _string(value).lower()
    return category if category in SAFE_PRACTICE_CATEGORIES else ""


def _bool_from_list(value: Any) -> bool:
    return isinstance(value, list) and any(_string(item) for item in value)


def _workflow_completion(data: Dict[str, Any]) -> Dict[str, Any]:
    summary = data.get("session_summary") if isinstance(data.get("session_summary"), dict) else {}
    completion = summary.get("workflow_completion") if isinstance(summary.get("workflow_completion"), dict) else {}
    allowed: Dict[str, Any] = {}
    for key in ("answer_coached", "follow_up_completed"):
        if isinstance(completion.get(key), bool):
            allowed[key] = completion[key]
    summary_scope = _string(completion.get("summary_scope"))
    if summary_scope:
        allowed["summary_scope"] = summary_scope
    return allowed


def _answer_state(data: Dict[str, Any]) -> Dict[str, Any]:
    feedback = data.get("answer_feedback") if isinstance(data.get("answer_feedback"), dict) else {}
    follow_up = data.get("follow_up") if isinstance(data.get("follow_up"), dict) else {}
    workflow = data.get("workflow") if isinstance(data.get("workflow"), dict) else {}
    state = {
        "has_answer_feedback": any(
            [
                bool(_string(feedback.get("summary"))),
                _bool_from_list(feedback.get("strengths")),
                _bool_from_list(feedback.get("gaps")),
                _bool_from_list(feedback.get("suggested_answer_outline")),
                isinstance(feedback.get("evidence_missed"), list) and len(feedback.get("evidence_missed")) > 0,
            ]
        ),
        "has_follow_up_feedback": _bool_from_list(follow_up.get("feedback")),
    }
    follow_up_mode = _string(follow_up.get("mode"))
    if follow_up_mode:
        state["follow_up_mode"] = follow_up_mode
    if isinstance(workflow.get("follow_up_count"), int):
        state["follow_up_count"] = max(0, workflow["follow_up_count"])
    return state


def build_context_snapshot(
    state: Dict[str, Any],
    data: Dict[str, Any],
    input_data: Dict[str, Any],
) -> Dict[str, Any]:
    del input_data
    workflow = data.get("workflow") if isinstance(data.get("workflow"), dict) else {}
    policy = data.get("context_policy") if isinstance(data.get("context_policy"), dict) else {}
    completion = _workflow_completion(data)
    snapshot = {
        "version": "v1",
        "scope": "request",
        "persistence": "not_persisted",
        "current_stage": _string(workflow.get("current_stage")),
        "active_role": _string(policy.get("active_role") or workflow.get("active_role")),
        "role_kind": _string(policy.get("role_kind")),
        "visible_sources": _snapshot_sources(policy.get("visible_sources")),
        "hidden_sources": _string_list(policy.get("hidden_sources")),
        "allowed_evidence_ids": _string_list(policy.get("allowed_evidence_ids")),
        "allowed_source_paths": _string_list(policy.get("allowed_source_paths")),
        "repository_access": _string(policy.get("repository_access")),
        "tool_access": _string(policy.get("tool_access")),
        "persists_user_answer": (
            bool(policy.get("persists_user_answer"))
            if isinstance(policy.get("persists_user_answer"), bool)
            else False
        ),
        "answer_state": _answer_state(data),
        "redaction_policy": {
            "includes_user_answer": False,
            "includes_follow_up_answer": False,
            "includes_hidden_source_content": False,
            "includes_repo_evidence_text": False,
        },
    }
    if completion:
        snapshot["workflow_completion"] = completion
    if not snapshot["current_stage"]:
        state_workflow = state.get("workflow") if isinstance(state.get("workflow"), dict) else {}
        snapshot["current_stage"] = _string(state_workflow.get("current_stage"))
    saved_memory_context = data.get("saved_memory_context") if isinstance(data.get("saved_memory_context"), list) else []
    if saved_memory_context:
        visible_sources = list(snapshot.get("visible_sources") or [])
        if "saved_memories" not in visible_sources:
            visible_sources.append("saved_memories")
        snapshot["visible_sources"] = visible_sources
        snapshot["saved_memory_count"] = min(len(saved_memory_context), 6)
    session_memory_context = sanitize_session_memory_state(
        data.get("session_memory_context") if isinstance(data.get("session_memory_context"), dict) else {}
    )
    if session_memory_context:
        visible_sources = list(snapshot.get("visible_sources") or [])
        if "session_memory" not in visible_sources:
            visible_sources.append("session_memory")
        snapshot["visible_sources"] = visible_sources
        snapshot["session_memory"] = {
            "has_target_role": bool(session_memory_context.get("target_role")),
            "answered_question_count": len(session_memory_context.get("answered_question_ids") or []),
            "missed_evidence_count": len(session_memory_context.get("missed_evidence_ids") or []),
        }
    vector_retrieval = data.get("vector_memory_retrieval") if isinstance(data.get("vector_memory_retrieval"), dict) else {}
    if vector_retrieval:
        vector_status = _string(vector_retrieval.get("status")) or "disabled"
        snapshot["vector_memory"] = {
            "enabled": vector_status != "disabled",
            "status": vector_status,
            "matched_count": min(max(int(vector_retrieval.get("applied_count") or 0), 0), 3),
            "threshold": vector_retrieval.get("threshold"),
            "model": _string(vector_retrieval.get("model")),
        }
        if vector_status == "matched":
            visible_sources = list(snapshot.get("visible_sources") or [])
            if "vector_memories" not in visible_sources:
                visible_sources.append("vector_memories")
            snapshot["visible_sources"] = visible_sources
    return {
        key: value
        for key, value in snapshot.items()
        if value not in ("", [], {})
    }


def _candidate(
    candidate_type: str,
    value: str,
    label: str,
    source_stage: str,
    source_fields: List[str],
) -> Dict[str, Any]:
    return {
        "id": f"{candidate_type}:{value}",
        "type": candidate_type,
        "value": value,
        "label": label,
        "source_stage": source_stage,
        "source_fields": source_fields,
        "requires_user_confirmation": True,
        "status": "candidate_only",
        "persisted": False,
        "privacy": {
            "includes_user_answer": False,
            "includes_follow_up_answer": False,
            "includes_repo_evidence_text": False,
        },
    }


def _weakness_tags(data: Dict[str, Any]) -> List[str]:
    # The text below is used only for keyword matching against fixed tag ids.
    # It must come from the workflow's sanitized feedback/summary payload.
    tags: List[str] = []
    feedback = data.get("answer_feedback") if isinstance(data.get("answer_feedback"), dict) else {}
    summary = data.get("session_summary") if isinstance(data.get("session_summary"), dict) else {}
    if isinstance(feedback.get("evidence_missed"), list) and feedback.get("evidence_missed"):
        tags.append("missing_evidence")
    if _string_list(summary.get("missed_evidence")):
        tags.append("missing_evidence")
    safe_text = " ".join(
        _string_list(feedback.get("gaps"))
        + _string_list(feedback.get("suggested_answer_outline"))
        + _string_list(summary.get("practice_notes"))
    )
    lowered = safe_text.lower()
    if any(term in lowered for term in ("tradeoff", "取舍", "权衡", "architecture")):
        tags.append("weak_architecture_tradeoff")
    if any(term in lowered for term in ("test", "testing", "validation", "验证", "测试")):
        tags.append("unclear_testing_story")
    return [tag for tag in dict.fromkeys(tags) if tag in ALLOWED_WEAKNESS_TAGS]


def build_memory_candidates(
    state: Dict[str, Any],
    data: Dict[str, Any],
    input_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    stage = _candidate_source_stage(input_data, data)
    language = _string(input_data.get("language"))
    if language in {"zh", "en"}:
        candidates.append(
            _candidate(
                "language_preference_hint",
                language,
                "本次请求的候选语言偏好。",
                stage,
                ["input.language"],
            )
        )
    coach_style = _string(input_data.get("coach_style"))
    if coach_style in {"concise", "direct", "encouraging", "balanced"}:
        candidates.append(
            _candidate(
                "feedback_preference_hint",
                coach_style,
                "本次请求的候选反馈风格偏好。",
                stage,
                ["input.coach_style"],
            )
        )
    question = data.get("selected_question") if isinstance(data.get("selected_question"), dict) else {}
    category = _safe_practice_category(question.get("category"))
    if category:
        candidates.append(
            _candidate(
                "recent_practice_category",
                category,
                "本次请求的候选练习分类。",
                stage,
                ["selected_question.category"],
            )
        )
    for tag in _weakness_tags(data):
        source_fields = ["answer_feedback.evidence_missed", "session_summary.missed_evidence"]
        if tag in {"weak_architecture_tradeoff", "unclear_testing_story"}:
            source_fields = [
                "answer_feedback.gaps",
                "answer_feedback.suggested_answer_outline",
                "session_summary.practice_notes",
            ]
        candidates.append(
            _candidate(
                "practice_weakness_tag",
                tag,
                f"候选练习弱项标签：{tag}。",
                stage,
                source_fields,
            )
        )
    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate["type"] not in ALLOWED_CANDIDATE_TYPES:
            continue
        if candidate["id"] in seen:
            continue
        seen.add(candidate["id"])
        deduped.append(candidate)
    return deduped


def attach_context_snapshot(data: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
    enriched = deepcopy(data)
    # Workflow callers pass _state_data(state) as data; state_like preserves the
    # helper signature without introducing a second unsanitized source.
    state_like = enriched
    enriched["context_snapshot"] = build_context_snapshot(state_like, enriched, input_data)
    enriched["memory_candidates"] = build_memory_candidates(state_like, enriched, input_data)
    return enriched
