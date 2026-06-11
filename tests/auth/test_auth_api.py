from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-auth", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data
    from app.main import app

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    with TestClient(app) as test_client:
        yield test_client

    reset_auth_engine()


def _login(client: TestClient, username_or_email: str, password: str) -> tuple[str, dict]:
    response = client.post(
        "/api/auth/login",
        json={"username_or_email": username_or_email, "password": password},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["access_token"], payload["user"]


def test_register_login_and_me_roundtrip(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "analyst02",
            "email": "analyst02@example.com",
            "password": "passw0rd123",
            "display_name": "Analyst Two",
        },
    )
    assert register.status_code == 201

    token, user = _login(client, "analyst02", "passw0rd123")
    assert "analyst" in user["roles"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "analyst02"
    assert body["default_country"] == "mx"
    assert "profile:run" in body["permissions"]


def test_viewer_cannot_execute_data_acquisition(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "viewer02",
            "email": "viewer02@example.com",
            "password": "passw0rd123",
            "display_name": "Viewer Two",
            "role_codes": ["viewer"],
        },
    )
    assert register.status_code == 201

    token, _user = _login(client, "viewer02", "passw0rd123")
    execute = client.post(
        "/api/data-acquisition/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "approved_sql": "SELECT uid FROM users LIMIT 1",
            "sql_kind": "query_only",
            "target_country": "mexico",
            "approved_by": "ignored-by-api",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert execute.status_code == 403


def test_orchestrator_session_uses_authenticated_identity(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "analyst03",
            "email": "analyst03@example.com",
            "password": "passw0rd123",
            "display_name": "Analyst Three",
        },
    )
    assert register.status_code == 201

    token, user = _login(client, "analyst03", "passw0rd123")
    created = client.post(
        "/api/orchestrator/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"initial_message": "hello"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["user_id"] == str(user["id"])
    assert payload["project_id"] == str(user["default_project_id"])
    assert payload["country"] == user["default_country"]
