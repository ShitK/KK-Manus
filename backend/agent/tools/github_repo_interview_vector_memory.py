"""User-confirmed semantic memory for the GitHub interview workflow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

import litellm


TABLE_NAME = "github_repo_interview_text_memories"
VECTOR_DIMENSIONS = 1024
DEFAULT_EMBEDDING_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MIN_MEMORY_TEXT_LENGTH = 80
MAX_MEMORY_TEXT_LENGTH = 600
MAX_QUERY_LENGTH = 600

FORBIDDEN_MARKERS = (
    "http://",
    "https://",
    "api_key",
    "authorization:",
    "traceback",
    "user_answer",
    "follow_up_answer",
    "raw_answer",
    "/users/",
)

SAFE_PRIVACY = {
    "includes_user_answer": False,
    "includes_follow_up_answer": False,
    "includes_repo_evidence_text": False,
}


class VectorMemoryEmbeddingError(RuntimeError):
    code = "vector_memory_embedding_unavailable"


class VectorMemoryTimeoutError(VectorMemoryEmbeddingError):
    code = "vector_memory_embedding_timeout"


class VectorMemoryMalformedResponseError(VectorMemoryEmbeddingError):
    code = "vector_memory_embedding_malformed"


class VectorMemoryDimensionError(VectorMemoryEmbeddingError):
    code = "vector_memory_embedding_dimension_mismatch"


@dataclass(frozen=True)
class VectorMemoryConfig:
    enabled: bool = False
    model: str = "openai/text-embedding-v4"
    api_base: str = DEFAULT_EMBEDDING_API_BASE
    match_threshold: float = 0.65
    match_count: int = 3
    timeout_seconds: float = 15.0

    @classmethod
    def from_env(cls) -> "VectorMemoryConfig":
        return cls(
            enabled=str(os.getenv("VECTOR_MEMORY_ENABLED", "false")).lower() in {"1", "true", "yes", "on"},
            model=str(os.getenv("VECTOR_MEMORY_EMBEDDING_MODEL", cls.model)).strip() or cls.model,
            api_base=(
                str(os.getenv("VECTOR_MEMORY_EMBEDDING_API_BASE", cls.api_base)).strip()
                or cls.api_base
            ),
            match_threshold=max(0.0, min(1.0, float(os.getenv("VECTOR_MEMORY_MATCH_THRESHOLD", "0.65")))),
            match_count=max(1, min(5, int(os.getenv("VECTOR_MEMORY_MATCH_COUNT", "3")))),
            timeout_seconds=max(1.0, min(60.0, float(os.getenv("VECTOR_MEMORY_EMBEDDING_TIMEOUT_SECONDS", "15")))),
        )


def _text(value: Any, limit: int = MAX_MEMORY_TEXT_LENGTH) -> str:
    return str(value or "").strip()[:limit]


def _safe_text(value: Any, limit: int) -> str:
    text = _text(value, limit)
    lowered = text.casefold()
    if not text or any(marker.casefold() in lowered for marker in FORBIDDEN_MARKERS):
        return ""
    return text


def content_hash(memory_text: str) -> str:
    return hashlib.sha256(memory_text.strip().casefold().encode("utf-8")).hexdigest()


def build_vector_memory_candidate(
    *,
    session_memory: Dict[str, Any],
    source_thread_id: str,
    source_agent_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    state = session_memory if isinstance(session_memory, dict) else {}
    target_role = _safe_text(state.get("target_role"), 80)
    category = _safe_text(state.get("current_practice_category"), 80)
    suggestion = _safe_text(state.get("next_practice_suggestion"), 240)
    question_ids = [
        _safe_text(item, 16)
        for item in (state.get("answered_question_ids") or [])
        if _safe_text(item, 16)
    ][:20]
    thread_id = _safe_text(source_thread_id, 128)
    if not thread_id or not suggestion:
        return {}

    parts = ["GitHub 仓库面试练习经验："]
    if target_role:
        parts.append(f"目标岗位为 {target_role}。")
    if category:
        parts.append(f"本轮重点为 {category}。")
    if question_ids:
        parts.append(f"已练习题目包括 {', '.join(question_ids)}。")
    parts.append(f"后续建议：{suggestion}")
    parts.append("该记忆只保留脱敏后的练习方向与改进建议，不包含回答原文或仓库证据原文。")
    memory_text = "".join(parts)[:MAX_MEMORY_TEXT_LENGTH]
    if len(memory_text) < MIN_MEMORY_TEXT_LENGTH or any(
        marker.casefold() in memory_text.casefold() for marker in FORBIDDEN_MARKERS
    ):
        return {}

    digest = content_hash(memory_text)
    candidate: Dict[str, Any] = {
        "id": f"text-memory-candidate:{digest[:16]}",
        "type": "practice_experience_summary",
        "text": memory_text,
        "content_hash": digest,
        "target_role": target_role or None,
        "category": category or None,
        "source_thread_id": thread_id,
        "source_stage": "summarize",
        "requires_user_confirmation": True,
        "persisted": False,
        "status": "candidate_only",
        "provenance": {"kind": "user_confirmed"},
        "privacy": dict(SAFE_PRIVACY),
    }
    if source_agent_run_id:
        candidate["source_agent_run_id"] = _safe_text(source_agent_run_id, 128)
    return candidate


def sanitize_vector_memory_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("invalid vector memory candidate")
    memory_text = _safe_text(candidate.get("text"), MAX_MEMORY_TEXT_LENGTH)
    if not (MIN_MEMORY_TEXT_LENGTH <= len(memory_text) <= MAX_MEMORY_TEXT_LENGTH):
        raise ValueError("vector memory text length must be between 80 and 600 characters")
    digest = content_hash(memory_text)
    if candidate.get("content_hash") != digest or candidate.get("id") != f"text-memory-candidate:{digest[:16]}":
        raise ValueError("vector memory candidate content hash mismatch")
    if candidate.get("type") != "practice_experience_summary":
        raise ValueError("unsupported vector memory type")
    if candidate.get("privacy") != SAFE_PRIVACY:
        raise ValueError("unsafe vector memory privacy declaration")
    return {
        "id": candidate["id"],
        "type": "practice_experience_summary",
        "text": memory_text,
        "content_hash": digest,
        "target_role": _safe_text(candidate.get("target_role"), 80) or None,
        "category": _safe_text(candidate.get("category"), 80) or None,
        "source_thread_id": _safe_text(candidate.get("source_thread_id"), 128),
        "source_agent_run_id": _safe_text(candidate.get("source_agent_run_id"), 128) or None,
        "source_stage": "summarize",
        "requires_user_confirmation": True,
        "persisted": False,
        "status": "candidate_only",
        "provenance": {"kind": "user_confirmed"},
        "privacy": dict(SAFE_PRIVACY),
    }


class LiteLLMVectorMemoryEmbeddingProvider:
    def __init__(
        self,
        config: VectorMemoryConfig,
        embedding_call: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        self.config = config
        self.embedding_call = embedding_call or litellm.aembedding
        self.uses_default_embedding_call = embedding_call is None

    async def embed_text(self, text: str) -> List[float]:
        api_key = str(os.getenv("DASHSCOPE_API_KEY") or "").strip()
        if self.uses_default_embedding_call and not api_key:
            raise VectorMemoryEmbeddingError("DashScope embedding API key is not configured")
        try:
            response = await self.embedding_call(
                model=self.config.model,
                input=[text],
                encoding_format="float",
                api_base=self.config.api_base,
                **({"api_key": api_key} if api_key else {}),
                timeout=self.config.timeout_seconds,
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise VectorMemoryTimeoutError("embedding request timed out") from exc
        except Exception as exc:
            raise VectorMemoryEmbeddingError("embedding request failed") from exc

        data = response.get("data") if isinstance(response, Mapping) else getattr(response, "data", None)
        if not isinstance(data, list) or not data:
            raise VectorMemoryMalformedResponseError("embedding response has no data")
        item = data[0]
        embedding = item.get("embedding") if isinstance(item, Mapping) else getattr(item, "embedding", None)
        if not isinstance(embedding, list):
            raise VectorMemoryMalformedResponseError("embedding response has no vector")
        if len(embedding) != VECTOR_DIMENSIONS:
            raise VectorMemoryDimensionError("embedding dimension mismatch")
        try:
            vector = [float(value) for value in embedding]
        except (TypeError, ValueError) as exc:
            raise VectorMemoryMalformedResponseError("embedding contains non-numeric values") from exc
        if not all(math.isfinite(value) for value in vector):
            raise VectorMemoryMalformedResponseError("embedding contains non-finite values")
        return vector


def _vector_literal(embedding: List[float]) -> str:
    if len(embedding) != VECTOR_DIMENSIONS or not all(math.isfinite(float(item)) for item in embedding):
        raise VectorMemoryDimensionError("embedding dimension mismatch")
    return "[" + ",".join(format(float(item), ".12g") for item in embedding) + "]"


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def _timestamp(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def _public_memory(row: Mapping[str, Any], similarity: Optional[float] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "id": str(row.get("id") or ""),
        "type": str(row.get("memory_type") or "practice_experience_summary"),
        "text": str(row.get("memory_text") or "")[:MAX_MEMORY_TEXT_LENGTH],
        "target_role": row.get("target_role"),
        "category": row.get("category"),
        "source_thread_id": row.get("source_thread_id"),
        "source_agent_run_id": row.get("source_agent_run_id"),
        "source_stage": str(row.get("source_stage") or "summarize"),
        "provenance": _json_value(row.get("provenance"), {}),
        "privacy": _json_value(row.get("privacy"), dict(SAFE_PRIVACY)),
        "status": str(row.get("status") or "active"),
        "persisted": True,
        "requires_user_confirmation": False,
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
    }
    if similarity is not None:
        result["similarity"] = max(0.0, min(1.0, float(similarity)))
    return result


def sanitize_vector_memory_context(value: Any, limit: int = 3) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    context: List[Dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict) or raw.get("persisted") is not True:
            continue
        memory_text = _safe_text(raw.get("text"), MAX_MEMORY_TEXT_LENGTH)
        if not memory_text:
            continue
        try:
            similarity = max(0.0, min(1.0, float(raw.get("similarity"))))
        except (TypeError, ValueError):
            continue
        item = {
            "id": _safe_text(raw.get("id"), 128),
            "text": memory_text,
            "similarity": similarity,
            "target_role": _safe_text(raw.get("target_role"), 80) or None,
            "category": _safe_text(raw.get("category"), 80) or None,
            "source_stage": _safe_text(raw.get("source_stage"), 40) or "summarize",
            "persisted": True,
            "provenance": {
                "kind": (
                    "demo_fixture"
                    if isinstance(raw.get("provenance"), dict)
                    and raw["provenance"].get("kind") == "demo_fixture"
                    else "user_confirmed"
                )
            },
        }
        if item["id"]:
            context.append(item)
        if len(context) >= max(0, min(limit, 3)):
            break
    return context


def sanitize_vector_memory_retrieval(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    status = str(raw.get("status") or "disabled")
    if status not in {"disabled", "matched", "no_match", "embedding_error", "retrieval_error"}:
        status = "retrieval_error"
    diagnostics = raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {}
    def safe_float(raw_value: Any, default: float = 0.0) -> float:
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return default

    def safe_int(raw_value: Any) -> int:
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return 0

    clean = {
        "status": status,
        "query_source": "current_user_input",
        "model": _safe_text(diagnostics.get("model"), 120),
        "threshold": max(0.0, min(1.0, safe_float(diagnostics.get("threshold")))),
        "top_k": max(0, min(3, safe_int(diagnostics.get("top_k")))),
        "candidate_count": max(0, safe_int(diagnostics.get("candidate_count"))),
        "matched_count": max(0, safe_int(diagnostics.get("matched_count"))),
        "applied_count": max(0, min(3, safe_int(diagnostics.get("applied_count")))),
        "filtered_by_threshold": max(0, safe_int(diagnostics.get("filtered_by_threshold"))),
        "filtered_by_topk": max(0, safe_int(diagnostics.get("filtered_by_topk"))),
        "filtered_count": max(0, safe_int(diagnostics.get("filtered_count"))),
        "fallback_used": bool(diagnostics.get("fallback_used")),
    }
    return clean


async def save_vector_memory(
    client: Any,
    provider: LiteLLMVectorMemoryEmbeddingProvider,
    config: VectorMemoryConfig,
    *,
    user_id: str,
    canonical_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    candidate = sanitize_vector_memory_candidate(canonical_candidate)
    embedding = await provider.embed_text(candidate["text"])
    sql = """
        INSERT INTO github_repo_interview_text_memories (
          user_id, memory_type, memory_text, content_hash, embedding, embedding_model,
          target_role, category, source_thread_id, source_agent_run_id, source_stage,
          provenance, privacy
        ) VALUES (
          $1::uuid, $2, $3, $4, $5::text::vector, $6,
          $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb
        )
        ON CONFLICT (user_id, content_hash) WHERE deleted_at IS NULL
        DO UPDATE SET updated_at = NOW(), status = 'active'
        RETURNING id, memory_type, memory_text, target_role, category,
          source_thread_id, source_agent_run_id, source_stage, provenance, privacy,
          status, created_at, updated_at
    """
    async with client.pool.acquire() as connection:
        row = await connection.fetchrow(
            sql,
            user_id,
            candidate["type"],
            candidate["text"],
            candidate["content_hash"],
            _vector_literal(embedding),
            config.model,
            candidate.get("target_role"),
            candidate.get("category"),
            candidate["source_thread_id"],
            candidate.get("source_agent_run_id"),
            "summarize",
            json.dumps(candidate["provenance"]),
            json.dumps(candidate["privacy"]),
        )
    return _public_memory(dict(row))


async def upsert_demo_vector_memory(
    client: Any,
    provider: LiteLLMVectorMemoryEmbeddingProvider,
    config: VectorMemoryConfig,
    *,
    user_id: str,
    fixture_id: str,
    memory_id: str,
    memory_text: str,
    target_role: Optional[str],
    category: Optional[str],
    source_thread_id: str,
) -> Dict[str, Any]:
    safe_text = _safe_text(memory_text, MAX_MEMORY_TEXT_LENGTH)
    if not (MIN_MEMORY_TEXT_LENGTH <= len(safe_text) <= MAX_MEMORY_TEXT_LENGTH):
        raise ValueError("demo memory text length must be between 80 and 600 characters")
    embedding = await provider.embed_text(safe_text)
    digest = content_hash(safe_text)
    provenance = {
        "kind": "demo_fixture",
        "fixture_id": _safe_text(fixture_id, 120),
        "memory_id": _safe_text(memory_id, 120),
    }
    sql = """
        INSERT INTO github_repo_interview_text_memories (
          user_id, memory_type, memory_text, content_hash, embedding, embedding_model,
          target_role, category, source_thread_id, source_stage, provenance, privacy
        ) VALUES (
          $1::uuid, 'practice_experience_summary', $2, $3, $4::text::vector, $5,
          $6, $7, $8, 'summarize', $9::jsonb, $10::jsonb
        )
        ON CONFLICT (user_id, content_hash) WHERE deleted_at IS NULL
        DO UPDATE SET
          embedding = EXCLUDED.embedding,
          embedding_model = EXCLUDED.embedding_model,
          target_role = EXCLUDED.target_role,
          category = EXCLUDED.category,
          source_thread_id = EXCLUDED.source_thread_id,
          provenance = EXCLUDED.provenance,
          privacy = EXCLUDED.privacy,
          status = 'active',
          updated_at = NOW()
        RETURNING id, memory_type, memory_text, target_role, category,
          source_thread_id, source_agent_run_id, source_stage, provenance, privacy,
          status, created_at, updated_at
    """
    async with client.pool.acquire() as connection:
        row = await connection.fetchrow(
            sql,
            user_id,
            safe_text,
            digest,
            _vector_literal(embedding),
            config.model,
            _safe_text(target_role, 80) or None,
            _safe_text(category, 80) or None,
            _safe_text(source_thread_id, 128),
            json.dumps(provenance),
            json.dumps(SAFE_PRIVACY),
        )
    return _public_memory(dict(row))


async def cleanup_demo_vector_memories(
    client: Any,
    *,
    user_id: str,
    fixture_id: str,
) -> int:
    sql = """
        UPDATE github_repo_interview_text_memories
        SET status = 'deleted', deleted_at = NOW(), updated_at = NOW()
        WHERE user_id = $1::uuid
          AND status = 'active'
          AND deleted_at IS NULL
          AND provenance ->> 'kind' = 'demo_fixture'
          AND provenance ->> 'fixture_id' = $2
    """
    async with client.pool.acquire() as connection:
        result = await connection.execute(sql, user_id, _safe_text(fixture_id, 120))
    try:
        return int(str(result).split()[-1])
    except (TypeError, ValueError):
        return 0


async def list_vector_memories(client: Any, *, user_id: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT id, memory_type, memory_text, target_role, category, source_thread_id,
          source_agent_run_id, source_stage, provenance, privacy, status, created_at, updated_at
        FROM github_repo_interview_text_memories
        WHERE user_id = $1::uuid AND status = 'active' AND deleted_at IS NULL
        ORDER BY updated_at DESC, id ASC
    """
    async with client.pool.acquire() as connection:
        rows = await connection.fetch(sql, user_id)
    return [_public_memory(dict(row)) for row in rows]


