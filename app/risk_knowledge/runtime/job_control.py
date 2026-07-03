"""Durable lease, cancel, and stale-recovery controls for indexing jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.knowledge_base.repositories.sqlalchemy import (
    SqlAlchemyKnowledgeIngestJobControlRepository,
    SqlAlchemyKnowledgeIngestJobRepository,
)
from app.knowledge_base.schemas import (
    IndexingJobStatus,
    IndexingJobStep,
    KnowledgeIngestJobControl,
)


class DurableJobControlService:
    def __init__(self, db, *, lease_seconds: int) -> None:
        self._db = db
        self._lease_seconds = max(lease_seconds, 1)
        self._control_repo = SqlAlchemyKnowledgeIngestJobControlRepository(db)
        self._job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)

    def get_control(self, job_id: str) -> KnowledgeIngestJobControl | None:
        return self._control_repo.get(job_id)

    def update_control(
        self,
        job_id: str,
        *,
        lease_owner: str | None = None,
        lease_expires_at: datetime | None = None,
        cancel_requested_at: datetime | None = None,
        stale_detected_at: datetime | None = None,
        stale_reason: str | None = None,
    ) -> KnowledgeIngestJobControl:
        current = self._control_repo.get(job_id)
        state = KnowledgeIngestJobControl(
            job_id=job_id,
            lease_owner=lease_owner if current is None else (lease_owner if lease_owner is not None else current.lease_owner),
            lease_expires_at=lease_expires_at if current is None else (lease_expires_at if lease_expires_at is not None else current.lease_expires_at),
            cancel_requested_at=cancel_requested_at if current is None else (cancel_requested_at if cancel_requested_at is not None else current.cancel_requested_at),
            stale_detected_at=stale_detected_at if current is None else (stale_detected_at if stale_detected_at is not None else current.stale_detected_at),
            stale_reason=stale_reason if current is None else (stale_reason if stale_reason is not None else current.stale_reason),
            created_at=current.created_at if current is not None else None,
        )
        updated = self._control_repo.upsert(state)
        self._db.commit()
        return updated

    def claim_job(self, job_id: str, *, owner: str) -> bool:
        job = self._job_repo.get(job_id)
        if job is None:
            return False
        if job.status not in {IndexingJobStatus.QUEUED, IndexingJobStatus.PENDING, IndexingJobStatus.RUNNING}:
            return False

        current = self._control_repo.get(job_id)
        now = self._now()
        if current is not None and current.lease_owner and current.lease_expires_at and current.lease_expires_at > now:
            return False

        self._control_repo.upsert(
            KnowledgeIngestJobControl(
                job_id=job_id,
                lease_owner=owner,
                lease_expires_at=now + timedelta(seconds=self._lease_seconds),
                cancel_requested_at=current.cancel_requested_at if current is not None else None,
                stale_detected_at=current.stale_detected_at if current is not None else None,
                stale_reason=current.stale_reason if current is not None else None,
                created_at=current.created_at if current is not None else None,
            )
        )
        self._db.commit()
        return True

    def heartbeat(self, job_id: str, *, owner: str) -> KnowledgeIngestJobControl:
        current = self._control_repo.get(job_id)
        if current is None or current.lease_owner != owner:
            raise ValueError(f"lease is not owned by {owner}: {job_id}")
        now = self._now()
        updated = self._control_repo.upsert(
            current.model_copy(
                update={
                    "lease_expires_at": now + timedelta(seconds=self._lease_seconds),
                }
            )
        )
        self._db.commit()
        return updated

    def release_job(self, job_id: str, *, owner: str | None = None) -> KnowledgeIngestJobControl | None:
        current = self._control_repo.get(job_id)
        if current is None:
            return None
        if owner is not None and current.lease_owner not in {None, owner}:
            raise ValueError(f"lease is not owned by {owner}: {job_id}")
        updated = self._control_repo.upsert(
            current.model_copy(
                update={
                    "lease_owner": None,
                    "lease_expires_at": None,
                }
            )
        )
        self._db.commit()
        return updated

    def requeue_stale_running_job(self, job_id: str, *, reason: str) -> bool:
        current = self._control_repo.get(job_id)
        job = self._job_repo.get(job_id)
        now = self._now()
        if current is None or job is None:
            return False
        if job.status != IndexingJobStatus.RUNNING:
            return False
        if current.lease_expires_at is None or current.lease_expires_at > now:
            return False

        self._control_repo.upsert(
            current.model_copy(
                update={
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "stale_detected_at": now,
                    "stale_reason": reason,
                }
            )
        )
        self._job_repo.update(
            job.model_copy(
                update={
                    "status": IndexingJobStatus.QUEUED,
                    "current_step": IndexingJobStep.QUEUED,
                }
            )
        )
        self._db.commit()
        return True

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
