from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.database import AuthSessionLocal
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


def _settings(**overrides):
    defaults = {
        "hybrid_retrieval_enabled_raw": "1",
        "hybrid_retrieval_mode_raw": "hybrid_enabled",
        "hybrid_retrieval_source_namespace_raw": "m2b_legacy_v3",
        "hybrid_retrieval_vector_index_path_raw": "",
        "hybrid_retrieval_allow_countries_raw": "mx",
        "hybrid_retrieval_allow_project_ids_raw": "1",
        "hybrid_retrieval_vector_rank_limit_raw": "8",
        "hybrid_retrieval_family_score_thresholds_json_raw": (
            '{"catalog_table": 0.18, "catalog_field": 0.16, "glossary_term": 0.17, "sql_example": 0.15}'
        ),
        "hybrid_retrieval_family_caps_json_raw": (
            '{"catalog_table": 1, "catalog_field": 2, "glossary_term": 1, "sql_example": 1}'
        ),
        "hybrid_retrieval_total_vector_supplement_cap_raw": "3",
        "hybrid_retrieval_deterministic_pass_guard_raw": "1",
        "hybrid_retrieval_shadow_sample_rate_raw": "0.0",
        "hybrid_retrieval_hybrid_enabled_projects_raw": "1",
        "hybrid_retrieval_hybrid_enabled_eval_gate_raw": "1",
        "hybrid_retrieval_hybrid_enabled_kill_switch_raw": "0",
        "project_root": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _latest_trace(run_id: int) -> dict:
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        return trace


def _assert_public_payload_hides_internal_fields(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for field in (
        "hybrid_trace",
        "retrieval_snapshot_json",
        "accepted_supplements",
        "discarded_candidate_sql",
        "candidate_attempt",
    ):
        assert field not in serialized


def test_create_run_hybrid_enabled_success_trace_contract(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-obsv-success", email="da-hybrid-obsv-success@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-obsv-success", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 41"),
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
    trace = _latest_trace(create.json()["run_id"])
    assert {
        "configured_mode",
        "effective_mode",
        "fallback_applied",
        "fallback_reason",
        "kill_switch_applied",
        "rollout_gate_passed",
        "eval_gate_passed",
        "prompt_injection_mode",
        "final_generation_pass",
        "candidate_attempt",
    }.issubset(trace.keys())
    assert trace["effective_mode"] == "hybrid_enabled"
    assert trace["fallback_applied"] is False
    assert trace["kill_switch_applied"] is False
    assert trace["rollout_gate_passed"] is True
    assert trace["eval_gate_passed"] is True
    assert trace["prompt_injection_mode"] == "supplemental_candidates_v1"
    assert trace["final_generation_pass"] == "hybrid_enabled"
    assert trace["candidate_attempt"]["attempted_mode"] == "hybrid_enabled"


def test_create_run_hybrid_enabled_allowlist_miss_fallback_trace_contract(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-obsv-fallback",
        email="da-hybrid-obsv-fallback@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-obsv-fallback", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    monkeypatch.setattr(settings, "hybrid_retrieval_hybrid_enabled_projects_raw", "not-current-project", raising=False)
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
    trace = _latest_trace(create.json()["run_id"])
    assert trace["effective_mode"] == "deterministic_only"
    assert trace["fallback_applied"] is True
    assert trace["fallback_reason"] == "hybrid_enabled_rollout_not_allowlisted"
    assert trace["prompt_injection_mode"] == "none"
    assert trace["rollout_gate_passed"] is False


def test_create_run_public_api_hides_hybrid_observability_fields_on_success(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-obsv-public-success",
        email="da-hybrid-obsv-public-success@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-obsv-public-success", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 45"),
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
    _assert_public_payload_hides_internal_fields(create.json())


def test_create_run_public_api_hides_hybrid_observability_fields_on_fallback(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-obsv-public-fallback",
        email="da-hybrid-obsv-public-fallback@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-obsv-public-fallback", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    _enable_hybrid_enabled_settings(monkeypatch=monkeypatch, index_path=index_path)
    monkeypatch.setattr(settings, "hybrid_retrieval_hybrid_enabled_projects_raw", "not-current-project", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 47"),
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
    _assert_public_payload_hides_internal_fields(create.json())


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"hybrid_retrieval_hybrid_enabled_kill_switch_raw": "1"}, "hybrid_enabled_kill_switch_applied"),
        ({"hybrid_retrieval_enabled_raw": "0"}, "hybrid_disabled"),
        ({"hybrid_retrieval_mode_raw": "deterministic_only"}, "mode_forced_deterministic"),
    ],
)
def test_evaluate_effective_mode_rollback_controls_force_deterministic_only(
    overrides: dict[str, str],
    expected_reason: str,
) -> None:
    from app.data_agent.hybrid_runtime import evaluate_effective_mode, load_hybrid_config

    config = load_hybrid_config(_settings(**overrides))
    decision = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="1",
        run_type="cohort_query",
        request_key="stable-request",
        is_query_only_scope=True,
    )

    assert decision.effective_mode.value == "deterministic_only"
    assert decision.fallback_applied is True
    assert decision.fallback_reason is not None
    assert decision.fallback_reason.value == expected_reason
