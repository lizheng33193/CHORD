"""Pydantic contracts for the M2D knowledge-base skeleton."""

from __future__ import annotations

from typing import Any

from enum import Enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeBaseType(str, Enum):
    RISK_DOMAIN = "risk_domain"


class KnowledgeBaseStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    MARKDOWN = "markdown"
    TXT = "txt"
    HTML = "html"
    JSON = "json"
    XLSX = "xlsx"
    XLS = "xls"
    PPTX = "pptx"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class DocumentVersionStatus(str, Enum):
    PARSED = "parsed"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ACTIVE = "active"
    REINDEXING = "reindexing"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class ChunkStatus(str, Enum):
    PENDING = "pending"
    INDEXED = "indexed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DELETED = "deleted"


class IngestJobStatus(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class IngestStep(str, Enum):
    QUEUED = "queued"
    LOCK_ACQUIRED = "lock_acquired"
    PARSING_DOCUMENT = "parsing_document"
    PARSING_PDF = "parsing_pdf"
    OCR_RUNNING = "ocr_running"
    LAYOUT_ANALYZING = "layout_analyzing"
    TABLE_ANALYZING = "table_analyzing"
    TEXT_MERGING = "text_merging"
    CHUNKING = "chunking"
    PERSISTING_CHUNKS = "persisting_chunks"
    EMBEDDING = "embedding"
    FAISS_BUILDING = "faiss_building"
    MANIFEST_PERSISTING = "manifest_persisting"
    ACTIVATING_MANIFEST = "activating_manifest"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


IndexingJobStatus = IngestJobStatus
IndexingJobStep = IngestStep


class IndexingJobTrigger(str, Enum):
    INITIAL_INDEX = "initial_index"
    RETRY = "retry"
    REBUILD_FROM_PARSED = "rebuild_from_parsed"
    REBUILD_FROM_PERSISTED_CHUNKS = "rebuild_from_persisted_chunks"


class PermissionScope(str, Enum):
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class KnowledgeBase(_StrictModel):
    kb_id: str = Field(..., min_length=1)
    kb_name: str = Field(..., min_length=1)
    kb_type: KnowledgeBaseType
    description: str | None = None
    status: KnowledgeBaseStatus
    index_alias: str = Field(..., min_length=1)


class KnowledgeDocument(_StrictModel):
    doc_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_title: str = Field(..., min_length=1)
    doc_name: str = Field(..., min_length=1)
    source_type: SourceType
    source_uri: str = Field(..., min_length=1)
    current_version_id: str | None = None
    status: DocumentStatus
    permission_scope: PermissionScope = PermissionScope.INTERNAL


class KnowledgeDocumentVersion(_StrictModel):
    version_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    file_hash: str = Field(..., min_length=1)
    file_uri: str = Field(..., min_length=1)
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=1)
    index_name: str | None = None
    status: DocumentVersionStatus
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None
    last_job_id: str | None = None


class KnowledgeChunk(_StrictModel):
    chunk_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    chunk_order: int = Field(..., ge=1)
    chunk_type: str = Field(..., min_length=1)
    section_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    status: ChunkStatus
    es_index_name: str | None = None
    es_doc_id: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = Field(default=None, ge=1)
    parser_version: str | None = None
    chunker_version: str | None = None
    permission_scope: PermissionScope = PermissionScope.INTERNAL
    source_type: SourceType | None = None
    source_uri: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_page_range(self) -> "KnowledgeChunk":
        if self.page_start is not None and self.page_end is not None and self.page_start > self.page_end:
            raise ValueError("page_start must be <= page_end")
        return self


class KnowledgeIngestJob(_StrictModel):
    job_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    idempotency_key: str | None = None
    status: IngestJobStatus
    current_step: IngestStep
    error_message: str | None = None
    trigger: IndexingJobTrigger = IndexingJobTrigger.INITIAL_INDEX
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)
    root_job_id: str | None = None
    retry_of_job_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None


class KnowledgeIngestJobControl(_StrictModel):
    job_id: str = Field(..., min_length=1)
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    stale_detected_at: datetime | None = None
    stale_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KnowledgeIngestArtifact(_StrictModel):
    job_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    artifact_kind: str = Field(..., min_length=1)
    artifact_path: str = Field(..., min_length=1)
    is_temporary: bool = False
    created_at: datetime | None = None
    cleaned_at: datetime | None = None


class KnowledgeIngestJobRuntimeState(_StrictModel):
    job_id: str = Field(..., min_length=1)
    progress_message: str | None = None
    progress_completed_steps: int | None = Field(default=None, ge=0)
    progress_total_steps: int | None = Field(default=None, ge=1)
    file_size_bytes: int | None = Field(default=None, ge=0)
    page_count: int | None = Field(default=None, ge=0)
    chunk_count: int | None = Field(default=None, ge=0)
    embedding_count: int | None = Field(default=None, ge=0)
    embedding_batch_count: int | None = Field(default=None, ge=0)
    embedding_batches_completed: int | None = Field(default=None, ge=0)
    vector_mapping_count: int | None = Field(default=None, ge=0)
    parser_duration_ms: int | None = Field(default=None, ge=0)
    embedding_duration_ms: int | None = Field(default=None, ge=0)
    faiss_duration_ms: int | None = Field(default=None, ge=0)
    total_duration_ms: int | None = Field(default=None, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None
