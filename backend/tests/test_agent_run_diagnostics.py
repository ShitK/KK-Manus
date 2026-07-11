import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from agent import api as agent_api
from agent.api import build_agent_run_diagnostics


class FakeQuery:
    def __init__(self, table_name, data_by_table):
        self.table_name = table_name
        self.data_by_table = data_by_table
        self.filters = []
        self.limit_value = None

    def select(self, *args):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    async def execute(self):
        rows = list(self.data_by_table.get(self.table_name, []))
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return SimpleNamespace(data=rows)


class FakeClient:
    def __init__(self, data_by_table):
        self.data_by_table = data_by_table

    def table(self, table_name):
        return FakeQuery(table_name, self.data_by_table)

    def schema(self, _schema_name):
        return self


class FakeRedis:
    async def llen(self, key):
        self.last_llen = key
        return 1

    async def scan_iter(self, match=None, count=None):
        self.last_scan = (match, count)
        yield "active_run:instance-1:run-123"


class FakeRedisFailing:
    async def llen(self, key):
        raise RuntimeError("redis unavailable")

    async def scan_iter(self, match=None, count=None):
        raise RuntimeError("redis unavailable")


class FakeStopRedis:
    def __init__(self):
        self.published = []
        self.lrange_key = None

    async def lrange(self, key, start, end):
        self.lrange_key = (key, start, end)
        return [json.dumps({"status": "assistant_response"})]

    async def publish(self, channel, message):
        self.published.append((channel, message))

    async def keys(self, pattern):
        self.keys_pattern = pattern
        return ["active_run:instance-1:run-123"]


class FakeStopRedisPublishFailing(FakeStopRedis):
    async def publish(self, channel, message):
        raise RuntimeError("publish failed")


class FakeStopRedisKeysFailing(FakeStopRedis):
    async def keys(self, pattern):
        self.keys_pattern = pattern
        raise RuntimeError("keys failed")


class FakeStopDB:
    @property
    async def client(self):
        return object()


class AgentRunDiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_builds_sanitized_diagnostics_for_owned_run(self):
        client = FakeClient(
            {
                "agent_runs": [
                    {
                        "id": 1,
                        "agent_run_id": "run-123",
                        "thread_id": "thread-123",
                        "agent_id": "agent-123",
                        "agent_version_id": None,
                        "status": "running",
                        "started_at": "2026-06-28T00:00:00",
                        "completed_at": None,
                        "created_at": "2026-06-28T00:00:00",
                        "updated_at": "2026-06-28T00:00:01",
                        "error": "Traceback (most recent call last): File /Users/kk/KK-Manus/backend/.env api_key=secret-value",
                        "metadata": json.dumps(
                            {
                                "model_name": "deepseek/deepseek-chat",
                                "debug_log": "Authorization: Bearer raw-token",
                                "last_error": "database failed at postgres://user:pass@host/db",
                                "llm_config": {
                                    "api_key": "secret-value",
                                    "connection_string": "postgres://secret",
                                },
                            }
                        ),
                    }
                ],
                "threads": [
                    {
                        "thread_id": "thread-123",
                        "project_id": "project-123",
                        "account_id": "user-123",
                        "name": "Demo Thread",
                    }
                ],
                "messages": [
                    {
                        "message_id": "message-1",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "你好，我是 KKManus。 api_key=secret-value " * 20,
                        "metadata": {
                            "thread_run_id": "run-123",
                            "credential": "hidden",
                            "debug": "api_key=raw-key",
                        },
                        "created_at": "2026-06-28T00:00:02",
                    }
                ],
                "events": [
                    {
                        "id": "event-1",
                        "session_id": "thread-123",
                        "author": "user",
                        "content": {"parts": [{"text": "你是谁"}]},
                        "timestamp": "2026-06-28T00:00:01",
                    }
                ],
            }
        )

        diagnostics = await build_agent_run_diagnostics(
            client,
            FakeRedis(),
            "run-123",
            "user-123",
        )

        self.assertEqual(diagnostics["agent_run"]["agent_run_id"], "run-123")
        self.assertEqual(diagnostics["agent_run"]["error"], "Internal error. Full traceback is available in backend logs.")
        self.assertEqual(diagnostics["agent_run"]["metadata"]["model_name"], "deepseek/deepseek-chat")
        self.assertEqual(diagnostics["agent_run"]["metadata"]["debug_log"], "Authorization: Bearer [REDACTED]")
        self.assertEqual(diagnostics["agent_run"]["metadata"]["last_error"], "database failed at [REDACTED]")
        self.assertEqual(diagnostics["agent_run"]["metadata"]["llm_config"]["api_key"], "[REDACTED]")
        self.assertEqual(diagnostics["agent_run"]["metadata"]["llm_config"]["connection_string"], "[REDACTED]")
        self.assertEqual(diagnostics["thread"]["thread_id"], "thread-123")
        self.assertEqual(diagnostics["messages"]["total"], 1)
        self.assertLessEqual(len(diagnostics["messages"]["recent"][0]["content_preview"]), 220)
        self.assertNotIn("secret-value", diagnostics["messages"]["recent"][0]["content_preview"])
        self.assertEqual(diagnostics["messages"]["recent"][0]["metadata"]["credential"], "[REDACTED]")
        self.assertEqual(diagnostics["messages"]["recent"][0]["metadata"]["debug"], "api_key=[REDACTED]")
        self.assertEqual(diagnostics["events"]["total"], 1)
        self.assertEqual(diagnostics["redis"]["response_count"], 1)
        self.assertEqual(diagnostics["redis"]["active_instance_keys"], ["active_run:instance-1:run-123"])

    async def test_rejects_diagnostics_for_non_owner_run(self):
        client = FakeClient(
            {
                "agent_runs": [
                    {
                        "id": 1,
                        "agent_run_id": "run-123",
                        "thread_id": "thread-123",
                        "status": "running",
                    }
                ],
                "threads": [
                    {
                        "thread_id": "thread-123",
                        "account_id": "owner-user",
                    }
                ],
            }
        )

        with patch("agent.api.verify_thread_access", side_effect=HTTPException(status_code=403, detail="Forbidden")):
            with self.assertRaises(HTTPException) as context:
                await build_agent_run_diagnostics(client, FakeRedis(), "run-123", "other-user")

        self.assertEqual(context.exception.status_code, 403)

    async def test_returns_404_for_missing_run(self):
        client = FakeClient({"agent_runs": [], "threads": []})

        with self.assertRaises(HTTPException) as context:
            await build_agent_run_diagnostics(client, FakeRedis(), "missing-run", "user-123")

        self.assertEqual(context.exception.status_code, 404)

    async def test_degrades_gracefully_when_redis_fails(self):
        client = FakeClient(
            {
                "agent_runs": [
                    {
                        "id": 1,
                        "agent_run_id": "run-123",
                        "thread_id": "thread-123",
                        "status": "running",
                    }
                ],
                "threads": [
                    {
                        "thread_id": "thread-123",
                        "account_id": "user-123",
                    }
                ],
                "messages": [],
                "events": [],
            }
        )

        diagnostics = await build_agent_run_diagnostics(
            client,
            FakeRedisFailing(),
            "run-123",
            "user-123",
        )

        self.assertEqual(diagnostics["redis"]["response_count"], 0)
        self.assertEqual(diagnostics["redis"]["active_instance_keys"], [])


