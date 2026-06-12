from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


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


@pytest.fixture()
def auth_db(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-auth", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import AuthSessionLocal, create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    yield

    reset_auth_engine()


def _login(client: TestClient, username_or_email: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username_or_email": username_or_email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _create_role(db, *, code: str, name: str, permission_codes: list[str]) -> None:
    from app.auth.models import Permission, Role, RolePermission

    role = Role(code=code, name=name, description=name)
    db.add(role)
    db.flush()
    permissions = db.scalars(select(Permission).where(Permission.code.in_(permission_codes))).all()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()


def test_normalize_country_alias_maps_business_names_to_codes() -> None:
    from app.auth.permissions import normalize_country_scope_value

    assert normalize_country_scope_value("mx") == "mx"
    assert normalize_country_scope_value("mexico") == "mx"
    assert normalize_country_scope_value("th") == "th"
    assert normalize_country_scope_value("thailand") == "th"
    assert normalize_country_scope_value("  MEXICO ") == "mx"


def test_require_country_access_accepts_alias_for_same_scope(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.permissions import require_country_access
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        service = AuthService(db)
        created = service.register_user(
            username="alias-user",
            email="alias-user@example.com",
            password="passw0rd123",
            display_name="Alias User",
            default_country="mx",
        )
        ctx = service.build_user_context(created.id)

        require_country_access(ctx, "mx", project_id=ctx.project_id)
        require_country_access(ctx, "mexico", project_id=ctx.project_id)


def test_invalid_token_is_401_but_scope_override_is_403(client: TestClient) -> None:
    register = client.post(
        "/api/auth/register",
        json={
            "username": "scope-user",
            "email": "scope-user@example.com",
            "password": "passw0rd123",
            "display_name": "Scope User",
        },
    )
    assert register.status_code == 201

    invalid = client.get("/api/auth/me", headers={"Authorization": "Bearer broken-token"})
    assert invalid.status_code == 401

    token = _login(client, "scope-user", "passw0rd123")
    forbidden = client.get(
        "/api/auth/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Country": "thailand",
        },
    )
    assert forbidden.status_code == 403
    assert "no access to country" in forbidden.json()["detail"]


def test_review_and_view_sql_permissions_are_independent(auth_db, client: TestClient) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        _create_role(
            db,
            code="review_only",
            name="Review Only",
            permission_codes=["data:query:review"],
        )
        service = AuthService(db)
        created = service.register_user(
            username="review-only-user",
            email="review-only-user@example.com",
            password="passw0rd123",
            display_name="Review Only User",
            role_codes=["review_only"],
            allow_privileged_roles=True,
        )
        ctx = service.build_user_context(created.id)
        assert "data:query:review" in ctx.permissions
        assert "data:query:view_sql" not in ctx.permissions

    token = _login(client, "review-only-user", "passw0rd123")
    response = client.get("/api/auth/my-permissions", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    permissions = set(response.json()["permissions"])
    assert "data:query:review" in permissions
    assert "data:query:view_sql" not in permissions
