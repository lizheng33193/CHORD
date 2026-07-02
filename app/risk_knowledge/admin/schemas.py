"""Admin API request and response DTOs for M2D-14A."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeBaseCreateRequest(_StrictModel):
    kb_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str | None = None
    domain: str = Field(default="risk", min_length=1)

    @model_validator(mode="after")
    def _validate_domain(self) -> "KnowledgeBaseCreateRequest":
        if self.domain.strip().lower() != "risk":
            raise ValueError("domain must be risk")
        return self


class KnowledgeBaseSummaryResponse(_StrictModel):
    kb_id: str
    name: str
    description: str | None = None
    status: str
    document_count: int
    active_document_count: int


class KnowledgeBaseListResponse(_StrictModel):
    items: list[KnowledgeBaseSummaryResponse]
    total: int


class UploadVersionResult(_StrictModel):
    document_id: str
    version_id: str
    filename: str
    file_size_bytes: int
    file_hash: str
    stored_path: str
    indexing_job_id: str | None = None


class DocumentCreateRequest(_StrictModel):
    title: str = Field(..., min_length=1)
    source_type: str = Field(default="manual", min_length=1)
    source_uri: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_type(self) -> "DocumentCreateRequest":
        if self.source_type.strip().lower() != "manual":
            raise ValueError("source_type must be manual")
        return self


class DocumentSummaryResponse(_StrictModel):
    document_id: str
    kb_id: str
    title: str
    source_type: str
    status: str
    version_count: int
    active_version_id: str | None = None


class DocumentListResponse(_StrictModel):
    items: list[DocumentSummaryResponse]
    total: int


class VersionSummaryResponse(_StrictModel):
    version_id: str
    document_id: str
    version_label: str
    file_hash: str
    file_uri: str
    status: str
    last_job_id: str | None = None
    active_manifest_index_id: str | None = None
    latest_manifest_index_id: str | None = None


class VersionListResponse(_StrictModel):
    items: list[VersionSummaryResponse]
    total: int


class VersionActivateRequest(_StrictModel):
    manifest_index_id: str | None = None


class VersionActivateResponse(_StrictModel):
    result: Literal["activated", "already_active"]
    version_id: str
    document_id: str
    manifest_index_id: str
    status: str


class IndexingJobSummaryResponse(_StrictModel):
    job_id: str
    kb_id: str
    document_id: str
    version_id: str
    trigger: str
    status: str
    current_step: str
    error_message: str | None = None
    attempt: int
    max_attempts: int
    root_job_id: str | None = None
    retry_of_job_id: str | None = None
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    runtime_state_available: bool
    runtime_status: str | None = None
    runtime_current_step: str | None = None
    progress_completed_steps: int | None = None
    progress_total_steps: int | None = None
    progress_message: str | None = None
    elapsed_seconds: int | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    chunk_count: int | None = None
    embedding_count: int | None = None
    embedding_batch_count: int | None = None
    embedding_batches_completed: int | None = None
    vector_mapping_count: int | None = None
    parser_duration_ms: int | None = None
    embedding_duration_ms: int | None = None
    faiss_duration_ms: int | None = None
    total_duration_ms: int | None = None


class IndexingJobListResponse(_StrictModel):
    items: list[IndexingJobSummaryResponse]
    total: int


class IndexingJobLaunchResponse(_StrictModel):
    result: Literal["accepted", "existing_job", "already_indexed"]
    job_id: str | None = None
    version_id: str
    status: str
    trigger: str | None = None
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None


class DebugRetrieveRequest(_StrictModel):
    kb_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    document_id: str | None = None
    version_id: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _validate_query(self) -> "DebugRetrieveRequest":
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class DebugRetrieveScopeResponse(_StrictModel):
    scope_type: str
    document_id: str | None = None
    version_id: str | None = None
    active_manifest_index_ids: list[str] = Field(default_factory=list)


class DebugRetrieveCandidateScoresResponse(_StrictModel):
    vector_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float


class DebugRetrieveCandidateResponse(_StrictModel):
    rank: int
    document_id: str
    version_id: str
    chunk_id: str
    manifest_index_id: str
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    content_hash: str
    text_preview: str
    scores: DebugRetrieveCandidateScoresResponse


class DebugRetrieveDiagnosticsResponse(_StrictModel):
    candidate_count: int
    fusion_method: str
    latency_ms: int
    vector_hit_count: int | None = None
    keyword_hit_count: int | None = None
    fused_hit_count: int | None = None


class DebugRetrieveResponse(_StrictModel):
    query: str
    kb_id: str
    scope: DebugRetrieveScopeResponse
    candidates: list[DebugRetrieveCandidateResponse]
    diagnostics: DebugRetrieveDiagnosticsResponse