class AgentRunStopTest(unittest.IsolatedAsyncioTestCase):
    async def test_stop_agent_run_updates_status_and_signals_redis(self):
        fake_redis = FakeStopRedis()
        update_status = AsyncMock(return_value=True)
        cleanup_response_list = AsyncMock()

        with patch.object(agent_api, "db", FakeStopDB()):
            with patch.object(agent_api, "redis", fake_redis):
                with patch.object(agent_api, "update_agent_run_status", update_status):
                    with patch.object(agent_api, "_cleanup_redis_response_list", cleanup_response_list):
                        await agent_api.stop_agent_run("run-123")

        update_status.assert_awaited_once()
        update_args = update_status.await_args.args
        self.assertEqual(update_args[1], "run-123")
        self.assertEqual(update_args[2], "stopped")
        self.assertIsNone(fake_redis.lrange_key)
        self.assertIn(("agent_run:run-123:control", "STOP"), fake_redis.published)
        self.assertIn(("agent_run:run-123:control:instance-1", "STOP"), fake_redis.published)
        cleanup_response_list.assert_awaited_once_with("run-123")

    async def test_stop_agent_run_marks_failed_when_error_message_provided(self):
        update_status = AsyncMock(return_value=True)

        with patch.object(agent_api, "db", FakeStopDB()):
            with patch.object(agent_api, "redis", FakeStopRedis()):
                with patch.object(agent_api, "update_agent_run_status", update_status):
                    with patch.object(agent_api, "_cleanup_redis_response_list", AsyncMock()):
                        await agent_api.stop_agent_run("run-123", error_message="worker shutdown")

        update_args = update_status.await_args.args
        update_kwargs = update_status.await_args.kwargs
        self.assertEqual(update_args[1], "run-123")
        self.assertEqual(update_args[2], "failed")
        self.assertEqual(update_kwargs["error"], "worker shutdown")

    async def test_stop_agent_run_raises_when_db_update_fails(self):
        update_status = AsyncMock(return_value=False)

        with patch.object(agent_api, "db", FakeStopDB()):
            with patch.object(agent_api, "redis", FakeStopRedis()):
                with patch.object(agent_api, "update_agent_run_status", update_status):
                    with patch.object(agent_api, "_cleanup_redis_response_list", AsyncMock()):
                        with self.assertRaises(HTTPException) as context:
                            await agent_api.stop_agent_run("run-123")

        self.assertEqual(context.exception.status_code, 500)

    async def test_stop_agent_run_continues_when_redis_publish_fails(self):
        cleanup_response_list = AsyncMock()

        with patch.object(agent_api, "db", FakeStopDB()):
            with patch.object(agent_api, "redis", FakeStopRedisPublishFailing()):
                with patch.object(agent_api, "update_agent_run_status", AsyncMock(return_value=True)):
                    with patch.object(agent_api, "_cleanup_redis_response_list", cleanup_response_list):
                        await agent_api.stop_agent_run("run-123")

        cleanup_response_list.assert_awaited_once_with("run-123")

    async def test_stop_agent_run_cleans_response_list_when_instance_lookup_fails(self):
        cleanup_response_list = AsyncMock()

        with patch.object(agent_api, "db", FakeStopDB()):
            with patch.object(agent_api, "redis", FakeStopRedisKeysFailing()):
                with patch.object(agent_api, "update_agent_run_status", AsyncMock(return_value=True)):
                    with patch.object(agent_api, "_cleanup_redis_response_list", cleanup_response_list):
                        await agent_api.stop_agent_run("run-123")

        cleanup_response_list.assert_awaited_once_with("run-123")

    async def test_content_previews_redact_structured_and_text_secrets(self):
        client = FakeClient(
            {
                "agent_runs": [
                    {
                        "id": 1,
                        "agent_run_id": "run-123",
                        "thread_id": "thread-123",
                        "status": "running",
                    }
                ],
                "threads": [
                    {
                        "thread_id": "thread-123",
                        "account_id": "user-123",
                    }
                ],
                "messages": [
                    {
                        "message_id": "message-json",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": {
                            "tool_result": {
                                "api_key": "raw-api-key",
                                "database": {
                                    "connection_string": "postgres://user:pass@localhost/db",
                                },
                            }
                        },
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:03",
                    },
                    {
                        "message_id": "message-auth",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "Authorization: Bearer raw-token",
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:02",
                    },
                    {
                        "message_id": "message-auth-token",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "Authorization: Token raw-authorization-token",
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:02",
                    },
                    {
                        "message_id": "message-auth-apikey",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "Authorization: ApiKey raw-authorization-key",
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:02",
                    },
                    {
                        "message_id": "message-auth-query",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "authorization=Bearer raw-query-token",
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:02",
                    },
                    {
                        "message_id": "message-dsn",
                        "thread_id": "thread-123",
                        "type": "assistant",
                        "content": "database failed at postgres://user:pass@localhost/db",
                        "metadata": {},
                        "created_at": "2026-06-28T00:00:01",
                    },
                ],
                "events": [
                    {
                        "id": "event-json",
                        "session_id": "thread-123",
                        "author": "model",
                        "content": json.dumps(
                            {
                                "diagnostics": {
                                    "api_key": "event-api-key",
                                    "connection_string": "postgres://event:secret@localhost/db",
                                }
                            }
                        ),
                        "timestamp": "2026-06-28T00:00:04",
                    }
                ],
            }
        )

        diagnostics = await build_agent_run_diagnostics(
            client,
            FakeRedis(),
            "run-123",
            "user-123",
        )

        previews = [
            message["content_preview"]
            for message in diagnostics["messages"]["recent"]
        ] + [
            event["content_preview"]
            for event in diagnostics["events"]["recent"]
        ]
        combined_preview = " ".join(previews)

        self.assertIn("[REDACTED]", combined_preview)
        self.assertNotIn("raw-api-key", combined_preview)
        self.assertNotIn("raw-token", combined_preview)
        self.assertNotIn("raw-authorization-token", combined_preview)
        self.assertNotIn("raw-authorization-key", combined_preview)
        self.assertNotIn("raw-query-token", combined_preview)
        self.assertNotIn("user:pass", combined_preview)
        self.assertNotIn("event-api-key", combined_preview)
        self.assertNotIn("event:secret", combined_preview)


if __name__ == "__main__":
    unittest.main()
