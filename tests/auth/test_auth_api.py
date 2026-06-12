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


def test_me_scope_override_without_access_returns_403(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "analyst-scope",
            "email": "analyst-scope@example.com",
            "password": "passw0rd123",
            "display_name": "Analyst Scope",
        },
    )
    assert register.status_code == 201

    token, _user = _login(client, "analyst-scope", "passw0rd123")
    me = client.get(
        "/api/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Country": "thailand",
        },
    )
    assert me.status_code == 403


def test_my_projects_returns_authorized_scopes(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "projects-user",
            "email": "projects-user@example.com",
            "password": "passw0rd123",
            "display_name": "Projects User",
        },
    )
    assert register.status_code == 201

    token, user = _login(client, "projects-user", "passw0rd123")
    response = client.get(
        "/api/auth/my-projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["projects"]
    assert payload["projects"][0]["project_id"] == user["default_project_id"]
    assert payload["projects"][0]["country"] == "mx"


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


def test_data_acquisition_generate_rejects_country_outside_scope(client: TestClient, monkeypatch) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "analyst-generate",
            "email": "analyst-generate@example.com",
            "password": "passw0rd123",
            "display_name": "Analyst Generate",
        },
    )
    assert register.status_code == 201

    token, _user = _login(client, "analyst-generate", "passw0rd123")

    def _unexpected_orchestrator():
        raise AssertionError("generate should be blocked before orchestrator call")

    monkeypatch.setattr("data_acquisition_agent.api._get_orchestrator", _unexpected_orchestrator)
    response = client.post(
        "/api/data-acquisition/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "拉取最近高风险用户",
            "target_country": "thailand",
            "target_action": "extract",
        },
    )
    assert response.status_code == 403


def test_data_acquisition_generate_requires_view_sql_permission(client: TestClient, monkeypatch) -> None:
    from sqlalchemy import select

    from app.auth.database import AuthSessionLocal
    from app.auth.models import Permission, Role, RolePermission
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        generate_permission = db.scalar(select(Permission).where(Permission.code == "data:query:generate"))
        assert generate_permission is not None

        role = Role(
            code="generate_only",
            name="Generate Only",
            description="Can generate SQL requests without viewing SQL text.",
        )
        db.add(role)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=generate_permission.id))
        db.commit()

        service = AuthService(db)
        service.register_user(
            username="generate-only-user",
            email="generate-only@example.com",
            password="passw0rd123",
            display_name="Generate Only User",
            role_codes=["generate_only"],
            allow_privileged_roles=True,
        )

    token, _user = _login(client, "generate-only-user", "passw0rd123")

    def _unexpected_orchestrator():
        raise AssertionError("generate should be blocked before orchestrator call")

    monkeypatch.setattr("data_acquisition_agent.api._get_orchestrator", _unexpected_orchestrator)
    response = client.post(
        "/api/data-acquisition/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "拉取最近高风险用户",
            "target_country": "mexico",
            "target_action": "extract",
        },
    )
    assert response.status_code == 403
    assert "data:query:view_sql" in response.json()["detail"]


def test_data_acquisition_execute_rejects_country_outside_scope(client: TestClient, monkeypatch) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "analyst-execute",
            "email": "analyst-execute@example.com",
            "password": "passw0rd123",
            "display_name": "Analyst Execute",
            "role_codes": ["data_admin"],
        },
    )
    assert register.status_code == 400

    from app.auth.database import AuthSessionLocal
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        service = AuthService(db)
        service.register_user(
            username="data-admin-execute",
            email="data-admin-execute@example.com",
            password="passw0rd123",
            display_name="Data Admin Execute",
            role_codes=["data_admin"],
            allow_privileged_roles=True,
        )

    token, _user = _login(client, "data-admin-execute", "passw0rd123")

    def _unexpected_execute(*_args, **_kwargs):
        raise AssertionError("execute should be blocked before pipeline call")

    monkeypatch.setattr("data_acquisition_agent.api._run_execute_pipeline", _unexpected_execute)
    response = client.post(
        "/api/data-acquisition/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "approved_sql": "SELECT uid FROM users LIMIT 1",
            "sql_kind": "query_only",
            "target_country": "thailand",
            "approved_by": "ignored-by-api",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert response.status_code == 403


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
