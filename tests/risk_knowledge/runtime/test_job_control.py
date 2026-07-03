from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _seed_job(*, job_id: str, status: str = "queued", current_step: str = "queued") -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import IndexingJobStatus, IndexingJobTrigger, KnowledgeIngestJob

    with AuthSessionLocal() as db:
        SqlAlchemyKnowledgeIngestJobRepository(db).create(
            KnowledgeIngestJob(
                job_id=job_id,
                kb_id="risk_domain_knowledge",
                doc_id="risk_guide",
                version_id="risk_guide_202607",
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


def test_job_control_claim_prevents_double_execution(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.runtime.job_control import DurableJobControlService

    _seed_job(job_id="idxjob_root", status="queued")

    with AuthSessionLocal() as db:
        service = DurableJobControlService(db, lease_seconds=30)

        first_claim = service.claim_job("idxjob_root", owner="worker-a")
        second_claim = service.claim_job("idxjob_root", owner="worker-b")

        assert first_claim is True
        assert second_claim is False
        control = service.get_control("idxjob_root")
        assert control is not None
        assert control.lease_owner == "worker-a"
        assert control.lease_expires_at is not None


def test_job_control_heartbeat_renews_existing_lease(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.runtime.job_control import DurableJobControlService

    _seed_job(job_id="idxjob_root", status="running")

    with AuthSessionLocal() as db:
        service = DurableJobControlService(db, lease_seconds=30)
        assert service.claim_job("idxjob_root", owner="worker-a") is True
        initial = service.get_control("idxjob_root")
        assert initial is not None

        service.heartbeat("idxjob_root", owner="worker-a")
        renewed = service.get_control("idxjob_root")

        assert renewed is not None
        assert renewed.lease_expires_at is not None
        assert initial.lease_expires_at is not None
        assert renewed.lease_expires_at >= initial.lease_expires_at


def test_job_control_marks_stale_then_requeues_before_reclaim(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
    from app.knowledge_base.schemas import IndexingJobStatus
    from app.risk_knowledge.runtime.job_control import DurableJobControlService

    _seed_job(job_id="idxjob_root", status="running", current_step="embedding")

    with AuthSessionLocal() as db:
        service = DurableJobControlService(db, lease_seconds=30)
        assert service.claim_job("idxjob_root", owner="worker-a") is True
        expired = service.get_control("idxjob_root")
        assert expired is not None
        service.update_control(
            "idxjob_root",
            lease_owner="worker-a",
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5),
        )
        assert service.requeue_stale_running_job("idxjob_root", reason="heartbeat timeout") is True

        control = service.get_control("idxjob_root")
        job = SqlAlchemyKnowledgeIngestJobRepository(db).get("idxjob_root")

        assert control is not None
        assert control.lease_owner is None
        assert control.stale_detected_at is not None
        assert control.stale_reason == "heartbeat timeout"
        assert job is not None
        assert job.status == IndexingJobStatus("queued")
        assert job.current_step.value == "queued"
        assert service.claim_job("idxjob_root", owner="worker-b") is True
