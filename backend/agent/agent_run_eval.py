import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


PASS = "pass"
WARN = "warn"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"

SUPPORTED_METRIC_IDS = (
    "run_liveness",
    "tool_reliability",
    "workflow_progress",
    "context_boundary",
    "evidence_grounding",
    "final_output_explainability",
)

FAILURE_PATTERNS = ("tool_failed", "timeout", "exception", "uncaught")
WARNING_PATTERNS = ("fallback", "warning", "partial", "normalized")


def _api_helpers():
    from agent import api as agent_api

    return agent_api


def _metric(
    metric_id: str,
    label: str,
    status: str,
    summary: str,
    details: Optional[List[str]] = None,
    basis: Optional[List[str]] = None,
    recommendation: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": metric_id,
        "label": label,
        "status": status,
        "summary": summary,
        "details": details or [],
        "basis": basis or [],
        "recommendation": recommendation or "",
    }


def _safe_parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item)


def _as_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(pattern in lowered for pattern in patterns)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _metadata_matches_agent_run(metadata: Any, agent_run_id: str) -> bool:
    return _metadata_run_id(metadata) == agent_run_id


def _metadata_run_id(metadata: Any) -> str:
    parsed = _safe_parse_json(metadata)
    if parsed is None and isinstance(metadata, dict):
        parsed = metadata
    if not isinstance(parsed, dict):
        return ""
    return str(parsed.get("agent_run_id") or parsed.get("thread_run_id") or "")


def _usage_content(message: Dict[str, Any]) -> Dict[str, Any]:
    content = _safe_parse_json(message.get("content"))
    if content is None and isinstance(message.get("content"), dict):
        content = message["content"]
    return content if isinstance(content, dict) else {}


def _usage_from_message(message: Dict[str, Any]) -> Dict[str, int]:
    """
    Only extract content.usage numeric fields.
    Do not copy the whole content object into the report because non-streaming
    assistant_response_end rows can contain raw prompt and assistant text.
    """
    content = _usage_content(message)
    usage = content.get("usage") if isinstance(content.get("usage"), dict) else {}
    prompt_tokens = _safe_int(usage.get("prompt_tokens"))
    completion_tokens = _safe_int(usage.get("completion_tokens"))
    total_tokens = _safe_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_time(row: Dict[str, Any]) -> Optional[datetime]:
    return _parse_datetime(row.get("created_at") or row.get("timestamp"))


def _run_time_window(run: Dict[str, Any]) -> tuple[Optional[datetime], Optional[datetime]]:
    started_at = _parse_datetime(run.get("started_at") or run.get("created_at"))
    ended_at = _parse_datetime(run.get("completed_at") or run.get("updated_at"))
    return started_at, ended_at


def _row_within_run_window(row: Dict[str, Any], run: Dict[str, Any]) -> bool:
    timestamp = _row_time(row)
    if timestamp is None:
        return False
    started_at, ended_at = _run_time_window(run)
    if started_at and timestamp < started_at:
        return False
    if ended_at and timestamp > ended_at:
        return False
    return True


def _filter_messages_for_run(messages: List[Dict[str, Any]], run: Dict[str, Any], agent_run_id: str) -> List[Dict[str, Any]]:
    tagged_messages = [message for message in messages if _metadata_run_id(message.get("metadata"))]
    if tagged_messages:
        return [
            message
            for message in tagged_messages
            if _metadata_matches_agent_run(message.get("metadata"), agent_run_id)
        ]
    return [message for message in messages if _row_within_run_window(message, run)]


