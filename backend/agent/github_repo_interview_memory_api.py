from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent.tools.github_repo_interview_memory import (
    list_active_memories,
    save_memory_candidate,
    soft_delete_memory,
)
from services.postgresql import DBConnection
from utils.simple_auth_middleware import get_current_user_id_from_jwt


router = APIRouter(prefix="/github-repo-interview/memories", tags=["github-repo-interview-memory"])
db = DBConnection()


class MemoryCandidateRequest(BaseModel):
    id: Optional[str] = None
    type: str
    value: str
    label: Optional[str] = None
    source_stage: str
    source_fields: List[str] = Field(default_factory=list)
    requires_user_confirmation: bool
    status: str
    persisted: bool
    privacy: Dict[str, bool]


class ConfirmMemoryRequest(BaseModel):
    candidate: MemoryCandidateRequest


class MemoryResponse(BaseModel):
    id: str
    type: str
    value: str
    label: str
    source_stage: Optional[str] = None
    source_fields: List[str] = Field(default_factory=list)
    status: str
    persisted: bool
    requires_user_confirmation: bool
    privacy: Dict[str, bool] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse]


@router.get("", response_model=MemoryListResponse)
async def list_memories(user_id: str = Depends(get_current_user_id_from_jwt)):
    client = await db.client
    memories = await list_active_memories(client, user_id)
    return {"memories": memories}


@router.post("", response_model=MemoryResponse)
async def confirm_memory(
    request: ConfirmMemoryRequest,
    user_id: str = Depends(get_current_user_id_from_jwt),
):
    client = await db.client
    try:
        return await save_memory_candidate(client, user_id, request.candidate.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{memory_id}", response_model=MemoryResponse)
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id_from_jwt),
):
    client = await db.client
    try:
        return await soft_delete_memory(client, user_id, memory_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
