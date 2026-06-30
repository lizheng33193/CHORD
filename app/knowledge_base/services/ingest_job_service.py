"""Metadata-only ingest-job services for the M2D knowledge-base skeleton."""

from __future__ import annotations

from datetime import UTC, datetime

from app.knowledge_base.lifecycle import assert_job_transition
from app.knowledge_base.repositories.interfaces import KnowledgeIngestJobRepository
from app.knowledge_base.schemas import IngestJobStatus, IngestStep, IndexingJobTrigger, KnowledgeIngestJob
from app.knowledge_base.errors import KnowledgeIngestJobNotFoundError

_DEFAULT_STEPS_BY_STATUS = {
    IngestJobStatus.PENDING: IngestStep.QUEUED,
    IngestJobStatus.RUNNING: IngestStep.LOCK_ACQUIRED,
    IngestJobStatus.COMPLETED: IngestStep.COMPLETED,
    IngestJobStatus.FAILED: IngestStep.FAILED,
    IngestJobStatus.CANCELED: IngestStep.FAILED,
}


class IngestJobService:
    def __init__(self, repository: KnowledgeIngestJobRepository) -> None:
        self._repository = repository

    def create_job(
        self,
        *,
        kb_id: str,
        doc_id: str,
        version_id: str,
        job_id: str,
        trigger: IndexingJobTrigger = IndexingJobTrigger.INITIAL_INDEX,
        attempt: int = 1,
        max_attempts: int = 3,
        root_job_id: str | None = None,
        retry_of_job_id: str | None = None,
    ) -> KnowledgeIngestJob:
        return self._repository.create(
            KnowledgeIngestJob(
                job_id=job_id,
                kb_id=kb_id,
                doc_id=doc_id,
                version_id=version_id,
                status=IngestJobStatus.PENDING,
                current_step=IngestStep.QUEUED,
                error_message=None,
                trigger=trigger,
                attempt=attempt,
                max_attempts=max_attempts,
                root_job_id=root_job_id or job_id,
                retry_of_job_id=retry_of_job_id,
                started_at=None,
                completed_at=None,
                last_heartbeat_at=None,
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )
        )

    def transition_job(self, job_id: str, next_status: IngestJobStatus, *, current_step: IngestStep | None = None) -> KnowledgeIngestJob:
        job = self.get_job(job_id)
        assert_job_transition(job.status, next_status)
        now = datetime.now(UTC).replace(tzinfo=None)
        updated = job.model_copy(
            update={
                "status": next_status,
                "current_step": current_step or _DEFAULT_STEPS_BY_STATUS[next_status],
                "started_at": now if next_status == IngestJobStatus.RUNNING and job.started_at is None else job.started_at,
                "completed_at": now if next_status in {IngestJobStatus.COMPLETED, IngestJobStatus.FAILED, IngestJobStatus.CANCELED} else job.completed_at,
                "last_heartbeat_at": now if next_status == IngestJobStatus.RUNNING else job.last_heartbeat_at,
            }
        )
        return self._repository.update(updated)

    def fail_job(self, job_id: str, error_message: str) -> KnowledgeIngestJob:
        job = self.get_job(job_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        updated = job.model_copy(
            update={
                "status": IngestJobStatus.FAILED,
                "current_step": IngestStep.FAILED,
                "error_message": error_message,
                "completed_at": now,
                "last_heartbeat_at": now,
            }
        )
        return self._repository.update(updated)

    def get_job(self, job_id: str) -> KnowledgeIngestJob:
        job = self._repository.get(job_id)
        if job is None:
            raise KnowledgeIngestJobNotFoundError(f"ingest job not found: {job_id}")
        return job
