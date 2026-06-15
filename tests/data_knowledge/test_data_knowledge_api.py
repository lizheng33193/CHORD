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
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-data-knowledge", raising=False)
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


def _register_privileged_user(*, username: str, email: str, role_codes: list[str]) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.service import AuthService

    with AuthSessionLocal() as db:
        AuthService(db).register_user(
            username=username,
            email=email,
            password="passw0rd123",
            display_name=username,
            role_codes=role_codes,
            allow_privileged_roles=True,
        )


def _create_role(db, *, code: str, name: str, permission_codes: list[str]) -> None:
    from app.auth.models import Permission, Role, RolePermission

    role = Role(code=code, name=name, description=name)
    db.add(role)
    db.flush()
    permissions = db.scalars(select(Permission).where(Permission.code.in_(permission_codes))).all()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()


def test_data_knowledge_examples_hide_sql_without_view_sql_permission(client: TestClient) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import Project
    from app.data_knowledge.models import DataSqlExample

    with AuthSessionLocal() as db:
        project = db.scalar(select(Project).where(Project.code == "maps_lz"))
        assert project is not None
        db.add(
            DataSqlExample(
                project_id=project.id,
                country="mx",
                status="active",
                source_type="manual",
                source_namespace="manual/mx/sql_examples",
                source_key="example:first-loan",
                source_hash="hash-1",
                created_by="admin",
                updated_by="admin",
                natural_language_request="查询首贷用户",
                run_type="cohort_query",
                output_bucket=None,
                sql_hash="sql-hash-1",
                sql_text="SELECT uid FROM dwd_w_apply LIMIT 5",
                tables_used_json=["dwd_w_apply"],
                fields_used_json=["uid"],
                pattern_summary="首贷 cohort",
                reviewer_username="admin",
                execution_status="executed",
            )
        )
        _create_role(
            db,
            code="knowledge_reader_only",
            name="Knowledge Reader Only",
            permission_codes=["data:knowledge:read"],
        )
        db.commit()

    _register_privileged_user(
        username="knowledge-reader",
        email="knowledge-reader@example.com",
        role_codes=["knowledge_reader_only"],
    )
    token, _ = _login(client, "knowledge-reader", "passw0rd123")

    response = client.get(
        "/api/data-knowledge/examples",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sql_text"] is None
    assert body["items"][0]["sql_hash"] == "sql-hash-1"


def test_data_knowledge_seed_import_requires_manage_permission(client: TestClient) -> None:
    _register_privileged_user(
        username="knowledge-analyst",
        email="knowledge-analyst@example.com",
        role_codes=["analyst"],
    )
    token, _ = _login(client, "knowledge-analyst", "passw0rd123")

    response = client.post(
        "/api/data-knowledge/seed/import",
        headers={"Authorization": f"Bearer {token}"},
        json={"bundle": "mx"},
    )
    assert response.status_code == 403
    assert "data:knowledge:manage" in response.json()["detail"]
