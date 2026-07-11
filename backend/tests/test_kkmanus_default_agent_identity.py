import unittest

from agent.identity import DEFAULT_ADK_APP_NAME, normalize_adk_app_name, normalize_event_author
from agent.fufanmanus.config import FufanmanusConfig


class KKManusDefaultAgentIdentityTest(unittest.TestCase):
    def test_default_agent_uses_kkmanus_public_identity(self):
        config = FufanmanusConfig.get_full_config()

        self.assertEqual(config["name"], "KKManus")
        self.assertIn("KKManus", config["description"])
        self.assertNotIn("FuFanManus", config["description"])

        system_prompt = FufanmanusConfig.get_system_prompt()
        self.assertIn("You are KKManus", system_prompt)
        for legacy_alias in ("FuFanManus", "fufanmanus", "FuFan", "小凡", "Suna", "Kortix"):
            self.assertNotIn(legacy_alias, system_prompt)

    def test_default_prompt_routes_github_interview_answer_feedback_to_workflow(self):
        system_prompt = FufanmanusConfig.get_system_prompt()

        self.assertIn("github_repo_interview_workflow", system_prompt)
        self.assertIn("coach_answer", system_prompt)
        self.assertIn("点评我的回答", system_prompt)
        self.assertIn("第 X 题答案", system_prompt)
        self.assertIn("QX 答案", system_prompt)
        self.assertIn("不要重新读取 GitHub", system_prompt)
        self.assertIn("不要直接用普通文本点评", system_prompt)

    def test_runtime_app_name_does_not_expose_legacy_identity(self):
        self.assertEqual(DEFAULT_ADK_APP_NAME, "kkmanus")
        self.assertEqual(normalize_adk_app_name("fufanmanus"), "kkmanus")
        self.assertEqual(normalize_adk_app_name("KKManus"), "kkmanus")
        self.assertEqual(normalize_adk_app_name(None), "kkmanus")

    def test_runtime_event_author_maps_agent_names_to_assistant_role(self):
        self.assertEqual(normalize_event_author("user"), "user")
        self.assertEqual(normalize_event_author("assistant"), "assistant")
        self.assertEqual(normalize_event_author("fufanmanus"), "assistant")
        self.assertEqual(normalize_event_author("kkmanus"), "assistant")


if __name__ == "__main__":
    unittest.main()
