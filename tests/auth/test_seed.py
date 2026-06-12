from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select


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


def test_seed_contains_expected_roles_permissions_and_default_admin(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Permission, Project, Role, User, UserProjectAccess
    from app.auth.seed import DEFAULT_PERMISSIONS, DEFAULT_PROJECT_CODE, DEFAULT_ROLES

    with AuthSessionLocal() as db:
        permission_codes = {row for row in db.scalars(select(Permission.code)).all()}
        role_codes = {row for row in db.scalars(select(Role.code)).all()}
        project = db.scalar(select(Project).where(Project.code == DEFAULT_PROJECT_CODE))
        admin = db.scalar(select(User).where(User.username == "admin"))

        assert permission_codes == set(DEFAULT_PERMISSIONS.keys())
        assert role_codes == set(DEFAULT_ROLES.keys())
        assert project is not None
        assert admin is not None
        assert admin.is_superuser is True

        access = db.scalar(
            select(UserProjectAccess).where(
                UserProjectAccess.user_id == admin.id,
                UserProjectAccess.project_id == project.id,
            )
        )
        assert access is not None
        assert access.access_level == "owner"
        assert access.country is None


def test_seed_role_permission_map_matches_m0_contract(auth_db) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Role

    with AuthSessionLocal() as db:
        analyst = db.scalar(select(Role).where(Role.code == "analyst"))
        viewer = db.scalar(select(Role).where(Role.code == "viewer"))
        data_admin = db.scalar(select(Role).where(Role.code == "data_admin"))

        assert analyst is not None
        assert viewer is not None
        assert data_admin is not None

        analyst_permissions = {
            link.permission.code
            for link in analyst.permission_links
            if link.permission is not None
        }
        viewer_permissions = {
            link.permission.code
            for link in viewer.permission_links
            if link.permission is not None
        }
        data_admin_permissions = {
            link.permission.code
            for link in data_admin.permission_links
            if link.permission is not None
        }

        assert "data:query:execute" not in analyst_permissions
        assert "data:query:view_sql" in analyst_permissions
        assert viewer_permissions == {"profile:view", "trace:view", "memory:read"}
        assert {
            "data:query:generate",
            "data:query:view_sql",
            "data:query:review",
            "data:query:execute",
            "data:bucket:writeback",
        }.issubset(data_admin_permissions)
