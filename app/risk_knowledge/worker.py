"""External worker entrypoint for PR-B runtime."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import socket
import threading
import time

from app.auth.database import AuthSessionLocal
from app.core.config import settings
from app.risk_knowledge.admin.indexing_admin_service import IndexingAdminService
from app.risk_knowledge.runtime.worker import IndexingWorkerLoop


def _execute_risk_knowledge_job(job_id: str, lease_owner: str) -> None:
    with AuthSessionLocal() as db:
        IndexingAdminService(db).execute_job(job_id, lease_owner=lease_owner)


def _build_redis_client():
    import redis

    return redis.from_url(settings.risk_knowledge_redis_url, decode_responses=True)


def _register_worker_presence(client, worker_id: str) -> None:
    payload = {
        "worker_id": worker_id,
        "source": "external",
        "heartbeat_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
    client.set(
        f"{settings.risk_knowledge_redis_key_prefix}:indexing:workers:{worker_id}",
        json.dumps(payload),
        ex=settings.risk_knowledge_worker_presence_ttl_seconds,
    )


def main() -> None:
    worker_id = f"{socket.gethostname()}:{threading.get_ident()}:{datetime.now(UTC).timestamp()}"
    client = _build_redis_client()
    loop = IndexingWorkerLoop(
        session_factory=AuthSessionLocal,
        lease_seconds=settings.risk_knowledge_indexing_stale_after_seconds,
        poll_seconds=settings.risk_knowledge_indexing_worker_poll_seconds,
        owner=worker_id,
        executor=_execute_risk_knowledge_job,
    )
    while True:
        _register_worker_presence(client, worker_id)
        loop.run_once()
        time.sleep(max(settings.risk_knowledge_indexing_worker_poll_seconds, 0.01))


if __name__ == "__main__":
    main()
