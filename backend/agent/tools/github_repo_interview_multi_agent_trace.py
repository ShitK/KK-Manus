"""Request-level controlled multi-agent trace helpers for GitHub interviews.

The trace is display metadata only. It does not read repositories, local files,
databases, or persist memory, and it must not include raw user answers.
"""

from copy import deepcopy
from typing import Any, Dict, List


TRACE_VERSION = "v1"
TRACE_MODE = "controlled_local_trace"
TRACE_SCOPE = "request"

ALLOWED_AGENT_IDS = {
    "repository_analyst",
    "interview_question",
    "answer_coach",
    "quality_reviewer",
}
ALLOWED_STATUSES = {"pending", "success", "partial", "error", "skipped"}
SAFE_REPOSITORY_ACCESS = "no_new_repository_access"
SAFE_TOOL_ACCESS = "none"

def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [_string(item) for item in value if _string(item)]


def _safe_status(value: str) -> str:
    normalized = _string(value)
    return normalized if normalized in ALLOWED_STATUSES else "pending"


def _workflow(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("workflow") if isinstance(data.get("workflow"), dict) else {}


def _context_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("context_snapshot") if isinstance(data.get("context_snapshot"), dict) else {}


def _evidence_policy(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("evidence_policy") if isinstance(data.get("evidence_policy"), dict) else {}


def _answer_feedback(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("answer_feedback") if isinstance(data.get("answer_feedback"), dict) else {}


def _session_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    return data.get("session_summary") if isinstance(data.get("session_summary"), dict) else {}


def _evidence_details(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    details = data.get("evidence_details") if isinstance(data.get("evidence_details"), list) else []
    return [item for item in details if isinstance(item, dict)]


def _allowed_evidence_ids(data: Dict[str, Any]) -> List[str]:
    policy = _evidence_policy(data)
    ids = _string_list(policy.get("allowed_evidence_ids"))
    if ids:
        return ids
    return [_string(item.get("evidence_id")) for item in _evidence_details(data) if _string(item.get("evidence_id"))]


def _allowed_source_paths(data: Dict[str, Any]) -> List[str]:
    snapshot = _context_snapshot(data)
    paths = _string_list(snapshot.get("allowed_source_paths"))
    if paths:
        return paths
    seen = set()
    allowed = []
    for item in _evidence_details(data):
        path = _string(item.get("source_path"))
        if path and path not in seen:
            seen.add(path)
            allowed.append(path)
    return allowed


def _has_answer_feedback(data: Dict[str, Any]) -> bool:
    feedback = _answer_feedback(data)
    if _string(feedback.get("summary")):
        return True
    for key in ("strengths", "gaps", "evidence_missed", "suggested_answer_outline", "follow_up_questions"):
        value = feedback.get(key)
        if isinstance(value, list) and any(_string(item) for item in value):
            return True
    return False


def _has_follow_up_feedback(data: Dict[str, Any]) -> bool:
    follow_up = data.get("follow_up") if isinstance(data.get("follow_up"), dict) else {}
    return bool(_string_list(follow_up.get("feedback")))


def _missed_evidence(data: Dict[str, Any]) -> bool:
    feedback = _answer_feedback(data)
    summary = _session_summary(data)
    return bool(
        (isinstance(feedback.get("evidence_missed"), list) and feedback.get("evidence_missed"))
        or _string_list(summary.get("missed_evidence"))
    )


def _notice_codes(notices: List[Dict[str, Any]]) -> set[str]:
    return {
        _string(notice.get("code"))
        for notice in notices
        if isinstance(notice, dict) and _string(notice.get("code"))
    }


def _redaction_policy_safe(snapshot: Dict[str, Any]) -> bool:
    policy = snapshot.get("redaction_policy") if isinstance(snapshot.get("redaction_policy"), dict) else {}
    unsafe_keys = (
        "includes_user_answer",
        "includes_follow_up_answer",
        "includes_hidden_source_content",
        "includes_repo_evidence_text",
    )
    return not any(policy.get(key) is True for key in unsafe_keys)


def _boundary_is_safe(data: Dict[str, Any]) -> bool:
    snapshot = _context_snapshot(data)
    repository_access = _string(snapshot.get("repository_access")) or _string(_evidence_policy(data).get("repository_access"))
    tool_access = _string(snapshot.get("tool_access")) or SAFE_TOOL_ACCESS
    persists_user_answer = snapshot.get("persists_user_answer")
    return (
        (not repository_access or repository_access == SAFE_REPOSITORY_ACCESS)
        and tool_access == SAFE_TOOL_ACCESS
        and persists_user_answer is not True
        and _redaction_policy_safe(snapshot)
    )


def _quality_signals(data: Dict[str, Any], warnings: List[Dict[str, Any]], errors: List[Dict[str, Any]]) -> Dict[str, str]:
    workflow = _workflow(data)
    current_stage = _string(workflow.get("current_stage"))
    allowed_ids = _allowed_evidence_ids(data)
    warning_codes = _notice_codes(warnings)
    error_codes = _notice_codes(errors)

    if not _has_answer_feedback(data) and current_stage == "question_selected":
        coverage = "not_started"
    elif _missed_evidence(data):
        coverage = "partial"
    elif _has_answer_feedback(data) or _string_list(_session_summary(data).get("covered_evidence")):
        coverage = "grounded"
    else:
        coverage = "not_started"

    partial_grounding_codes = {
        "filtered_hallucinated_references",
        "follow_up_feedback_fallback_used",
        "coach_generation_failed",
        "invalid_question",
        "invalid_question_evidence",
    }
    if not allowed_ids or not _evidence_details(data):
        evidence_grounding = "missing"
    elif warning_codes.intersection(partial_grounding_codes) or error_codes.intersection(partial_grounding_codes):
        evidence_grounding = "partial"
    else:
        evidence_grounding = "grounded"

    if errors:
        boundary_health = "error"
    elif warnings or not _boundary_is_safe(data):
        boundary_health = "warning"
    else:
        boundary_health = "clean"

    if current_stage == "question_selected" and not _has_answer_feedback(data):
        next_step = "answer_question"
    elif error_codes.intersection({"coach_generation_failed", "follow_up_generation_failed"}):
        next_step = "retry_same_stage"
    elif error_codes.intersection({"invalid_question", "invalid_question_evidence", "question_not_found"}):
        next_step = "select_another_question"
    elif coverage == "partial" or evidence_grounding == "partial":
        next_step = "revise_with_evidence"
    elif _string_list(_answer_feedback(data).get("follow_up_questions")) and not _has_follow_up_feedback(data):
        next_step = "answer_follow_up"
    elif _has_answer_feedback(data):
        next_step = "summarize"
    else:
        next_step = "answer_question"

    return {
        "coverage": coverage,
        "evidence_grounding": evidence_grounding,
        "boundary_health": boundary_health,
        "recommended_next_step": next_step,
    }


def _agent(
    agent_id: str,
    role_name: str,
    status: str,
    stage: str,
    input_sources: List[str],
    visible_context: List[str],
    forbidden_scope: List[str],
    uses_repo_evidence: bool,
    reads_user_answer: bool,
    output_summary: str,
) -> Dict[str, Any]:
    return {
        "id": agent_id,
        "role_name": role_name,
        "status": _safe_status(status),
        "stage": stage,
        "input_sources": input_sources,
        "visible_context": visible_context,
        "forbidden_scope": forbidden_scope,
        "uses_repo_evidence": uses_repo_evidence,
        "reads_user_answer": reads_user_answer,
        "persists_memory": False,
        "output_summary": output_summary,
    }


def _answer_agent_status(data: Dict[str, Any], errors: List[Dict[str, Any]]) -> str:
    if errors and _workflow(data).get("active_role") == "answer_coach":
        return "error"
    if _has_answer_feedback(data) or _has_follow_up_feedback(data):
        return "success"
    if _workflow(data).get("current_stage") == "question_selected":
        return "pending"
    return "partial"


def _quality_agent_status(errors: List[Dict[str, Any]], warnings: List[Dict[str, Any]]) -> str:
    if errors:
        return "error"
    if warnings:
        return "partial"
    return "success"


def build_multi_agent_trace(
    state: Dict[str, Any],
    data: Dict[str, Any],
    input_data: Dict[str, Any],
    warnings: List[Dict[str, Any]] | None = None,
    errors: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    del state, input_data
    safe_data = deepcopy(data if isinstance(data, dict) else {})
    warning_list = [item for item in warnings or [] if isinstance(item, dict)]
    error_list = [item for item in errors or [] if isinstance(item, dict)]
    allowed_ids = _allowed_evidence_ids(safe_data)
    allowed_paths = _allowed_source_paths(safe_data)
    visible_evidence = allowed_ids + allowed_paths
    current_stage = _string(_workflow(safe_data).get("current_stage"))
    signals = _quality_signals(safe_data, warning_list, error_list)

    agents = [
        _agent(
            "repository_analyst",
            "RepositoryAnalystAgent",
            "success" if visible_evidence else "partial",
            "prep",
            ["prep_questions_pack.question_generation_summary", "selected_question.evidence_details"],
            visible_evidence,
            ["user_answer", "local_files", "new_github_reads_after_prep", "thread_history"],
            True,
            False,
            "基于已读取的仓库证据摘要项目结构、关键文件和架构边界。",
        ),
        _agent(
            "interview_question",
            "InterviewQuestionAgent",
            "success" if allowed_ids else "error",
            "prep",
            ["repository_analyst.output_summary", "selected_question.evidence_details"],
            visible_evidence,
            ["unsupported_questions_without_evidence", "user_answer", "local_files"],
            True,
            False,
            "基于允许范围内的证据生成结构化面试题包和证据引用。",
        ),
        _agent(
            "answer_coach",
            "AnswerCoachAgent",
            _answer_agent_status(safe_data, error_list),
            current_stage or "coach_answer",
            ["selected_question", "evidence_details", "context_snapshot", "current_user_answer"],
            ["selected_question"] + visible_evidence,
            ["new_github_reads", "local_files", "non_allowlisted_repo_evidence", "persist_raw_user_answer"],
            True,
            True,
            "基于当前题目、当前回答和允许范围内的证据生成结构化辅导反馈。",
        ),
        _agent(
            "quality_reviewer",
            "QualityReviewerAgent",
            _quality_agent_status(error_list, warning_list),
            current_stage or "coach_answer",
            ["answer_feedback", "follow_up", "session_summary", "context_snapshot", "warnings", "errors"],
            ["structured_feedback", "context_boundary_metadata"] + visible_evidence,
            ["raw_user_answer", "direct_repo_reads", "direct_github_reads", "candidate_scoring"],
            bool(allowed_ids),
            False,
            "基于结构化反馈和上下文边界信息生成本地诊断信号与下一步建议。",
        ),
    ]

    return {
        "version": TRACE_VERSION,
        "mode": TRACE_MODE,
        "scope": TRACE_SCOPE,
        "orchestrator": {
            "name": "MainAgent",
            "status": _safe_status("error" if error_list else "success"),
            "output_summary": "按固定 stage 调度 GitHub 面试工作流。",
        },
        "agents": [agent for agent in agents if agent["id"] in ALLOWED_AGENT_IDS],
        "quality_signals": signals,
    }
