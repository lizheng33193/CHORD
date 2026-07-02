"""Runtime schemas for M2D-9 indexing orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.knowledge_base.schemas import IndexingJobTrigger


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


RuntimeStatus = Literal["queued", "running", "completed", "failed"]
RuntimeStep = Literal[
    "queued",
    "lock_acquired",
    "parsing_document",
    "parsing_pdf",
    "ocr_running",
    "layout_analyzing",
    "table_analyzing",
    "text_merging",
    "chunking",
    "persisting_chunks",
    "embedding",
    "faiss_building",
    "manifest_persisting",
    "activating_manifest",
    "completed",
    "failed",
]


class RedisIndexingJobState(_StrictModel):
    job_id: str = Field(..., min_length=1)
    kb_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    version_id: str = Field(..., min_length=1)
    trigger: IndexingJobTrigger
    runtime_status: RuntimeStatus
    current_step: RuntimeStep
    attempt: int = Field(..., ge=1)
    max_attempts: int = Field(..., ge=1)
    progress_completed_steps: int = Field(..., ge=0)
    progress_total_steps: int = Field(..., ge=1)
    progress_message: str = Field(..., min_length=1)
    lock_token: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    active_manifest_index_id: str | None = None
    latest_manifest_index_id: str | None = None
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
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat_at: datetime | None = None


class IndexingJobRunResult(_StrictModel):
    job_id: str = Field(..., min_length=1)
    root_job_id: str = Field(..., min_length=1)
    retry_of_job_id: str | None = None
    attempt: int = Field(..., ge=1)
    version_id: str = Field(..., min_length=1)
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None
