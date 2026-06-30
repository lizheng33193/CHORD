"""Persistence-side contracts for M2D-8."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PersistedChunkRecord(_StrictModel):
    id: int
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    normalized_content_hash: str = Field(..., min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    token_count: int | None = None
    created_at: datetime
    updated_at: datetime


class PersistedChunkBatchResult(_StrictModel):
    records: list[PersistedChunkRecord] = Field(default_factory=list)


class PersistedEmbeddingRecord(_StrictModel):
    id: int | None = None
    embedding_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    version_id: str | None = None
    content_hash: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    dimension: int = Field(..., ge=1)
    vector_checksum: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)


class PersistedEmbeddingBatchResult(_StrictModel):
    records: list[PersistedEmbeddingRecord] = Field(default_factory=list)
