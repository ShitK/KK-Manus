import unittest

from agentpress.response_processor import ResponseProcessor
from agentpress.tool_registry import ToolRegistry


class _FakeTrace:
    def event(self, *args, **kwargs):
        return None


class _FakeUsageMetadata:
    prompt_token_count = 10
    candidates_token_count = 5
    total_token_count = 15


class _FakePart:
    def __init__(self, text):
        self.text = text


class _FakeContent:
    def __init__(self, text):
        self.parts = [_FakePart(text)]


class _FakeFinalTextEvent:
    partial = False
    usage_metadata = _FakeUsageMetadata()
    timestamp = 1234567890
    error_code = None
    turn_complete = True
    actions = None
    long_running_tool_ids = []

    def __init__(self, text):
        self.content = _FakeContent(text)

    def is_final_response(self):
        return True


async def _single_event_stream(event):
    yield event


async def _capture_add_message(saved_messages, **kwargs):
    message = {
        "message_id": f"msg-{len(saved_messages) + 1}",
        "thread_id": kwargs["thread_id"],
        "type": kwargs["type"],
        "content": kwargs["content"],
        "is_llm_message": kwargs.get("is_llm_message", False),
        "metadata": kwargs.get("metadata") or {},
        "created_at": "2026-07-07T00:00:00+00:00",
        "updated_at": "2026-07-07T00:00:00+00:00",
    }
    saved_messages.append(message)
    return message


class ResponseProcessorFinalChunkTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_final_complete_text_when_no_prior_stream_chunks(self):
        saved_messages = []
        processor = ResponseProcessor(
            tool_registry=ToolRegistry(),
            add_message_callback=lambda **kwargs: _capture_add_message(
                saved_messages,
                **kwargs,
            ),
            trace=_FakeTrace(),
        )

        outputs = [
            chunk
            async for chunk in processor.process_adk_streaming_response(
                _single_event_stream(
                    _FakeFinalTextEvent("这是只出现在 final chunk 里的点评。")
                ),
                thread_id="thread-1",
                prompt_messages=[],
                llm_model="test-model",
            )
        ]

        assistant_messages = [
            message for message in saved_messages if message["type"] == "assistant"
        ]

        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(
            assistant_messages[0]["content"]["content"],
            "这是只出现在 final chunk 里的点评。",
        )
        self.assertTrue(any(chunk.get("type") == "assistant" for chunk in outputs))


class ResponseProcessorStreamDedupTests(unittest.TestCase):
    def test_keeps_normal_delta_chunk(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta(
                "好的，",
                "我来调用工具。",
            ),
            "我来调用工具。",
        )

    def test_converts_cumulative_chunk_to_suffix_delta(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta(
                "好的，重新开始一次完整的练习。",
                "好的，重新开始一次完整的练习。先调用 github_repo_interview_prep。",
            ),
            "先调用 github_repo_interview_prep。",
        )

    def test_drops_sentence_level_duplicate_chunk(self):
        duplicate = "好的，重新开始一次完整的练习。先调用 github_repo_interview_prep 生成 evidence-backed questions。"
        self.assertEqual(
            ResponseProcessor._normalize_text_delta(
                duplicate,
                duplicate,
            ),
            "",
        )

    def test_drops_long_prefix_duplicate_chunk(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta(
                "好的，重新开始一次完整的练习。先调用工具。",
                "好的，重新开始一次完整的练习。",
            ),
            "",
        )

    def test_does_not_dedupe_short_repeated_text_to_avoid_over_filtering(self):
        # Short repeated text is intentionally kept to avoid suppressing valid prose.
        self.assertEqual(
            ResponseProcessor._normalize_text_delta("哈哈", "哈"),
            "哈",
        )

    def test_coerces_list_chunk_before_normalizing(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta(
                "问题已生成。",
                ["问题已生成。", "现在选择 Q1。"],
            ),
            "现在选择 Q1。",
        )

    def test_empty_chunk_returns_empty_delta(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta("已有内容", ""),
            "",
        )

    def test_none_chunk_returns_empty_delta(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta("已有内容", None),
            "",
        )

    def test_empty_list_chunk_returns_empty_delta(self):
        self.assertEqual(
            ResponseProcessor._normalize_text_delta("已有内容", []),
            "",
        )


if __name__ == "__main__":
    unittest.main()
