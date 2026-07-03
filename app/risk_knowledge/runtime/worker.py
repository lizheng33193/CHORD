"""Single-process polling worker for durable indexing jobs."""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.knowledge_base.repositories.sqlalchemy import SqlAlchemyKnowledgeIngestJobRepository
from app.knowledge_base.schemas import IndexingJobStatus
from app.risk_knowledge.runtime.job_control import DurableJobControlService


class IndexingWorkerLoop:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        lease_seconds: int,
        poll_seconds: float,
        owner: str | None = None,
        executor: Callable[[str, str], None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._lease_seconds = lease_seconds
        self._poll_seconds = max(poll_seconds, 0.01)
        self._owner = owner or f"{socket.gethostname()}:{threading.get_ident()}"
        self._executor = executor or (lambda _job_id, _owner: None)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, daemon=True, name="risk-knowledge-indexing-worker")
        self._thread.start()

    def stop(self, *, join_timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(join_timeout_seconds, 0.1))
            self._thread = None

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                pass
            self._stop_event.wait(self._poll_seconds)

    def run_once(self) -> str | None:
        with self._session_factory() as db:
            control = DurableJobControlService(db, lease_seconds=self._lease_seconds)
            job_repo = SqlAlchemyKnowledgeIngestJobRepository(db)
            running_jobs = job_repo.list_by_statuses(["running"])
            for job in running_jobs:
                control.requeue_stale_running_job(job.job_id, reason="heartbeat timeout")

            queued_jobs = job_repo.list_by_statuses(["queued", "pending"])
            for job in queued_jobs:
                if not control.claim_job(job.job_id, owner=self._owner):
                    continue
                self._executor(job.job_id, self._owner)
                return job.job_id
        return None


class RiskKnowledgeIndexingWorkerManager:
    def __init__(self, *, enabled: bool, worker_factory: Callable[[], object]) -> None:
        self._enabled = enabled
        self._worker_factory = worker_factory
        self._worker = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if not self._enabled or self._running:
            return
        self._worker = self._worker_factory()
        self._worker.start()
        self._running = True

    def stop(self) -> None:
        if not self._running or self._worker is None:
            return
        self._worker.stop()
        self._running = False


def build_default_worker_manager(*, session_factory, executor: Callable[[str, str], None]) -> RiskKnowledgeIndexingWorkerManager:
    return RiskKnowledgeIndexingWorkerManager(
        enabled=settings.risk_knowledge_indexing_worker_enabled,
        worker_factory=lambda: IndexingWorkerLoop(
            session_factory=session_factory,
            lease_seconds=settings.risk_knowledge_indexing_stale_after_seconds,
            poll_seconds=settings.risk_knowledge_indexing_worker_poll_seconds,
            owner=f"{socket.gethostname()}:{datetime.now(UTC).timestamp()}",
            executor=executor,
        ),
    )
