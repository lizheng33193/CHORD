from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-pr-b-runtime", raising=False)

    from app.auth.database import create_auth_schema, reset_auth_engine

    reset_auth_engine()
    create_auth_schema()

    yield tmp_path

    reset_auth_engine()


@pytest.fixture()
def fake_redis_client():
    import fakeredis

    return fakeredis.FakeRedis(decode_responses=True)

