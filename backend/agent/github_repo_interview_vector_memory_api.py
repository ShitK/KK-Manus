"""Authenticated API for user-confirmed GitHub interview text memories."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent.tools.github_repo_interview_session_memory import load_session_memory
from agent.tools.github_repo_interview_vector_memory import (
    LiteLLMVectorMemoryEmbeddingProvider,
    VectorMemoryConfig,
    VectorMemoryEmbeddingError,
    build_vector_memory_candidate,
    list_vector_memories,
    save_vector_memory,
    soft_delete_vector_memory,
)
from services.postgresql import DBConnection
from utils.simple_auth_middleware import get_current_user_id_from_jwt


router = APIRouter(
    prefix="/github-repo-interview/text-memories",
    tags=["github-repo-interview-vector-memory"],
)
db = DBConnection()


class VectorMemoryCandidateRequest(BaseModel):
    id: str
    type: str
    text: str
    content_hash: str
    target_role: Optional[str] = None
    category: Optional[str] = None
    source_thread_id: str
    source_agent_run_id: Optional[str] = None
    source_stage: str = "summarize"
    requires_user_confirmation: bool = True
    persisted: bool = False
    status: str = "candidate_only"
    provenance: Dict[str, Any] = Field(default_factory=dict)
    privacy: Dict[str, bool]


class ConfirmVectorMemoryRequest(BaseModel):
    candidate: VectorMemoryCandidateRequest
    source_thread_id: str


class VectorMemoryResponse(BaseModel):
    id: str
    type: str
    text: str
    target_role: Optional[str] = None
    category: Optional[str] = None
    source_thread_id: Optional[str] = None
    source_agent_run_id: Optional[str] = None
    source_stage: str = "summarize"
    provenance: Dict[str, Any] = Field(default_factory=dict)
    privacy: Dict[str, bool] = Field(default_factory=dict)
    status: str
    persisted: bool
    requires_user_confirmation: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VectorMemoryListResponse(BaseModel):
    memories: List[VectorMemoryResponse]


@router.get("", response_model=VectorMemoryListResponse)
async def list_text_memories(user_id: str = Depends(get_current_user_id_from_jwt)):
    client = await db.client
    memories = await list_vector_memories(client, user_id=user_id)
    return {"memories": memories}


@router.post("", response_model=VectorMemoryResponse)
async def confirm_text_memory(
    request: ConfirmVectorMemoryRequest,
    user_id: str = Depends(get_current_user_id_from_jwt),
):
    client = await db.client
    source_thread_id = request.source_thread_id.strip()
    if not source_thread_id or request.candidate.source_thread_id != source_thread_id:
        raise HTTPException(status_code=400, detail={"code": "invalid_vector_memory_candidate"})

    session_memory = await load_session_memory(client, user_id, source_thread_id)
    canonical = build_vector_memory_candidate(
        session_memory=session_memory,
        source_thread_id=source_thread_id,
        source_agent_run_id=(
            str(session_memory.get("source_agent_run_id"))
            if session_memory.get("source_agent_run_id")
            else None
        ),
    )
    if not canonical:
        raise HTTPException(status_code=400, detail={"code": "vector_memory_candidate_unavailable"})
    if (
        canonical["id"] != request.candidate.id
        or canonical["content_hash"] != request.candidate.content_hash
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "vector_memory_candidate_stale", "candidate": canonical},
        )

    config = VectorMemoryConfig.from_env()
    provider = LiteLLMVectorMemoryEmbeddingProvider(config)
    try:
        return await save_vector_memory(
            client,
            provider,
            config,
            user_id=user_id,
            canonical_candidate=canonical,
        )
    except VectorMemoryEmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "vector_memory_embedding_unavailable", "retryable": True},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_vector_memory_candidate"}) from exc


@router.delete("/{memory_id}", response_model=VectorMemoryResponse)
async def delete_text_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id_from_jwt),
):
    client = await db.client
    try:
        return await soft_delete_vector_memory(client, user_id=user_id, memory_id=memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "vector_memory_not_found"}) from exc
