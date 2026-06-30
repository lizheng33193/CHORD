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
    lock_token: str = Field(..., min_length=1)
    error_code: str | None = None
    error_message: str | None = None
    active_manifest_index_id: str | None = None
    latest_manifest_index_id: str | None = None
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
