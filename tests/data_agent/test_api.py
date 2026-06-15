from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-data-agent", raising=False)
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


def _stub_generate_result(sql: str, sql_kind: str = "query_only") -> dict:
    return {
        "request_id": "gen-001",
        "target_country": "mexico",
        "reasoning_summary": "stub",
        "sql": sql,
        "sql_kind": sql_kind,
        "python": None,
        "audit_report": {"high_risk_ddl": sql_kind == "build_table_script", "final_verdict": "ok"},
        "metadata": {
            "model": "stub",
            "tokens_used": None,
            "token_estimate": 1,
            "knowledge_files_loaded": [],
            "redaction_events": 0,
            "danger_scan_events": 0,
            "generated_at": "2026-06-12T00:00:00Z",
        },
    }


def test_data_agent_run_lifecycle_create_list_and_hidden_sql_without_view_permission(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-admin", email="da-admin@example.com", role_codes=["data_admin"])
    token, _user = _login(client, "da-admin", "passw0rd123")
    raw_sql = "  SELECT uid FROM users LIMIT 5  \n"
    normalized_sql = "SELECT uid FROM users LIMIT 5"

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(raw_sql),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["status"] == "awaiting_review"
    assert payload["current_sql"]["sql_text"] == normalized_sql
    assert payload["current_sql"]["sql_hash"] == hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()
    run_id = payload["run_id"]

    listed = client.get("/api/data-agent/runs", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    runs = listed.json()["runs"]
    assert any(run["run_id"] == run_id for run in runs)

    from app.auth.database import AuthSessionLocal

    with AuthSessionLocal() as db:
        _create_role(
            db,
            code="data_execute_only",
            name="Data Execute Only",
            permission_codes=["data:query:execute"],
        )
    _register_privileged_user(
        username="execute-only",
        email="execute-only@example.com",
        role_codes=["data_execute_only"],
    )
    no_view_token, _ = _login(client, "execute-only", "passw0rd123")

    detail = client.get(
        f"/api/data-agent/runs/{run_id}",
        headers={"Authorization": f"Bearer {no_view_token}"},
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["current_sql"]["sql_text"] is None
    assert detail_payload["current_sql"]["sql_hash"]


def test_data_agent_build_table_script_is_review_only_and_cannot_be_approved_or_executed(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-script", email="da-script@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-script", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "CREATE TABLE tmp.test AS SELECT uid FROM users",
            sql_kind="build_table_script",
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "建表保存 cohort",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]
    assert create.json()["current_sql"]["safety_status"] == "review_only"

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 409

    execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert execute.status_code == 409


def test_data_agent_edit_requires_review_permission_and_clears_previous_approval(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-edit", email="da-edit@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-edit", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 3"),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查最近用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200
    assert approve.json()["approved_sql_hash"] == approve.json()["current_sql"]["sql_hash"]
    approved_hash = approve.json()["approved_sql_hash"]

    edit = client.post(
        f"/api/data-agent/runs/{run_id}/edit",
        headers={"Authorization": f"Bearer {token}"},
        json={"sql_text": "  SELECT uid FROM users LIMIT 10  \n", "comment": "扩大范围"},
    )
    assert edit.status_code == 200
    edit_payload = edit.json()
    assert edit_payload["status"] == "awaiting_review"
    assert edit_payload["approved_sql_hash"] is None
    assert edit_payload["current_sql"]["sql_hash"] != approved_hash
    assert edit_payload["current_sql"]["source"] == "manual_edited"
    assert edit_payload["current_sql"]["sql_text"] == "SELECT uid FROM users LIMIT 10"
    assert edit_payload["current_sql"]["sql_hash"] == hashlib.sha256(
        "SELECT uid FROM users LIMIT 10".encode("utf-8")
    ).hexdigest()


def test_data_agent_execute_requires_writeback_permission_for_bucket_writeback(client: TestClient, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal

    with AuthSessionLocal() as db:
        _create_role(
            db,
            code="review_execute_no_writeback",
            name="Review Execute No Writeback",
            permission_codes=[
                "data:query:generate",
                "data:query:view_sql",
                "data:query:review",
                "data:query:execute",
            ],
        )
    _register_privileged_user(
        username="da-no-writeback",
        email="da-no-writeback@example.com",
        role_codes=["review_execute_no_writeback"],
    )
    token, _ = _login(client, "da-no-writeback", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid, score FROM users LIMIT 2"),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "补齐行为画像",
            "target_country": "mexico",
            "run_type": "bucket_writeback",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200

    execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert execute.status_code == 403


def test_data_agent_execute_rejects_hash_mismatch_and_supports_cohort_query_execution(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-exec", email="da-exec@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-exec", "passw0rd123")
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("  SELECT uid FROM users LIMIT 2  \n"),
    )
    monkeypatch.setattr(
        "app.data_agent.service._execute_cohort_query",
        lambda *, sql_text, target_country: captured.update({"sql_text": sql_text, "target_country": target_country}) or {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 2,
            "preview_rows": [{"uid": "u1"}, {"uid": "u2"}],
        },
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查 cohort",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200

    client.post(
        f"/api/data-agent/runs/{run_id}/edit",
        headers={"Authorization": f"Bearer {token}"},
        json={"sql_text": "SELECT uid FROM users LIMIT 5", "comment": "扩大 cohort"},
    )
    stale_execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert stale_execute.status_code == 409

    approve_again = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve_again.status_code == 200

    execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert execute.status_code == 200
    payload = execute.json()
    assert payload["status"] == "executed"
    assert payload["execution"]["rows_actual"] == 2
    assert payload["execution"]["uids"] == ["u1", "u2"]
    assert payload["writeback"] is None
    assert captured["sql_text"] == "SELECT uid FROM users LIMIT 5"
    assert captured["target_country"] == "mx"


def test_data_agent_bucket_writeback_records_real_target_dir_in_api_db_and_audit(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    from app.auth.database import AuthSessionLocal
    from app.auth.models import AuditEvent
    from app.data_agent.models import DataAgentWritebackEvent

    _register_privileged_user(username="da-writeback", email="da-writeback@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-writeback", "passw0rd123")
    target_dir = str(tmp_path / "behavior" / "by_uid")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid, score FROM users LIMIT 2"),
    )
    monkeypatch.setattr(
        "app.data_agent.service._execute_bucket_writeback",
        lambda *, run, sql_text, approved_by: {
            "rows_actual": 2,
            "rows_estimated": 2,
            "uids": ["u1", "u2"],
            "preview_rows": [],
            "artifact": {
                "filenames": ["u1.json", "u2.json"],
                "written_file_count": 2,
                "total_uids": 2,
                "rows_per_uid": {"u1": 1, "u2": 1},
            },
            "output_bucket": "behavior",
            "output_format": "json",
            "target_dir": target_dir,
            "written_uid_count": 2,
        },
    )

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "写回行为画像 bucket",
            "target_country": "mexico",
            "run_type": "bucket_writeback",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200

    execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert execute.status_code == 200
    payload = execute.json()
    assert payload["writeback"]["target_dir"] == target_dir
    assert payload["writeback"]["artifact"]["filenames"] == ["u1.json", "u2.json"]
    assert all("/" not in filename for filename in payload["writeback"]["artifact"]["filenames"])

    with AuthSessionLocal() as db:
        writeback_event = db.scalar(
            select(DataAgentWritebackEvent).where(DataAgentWritebackEvent.run_id == run_id)
        )
        assert writeback_event is not None
        assert writeback_event.target_dir == target_dir
        audit_event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.event_type == "data.bucket.writeback", AuditEvent.resource_id == run_id)
            .order_by(AuditEvent.id.desc())
        )
        assert audit_event is not None
        assert audit_event.metadata_json["target_dir"] == target_dir


def test_data_agent_create_run_invokes_retrieval_and_keeps_snapshot_hidden(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-knowledge", email="da-knowledge@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-knowledge", "passw0rd123")

    captured: dict[str, object] = {}

    def _fake_generate(**kwargs):
        captured["retrieved_context"] = kwargs.get("retrieved_context")
        captured["prompt_context"] = kwargs.get("prompt_context")
        return _stub_generate_result("SELECT uid FROM users LIMIT 7")

    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询首贷从未逾期用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert captured["retrieved_context"] is not None
    assert captured["prompt_context"] is not None
    assert "retrieval_snapshot_json" not in body["current_sql"]


def test_data_agent_revise_run_invokes_retrieval(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-revise-knowledge", email="da-revise-knowledge@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-revise-knowledge", "passw0rd123")

    calls: list[dict[str, object]] = []

    def _fake_generate(**kwargs):
        calls.append(kwargs)
        return _stub_generate_result("SELECT uid FROM users LIMIT 9")

    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "请改成首贷用户"},
    )
    assert revise.status_code == 200
    assert len(calls) == 2
    assert calls[1]["retrieved_context"] is not None
    assert calls[1]["prompt_context"] is not None


def test_data_agent_successful_execute_persists_draft_sql_example(client: TestClient, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_knowledge.models import DataSqlExample

    _register_privileged_user(username="da-memory", email="da-memory@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-memory", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 11"),
    )
    monkeypatch.setattr(
        "app.data_agent.service._execute_cohort_query",
        lambda *, sql_text, target_country: {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 2,
            "preview_rows": [{"uid": "u1"}],
        },
    )

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询首贷用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200
    current_hash = approve.json()["current_sql"]["sql_hash"]

    execute = client.post(
        f"/api/data-agent/runs/{run_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert execute.status_code == 200

    with AuthSessionLocal() as db:
        rows = list(db.scalars(select(DataSqlExample).where(DataSqlExample.source_type == "approved_sql")).all())
        assert rows
        example = rows[-1]
        assert example.status == "draft"
        assert example.sql_hash == current_hash
        assert example.natural_language_request == "查询首贷用户"


def test_data_agent_failed_execute_opens_error_case_and_revise_resolves_it(client: TestClient, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_knowledge.models import DataSqlErrorCase

    _register_privileged_user(username="da-error", email="da-error@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-error", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 13"),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 200

    monkeypatch.setattr(
        "app.data_agent.service._execute_cohort_query",
        lambda *, sql_text, target_country: (_ for _ in ()).throw(RuntimeError("missing join key")),
    )
    with pytest.raises(RuntimeError, match="missing join key"):
        client.post(
            f"/api/data-agent/runs/{run_id}/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

    with AuthSessionLocal() as db:
        rows = list(db.scalars(select(DataSqlErrorCase).where(DataSqlErrorCase.source_type == "error_case")).all())
        assert rows
        error_case = rows[-1]
        assert error_case.status == "open"
        assert error_case.error_message == "missing join key"

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users WHERE risk_level = 'high' LIMIT 13"),
    )
    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "修正 join key"},
    )
    assert revise.status_code == 200

    with AuthSessionLocal() as db:
        rows = list(db.scalars(select(DataSqlErrorCase).where(DataSqlErrorCase.source_type == "error_case")).all())
        resolved = rows[-1]
        assert resolved.status == "resolved"
        assert resolved.fixed_sql_hash is not None
        assert resolved.fixed_sql_text == "SELECT uid FROM users WHERE risk_level = 'high' LIMIT 13"


def test_data_agent_review_without_view_sql_can_reject_but_cannot_approve_or_edit(client: TestClient, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal

    with AuthSessionLocal() as db:
        _create_role(
            db,
            code="review_only",
            name="Review Only",
            permission_codes=["data:query:review"],
        )

    _register_privileged_user(username="da-owner", email="da-owner@example.com", role_codes=["data_admin"])
    owner_token, _ = _login(client, "da-owner", "passw0rd123")
    _register_privileged_user(username="da-reviewer", email="da-reviewer@example.com", role_codes=["review_only"])
    reviewer_token, _ = _login(client, "da-reviewer", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 8"),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "natural_language_request": "创建一个待审 SQL",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    approve = client.post(
        f"/api/data-agent/runs/{run_id}/approve",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={},
    )
    assert approve.status_code == 403

    edit = client.post(
        f"/api/data-agent/runs/{run_id}/edit",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"sql_text": "SELECT uid FROM users LIMIT 9", "comment": "nope"},
    )
    assert edit.status_code == 403

    reject = client.post(
        f"/api/data-agent/runs/{run_id}/reject",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"comment": "先拒绝，等待更高权限复审"},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
