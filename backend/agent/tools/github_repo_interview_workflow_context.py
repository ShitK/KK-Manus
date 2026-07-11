from copy import deepcopy
from typing import Any, Dict

from agent.tools.github_repo_interview_workflow_roles import role_contract


HIDDEN_CONTEXT_SOURCES = (
    "repo_metadata",
    "readme",
    "project_context_pack",
    "markdown",
    "thread_history",
    "local_files",
)


ROLE_VISIBLE_SOURCES = {
    "question_selector": (
        "selected_question",
        "question_generation_summary",
    ),
    "answer_coach": (
        "selected_question",
        "evidence_details",
        "evidence_policy",
        "user_answer",
    ),
    "follow_up_coach": (
        "selected_question",
        "evidence_details",
        "evidence_policy",
        "filtered_answer_feedback",
        "follow_up_answer",
    ),
    "session_summarizer": (
        "selected_question",
        "evidence_details",
        "evidence_policy",
        "filtered_answer_feedback",
        "filtered_follow_up",
    ),
}


def _allowed_source_paths(state: Dict[str, Any]) -> list[str]:
    paths = []
    for detail in state.get("evidence_details") or []:
        if not isinstance(detail, dict):
            continue
        source_path = detail.get("source_path")
        if isinstance(source_path, str) and source_path.strip() and source_path.strip() not in paths:
            paths.append(source_path.strip())
    return paths


def context_policy_for_state(state: Dict[str, Any], role_id: str) -> Dict[str, Any]:
    role = role_contract(role_id)
    evidence_policy = state.get("evidence_policy") if isinstance(state.get("evidence_policy"), dict) else {}
    visible_sources = ROLE_VISIBLE_SOURCES.get(
        role_id,
        ("selected_question", "evidence_details", "evidence_policy"),
    )
    return {
        "mode": "role_scoped",
        "active_role": role.get("id") or role_id,
        "role_kind": role.get("kind") or "deterministic",
        "source": evidence_policy.get("source") or "selected_question.evidence_details",
        "visible_sources": list(visible_sources),
        "hidden_sources": list(HIDDEN_CONTEXT_SOURCES),
        "allowed_evidence_ids": list(evidence_policy.get("allowed_evidence_ids") or []),
        "allowed_source_paths": _allowed_source_paths(state),
        "max_evidence_details": evidence_policy.get("max_evidence_details"),
        "repository_access": (
            role.get("repository_access")
            or evidence_policy.get("repository_access")
            or "no_new_repository_access"
        ),
        "tool_access": "none",
        "persists_user_answer": False,
    }


def attach_context_policy(
    request: Dict[str, Any],
    state: Dict[str, Any],
    role_id: str,
) -> Dict[str, Any]:
    request_with_policy = deepcopy(request)
    request_with_policy["context_policy"] = context_policy_for_state(state, role_id)
    return request_with_policy
