import unittest

from agent.tools.github_repo_questions import build_interview_questions


class GitHubRepoQuestionsTest(unittest.TestCase):
    def sample_context_pack(self):
        return {
            "repo_metadata": {
                "full_name": "pypa/sampleproject",
                "primary_language": "Python",
                "description": "A sample Python project",
            },
            "readme_summary": {
                "summary": "A sample project demonstrating Python packaging.",
                "confidence": "medium",
            },
            "manifest_summary": [
                {
                    "path": "pyproject.toml",
                    "ecosystem": "python",
                    "dependencies": ["peppercorn"],
                    "scripts_or_entrypoints": ["sample"],
                    "summary": "python manifest with 1 detected dependency.",
                }
            ],
            "directory_summary": {
                "top_level_dirs": ["src", "tests"],
                "notable_paths": ["pyproject.toml", "src/sample/__init__.py", "noxfile.py"],
                "total_entries": 17,
                "truncated": False,
                "summary": "Repository tree includes 17 entries and Python package source.",
            },
            "file_summaries": [
                {
                    "path": "src/sample/__init__.py",
                    "role": "source file",
                    "important_symbols": ["main"],
                    "summary": "src/sample/__init__.py exposes package code.",
                    "evidence_snippets": [
                        {"id": "src:src/sample/__init__.py#snippet-1", "text": "def main():"}
                    ],
                    "interview_relevance": ["implementation detail"],
                    "confidence": "medium",
                },
                {
                    "path": "noxfile.py",
                    "role": "source file",
                    "important_symbols": ["tests"],
                    "summary": "noxfile.py defines automation sessions.",
                    "evidence_snippets": [
                        {"id": "src:noxfile.py#snippet-1", "text": "def tests(session):"}
                    ],
                    "interview_relevance": ["testing automation"],
                    "confidence": "medium",
                },
            ],
            "evidence_map": [
                {
                    "id": "src:src/sample/__init__.py#snippet-1",
                    "source_path": "src/sample/__init__.py",
                    "source_type": "source",
                    "claim": "Package source exists.",
                    "confidence": "medium",
                },
                {
                    "id": "src:noxfile.py#snippet-1",
                    "source_path": "noxfile.py",
                    "source_type": "source",
                    "claim": "Automation source exists.",
                    "confidence": "medium",
                },
            ],
        }

    def test_generates_requested_number_of_zh_questions_with_evidence(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        self.assertEqual(result["summary"]["requested_count"], 3)
        self.assertEqual(result["summary"]["generated_count"], 3)
        self.assertEqual(result["summary"]["available_template_count"], 4)
        self.assertEqual(result["summary"]["difficulty"], "mid")
        self.assertTrue(result["summary"]["has_source_evidence"])
        self.assertEqual([question["id"] for question in result["questions"]], ["Q1", "Q2", "Q3"])
        for question in result["questions"]:
            self.assertEqual(question["difficulty"], "mid")
            self.assertLessEqual(len(question["question"]), 300)
            self.assertLessEqual(len(question["answer_direction"]), 500)
            self.assertTrue(question["question"].startswith("你"))
            self.assertTrue(question["answer_direction"])
            self.assertTrue(question["evidence_refs"])
            self.assertTrue(question["source_paths"])

    def test_dependency_question_uses_manifest_evidence(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        dependency_question = result["questions"][2]
        self.assertEqual(dependency_question["category"], "dependency and packaging")
        self.assertEqual(dependency_question["evidence_refs"], ["manifest:pyproject.toml"])
        self.assertEqual(dependency_question["source_paths"], ["pyproject.toml"])

    def test_caps_question_count_to_available_templates_without_duplicates(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="senior",
            question_count=10,
            language="zh",
        )

        questions = result["questions"]
        self.assertGreaterEqual(len(questions), 4)
        self.assertLessEqual(len(questions), 10)
        self.assertEqual(len({question["question"] for question in questions}), len(questions))
        self.assertEqual([question["id"] for question in questions], [f"Q{i + 1}" for i in range(len(questions))])

    def test_generates_english_questions_when_language_is_en(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="junior",
            question_count=2,
            language="en",
        )

        self.assertEqual(len(result["questions"]), 2)
        self.assertIn("How would you explain", result["questions"][0]["question"])
        self.assertIn("Start by", result["questions"][0]["answer_direction"])

    def test_difficulty_affects_question_wording(self):
        junior = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="junior",
            question_count=1,
            language="zh",
        )
        senior = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="senior",
            question_count=1,
            language="zh",
        )

        self.assertIn("先识别", junior["questions"][0]["answer_direction"])
        self.assertIn("权衡", senior["questions"][0]["answer_direction"])
        self.assertNotEqual(junior["questions"][0]["answer_direction"], senior["questions"][0]["answer_direction"])

    def test_falls_back_when_source_evidence_is_missing(self):
        context_pack = self.sample_context_pack()
        context_pack["file_summaries"] = []
        context_pack["evidence_map"] = []

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        self.assertFalse(result["summary"]["has_source_evidence"])
        self.assertEqual(len(result["questions"]), 3)
        self.assertTrue(all(question["confidence"] == "low" for question in result["questions"]))
        self.assertTrue(all(question["source_paths"] for question in result["questions"]))

    def test_skips_dependency_question_without_manifest_summary(self):
        context_pack = self.sample_context_pack()
        context_pack["manifest_summary"] = []

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        categories = [question["category"] for question in result["questions"]]
        self.assertNotIn("dependency and packaging", categories)
        self.assertEqual(result["summary"]["available_template_count"], 3)
        self.assertEqual(result["summary"]["generated_count"], 3)
        self.assertTrue(result["summary"]["has_source_evidence"])
        self.assertTrue(all(question["evidence_refs"] for question in result["questions"]))
        for question in result["questions"]:
            self.assertFalse(any(ref.startswith("manifest:") for ref in question["evidence_refs"]))
            self.assertLessEqual(len(question["question"]), 300)
            self.assertLessEqual(len(question["answer_direction"]), 500)

    def test_questions_include_readable_evidence_details(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        for question in result["questions"]:
            details = question.get("evidence_details")
            self.assertTrue(details)
            self.assertLessEqual(len(details), 3)
            source_paths = set(question["source_paths"])
            for detail in details:
                self.assertTrue(detail.get("evidence_id"))
                self.assertTrue(detail.get("source_path"))
                self.assertTrue(detail.get("evidence_type"))
                self.assertTrue(detail.get("why_it_matters"))
                self.assertTrue(detail.get("snippet") or detail.get("summary"))
                if detail["source_path"] != "repository tree" and detail["source_path"] != "README":
                    self.assertIn(detail["source_path"], source_paths)

    def test_manifest_question_includes_manifest_detail(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        dependency_question = result["questions"][2]
        manifest_details = [
            detail
            for detail in dependency_question["evidence_details"]
            if detail["evidence_type"] == "manifest"
        ]
        self.assertTrue(manifest_details)
        detail = manifest_details[0]
        self.assertEqual(detail["evidence_id"], "manifest:pyproject.toml")
        self.assertEqual(detail["source_path"], "pyproject.toml")
        self.assertIn("python", detail["summary"])
        self.assertIn("peppercorn", detail["summary"])

    def test_source_question_includes_source_snippet_detail(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=2,
            language="zh",
        )

        implementation_question = result["questions"][1]
        source_details = [
            detail
            for detail in implementation_question["evidence_details"]
            if detail["evidence_type"] == "source"
        ]
        self.assertTrue(source_details)
        detail = source_details[0]
        self.assertEqual(detail["source_path"], "src/sample/__init__.py")
        self.assertIn("def main():", detail["snippet"])
        self.assertLessEqual(len(detail["snippet"]), 300)

    def test_grounded_direction_mentions_current_evidence_path(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        for question in result["questions"]:
            detail_paths = {detail["source_path"] for detail in question["evidence_details"]}
            self.assertTrue(any(path in question["answer_direction"] for path in detail_paths))
            self.assertLessEqual(len(question["answer_direction"]), 500)

    def test_architecture_question_does_not_force_manifest_detail(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=1,
            language="zh",
        )

        architecture_question = result["questions"][0]
        self.assertEqual(architecture_question["category"], "architecture")
        self.assertFalse(
            any(
                detail["evidence_type"] == "manifest"
                for detail in architecture_question["evidence_details"]
            )
        )
        self.assertNotIn("pyproject.toml", architecture_question["answer_direction"])

    def test_direction_paths_belong_to_current_question(self):
        result = build_interview_questions(
            self.sample_context_pack(),
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        known_paths = {"pyproject.toml", "src/sample/__init__.py", "noxfile.py"}
        for question in result["questions"]:
            allowed_paths = set(question["source_paths"]) | {
                detail["source_path"] for detail in question["evidence_details"]
            }
            mentioned_paths = {
                path for path in known_paths if path in question["answer_direction"]
            }
            self.assertTrue(mentioned_paths)
            self.assertTrue(mentioned_paths.issubset(allowed_paths))

    def test_empty_context_direction_does_not_invent_evidence_path(self):
        context_pack = {
            "repo_metadata": {"full_name": "owner/empty"},
            "readme_summary": {},
            "manifest_summary": [],
            "directory_summary": {},
            "file_summaries": [],
            "evidence_map": [],
        }

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=1,
            language="zh",
        )

        question = result["questions"][0]
        self.assertEqual(question["evidence_details"], [])
        self.assertNotIn("先结合 README", question["answer_direction"])
        self.assertIn("可用证据有限", question["answer_direction"])

    def test_fallback_details_when_source_evidence_is_missing(self):
        context_pack = self.sample_context_pack()
        context_pack["file_summaries"] = []
        context_pack["evidence_map"] = []

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=3,
            language="zh",
        )

        self.assertFalse(result["summary"]["has_source_evidence"])
        for question in result["questions"]:
            self.assertEqual(question["confidence"], "low")
            self.assertTrue(question["evidence_details"])
            self.assertTrue(
                all(detail["evidence_type"] in {"readme", "manifest", "directory"} for detail in question["evidence_details"])
            )

    def test_evidence_details_are_bounded(self):
        context_pack = self.sample_context_pack()
        for index in range(5):
            path = f"src/extra_{index}.py"
            evidence_id = f"src:{path}#snippet-1"
            context_pack["evidence_map"].append(
                {
                    "id": evidence_id,
                    "source_path": path,
                    "source_type": "source",
                    "claim": "Extra source exists.",
                    "snippet": "x = 1\n" * 200,
                    "confidence": "medium",
                }
            )
            context_pack["file_summaries"].append(
                {
                    "path": path,
                    "role": "source file",
                    "important_symbols": [],
                    "summary": "Extra source summary " * 100,
                    "evidence_snippets": [{"id": evidence_id, "text": "x = 1\n" * 200}],
                    "interview_relevance": ["implementation detail"],
                    "confidence": "medium",
                }
            )

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="senior",
            question_count=1,
            language="zh",
        )

        details = result["questions"][0]["evidence_details"]
        self.assertLessEqual(len(details), 3)
        for detail in details:
            self.assertLessEqual(len(detail.get("snippet", "")), 300)
            self.assertLessEqual(len(detail.get("summary", "")), 300)
            self.assertLessEqual(len(detail.get("why_it_matters", "")), 240)
            self.assertTrue(detail.get("snippet") or detail.get("summary"))

    def test_unknown_evidence_ref_keeps_question_safe(self):
        context_pack = self.sample_context_pack()
        context_pack["evidence_map"].insert(
            0,
            {
                "id": "unknown:opaque-ref",
                "source_path": "mystery",
                "source_type": "unknown",
                "claim": "Unknown evidence exists.",
                "confidence": "low",
            },
        )

        result = build_interview_questions(
            context_pack,
            target_role="Python backend engineer",
            difficulty="mid",
            question_count=1,
            language="zh",
        )

        question = result["questions"][0]
        self.assertIn("unknown:opaque-ref", question["evidence_refs"])
        self.assertTrue(question["evidence_details"])
        self.assertFalse(
            any(detail.get("evidence_id") == "unknown:opaque-ref" for detail in question["evidence_details"])
        )


if __name__ == "__main__":
    unittest.main()
