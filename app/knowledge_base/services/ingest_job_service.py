"""Metadata-only ingest-job services for the M2D knowledge-base skeleton."""

from __future__ import annotations

from app.knowledge_base.lifecycle import assert_job_transition
from app.knowledge_base.repositories.interfaces import KnowledgeIngestJobRepository
from app.knowledge_base.schemas import IngestJobStatus, IngestStep, KnowledgeIngestJob
from app.knowledge_base.errors import KnowledgeIngestJobNotFoundError


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
    ) -> KnowledgeIngestJob:
        return self._repository.create(
            KnowledgeIngestJob(
                job_id=job_id,
                kb_id=kb_id,
                doc_id=doc_id,
                version_id=version_id,
                status=IngestJobStatus.UPLOADED,
                current_step=IngestStep.UPLOADED,
                error_message=None,
            )
        )

    def transition_job(self, job_id: str, next_status: IngestJobStatus) -> KnowledgeIngestJob:
        job = self.get_job(job_id)
        assert_job_transition(job.status, next_status)
        updated = job.model_copy(
            update={
                "status": next_status,
                "current_step": IngestStep(next_status.value),
            }
        )
        return self._repository.update(updated)

    def fail_job(self, job_id: str, error_message: str) -> KnowledgeIngestJob:
        job = self.get_job(job_id)
        updated = job.model_copy(
            update={
                "status": IngestJobStatus.FAILED,
                "current_step": IngestStep.FAILED,
                "error_message": error_message,
            }
        )
        return self._repository.update(updated)

    def get_job(self, job_id: str) -> KnowledgeIngestJob:
        job = self._repository.get(job_id)
        if job is None:
            raise KnowledgeIngestJobNotFoundError(f"ingest job not found: {job_id}")
        return job
