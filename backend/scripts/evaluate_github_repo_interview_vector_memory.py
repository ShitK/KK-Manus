"""Small regression harness for GitHub interview semantic memory.

The default command validates the fixed dataset contract without calling an
external model. Tests inject the production retrieval adapter; a live adapter
can be added once the target database exposes pgvector.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List


DEFAULT_CASES = Path("tests/fixtures/github_repo_interview_vector_memory_eval_cases.json")


def validate_cases(cases: List[Dict[str, Any]]) -> None:
    if len(cases) < 15:
        raise ValueError("vector memory eval requires at least 15 cases")
    seen = set()
    for case in cases:
        case_id = str(case.get("id") or "").strip()
        query = str(case.get("query") or "").strip()
        status = case.get("expected_status")
        if not case_id or case_id in seen:
            raise ValueError("eval case ids must be non-empty and unique")
        if not query:
            raise ValueError(f"eval case {case_id} has no query")
        if status not in {"matched", "no_match", "embedding_error", "retrieval_error"}:
            raise ValueError(f"eval case {case_id} has unsupported expected status")
        if not isinstance(case.get("expected_memory_ids"), list):
            raise ValueError(f"eval case {case_id} has invalid expected ids")
        if not isinstance(case.get("forbidden_memory_ids"), list):
            raise ValueError(f"eval case {case_id} has invalid forbidden ids")
        seen.add(case_id)


async def evaluate_cases(
    cases: List[Dict[str, Any]],
    retrieve_case: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
) -> Dict[str, Any]:
    validate_cases(cases)
    results = []
    positive_count = 0
    positive_pass = 0
    rejection_count = 0
    rejection_pass = 0
    no_match_count = 0
    no_match_pass = 0
    fallback_count = 0
    fallback_pass = 0
    ownership_violations = 0

    for case in cases:
        actual = await retrieve_case(case)
        actual_ids = {str(item) for item in actual.get("memory_ids") or []}
        expected_ids = {str(item) for item in case.get("expected_memory_ids") or []}
        forbidden_ids = {str(item) for item in case.get("forbidden_memory_ids") or []}
        expected_status = case["expected_status"]
        status_ok = actual.get("status") == expected_status
        hit_ok = expected_ids.issubset(actual_ids)
        rejection_ok = not bool(forbidden_ids & actual_ids)
        passed = status_ok and hit_ok and rejection_ok

        if expected_ids:
            positive_count += 1
            positive_pass += int(hit_ok and status_ok)
        if forbidden_ids:
            rejection_count += 1
            rejection_pass += int(rejection_ok)
        if expected_status == "no_match":
            no_match_count += 1
            no_match_pass += int(status_ok and not actual_ids)
        if expected_status in {"embedding_error", "retrieval_error"}:
            fallback_count += 1
            fallback_pass += int(bool(actual.get("fallback_used")))
        ownership_violations += int(bool(actual.get("ownership_violation")))
        results.append(
            {
                "id": case["id"],
                "expected_status": expected_status,
                "actual_status": actual.get("status"),
                "expected_memory_ids": sorted(expected_ids),
                "actual_memory_ids": sorted(actual_ids),
                "passed": passed,
            }
        )

    ratio = lambda passed, total: round(passed / total, 4) if total else 1.0
    return {
        "metrics": {
            "case_count": len(cases),
            "expected_hit_rate": ratio(positive_pass, positive_count),
            "irrelevant_rejection_rate": ratio(rejection_pass, rejection_count),
            "memory_ownership_violation_count": ownership_violations,
            "fallback_success_rate": ratio(fallback_pass, fallback_count),
            "no_match_accuracy": ratio(no_match_pass, no_match_count),
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--contract-only", action="store_true", default=True)
    args = parser.parse_args()
    payload = json.loads(args.cases.read_text())
    cases = payload.get("cases") or []
    validate_cases(cases)
    report = {
        "dataset_id": payload.get("dataset_id"),
        "mode": "contract_only",
        "case_count": len(cases),
        "status": "valid",
        "note": "No retrieval quality claim is produced until a pgvector-capable database is configured.",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
