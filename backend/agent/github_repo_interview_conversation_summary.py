import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.tools.github_repo_interview_session_memory import sanitize_session_memory_state
from services.llm import make_llm_api_call
from utils.config import config
from utils.logger import logger


TOOL_NAME = "github_repo_interview_conversation_summary"
MAX_TURN_TEXT_CHARS = 1200


def _json_loads_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return value


def _safe_string(value: Any, max_chars: int = 300) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _safe_string_list(value: Any, max_items: int = 6, max_chars: int = 160) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _safe_string(item, max_chars)
        if text:
            result.append(text)
        if len(result) >= max_items:
            break
    return result


def _safe_usage(value: Any) -> Dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    prompt_tokens = _safe_int(
        usage.get("prompt_tokens")
        or usage.get("prompt_token_count")
        or usage.get("input_tokens")
    )
    completion_tokens = _safe_int(
        usage.get("completion_tokens")
        or usage.get("candidates_token_count")
        or usage.get("output_tokens")
    )
    total_tokens = _safe_int(usage.get("total_tokens") or usage.get("total_token_count"))
    if not total_tokens:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    return {}


def _response_value(response: Any, key: str) -> Any:
    if isinstance(response, dict):
        return response.get(key)
    return getattr(response, key, None)


def _approx_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 1) // 2)


def _llm_metadata_from_response(
    response: Any,
    fallback_model: str,
    prompt_messages: List[Dict[str, Any]],
    response_text: str,
) -> Dict[str, Any]:
    model = _safe_string(_response_value(response, "model"), 160) or fallback_model
    usage = _safe_usage(_as_dict(_response_value(response, "usage")))
    usage_source = "provider"
    if not usage["total_tokens"]:
        prompt_text = json.dumps(prompt_messages or [], ensure_ascii=False)
        usage = {
            "prompt_tokens": _approx_token_count(prompt_text),
            "completion_tokens": _approx_token_count(response_text),
            "total_tokens": _approx_token_count(prompt_text) + _approx_token_count(response_text),
        }
        usage_source = "estimated_char_count"
    return {
        "model": model,
        "usage": usage,
        "usage_source": usage_source,
    }


def _safe_llm_metadata(value: Any) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    usage = _safe_usage(source.get("usage"))
    return {
        "model": _safe_string(source.get("model"), 160),
        "usage": usage,
        "usage_source": _safe_string(source.get("usage_source"), 80) or "unavailable",
    }


