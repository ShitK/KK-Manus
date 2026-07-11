"""User-confirmed lightweight memory helpers for GitHub interview workflow.

This module stores only sanitized candidate values. It must not store user
answer text, follow-up answer text, repo evidence text, README content, URLs, or
local file content.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List


TABLE_NAME = "github_repo_interview_memories"

ALLOWED_VALUES = {
    "language_preference_hint": {"zh", "en"},
    "feedback_preference_hint": {"concise", "direct", "encouraging", "balanced"},
    "recent_practice_category": {
        "architecture",
        "dependency and packaging",
        "implementation detail",
        "testing and automation",
    },
    "practice_weakness_tag": {
        "missing_evidence",
        "weak_architecture_tradeoff",
        "unclear_testing_story",
    },
}

ALLOWED_SOURCE_STAGES = {"select_question", "coach_answer", "coach_follow_up", "summarize"}

ALLOWED_SOURCE_FIELDS = {
    "input.language",
    "input.coach_style",
    "selected_question.category",
    "answer_feedback.evidence_missed",
    "answer_feedback.gaps",
    "answer_feedback.suggested_answer_outline",
    "session_summary.missed_evidence",
    "session_summary.practice_notes",
}

LABELS = {
    "language_preference_hint": {
        "zh": "本次请求的候选语言偏好。",
        "en": "本次请求的候选语言偏好。",
    },
    "feedback_preference_hint": {
        "concise": "本次请求的候选反馈风格偏好。",
        "direct": "本次请求的候选反馈风格偏好。",
        "encouraging": "本次请求的候选反馈风格偏好。",
        "balanced": "本次请求的候选反馈风格偏好。",
    },
    "recent_practice_category": {
        "architecture": "本次请求的候选练习分类。",
        "dependency and packaging": "本次请求的候选练习分类。",
        "implementation detail": "本次请求的候选练习分类。",
        "testing and automation": "本次请求的候选练习分类。",
    },
    "practice_weakness_tag": {
        "missing_evidence": "候选练习弱项标签：missing_evidence。",
        "weak_architecture_tradeoff": "候选练习弱项标签：weak_architecture_tradeoff。",
        "unclear_testing_story": "候选练习弱项标签：unclear_testing_story。",
    },
}

SAFE_PRIVACY = {
    "includes_user_answer": False,
    "includes_follow_up_answer": False,
    "includes_repo_evidence_text": False,
}

FORBIDDEN_TEXT_MARKERS = (
    "http://",
    "https://",
    "user_answer",
    "follow_up_answer",
    "user_answer_excerpt",
    "project_context_pack",
    "README",
    "readme",
    "markdown",
    "snippet",
    "evidence_details",
)


def _reject_forbidden_text(value: str) -> None:
    normalized = value.lower()
    for marker in FORBIDDEN_TEXT_MARKERS:
        if marker.lower() in normalized:
            raise ValueError(f"memory text contains forbidden marker: {marker}")


def _raw_text(value: Any) -> str:
    return str(value or "").strip()


def _checked_text(value: Any, max_len: int) -> str:
    text = _raw_text(value)
    _reject_forbidden_text(text)
    return text[:max_len]


def _safe_source_fields(value: Any, *, reject_unknown: bool = True) -> List[str]:
    if not isinstance(value, list):
        return []
    fields = []
    for item in value:
        text = _checked_text(item, 80)
        if text not in ALLOWED_SOURCE_FIELDS:
            if reject_unknown:
                raise ValueError("unsupported source field")
            continue
        if text not in fields:
            fields.append(text)
    return fields


def _json_field(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return default
        return parsed if parsed is not None else default
    return value if value is not None else default


def _db_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _response_timestamp(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def sanitize_memory_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    if candidate.get("requires_user_confirmation") is not True:
        raise ValueError("candidate must require user confirmation")
    if candidate.get("persisted") is not False:
        raise ValueError("candidate must not already be persisted")
    if candidate.get("status") != "candidate_only":
        raise ValueError("candidate status must be candidate_only")
    if candidate.get("privacy") != SAFE_PRIVACY:
        raise ValueError("candidate privacy must be fully redacted")

    memory_type = _checked_text(candidate.get("type"), 80)
    memory_value = _checked_text(candidate.get("value"), 80)
    if memory_type not in ALLOWED_VALUES:
        raise ValueError("unsupported memory type")
    if memory_value not in ALLOWED_VALUES[memory_type]:
        raise ValueError("unsupported memory value")

    label = LABELS[memory_type][memory_value]
    source_stage = _checked_text(candidate.get("source_stage"), 40)
    source_fields = _safe_source_fields(candidate.get("source_fields"), reject_unknown=True)
    if source_stage not in ALLOWED_SOURCE_STAGES:
        raise ValueError("unsupported source stage")
    if not source_fields:
        raise ValueError("at least one safe source field is required")

    return {
        "memory_type": memory_type,
        "memory_value": memory_value,
        "label": label,
        "source_stage": source_stage,
        "source_fields": source_fields,
        "provenance": {
            "tool": "github_repo_interview_workflow",
            "candidate_id": f"{memory_type}:{memory_value}",
            "slice": "10",
        },
        "privacy": dict(SAFE_PRIVACY),
        "status": "active",
    }


def row_to_memory(row: Dict[str, Any]) -> Dict[str, Any]:
    is_active = row.get("status") == "active" and row.get("deleted_at") is None
    source_fields = _json_field(row.get("source_fields"), [])
    privacy = _json_field(row.get("privacy"), dict(SAFE_PRIVACY))
    return {
        "id": str(row.get("id") or ""),
        "type": row.get("memory_type"),
        "value": row.get("memory_value"),
        "label": row.get("label"),
        "source_stage": row.get("source_stage"),
        "source_fields": source_fields if isinstance(source_fields, list) else [],
        "status": row.get("status") or "active",
        "persisted": is_active,
        "requires_user_confirmation": False,
        "privacy": privacy if isinstance(privacy, dict) else dict(SAFE_PRIVACY),
        "created_at": _response_timestamp(row.get("created_at")),
        "updated_at": _response_timestamp(row.get("updated_at")),
    }


async def save_memory_candidate(client: Any, user_id: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = sanitize_memory_candidate(candidate)
    existing = await (
        client.table(TABLE_NAME)
        .select("*")
        .eq("user_id", user_id)
        .eq("memory_type", sanitized["memory_type"])
        .eq("memory_value", sanitized["memory_value"])
        .maybe_single()
        .execute()
    )
    now = datetime.now(timezone.utc)
    if existing.data:
        query = (
            client.table(TABLE_NAME)
            .eq("id", existing.data["id"])
            .eq("user_id", user_id)
            .maybe_single()
        )
        updated = await query.update(
            {
                "label": sanitized["label"],
                "source_stage": sanitized["source_stage"],
                "source_fields": _db_json(sanitized["source_fields"]),
                "provenance": _db_json(sanitized["provenance"]),
                "privacy": _db_json(sanitized["privacy"]),
                "status": "active",
                "deleted_at": None,
                "updated_at": now,
            }
        )
        return row_to_memory(updated.data)

    created = await client.table(TABLE_NAME).insert(
        {
            "user_id": user_id,
            **{
                **sanitized,
                "source_fields": _db_json(sanitized["source_fields"]),
                "provenance": _db_json(sanitized["provenance"]),
                "privacy": _db_json(sanitized["privacy"]),
            },
        }
    )
    row = created.data[0] if isinstance(created.data, list) else created.data
    return row_to_memory(row)


async def list_active_memories(client: Any, user_id: str) -> List[Dict[str, Any]]:
    result = await (
        client.table(TABLE_NAME)
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .is_("deleted_at", None)
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
    )
    rows = result.data if isinstance(result.data, list) else []
    return [row_to_memory(row) for row in rows]


async def soft_delete_memory(client: Any, user_id: str, memory_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    query = (
        client.table(TABLE_NAME)
        .eq("id", memory_id)
        .eq("user_id", user_id)
        .maybe_single()
    )
    result = await query.update({"status": "deleted", "deleted_at": now, "updated_at": now})
    if not result.data:
        raise KeyError("memory not found")
    return row_to_memory(result.data)


def select_workflow_memory_context(memories: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    selected = []
    for memory in memories:
        if len(selected) >= limit:
            break
        try:
            if memory.get("persisted") is not True:
                continue
            if memory.get("status") not in (None, "active"):
                continue
            memory_type = _checked_text(memory.get("type"), 80)
            memory_value = _checked_text(memory.get("value"), 80)
            label = _checked_text(memory.get("label"), 160)
            if memory_type not in ALLOWED_VALUES or memory_value not in ALLOWED_VALUES[memory_type]:
                continue
            source_stage = _checked_text(memory.get("source_stage"), 40)
            if source_stage not in ALLOWED_SOURCE_STAGES:
                continue
            source_fields = _safe_source_fields(memory.get("source_fields"), reject_unknown=False)
            if not label or not source_fields:
                continue
            selected.append(
                {
                    "id": _checked_text(memory.get("id"), 80),
                    "type": memory_type,
                    "value": memory_value,
                    "label": label,
                    "source_stage": source_stage,
                    "source_fields": source_fields,
                    "persisted": True,
                }
            )
        except ValueError:
            continue
    return selected
