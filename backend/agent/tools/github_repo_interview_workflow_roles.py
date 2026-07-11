from copy import deepcopy
import re
from typing import Any, Dict

from agent.tools.github_repo_answer_coach import _warning


PATHLIKE_PATTERN = re.compile(r"\b[\w./-]+\.(?:py|ts|tsx|js|jsx|toml|json|md|yml|yaml|go|rs|java)\b")
MAX_PRIOR_REASON_CHARS = 300


WORKFLOW_ROLE_CONTRACTS = (
    {
        "id": "workflow_orchestrator",
        "kind": "deterministic",
        "stage": "all",
        "evidence_scope": "workflow_state",
        "repository_access": "no_new_repository_access",
    },
    {
        "id": "question_selector",
        "kind": "deterministic",
        "stage": "select_question",
        "evidence_scope": "interview_questions",
        "repository_access": "no_new_repository_access",
    },
    {
        "id": "evidence_gatekeeper",
        "kind": "deterministic",
        "stage": "all",
        "evidence_scope": "selected_question.evidence_details",
        "repository_access": "no_new_repository_access",
    },
    {
        "id": "answer_coach",
        "kind": "llm",
        "stage": "coach_answer",
        "evidence_scope": "selected_question.evidence_details",
        "repository_access": "no_new_repository_access",
    },
    {
        "id": "follow_up_coach",
        "kind": "llm",
        "stage": "coach_follow_up",
        "evidence_scope": "selected_question.evidence_details",
        "repository_access": "no_new_repository_access",
    },
    {
        "id": "session_summarizer",
        "kind": "llm",
        "stage": "summarize",
        "evidence_scope": "selected_question.evidence_details",
        "repository_access": "no_new_repository_access",
    },
)


STAGE_TO_ACTIVE_ROLE = {
    "select_question": "question_selector",
    "coach_answer": "answer_coach",
    "coach_follow_up": "follow_up_coach",
    "summarize": "session_summarizer",
}


def workflow_role_contracts() -> list[Dict[str, Any]]:
    return deepcopy(list(WORKFLOW_ROLE_CONTRACTS))


def active_role_for_stage(stage: str) -> str:
    # Unknown stages follow build_workflow_state's default question-selected path.
    return STAGE_TO_ACTIVE_ROLE.get(str(stage or "").strip(), "question_selector")


def role_contract(role_id: str) -> Dict[str, Any]:
    for role in WORKFLOW_ROLE_CONTRACTS:
        if role["id"] == role_id:
            return deepcopy(role)
    return {}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