def _safe_practice_overview(value: Any, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    fallback_source = fallback if isinstance(fallback, dict) else {}
    unknown = "未在本轮对话中明确"
    return {
        "repository": _safe_string(source.get("repository"), 120)
        or _safe_string(fallback_source.get("repository"), 120)
        or unknown,
        "role": _safe_string(source.get("role"), 80)
        or _safe_string(fallback_source.get("role"), 80)
        or unknown,
        "difficulty": _safe_string(source.get("difficulty"), 80)
        or _safe_string(fallback_source.get("difficulty"), 80)
        or unknown,
        "completed_items": _safe_string_list(
            source.get("completed_items") or fallback_source.get("completed_items"),
            max_items=10,
            max_chars=140,
        ),
        "unfinished_items": _safe_string_list(
            source.get("unfinished_items") or source.get("open_items") or fallback_source.get("unfinished_items"),
            max_items=10,
            max_chars=140,
        ),
    }


def _safe_title_detail_list(value: Any, max_items: int = 8) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            title = _safe_string(item.get("title") or item.get("name"), 80)
            detail = _safe_string(item.get("detail") or item.get("description") or item.get("rationale"), 500)
        else:
            title = ""
            detail = _safe_string(item, 500)
        if title or detail:
            result.append({"title": title or "亮点", "detail": detail})
        if len(result) >= max_items:
            break
    return result


def _safe_improvement_list(value: Any, max_items: int = 8) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            weakness = _safe_string(item.get("weakness") or item.get("title"), 100)
            evidence = _safe_string(item.get("evidence") or item.get("specific_behavior") or item.get("detail"), 420)
            suggestion = _safe_string(item.get("suggestion") or item.get("improvement_suggestion"), 420)
        else:
            weakness = _safe_string(item, 100)
            evidence = ""
            suggestion = ""
        if weakness or evidence or suggestion:
            result.append(
                {
                    "weakness": weakness or "待打磨点",
                    "evidence": evidence,
                    "suggestion": suggestion,
                }
            )
        if len(result) >= max_items:
            break
    return result


def _safe_ability_profile(value: Any, max_items: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        dimension = _safe_string(item.get("dimension") or item.get("name"), 80)
        score_value = item.get("score")
        score: Optional[int] = None
        if isinstance(score_value, (int, float)):
            score = max(0, min(100, int(round(score_value))))
        elif isinstance(score_value, str):
            try:
                score = max(0, min(100, int(round(float(score_value.strip().rstrip("%"))))))
            except ValueError:
                score = None
        rationale = _safe_string(item.get("rationale") or item.get("detail"), 420)
        if dimension or rationale or score is not None:
            result.append(
                {
                    "dimension": dimension or "综合能力",
                    "score": score,
                    "rationale": rationale,
                }
            )
        if len(result) >= max_items:
            break
    return result


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, timezone.utc)


def _parts_text(content: Dict[str, Any]) -> str:
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    texts = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text") or part.get("content")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return "\n".join(texts).strip()


def _text_from_event_content(content: Any) -> str:
    parsed = _json_loads_maybe(content)
    if isinstance(parsed, str):
        return parsed.strip()
    if not isinstance(parsed, dict):
        return ""
    direct = parsed.get("content") or parsed.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return _parts_text(parsed)


def _role_from_event(row: Dict[str, Any]) -> str:
    content = _json_loads_maybe(row.get("content"))
    if isinstance(content, dict):
        role = str(content.get("role") or "").strip().lower()
        if role == "user":
            return "user"
        if role in {"model", "assistant"}:
            return "assistant"
    author = str(row.get("author") or "").strip().lower()
    if author == "user":
        return "user"
    if author:
        return "assistant"
    return ""


def _text_from_message_content(content: Any) -> str:
    parsed = _json_loads_maybe(content)
    if isinstance(parsed, str):
        return parsed.strip()
    if not isinstance(parsed, dict):
        return ""
    direct = parsed.get("content") or parsed.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return _parts_text(parsed)


def _role_from_message(row: Dict[str, Any]) -> str:
    message_type = str(row.get("type") or "").strip().lower()
    if message_type in {"tool", "status", "assistant_response_end"}:
        return ""
    if message_type == "user":
        return "user"
    if message_type == "assistant":
        return "assistant"
    content = _json_loads_maybe(row.get("content"))
    if isinstance(content, dict):
        role = str(content.get("role") or "").strip().lower()
        if role in {"user", "assistant"}:
            return role
    return ""


def extract_conversation_turns(
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    max_turns: int = 24,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, Any]] = []
    for event in events or []:
        role = _role_from_event(event)
        text = _text_from_event_content(event.get("content"))
        if role and text:
            rows.append(
                {
                    "role": role,
                    "text": _safe_string(text, MAX_TURN_TEXT_CHARS),
                    "source": "events",
                    "time": event.get("timestamp") or event.get("created_at"),
                }
            )
    for message in messages or []:
        role = _role_from_message(message)
        text = _text_from_message_content(message.get("content"))
        if role and text:
            rows.append(
                {
                    "role": role,
                    "text": _safe_string(text, MAX_TURN_TEXT_CHARS),
                    "source": "messages",
                    "time": message.get("created_at") or message.get("timestamp"),
                }
            )
    rows.sort(key=lambda row: _parse_time(row.get("time")))
    bounded = rows[-max(1, int(max_turns or 24)) :]
    return [
        {"role": row["role"], "text": row["text"], "source": row["source"]}
        for row in bounded
    ]


