"""Embedding contracts for M2D-8."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmbeddingInput(_StrictModel):
    chunk_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    input_type: Literal["document", "query"] = "document"


class EmbeddingVectorResult(_StrictModel):
    chunk_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    dimension: int = Field(..., ge=1)
    vector: list[float] = Field(default_factory=list)
    vector_checksum: str = Field(..., min_length=1)
