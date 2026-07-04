from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def runtime_client(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-pr-b-runtime", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    from app.auth.database import create_auth_schema, reset_auth_engine
    from app.main import app

    reset_auth_engine()
    create_auth_schema()

    with TestClient(app) as client:
        yield client

    reset_auth_engine()


def test_pr_b_indexing_routes_cover_submit_status_retry_rebuild_and_worker_health(runtime_client, monkeypatch) -> None:
    from app.api import risk_knowledge_indexing
    from app.api import risk_knowledge_workers

    class StubIndexingService:
        def submit_job(self, *, version_id: str, idempotency_key: str | None = None):
            assert version_id == "risk_guide_v1"
            assert idempotency_key == "idem-index-1"
            return {
                "job_id": "idxjob_submit",
                "version_id": version_id,
                "job_type": "initial_index",
                "status": "queued",
                "idempotency_key": idempotency_key,
            }

        def get_job(self, job_id: str):
            assert job_id == "idxjob_submit"
            return {
                "job_id": job_id,
                "version_id": "risk_guide_v1",
                "job_type": "initial_index",
                "status": "succeeded",
                "idempotency_key": "idem-index-1",
                "error_code": None,
                "error_message": None,
            }

        def retry_job(self, job_id: str, *, idempotency_key: str | None = None):
            assert job_id == "idxjob_failed"
            assert idempotency_key == "idem-retry-1"
            return {
                "job_id": "idxjob_retry",
                "version_id": "risk_guide_v1",
                "job_type": "retry",
                "status": "queued",
                "idempotency_key": idempotency_key,
            }

        def rebuild(self, *, version_id: str, idempotency_key: str | None = None):
            assert version_id == "risk_guide_v1"
            assert idempotency_key == "idem-rebuild-1"
            return {
                "job_id": "idxjob_rebuild",
                "version_id": version_id,
                "job_type": "rebuild",
                "status": "queued",
                "idempotency_key": idempotency_key,
            }

    class StubWorkerService:
        def health(self):
            return {
                "worker_mode": "external",
                "fallback_enabled": False,
                "has_live_workers": True,
                "accepting_jobs": True,
                "live_workers": [{"worker_id": "worker-1", "source": "external"}],
            }

    monkeypatch.setattr(risk_knowledge_indexing, "_indexing_service", lambda _db: StubIndexingService())
    monkeypatch.setattr(risk_knowledge_workers, "_worker_service", lambda: StubWorkerService())

    submit = runtime_client.post(
        "/api/risk-knowledge/indexing/jobs",
        json={"version_id": "risk_guide_v1", "idempotency_key": "idem-index-1"},
    )
    assert submit.status_code == 200
    assert submit.json()["job_id"] == "idxjob_submit"
    assert submit.json()["status"] == "queued"

    detail = runtime_client.get("/api/risk-knowledge/indexing/jobs/idxjob_submit")
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"

    retry = runtime_client.post(
        "/api/risk-knowledge/indexing/jobs/idxjob_failed/retry",
        json={"idempotency_key": "idem-retry-1"},
    )
    assert retry.status_code == 200
    assert retry.json()["job_type"] == "retry"

    rebuild = runtime_client.post(
        "/api/risk-knowledge/indexing/rebuild",
        json={"version_id": "risk_guide_v1", "idempotency_key": "idem-rebuild-1"},
    )
    assert rebuild.status_code == 200
    assert rebuild.json()["job_type"] == "rebuild"

    health = runtime_client.get("/api/risk-knowledge/workers/health")
    assert health.status_code == 200
    assert health.json()["worker_mode"] == "external"
    assert health.json()["accepting_jobs"] is True

