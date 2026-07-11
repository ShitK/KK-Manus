import unittest

from agent.api import delete_thread_records


class FakeDeleteQuery:
    def __init__(self, table_name, operations):
        self.table_name = table_name
        self.operations = operations
        self.column = None
        self.value = None

    def eq(self, column, value):
        self.column = column
        self.value = value
        return self

    async def delete(self):
        self.operations.append((self.table_name, self.column, self.value))
        return None


class FakeClient:
    def __init__(self):
        self.operations = []

    def table(self, table_name):
        return FakeDeleteQuery(table_name, self.operations)


class ThreadDeletionTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_thread_records_removes_related_rows_before_thread(self):
        client = FakeClient()

        await delete_thread_records(client, "thread-123")

        self.assertEqual(
            client.operations,
            [
                ("events", "session_id", "thread-123"),
                ("messages", "thread_id", "thread-123"),
                ("agent_runs", "thread_id", "thread-123"),
                ("sessions", "id", "thread-123"),
                ("threads", "thread_id", "thread-123"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
