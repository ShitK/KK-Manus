import json
import unittest

from agentpress.response_processor import ResponseProcessor
from agentpress.tool import ToolResult


class ResponseProcessorGitHubBoundaryTests(unittest.TestCase):
    def test_replaces_assistant_content_when_github_repo_tool_fails(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "error",
                                    "errors": [
                                        {
                                            "code": "network_timeout",
                                            "message": "GitHub request failed or timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            }
        ]

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            "Q1: Flask 的 app.config 如何工作？\n\n证据详情：源码 flask/config.py ...",
            tool_completed_buffer,
        )

        self.assertNotIn("flask/config.py", content)
        self.assertIn("GitHub 仓库读取失败", content)
        self.assertIn("network_timeout", content)

    def test_keeps_assistant_content_when_github_repo_tool_succeeds(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=True,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "success",
                                    "data": {"interview_questions": {"questions": []}},
                                }
                            ),
                        ),
                    },
                )()
            }
        ]

        original = "Q1: 这是基于工具成功结果的总结。"

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            original,
            tool_completed_buffer,
        )

        self.assertEqual(content, original)

    def test_keeps_assistant_content_when_later_github_repo_tool_succeeds(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "error",
                                    "errors": [
                                        {
                                            "code": "network_timeout",
                                            "message": "GitHub request failed or timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            },
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_2",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=True,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "success",
                                    "data": {
                                        "interview_questions": {
                                            "questions": [
                                                {
                                                    "id": "q1",
                                                    "question": "Explain the repository architecture.",
                                                    "evidence_details": [
                                                        {"source_path": "src/requests/api.py"}
                                                    ],
                                                }
                                            ]
                                        }
                                    },
                                }
                            ),
                        ),
                    },
                )()
            },
        ]

        original = "已生成基于仓库证据的 4 道面试题。"

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            original,
            tool_completed_buffer,
        )

        self.assertEqual(content, original)

    def test_keeps_partial_success_when_github_repo_tool_generated_grounded_questions(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=True,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "partial",
                                    "warnings": [
                                        {
                                            "code": "network_timeout",
                                            "message": "GitHub request failed or timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                    "data": {
                                        "interview_questions": [
                                            {
                                                "id": "Q1",
                                                "question": "Explain the repository architecture.",
                                                "source_paths": ["src/index.ts"],
                                                "evidence_refs": ["src:src/index.ts#snippet-1"],
                                                "evidence_details": [
                                                    {
                                                        "source_path": "src/index.ts",
                                                        "evidence_id": "src:src/index.ts#snippet-1",
                                                    }
                                                ],
                                            }
                                        ],
                                        "question_generation_summary": {
                                            "generated_count": 1,
                                            "has_source_evidence": True,
                                            "has_evidence_details": True,
                                        },
                                    },
                                }
                            ),
                        ),
                    },
                )()
            }
        ]

        original = "Q1: Explain the repository architecture.\n\n证据详情：src/index.ts"

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            original,
            tool_completed_buffer,
        )

        self.assertEqual(content, original)

    def test_later_partial_grounded_success_overrides_earlier_github_failure(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "error",
                                    "errors": [
                                        {
                                            "code": "network_timeout",
                                            "message": "GitHub request failed or timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            },
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_2",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=True,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "partial",
                                    "warnings": [
                                        {
                                            "code": "network_timeout",
                                            "message": "src/index.ts: GitHub request timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                    "data": {
                                        "interview_questions": [
                                            {
                                                "id": "Q1",
                                                "question": "Explain the repository architecture.",
                                                "source_paths": ["src/index.ts"],
                                                "evidence_refs": ["src:src/index.ts#snippet-1"],
                                                "evidence_details": [
                                                    {
                                                        "source_path": "src/index.ts",
                                                        "evidence_id": "src:src/index.ts#snippet-1",
                                                    }
                                                ],
                                            }
                                        ],
                                        "question_generation_summary": {
                                            "generated_count": 1,
                                            "has_source_evidence": True,
                                            "has_evidence_details": True,
                                        },
                                    },
                                }
                            ),
                        ),
                    },
                )()
            },
        ]

        original = "Q1: Explain the repository architecture.\n\n证据详情：src/index.ts"

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            original,
            tool_completed_buffer,
        )

        self.assertEqual(content, original)

    def test_partial_payload_success_does_not_override_earlier_github_failure(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "error",
                                    "errors": [
                                        {
                                            "code": "network_timeout",
                                            "message": "GitHub request failed or timed out.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            },
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_2",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=True,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "partial",
                                    "data": {
                                        "interview_questions": [
                                            {"question": "Should not be treated as success"}
                                        ]
                                    },
                                    "errors": [
                                        {
                                            "code": "github_request_failed",
                                            "message": "Question generation only partially completed.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            },
        ]

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            "Q1: 这是不应保留的 partial payload 内容。",
            tool_completed_buffer,
        )

        self.assertIn("GitHub 仓库读取失败", content)
        self.assertIn("network_timeout", content)

    def test_replaces_assistant_content_when_failed_github_tool_returns_partial_status(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "github_repo_interview_prep",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "github_repo_interview_prep",
                                    "status": "partial",
                                    "data": {
                                        "interview_questions": [
                                            {"question": "Should not be trusted"}
                                        ]
                                    },
                                    "errors": [
                                        {
                                            "code": "github_request_failed",
                                            "message": "Question generation failed after partial reads.",
                                            "retryable": True,
                                        }
                                    ],
                                }
                            ),
                        ),
                    },
                )()
            }
        ]

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            "Q1: 这是不应保存的 partial 失败内容。\n\n证据详情：src/app.py ...",
            tool_completed_buffer,
        )

        self.assertNotIn("src/app.py", content)
        self.assertIn("GitHub 仓库读取失败", content)
        self.assertIn("github_request_failed", content)

    def test_keeps_assistant_content_for_other_failed_tools(self):
        tool_completed_buffer = [
            {
                "context": type(
                    "Context",
                    (),
                    {
                        "tool_call": {
                            "id": "call_1",
                            "function_name": "web_search_tool",
                        },
                        "result": ToolResult(
                            success=False,
                            output=json.dumps(
                                {
                                    "tool": "web_search_tool",
                                    "status": "error",
                                    "errors": [{"code": "timeout"}],
                                }
                            ),
                        ),
                    },
                )()
            }
        ]

        original = "普通回答不应被 GitHub Repo Interview Prep 边界影响。"

        content = ResponseProcessor._guard_content_for_failed_grounded_tools(
            original,
            tool_completed_buffer,
        )

        self.assertEqual(content, original)


if __name__ == "__main__":
    unittest.main()
