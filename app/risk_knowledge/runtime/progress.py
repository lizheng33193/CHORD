"""Shared progress writer for live Redis state and durable indexing observability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeIngestJobRepository,
    SqlAlchemyKnowledgeIngestJobRuntimeStateRepository,
)
from app.knowledge_base.schemas import (
    IngestStep,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeIngestJob,
    KnowledgeIngestJobRuntimeState,
)
from app.risk_knowledge.runtime.schemas import RedisIndexingJobState

DEFAULT_PROGRESS_TOTAL_STEPS = 10
STAGE_PROGRESS_BY_STEP = {
    "queued": 0,
    "lock_acquired": 0,
    "parsing_document": 1,
    "parsing_pdf": 1,
    "ocr_running": 1,
    "layout_analyzing": 2,
    "table_analyzing": 3,
    "text_merging": 4,
    "chunking": 5,
    "persisting_chunks": 6,
    "embedding": 7,
    "faiss_building": 8,
    "manifest_persisting": 9,
    "activating_manifest": 10,
    "completed": 10,
    "failed": 10,
}


@dataclass(frozen=True)
class ProgressUpdate:
    current_step: str | None = None
    progress_message: str | None = None
    runtime_status: str | None = None
    progress_completed_steps: int | None = None
    progress_total_steps: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    latest_manifest_index_id: str | None = None
    active_manifest_index_id: str | None = None
    lock_token: str | None = None
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
    completed: bool = False


class IndexingProgressUpdater:
    def __init__(
        self,
        *,
        job: KnowledgeIngestJob,
        document: KnowledgeDocument,
        version: KnowledgeDocumentVersion,
        redis_state_store,
        session_factory,
        durable_flush_interval_seconds: float = 3.0,
    ) -> None:
        self._job = job
        self._document = document
        self._version = version
        self._redis_state_store = redis_state_store
        self._session_factory = session_factory
        self._durable_flush_interval = timedelta(seconds=durable_flush_interval_seconds)
        self._last_durable_flush_at: datetime | None = None

    def get_runtime_state(self) -> RedisIndexingJobState | None:
        try:
            return self._redis_state_store.get(self._job.job_id)
        except Exception:
            return None

    def update(self, update: ProgressUpdate, *, force: bool = False) -> None:
        now = self._now()
        self._write_redis(update, now)
        if force or self._should_flush_durable(now):
            self._write_durable(update, now)
            self._last_durable_flush_at = now

    def _write_redis(self, update: ProgressUpdate, now: datetime) -> None:
        existing = self.get_runtime_state()
        state = (existing or self._build_initial_state(now)).model_copy(
            update={
                "runtime_status": update.runtime_status or (existing.runtime_status if existing else "running"),
                "current_step": update.current_step or (existing.current_step if existing else "queued"),
                "progress_message": update.progress_message or (existing.progress_message if existing else "queued"),
                "progress_completed_steps": self._pick_int(update.progress_completed_steps, existing.progress_completed_steps if existing else 0),
                "progress_total_steps": self._pick_int(update.progress_total_steps, existing.progress_total_steps if existing else DEFAULT_PROGRESS_TOTAL_STEPS),
                "error_code": update.error_code if update.error_code is not None else (existing.error_code if existing else None),
                "error_message": update.error_message if update.error_message is not None else (existing.error_message if existing else None),
                "latest_manifest_index_id": update.latest_manifest_index_id or (existing.latest_manifest_index_id if existing else self._job.latest_manifest_index_id),
                "active_manifest_index_id": update.active_manifest_index_id or (existing.active_manifest_index_id if existing else self._job.active_manifest_index_id),
                "lock_token": update.lock_token if update.lock_token is not None else (existing.lock_token if existing else None),
                "file_size_bytes": self._pick_optional(update.file_size_bytes, existing.file_size_bytes if existing else None),
                "page_count": self._pick_optional(update.page_count, existing.page_count if existing else None),
                "chunk_count": self._pick_optional(update.chunk_count, existing.chunk_count if existing else None),
                "embedding_count": self._pick_optional(update.embedding_count, existing.embedding_count if existing else None),
                "embedding_batch_count": self._pick_optional(update.embedding_batch_count, existing.embedding_batch_count if existing else None),
                "embedding_batches_completed": self._pick_optional(update.embedding_batches_completed, existing.embedding_batches_completed if existing else None),
                "vector_mapping_count": self._pick_optional(update.vector_mapping_count, existing.vector_mapping_count if existing else None),
                "parser_duration_ms": self._pick_optional(update.parser_duration_ms, existing.parser_duration_ms if existing else None),
                "embedding_duration_ms": self._pick_optional(update.embedding_duration_ms, existing.embedding_duration_ms if existing else None),
                "faiss_duration_ms": self._pick_optional(update.faiss_duration_ms, existing.faiss_duration_ms if existing else None),
                "total_duration_ms": self._pick_optional(update.total_duration_ms, existing.total_duration_ms if existing else None),
                "updated_at": now,
                "last_heartbeat_at": now,
                "completed_at": now if update.completed else (existing.completed_at if existing else None),
            }
        )
        try:
            self._redis_state_store.put(state)
        except Exception:
            return None

    def _write_durable(self, update: ProgressUpdate, now: datetime) -> None:
        with self._session_factory() as db:
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            runtime_repo = SqlAlchemyKnowledgeIngestJobRuntimeStateRepository(db)
            job = job_repo.get(self._job.job_id)
            if job is not None:
                job_repo.update(
                job.model_copy(
                    update={
                        "current_step": IngestStep(update.current_step) if update.current_step is not None else job.current_step,
                        "last_heartbeat_at": now,
                        "error_message": update.error_message if update.error_message is not None else job.error_message,
                        "latest_manifest_index_id": update.latest_manifest_index_id or job.latest_manifest_index_id,
                        "active_manifest_index_id": update.active_manifest_index_id or job.active_manifest_index_id,
                    }
                    )
                )
            existing_runtime = runtime_repo.get(self._job.job_id)
            runtime_repo.upsert(
                KnowledgeIngestJobRuntimeState(
                    job_id=self._job.job_id,
                    progress_message=update.progress_message if update.progress_message is not None else (existing_runtime.progress_message if existing_runtime else None),
                    progress_completed_steps=self._pick_optional(update.progress_completed_steps, existing_runtime.progress_completed_steps if existing_runtime else None),
                    progress_total_steps=self._pick_optional(update.progress_total_steps, existing_runtime.progress_total_steps if existing_runtime else None),
                    file_size_bytes=self._pick_optional(update.file_size_bytes, existing_runtime.file_size_bytes if existing_runtime else None),
                    page_count=self._pick_optional(update.page_count, existing_runtime.page_count if existing_runtime else None),
                    chunk_count=self._pick_optional(update.chunk_count, existing_runtime.chunk_count if existing_runtime else None),
                    embedding_count=self._pick_optional(update.embedding_count, existing_runtime.embedding_count if existing_runtime else None),
                    embedding_batch_count=self._pick_optional(update.embedding_batch_count, existing_runtime.embedding_batch_count if existing_runtime else None),
                    embedding_batches_completed=self._pick_optional(update.embedding_batches_completed, existing_runtime.embedding_batches_completed if existing_runtime else None),
                    vector_mapping_count=self._pick_optional(update.vector_mapping_count, existing_runtime.vector_mapping_count if existing_runtime else None),
                    parser_duration_ms=self._pick_optional(update.parser_duration_ms, existing_runtime.parser_duration_ms if existing_runtime else None),
                    embedding_duration_ms=self._pick_optional(update.embedding_duration_ms, existing_runtime.embedding_duration_ms if existing_runtime else None),
                    faiss_duration_ms=self._pick_optional(update.faiss_duration_ms, existing_runtime.faiss_duration_ms if existing_runtime else None),
                    total_duration_ms=self._pick_optional(update.total_duration_ms, existing_runtime.total_duration_ms if existing_runtime else None),
                    created_at=existing_runtime.created_at if existing_runtime else None,
                    updated_at=now,
                )
            )
            db.commit()

    def _build_initial_state(self, now: datetime) -> RedisIndexingJobState:
        return RedisIndexingJobState(
            job_id=self._job.job_id,
            kb_id=self._document.kb_id,
            doc_id=self._document.doc_id,
            version_id=self._version.version_id,
            trigger=self._job.trigger,
            runtime_status="running",
            current_step="queued",
            attempt=self._job.attempt,
            max_attempts=self._job.max_attempts,
            progress_completed_steps=0,
            progress_total_steps=DEFAULT_PROGRESS_TOTAL_STEPS,
            progress_message="queued",
            lock_token=None,
            error_code=None,
            error_message=None,
            active_manifest_index_id=self._job.active_manifest_index_id or self._version.active_manifest_index_id,
            latest_manifest_index_id=self._job.latest_manifest_index_id or self._version.latest_manifest_index_id,
            started_at=self._job.started_at or now,
            updated_at=now,
            completed_at=self._job.completed_at,
            last_heartbeat_at=now,
        )

    def _should_flush_durable(self, now: datetime) -> bool:
        if self._last_durable_flush_at is None:
            return True
        return now - self._last_durable_flush_at >= self._durable_flush_interval

    @staticmethod
    def _pick_optional(value: Any, fallback: Any) -> Any:
        return fallback if value is None else value

    @staticmethod
    def _pick_int(value: int | None, fallback: int) -> int:
        return fallback if value is None else value

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


def resolve_stage_progress(step: str | None) -> int:
    if step is None:
        return 0
    return STAGE_PROGRESS_BY_STEP.get(step, 0)
