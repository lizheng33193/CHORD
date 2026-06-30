"""Schemas for FAISS foundation artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaissVectorMappingEntry(_StrictModel):
    chunk_id: str = Field(..., min_length=1)
    embedding_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)


class FaissIndexManifestDraft(_StrictModel):
    index_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    embedding_provider: str = Field(..., min_length=1)
    embedding_model: str = Field(..., min_length=1)
    embedding_dimension: int = Field(..., ge=1)
    job_id: str | None = None
    index_type: str = Field(..., min_length=1)
    distance_metric: str = Field(..., min_length=1)
    chunk_content_pairs: list[tuple[str, str]] = Field(default_factory=list)


class FaissIndexManifest(_StrictModel):
    index_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    embedding_provider: str = Field(..., min_length=1)
    embedding_model: str = Field(..., min_length=1)
    embedding_dimension: int = Field(..., ge=1)
    job_id: str | None = None
    index_type: str = Field(..., min_length=1)
    distance_metric: str = Field(..., min_length=1)
    record_count: int = Field(..., ge=0)
    artifact_path: str = Field(..., min_length=1)
    mapping_path: str = Field(..., min_length=1)
    checksum: str = Field(..., min_length=1)
    build_fingerprint: str = Field(..., min_length=1)
    build_status: str = Field(..., min_length=1)
    is_active: bool = False
    superseded_by_index_id: str | None = None
    superseded_at: datetime | None = None
    built_at: datetime


@dataclass(frozen=True)
class FaissBuildResult:
    index: Any
    manifest: FaissIndexManifest
    vector_mappings: dict[int, FaissVectorMappingEntry]


@dataclass(frozen=True)
class SavedFaissIndex:
    manifest: FaissIndexManifest
    vector_mappings: dict[int, FaissVectorMappingEntry]


@dataclass(frozen=True)
class LoadedFaissIndex:
    index: Any
    manifest: FaissIndexManifest
    vector_mappings: dict[int, FaissVectorMappingEntry]
