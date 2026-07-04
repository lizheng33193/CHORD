from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _seed_job(*, job_id: str, status: str = "running", current_step: str = "embedding") -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import IndexingJobStatus, IndexingJobTrigger, KnowledgeIngestJob

    with AuthSessionLocal() as db:
        SqlAlchemyKnowledgeIngestJobRepository(db).create(
            KnowledgeIngestJob(
                job_id=job_id,
                kb_id="risk_domain_knowledge",
                doc_id="risk_guide",
                version_id="risk_guide_v1",
                status=IndexingJobStatus(status),
                current_step=current_step,
                error_message=None,
                trigger=IndexingJobTrigger.INITIAL_INDEX,
                attempt=1,
                max_attempts=3,
                root_job_id=job_id,
                retry_of_job_id=None,
                started_at=datetime.now(UTC).replace(tzinfo=None),
                completed_at=None,
                last_heartbeat_at=None,
                latest_manifest_index_id=None,
                active_manifest_index_id=None,
            )
        )
        db.commit()


def test_production_job_view_maps_requeued_stale_job_to_stale_status(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.runtime.job_control import DurableJobControlService
    from app.risk_knowledge.indexing.facade import RiskKnowledgeIndexingFacade

    _seed_job(job_id="idxjob_stale")

    with AuthSessionLocal() as db:
        control = DurableJobControlService(db, lease_seconds=30)
        assert control.claim_job("idxjob_stale", owner="worker-old") is True
        control.update_control(
            "idxjob_stale",
            lease_owner="worker-old",
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5),
        )
        assert control.requeue_stale_running_job("idxjob_stale", reason="heartbeat timeout") is True

    with AuthSessionLocal() as db:
        summary = RiskKnowledgeIndexingFacade(db).get_job("idxjob_stale")

    assert summary["status"] == "stale"
    assert summary["stale_reason"] == "heartbeat timeout"