def _fallback_summary(turns: List[Dict[str, str]]) -> Dict[str, Any]:
    if not turns:
        overview = "暂无足够可见对话可总结。"
    else:
        overview = "本轮总结基于当前 thread 中可见的用户与 agent 对话生成。"
    question_ids: List[str] = []
    for turn in turns:
        upper = turn.get("text", "").upper()
        for index in range(1, 10):
            question_id = f"Q{index}"
            if question_id in upper and question_id not in question_ids:
                question_ids.append(question_id)
    return {
        "overview": overview,
        "discussed_questions": question_ids,
        "agent_help": ["整理当前可见对话中的练习脉络。"] if turns else [],
        "open_items": ["继续选择题目练习，或补充更多对话后再总结。"] if not turns else [],
        "practice_overview": {
            "repository": "未在本轮对话中明确",
            "role": "未在本轮对话中明确",
            "difficulty": "未在本轮对话中明确",
            "completed_items": question_ids,
            "unfinished_items": ["未在本轮对话中明确"] if turns else [],
        },
        "performance_highlights": [
            {"title": "对话脉络整理", "detail": "已基于当前 thread 中可见的用户与 agent 对话生成总结。"}
        ]
        if turns
        else [],
        "improvement_areas": [],
        "ability_profile": [],
        "next_practice_steps": ["继续选择下一题练习，或要求我按面试表达重新整理某个回答。"],
        "next_practice_suggestion": "继续选择下一题练习，或要求我按面试表达重新整理某个回答。",
    }


def _sanitize_llm_summary(summary: Optional[Dict[str, Any]], turns: List[Dict[str, str]]) -> Dict[str, Any]:
    source = summary if isinstance(summary, dict) else _fallback_summary(turns)
    fallback = _fallback_summary(turns)
    overview = _safe_string(source.get("overview"), 500) or fallback["overview"]
    next_step = _safe_string(source.get("next_practice_suggestion"), 240) or fallback["next_practice_suggestion"]
    return {
        "overview": overview,
        "raw_report": _safe_string(source.get("raw_report"), 8000),
        "_llm_metadata": _safe_llm_metadata(source.get("_llm_metadata")),
        "discussed_questions": _safe_string_list(source.get("discussed_questions"), max_items=10, max_chars=80),
        "agent_help": _safe_string_list(source.get("agent_help"), max_items=8, max_chars=180),
        "open_items": _safe_string_list(source.get("open_items"), max_items=8, max_chars=180),
        "practice_overview": _safe_practice_overview(
            source.get("practice_overview"),
            fallback.get("practice_overview"),
        ),
        "performance_highlights": _safe_title_detail_list(
            source.get("performance_highlights"),
            max_items=8,
        ),
        "improvement_areas": _safe_improvement_list(
            source.get("improvement_areas"),
            max_items=8,
        ),
        "ability_profile": _safe_ability_profile(
            source.get("ability_profile"),
            max_items=8,
        ),
        "next_practice_steps": _safe_string_list(
            source.get("next_practice_steps"),
            max_items=8,
            max_chars=220,
        )
        or fallback.get("next_practice_steps", []),
        "next_practice_suggestion": next_step,
    }


def _workflow_steps() -> List[Dict[str, str]]:
    return [
        {"id": "prep", "label": "Prep", "status": "success"},
        {"id": "question", "label": "Question", "status": "success"},
        {"id": "answer_coach", "label": "Answer Coach", "status": "success"},
        {"id": "quality_reviewer", "label": "Quality Reviewer", "status": "partial"},
        {"id": "summary", "label": "Summary", "status": "success"},
    ]