async def soft_delete_vector_memory(client: Any, *, user_id: str, memory_id: str) -> Dict[str, Any]:
    sql = """
        UPDATE github_repo_interview_text_memories
        SET status = 'deleted', deleted_at = NOW(), updated_at = NOW()
        WHERE id = $1::uuid AND user_id = $2::uuid AND status = 'active' AND deleted_at IS NULL
        RETURNING id, memory_type, memory_text, target_role, category, source_thread_id,
          source_agent_run_id, source_stage, provenance, privacy, status, created_at, updated_at
    """
    async with client.pool.acquire() as connection:
        row = await connection.fetchrow(sql, memory_id, user_id)
    if row is None:
        raise KeyError("vector memory not found")
    return _public_memory(dict(row))


def _diagnostics(config: VectorMemoryConfig) -> Dict[str, Any]:
    return {
        "query_source": "current_user_input",
        "model": config.model,
        "threshold": config.match_threshold,
        "top_k": config.match_count,
        "candidate_count": 0,
        "matched_count": 0,
        "applied_count": 0,
        "filtered_by_threshold": 0,
        "filtered_by_topk": 0,
        "filtered_count": 0,
        "fallback_used": False,
    }


async def retrieve_vector_memories(
    client: Any,
    provider: LiteLLMVectorMemoryEmbeddingProvider,
    config: VectorMemoryConfig,
    *,
    user_id: str,
    query_text: str,
    target_role: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    diagnostics = _diagnostics(config)
    if not config.enabled:
        return {"status": "disabled", "context": [], "diagnostics": diagnostics, "warnings": []}

    query = _safe_text(query_text, MAX_QUERY_LENGTH)
    if not query:
        return {"status": "no_match", "context": [], "diagnostics": diagnostics, "warnings": []}
    try:
        embedding = await provider.embed_text(query)
    except VectorMemoryEmbeddingError:
        diagnostics["fallback_used"] = True
        return {
            "status": "embedding_error",
            "context": [],
            "diagnostics": diagnostics,
            "warnings": ["vector_memory_retrieval_unavailable"],
        }

    sql = """
        SELECT * FROM match_github_repo_interview_text_memories(
          $1::uuid, $2::text::vector, $3::integer, $4::text, $5::text
        )
    """
    try:
        async with client.pool.acquire() as connection:
            rows = await connection.fetch(
                sql,
                user_id,
                _vector_literal(embedding),
                min(config.match_count * 4, 20),
                _safe_text(target_role, 80) or None,
                _safe_text(category, 80) or None,
            )
    except Exception:
        diagnostics["fallback_used"] = True
        return {
            "status": "retrieval_error",
            "context": [],
            "diagnostics": diagnostics,
            "warnings": ["vector_memory_retrieval_unavailable"],
        }

    candidates = [dict(row) for row in rows]
    matched = [row for row in candidates if float(row.get("similarity") or 0.0) >= config.match_threshold]
    applied = matched[: config.match_count]
    diagnostics.update(
        {
            "candidate_count": len(candidates),
            "matched_count": len(matched),
            "applied_count": len(applied),
            "filtered_by_threshold": len(candidates) - len(matched),
            "filtered_by_topk": len(matched) - len(applied),
            "filtered_count": len(candidates) - len(applied),
        }
    )
    context = [_public_memory(row, float(row.get("similarity") or 0.0)) for row in applied]
    return {
        "status": "matched" if context else "no_match",
        "context": context,
        "diagnostics": diagnostics,
        "warnings": [],
    }
