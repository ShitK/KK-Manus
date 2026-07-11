import unittest

from agent.tools.github_repo_interview_intent import (
    normalize_coach_style,
    normalize_language,
    normalize_question_category,
)


class GitHubRepoInterviewIntentTest(unittest.TestCase):
    def test_normalize_language_accepts_chinese_aliases(self):
        self.assertEqual(normalize_language("中文"), ("zh", True))
        self.assertEqual(normalize_language("请用中文展示"), ("zh", True))
        self.assertEqual(normalize_language("English"), ("en", True))

    def test_normalize_coach_style_accepts_chinese_aliases(self):
        self.assertEqual(normalize_coach_style("平衡一点"), ("balanced", True))
        self.assertEqual(normalize_coach_style("既指出优点也指出不足"), ("balanced", True))
        self.assertEqual(normalize_coach_style("直接"), ("direct", True))
        self.assertEqual(normalize_coach_style("concise"), ("concise", False))

    def test_normalize_question_category_accepts_chinese_aliases(self):
        self.assertEqual(normalize_question_category("架构设计"), ("architecture", True))
        self.assertEqual(normalize_question_category("架构边界"), ("architecture", True))
        self.assertEqual(normalize_question_category("代码细节"), ("implementation detail", True))
        self.assertEqual(normalize_question_category("依赖与工程化"), ("dependency and packaging", True))
        self.assertEqual(normalize_question_category("测试验证"), ("testing and automation", True))

    def test_unknown_alias_returns_empty_string(self):
        self.assertEqual(normalize_language("法语"), ("", False))
        self.assertEqual(normalize_coach_style("随便"), ("", False))
        self.assertEqual(normalize_question_category("产品体验"), ("", False))

    def test_negative_phrases_do_not_match_by_substring(self):
        self.assertEqual(normalize_question_category("不要问测试"), ("", False))
        self.assertEqual(normalize_question_category("不需要架构设计"), ("", False))
        self.assertEqual(normalize_coach_style("不要直接告诉我答案"), ("", False))


if __name__ == "__main__":
    unittest.main()
