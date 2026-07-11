import json
import re
from copy import deepcopy
from typing import Any, Awaitable, Callable, Dict, List, Optional

from agent.tools.github_repo_answer_coach import (
    ALLOWED_COACH_STYLES,
    ALLOWED_LANGUAGES,
    DISALLOWED_JUDGMENT_PATTERN,
    MAX_USER_ANSWER_CHARS,
    AnswerCoachEngine,
    LLMAnswerCoachEngine,
    _extract_json_response,
    _error,
    _normalize_max_follow_ups,
    _sanitize_feedback,
    _valid_evidence_ids,
    _warning,
    build_coach_request,
)
from agent.tools.github_repo_answer_quality_signals import build_answer_quality_signals
from agent.tools.github_repo_interview_intent import (
    normalize_coach_style,
    normalize_language,
    normalize_question_category,
)
from agent.tools.github_repo_interview_workflow_context import attach_context_policy
from agent.tools.github_repo_interview_memory import select_workflow_memory_context
from agent.tools.github_repo_interview_multi_agent_trace import build_multi_agent_trace
from agent.tools.github_repo_interview_session_memory import (
    build_session_memory_patch,
    sanitize_session_memory_state,
)
from agent.tools.github_repo_interview_vector_memory import (
    sanitize_vector_memory_context,
    sanitize_vector_memory_retrieval,
)
from agent.tools.github_repo_interview_workflow import build_workflow_state
from agent.tools.github_repo_interview_workflow_roles import EvidenceGatekeeper, role_contract
from agent.tools.github_repo_interview_workflow_snapshot import attach_context_snapshot
from agentpress.tool import Tool, ToolResult, usage_example
from services.llm import make_llm_api_call
from utils.config import config


WORKFLOW_EXTRA_JUDGMENT_PATTERN = re.compile(r"(排名|名次|等级|评级)")
MemoryContextLoader = Callable[..., Awaitable[Dict[str, Any]]]


class WorkflowStageEngine:
    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class LLMWorkflowStageEngine(WorkflowStageEngine):
    def __init__(self, stage_name: str, model_name: Optional[str] = None):
        self.stage_name = stage_name
        self.model_name = model_name or config.MODEL_TO_USE or "deepseek/deepseek-v4-flash"

    async def generate_feedback(self, request: Dict[str, Any]) -> Dict[str, Any]:
        response = await make_llm_api_call(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a bounded GitHub interview workflow coach. "
                        "Use only the provided selected question, allowed evidence, and prior feedback. "
                        "Do not use outside knowledge about the repository or the user's prior answers. "
                        "Do not add repository facts, URLs, scores, rankings, or pass/fail judgments. "
                        "If you mention file paths, use only the provided allowed source paths. "
                        "Return only valid JSON for the requested workflow stage."
                    ),
                },
                {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
            ],
            model_name=self.model_name,
            temperature=0,
            max_tokens=900,
            tools=None,
            tool_choice="none",
            stream=False,
        )
        try:
            return _extract_json_response(response)
        except Exception:
            if self.stage_name == "summary":
                raw_text = _llm_response_text(response)
                if raw_text:
                    return {"demo_summary_text": raw_text}
            raise


def _llm_response_text(response: Any) -> str:
    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if not choices:
        return ""
    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else getattr(first_choice, "message", None)
    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    return content.strip() if isinstance(content, str) else ""


