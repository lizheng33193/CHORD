from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from data_acquisition_agent.orchestrator import OrchestratorError
from data_acquisition_agent.schemas import ErrorType
from sqlalchemy import func
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


def _stub_generate_result(sql: str | None, sql_kind: str = "query_only", *, python: str | None = None) -> dict:
    return {
        "request_id": "gen-001",
        "target_country": "mexico",
        "reasoning_summary": "stub",
        "sql": sql,
        "sql_kind": sql_kind,
        "python": python,
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
        captured["knowledge_prompt_context"] = kwargs.get("knowledge_prompt_context")
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
    assert captured["knowledge_prompt_context"] is not None
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
    assert calls[1]["knowledge_prompt_context"] is not None


def test_data_agent_create_run_blocks_unresolved_placeholders(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-placeholder", email="da-placeholder@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-placeholder", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users WHERE uid IN (<target_users>)"),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询指定 cohort",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["current_sql"]["safety_status"] == "blocked"
    assert any("placeholder" in reason.lower() for reason in body["current_sql"]["safety_result"]["blocked_reasons"])

    approve = client.post(
        f"/api/data-agent/runs/{body['run_id']}/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert approve.status_code == 409


def test_data_agent_create_run_does_not_block_normal_sql_comparisons(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-safe-compare", email="da-safe-compare@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-safe-compare", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT uid FROM users WHERE amount < 100 AND dt > '2026-01-01'"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询小额用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    assert create.json()["current_sql"]["safety_status"] == "passed"


def test_data_agent_create_run_returns_422_without_persisting_run_on_structured_output_failure(client: TestClient, monkeypatch) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_agent.models import DataAgentRun

    _register_privileged_user(username="da-create-422", email="da-create-422@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-create-422", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, "model output failed schema validation", request_id="rid-create-422")
        ),
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
    assert create.status_code == 422
    body = create.json()
    assert body["detail"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["detail"]["stage"] == "structured_output"
    assert "raw" not in str(body).lower()

    with AuthSessionLocal() as db:
        run_count = db.scalar(select(func.count()).select_from(DataAgentRun))
        assert run_count == 0


@pytest.mark.parametrize("sql_value", [None, "", "   "])
def test_data_agent_create_run_rejects_non_sql_generation_results(
    client: TestClient,
    monkeypatch,
    sql_value: str | None,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_agent.models import DataAgentRun, DataAgentSqlVersion

    _register_privileged_user(username="da-create-no-sql", email="da-create-no-sql@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-create-no-sql", "passw0rd123")

    with AuthSessionLocal() as db:
        before_runs = db.scalar(select(func.count()).select_from(DataAgentRun))
        before_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(sql_value, python="print('x')"),
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
    assert create.status_code == 422
    body = create.json()
    assert body["detail"]["code"] == "SQL_GENERATION_REQUIRED"
    assert body["detail"]["stage"] == "data_agent_sql_generation"
    assert body["detail"]["retriable"] is True
    assert "python" not in str(body).lower()
    assert "prompt" not in str(body).lower()
    assert "context" not in str(body).lower()

    with AuthSessionLocal() as db:
        after_runs = db.scalar(select(func.count()).select_from(DataAgentRun))
        after_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert after_runs == before_runs
        assert after_versions == before_versions


def test_data_agent_revise_run_returns_422_without_mutating_current_sql(client: TestClient, monkeypatch) -> None:
    _register_privileged_user(username="da-revise-422", email="da-revise-422@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-revise-422", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 4"),
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
    original_hash = create.json()["current_sql"]["sql_hash"]

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, "model output failed schema validation", request_id="rid-revise-422")
        ),
    )
    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "请改成最近 7 天"},
    )
    assert revise.status_code == 422
    body = revise.json()
    assert body["detail"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["detail"]["run_id"] == run_id

    detail = client.get(
        f"/api/data-agent/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["current_sql"]["sql_hash"] == original_hash


def test_data_agent_revise_run_rejects_non_sql_generation_results_without_creating_version(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_agent.models import DataAgentSqlVersion

    _register_privileged_user(username="da-revise-no-sql", email="da-revise-no-sql@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-revise-no-sql", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 4"),
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
    original_hash = approve.json()["current_sql"]["sql_hash"]
    original_approved_hash = approve.json()["approved_sql_hash"]

    with AuthSessionLocal() as db:
        before_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(None, python="print('x')"),
    )
    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "请改成最近 7 天"},
    )
    assert revise.status_code == 422
    body = revise.json()
    assert body["detail"]["code"] == "SQL_GENERATION_REQUIRED"
    assert body["detail"]["stage"] == "data_agent_sql_generation"
    assert body["detail"]["run_id"] == run_id
    assert body["detail"]["retriable"] is True
    assert "python" not in str(body).lower()
    assert "prompt" not in str(body).lower()
    assert "context" not in str(body).lower()

    with AuthSessionLocal() as db:
        after_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert after_versions == before_versions

    detail = client.get(
        f"/api/data-agent/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["current_sql"]["sql_hash"] == original_hash
    assert detail_payload["approved_sql_hash"] == original_approved_hash
    assert detail_payload["status"] == "approved"


def test_data_agent_bucket_writeback_create_returns_specific_422_for_under_specified_request(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.auth.database import AuthSessionLocal
    from app.data_agent.models import DataAgentRun, DataAgentSqlVersion

    _register_privileged_user(username="da-writeback-422", email="da-writeback-422@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-writeback-422", "passw0rd123")

    with AuthSessionLocal() as db:
        before_runs = db.scalar(select(func.count()).select_from(DataAgentRun))
        before_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, "model output failed schema validation", request_id="rid-writeback-create")
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior",
            "target_country": "mexico",
            "run_type": "bucket_writeback",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert create.status_code == 422
    body = create.json()
    assert body["detail"]["code"] == "DATA_AGENT_WRITEBACK_REQUIRES_COHORT"
    assert body["detail"]["stage"] == "data_agent_sql_generation"
    assert body["detail"]["retriable"] is True

    with AuthSessionLocal() as db:
        after_runs = db.scalar(select(func.count()).select_from(DataAgentRun))
        after_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert after_runs == before_runs
        assert after_versions == before_versions


@pytest.mark.parametrize(
    "request_text",
    [
        "帮我查询并写回 behavior",
        "找一下行为数据并写回",
    ],
)
def test_data_agent_bucket_writeback_generic_verbs_still_require_explicit_cohort(
    client: TestClient,
    monkeypatch,
    request_text: str,
) -> None:
    _register_privileged_user(username="da-writeback-generic", email="da-writeback-generic@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-writeback-generic", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, "model output failed schema validation", request_id="rid-writeback-generic")
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": request_text,
            "target_country": "mexico",
            "run_type": "bucket_writeback",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert create.status_code == 422
    body = create.json()
    assert body["detail"]["code"] == "DATA_AGENT_WRITEBACK_REQUIRES_COHORT"
    assert body["detail"]["stage"] == "data_agent_sql_generation"
    assert body["detail"]["retriable"] is True


def test_data_agent_bucket_writeback_revise_returns_specific_422_without_mutating_current_sql(
    client: TestClient,
    monkeypatch,
) -> None:
    from datetime import datetime

    from app.auth.database import AuthSessionLocal
    from app.data_agent.models import DataAgentRun, DataAgentSqlVersion

    _register_privileged_user(username="da-writeback-revise", email="da-writeback-revise@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-writeback-revise", "passw0rd123")

    run_id = "writeback-fu3-revise"
    with AuthSessionLocal() as db:
        run = DataAgentRun(
            run_id=run_id,
            user_id=1,
            project_id=1,
            country="mx",
            run_type="bucket_writeback",
            natural_language_request="用 Data Agent 补齐这些用户的 behavior 数据并写回 behavior",
            status="approved",
            sql_kind="query_only",
            approved_sql_hash="orig-hash",
            output_bucket="behavior",
            output_format="json",
            uid_column="uid",
            overwrite=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        version = DataAgentSqlVersion(
            run_id=run_id,
            version_no=1,
            sql_text="SELECT uid, eventname FROM dwb_b1_data_burying_point WHERE uid IN ('u1')",
            sql_hash="orig-hash",
            source="agent_generated",
            sql_kind="query_only",
            safety_status="passed",
            safety_result_json={
                "status": "passed",
                "risk_level": "low",
                "blocked_reasons": [],
                "warnings": [],
                "normalized_sql": "SELECT uid, eventname FROM dwb_b1_data_burying_point WHERE uid IN ('u1')",
                "sql_hash": "orig-hash",
                "target_country": "mx",
            },
            retrieval_snapshot_json=None,
            created_by="da-writeback-revise",
        )
        db.add(version)
        db.flush()
        run.current_sql_version_id = version.id
        run.approved_sql_version_id = version.id
        db.commit()
        before_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))

    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED, "model output failed schema validation", request_id="rid-writeback-revise")
        ),
    )
    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "请调整写回逻辑"},
    )
    assert revise.status_code == 422
    body = revise.json()
    assert body["detail"]["code"] == "DATA_AGENT_WRITEBACK_REQUIRES_COHORT"
    assert body["detail"]["stage"] == "data_agent_sql_generation"
    assert body["detail"]["run_id"] == run_id
    assert body["detail"]["retriable"] is True

    with AuthSessionLocal() as db:
        after_versions = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert after_versions == before_versions

    detail = client.get(
        f"/api/data-agent/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["current_sql"]["sql_hash"] == "orig-hash"
    assert detail_payload["approved_sql_hash"] == "orig-hash"
    assert detail_payload["status"] == "approved"


def test_data_agent_adds_unsupported_field_warning_without_blocking_run(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-field-risk", email="da-field-risk@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-field-risk", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "risk_level", "apply_time"],
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT user_uuid FROM dwd_w_apply WHERE risk_level = 'high' AND apply_time >= date_sub(current_date, 7)"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询最近 7 天高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["current_sql"]["safety_status"] == "passed"
    warnings = body["current_sql"]["safety_result"]["warnings"]
    assert any(item["category"] == "UNSUPPORTED_FIELD" for item in warnings)
    assert any(item["field"] == "user_uuid" and item["table"] == "dwd_w_apply" for item in warnings)


def test_data_agent_adds_non_canonical_field_warning_without_blocking_run(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-noncanonical", email="da-noncanonical@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-noncanonical", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "user_uuid", "risk_level", "apply_time", "apply_create_at"],
                },
                "canonical_alternative_to_preferred_by_table": {
                    "dwd_w_apply": {
                        "user_uuid": "uid",
                        "apply_create_at": "apply_time",
                    },
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT user_uuid, apply_create_at FROM hive.dwd.dwd_w_apply "
            "WHERE risk_level = 'high' AND apply_create_at >= date_sub(current_date, 7)"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询最近 7 天高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    body = create.json()
    assert body["current_sql"]["safety_status"] == "passed"
    warnings = body["current_sql"]["safety_result"]["warnings"]
    assert any(
        item["category"] == "NON_CANONICAL_FIELD"
        and item["field"] == "user_uuid"
        and item["preferred_field"] == "uid"
        and item["table"] == "dwd_w_apply"
        for item in warnings
    )
    assert any(
        item["category"] == "NON_CANONICAL_FIELD"
        and item["field"] == "apply_create_at"
        and item["preferred_field"] == "apply_time"
        and item["table"] == "dwd_w_apply"
        for item in warnings
    )
    assert not any(item["category"] == "UNSUPPORTED_FIELD" for item in warnings)


def test_data_agent_preferred_field_does_not_trigger_non_canonical_warning(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-preferred", email="da-preferred@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-preferred", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "user_uuid", "risk_level", "apply_time", "apply_create_at"],
                },
                "canonical_alternative_to_preferred_by_table": {
                    "dwd_w_apply": {
                        "user_uuid": "uid",
                        "apply_create_at": "apply_time",
                    },
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT uid, apply_time FROM dwd_w_apply "
            "WHERE risk_level = 'high' AND apply_time >= date_sub(current_date, 7)"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询最近 7 天高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    warnings = create.json()["current_sql"]["safety_result"]["warnings"]
    assert not any(item["category"] == "NON_CANONICAL_FIELD" for item in warnings)


def test_data_agent_does_not_flag_interval_units_as_unsupported_fields(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-interval-safe", email="da-interval-safe@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-interval-safe", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "risk_level", "apply_time"],
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT uid FROM hive.dwd.dwd_w_apply "
            "WHERE risk_level = 'high' "
            "AND apply_time >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询最近 7 天高风险用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    warnings = create.json()["current_sql"]["safety_result"]["warnings"]
    assert not any(item["field"] in {"interval", "day"} for item in warnings)


def test_data_agent_does_not_flag_cte_alias_as_unsupported_field(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-cte-safe", email="da-cte-safe@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-cte-safe", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "apply_time"],
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "WITH target_users AS ("
            " SELECT uid, MIN(apply_time) AS first_apply_time"
            " FROM dwd_w_apply GROUP BY uid"
            ") "
            "SELECT uid, first_apply_time FROM target_users"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询首贷用户首次申请时间",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    warnings = create.json()["current_sql"]["safety_result"]["warnings"]
    assert not any(item["category"] == "UNSUPPORTED_FIELD" for item in warnings)


def test_data_agent_does_not_flag_select_or_aggregate_alias_as_unsupported_field(
    client: TestClient,
    monkeypatch,
) -> None:
    _register_privileged_user(username="da-alias-safe", email="da-alias-safe@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-alias-safe", "passw0rd123")

    monkeypatch.setattr(
        "app.data_agent.service.DataAgentService._build_generation_context",
        lambda self, **_kwargs: (
            None,
            None,
            {
                "country": "mx",
                "project_id": 1,
                "grounded_fields_by_table": {
                    "dwd_w_apply": ["uid", "apply_time"],
                },
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "SELECT uid AS user_id, MIN(apply_time) AS first_apply_time "
            "FROM dwd_w_apply GROUP BY uid"
        ),
    )
    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询首贷用户首次申请时间",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    warnings = create.json()["current_sql"]["safety_result"]["warnings"]
    assert not any(item["category"] == "UNSUPPORTED_FIELD" for item in warnings)


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
