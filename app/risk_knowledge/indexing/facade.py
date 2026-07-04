"""Production-oriented PR-B indexing, manifest, and worker facades."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import settings
from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeDocumentRepository, SqlAlchemyKnowledgeIngestJobRepository
from app.knowledge_base.schemas import IndexingJobStatus, IndexingJobTrigger
from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
from app.risk_knowledge.persistence.models import FaissIndexManifestRecord
from app.risk_knowledge.persistence.repositories import SqlAlchemyFaissIndexRepository
from app.risk_knowledge.runtime.worker import should_start_in_process_worker


class RiskKnowledgeIndexingFacade:
    def __init__(self, db, *, redis_client=None) -> None:
        self._db = db
        self._admin = IndexingAdminService(db, redis_client=redis_client, job_launcher=lambda task: None)
        self._jobs = SqlAlchemyKnowledgeIngestJobRepository(db)

    def submit_job(self, *, version_id: str, idempotency_key: str | None = None) -> dict[str, object]:
        launched = self._admin.start_index_with_options(version_id, idempotency_key=idempotency_key)
        job = self._jobs.get(launched.job_id) if launched.job_id else None
        return self._job_launch_payload(
            launched.job_id,
            launched.version_id,
            job.trigger.value if job is not None else "initial_index",
            self._map_status(job.status.value if job is not None else launched.status, job),
            idempotency_key if job is None else job.idempotency_key,
        )

    def rebuild(self, *, version_id: str, idempotency_key: str | None = None) -> dict[str, object]:
        launched = self._admin.start_rebuild_with_options(version_id, idempotency_key=idempotency_key)
        job = self._jobs.get(launched.job_id) if launched.job_id else None
        return self._job_launch_payload(
            launched.job_id,
            launched.version_id,
            "rebuild",
            self._map_status(job.status.value if job is not None else launched.status, job),
            idempotency_key if job is None else job.idempotency_key,
        )

    def retry_job(self, job_id: str, *, idempotency_key: str | None = None) -> dict[str, object]:
        launched = self._admin.retry_job_with_options(job_id, idempotency_key=idempotency_key)
        job = self._jobs.get(launched.job_id) if launched.job_id else None
        return self._job_launch_payload(
            launched.job_id,
            launched.version_id,
            "retry",
            self._map_status(job.status.value if job is not None else launched.status, job),
            idempotency_key if job is None else job.idempotency_key,
        )

    def get_job(self, job_id: str) -> dict[str, object]:
        summary = self._admin.get_job(job_id)
        job = self._jobs.get(job_id)
        return {
            "job_id": summary.job_id,
            "version_id": summary.version_id,
            "job_type": self._map_job_type(summary.trigger),
            "status": self._map_status(summary.status, job, stale_detected_at=summary.stale_detected_at),
            "idempotency_key": job.idempotency_key if job is not None else None,
            "error_code": None,
            "error_message": summary.error_message,
            "stale_reason": summary.stale_reason,
        }

    @staticmethod
    def _job_launch_payload(job_id: str | None, version_id: str, job_type: str, status: str, idempotency_key: str | None) -> dict[str, object]:
        return {
            "job_id": job_id,
            "version_id": version_id,
            "job_type": job_type,
            "status": status,
            "idempotency_key": idempotency_key,
        }

    @staticmethod
    def _map_job_type(trigger: str) -> str:
        return {
            IndexingJobTrigger.INITIAL_INDEX.value: "initial_index",
            IndexingJobTrigger.RETRY.value: "retry",
            IndexingJobTrigger.REBUILD_FROM_PARSED.value: "rebuild",
            IndexingJobTrigger.REBUILD_FROM_PERSISTED_CHUNKS.value: "rebuild",
        }.get(trigger, trigger)

    @staticmethod
    def _map_status(status: str, job=None, *, stale_detected_at=None) -> str:
        if stale_detected_at is not None and status in {"queued", "pending", "running"}:
            return "stale"
        if status == IndexingJobStatus.COMPLETED.value:
            return "succeeded"
        if status == IndexingJobStatus.CANCELED.value:
            return "cancelled"
        if status == IndexingJobStatus.FAILED.value and job is not None and job.attempt >= job.max_attempts:
            return "dead"
        if status == IndexingJobStatus.FAILED.value:
            return "failed"
        if status == "pending":
            return "queued"
        return status


class RiskKnowledgeManifestFacade:
    def __init__(self, db) -> None:
        self._db = db
        self._manifests = SqlAlchemyFaissIndexRepository(db)
        self._documents = SqlAlchemyKnowledgeDocumentRepository(db)

    def get_manifest(self, manifest_id: str) -> dict[str, object]:
        manifest = self._require_manifest(manifest_id)
        return {
            "manifest_id": manifest.index_id,
            "version_id": manifest.version_id,
            "status": self._external_manifest_status(manifest),
            "is_active": manifest.is_active,
        }

    def activate_manifest(self, manifest_id: str) -> dict[str, object]:
        manifest = self._require_manifest(manifest_id)
        if self._external_manifest_status(manifest) == "failed":
            raise ValueError("failed manifest cannot be activated")
        activated = self._manifests.activate_manifest(version_id=manifest.version_id, index_id=manifest.index_id)
        version = self._documents.get_version(manifest.version_id)
        if version is None:
            raise ValueError(f"document version not found: {manifest.version_id}")
        self._documents.update_version(
            version.model_copy(
                update={
                    "active_manifest_index_id": activated.index_id,
                    "latest_manifest_index_id": activated.index_id,
                }
            )
        )
        self._db.commit()
        return {
            "manifest_id": activated.index_id,
            "version_id": activated.version_id,
            "status": self._external_manifest_status(activated),
        }

    def rollback_manifest(self, manifest_id: str) -> dict[str, object]:
        manifest = self._require_manifest(manifest_id)
        if not manifest.is_active:
            raise ValueError("only active manifests can be rolled back")
        previous = self._db.scalar(
            select(FaissIndexManifestRecord)
            .where(FaissIndexManifestRecord.version_id == manifest.version_id)
            .where(FaissIndexManifestRecord.superseded_by_index_id == manifest.index_id)
            .order_by(FaissIndexManifestRecord.updated_at.desc(), FaissIndexManifestRecord.id.desc())
        )
        if previous is None:
            raise ValueError("previous active manifest not found for rollback")
        manifest.is_active = False
        manifest.build_status = "rolled_back"
        manifest.superseded_by_index_id = previous.index_id
        manifest.superseded_at = datetime.now(UTC).replace(tzinfo=None)
        restored = self._manifests.activate_manifest(version_id=previous.version_id, index_id=previous.index_id)
        manifest.is_active = False
        manifest.build_status = "rolled_back"
        manifest.superseded_by_index_id = previous.index_id
        version = self._documents.get_version(previous.version_id)
        if version is None:
            raise ValueError(f"document version not found: {previous.version_id}")
        self._documents.update_version(
            version.model_copy(
                update={
                    "active_manifest_index_id": restored.index_id,
                }
            )
        )
        self._db.commit()
        return {
            "manifest_id": restored.index_id,
            "version_id": restored.version_id,
            "status": self._external_manifest_status(restored),
            "rolled_back_from_manifest_id": manifest.index_id,
        }

    def _require_manifest(self, manifest_id: str):
        manifest = self._manifests.get(manifest_id)
        if manifest is None:
            raise ValueError(f"manifest not found: {manifest_id}")
        return manifest

    @staticmethod
    def _external_manifest_status(manifest) -> str:
        if manifest.is_active:
            return "active"
        if manifest.build_status == "failed":
            return "failed"
        if manifest.build_status == "rolled_back":
            return "rolled_back"
        if manifest.build_status in {"built", "saved"}:
            return "built"
        if manifest.build_status == "superseded":
            return "archived"
        return manifest.build_status


class RiskKnowledgeWorkerFacade:
    def __init__(self, *, redis_client=None) -> None:
        self._redis_client = redis_client

    def health(self) -> dict[str, object]:
        workers = self.list_workers()
        fallback_enabled = settings.risk_knowledge_in_process_worker_fallback_enabled
        worker_mode = settings.risk_knowledge_worker_mode
        return {
            "worker_mode": worker_mode,
            "fallback_enabled": fallback_enabled,
            "has_live_workers": len(workers) > 0,
            "accepting_jobs": len(workers) > 0 or should_start_in_process_worker(worker_mode=worker_mode, fallback_enabled=fallback_enabled),
            "live_workers": workers,
        }

    def list_workers(self) -> list[dict[str, object]]:
        client = self._redis_client
        if client is None:
            try:
                import redis

                client = redis.from_url(settings.risk_knowledge_redis_url, decode_responses=True)
            except Exception:
                return []
        prefix = f"{settings.risk_knowledge_redis_key_prefix}:indexing:workers:"
        workers: list[dict[str, object]] = []
        try:
            for key in client.scan_iter(f"{prefix}*"):
                raw = client.get(key)
                if not raw:
                    continue
                payload = json.loads(raw)
                workers.append(payload)
        except Exception:
            return []
        return workers