def _contains_disallowed_judgment(value: Any) -> bool:
    if isinstance(value, str):
        return bool(DISALLOWED_JUDGMENT_PATTERN.search(value) or WORKFLOW_EXTRA_JUDGMENT_PATTERN.search(value))
    if isinstance(value, list):
        return any(_contains_disallowed_judgment(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_disallowed_judgment(item) for item in value.values())
    return False


def _previous_follow_up_count(previous_workflow_state: Optional[Dict[str, Any]]) -> int:
    if not isinstance(previous_workflow_state, dict):
        return 0
    workflow = previous_workflow_state.get("workflow")
    if not isinstance(workflow, dict):
        return 0
    try:
        return max(0, int(workflow.get("follow_up_count") or 0))
    except (TypeError, ValueError):
        return 0


def _previous_answered_question_ids(previous_workflow_state: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(previous_workflow_state, dict):
        return []
    workflow = previous_workflow_state.get("workflow")
    if not isinstance(workflow, dict):
        return []
    answered = workflow.get("answered_question_ids")
    if not isinstance(answered, list):
        return []
    seen = set()
    result = []
    for item in answered:
        question_id = str(item or "").strip()
        if question_id and question_id not in seen:
            seen.add(question_id)
            result.append(question_id)
    return result


def _practice_history_from_previous_state(previous_workflow_state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(previous_workflow_state, dict):
        return []
    workflow = previous_workflow_state.get("workflow")
    if not isinstance(workflow, dict):
        return []
    raw_history = workflow.get("practice_history")
    if not isinstance(raw_history, list):
        return []
    history: List[Dict[str, Any]] = []
    seen = set()
    for raw_item in raw_history:
        if not isinstance(raw_item, dict):
            continue
        question_id = str(raw_item.get("question_id") or raw_item.get("id") or "").strip()
        if not question_id or question_id in seen:
            continue
        seen.add(question_id)
        item: Dict[str, Any] = {"question_id": question_id}
        question = str(raw_item.get("question") or "").strip()
        if question:
            item["question"] = question
        answer_feedback = raw_item.get("answer_feedback")
        if isinstance(answer_feedback, dict):
            item["answer_feedback"] = {
                key: deepcopy(value)
                for key, value in answer_feedback.items()
                if key in {"summary", "strengths", "gaps", "evidence_missed", "suggested_answer_outline", "follow_up_questions"}
            }
        follow_up = raw_item.get("follow_up")
        if isinstance(follow_up, dict):
            item["follow_up"] = {
                key: deepcopy(value)
                for key, value in follow_up.items()
                if key in {"mode", "questions", "feedback", "grounding_notes"}
            }
        history.append(item)
    return history


def _unwrap_previous_workflow_state(previous_workflow_state: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(previous_workflow_state, dict):
        return None
    data = previous_workflow_state.get("data")
    if not isinstance(data, dict):
        return previous_workflow_state
    payload_type = str(previous_workflow_state.get("tool") or previous_workflow_state.get("type") or "").strip()
    if payload_type == "github_repo_interview_workflow":
        return data
    if any(key in data for key in ("selected_question", "workflow", "answer_feedback", "follow_up", "session_summary")):
        return data
    return previous_workflow_state


def _mark_question_answered(data: Dict[str, Any], previous_workflow_state: Optional[Dict[str, Any]]) -> None:
    selected = data.get("selected_question") if isinstance(data.get("selected_question"), dict) else {}
    question_id = str(selected.get("id") or "").strip()
    answered = _previous_answered_question_ids(previous_workflow_state)
    if question_id and question_id not in answered:
        answered.append(question_id)
    data.setdefault("workflow", {})["answered_question_ids"] = answered


def _questions_from_pack(prep_questions_pack: Any) -> List[Dict[str, Any]]:
    source = prep_questions_pack.get("data") if isinstance(prep_questions_pack, dict) else {}
    if not isinstance(source, dict):
        source = prep_questions_pack if isinstance(prep_questions_pack, dict) else {}
    questions = source.get("interview_questions")
    return questions if isinstance(questions, list) else []


def _first_unanswered_question_id(prep_questions_pack: Any, session_memory_context: Dict[str, Any]) -> str:
    answered = {
        str(question_id or "").strip().upper()
        for question_id in session_memory_context.get("answered_question_ids", [])
        if str(question_id or "").strip()
    }
    first_question_id = ""
    for question in _questions_from_pack(prep_questions_pack):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        if not first_question_id:
            first_question_id = question_id
        if question_id.upper() not in answered:
            return question_id
    return first_question_id


def _other_questions_from_pack(
    prep_questions_pack: Any,
    current_question_id: str,
    previous_workflow_state: Optional[Dict[str, Any]],
    limit: int = 3,
) -> List[Dict[str, str]]:
    answered = set(_previous_answered_question_ids(previous_workflow_state))
    current = str(current_question_id or "").strip()
    if current:
        answered.add(current)
    other_questions: List[Dict[str, str]] = []
    for question in _questions_from_pack(prep_questions_pack):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        question_text = str(question.get("question") or "").strip()
        if not question_id or not question_text or question_id in answered:
            continue
        item = {"id": question_id, "question": question_text}
        for key in ("category", "difficulty"):
            value = str(question.get(key) or "").strip()
            if value:
                item[key] = value
        other_questions.append(item)
        if len(other_questions) >= limit:
            break
    return other_questions


def _first_evidence_source_path(state: Dict[str, Any]) -> str:
    for detail in state.get("evidence_details") or []:
        if isinstance(detail, dict):
            source_path = str(detail.get("source_path") or "").strip()
            if source_path:
                return source_path
    return "the selected evidence"


def _fallback_follow_up_question(state: Dict[str, Any], language: str) -> str:
    source_path = _first_evidence_source_path(state)
    if language == "en":
        return (
            f"Based only on {source_path}, how would you strengthen your answer "
            "with one concrete design tradeoff and one validation step?"
        )
    return f"只基于 {source_path} 这条 evidence，你会如何补充一个具体设计取舍和一个验证步骤？"


def _follow_up_prompt_from_prior_feedback(
    state: Dict[str, Any],
    answer_feedback: Dict[str, Any],
    language: str,
    max_follow_ups: int,
) -> Dict[str, Any]:
    questions = [
        str(question).strip()
        for question in answer_feedback.get("follow_up_questions") or []
        if isinstance(question, str) and question.strip()
    ][:max_follow_ups]
    fallback_used = False
    if not questions:
        questions = [_fallback_follow_up_question(state, language)]
        fallback_used = True
    return {
        "mode": "question_prompt",
        "questions": questions,
        "feedback": [],
        "grounding_notes": [
            "Follow-up questions are derived only from filtered answer_feedback and selected_question.evidence_details."
        ],
        "fallback_used": fallback_used,
    }


def _follow_up_answer_hints(follow_up_answer: str, language: str) -> List[str]:
    text = str(follow_up_answer or "")
    lowered = text.lower()
    hints: List[str] = []
    if any(token in text for token in ("CLI", "命令", "参数", "入口")) or any(
        token in lowered for token in ("createprogram", "parse", "entrypoint")
    ):
        hints.append("you grounded the answer in CLI entry behavior" if language == "en" else "已经把回答落到 CLI 入口行为")
    if any(token in text for token in ("集成测试", "测试", "验证")) or "integration test" in lowered:
        hints.append("you added a validation/testing path" if language == "en" else "补充了集成测试或验证路径")
    if any(token in lowered for token in ("mock", "stub", "fake")) or "模拟" in text:
        hints.append("you separated dependencies with a mock boundary" if language == "en" else "说明了用 mock 隔离依赖")
    if "application" in lowered or "应用层" in text:
        hints.append("you distinguished the application layer from the entry layer" if language == "en" else "区分了入口层和 application 层")
    return hints[:3]


def _follow_up_output_contract(language: str) -> Dict[str, Any]:
    if language == "en":
        example = {
            "questions": ["What validation would prove the claim using the allowed evidence?"],
            "feedback": ["Your follow-up answer added a validation path grounded in the selected evidence."],
            "grounding_notes": ["Only use allowed evidence ids and selected source paths."],
        }
    else:
        example = {
            "questions": ["你会如何用 allowed evidence 证明这个判断？"],
            "feedback": ["你的追问回答补充了验证路径，并且仍然锚定当前题目的证据。"],
            "grounding_notes": ["只使用 allowed evidence ids 和当前题目的 source paths。"],
        }
    return {
        "format": "json_object",
        "required_keys": ["questions", "feedback", "grounding_notes"],
        "schema": {
            "questions": "array of strings; each item must be a follow-up question",
            "feedback": "array of strings; concise feedback on the follow_up_answer",
            "grounding_notes": "array of strings; optional evidence-bound notes",
        },
        "rules": [
            "allowed_evidence_only",
            "no_new_repository_access",
            "no_scores_or_pass_fail",
            "no_candidate_judgment",
            "do_not_echo_raw_user_answer",
        ],
        "example": example,
    }


def _fallback_follow_up_next_question(follow_up_answer: str, source_path: str, language: str) -> str:
    text = str(follow_up_answer or "")
    lowered = text.lower()
    mentions_cli = any(token in text for token in ("CLI", "命令", "参数", "入口")) or any(
        token in lowered for token in ("createprogram", "parse", "entrypoint")
    )
    mentions_test = any(token in text for token in ("集成测试", "测试", "验证")) or "integration test" in lowered
    mentions_mock = any(token in lowered for token in ("mock", "stub", "fake")) or "模拟" in text
    mentions_application = "application" in lowered or "应用层" in text

    if language == "en":
        if mentions_cli and mentions_test and (mentions_mock or mentions_application):
            return (
                "If that entry-layer test fails, how would you distinguish a CLI parsing issue, "
                "an application-layer contract issue, and a mock-boundary issue?"
            )
        if mentions_test:
            return f"What assertion or failure case would make your validation of {source_path} convincing?"
        return f"What concrete validation would prove the claim supported by {source_path}?"

    if mentions_cli and mentions_test and (mentions_mock or mentions_application):
        return "如果这个入口层测试失败，你会如何区分是 CLI 参数解析、application 调用契约，还是 mock 边界问题？"
    if mentions_test:
        return f"你会补哪一条断言或失败用例，让 {source_path} 这条验证更有说服力？"
    return f"围绕 {source_path}，你会用什么具体验证来证明这个判断？"


def _fallback_follow_up_feedback(
    state: Dict[str, Any],
    language: str,
    follow_up_answer: str = "",
) -> Dict[str, Any]:
    source_path = _first_evidence_source_path(state)
    hints = _follow_up_answer_hints(follow_up_answer, language)
    if language == "en":
        if hints:
            feedback = (
                "Your follow-up answer was received: "
                + "; ".join(hints)
                + f". Next, tie that reasoning back to {source_path} with one observable assertion or failure path."
            )
        else:
            feedback = (
                f"Your follow-up answer was received. Keep the next revision grounded in {source_path}, "
                "and make the design tradeoff and validation step explicit."
            )
        question = _fallback_follow_up_next_question(follow_up_answer, source_path, language)
    else:
        if hints:
            feedback = (
                "已收到你的追问回答："
                + "，".join(hints)
                + f"。下一步请回扣 {source_path}，补一条可观察断言或失败定位路径。"
            )
        else:
            feedback = f"已收到你的追问回答。下一版请继续锚定 {source_path}，并明确说出设计取舍和验证步骤。"
        question = _fallback_follow_up_next_question(follow_up_answer, source_path, language)
    return {
        "mode": "answer_feedback_fallback",
        "questions": [question],
        "feedback": [feedback],
        "grounding_notes": [
            "Fallback feedback is deterministic and uses only selected_question.evidence_details."
        ],
    }


def _fallback_answer_feedback(
    state: Dict[str, Any],
    language: str,
    max_follow_ups: int,
) -> Dict[str, Any]:
    source_path = _first_evidence_source_path(state)
    evidence_details = [detail for detail in state.get("evidence_details") or [] if isinstance(detail, dict)]
    first_detail = evidence_details[0] if evidence_details else {}
    evidence_id = str(first_detail.get("evidence_id") or "").strip()
    evidence_type = str(first_detail.get("evidence_type") or "").strip()
    question_id = str(state.get("selected_question", {}).get("id") or "").strip() or "current question"

    if language == "en":
        return {
            "summary": (
                "Your answer was received. The live coach output was unavailable or rejected, "
                "so this bounded fallback only checks the answer against the selected evidence."
            ),
            "strengths": [
                "You attempted to answer the selected interview question directly.",
                f"You can anchor the next revision in {source_path}.",
            ],
            "gaps": [
                f"Make the link to {source_path} explicit: name what the file proves and what it does not prove.",
                "Add one concrete tradeoff and one validation step instead of only describing the module split.",
            ],
            "evidence_missed": [
                {
                    "evidence_id": evidence_id,
                    "source_path": source_path,
                    "reason": f"Use this {evidence_type or 'evidence'} item to ground the architecture claim.",
                }
            ]
            if evidence_id
            else [],
            "suggested_answer_outline": [
                f"Start with the role of {source_path}.",
                "Explain the boundary it shows, then name the tradeoff.",
                "Close with how you would validate the design in code or tests.",
            ],
            "follow_up_questions": [
                f"For {question_id}, what exact behavior or test would prove your architecture explanation?"
            ][:max_follow_ups],
            "grounding_notes": [
                "Deterministic fallback feedback; no repository reread, no raw answer persistence, allowed evidence only."
            ],
        }

    return {
        "summary": "已收到你的回答。实时点评输出不可用或被边界校验拒绝，所以这里用受控兜底点评，只基于当前题目的允许证据。",
        "strengths": [
            "你已经直接回答了当前面试题。",
            f"下一版可以继续锚定 {source_path} 来证明你的架构判断。",
        ],
        "gaps": [
            f"需要更明确说明 {source_path} 这条证据证明了什么、不能证明什么。",
            "建议补一个具体设计取舍和一个验证步骤，不只停留在模块分层描述。",
        ],
        "evidence_missed": [
            {
                "evidence_id": evidence_id,
                "source_path": source_path,
                "reason": f"这条{evidence_type or '证据'}可以用来支撑架构边界说明。",
            }
        ]
        if evidence_id
        else [],
        "suggested_answer_outline": [
            f"先说明 {source_path} 在项目里的职责。",
            "再解释它体现的边界，以及为什么这样拆分。",
            "最后补充如何用代码路径或测试验证这个设计判断。",
        ],
        "follow_up_questions": [f"针对 {question_id}，你会用哪一个具体验证来证明你的架构解释？"][:max_follow_ups],
        "grounding_notes": ["确定性兜底点评；不重新读取仓库，不保存用户回答原文，只使用允许证据。"],
    }


def _summary_needs_fallback(summary: Dict[str, Any]) -> bool:
    return not any(
        isinstance(summary.get(key), list) and len(summary.get(key) or []) > 0
        for key in ("covered_evidence", "missed_evidence", "practice_notes")
    )


def _raw_summary_notes(response: Any) -> List[str]:
    if isinstance(response, str):
        text = response.strip()
        return [text] if text else []
    if not isinstance(response, dict):
        return []
    notes: List[str] = []
    for key in ("demo_summary_text", "summary", "overall_summary"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            notes.append(value.strip())
    raw_practice_notes = response.get("practice_notes")
    if isinstance(raw_practice_notes, list):
        notes.extend(str(item).strip() for item in raw_practice_notes if str(item).strip())
    elif isinstance(raw_practice_notes, str) and raw_practice_notes.strip():
        notes.append(raw_practice_notes.strip())
    return notes[:5]


def _demo_relaxed_session_summary(response: Any, language: str) -> Dict[str, Any]:
    notes = _raw_summary_notes(response)
    if not notes:
        return {}
    next_suggestion = ""
    if isinstance(response, dict):
        next_suggestion = str(response.get("next_practice_suggestion") or "").strip()
    if not next_suggestion:
        next_suggestion = "Pick another question or revise the same answer with stronger evidence." if language == "en" else "继续选择下一题练习。"
    return {
        "covered_evidence": [],
        "missed_evidence": [],
        "practice_notes": notes,
        "next_practice_suggestion": next_suggestion,
        "demo_relaxed_validation": True,
    }


def _fallback_session_summary(
    state: Dict[str, Any],
    answer_feedback: Dict[str, Any],
    filtered_follow_up: Dict[str, Any],
    language: str,
) -> Dict[str, Any]:
    allowed_ids = [
        str(evidence_id).strip()
        for evidence_id in state.get("evidence_policy", {}).get("allowed_evidence_ids") or []
        if str(evidence_id).strip()
    ]
    missed_ids = [
        str(item.get("evidence_id") or "").strip()
        for item in answer_feedback.get("evidence_missed") or []
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip() in allowed_ids
    ]
    covered_ids = [evidence_id for evidence_id in allowed_ids if evidence_id not in set(missed_ids)]
    if not covered_ids and not missed_ids:
        covered_ids = allowed_ids[:1]

    notes: List[str] = []
    summary = str(answer_feedback.get("summary") or "").strip()
    if summary:
        notes.append(summary)
    gaps = [str(item).strip() for item in answer_feedback.get("gaps") or [] if str(item).strip()]
    if gaps:
        notes.append(gaps[0])
    follow_up_feedback = [
        str(item).strip()
        for item in filtered_follow_up.get("feedback") or []
        if str(item).strip()
    ]
    if follow_up_feedback:
        notes.append(follow_up_feedback[0])
    if not notes:
        notes.append(
            "Summary fallback used existing answer feedback and selected evidence only."
            if language == "en"
            else "本轮总结使用已有回答点评和当前题目的允许证据生成。"
        )

    source_path = _first_evidence_source_path(state)
    suggestion = (
        f"Continue by turning the evidence in {source_path} into one tradeoff and one validation step."
        if language == "en"
        else f"继续练习如何把 {source_path} 的证据讲成具体取舍和验证步骤。"
    )
    return {
        "covered_evidence": covered_ids,
        "missed_evidence": missed_ids,
        "practice_notes": notes[:3],
        "next_practice_suggestion": suggestion,
    }


def _follow_up_completed(filtered_follow_up: Dict[str, Any]) -> bool:
    feedback = filtered_follow_up.get("feedback")
    return isinstance(feedback, list) and any(str(item).strip() for item in feedback)


def _answer_coached(filtered_feedback: Dict[str, Any]) -> bool:
    if not isinstance(filtered_feedback, dict):
        return False
    if str(filtered_feedback.get("summary") or "").strip():
        return True
    for key in ("strengths", "gaps", "evidence_missed", "suggested_answer_outline", "follow_up_questions"):
        value = filtered_feedback.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    return False


def _workflow_completion(
    answer_coached: bool,
    follow_up_completed: bool,
    answered_question_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    completion = {
        "answer_coached": answer_coached,
        "follow_up_completed": follow_up_completed,
        "summary_scope": "answer_and_follow_up" if follow_up_completed else "answer_feedback_only",
    }
    answered = [
        str(question_id).strip()
        for question_id in answered_question_ids or []
        if str(question_id).strip()
    ]
    if answered:
        completion["answered_question_ids"] = answered
        if len(answered) > 1:
            completion["summary_scope"] = "practice_session"
    return completion


def _normalized_intent(
    raw_language: str,
    language: str,
    language_changed: bool,
    raw_coach_style: str,
    coach_style: str,
    coach_style_changed: bool,
    raw_category: str,
    category: str,
    category_changed: bool,
) -> Dict[str, Any]:
    intent: Dict[str, Any] = {}
    if language_changed:
        intent["language"] = {"raw": raw_language, "normalized": language}
    if coach_style_changed:
        intent["coach_style"] = {"raw": raw_coach_style, "normalized": coach_style}
    if category_changed:
        intent["preferred_question_category"] = {"raw": raw_category, "normalized": category}
    return intent


class GitHubRepoInterviewWorkflowTool(Tool):
    """Coordinate a bounded GitHub Repo Interview workflow from existing evidence."""

    def __init__(
        self,
        answer_coach_engine: Optional[AnswerCoachEngine] = None,
        follow_up_engine: Optional[WorkflowStageEngine] = None,
        summary_engine: Optional[WorkflowStageEngine] = None,
        memory_context_loader: Optional[MemoryContextLoader] = None,
    ):
        super().__init__()
        self.answer_coach_engine = answer_coach_engine or LLMAnswerCoachEngine()
        self.follow_up_engine = follow_up_engine or LLMWorkflowStageEngine("follow_up")
        self.summary_engine = summary_engine or LLMWorkflowStageEngine("summary")
        # ToolRegistry exposes public bound callables as model tools. Keep this
        # server-owned loader private so only the workflow method is callable.
        self._memory_context_loader = memory_context_loader

    async def _load_missing_memory_context(
        self,
        *,
        prep_questions_pack: Dict[str, Any],
        question_id: str,
        user_answer: str,
        follow_up_answer: str,
        preferred_question_category: str,
        saved_memory_context: Optional[List[Dict[str, Any]]],
        session_memory_context: Optional[Dict[str, Any]],
        vector_memory_context: Optional[List[Dict[str, Any]]],
        vector_memory_retrieval: Optional[Dict[str, Any]],
    ) -> tuple[
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, Any]],
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, Any]],
    ]:
        if self._memory_context_loader is None:
            return (
                saved_memory_context,
                session_memory_context,
                vector_memory_context,
                vector_memory_retrieval,
            )

        selected_question = next(
            (
                question
                for question in _questions_from_pack(prep_questions_pack)
                if isinstance(question, dict)
                and str(question.get("id") or "").strip() == str(question_id or "").strip()
            ),
            {},
        )
        existing_session = session_memory_context if isinstance(session_memory_context, dict) else {}
        category = str(
            preferred_question_category
            or existing_session.get("current_practice_category")
            or selected_question.get("category")
            or ""
        ).strip()
        query_text = str(
            follow_up_answer
            or user_answer
            or selected_question.get("question")
            or f"GitHub 仓库面试练习 {question_id} {category}"
        ).strip()
        try:
            loaded = await self._memory_context_loader(
                query_text=query_text,
                target_role=str(existing_session.get("target_role") or "").strip() or None,
                category=category or None,
            )
        except Exception:
            loaded = {
                "session_memory_context": {},
                "saved_memory_context": [],
                "vector_memory_context": [],
                "vector_memory_retrieval": {
                    "status": "retrieval_error",
                    "diagnostics": {"fallback_used": True},
                },
            }
        loaded = loaded if isinstance(loaded, dict) else {}
        loaded_saved = loaded.get("saved_memory_context")
        saved_memory_context = loaded_saved if isinstance(loaded_saved, list) else []
        loaded_session = loaded.get("session_memory_context")
        session_memory_context = loaded_session if isinstance(loaded_session, dict) else {}
        loaded_vector = loaded.get("vector_memory_context")
        vector_memory_context = loaded_vector if isinstance(loaded_vector, list) else []
        loaded_retrieval = loaded.get("vector_memory_retrieval")
        vector_memory_retrieval = loaded_retrieval if isinstance(loaded_retrieval, dict) else {
            "status": "retrieval_error",
            "diagnostics": {"fallback_used": True},
        }
        return (
            saved_memory_context,
            session_memory_context,
            vector_memory_context,
            vector_memory_retrieval,
        )

    def _json_result(self, payload: Dict[str, Any], success: bool = True) -> ToolResult:
        return ToolResult(success=success, output=json.dumps(payload, ensure_ascii=False, indent=2))

    def _payload(
        self,
        status: str,
        input_data: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[list[Dict[str, Any]]] = None,
        errors: Optional[list[Dict[str, Any]]] = None,
        next_step: str = "",
    ) -> Dict[str, Any]:
        return {
            "tool": "github_repo_interview_workflow",
            "type": "github_repo_interview_workflow",
            "version": "v1",
            "status": status,
            "partial": status == "partial",
            "input": input_data,
            "data": data or {},
            "warnings": warnings or [],
            "errors": errors or [],
            "next_step": next_step,
        }

    def _state_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in state.items()
            if key not in {"status", "partial", "warnings", "errors"}
        }

    def _attach_saved_memory_context(
        self,
        data: Dict[str, Any],
        saved_memory_context: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        memories = select_workflow_memory_context(saved_memory_context or [])
        if memories:
            data["saved_memory_context"] = memories
        return data

    def _attach_session_memory_context(
        self,
        data: Dict[str, Any],
        session_memory_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        memory = sanitize_session_memory_state(session_memory_context or {})
        if memory:
            data["session_memory_context"] = memory
        return data

    def _attach_vector_memory_context(
        self,
        data: Dict[str, Any],
        vector_memory_context: Optional[List[Dict[str, Any]]],
        vector_memory_retrieval: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        context = sanitize_vector_memory_context(vector_memory_context or [])
        retrieval = sanitize_vector_memory_retrieval(vector_memory_retrieval or {})
        if retrieval.get("status") == "disabled" and not context:
            return data
        if context:
            data["vector_memory_context"] = context
        data["vector_memory_retrieval"] = retrieval
        return data

    def _attach_session_memory_patch(
        self,
        data: Dict[str, Any],
        input_data: Dict[str, Any],
        session_memory_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        patch = build_session_memory_patch(
            input_data=input_data,
            workflow_data=data,
            existing_memory=session_memory_context or {},
        )
        if patch:
            data["session_memory_patch"] = patch
        return data

    def _attach_session_memory_fields(
        self,
        data: Dict[str, Any],
        input_data: Dict[str, Any],
        session_memory_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        data = self._attach_session_memory_context(data, session_memory_context)
        return self._attach_session_memory_patch(data, input_data, session_memory_context)

    def _attach_normalized_intent(self, data: Dict[str, Any], normalized_intent: Dict[str, Any]) -> Dict[str, Any]:
        if normalized_intent:
            data["normalized_intent"] = normalized_intent
        return data

    def _attach_answer_quality_signals(
        self,
        data: Dict[str, Any],
        warnings: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        signals = build_answer_quality_signals(data, warnings=warnings, errors=errors)
        if signals:
            data["answer_quality_signals"] = signals
        return data

    def _attach_multi_agent_trace(
        self,
        state: Dict[str, Any],
        data: Dict[str, Any],
        input_data: Dict[str, Any],
        warnings: list[Dict[str, Any]],
        errors: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        data["multi_agent_trace"] = build_multi_agent_trace(
            state,
            data,
            input_data,
            warnings,
            errors or [],
        )
        return data

    @usage_example("""
Chinese GitHub interview answer-coach routing:

If a GitHub interview prep result or workflow state already exists and the user says:
- "点评我的回答"
- "评价一下"
- "我这样答可以吗"
- "回答如下"
- "帮我指出优缺点"
- "根据刚才的问题点评"
- "第 X 题答案"
- "第 X 题我的答案是"
- "QX 答案"
- "QX 我的回答"

call github_repo_interview_workflow instead of replying with ordinary text feedback.

Required call shape:
<function_calls>
<invoke name="github_repo_interview_workflow">
<parameter name="stage">coach_answer</parameter>
<parameter name="prep_questions_pack">{existing prep_questions_pack from the previous GitHub interview prep result}</parameter>
<parameter name="question_id">QX when the user says 第 X 题 or QX, otherwise the current selected question id</parameter>
<parameter name="user_answer">{the user's latest answer text}</parameter>
<parameter name="previous_workflow_state">{existing GitHub interview workflow state, if available}</parameter>
<parameter name="language">zh</parameter>
<parameter name="coach_style">balanced</parameter>
</invoke>
</function_calls>

不要重新读取 GitHub. Do not call github_repo_interview_prep. Do not read local files. Do not save the raw user answer.
""")
    async def github_repo_interview_workflow(
        self,
        stage: str,
        prep_questions_pack: Dict[str, Any],
        question_id: str = "",
        user_answer: str = "",
        follow_up_answer: str = "",
        selected_follow_up_id: str = "",
        previous_workflow_state: Optional[Dict[str, Any]] = None,
        saved_memory_context: Optional[List[Dict[str, Any]]] = None,
        session_memory_context: Optional[Dict[str, Any]] = None,
        vector_memory_context: Optional[List[Dict[str, Any]]] = None,
        vector_memory_retrieval: Optional[Dict[str, Any]] = None,
        language: str = "zh",
        coach_style: str = "concise",
        preferred_question_category: str = "",
        max_follow_ups: int = 2,
    ) -> ToolResult:
        """Run one bounded GitHub interview workflow stage using existing evidence only.

        Use this tool, with stage="coach_answer", for Chinese follow-up messages such
        as "点评我的回答", "回答如下", "第 X 题答案", or "QX 答案" after a GitHub
        interview question pack already exists. This stage must reuse existing
        prep_questions_pack / previous_workflow_state and must not reread GitHub,
        inspect local files, persist raw answers, or call github_repo_interview_prep.
        """
        del selected_follow_up_id
        previous_workflow_state = _unwrap_previous_workflow_state(previous_workflow_state)
        (
            saved_memory_context,
            session_memory_context,
            vector_memory_context,
            vector_memory_retrieval,
        ) = await self._load_missing_memory_context(
            prep_questions_pack=prep_questions_pack,
            question_id=question_id,
            user_answer=user_answer,
            follow_up_answer=follow_up_answer,
            preferred_question_category=preferred_question_category,
            saved_memory_context=saved_memory_context,
            session_memory_context=session_memory_context,
            vector_memory_context=vector_memory_context,
            vector_memory_retrieval=vector_memory_retrieval,
        )
        session_memory_context = sanitize_session_memory_state(session_memory_context or {})

        normalized_max_follow_ups = _normalize_max_follow_ups(max_follow_ups)
        raw_language = language
        raw_coach_style = coach_style
        raw_category = preferred_question_category
        normalized_language, language_changed = normalize_language(language)
        normalized_coach_style, coach_style_changed = normalize_coach_style(coach_style)
        normalized_category, category_changed = normalize_question_category(preferred_question_category)
        language = normalized_language or language
        coach_style = normalized_coach_style or coach_style
        preferred_question_category = normalized_category or preferred_question_category
        if stage == "select_question" and not str(question_id or "").strip() and not preferred_question_category:
            question_id = _first_unanswered_question_id(prep_questions_pack, session_memory_context)
        normalized_intent = _normalized_intent(
            raw_language,
            language,
            language_changed,
            raw_coach_style,
            coach_style,
            coach_style_changed,
            raw_category,
            preferred_question_category,
            category_changed,
        )
        input_data = {
            "stage": stage,
            "question_id": question_id,
            "language": language,
            "coach_style": coach_style,
            "preferred_question_category": preferred_question_category,
            "max_follow_ups": normalized_max_follow_ups,
        }

        state = build_workflow_state(
            stage=stage,
            prep_questions_pack=prep_questions_pack,
            question_id=question_id,
            previous_workflow_state=previous_workflow_state,
            language=language,
            preferred_question_category=preferred_question_category,
            follow_up_answer=follow_up_answer,
        )
        if state.get("status") == "error":
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=self._state_data(state),
                    warnings=state.get("warnings"),
                    errors=state.get("errors"),
                    next_step="Provide a Slice 4 question pack and an exact question_id or matching preferred_question_category.",
                ),
                success=False,
            )

        warnings = list(state.get("warnings") or [])
        if language not in ALLOWED_LANGUAGES:
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=self._state_data(state),
                    warnings=warnings,
                    errors=[_error("invalid_question", "language must be one of: zh, en.")],
                    next_step="Use language zh or en.",
                ),
                success=False,
            )
        if coach_style not in ALLOWED_COACH_STYLES:
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=self._state_data(state),
                    warnings=warnings,
                    errors=[
                        _error(
                            "invalid_question",
                            "coach_style must be one of: concise, direct, encouraging, balanced.",
                        )
                    ],
                    next_step="Use a supported coach_style.",
                ),
                success=False,
            )

        if stage == "coach_follow_up":
            return await self._run_follow_up_stage(
                state=state,
                input_data=input_data,
                prep_questions_pack=prep_questions_pack,
                warnings=warnings,
                previous_workflow_state=previous_workflow_state,
                follow_up_answer=follow_up_answer,
                saved_memory_context=saved_memory_context,
                session_memory_context=session_memory_context,
                vector_memory_context=vector_memory_context,
                vector_memory_retrieval=vector_memory_retrieval,
                language=language,
                max_follow_ups=normalized_max_follow_ups,
                normalized_intent=normalized_intent,
            )

        if stage == "summarize":
            return await self._run_summary_stage(
                state=state,
                input_data=input_data,
                warnings=warnings,
                previous_workflow_state=previous_workflow_state,
                saved_memory_context=saved_memory_context,
                session_memory_context=session_memory_context,
                vector_memory_context=vector_memory_context,
                vector_memory_retrieval=vector_memory_retrieval,
                language=language,
                normalized_intent=normalized_intent,
            )

        if stage != "coach_answer":
            data = self._attach_saved_memory_context(self._state_data(state), saved_memory_context)
            data = self._attach_session_memory_fields(data, input_data, session_memory_context)
            data = self._attach_vector_memory_context(data, vector_memory_context, vector_memory_retrieval)
            data = self._attach_normalized_intent(data, normalized_intent)
            data = attach_context_snapshot(data, input_data)
            data = self._attach_multi_agent_trace(state, data, input_data, warnings)
            return self._json_result(
                self._payload(
                    "success",
                    input_data,
                    data=data,
                    warnings=warnings,
                    next_step="Answer the selected question to start coaching.",
                )
            )

        stripped_answer = str(user_answer or "").strip()
        if not stripped_answer:
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=self._state_data(state),
                    warnings=warnings,
                    errors=[_error("invalid_user_answer", "user_answer must be a non-empty string.")],
                    next_step="Provide user_answer for coach_answer.",
                ),
                success=False,
            )
        if len(stripped_answer) > MAX_USER_ANSWER_CHARS:
            stripped_answer = stripped_answer[:MAX_USER_ANSWER_CHARS]
            warnings.append(
                _warning(
                    "user_answer_truncated",
                    f"user_answer was truncated to {MAX_USER_ANSWER_CHARS} characters.",
                )
            )
        input_data["user_answer_excerpt"] = stripped_answer[:300]

        question_for_coach = {
            **state["selected_question"],
            "evidence_details": state["evidence_details"],
        }
        request = build_coach_request(
            question_for_coach,
            stripped_answer,
            language,
            coach_style,
            normalized_max_follow_ups,
        )
        request["role"] = role_contract("answer_coach")
        safe_vector_context = sanitize_vector_memory_context(vector_memory_context or [])
        safe_saved_context = select_workflow_memory_context(saved_memory_context or [])
        if safe_saved_context or safe_vector_context:
            request["memory_context"] = {
                "structured": safe_saved_context,
                "semantic": safe_vector_context,
                "rules": [
                    "use_as_user_practice_preference_only",
                    "do_not_treat_as_repository_evidence",
                ],
            }
        request = attach_context_policy(request, state, "answer_coach")
        valid_evidence_ids = _valid_evidence_ids(request["evidence_details"])
        if not valid_evidence_ids:
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=self._state_data(state),
                    warnings=warnings,
                    errors=[_error("invalid_question", "question.evidence_details must include at least one evidence_id.")],
                    next_step="Select a question with readable evidence_details.",
                ),
                success=False,
            )

        fallback_reason = ""
        try:
            feedback = await self.answer_coach_engine.generate_feedback(request)
        except Exception:
            feedback = None
            fallback_reason = "engine_exception"

        if not isinstance(feedback, dict):
            fallback_reason = fallback_reason or "invalid_output"
            feedback = _fallback_answer_feedback(state, language, normalized_max_follow_ups)

        sanitized_feedback, feedback_warnings, feedback_error = _sanitize_feedback(
            feedback,
            valid_evidence_ids,
            normalized_max_follow_ups,
        )
        warnings.extend(feedback_warnings)
        if feedback_error:
            fallback_reason = fallback_reason or "rejected_output"
            fallback_feedback = _fallback_answer_feedback(state, language, normalized_max_follow_ups)
            sanitized_feedback, fallback_warnings, fallback_error = _sanitize_feedback(
                fallback_feedback,
                valid_evidence_ids,
                normalized_max_follow_ups,
            )
            warnings.extend(fallback_warnings)
            if fallback_error:
                return self._json_result(
                    self._payload(
                        "error",
                        input_data,
                        data=self._state_data(state),
                        warnings=warnings,
                        errors=[_error(fallback_error["code"], fallback_error["message"])],
                        next_step="Select a question with readable allowed evidence.",
                    ),
                    success=False,
                )
        if fallback_reason:
            warnings.append(
                _warning(
                    "answer_coach_fallback_used",
                    "Answer coach output was unavailable or rejected; returned deterministic evidence-bounded feedback.",
                )
            )

        data = self._state_data(state)
        data["answer_feedback"] = sanitized_feedback or {}
        _mark_question_answered(data, previous_workflow_state)
        data = self._attach_saved_memory_context(data, saved_memory_context)
        data = self._attach_session_memory_fields(data, input_data, session_memory_context)
        data = self._attach_vector_memory_context(data, vector_memory_context, vector_memory_retrieval)
        data = self._attach_normalized_intent(data, normalized_intent)
        data = attach_context_snapshot(data, input_data)
        data = self._attach_answer_quality_signals(data, warnings=warnings)
        data = self._attach_multi_agent_trace(state, data, input_data, warnings)
        return self._json_result(
            self._payload(
                "success",
                input_data,
                data=data,
                warnings=warnings,
                next_step="Answer one follow-up question using the same evidence.",
            )
        )

    async def _run_follow_up_stage(
        self,
        state: Dict[str, Any],
        input_data: Dict[str, Any],
        prep_questions_pack: Dict[str, Any],
        warnings: list[Dict[str, Any]],
        previous_workflow_state: Optional[Dict[str, Any]],
        follow_up_answer: str,
        saved_memory_context: Optional[List[Dict[str, Any]]],
        session_memory_context: Optional[Dict[str, Any]],
        vector_memory_context: Optional[List[Dict[str, Any]]],
        vector_memory_retrieval: Optional[Dict[str, Any]],
        language: str,
        max_follow_ups: int,
        normalized_intent: Dict[str, Any],
    ) -> ToolResult:
        stripped_answer = str(follow_up_answer or "").strip()
        prior_follow_up_count = _previous_follow_up_count(previous_workflow_state)
        if prior_follow_up_count >= max_follow_ups:
            data = self._state_data(state)
            data.setdefault("workflow", {})["follow_up_count"] = prior_follow_up_count
            return self._json_result(
                self._payload(
                    "error",
                    input_data,
                    data=data,
                    warnings=warnings,
                    errors=[
                        _error(
                            "follow_up_limit_reached",
                            f"coach_follow_up is limited to {max_follow_ups} request(s) for this workflow.",
                        )
                    ],
                    next_step="Summarize this practice session or select another question.",
                ),
                success=False,
            )

        gatekeeper = EvidenceGatekeeper(state)
        answer_feedback = gatekeeper.filter_prior_feedback(previous_workflow_state, warnings)
        if not stripped_answer:
            follow_up = _follow_up_prompt_from_prior_feedback(
                state,
                answer_feedback,
                language,
                max_follow_ups,
            )
            if follow_up.pop("fallback_used", False):
                warnings.append(
                    _warning(
                        "follow_up_question_fallback_used",
                        "No usable prior follow-up question was available; returned a deterministic evidence-bounded question.",
                    )
                )
            data = self._state_data(state)
            data.setdefault("workflow", {})["follow_up_count"] = prior_follow_up_count
            data["answer_feedback"] = answer_feedback
            data["follow_up"] = follow_up
            data = self._attach_saved_memory_context(data, saved_memory_context)
            data = self._attach_session_memory_fields(data, input_data, session_memory_context)
            data = self._attach_vector_memory_context(data, vector_memory_context, vector_memory_retrieval)
            data = self._attach_normalized_intent(data, normalized_intent)
            data = attach_context_snapshot(data, input_data)
            if _answer_coached(answer_feedback):
                data = self._attach_answer_quality_signals(data, warnings=warnings)
            data = self._attach_multi_agent_trace(state, data, input_data, warnings)
            return self._json_result(
                self._payload(
                    "success",
                    input_data,
                    data=data,
                    warnings=warnings,
                    next_step="Answer one follow-up question, then call coach_follow_up again with follow_up_answer.",
                )
            )

        if len(stripped_answer) > MAX_USER_ANSWER_CHARS:
            stripped_answer = stripped_answer[:MAX_USER_ANSWER_CHARS]
            warnings.append(
                _warning(
                    "follow_up_answer_truncated",
                    f"follow_up_answer was truncated to {MAX_USER_ANSWER_CHARS} characters.",
                )
            )

        request = attach_context_policy(
            {
                "stage": "coach_follow_up",
                "role": role_contract("follow_up_coach"),
                "question": state["selected_question"],
                "evidence_details": state["evidence_details"],
                "answer_feedback": answer_feedback,
                "follow_up_answer": stripped_answer,
                "language": language,
                "max_follow_ups": max_follow_ups,
                "output_contract": _follow_up_output_contract(language),
            },
            state,
            "follow_up_coach",
        )
        safe_vector_context = sanitize_vector_memory_context(vector_memory_context or [])
        safe_saved_context = select_workflow_memory_context(saved_memory_context or [])
        if safe_saved_context or safe_vector_context:
            request["memory_context"] = {
                "structured": safe_saved_context,
                "semantic": safe_vector_context,
                "rules": ["do_not_treat_as_repository_evidence"],
            }
        fallback_reason = ""
        try:
            response = await self.follow_up_engine.generate_feedback(request)
        except Exception:
            response = None
            fallback_reason = "engine_exception"
        if not isinstance(response, dict) or _contains_disallowed_judgment(response):
            fallback_reason = fallback_reason or "rejected_output"
            follow_up = _fallback_follow_up_feedback(state, language, stripped_answer)
        else:
            follow_up = gatekeeper.filter_follow_up_response(response, max_follow_ups, warnings)
            if not follow_up.get("questions") and not follow_up.get("feedback"):
                fallback_reason = "empty_filtered_output"
                follow_up = _fallback_follow_up_feedback(state, language, stripped_answer)
            else:
                follow_up["mode"] = "answer_feedback"
        if fallback_reason:
            warnings.append(
                _warning(
                    "follow_up_feedback_fallback_used",
                    "Follow-up LLM output was unavailable or rejected; returned deterministic bounded feedback.",
                )
            )
        data = self._state_data(state)
        data.setdefault("workflow", {})["follow_up_count"] = prior_follow_up_count + 1
        _mark_question_answered(data, previous_workflow_state)
        data["answer_feedback"] = answer_feedback
        data["follow_up"] = follow_up
        data["other_questions"] = _other_questions_from_pack(
            prep_questions_pack,
            str(data.get("selected_question", {}).get("id") or ""),
            previous_workflow_state,
        )
        data = self._attach_saved_memory_context(data, saved_memory_context)
        data = self._attach_session_memory_fields(data, input_data, session_memory_context)
        data = self._attach_vector_memory_context(data, vector_memory_context, vector_memory_retrieval)
        data = self._attach_normalized_intent(data, normalized_intent)
        data = attach_context_snapshot(data, input_data)
        if _answer_coached(answer_feedback):
            data = self._attach_answer_quality_signals(data, warnings=warnings)
        data = self._attach_multi_agent_trace(state, data, input_data, warnings)
        return self._json_result(
            self._payload(
                "success",
                input_data,
                data=data,
                warnings=warnings,
                next_step="Summarize this practice session when ready.",
            )
        )

    async def _run_summary_stage(
        self,
        state: Dict[str, Any],
        input_data: Dict[str, Any],
        warnings: list[Dict[str, Any]],
        previous_workflow_state: Optional[Dict[str, Any]],
        saved_memory_context: Optional[List[Dict[str, Any]]],
        session_memory_context: Optional[Dict[str, Any]],
        vector_memory_context: Optional[List[Dict[str, Any]]],
        vector_memory_retrieval: Optional[Dict[str, Any]],
        language: str,
        normalized_intent: Dict[str, Any],
    ) -> ToolResult:
        previous = previous_workflow_state if isinstance(previous_workflow_state, dict) else {}
        gatekeeper = EvidenceGatekeeper(state)
        answer_feedback = gatekeeper.filter_prior_feedback(previous, warnings)
        filtered_follow_up = gatekeeper.filter_prior_follow_up(previous, warnings)
        practice_history = _practice_history_from_previous_state(previous)
        answered_question_ids = [item["question_id"] for item in practice_history]
        if not answered_question_ids:
            answered_question_ids = _previous_answered_question_ids(previous)
        current_question_id = str(state.get("selected_question", {}).get("id") or "").strip()
        if current_question_id and current_question_id not in answered_question_ids:
            answered_question_ids.append(current_question_id)
        has_answer_feedback = _answer_coached(answer_feedback)
        has_completed_follow_up = _follow_up_completed(filtered_follow_up)
        if not has_completed_follow_up:
            warnings.append(
                _warning(
                    "follow_up_not_completed",
                    "Summary was generated without completed follow-up feedback.",
                )
            )
        request_body = {
            "stage": "summarize",
            "role": role_contract("session_summarizer"),
            "question": state["selected_question"],
            "evidence_details": state["evidence_details"],
            "answer_feedback": answer_feedback,
            "follow_up": filtered_follow_up,
            "practice_history": practice_history,
            "language": language,
        }
        safe_vector_context = sanitize_vector_memory_context(vector_memory_context or [])
        safe_saved_context = select_workflow_memory_context(saved_memory_context or [])
        if safe_saved_context or safe_vector_context:
            request_body["memory_context"] = {
                "structured": safe_saved_context,
                "semantic": safe_vector_context,
                "rules": ["do_not_treat_as_repository_evidence"],
            }
        request = attach_context_policy(request_body, state, "session_summarizer")
        try:
            response = await self.summary_engine.generate_feedback(request)
        except Exception:
            return self._workflow_generation_failed(input_data, state, warnings)
        summary = {}
        if isinstance(response, dict) and not _contains_disallowed_judgment(response):
            summary = gatekeeper.filter_summary_response(response, warnings)
        if _summary_needs_fallback(summary):
            relaxed_summary = _demo_relaxed_session_summary(response, language)
            if relaxed_summary:
                summary = relaxed_summary
                warnings.append(
                    _warning(
                        "summary_demo_relaxed_validation_used",
                        "Summary used demo-relaxed validation: returned LLM content without strict evidence grounding failure.",
                    )
                )
        if _summary_needs_fallback(summary):
            summary = _fallback_session_summary(state, answer_feedback, filtered_follow_up, language)
            warnings.append(
                _warning(
                    "summary_fallback_used",
                    "Summary LLM output was empty after demo-relaxed validation; returned deterministic bounded summary.",
                )
            )
        summary["workflow_completion"] = _workflow_completion(
            has_answer_feedback,
            has_completed_follow_up,
            answered_question_ids,
        )
        data = self._state_data(state)
        if answered_question_ids:
            data.setdefault("workflow", {})["answered_question_ids"] = answered_question_ids
        if practice_history:
            data.setdefault("workflow", {})["practice_history"] = practice_history
        data["session_summary"] = summary
        data = self._attach_saved_memory_context(data, saved_memory_context)
        data = self._attach_session_memory_fields(data, input_data, session_memory_context)
        data = self._attach_vector_memory_context(data, vector_memory_context, vector_memory_retrieval)
        data = self._attach_normalized_intent(data, normalized_intent)
        data = attach_context_snapshot(data, input_data)
        data = self._attach_answer_quality_signals(data, warnings=warnings)
        data = self._attach_multi_agent_trace(state, data, input_data, warnings)
        next_step = (
            "Follow-up was not answered; answer the follow-up question or pick another question."
            if not has_completed_follow_up
            else "Pick another question or revise the same answer with stronger evidence."
        )
        return self._json_result(
            self._payload(
                "success",
                input_data,
                data=data,
                warnings=warnings,
                next_step=next_step,
            )
        )

    def _workflow_generation_failed(
        self,
        input_data: Dict[str, Any],
        state: Dict[str, Any],
        warnings: list[Dict[str, Any]],
    ) -> ToolResult:
        return self._json_result(
            self._payload(
                "error",
                input_data,
                data=self._state_data(state),
                warnings=warnings,
                errors=[
                    _error(
                        "workflow_generation_failed",
                        "Workflow stage output could not be generated within the evidence and scoring boundaries.",
                    )
                ],
                next_step="Retry with output grounded only in allowed evidence and without scoring.",
            ),
            success=False,
        )
