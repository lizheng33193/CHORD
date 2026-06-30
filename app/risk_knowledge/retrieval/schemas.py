"""Schemas for M2D-10 hybrid retrieval foundation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrievalScopeType(str, Enum):
    EXPLICIT_VERSION = "explicit_version"
    ACTIVE_DOCUMENT_VERSION = "active_document_version"
    KB_ACTIVE_DOCUMENTS = "kb_active_documents"


class RetrievalQuery(_StrictModel):
    query: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    version_id: str | None = None
    document_id: str | None = None
    vector_top_k: int = Field(default=50, ge=1)
    keyword_top_k: int = Field(default=50, ge=1)
    fused_top_k: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _validate_query(self) -> "RetrievalQuery":
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class ActiveRetrievalManifest(_StrictModel):
    manifest_index_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    embedding_provider: str = Field(..., min_length=1)
    embedding_model: str = Field(..., min_length=1)
    embedding_dimension: int = Field(..., ge=1)
    distance_metric: str = Field(..., min_length=1)
    artifact_path: str = Field(..., min_length=1)
    mapping_path: str = Field(..., min_length=1)
    checksum: str = Field(..., min_length=1)
    build_fingerprint: str = Field(..., min_length=1)


class ActiveRetrievalScope(_StrictModel):
    scope_type: RetrievalScopeType
    kb_id: str = Field(..., min_length=1)
    document_id: str | None = None
    version_id: str | None = None
    active_manifest_index_ids: list[str] = Field(default_factory=list)
    manifests: list[ActiveRetrievalManifest] = Field(default_factory=list)


class QueryEmbeddingResult(_StrictModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    dimension: int = Field(..., ge=1)
    vector: list[float] = Field(default_factory=list)
    vector_checksum: str = Field(..., min_length=1)


class VectorRetrievalHit(_StrictModel):
    retrieval_key: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    vector_id: int
    raw_score: float
    distance_metric: str = Field(..., min_length=1)
    rank: int = Field(..., ge=1)


class KeywordRetrievalHit(_StrictModel):
    retrieval_key: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    score: float
    rank: int = Field(..., ge=1)
    matched_terms: list[str] = Field(default_factory=list)


class FusedRetrievalHit(_StrictModel):
    retrieval_key: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    vector_raw_score: float | None = None
    keyword_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None
    fused_score: float
    fused_rank: int = Field(..., ge=1)
    matched_channels: list[str] = Field(default_factory=list)


class HybridRetrievalCandidate(_StrictModel):
    retrieval_key: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    manifest_index_id: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    text: str = Field(..., min_length=1)
    vector_raw_score: float | None = None
    keyword_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None
    fused_score: float
    fused_rank: int = Field(..., ge=1)
    matched_channels: list[str] = Field(default_factory=list)


class HybridRetrievalResult(_StrictModel):
    query: str = Field(..., min_length=1)
    normalized_query: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    scope_type: RetrievalScopeType
    document_id: str | None = None
    version_id: str | None = None
    active_manifest_index_ids: list[str] = Field(default_factory=list)
    embedding_provider: str = Field(..., min_length=1)
    embedding_model: str = Field(..., min_length=1)
    embedding_dimension: int = Field(..., ge=1)
    candidates: list[HybridRetrievalCandidate] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