def _question_ids_from_summary_items(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    question_ids: List[str] = []
    for item in items:
        text = str(item or "")
        for match in re.findall(r"\bQ\d+\b", text, flags=re.IGNORECASE):
            question_id = match.upper()
            if question_id not in question_ids:
                question_ids.append(question_id)
    return question_ids


def build_conversation_summary_session_memory_patch(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    summary = data.get("conversation_summary") if isinstance(data.get("conversation_summary"), dict) else {}
    session_summary = data.get("session_summary") if isinstance(data.get("session_summary"), dict) else {}
    practice_overview = summary.get("practice_overview") if isinstance(summary.get("practice_overview"), dict) else {}

    patch: Dict[str, Any] = {"summary_completed": True}
    target_role = _safe_string(practice_overview.get("role"), 80)
    if target_role:
        patch["target_role"] = target_role
        patch["target_role_source"] = "inferred_from_input"

    question_ids = _question_ids_from_summary_items(summary.get("discussed_questions"))
    if question_ids:
        patch["answered_question_ids"] = question_ids
        patch["last_question_id"] = question_ids[-1]

    suggestion = _safe_string(
        session_summary.get("next_practice_suggestion") or summary.get("next_practice_suggestion"),
        240,
    )
    if suggestion:
        patch["next_practice_suggestion"] = suggestion

    return sanitize_session_memory_state(patch)


def build_conversation_summary_payload(
    turns: List[Dict[str, str]],
    llm_summary: Optional[Dict[str, Any]],
    language: str = "zh",
    fallback_reason_code: Optional[str] = None,
) -> Dict[str, Any]:
    used_fallback = not isinstance(llm_summary, dict)
    summary = _sanitize_llm_summary(llm_summary, turns)
    llm_metadata = _safe_llm_metadata(summary.get("_llm_metadata"))
    status = "partial" if used_fallback else "success"
    warnings = []
    if used_fallback:
        warnings.append(
            {
                "code": "conversation_summary_fallback_used",
                "message": "Conversation summary used deterministic fallback because LLM output was unavailable.",
            }
        )
        if fallback_reason_code:
            warnings.append(
                {
                    "code": fallback_reason_code,
                    "message": "Conversation summary LLM output was unavailable or not usable.",
                }
            )
    payload = {
        "tool": TOOL_NAME,
        "type": TOOL_NAME,
        "status": status,
        "input": {
            "summary_scope": "thread_dialogue",
            "language": language,
            "max_turns": 24,
        },
        "data": {
            "summary_kind": "conversation_summary",
            "conversation_turn_count": len(turns or []),
            "llm_metadata": llm_metadata,
            "workflow": {
                "current_stage": "summary_ready",
                "steps": _workflow_steps(),
            },
            "conversation_summary": {
                key: value
                for key, value in summary.items()
                if key
                in {
                    "overview",
                    "raw_report",
                    "discussed_questions",
                    "agent_help",
                    "open_items",
                    "practice_overview",
                    "performance_highlights",
                    "improvement_areas",
                    "ability_profile",
                    "next_practice_steps",
                }
            },
            "session_summary": {
                "practice_notes": [
                    "本次总结来自 thread 可见对话，不代表结构化 workflow 点评全部完成。",
                    "总结没有重新读取 GitHub 仓库。",
                ],
                "next_practice_suggestion": summary["next_practice_suggestion"],
                "workflow_completion": {
                    "summary_scope": "thread_dialogue",
                },
            },
            "context_snapshot": {
                "redaction_policy": {
                    "includes_user_answer": False,
                    "includes_follow_up_answer": False,
                    "includes_repo_evidence_text": False,
                    "includes_hidden_source_content": False,
                }
            },
        },
        "warnings": warnings,
        "errors": [],
        "next_step": summary["next_practice_suggestion"],
    }
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    patch = build_conversation_summary_session_memory_patch(data)
    if patch:
        data["session_memory_patch"] = patch
    return payload


def build_conversation_summary_assistant_response_end(
    payload: Dict[str, Any],
    final_text: str,
    fallback_model: str,
) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else {}
    data = data if isinstance(data, dict) else {}
    llm_metadata = _safe_llm_metadata(data.get("llm_metadata"))
    usage = llm_metadata.get("usage") or {}
    usage_source = llm_metadata.get("usage_source") or "unavailable"
    model = llm_metadata.get("model") or fallback_model
    return {
        "status_type": "assistant_response_end",
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_text,
                },
            }
        ],
        "model": model,
        "usage": usage,
        "usage_source": usage_source,
        "usage_estimated": usage_source != "provider",
        "streaming": False,
    }