class EvidenceGatekeeper:
    """Apply the workflow evidence boundary to prior state and LLM stage output."""

    def __init__(self, state: Dict[str, Any]):
        self.state = state
        self.allowed_paths = {
            detail["source_path"]
            for detail in state.get("evidence_details") or []
            if isinstance(detail, dict) and isinstance(detail.get("source_path"), str)
        }
        self.allowed_ids = set(state.get("evidence_policy", {}).get("allowed_evidence_ids") or [])

    def text_mentions_unknown_source(self, text: str) -> bool:
        if "http://" in text or "https://" in text:
            return True
        for evidence_ref in re.findall(r"\b(?:src|manifest|readme|directory):[^\s,，。)）]+", text):
            if evidence_ref not in self.allowed_ids:
                return True
        for path in PATHLIKE_PATTERN.findall(text):
            if path not in self.allowed_paths:
                return True
        return False

    def safe_text_list(self, value: Any) -> tuple[list[str], int]:
        kept = []
        dropped = 0
        for item in string_list(value):
            if self.text_mentions_unknown_source(item):
                dropped += 1
                continue
            kept.append(item)
        return kept, dropped

    def append_filtered_warning(self, warnings: list[Dict[str, Any]], dropped_count: int) -> None:
        if dropped_count <= 0:
            return
        warnings.append(
            _warning(
                "filtered_hallucinated_references",
                f"{dropped_count} text item(s) with unknown source paths, URLs, or evidence references were removed.",
            )
        )

    def filter_prior_feedback(
        self,
        previous_workflow_state: Any,
        warnings: list[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        previous = previous_workflow_state if isinstance(previous_workflow_state, dict) else {}
        feedback = previous.get("answer_feedback") if isinstance(previous.get("answer_feedback"), dict) else {}
        dropped_count = 0
        gaps, dropped = self.safe_text_list(feedback.get("gaps"))
        dropped_count += dropped
        follow_up_questions, dropped = self.safe_text_list(feedback.get("follow_up_questions"))
        dropped_count += dropped

        filtered: Dict[str, Any] = {
            "gaps": gaps,
            "follow_up_questions": follow_up_questions,
            "evidence_missed": [],
        }
        summary = str(feedback.get("summary") or "").strip()
        if summary and not self.text_mentions_unknown_source(summary):
            filtered["summary"] = summary
        elif summary:
            dropped_count += 1
        for item in feedback.get("evidence_missed") if isinstance(feedback.get("evidence_missed"), list) else []:
            if not isinstance(item, dict):
                continue
            evidence_id = item.get("evidence_id")
            source_path = item.get("source_path")
            if evidence_id in self.allowed_ids and source_path in self.allowed_paths:
                filtered["evidence_missed"].append(
                    {
                        "evidence_id": evidence_id,
                        "source_path": source_path,
                        "reason": str(item.get("reason") or "").strip()[:MAX_PRIOR_REASON_CHARS],
                    }
                )
            else:
                dropped_count += 1
        if warnings is not None:
            self.append_filtered_warning(warnings, dropped_count)
        return filtered

    def filter_prior_follow_up(
        self,
        previous_workflow_state: Any,
        warnings: list[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        previous = previous_workflow_state if isinstance(previous_workflow_state, dict) else {}
        follow_up = previous.get("follow_up") if isinstance(previous.get("follow_up"), dict) else {}
        dropped_count = 0
        questions, dropped = self.safe_text_list(follow_up.get("questions"))
        dropped_count += dropped
        feedback, dropped = self.safe_text_list(follow_up.get("feedback"))
        dropped_count += dropped
        grounding_notes, dropped = self.safe_text_list(follow_up.get("grounding_notes"))
        dropped_count += dropped
        if warnings is not None:
            self.append_filtered_warning(warnings, dropped_count)
        return {
            "questions": questions,
            "feedback": feedback,
            "grounding_notes": grounding_notes,
        }

    def filter_follow_up_response(
        self,
        response: Dict[str, Any],
        max_follow_ups: int,
        warnings: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        questions, dropped_questions = self.safe_text_list(response.get("questions"))
        feedback, dropped_feedback = self.safe_text_list(response.get("feedback"))
        grounding_notes, dropped_grounding_notes = self.safe_text_list(response.get("grounding_notes"))
        self.append_filtered_warning(warnings, dropped_questions + dropped_feedback + dropped_grounding_notes)
        return {
            "questions": questions[:max_follow_ups],
            "feedback": feedback,
            "grounding_notes": grounding_notes,
        }

    def filter_summary_response(self, response: Dict[str, Any], warnings: list[Dict[str, Any]]) -> Dict[str, Any]:
        practice_notes, dropped_notes = self.safe_text_list(response.get("practice_notes"))
        self.append_filtered_warning(warnings, dropped_notes)
        summary = {
            "covered_evidence": [item for item in string_list(response.get("covered_evidence")) if item in self.allowed_ids],
            "missed_evidence": [item for item in string_list(response.get("missed_evidence")) if item in self.allowed_ids],
            "practice_notes": practice_notes,
        }
        suggestion = str(response.get("next_practice_suggestion") or "").strip()
        if suggestion and not self.text_mentions_unknown_source(suggestion):
            summary["next_practice_suggestion"] = suggestion
        elif suggestion:
            self.append_filtered_warning(warnings, 1)
        return summary
