"""Thread-scoped short-term memory helpers for GitHub interview workflow.

This module stores only sanitized structured state. It must not persist raw
answers, follow-up answer text, repo evidence text, URLs, local paths, secrets,
or tracebacks.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


TABLE_NAME = "github_repo_interview_session_memories"
WORKFLOW_NAME = "github_repo_interview_workflow"

MAX_LIST_ITEMS = 20
MAX_TARGET_ROLE_LEN = 80
MAX_SUGGESTION_LEN = 240
MAX_EVIDENCE_ID_LEN = 160

ALLOWED_TARGET_ROLE_SOURCES = {
    "user_selected",
    "inferred_from_input",
    "carried_from_session",
    "unset",
}

TEXT_FORBIDDEN_MARKERS = (
    "http://",
    "https://",
    "api_key",
    "authorization:",
    "traceback",
)

EVIDENCE_FORBIDDEN_MARKERS = (
    "http://",
    "https://",
    "api_key",
    "authorization:",
    "traceback",
    "user_answer",
    "follow_up_answer",
    "raw_answer",
)

QUESTION_ID_RE = re.compile(r"^Q\d+$", re.IGNORECASE)


def _string(value: Any) -> str:
    return str(value or "").strip()


def _has_forbidden_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _safe_text(value: Any, max_len: int) -> str:
    text = _string(value)
    if not text or _has_forbidden_marker(text, TEXT_FORBIDDEN_MARKERS):
        return ""
    return text[:max_len]


def _normalize_question_id(value: Any) -> str:
    text = _string(value).upper()
    return text if QUESTION_ID_RE.match(text) else ""


def _dedup(values: List[str], limit: int = MAX_LIST_ITEMS) -> List[str]:
    result: List[str] = []
    for value in values:
        text = _string(value)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _question_ids(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return _dedup([qid for item in value if (qid := _normalize_question_id(item))])


def _evidence_ids(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    ids: List[str] = []
    for item in value:
        text = _string(item)[:MAX_EVIDENCE_ID_LEN]
        if not text or _has_forbidden_marker(text, EVIDENCE_FORBIDDEN_MARKERS):
            continue
        ids.append(text)
    return _dedup(ids)


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return default
        return parsed if parsed is not None else default
    return value if value is not None else default


def _timestamp(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def sanitize_session_memory_state(value: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    state: Dict[str, Any] = {}

    target_role = _safe_text(value.get("target_role"), MAX_TARGET_ROLE_LEN)
    if target_role:
        state["target_role"] = target_role

    target_role_source = _string(value.get("target_role_source"))
    if target_role_source in ALLOWED_TARGET_ROLE_SOURCES:
        state["target_role_source"] = target_role_source

    answered_question_ids = _question_ids(value.get("answered_question_ids"))
    if answered_question_ids:
        state["answered_question_ids"] = answered_question_ids

    last_question_id = _normalize_question_id(value.get("last_question_id"))
    if last_question_id:
        state["last_question_id"] = last_question_id

    current_practice_category = _safe_text(value.get("current_practice_category"), 80)
    if current_practice_category:
        state["current_practice_category"] = current_practice_category

    missed_evidence_ids = _evidence_ids(value.get("missed_evidence_ids"))
    if missed_evidence_ids:
        state["missed_evidence_ids"] = missed_evidence_ids

    next_practice_suggestion = _safe_text(value.get("next_practice_suggestion"), MAX_SUGGESTION_LEN)
    if next_practice_suggestion:
        state["next_practice_suggestion"] = next_practice_suggestion

    if isinstance(value.get("summary_completed"), bool):
        state["summary_completed"] = value["summary_completed"]

    return state


def _selected_question(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    selected = workflow_data.get("selected_question")
    return selected if isinstance(selected, dict) else {}


def _session_summary(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    summary = workflow_data.get("session_summary")
    return summary if isinstance(summary, dict) else {}


def _answer_feedback(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    feedback = workflow_data.get("answer_feedback")
    return feedback if isinstance(feedback, dict) else {}


def build_session_memory_patch(
    *,
    input_data: Dict[str, Any],
    workflow_data: Dict[str, Any],
    existing_memory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    input_data = input_data if isinstance(input_data, dict) else {}
    workflow_data = workflow_data if isinstance(workflow_data, dict) else {}
    existing = sanitize_session_memory_state(existing_memory or {})

    selected_question = _selected_question(workflow_data)
    session_summary = _session_summary(workflow_data)
    answer_feedback = _answer_feedback(workflow_data)

    patch: Dict[str, Any] = {}

    target_role = _safe_text(input_data.get("target_role"), MAX_TARGET_ROLE_LEN)
    if target_role:
        patch["target_role"] = target_role
        patch["target_role_source"] = "user_selected"
    elif existing.get("target_role"):
        patch["target_role"] = existing["target_role"]
        patch["target_role_source"] = "carried_from_session"

    question_ids: List[str] = []
    selected_question_id = _normalize_question_id(selected_question.get("id"))
    if selected_question_id:
        question_ids.append(selected_question_id)

    workflow_completion = session_summary.get("workflow_completion")
    if isinstance(workflow_completion, dict):
        question_ids.extend(_question_ids(workflow_completion.get("answered_question_ids")))

    question_ids = _dedup(question_ids)
    if question_ids:
        patch["answered_question_ids"] = question_ids
        patch["last_question_id"] = question_ids[-1]

    category = _safe_text(selected_question.get("category"), 80)
    if category:
        patch["current_practice_category"] = category

    missed_evidence = []
    missed_evidence.extend(_evidence_ids(session_summary.get("missed_evidence")))
    missed_evidence.extend(_evidence_ids(answer_feedback.get("evidence_missed")))
    if missed_evidence:
        patch["missed_evidence_ids"] = _dedup(missed_evidence)

    suggestion = _safe_text(session_summary.get("next_practice_suggestion"), MAX_SUGGESTION_LEN)
    if not suggestion:
        suggestion = _safe_text(workflow_data.get("next_practice_suggestion"), MAX_SUGGESTION_LEN)
    if suggestion:
        patch["next_practice_suggestion"] = suggestion

    stage = _string(input_data.get("stage"))
    if stage == "summarize" or session_summary:
        patch["summary_completed"] = True

    return sanitize_session_memory_state(patch)


def merge_session_memory(existing: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    existing_state = sanitize_session_memory_state(existing or {})
    patch_state = sanitize_session_memory_state(patch or {})
    merged = dict(existing_state)

    for key, value in patch_state.items():
        if key in {"answered_question_ids", "missed_evidence_ids"}:
            merged[key] = _dedup(list(merged.get(key) or []) + list(value or []))
        else:
            merged[key] = value

    return sanitize_session_memory_state(merged)


def row_to_session_memory(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    memory_state = _decode_json(row.get("memory_state"), {})
    state = sanitize_session_memory_state(memory_state if isinstance(memory_state, dict) else {})
    if row.get("thread_id") is not None:
        state["thread_id"] = str(row.get("thread_id"))
    if row.get("source_agent_run_id") is not None:
        state["source_agent_run_id"] = str(row.get("source_agent_run_id"))
    if row.get("updated_from_stage") is not None:
        state["updated_from_stage"] = str(row.get("updated_from_stage"))
    if row.get("created_at") is not None:
        state["created_at"] = _timestamp(row.get("created_at"))
    if row.get("updated_at") is not None:
        state["updated_at"] = _timestamp(row.get("updated_at"))
    return state


async def _select_row(client: Any, user_id: str, thread_id: str) -> Any:
    result = await (
        client.table(TABLE_NAME)
        .select("*")
        .eq("user_id", user_id)
        .eq("thread_id", thread_id)
        .eq("workflow_name", WORKFLOW_NAME)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )
    return result.data


async def load_session_memory(client: Any, user_id: str, thread_id: str) -> Dict[str, Any]:
    row = await _select_row(client, user_id, thread_id)
    if not row:
        return {}
    return row_to_session_memory(row)


async def upsert_session_memory(
    client: Any,
    user_id: str,
    thread_id: str,
    patch: Dict[str, Any],
    source_agent_run_id: str | None = None,
    updated_from_stage: str | None = None,
) -> Dict[str, Any]:
    sanitized_patch = sanitize_session_memory_state(patch or {})
    if not sanitized_patch:
        return await load_session_memory(client, user_id, thread_id)

    existing_row = await _select_row(client, user_id, thread_id)
    existing_state = row_to_session_memory(existing_row) if existing_row else {}
    merged_state = merge_session_memory(existing_state, sanitized_patch)
    now = datetime.now(timezone.utc).isoformat()

    values = {
        "memory_state": merged_state,
        "source_agent_run_id": source_agent_run_id,
        "updated_from_stage": updated_from_stage,
        "updated_at": now,
    }

    if existing_row:
        await (
            client.table(TABLE_NAME)
            .update(values)
            .eq("user_id", user_id)
            .eq("thread_id", thread_id)
            .eq("workflow_name", WORKFLOW_NAME)
            .eq("status", "active")
            .execute()
        )
    else:
        await (
            client.table(TABLE_NAME)
            .insert(
                {
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "workflow_name": WORKFLOW_NAME,
                    "memory_state": merged_state,
                    "source_agent_run_id": source_agent_run_id,
                    "updated_from_stage": updated_from_stage,
                    "status": "active",
                }
            )
            .execute()
        )

    return {
        **merged_state,
        "thread_id": thread_id,
        "source_agent_run_id": source_agent_run_id,
        "updated_from_stage": updated_from_stage,
    }