def _markdown_list(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    lines = [f"- {str(item).strip()}" for item in items if str(item).strip()]
    return "\n".join(lines) if lines else "- 暂无"


def _markdown_practice_overview(overview: Any) -> str:
    source = overview if isinstance(overview, dict) else {}
    completed_items = _markdown_inline_list(source.get("completed_items"))
    unfinished_items = _markdown_inline_list(source.get("unfinished_items"))
    rows = [
        ("仓库", source.get("repository") or "未在本轮对话中明确"),
        ("角色", source.get("role") or "未在本轮对话中明确"),
        ("难度", source.get("difficulty") or "未在本轮对话中明确"),
        ("完成题目", completed_items or "暂无"),
        ("未答 / 待补", unfinished_items or "暂无"),
    ]
    body = "\n".join(f"| {label} | {str(value).strip()} |" for label, value in rows)
    return f"| 项目 | 内容 |\n| --- | --- |\n{body}"


def _markdown_inline_list(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    values = [str(item).strip() for item in items if str(item).strip()]
    return "；".join(values)


def _markdown_title_detail_list(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    lines = []
    for item in items:
        if not isinstance(item, dict):
            text = str(item).strip()
            if text:
                lines.append(f"- {text}")
            continue
        title = str(item.get("title") or "亮点").strip()
        detail = str(item.get("detail") or "").strip()
        lines.append(f"- **{title}**：{detail}" if detail else f"- **{title}**")
    return "\n".join(lines) if lines else "- 暂无"


def _markdown_improvement_table(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        weakness = str(item.get("weakness") or "待打磨点").strip()
        evidence = str(item.get("evidence") or "未在本轮对话中明确").strip()
        suggestion = str(item.get("suggestion") or "继续补充细节。").strip()
        rows.append(f"| {weakness} | {evidence} | {suggestion} |")
    if not rows:
        return "- 暂无"
    return "| 弱项 | 具体表现 | 改进建议 |\n| --- | --- | --- |\n" + "\n".join(rows)


def _markdown_ability_profile(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension") or "综合能力").strip()
        score = item.get("score")
        score_text = f"{score}%" if isinstance(score, int) else "未量化"
        rationale = str(item.get("rationale") or "").strip()
        lines.append(f"- **{dimension}**：{score_text}" + (f" —— {rationale}" if rationale else ""))
    return "\n".join(lines) if lines else "- 暂无"


def render_conversation_summary_markdown(payload: Dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else {}
    data = data if isinstance(data, dict) else {}
    summary = data.get("conversation_summary")
    summary = summary if isinstance(summary, dict) else {}
    session_summary = data.get("session_summary")
    session_summary = session_summary if isinstance(session_summary, dict) else {}
    raw_report = str(summary.get("raw_report") or "").strip()
    if raw_report:
        return raw_report
    overview = str(summary.get("overview") or "暂无足够可见对话可总结。").strip()
    sections = [
        "## 整轮面试练习总结",
        f"### 一、练习概况\n\n{_markdown_practice_overview(summary.get('practice_overview'))}",
        f"### 二、你的表现亮点\n\n{_markdown_title_detail_list(summary.get('performance_highlights'))}",
        f"### 三、需要持续打磨的方面\n\n{_markdown_improvement_table(summary.get('improvement_areas'))}",
        f"### 四、能力画像（基于本轮可见对话）\n\n{_markdown_ability_profile(summary.get('ability_profile'))}",
        f"### 五、后续练习建议\n\n{_markdown_list(summary.get('next_practice_steps'))}",
        f"### 练习记录\n\n{overview}\n\n{_markdown_list(session_summary.get('practice_notes'))}",
        f"**下一步建议**\n\n{str(session_summary.get('next_practice_suggestion') or payload.get('next_step') or '继续选择下一题练习。').strip()}",
    ]
    return "\n\n".join(sections).strip()


def _llm_response_text(response: Any) -> str:
    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if not choices:
        return ""
    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else getattr(first_choice, "message", None)
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    return content.strip() if isinstance(content, str) else ""


def _extract_json_response(response: Any) -> Dict[str, Any]:
    text = _llm_response_text(response)
    if not text:
        return {}
    parsed = _json_loads_maybe(text)
    if isinstance(parsed, dict):
        return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = _json_loads_maybe(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    return {"raw_report": text}


async def generate_conversation_summary(
    turns: List[Dict[str, str]],
    model_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not turns:
        return None
    messages = [
        {
            "role": "system",
            "content": (
                "你是 GitHub 仓库面试练习的复盘教练。请只基于用户和 agent 的可见对话，"
                "写一份信息量充足、接近“整轮面试练习总结”的中文复盘报告。"
                "可以做表现亮点、待打磨点和能力画像，但要说明这是基于本轮可见对话的练习画像，"
                "不是正式面试评分。不要声称重新读取了 GitHub 仓库；如果仓库、角色、难度或未答题目"
                "没有在对话中明确出现，就写“未在本轮对话中明确”。"
                "优先返回 valid JSON，字段包括："
                "overview, discussed_questions, agent_help, open_items, practice_overview, "
                "performance_highlights, improvement_areas, ability_profile, next_practice_steps, "
                "next_practice_suggestion。"
                "practice_overview 包含 repository, role, difficulty, completed_items, unfinished_items。"
                "performance_highlights 是 {title, detail} 数组；improvement_areas 是 "
                "{weakness, evidence, suggestion} 数组；ability_profile 是 "
                "{dimension, score, rationale} 数组，score 为 0-100。"
                "请自由发挥表达，但保持结论可追溯到对话内容，避免空泛短句。"
                "如果模型或网关不支持严格 JSON，也可以直接输出完整 Markdown 复盘报告。"
            ),
        },
        {"role": "user", "content": json.dumps({"turns": turns}, ensure_ascii=False)},
    ]
    resolved_model_name = model_name or config.MODEL_TO_USE or "deepseek/deepseek-v4-flash"
    try:
        response = await make_llm_api_call(
            messages=messages,
            model_name=resolved_model_name,
            response_format={"type": "json_object"},
            temperature=0.35,
            max_tokens=2200,
            tools=None,
            tool_choice="none",
            stream=False,
        )
    except Exception as exc:
        logger.warning(
            "Conversation summary JSON response_format failed; retrying without JSON mode. "
            f"error_type={type(exc).__name__}"
        )
        response = await make_llm_api_call(
            messages=messages,
            model_name=resolved_model_name,
            response_format=None,
            temperature=0.35,
            max_tokens=2200,
            tools=None,
            tool_choice="none",
            stream=False,
        )
    parsed = _extract_json_response(response)
    if parsed:
        parsed["_llm_metadata"] = _llm_metadata_from_response(
            response=response,
            fallback_model=resolved_model_name,
            prompt_messages=messages,
            response_text=_llm_response_text(response),
        )
    return parsed if parsed else None


async def build_conversation_summary_from_context(
    messages: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    language: str = "zh",
) -> Dict[str, Any]:
    turns = extract_conversation_turns(messages=messages, events=events)
    fallback_reason_code: Optional[str] = None
    try:
        llm_summary = await generate_conversation_summary(turns, model_name=model_name)
        if not isinstance(llm_summary, dict):
            fallback_reason_code = "conversation_summary_llm_unavailable"
    except Exception as exc:
        logger.warning(
            "Conversation summary LLM generation failed; using deterministic fallback. "
            f"error_type={type(exc).__name__}"
        )
        llm_summary = None
        fallback_reason_code = "conversation_summary_llm_error"
    return build_conversation_summary_payload(
        turns=turns,
        llm_summary=llm_summary,
        language=language,
        fallback_reason_code=fallback_reason_code,
    )
