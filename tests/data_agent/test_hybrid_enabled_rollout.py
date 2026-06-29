from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select

from app.auth.database import AuthSessionLocal
from app.data_agent.models import DataAgentRun
from app.data_agent.models import DataAgentSqlVersion
from tests.data_agent.test_hybrid_shadow_runtime import _write_vector_index


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "auth_database_url", f"sqlite:///{tmp_path / 'auth.sqlite3'}", raising=False)
    monkeypatch.setattr(settings, "auth_jwt_secret", "test-secret-for-data-agent", raising=False)
    monkeypatch.setattr(settings, "default_admin_username", "admin", raising=False)
    monkeypatch.setattr(settings, "default_admin_email", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "default_admin_password", "admin123456", raising=False)

    from app.auth.database import create_auth_schema, reset_auth_engine
    from app.auth.seed import seed_auth_data
    from app.main import app

    reset_auth_engine()
    create_auth_schema()
    with AuthSessionLocal() as db:
        seed_auth_data(db)

    with TestClient(app) as test_client:
        yield test_client

    reset_auth_engine()


def _enable_hybrid_enabled_settings(*, monkeypatch, index_path: Path, project_id: str = "1") -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_enabled", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", project_id, raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_hybrid_enabled_projects_raw", project_id, raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_hybrid_enabled_eval_gate_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_hybrid_enabled_kill_switch_raw", "0", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
    )


def _runtime_settings(*, index_path: Path, project_id: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        hybrid_retrieval_enabled_raw="1",
        hybrid_retrieval_mode_raw="hybrid_enabled",
        hybrid_retrieval_source_namespace_raw="m2b_legacy_v3",
        hybrid_retrieval_vector_index_path_raw=str(index_path),
        hybrid_retrieval_allow_countries_raw="mx",
        hybrid_retrieval_allow_project_ids_raw=project_id,
        hybrid_retrieval_vector_rank_limit_raw="8",
        hybrid_retrieval_family_score_thresholds_json_raw='{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        hybrid_retrieval_family_caps_json_raw='{"catalog_table": 1, "catalog_field": 2, "glossary_term": 1, "sql_example": 1}',
        hybrid_retrieval_total_vector_supplement_cap_raw="3",
        hybrid_retrieval_deterministic_pass_guard_raw="1",
        hybrid_retrieval_hybrid_enabled_projects_raw=project_id,
        hybrid_retrieval_hybrid_enabled_eval_gate_raw="1",
        hybrid_retrieval_hybrid_enabled_kill_switch_raw="0",
        hybrid_retrieval_shadow_sample_rate_raw="0.0",
        project_root=Path("/Users/zhengli/Desktop/workspace/CHORD"),
    )


def test_create_run_hybrid_enabled_injects_prompt_and_persists_enabled_provenance(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-enabled", email="da-hybrid-enabled@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-enabled", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    captured: dict[str, str] = {}

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        captured["rendered_text"] = getattr(prompt_context, "rendered_text", "")
        return _stub_generate_result("SELECT uid FROM users LIMIT 33")

    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

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
    assert "Supplemental Hybrid Knowledge Candidates" in captured["rendered_text"]

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "hybrid_enabled"
        assert trace["final_generation_pass"] == "hybrid_enabled"
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["attempted_mode"] == "hybrid_enabled"
        assert trace["prompt_injection_mode"] == "supplemental_candidates_v1"
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "hybrid_enabled",
            "prompt_injection_mode": "supplemental_candidates_v1",
            "source_context": "hybrid_enabled_attempt",
        }
        assert snapshot["context_hash"] == hashlib.sha256(captured["rendered_text"].encode("utf-8")).hexdigest()


