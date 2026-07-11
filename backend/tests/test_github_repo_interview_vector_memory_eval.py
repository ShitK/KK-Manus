import json
from pathlib import Path
import unittest

from scripts.evaluate_github_repo_interview_vector_memory import evaluate_cases, validate_cases


class VectorMemoryEvalTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        payload = json.loads(
            Path("tests/fixtures/github_repo_interview_vector_memory_eval_cases.json").read_text()
        )
        self.cases = payload["cases"]

    def test_fixture_has_fifteen_unique_cases_and_negative_cases(self):
        validate_cases(self.cases)
        self.assertGreaterEqual(len(self.cases), 15)
        self.assertEqual(len({case["id"] for case in self.cases}), len(self.cases))
        self.assertTrue(any(case["expected_status"] == "no_match" for case in self.cases))

    async def test_metrics_detect_hits_rejections_and_fallback(self):
        async def fake_retrieve(case):
            if case["id"] == "empty_memory_set":
                return {"status": "no_match", "memory_ids": [], "fallback_used": False}
            return {
                "status": case["expected_status"],
                "memory_ids": case["expected_memory_ids"],
                "fallback_used": False,
            }

        report = await evaluate_cases(self.cases, fake_retrieve)
        self.assertEqual(report["metrics"]["case_count"], 15)
        self.assertEqual(report["metrics"]["expected_hit_rate"], 1.0)
        self.assertEqual(report["metrics"]["irrelevant_rejection_rate"], 1.0)
        self.assertEqual(report["metrics"]["memory_ownership_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
