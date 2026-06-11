from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from app.core.config import settings
    from app.services.orchestrator_agent import session_store

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-auth", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)
    monkeypatch.setattr(session_store, "_sessions_dir", lambda: tmp_path / "sessions")
    session_store._CACHE.clear()
    session_store._DIRTY.clear()

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data
    from app.main import app

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    with TestClient(app) as test_client:
        yield test_client

    session_store._CACHE.clear()
    session_store._DIRTY.clear()
    reset_auth_engine()


def _login(client: TestClient, username_or_email: str, password: str) -> tuple[str, dict]:
    response = client.post(
        "/api/auth/login",
        json={"username_or_email": username_or_email, "password": password},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["access_token"], payload["user"]


def test_orchestrator_session_keeps_bound_project_and_country_scope(client: TestClient) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import User, UserProjectAccess

    register = client.post(
        "/api/auth/register",
        json={
            "username": "dual-scope-user",
            "email": "dual-scope-user@example.com",
            "password": "passw0rd123",
            "display_name": "Dual Scope User",
        },
    )
    assert register.status_code == 201

    with AuthSessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "dual-scope-user"))
        assert user is not None
        db.add(
            UserProjectAccess(
                user_id=user.id,
                project_id=user.default_project_id,
                country="th",
                access_level="member",
            )
        )
        db.commit()

    token, user = _login(client, "dual-scope-user", "passw0rd123")
    created = client.post(
        "/api/orchestrator/sessions",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Country": "mx",
            "X-Project-ID": str(user["default_project_id"]),
        },
        json={"initial_message": "hello"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    session_payload = client.get(
        f"/api/orchestrator/sessions/{session_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Country": "mx",
            "X-Project-ID": str(user["default_project_id"]),
        },
    )
    assert session_payload.status_code == 200
    active_entities = session_payload.json()["active_entities"]
    assert active_entities["user_context_snapshot"]["country"] == "mx"
    assert active_entities["request_context"]["user"]["country"] == "mx"

    wrong_scope = client.get(
        f"/api/orchestrator/sessions/{session_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Country": "th",
            "X-Project-ID": str(user["default_project_id"]),
        },
    )
    assert wrong_scope.status_code == 403


def test_runtime_audit_helper_persists_actor_request_and_trace_fields(client: TestClient) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import AuditEvent
    from app.auth.service import AuthService
    from app.core.audit import record_runtime_audit_event
    from app.core.request_context import RequestContext

    register = client.post(
        "/api/auth/register",
        json={
            "username": "audit-user",
            "email": "audit-user@example.com",
            "password": "passw0rd123",
            "display_name": "Audit User",
        },
    )
    assert register.status_code == 201

    with AuthSessionLocal() as db:
        service = AuthService(db)
        user = service.authenticate_user("audit-user", "passw0rd123")
        assert user is not None
        ctx = service.build_user_context(user.id)
        request_context = RequestContext(
            request_id="req-1",
            user=ctx,
            session_id="sess-1",
            trace_id="trace-1",
        )

    record_runtime_audit_event(
        user=ctx,
        request_context=request_context,
        event_type="memory.create",
        action="create",
        resource_type="memory",
        resource_id="mem-1",
        metadata={"scope": "project"},
    )

    with AuthSessionLocal() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "memory.create"))
        assert event is not None
        assert event.user_id == int(ctx.user_id)
        assert event.project_id == int(ctx.project_id)
        assert event.country == "mx"
        assert event.request_id == "req-1"
        assert event.session_id == "sess-1"
        assert event.trace_id == "trace-1"
        assert event.resource_type == "memory"
        assert event.resource_id == "mem-1"
