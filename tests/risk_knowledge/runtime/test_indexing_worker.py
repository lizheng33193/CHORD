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


def test_worker_run_once_executes_queued_job(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.runtime.worker import IndexingWorkerLoop

    executed: list[tuple[str, str]] = []
    _seed_job(job_id="idxjob_root", status="queued")

    worker = IndexingWorkerLoop(
        session_factory=AuthSessionLocal,
        lease_seconds=30,
        poll_seconds=0.01,
        owner="worker-a",
        executor=lambda job_id, owner: executed.append((job_id, owner)),
    )

    picked = worker.run_once()

    assert picked == "idxjob_root"
    assert executed == [("idxjob_root", "worker-a")]


def test_worker_run_once_requeues_and_executes_stale_running_job(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.risk_knowledge.runtime.job_control import DurableJobControlService
    from app.risk_knowledge.runtime.worker import IndexingWorkerLoop

    executed: list[tuple[str, str]] = []
    _seed_job(job_id="idxjob_stale", status="running", current_step="embedding")

    with AuthSessionLocal() as db:
        control = DurableJobControlService(db, lease_seconds=30)
        assert control.claim_job("idxjob_stale", owner="worker-old") is True
        control.update_control(
            "idxjob_stale",
            lease_owner="worker-old",
            lease_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=5),
        )

    worker = IndexingWorkerLoop(
        session_factory=AuthSessionLocal,
        lease_seconds=30,
        poll_seconds=0.01,
        owner="worker-new",
        executor=lambda job_id, owner: executed.append((job_id, owner)),
    )

    picked = worker.run_once()

    assert picked == "idxjob_stale"
    assert executed == [("idxjob_stale", "worker-new")]


def test_worker_manager_can_be_disabled(auth_db) -> None:
    from app.risk_knowledge.runtime.worker import RiskKnowledgeIndexingWorkerManager

    starts: list[str] = []

    class StubWorker:
        def start(self) -> None:
            starts.append("started")

        def stop(self) -> None:
            starts.append("stopped")

    manager = RiskKnowledgeIndexingWorkerManager(
        enabled=False,
        worker_factory=lambda: StubWorker(),
    )

    manager.start()

    assert starts == []
    assert manager.is_running is False


def test_worker_manager_start_and_stop_only_once(auth_db) -> None:
    from app.risk_knowledge.runtime.worker import RiskKnowledgeIndexingWorkerManager

    events: list[str] = []

    class StubWorker:
        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    manager = RiskKnowledgeIndexingWorkerManager(
        enabled=True,
        worker_factory=lambda: StubWorker(),
    )

    manager.start()
    manager.start()
    manager.stop()
    manager.stop()

    assert events == ["start", "stop"]
    assert manager.is_running is False
