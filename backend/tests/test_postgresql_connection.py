import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from services.postgresql import DBConnection


class _FakePool:
    def __init__(self, closing=False):
        self._closing = closing

    def is_closing(self):
        return self._closing


class DBConnectionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        DBConnection._instance = None

    async def asyncTearDown(self):
        DBConnection._instance = None

    async def test_initialize_recreates_pool_bound_to_a_different_event_loop(self):
        connection = DBConnection()
        connection._initialized = True
        connection._pool = _FakePool()
        connection._loop = object()

        new_pool = _FakePool()
        with patch("services.postgresql.asyncpg.create_pool", new=AsyncMock(return_value=new_pool)) as create_pool:
            await connection.initialize()

        create_pool.assert_awaited_once()
        self.assertIs(connection._pool, new_pool)
        self.assertIs(connection._loop, asyncio.get_running_loop())

    async def test_initialize_recreates_closing_pool(self):
        connection = DBConnection()
        connection._initialized = True
        connection._pool = _FakePool(closing=True)
        connection._loop = asyncio.get_running_loop()

        new_pool = _FakePool()
        with patch("services.postgresql.asyncpg.create_pool", new=AsyncMock(return_value=new_pool)) as create_pool:
            await connection.initialize()

        create_pool.assert_awaited_once()
        self.assertIs(connection._pool, new_pool)

    async def test_client_recreates_stale_pool_before_returning_client(self):
        connection = DBConnection()
        connection._initialized = True
        connection._pool = _FakePool()
        connection._loop = object()

        new_pool = _FakePool()
        with patch("services.postgresql.asyncpg.create_pool", new=AsyncMock(return_value=new_pool)) as create_pool:
            client = await connection.client

        create_pool.assert_awaited_once()
        self.assertIs(client.pool, new_pool)

    async def test_concurrent_client_initializes_pool_once(self):
        connection = DBConnection()
        new_pool = _FakePool()
        create_started = asyncio.Event()

        async def create_pool(*args, **kwargs):
            create_started.set()
            await asyncio.sleep(0)
            return new_pool

        with patch("services.postgresql.asyncpg.create_pool", new=AsyncMock(side_effect=create_pool)) as create_pool_mock:
            clients = await asyncio.gather(connection.client, connection.client)

        create_pool_mock.assert_awaited_once()
        self.assertIs(clients[0].pool, new_pool)
        self.assertIs(clients[1].pool, new_pool)
        self.assertTrue(create_started.is_set())

    async def test_initialize_resets_state_when_pool_creation_fails(self):
        connection = DBConnection()
        connection._initialized = True
        connection._pool = _FakePool()
        connection._loop = object()

        with patch("services.postgresql.asyncpg.create_pool", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(RuntimeError):
                await connection.initialize()

        self.assertFalse(connection._initialized)
        self.assertIsNone(connection._pool)
        self.assertIsNone(connection._loop)


if __name__ == "__main__":
    unittest.main()
