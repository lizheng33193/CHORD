from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d14a", raising=False)

    from app.auth.database import create_auth_schema, reset_auth_engine

    reset_auth_engine()
    create_auth_schema()

    yield

    reset_auth_engine()


@pytest.fixture()
def admin_client(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-m2d14a", raising=False)
    monkeypatch.setattr(settings, "risk_knowledge_faiss_artifact_dir", str(tmp_path / "faiss"), raising=False)

    from app.auth.database import create_auth_schema, reset_auth_engine
    from app.main import app

    reset_auth_engine()
    create_auth_schema()

    with TestClient(app) as client:
        yield client

    reset_auth_engine()


@pytest.fixture()
def fake_redis_client():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)


class DeterministicAdminEmbeddingProvider:
    provider_name = "deterministic_test"

    def embed(self, inputs):
        from app.risk_knowledge.embedding.schemas import EmbeddingVectorResult

        return [
            EmbeddingVectorResult(
                chunk_id=item.chunk_id,
                content_hash=item.content_hash,
                provider=self.provider_name,
                model="deterministic-v1",
                dimension=2,
                vector=[float(len(item.text)), float(len(item.chunk_id))],
                vector_checksum=f"sha256:{item.chunk_id}",
            )
            for item in inputs
        ]
