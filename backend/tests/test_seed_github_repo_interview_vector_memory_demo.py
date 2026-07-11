import unittest
from pathlib import Path

from scripts.seed_github_repo_interview_vector_memory_demo import load_dataset


class SeedVectorMemoryDemoTest(unittest.TestCase):
    def test_dataset_is_grounded_and_safe(self):
        dataset = load_dataset(
            Path("tests/fixtures/miniclawd_vector_memory_demo_seed.json")
        )
        self.assertEqual(dataset["repository"], "ShitK/miniclawd")
        self.assertEqual(dataset["commit"], "2d65665")
        self.assertGreaterEqual(len(dataset["memories"]), 8)
        self.assertGreaterEqual(len(dataset["showcase_queries"]), 4)
        self.assertEqual(
            len({item["id"] for item in dataset["memories"]}),
            len(dataset["memories"]),
        )

    def test_dataset_rejects_source_drift(self):
        with self.assertRaises(ValueError):
            load_dataset(
                Path("tests/fixtures/miniclawd_vector_memory_demo_seed.json"),
                expected_commit="wrong",
            )


if __name__ == "__main__":
    unittest.main()
