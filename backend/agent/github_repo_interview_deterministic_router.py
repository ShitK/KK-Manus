import json
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional


_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


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


def extract_event_text(content: Any) -> str:
    """Extract user-visible text from ADK event content shapes."""
    content = _json_loads_maybe(content)
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, dict):
        return ""

    direct = content.get("content") or content.get("text")
    if isinstance(direct, str):
        return direct.strip()

    parts = content.get("parts")
    if isinstance(parts, list):
        texts: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text") or part.get("content")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        return "\n".join(texts).strip()

    return ""


def _normalize_question_number(raw_number: str) -> Optional[str]:
    number = raw_number.strip().upper()
    if number.isdigit():
        return f"Q{int(number)}"
    value = _CHINESE_NUMBERS.get(number)
    if value:
        return f"Q{value}"
    return None


def detect_answer_coach_intent(text: str) -> Optional[Dict[str, str]]:
    normalized = str(text or "").strip()
    if not normalized:
        return None

    patterns = [
        r"第\s*([0-9一二三四五六七八九十]+)\s*题[^，。；\n]*(答案|回答|答|这样答|我会这样答|我的答案|我的回答|我准备这样说)",
        r"\bQ\s*([0-9]+)\b[^，。；\n]*(答案|回答|答|这样答|我的回答|我会这样答|我准备这样说)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        question_id = _normalize_question_number(match.group(1))
        if question_id:
            return {"kind": "answer_coach", "question_id": question_id}

    generic_patterns = [
        "点评我的回答",
        "评价一下",
        "我这样答可以吗",
        "这样回答行不行",
        "这样答行不行",
        "回答如下",
        "我的回答是",
        "我会这么回答",
        "我准备这样说",
        "帮我看看这版回答",
        "帮我指出优缺点",
        "根据刚才的问题点评",
        "请按刚才问题点评",
    ]
    if any(pattern in normalized for pattern in generic_patterns):
        return {"kind": "answer_coach"}

    return None


def _extract_follow_up_answer(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    patterns = [
        r"^(?:我\s*)?(?:来\s*)?(?:回答|答)\s*(?:第\s*)?追问\s*[0-9一二三四五六七八九十]*\s*[:：,，。\-—\s]*(.+)$",
        r"^追问\s*[0-9一二三四五六七八九十]+\s*(?:的)?(?:回答|答案)?\s*[:：,，。\-—\s]*(.+)$",
        r"^针对\s*追问\s*[0-9一二三四五六七八九十]+\s*[,，:：\s]*(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _detect_summary_intent(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    has_summary_action = any(keyword in normalized for keyword in ("总结", "复盘", "回顾"))
    has_practice_context = any(
        keyword in normalized
        for keyword in (
            "这一轮",
            "这轮",
            "本轮",
            "整轮",
            "这次",
            "面试练习",
            "GitHub 仓库面试",
            "Github 仓库面试",
            "github 仓库面试",
            "练习总结",
        )
    )
    return has_summary_action and has_practice_context


def _message_tool_name(message: Dict[str, Any], content: Any) -> str:
    metadata = _json_loads_maybe(message.get("metadata") or {})
    if isinstance(metadata, dict):
        tool_name = metadata.get("tool_name") or metadata.get("function_name")
        if isinstance(tool_name, str) and tool_name.strip():
            return tool_name.strip()
    if isinstance(content, dict):
        tool_name = content.get("tool_name") or content.get("name")
        if isinstance(tool_name, str) and tool_name.strip():
            return tool_name.strip()
    return ""


def _message_result_payload(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = _json_loads_maybe(message.get("content"))
    tool_name = _message_tool_name(message, content)
    payload: Any = None

    if isinstance(content, dict) and "result" in content:
        payload = _json_loads_maybe(content.get("result"))
    elif isinstance(content, dict):
        payload = content
    elif isinstance(content, str):
        payload = _json_loads_maybe(content)

    if not isinstance(payload, dict):
        return None

    payload_tool = payload.get("tool") or payload.get("type") or tool_name
    if payload_tool in {"github_repo_interview_prep", "github_repo_interview_workflow"}:
        return payload
    if tool_name in {"github_repo_interview_prep", "github_repo_interview_workflow"}:
        return payload
    return None


def _latest_tool_payload(
    historical_messages: List[Dict[str, Any]],
    tool_name: str,
) -> Optional[Dict[str, Any]]:
    for message in historical_messages:
        if not isinstance(message, dict):
            continue
        payload = _message_result_payload(message)
        if not isinstance(payload, dict):
            continue
        payload_tool = payload.get("tool") or payload.get("type")
        if payload_tool == tool_name:
            return payload
    return None


def _latest_workflow_payload_with_answer_feedback(
    historical_messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for message in historical_messages:
        if not isinstance(message, dict):
            continue
        payload = _message_result_payload(message)
        if not isinstance(payload, dict):
            continue
        payload_tool = payload.get("tool") or payload.get("type")
        if payload_tool == "github_repo_interview_workflow" and _has_answer_feedback(payload):
            return payload
    return None


def _workflow_payloads_with_answer_feedback(
    historical_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    seen_question_ids = set()
    for message in historical_messages:
        if not isinstance(message, dict):
            continue
        payload = _message_result_payload(message)
        if not isinstance(payload, dict):
            continue
        payload_tool = payload.get("tool") or payload.get("type")
        if payload_tool != "github_repo_interview_workflow" or not _has_answer_feedback(payload):
            continue
        question_id = _current_question_id(payload)
        if question_id and question_id in seen_question_ids:
            continue
        if question_id:
            seen_question_ids.add(question_id)
        payloads.append(payload)
    return list(reversed(payloads))


def _compact_workflow_practice_item(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = _data_from_workflow_state(payload)
    selected = data.get("selected_question")
    selected = selected if isinstance(selected, dict) else {}
    question_id = str(selected.get("id") or _current_question_id(payload) or "").strip()
    if not question_id:
        return None
    item: Dict[str, Any] = {"question_id": question_id}
    question = str(selected.get("question") or "").strip()
    if question:
        item["question"] = question
    answer_feedback = data.get("answer_feedback")
    if isinstance(answer_feedback, dict):
        item["answer_feedback"] = {
            key: deepcopy(value)
            for key, value in answer_feedback.items()
            if key in {"summary", "strengths", "gaps", "evidence_missed", "suggested_answer_outline", "follow_up_questions"}
        }
    follow_up = data.get("follow_up")
    if isinstance(follow_up, dict):
        item["follow_up"] = {
            key: deepcopy(value)
            for key, value in follow_up.items()
            if key in {"mode", "questions", "feedback", "grounding_notes"}
        }
    return item


def _attach_practice_history(
    previous_workflow_state: Dict[str, Any],
    workflow_payloads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result = deepcopy(previous_workflow_state)
    data = result.get("data")
    if not isinstance(data, dict):
        data = result
    workflow = data.get("workflow")
    if not isinstance(workflow, dict):
        workflow = {}
        data["workflow"] = workflow
    history = [
        item
        for item in (_compact_workflow_practice_item(payload) for payload in workflow_payloads)
        if isinstance(item, dict)
    ]
    if history:
        workflow["practice_history"] = history
        workflow["answered_question_ids"] = [item["question_id"] for item in history]
    return result


def _current_question_id(previous_workflow_state: Optional[Dict[str, Any]]) -> str:
    if not isinstance(previous_workflow_state, dict):
        return ""
    input_data = previous_workflow_state.get("input")
    if isinstance(input_data, dict):
        question_id = input_data.get("question_id")
        if isinstance(question_id, str) and question_id.strip():
            return question_id.strip()
    data = previous_workflow_state.get("data")
    if not isinstance(data, dict):
        data = previous_workflow_state
    selected = data.get("selected_question")
    if isinstance(selected, dict):
        question_id = selected.get("id")
        if isinstance(question_id, str):
            return question_id.strip()
    return ""


def _data_from_workflow_state(previous_workflow_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(previous_workflow_state, dict):
        return {}
    data = previous_workflow_state.get("data")
    return data if isinstance(data, dict) else previous_workflow_state


def _has_answer_feedback(previous_workflow_state: Optional[Dict[str, Any]]) -> bool:
    data = _data_from_workflow_state(previous_workflow_state)
    answer_feedback = data.get("answer_feedback")
    if not isinstance(answer_feedback, dict):
        return False
    if str(answer_feedback.get("summary") or "").strip():
        return True
    for key in ("strengths", "gaps", "evidence_missed", "suggested_answer_outline", "follow_up_questions"):
        value = answer_feedback.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
    return False


def build_deterministic_answer_route(
    latest_user_text: str,
    historical_messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    prep_payload = _latest_tool_payload(historical_messages, "github_repo_interview_prep")
    if _detect_summary_intent(latest_user_text):
        return {
            "kind": "conversation_summary",
            "tool_name": "github_repo_interview_conversation_summary",
            "summary_scope": "thread_dialogue",
            "language": "zh",
        }

    follow_up_answer = _extract_follow_up_answer(latest_user_text)
    intent = detect_answer_coach_intent(latest_user_text)
    if not intent and not follow_up_answer:
        return None

    if not prep_payload:
        return None

    if follow_up_answer:
        previous_workflow_state = _latest_workflow_payload_with_answer_feedback(historical_messages)
        question_id = _current_question_id(previous_workflow_state)
        if previous_workflow_state and question_id:
            return {
                "stage": "coach_follow_up",
                "prep_questions_pack": prep_payload,
                "question_id": question_id,
                "follow_up_answer": follow_up_answer,
                "previous_workflow_state": previous_workflow_state,
                "language": "zh",
                "coach_style": "balanced",
            }

    previous_workflow_state = _latest_tool_payload(
        historical_messages,
        "github_repo_interview_workflow",
    )
    if not intent.get("question_id"):
        previous_workflow_state = (
            _latest_workflow_payload_with_answer_feedback(historical_messages)
            or previous_workflow_state
        )
    question_id = intent.get("question_id") or _current_question_id(previous_workflow_state)
    if not question_id:
        return None

    if previous_workflow_state and not intent.get("question_id") and _has_answer_feedback(previous_workflow_state):
        return {
            "stage": "coach_follow_up",
            "prep_questions_pack": prep_payload,
            "question_id": question_id,
            "follow_up_answer": str(latest_user_text or "").strip(),
            "previous_workflow_state": previous_workflow_state,
            "language": "zh",
            "coach_style": "balanced",
        }

    return {
        "stage": "coach_answer",
        "prep_questions_pack": prep_payload,
        "question_id": question_id,
        "user_answer": str(latest_user_text or "").strip(),
        "previous_workflow_state": previous_workflow_state,
        "language": "zh",
        "coach_style": "balanced",
    }


def _markdown_list(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    lines = [f"- {str(item).strip()}" for item in items if str(item).strip()]
    return "\n".join(lines) if lines else "- 暂无"


MARKDOWN_CATEGORY_LABELS = {
    "architecture": "架构设计",
    "implementation detail": "实现细节",
    "dependency and packaging": "依赖与工程化",
    "testing and automation": "测试与自动化",
}

MARKDOWN_DIFFICULTY_LABELS = {
    "junior": "初级",
    "mid": "中级",
    "medium": "中级",
    "senior": "高级",
}


def _localized_markdown_term(value: Any, labels: Dict[str, str]) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    return labels.get(normalized) or str(value or "").strip()


def _markdown_other_questions(items: Any) -> str:
    if not isinstance(items, list):
        return "- 暂无"
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("id") or "").strip()
        question = str(item.get("question") or "").strip()
        category = _localized_markdown_term(item.get("category"), MARKDOWN_CATEGORY_LABELS)
        difficulty = _localized_markdown_term(item.get("difficulty"), MARKDOWN_DIFFICULTY_LABELS)
        if not question_id or not question:
            continue
        suffix_parts = [part for part in (category, difficulty) if part]
        suffix = f"（{', '.join(suffix_parts)}）" if suffix_parts else ""
        lines.append(f"- **{question_id}**{suffix}: {question}")
    return "\n".join(lines) if lines else "- 暂无"


def _summary_title_question_ids(completion: Dict[str, Any], fallback_question_id: str) -> str:
    raw_ids = completion.get("answered_question_ids")
    ids = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            question_id = str(item or "").strip()
            if question_id and question_id not in ids:
                ids.append(question_id)
    if len(ids) > 1:
        return " + ".join(ids)
    return ids[0] if ids else fallback_question_id


def _practice_history_markdown(data: Dict[str, Any]) -> str:
    workflow = data.get("workflow")
    workflow = workflow if isinstance(workflow, dict) else {}
    history = workflow.get("practice_history")
    if not isinstance(history, list):
        return ""
    lines = []
    for item in history:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or item.get("id") or "").strip()
        if not question_id:
            continue
        question = str(item.get("question") or "").strip()
        feedback = item.get("answer_feedback")
        feedback = feedback if isinstance(feedback, dict) else {}
        summary = str(feedback.get("summary") or "").strip()
        details = "；".join(part for part in (question, summary) if part)
        lines.append(f"- **{question_id}**：{details}" if details else f"- **{question_id}**")
    return "\n".join(lines)


def render_workflow_feedback_markdown(payload: Dict[str, Any]) -> str:
    input_data = payload.get("input") if isinstance(payload, dict) else {}
    input_data = input_data if isinstance(input_data, dict) else {}
    data = payload.get("data") if isinstance(payload, dict) else {}
    data = data if isinstance(data, dict) else {}
    selected_question = data.get("selected_question")
    selected_question = selected_question if isinstance(selected_question, dict) else {}
    stage = str(input_data.get("stage") or "").strip()
    if stage == "summarize":
        summary = data.get("session_summary")
        summary = summary if isinstance(summary, dict) else {}
        completion = summary.get("workflow_completion")
        completion = completion if isinstance(completion, dict) else {}
        question_id = str(selected_question.get("id") or "").strip() or "当前题目"
        title_question_ids = _summary_title_question_ids(completion, question_id)
        question = str(selected_question.get("question") or "").strip()
        status_parts = []
        if completion.get("answer_coached") is True:
            status_parts.append("回答点评已完成")
        elif completion:
            status_parts.append("回答点评未完成")
        if completion.get("follow_up_completed") is True:
            status_parts.append("追问已完成")
        elif completion:
            status_parts.append("追问未完成")
        title = "整轮练习总结" if " + " in title_question_ids else "练习总结"
        sections = [f"## {title}：{title_question_ids}"]
        if question:
            sections.append(f"> {question}")
        if status_parts:
            sections.append(f"**完成状态**\n\n- {'；'.join(status_parts)}")
        practice_history_markdown = _practice_history_markdown(data)
        if practice_history_markdown:
            sections.append(f"**已练习题目**\n\n{practice_history_markdown}")
        sections.extend(
            [
                f"**已覆盖证据**\n\n{_markdown_list(summary.get('covered_evidence'))}",
                f"**还可补充证据**\n\n{_markdown_list(summary.get('missed_evidence'))}",
                f"**练习记录**\n\n{_markdown_list(summary.get('practice_notes'))}",
                f"**下一步建议**\n\n{str(summary.get('next_practice_suggestion') or '继续选择下一题练习。').strip()}",
            ]
        )
        return "\n\n".join(sections).strip()

    if stage == "coach_follow_up":
        follow_up = data.get("follow_up")
        follow_up = follow_up if isinstance(follow_up, dict) else {}
        question_id = str(selected_question.get("id") or "").strip() or "当前题目"
        question = str(selected_question.get("question") or "").strip()
        sections = [f"## 追问点评：{question_id}"]
        if question:
            sections.append(f"> {question}")
        sections.extend(
            [
                f"**追问反馈**\n\n{_markdown_list(follow_up.get('feedback'))}",
                f"**继续追问**\n\n{_markdown_list(follow_up.get('questions'))}",
                f"**回答其他问题**\n\n{_markdown_other_questions(data.get('other_questions'))}",
            ]
        )
        return "\n\n".join(sections).strip()

    feedback = data.get("answer_feedback")
    feedback = feedback if isinstance(feedback, dict) else {}

    question_id = str(selected_question.get("id") or "").strip() or "当前题目"
    question = str(selected_question.get("question") or "").strip()
    summary = str(feedback.get("summary") or "").strip() or "已完成本题回答点评。"

    sections = [
        f"## 点评：{question_id}",
    ]
    if question:
        sections.append(f"> {question}")
    sections.extend(
        [
            f"**反馈摘要**\n\n{summary}",
            f"**优点**\n\n{_markdown_list(feedback.get('strengths'))}",
            f"**需要补充**\n\n{_markdown_list(feedback.get('gaps'))}",
            f"**建议答题方向**\n\n{_markdown_list(feedback.get('suggested_answer_outline'))}",
            f"**追问练习**\n\n{_markdown_list(feedback.get('follow_up_questions'))}",
        ]
    )
    return "\n\n".join(sections).strip()
