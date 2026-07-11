"""Request-level answer quality diagnostic signals for GitHub interview workflow.

The signals are derived from already-sanitized workflow payload fields. This
module does not call LLMs, access GitHub, read local files, write databases, or
include user answer text.
"""

from typing import Any, Dict, List


Signal = Dict[str, Any]

HALLUCINATION_WARNING_CODES = {
    "filtered_hallucinated_references",
    "invalid_evidence_reference",
}

NEGATIVE_CONTEXT_TERMS = (
    "缺少",
    "不足",
    "需要补充",
    "未说明",
    "不清",
    "unclear",
    "missing",
    "weak",
)


def _items(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> List[str]:
    return [str(item).strip() for item in _items(value) if str(item or "").strip()]


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _warning_codes(warnings: List[Dict[str, Any]]) -> set[str]:
    return {
        str(warning.get("code") or "").strip()
        for warning in warnings
        if isinstance(warning, dict) and str(warning.get("code") or "").strip()
    }


def _safe_evidence_ref(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text:
        return ""
    if "://" in lowered:
        return ""
    if lowered.startswith(("readme:", "readme#", "readme/")) or "readme.md" in lowered:
        return ""
    return text


def _dedupe_safe_evidence_refs(values: List[str]) -> List[str]:
    refs = []
    for value in values:
        ref = _safe_evidence_ref(value)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _signal(
    signal_id: str,
    label: str,
    status: str,
    severity: str,
    basis_fields: List[str],
    evidence_refs: List[str] | None = None,
    notes: List[str] | None = None,
) -> Signal:
    return {
        "id": signal_id,
        "label": label,
        "status": status,
        "severity": severity,
        "basis_fields": basis_fields,
        "evidence_refs": _dedupe_safe_evidence_refs(evidence_refs or []),
        "notes": notes or [],
    }


def _missed_evidence_ids(data: Dict[str, Any]) -> List[str]:
    feedback = _dict(data.get("answer_feedback"))
    summary = _dict(data.get("session_summary"))
    missed = []
    for item in _items(feedback.get("evidence_missed")):
        if not isinstance(item, dict):
            continue
        evidence_id = _safe_evidence_ref(item.get("evidence_id"))
        if evidence_id and evidence_id not in missed:
            missed.append(evidence_id)
    for evidence_id in _strings(summary.get("missed_evidence")):
        safe_id = _safe_evidence_ref(evidence_id)
        if safe_id and safe_id not in missed:
            missed.append(safe_id)
    return missed


def _has_missed_evidence(data: Dict[str, Any]) -> bool:
    feedback = _dict(data.get("answer_feedback"))
    summary = _dict(data.get("session_summary"))
    return bool(_items(feedback.get("evidence_missed")) or _strings(summary.get("missed_evidence")))


def _missed_evidence_basis_fields(data: Dict[str, Any]) -> List[str]:
    feedback = _dict(data.get("answer_feedback"))
    summary = _dict(data.get("session_summary"))
    fields = []
    if _items(feedback.get("evidence_missed")):
        fields.append("answer_feedback.evidence_missed")
    if _strings(summary.get("missed_evidence")):
        fields.append("session_summary.missed_evidence")
    return fields or ["answer_feedback.evidence_missed", "session_summary.missed_evidence"]


def _covered_evidence_ids(data: Dict[str, Any]) -> List[str]:
    summary = _dict(data.get("session_summary"))
    return _dedupe_safe_evidence_refs(_strings(summary.get("covered_evidence")))


def _has_allowed_evidence(data: Dict[str, Any]) -> bool:
    policy = _dict(data.get("evidence_policy"))
    context_policy = _dict(data.get("context_policy"))
    snapshot = _dict(data.get("context_snapshot"))
    return bool(
        _strings(policy.get("allowed_evidence_ids"))
        or _strings(context_policy.get("allowed_evidence_ids"))
        or _strings(snapshot.get("allowed_evidence_ids"))
    )


def _has_answer_feedback(data: Dict[str, Any]) -> bool:
    feedback = _dict(data.get("answer_feedback"))
    return any(
        [
            bool(str(feedback.get("summary") or "").strip()),
            bool(_strings(feedback.get("strengths"))),
            bool(_strings(feedback.get("gaps"))),
            bool(_items(feedback.get("evidence_missed"))),
            bool(_strings(feedback.get("suggested_answer_outline"))),
            bool(_strings(feedback.get("grounding_notes"))),
        ]
    )


def _has_session_summary(data: Dict[str, Any]) -> bool:
    summary = _dict(data.get("session_summary"))
    return any(
        [
            bool(_strings(summary.get("covered_evidence"))),
            bool(_strings(summary.get("missed_evidence"))),
            bool(_strings(summary.get("practice_notes"))),
            bool(str(summary.get("next_practice_suggestion") or "").strip()),
        ]
    )


def _practice_basis_fields(data: Dict[str, Any]) -> List[str]:
    feedback = _dict(data.get("answer_feedback"))
    summary = _dict(data.get("session_summary"))
    fields = []
    if _strings(feedback.get("gaps")):
        fields.append("answer_feedback.gaps")
    if _strings(feedback.get("suggested_answer_outline")):
        fields.append("answer_feedback.suggested_answer_outline")
    if _strings(summary.get("practice_notes")):
        fields.append("session_summary.practice_notes")
    return fields or [
        "answer_feedback.gaps",
        "answer_feedback.suggested_answer_outline",
        "session_summary.practice_notes",
    ]


def _practice_text(data: Dict[str, Any]) -> str:
    feedback = _dict(data.get("answer_feedback"))
    summary = _dict(data.get("session_summary"))
    parts = (
        _strings(feedback.get("gaps"))
        + _strings(feedback.get("suggested_answer_outline"))
        + _strings(summary.get("practice_notes"))
    )
    return " ".join(parts).lower()


def _has_weak_context(text: str, topic_terms: tuple[str, ...]) -> bool:
    if not any(term in text for term in topic_terms):
        return False
    return any(term in text for term in NEGATIVE_CONTEXT_TERMS)


def _redaction_flags(data: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _dict(data.get("context_snapshot"))
    return _dict(snapshot.get("redaction_policy"))


def build_answer_quality_signals(
    data: Dict[str, Any],
    warnings: List[Dict[str, Any]] | None = None,
    errors: List[Dict[str, Any]] | None = None,
) -> List[Signal]:
    warnings = warnings or []
    errors = errors or []
    if errors:
        return []

    has_allowed = _has_allowed_evidence(data)
    missed_ids = _missed_evidence_ids(data)
    has_missed = _has_missed_evidence(data)
    covered_ids = _covered_evidence_ids(data)
    has_feedback = _has_answer_feedback(data)
    has_summary = _has_session_summary(data)
    warning_codes = _warning_codes(warnings)
    practice_text = _practice_text(data)
    missed_basis_fields = _missed_evidence_basis_fields(data)
    practice_basis_fields = _practice_basis_fields(data)

    signals: List[Signal] = []

    signals.append(
        _signal(
            "evidence_grounding",
            "证据支撑",
            "needs_attention" if has_missed else ("supported" if has_feedback else "not_available"),
            "warning" if has_missed else ("positive" if has_feedback else "neutral"),
            missed_basis_fields if has_missed else ["answer_feedback.grounding_notes"],
            missed_ids or covered_ids,
            ["存在遗漏 evidence。"] if has_missed else (["反馈已基于 allowed evidence 生成。"] if has_feedback else []),
        )
    )

    signals.append(
        _signal(
            "completeness_missing_evidence",
            "完整性 / 遗漏证据",
            "needs_attention" if has_missed else ("supported" if has_feedback else "not_available"),
            "warning" if has_missed else ("positive" if has_feedback else "neutral"),
            missed_basis_fields,
            missed_ids,
            ["本轮回答还有未覆盖的 allowed evidence。"] if has_missed else [],
        )
    )

    hallucination_codes = sorted(warning_codes.intersection(HALLUCINATION_WARNING_CODES))
    signals.append(
        _signal(
            "hallucination_risk",
            "幻觉引用风险",
            "guarded" if hallucination_codes else ("supported" if has_allowed else "not_available"),
            "warning" if hallucination_codes else ("positive" if has_allowed else "neutral"),
            [f"warnings.{code}" for code in hallucination_codes] or ["evidence_policy.allowed_evidence_ids"],
            [],
            ["未知引用已被过滤。"] if hallucination_codes else [],
        )
    )

    architecture_flag = _has_weak_context(practice_text, ("architecture", "架构"))
    signals.append(
        _signal(
            "architecture_understanding",
            "架构理解",
            "needs_attention" if architecture_flag else ("not_available" if not has_feedback else "supported"),
            "warning" if architecture_flag else ("neutral" if not has_feedback else "positive"),
            practice_basis_fields,
            [],
            ["反馈字段中出现架构表达相关缺口。"] if architecture_flag else [],
        )
    )

    tradeoff_flag = _has_weak_context(practice_text, ("tradeoff", "取舍", "权衡"))
    signals.append(
        _signal(
            "tradeoff_awareness",
            "取舍意识",
            "needs_attention" if tradeoff_flag else ("not_available" if not has_feedback else "supported"),
            "warning" if tradeoff_flag else ("neutral" if not has_feedback else "positive"),
            practice_basis_fields,
            [],
            ["反馈字段中出现设计取舍相关缺口。"] if tradeoff_flag else [],
        )
    )

    has_selected_question = bool(data.get("selected_question"))
    signals.append(
        _signal(
            "question_relevance",
            "问题相关性",
            "supported" if has_selected_question and has_feedback else "not_available",
            "positive" if has_selected_question and has_feedback else "neutral",
            ["selected_question", "answer_feedback"]
            if has_feedback
            else (["selected_question", "session_summary"] if has_summary else ["selected_question"]),
            [],
            ["已基于当前 selected question 生成反馈。"] if has_selected_question and has_feedback else [],
        )
    )

    redaction = _redaction_flags(data)
    redaction_values = [
        redaction.get("includes_user_answer"),
        redaction.get("includes_follow_up_answer"),
        redaction.get("includes_hidden_source_content"),
        redaction.get("includes_repo_evidence_text"),
    ]
    has_redaction = any(isinstance(value, bool) for value in redaction_values)
    unsafe_redaction = any(value is True for value in redaction_values)
    signals.append(
        _signal(
            "privacy_boundary",
            "隐私边界",
            "needs_attention" if unsafe_redaction else ("supported" if has_redaction else "not_available"),
            "warning" if unsafe_redaction else ("positive" if has_redaction else "neutral"),
            ["context_snapshot.redaction_policy"],
            [],
            ["质量信号不包含回答原文或 evidence 原文。"] if has_redaction and not unsafe_redaction else [],
        )
    )

    return signals