def _filter_events_for_run(events: List[Dict[str, Any]], run: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not events:
        return []
    started_at, ended_at = _run_time_window(run)
    if not started_at and not ended_at:
        return events
    return [event for event in events if _row_within_run_window(event, run)]


async def _fetch_thread(client, thread_id: str) -> Dict[str, Any]:
    result = await (
        client.table("threads")
        .select("thread_id, project_id, account_id, name, created_at, updated_at")
        .eq("thread_id", thread_id)
        .execute()
    )
    return result.data[0] if result.data else {}


async def _fetch_recent_messages(client, thread_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    result = await (
        client.table("messages")
        .select("message_id, thread_id, type, content, metadata, created_at")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def _fetch_usage_messages(client, thread_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    result = await (
        client.table("messages")
        .select("message_id, thread_id, type, content, metadata, created_at")
        .eq("thread_id", thread_id)
        .eq("type", "assistant_response_end")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def _fetch_recent_events(client, thread_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    result = await (
        client.schema("public")
        .table("events")
        .select("id, session_id, author, content, timestamp")
        .eq("session_id", thread_id)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def _redis_snapshot(redis_client, agent_run_id: str) -> Dict[str, Any]:
    agent_api = _api_helpers()
    response_list_key = f"agent_run:{agent_run_id}:responses"
    try:
        resolved = await agent_api._get_diagnostic_redis_client(redis_client)
        response_count = await resolved.llen(response_list_key)
    except Exception:
        response_count = 0
    try:
        active_instance_keys = await agent_api._scan_active_run_keys(redis_client, agent_run_id)
    except Exception:
        active_instance_keys = []
    return {
        "response_count": response_count,
        "active_instance_keys": active_instance_keys,
    }


def _structured_failure_texts(rows: List[Dict[str, Any]]) -> List[str]:
    texts = []
    for row in rows:
        parsed = _safe_parse_json(row.get("content"))
        if parsed is None:
            continue
        for item in _walk_json(parsed):
            for key in ("error", "errors", "exception", "traceback"):
                if key in item:
                    texts.append(json.dumps(item.get(key), ensure_ascii=False))
            status = str(item.get("status") or "").lower()
            if status in {"error", "failed"}:
                texts.append(status)
            if item.get("success") is False and (item.get("tool") or item.get("name") or item.get("type")):
                texts.append("tool_failed")
    return texts


def _extract_raw_failure_signals(run: Dict[str, Any], messages: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> Dict[str, bool]:
    texts = [
        str(run.get("error") or ""),
        *_structured_failure_texts(messages),
        *_structured_failure_texts(events),
    ]
    joined = "\n".join(texts).lower()
    return {
        "has_traceback": "traceback" in joined,
        "has_timeout": "timeout" in joined,
        "has_exception": "exception" in joined or "uncaught" in joined,
        "has_tool_failed": "tool_failed" in joined,
    }


def _workflow_payload_from_value(value: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
    if depth > 4:
        return None
    parsed = _safe_parse_json(value)
    if parsed is not None:
        value = parsed
    if not isinstance(value, dict):
        return None

    tool = value.get("tool") or value.get("type") or value.get("name")
    if tool == "github_repo_interview_workflow" and (
        value.get("tool") == "github_repo_interview_workflow"
        or value.get("type") == "github_repo_interview_workflow"
    ):
        return value

    for key in ("result", "output", "content", "message"):
        payload = _workflow_payload_from_value(value.get(key), depth + 1)
        if payload:
            return payload

    response = _safe_dict(value.get("response"))
    for key in ("result", "output", "content", "message"):
        payload = _workflow_payload_from_value(response.get(key), depth + 1)
        if payload:
            return payload
    return None


def _workflow_payload_from_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tool = item.get("tool") or item.get("type") or item.get("name")
    if tool != "github_repo_interview_workflow":
        return None
    return _workflow_payload_from_value(item) or item


def _extract_workflow_payloads(messages: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    agent_api = _api_helpers()
    payloads = []
    for row in [*messages, *events]:
        parsed = _safe_parse_json(row.get("content"))
        if parsed is None:
            continue
        for item in _walk_json(parsed):
            payload = _workflow_payload_from_item(item)
            if payload:
                payloads.append(agent_api._sanitize_diagnostic_value(payload))
    return payloads


def _diagnostic_items_from_payloads(workflow_payloads: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    items = []
    for payload in workflow_payloads:
        data = _as_data(payload)
        for item in [*_safe_list(payload.get(key)), *_safe_list(data.get(key))]:
            if isinstance(item, dict):
                items.append(item)
    return items


def _warning_codes(workflow_payloads: List[Dict[str, Any]]) -> List[str]:
    codes = []
    for warning in _diagnostic_items_from_payloads(workflow_payloads, "warnings"):
        if warning.get("code"):
            codes.append(str(warning["code"]))
    return codes


def _error_codes(workflow_payloads: List[Dict[str, Any]]) -> List[str]:
    codes = []
    for error in _diagnostic_items_from_payloads(workflow_payloads, "errors"):
        if error.get("code"):
            codes.append(str(error["code"]))
    return codes


def _has_workflow_errors(workflow_payloads: List[Dict[str, Any]]) -> bool:
    return bool(_diagnostic_items_from_payloads(workflow_payloads, "errors"))


def _has_workflow_warnings(workflow_payloads: List[Dict[str, Any]]) -> bool:
    return bool(_diagnostic_items_from_payloads(workflow_payloads, "warnings"))


def _workflow_stage(payload: Dict[str, Any]) -> str:
    data = _as_data(payload)
    workflow = _safe_dict(data.get("workflow"))
    stage = workflow.get("stage") or workflow.get("current_stage")
    if stage:
        return str(stage)
    input_data = _safe_dict(payload.get("input"))
    stage = input_data.get("stage")
    return str(stage) if stage else ""


def _latest_workflow_stage(workflow_payloads: List[Dict[str, Any]]) -> str:
    for payload in reversed(workflow_payloads):
        stage = _workflow_stage(payload)
        if stage:
            return stage
    return ""


def _sanitized_previews(messages: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[str]:
    agent_api = _api_helpers()
    previews = [agent_api._preview_diagnostic_content(row.get("content")) for row in messages]
    previews += [agent_api._preview_diagnostic_content(row.get("content")) for row in events]
    return previews


def _latest_activity_time(run: Dict[str, Any], messages: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> Optional[datetime]:
    candidates = [
        _parse_datetime(run.get("updated_at")),
        _parse_datetime(run.get("created_at")),
        *[_parse_datetime(message.get("created_at")) for message in messages],
        *[_parse_datetime(event.get("timestamp")) for event in events],
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return max(candidates) if candidates else None


def _build_run_liveness_metric(
    run: Dict[str, Any],
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    redis_snapshot: Dict[str, Any],
    now: datetime,
) -> Dict[str, Any]:
    status = str(run.get("status") or "")
    if status in {"failed", "error"} or run.get("error"):
        return _metric(
            "run_liveness",
            "运行活跃度",
            FAIL,
            "Agent Run 失败或存在错误。",
            basis=["agent_run.status", "agent_run.error"],
            recommendation="查看后端日志和 tool_reliability 指标。",
        )
    if status in {"completed", "stopped"}:
        return _metric(
            "run_liveness",
            "运行活跃度",
            PASS,
            "Agent Run 已结束，没有检测到运行卡住。",
            basis=["agent_run.status", "agent_run.completed_at"],
        )
    if status == "running":
        if redis_snapshot.get("active_instance_keys") and redis_snapshot.get("response_count", 0) > 0:
            return _metric(
                "run_liveness",
                "运行活跃度",
                PASS,
                "Agent Run 正在运行，并且 Redis 仍有活动信号。",
                basis=["agent_run.status", "redis.active_instance_keys", "redis.response_count"],
            )
        latest = _latest_activity_time(run, messages, events)
        if not latest:
            return _metric(
                "run_liveness",
                "运行活跃度",
                NOT_APPLICABLE,
                "缺少可比较的运行时间字段。",
                basis=["agent_run.updated_at", "messages.created_at", "events.timestamp"],
            )
        if (now - latest).total_seconds() <= 120:
            return _metric(
                "run_liveness",
                "运行活跃度",
                PASS,
                "Agent Run 正在运行，最近 120 秒内有可见推进。",
                basis=["agent_run.updated_at", "messages.created_at", "events.timestamp"],
            )
        return _metric(
            "run_liveness",
            "运行活跃度",
            WARN,
            "Agent Run 正在运行，但最近 120 秒没有可见推进。",
            basis=["agent_run.updated_at", "messages.created_at", "events.timestamp"],
            recommendation="检查 worker、Redis stream 和最近 tool event。",
        )
    return _metric("run_liveness", "运行活跃度", NOT_APPLICABLE, "当前状态无法判断运行活跃度。")


def _build_tool_reliability_metric(
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    workflow_payloads: List[Dict[str, Any]],
    raw_failure_signals: Dict[str, bool],
) -> Dict[str, Any]:
    if any(raw_failure_signals.values()) or _has_workflow_errors(workflow_payloads):
        return _metric(
            "tool_reliability",
            "工具可靠性",
            FAIL,
            "检测到工具失败、异常堆栈、超时或 Workflow 错误信号。",
            basis=["agent_run.error", "messages.content", "events.content", "workflow_payload.errors"],
            recommendation="先定位失败工具和后端日志，再补充回归测试。",
        )
    previews = " ".join(_sanitized_previews(messages, events))
    warning_codes = _warning_codes(workflow_payloads)
    if _contains_any(previews, WARNING_PATTERNS) or warning_codes:
        return _metric(
            "tool_reliability",
            "工具可靠性",
            WARN,
            "检测到提醒、降级或部分结果，但本轮仍有结构化输出。",
            details=[f"提醒代码: {', '.join(warning_codes)}"] if warning_codes else [],
            basis=["messages.content", "events.content", "workflow_payload.warnings"],
            recommendation="保留结构化降级结果，并为对应 Workflow 阶段补回归测试。",
        )
    if workflow_payloads or _contains_any(previews, ("tool",)):
        return _metric(
            "tool_reliability",
            "工具可靠性",
            PASS,
            "未检测到工具失败信号。",
            basis=["messages.content", "events.content", "workflow_payload"],
        )
    return _metric("tool_reliability", "工具可靠性", NOT_APPLICABLE, "本轮没有检测到工具相关事件。")


def _build_workflow_progress_metric(workflow_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not workflow_payloads:
        return _metric("workflow_progress", "Workflow 推进", NOT_APPLICABLE, "未检测到受支持的 Workflow 结构化数据。")
    latest = workflow_payloads[-1]
    data = _as_data(latest)
    stage = _latest_workflow_stage(workflow_payloads)
    errors = _error_codes(workflow_payloads)
    warnings = _warning_codes(workflow_payloads)
    if errors:
        return _metric(
            "workflow_progress",
            "Workflow 推进",
            FAIL,
            "Workflow 结构化数据包含错误。",
            details=[f"错误代码: {', '.join(errors)}"],
            basis=["workflow_payload.errors"],
            recommendation="检查 Workflow 阶段的错误处理和降级输出。",
        )
    if warnings or data.get("partial"):
        return _metric(
            "workflow_progress",
            "Workflow 推进",
            WARN,
            "Workflow 返回了结构化结果，但包含提醒或部分结果信号。",
            details=[f"最近 Workflow 阶段: {stage or '未知'}", f"提醒代码: {', '.join(warnings)}"],
            basis=["workflow_payload.workflow.stage", "workflow_payload.warnings"],
            recommendation="确认提醒是否符合预期，并补充该 Workflow 阶段的回归测试。",
        )
    if stage:
        return _metric(
            "workflow_progress",
            "Workflow 推进",
            PASS,
            "Workflow 阶段可解释，且没有错误或提醒。",
            details=[f"最近 Workflow 阶段: {stage}"],
            basis=["workflow_payload.workflow.stage"],
        )
    return _metric(
        "workflow_progress",
        "Workflow 推进",
        FAIL,
        "Workflow 结构化数据缺少阶段信息，前端无法解释推进状态。",
        basis=["workflow_payload.workflow.stage"],
        recommendation="补齐 Workflow 阶段字段，或调整结构化数据规范化逻辑。",
    )


def _build_context_boundary_metric(workflow_payloads: List[Dict[str, Any]], sanitized_previews: List[str]) -> Dict[str, Any]:
    combined = " ".join(sanitized_previews).lower()
    if "api_key=" in combined or "authorization:" in combined or "traceback" in combined:
        return _metric(
            "context_boundary",
            "上下文边界",
            FAIL,
            "报告预览中仍有未脱敏边界风险信号。",
            basis=["messages.content", "events.content"],
            recommendation="修复 diagnostics redaction 后再开放前端展示。",
        )
    if not workflow_payloads:
        return _metric("context_boundary", "上下文边界", NOT_APPLICABLE, "当前运行没有相关 Workflow 或上下文结构化数据。")
    latest_data = _as_data(workflow_payloads[-1])
    snapshot = _safe_dict(latest_data.get("context_snapshot"))
    redaction_policy = _safe_dict(snapshot.get("redaction_policy"))
    if not redaction_policy:
        return _metric(
            "context_boundary",
            "上下文边界",
            WARN,
            "Workflow 存在，但缺少上下文边界信息。",
            basis=["context_snapshot.redaction_policy"],
            recommendation="补充上下文脱敏策略，或确认该 Workflow 不需要上下文边界检查。",
        )
    risky = [
        "includes_user_answer",
        "includes_follow_up_answer",
        "includes_repo_evidence_text",
        "includes_hidden_source_content",
    ]
    if any(redaction_policy.get(key) for key in risky):
        return _metric(
            "context_boundary",
            "上下文边界",
            FAIL,
            "上下文快照显示 Workflow 结构化数据可能包含原始回答或隐藏来源内容。",
            basis=["context_snapshot.redaction_policy"],
            recommendation="收紧 Workflow 结构化数据的脱敏策略。",
        )
    return _metric(
        "context_boundary",
        "上下文边界",
        PASS,
        "Context snapshot 明确排除了 raw answer、repo evidence text 和隐藏来源内容。",
        basis=["context_snapshot.redaction_policy"],
    )


def _build_evidence_grounding_metric(workflow_payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not workflow_payloads:
        return _metric("evidence_grounding", "证据引用", NOT_APPLICABLE, "当前运行没有证据策略。")
    warning_codes = _warning_codes(workflow_payloads)
    error_codes = _error_codes(workflow_payloads)
    joined_codes = " ".join([*warning_codes, *error_codes]).lower()
    if "invalid_evidence" in joined_codes or "unauthorized" in joined_codes:
        return _metric(
            "evidence_grounding",
            "证据引用",
            FAIL,
            "检测到无效或未授权 evidence 引用。",
            details=[f"诊断信号: {', '.join([*warning_codes, *error_codes])}"],
            basis=["workflow_payload.warnings", "workflow_payload.errors"],
            recommendation="检查 evidence allowlist 和引用过滤逻辑。",
        )
    if "missed" in joined_codes or "hallucinated" in joined_codes:
        return _metric(
            "evidence_grounding",
            "证据引用",
            WARN,
            "检测到遗漏 evidence 或幻觉引用过滤信号。",
            details=[f"提醒代码: {', '.join(warning_codes)}"] if warning_codes else [],
            basis=["workflow_payload.warnings"],
            recommendation="检查回答反馈与证据策略的衔接。",
        )
    latest_data = _as_data(workflow_payloads[-1])
    evidence_policy = _safe_dict(latest_data.get("evidence_policy"))
    if not evidence_policy:
        return _metric("evidence_grounding", "证据引用", NOT_APPLICABLE, "当前 Workflow 结构化数据没有证据策略。")
    allowed = _safe_list(evidence_policy.get("allowed_evidence_ids"))
    if allowed:
        return _metric(
            "evidence_grounding",
            "证据引用",
            PASS,
            "检测到允许引用的证据策略，且没有证据提醒。",
            details=[f"允许引用的证据数: {len(allowed)}"],
            basis=["evidence_policy.allowed_evidence_ids"],
        )
    return _metric("evidence_grounding", "证据引用", WARN, "证据策略存在，但允许引用的证据为空。")


def _model_event_text(content: Any) -> str:
    parsed = _safe_parse_json(content)
    if not isinstance(parsed, dict):
        return ""
    if parsed.get("role") != "model":
        return ""
    parts = _safe_list(parsed.get("parts"))
    text_parts = [
        str(part.get("text") or "").strip()
        for part in parts
        if isinstance(part, dict) and str(part.get("text") or "").strip()
    ]
    return "\n".join(text_parts).strip()


def _final_output_sources(messages: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    agent_api = _api_helpers()
    sources = [
        {
            "basis": "messages.content",
            "preview": agent_api._preview_diagnostic_content(message.get("content")),
        }
        for message in messages
        if message.get("type") == "assistant"
    ]
    for event in events:
        text = _model_event_text(event.get("content"))
        if text:
            sources.append(
                {
                    "basis": "events.content",
                    "preview": agent_api._preview_diagnostic_content(text),
                }
            )
    return [source for source in sources if source["preview"]]


def _build_final_output_metric(
    run: Dict[str, Any],
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    workflow_payloads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    status = str(run.get("status") or "")
    if status in {"failed", "error"} or run.get("error"):
        return _metric(
            "final_output_explainability",
            "最终输出可解释性",
            FAIL,
            "Agent Run 失败，无法确认有可解释的最终输出。",
            basis=["agent_run.status", "agent_run.error"],
            recommendation="先修复运行失败，再检查最终输出。",
        )
    output_sources = _final_output_sources(messages, events)
    if status == "running" and not output_sources:
        return _metric("final_output_explainability", "最终输出可解释性", NOT_APPLICABLE, "Run 仍在运行，尚未产生最终输出。")
    if output_sources and len(output_sources[0]["preview"]) >= 8:
        basis = sorted({source["basis"] for source in output_sources})
        return _metric(
            "final_output_explainability",
            "最终输出可解释性",
            PASS,
            "检测到可展示的 assistant 输出。",
            basis=basis,
        )
    if status == "completed" and workflow_payloads:
        return _metric(
            "final_output_explainability",
            "最终输出可解释性",
            WARN,
            "运行已完成，但主要输出像是结构化工具数据，缺少自然语言收束。",
            basis=["messages.content", "workflow_payload"],
            recommendation="补充面向用户的最终总结。",
        )
    return _metric(
        "final_output_explainability",
        "最终输出可解释性",
        FAIL if status == "completed" else NOT_APPLICABLE,
        "没有检测到可展示的最终输出。",
        basis=["messages.content", "events.content"],
    )


def _timeline_entry(time, kind, status, title, description, source):
    return {
        "time": time,
        "kind": kind,
        "status": status,
        "title": title,
        "description": description,
        "source": source,
    }


def _build_timeline(
    run: Dict[str, Any],
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    workflow_payloads: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    agent_api = _api_helpers()
    entries = []
    if run.get("started_at") or run.get("created_at"):
        entries.append(_timeline_entry(run.get("started_at") or run.get("created_at"), "agent_run.running", "normal", "运行开始", "状态进入运行中。", "agent_runs"))
    for message in messages[:20]:
        entries.append(
            _timeline_entry(
                message.get("created_at"),
                "message.created",
                "normal",
                f"Message: {message.get('type') or 'unknown'}",
                agent_api._preview_diagnostic_content(message.get("content"), max_length=120),
                "messages",
            )
        )
    for event in events[:20]:
        entries.append(
            _timeline_entry(
                event.get("timestamp"),
                "event.created",
                "normal",
                f"Event: {event.get('author') or 'unknown'}",
                agent_api._preview_diagnostic_content(event.get("content"), max_length=120),
                "events",
            )
        )
    for payload in workflow_payloads[-10:]:
        data = _as_data(payload)
        stage = _safe_dict(data.get("workflow")).get("stage") or "未知"
        warnings = _warning_codes([payload])
        errors = _error_codes([payload])
        entry_status = "fail" if errors else "warn" if warnings else "normal"
        entries.append(
            _timeline_entry(
                run.get("updated_at"),
                "workflow.stage.detected",
                entry_status,
                f"Workflow 阶段: {stage}",
                ", ".join([*warnings, *errors]) or "检测到 Workflow 结构化数据。",
                "workflow_payload",
            )
        )
    if run.get("completed_at"):
        status = "fail" if str(run.get("status")) in {"failed", "error"} or run.get("error") else "normal"
        entries.append(_timeline_entry(run.get("completed_at"), "agent_run.completed", status, "运行结束", f"最终状态: {run.get('status')}", "agent_runs"))
    entries.sort(key=lambda item: item.get("time") or "")
    return entries[:50]


def _build_token_usage(agent_run_id: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    matched = [
        message
        for message in messages
        if message.get("type") == "assistant_response_end"
        and _metadata_matches_agent_run(message.get("metadata"), agent_run_id)
    ]
    if not matched:
        return {
            "attribution": "none",
            "source": "messages.assistant_response_end.metadata.agent_run_id",
            "model": None,
            "models": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "message_count": 0,
            "estimated": False,
            "available": False,
            "note": "未找到带 agent_run_id 精确归属的 token usage；历史 run 可能缺少该 metadata。",
        }

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    models = []
    estimated = False

    for message in matched:
        usage = _usage_from_message(message)
        prompt_tokens += usage["prompt_tokens"]
        completion_tokens += usage["completion_tokens"]
        total_tokens += usage["total_tokens"]
        content = _usage_content(message)
        if content.get("model"):
            models.append(str(content["model"]))
        if content.get("usage_estimated") is True:
            estimated = True

    unique_models = sorted(set(models))
    return {
        "attribution": "exact",
        "source": "messages.assistant_response_end.metadata.agent_run_id",
        "model": unique_models[0] if len(unique_models) == 1 else None,
        "models": unique_models,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "message_count": len(matched),
        "estimated": estimated,
        "available": True,
        "note": "已按 agent_run_id 精确归属。",
    }


def _overall(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    statuses = [metric["status"] for metric in metrics]
    if FAIL in statuses:
        status = "failed"
        summary = "本轮 Agent Run 存在失败级诊断信号。"
    elif WARN in statuses:
        status = "attention"
        summary = "本轮 Agent Run 可解释，但存在需要关注的诊断信号。"
    else:
        status = "healthy"
        summary = "本轮 Agent Run 没有检测到需要关注的运行质量问题。"
    next_steps = [
        metric["recommendation"]
        for metric in metrics
        if metric["status"] in {WARN, FAIL} and metric.get("recommendation")
    ][:4]
    return {"status": status, "summary": summary, "next_steps": next_steps}


def _run_summary(
    run: Dict[str, Any],
    thread: Dict[str, Any],
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    redis_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    status = run.get("status") or "unknown"
    has_error = bool(run.get("error")) or status in {"failed", "error"}
    if has_error:
        summary_status = "failed"
        summary = "运行失败或存在错误。"
    elif status == "running":
        summary_status = "running"
        summary = "运行中，最近有可见推进。" if redis_snapshot.get("active_instance_keys") else "运行中，等待更多运行信号。"
    else:
        summary_status = "completed" if status == "completed" else str(status)
        summary = "已完成。" if status == "completed" else f"当前状态：{status}。"
    return {
        "agent_run_id": run.get("agent_run_id") or str(run.get("id")),
        "thread_id": run.get("thread_id"),
        "thread_name": thread.get("name"),
        "status": status,
        "started_at": run.get("started_at"),
        "updated_at": run.get("updated_at"),
        "completed_at": run.get("completed_at"),
        "has_error": has_error,
        "is_active": bool(redis_snapshot.get("active_instance_keys")),
        "message_count": len(messages),
        "event_count": len(events),
        "summary_status": summary_status,
        "summary": summary,
    }


async def build_agent_run_eval_report(
    client,
    redis_client,
    agent_run_id: str,
    user_id: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    agent_api = _api_helpers()
    now = now or datetime.now(timezone.utc)
    run = await agent_api.get_agent_run_with_access_check(client, agent_run_id, user_id)
    thread = await _fetch_thread(client, run["thread_id"])
    recent_messages = await _fetch_recent_messages(client, run["thread_id"])
    usage_messages = await _fetch_usage_messages(client, run["thread_id"])
    recent_events = await _fetch_recent_events(client, run["thread_id"])
    messages = _filter_messages_for_run(recent_messages, run, agent_run_id)
    events = _filter_events_for_run(recent_events, run)
    redis_state = await _redis_snapshot(redis_client, agent_run_id)
    raw_failure_signals = _extract_raw_failure_signals(run, messages, events)
    workflow_payloads = _extract_workflow_payloads(messages, events)
    previews = _sanitized_previews(messages, events)
    token_usage = _build_token_usage(agent_run_id, usage_messages)

    metrics = [
        _build_run_liveness_metric(run, messages, events, redis_state, now),
        _build_tool_reliability_metric(messages, events, workflow_payloads, raw_failure_signals),
        _build_workflow_progress_metric(workflow_payloads),
        _build_context_boundary_metric(workflow_payloads, previews),
        _build_evidence_grounding_metric(workflow_payloads),
        _build_final_output_metric(run, messages, events, workflow_payloads),
    ]

    warning_count = len(_warning_codes(workflow_payloads))
    error_count = len(_error_codes(workflow_payloads))
    fallback_count = sum(1 for code in _warning_codes(workflow_payloads) if "fallback" in code.lower())

    return {
        "run": _run_summary(run, thread, messages, events, redis_state),
        "overall": _overall(metrics),
        "metrics": metrics,
        "token_usage": token_usage,
        "timeline": _build_timeline(run, messages, events, workflow_payloads),
        "observations": {
            "tool_event_count": 1 if workflow_payloads else 0,
            "workflow_payload_count": len(workflow_payloads),
            "warning_count": warning_count,
            "error_count": error_count,
            "fallback_count": fallback_count,
        },
    }


async def list_agent_eval_runs(
    client,
    redis_client,
    user_id: str,
    limit: int = 20,
    status: str = "all",
) -> Dict[str, Any]:
    threads_result = await (
        client.table("threads")
        .select("thread_id, name, account_id")
        .eq("account_id", user_id)
        .order("updated_at", desc=True)
        .limit(300)
        .execute()
    )
    threads = threads_result.data or []
    thread_by_id = {thread.get("thread_id"): thread for thread in threads}
    thread_ids = [thread_id for thread_id in thread_by_id if thread_id]
    if not thread_ids:
        return {"runs": []}

    query = (
        client.table("agent_runs")
        .select("id, agent_run_id, thread_id, status, started_at, completed_at, error, created_at, updated_at")
        .in_("thread_id", thread_ids)
        .order("created_at", desc=True)
    )
    if status != "all":
        query = query.eq("status", status)
    runs_result = await query.execute()
    rows = runs_result.data or []

    summaries = []
    for run in rows:
        agent_run_id = run.get("agent_run_id") or str(run.get("id"))
        recent_messages = await _fetch_recent_messages(client, run.get("thread_id"), limit=10)
        recent_events = await _fetch_recent_events(client, run.get("thread_id"), limit=10)
        messages = _filter_messages_for_run(recent_messages, run, agent_run_id)
        events = _filter_events_for_run(recent_events, run)
        redis_state = await _redis_snapshot(redis_client, agent_run_id)
        summaries.append(_run_summary(run, thread_by_id.get(run.get("thread_id"), {}), messages, events, redis_state))

    summaries.sort(
        key=lambda item: (
            item["status"] != "running",
            _parse_datetime(item.get("updated_at") or item.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=False,
    )
    running = [item for item in summaries if item["status"] == "running"]
    others = [item for item in summaries if item["status"] != "running"]
    others.sort(
        key=lambda item: _parse_datetime(item.get("updated_at") or item.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return {"runs": [*running, *others][:limit]}
