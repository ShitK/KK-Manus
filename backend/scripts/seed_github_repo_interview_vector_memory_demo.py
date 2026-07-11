"""Seed and verify a reproducible miniclawd semantic-memory demo dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from agent.tools.github_repo_interview_vector_memory import (
    FORBIDDEN_MARKERS,
    LiteLLMVectorMemoryEmbeddingProvider,
    VectorMemoryConfig,
    cleanup_demo_vector_memories,
    retrieve_vector_memories,
    upsert_demo_vector_memory,
)
from services.postgresql import DBConnection


DEFAULT_DATASET = Path("tests/fixtures/miniclawd_vector_memory_demo_seed.json")
EXPECTED_REPOSITORY = "ShitK/miniclawd"
EXPECTED_COMMIT = "2d65665"


def load_dataset(
    path: Path,
    *,
    expected_repository: str = EXPECTED_REPOSITORY,
    expected_commit: str = EXPECTED_COMMIT,
) -> Dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("repository") != expected_repository or payload.get("commit") != expected_commit:
        raise ValueError("miniclawd demo source repository or commit drifted")
    fixture_id = str(payload.get("fixture_id") or "").strip()
    memories = payload.get("memories")
    queries = payload.get("showcase_queries")
    if not fixture_id or not isinstance(memories, list) or len(memories) < 8:
        raise ValueError("demo dataset requires fixture id and at least eight memories")
    if not isinstance(queries, list) or len(queries) < 4:
        raise ValueError("demo dataset requires at least four showcase queries")

    memory_ids = set()
    for memory in memories:
        memory_id = str(memory.get("id") or "").strip()
        text = str(memory.get("text") or "").strip()
        if not memory_id or memory_id in memory_ids:
            raise ValueError("demo memory ids must be non-empty and unique")
        if not 80 <= len(text) <= 600:
            raise ValueError(f"demo memory {memory_id} must contain 80-600 characters")
        lowered = text.casefold()
        if any(marker.casefold() in lowered for marker in FORBIDDEN_MARKERS):
            raise ValueError(f"demo memory {memory_id} contains a forbidden marker")
        memory_ids.add(memory_id)
    for query in queries:
        expected = set(query.get("expected_memory_ids") or [])
        if not str(query.get("id") or "").strip() or not str(query.get("query") or "").strip():
            raise ValueError("showcase query requires id and query")
        if not expected or not expected.issubset(memory_ids):
            raise ValueError("showcase query references an unknown memory")
    return payload


async def _preflight(client: Any) -> None:
    async with client.pool.acquire() as connection:
        available = await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'vector')"
        )
        installed = await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
        )
    if not available:
        raise RuntimeError(
            "Current PostgreSQL does not provide pgvector. Keep VECTOR_MEMORY_ENABLED=false "
            "and switch to a pgvector-capable database before apply/verify."
        )
    if not installed:
        raise RuntimeError("pgvector is available but the migration has not been applied")


async def _account_id_for_thread(client: Any, thread_id: str) -> str:
    async with client.pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT account_id FROM threads WHERE thread_id = $1 LIMIT 1",
            thread_id,
        )
    if not row or not row.get("account_id"):
        raise RuntimeError("thread was not found or has no authenticated owner")
    return str(row["account_id"])


def _enabled_config() -> VectorMemoryConfig:
    configured = VectorMemoryConfig.from_env()
    return VectorMemoryConfig(
        enabled=True,
        model=configured.model,
        api_base=configured.api_base,
        match_threshold=configured.match_threshold,
        match_count=configured.match_count,
        timeout_seconds=configured.timeout_seconds,
    )


async def run(mode: str, dataset: Dict[str, Any], thread_id: Optional[str]) -> Dict[str, Any]:
    if mode == "dry-run":
        return {
            "mode": mode,
            "fixture_id": dataset["fixture_id"],
            "repository": dataset["repository"],
            "commit": dataset["commit"],
            "memory_count": len(dataset["memories"]),
            "query_count": len(dataset["showcase_queries"]),
            "database_writes": 0,
        }
    if not thread_id:
        raise ValueError("--thread-id is required for apply, verify, and cleanup")

    load_dotenv(override=True)
    client = await DBConnection().client
    await _preflight(client)
    user_id = await _account_id_for_thread(client, thread_id)
    config = _enabled_config()
    provider = LiteLLMVectorMemoryEmbeddingProvider(config)

    if mode == "cleanup":
        count = await cleanup_demo_vector_memories(
            client,
            user_id=user_id,
            fixture_id=dataset["fixture_id"],
        )
        return {"mode": mode, "deleted_count": count, "fixture_id": dataset["fixture_id"]}

    if mode == "apply":
        saved = []
        for memory in dataset["memories"]:
            row = await upsert_demo_vector_memory(
                client,
                provider,
                config,
                user_id=user_id,
                fixture_id=dataset["fixture_id"],
                memory_id=memory["id"],
                memory_text=memory["text"],
                target_role=memory.get("target_role"),
                category=memory.get("category"),
                source_thread_id=thread_id,
            )
            saved.append(row["id"])
        return {"mode": mode, "saved_count": len(saved), "fixture_id": dataset["fixture_id"]}

    results = []
    for query in dataset["showcase_queries"]:
        retrieval = await retrieve_vector_memories(
            client,
            provider,
            config,
            user_id=user_id,
            query_text=query["query"],
            target_role=query.get("target_role"),
            category=query.get("category"),
        )
        actual_ids = {
            str((item.get("provenance") or {}).get("memory_id") or "")
            for item in retrieval.get("context") or []
        }
        expected_ids = set(query["expected_memory_ids"])
        results.append(
            {
                "id": query["id"],
                "status": retrieval["status"],
                "expected_memory_ids": sorted(expected_ids),
                "actual_memory_ids": sorted(item for item in actual_ids if item),
                "passed": retrieval["status"] == "matched" and expected_ids.issubset(actual_ids),
            }
        )
    return {
        "mode": mode,
        "fixture_id": dataset["fixture_id"],
        "passed": all(item["passed"] for item in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["dry-run", "apply", "verify", "cleanup"])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--thread-id")
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    result = asyncio.run(run(args.mode, dataset, args.thread_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