def test_create_run_hybrid_enabled_falls_back_when_no_accepted_supplements(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-enabled-no-supplements",
        email="da-hybrid-enabled-no-supplements@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-enabled-no-supplements", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    prompts: list[str] = []

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return _stub_generate_result("SELECT uid FROM users LIMIT 35")

    monkeypatch.setattr(
        "app.data_agent.service.DataKnowledgeRetriever.retrieve",
        lambda *_args, **_kwargs: _retrieved_context(include_behavior_table=False),
    )
    monkeypatch.setattr("app.data_agent.hybrid_runtime._select_vector_supplements", lambda **_kwargs: ([], []))
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

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
    assert len(prompts) == 1
    assert "Supplemental Hybrid Knowledge Candidates" not in prompts[0]

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["fallback_reason"] == "hybrid_enabled_no_accepted_supplements"


def test_create_run_hybrid_enabled_blank_sql_reruns_deterministic(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-enabled-rerun",
        email="da-hybrid-enabled-rerun@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-enabled-rerun", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    prompts: list[str] = []
    responses = iter(
        [
            _stub_generate_result("   "),
            _stub_generate_result("SELECT uid FROM users LIMIT 39"),
        ]
    )

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return next(responses)

    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

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
    assert len(prompts) == 2
    assert "Supplemental Hybrid Knowledge Candidates" in prompts[0]
    assert "Supplemental Hybrid Knowledge Candidates" not in prompts[1]

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["candidate_attempt"]["attempted_mode"] == "hybrid_enabled"
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["effective_mode"] == "deterministic_only"


def test_create_run_hybrid_enabled_rerun_failure_surfaces_final_error_without_persisting(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from data_acquisition_agent.orchestrator import OrchestratorError
    from data_acquisition_agent.schemas import ErrorType
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-enabled-rerun-fail",
        email="da-hybrid-enabled-rerun-fail@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-enabled-rerun-fail", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    prompts: list[str] = []

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        rendered_text = getattr(prompt_context, "rendered_text", "")
        prompts.append(rendered_text)
        if "Supplemental Hybrid Knowledge Candidates" in rendered_text:
            return _stub_generate_result("   ")
        raise OrchestratorError(
            ErrorType.UPSTREAM_LLM_ERROR,
            "deterministic rerun final failure",
            request_id="rid-hybrid-enabled-rerun-final-failure",
        )

    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "查询首贷用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )

    assert create.status_code == 502
    assert len(prompts) == 2

    body = create.json()
    assert body["detail"]["reason"] == "deterministic rerun final failure"
    with AuthSessionLocal() as db:
        run_count = db.scalar(select(func.count()).select_from(DataAgentRun))
        version_count = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert run_count == 0
        assert version_count == 0


def test_create_run_hybrid_enabled_keeps_public_api_clean(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-enabled-api-clean",
        email="da-hybrid-enabled-api-clean@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-enabled-api-clean", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)

    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 43"),
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
    rendered = create.text
    assert "hybrid_trace" not in rendered
    assert "accepted_supplements" not in rendered
    assert "retrieval_snapshot_json" not in rendered


def test_build_shadow_trace_hybrid_enabled_vector_unavailable_falls_back(tmp_path: Path) -> None:
    from app.data_agent.hybrid_runtime import build_shadow_trace
    from tests.data_agent.test_api import _retrieved_context

    result = build_shadow_trace(
        settings=_runtime_settings(index_path=tmp_path / "missing-vector-index.json"),
        natural_language_request="查询首贷用户",
        country="mx",
        project_id="1",
        run_type="cohort_query",
        output_bucket=None,
        retrieved_context=_retrieved_context(),
        request_key="vector-unavailable",
    )

    assert result.trace is not None
    assert result.trace["effective_mode"] == "deterministic_only"
    assert result.trace["fallback_reason"] == "hybrid_enabled_vector_unavailable"
    assert result.audit_summary["hybrid_fallback_reason"] == "hybrid_enabled_vector_unavailable"


def test_build_shadow_trace_hybrid_enabled_audit_unavailable_returns_no_trace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.data_agent.hybrid_runtime import build_shadow_trace
    from tests.data_agent.test_api import _retrieved_context

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)

    def _boom(*_args, **_kwargs):
        raise TypeError("trace serialization failed")

    monkeypatch.setattr("app.data_agent.hybrid_runtime.json.dumps", _boom)

    result = build_shadow_trace(
        settings=_runtime_settings(index_path=index_path),
        natural_language_request="查询首贷用户",
        country="mx",
        project_id="1",
        run_type="cohort_query",
        output_bucket=None,
        retrieved_context=_retrieved_context(),
        request_key="audit-unavailable",
    )

    assert result.trace is None
    assert result.audit_summary["hybrid_fallback_reason"] == "hybrid_enabled_audit_unavailable"
