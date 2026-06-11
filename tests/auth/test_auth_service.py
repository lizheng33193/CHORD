from __future__ import annotations

from pathlib import Path

import pytest


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


def test_register_and_authenticate_user_builds_runtime_context(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        service = AuthService(db)
        created = service.register_user(
            username="analyst01",
            email="analyst01@example.com",
            password="passw0rd123",
            display_name="Ana Lyst",
        )

        authenticated = service.authenticate_user("analyst01", "passw0rd123")
        assert authenticated is not None
        assert authenticated.id == created.id

        ctx = service.build_user_context(created.id)
        assert ctx.user_id == str(created.id)
        assert ctx.username == "analyst01"
        assert ctx.display_name == "Ana Lyst"
        assert ctx.project_code == "maps_lz"
        assert ctx.country == "mx"
        assert "analyst" in ctx.roles
        assert "profile:run" in ctx.permissions
        assert "memory:write" in ctx.permissions


def test_scope_override_rejects_country_without_access(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        service = AuthService(db)
        created = service.register_user(
            username="viewer01",
            email="viewer01@example.com",
            password="passw0rd123",
            display_name="View Only",
            role_codes=["viewer"],
            default_country="mx",
        )

        with pytest.raises(PermissionError):
            service.build_user_context(created.id, requested_country="th")
