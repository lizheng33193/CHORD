from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.database import AuthSessionLocal
from app.auth.models import AuditEvent
from app.data_agent.models import DataAgentSqlVersion


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


def _write_vector_index(path: Path) -> None:
    payload = {
        "schema_version": "m2b_vector_index_v1",
        "source_namespace": "m2b_legacy_v3",
        "vectorizer_name": "local_hashing_bow_v1",
        "vector_dim": 512,
        "vector_format": "sparse_hash_weight_map",
        "records": [
            {
                "record_id": "sha256:test-record-1",
                "source_key": "glossary.mx.mob1",
                "source_namespace": "m2b_legacy_v3",
                "asset_family": "glossary_term",
                "country": "mx",
                "title": "mob1",
                "vector": {"1": 0.8, "2": 0.6},
                "metadata": {"source_key": "glossary.mx.mob1"},
            },
            {
                "record_id": "sha256:test-record-2",
                "source_key": "field.mx.dwd_w_apply.withdraw_uuid",
                "source_namespace": "m2b_legacy_v3",
                "asset_family": "catalog_field",
                "country": "mx",
                "title": "dwd_w_apply.withdraw_uuid",
                "vector": {"3": 1.0},
                "metadata": {"source_key": "field.mx.dwd_w_apply.withdraw_uuid", "field_name": "withdraw_uuid"},
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_create_run_default_disabled_does_not_write_hybrid_trace(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-off", email="da-hybrid-off@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-off", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "0", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 5"),
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

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        snapshot = version.retrieval_snapshot_json or {}
        assert "hybrid_trace" not in snapshot


def test_create_run_hybrid_shadow_writes_trace_without_changing_prompt_or_api(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-on", email="da-hybrid-on@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-on", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    captured: dict[str, object] = {}

    def _fake_generate(**kwargs):
        captured["knowledge_prompt_context"] = kwargs.get("knowledge_prompt_context")
        return _stub_generate_result("SELECT uid FROM users LIMIT 7")

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
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
    body = create.json()
    assert "retrieval_snapshot_json" not in body["current_sql"]
    rendered = getattr(captured["knowledge_prompt_context"], "rendered_text", "")
    assert "hybrid_trace" not in rendered

    run_id = body["run_id"]
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["configured_mode"] == "hybrid_shadow"
        assert trace["effective_mode"] == "hybrid_shadow"
        assert trace["prompt_injection_mode"] == "none"
        assert "expected_tables" not in json.dumps(trace, ensure_ascii=False)
        assert "matched_expected" not in json.dumps(trace, ensure_ascii=False)
        assert "missing_expected" not in json.dumps(trace, ensure_ascii=False)
        assert len(trace["deterministic_candidates"]) <= 20
        assert len(trace["vector_candidates"]) <= 10
        assert len(trace["accepted_supplements"]) <= 3
        assert len(trace["rejected_candidates"]) <= 20


def test_create_run_hybrid_candidate_injects_supplemental_prompt_and_persists_final_candidate_result(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-candidate", email="da-hybrid-candidate@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-candidate", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    captured: dict[str, object] = {}

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        captured["rendered_text"] = getattr(prompt_context, "rendered_text", "")
        return _stub_generate_result("SELECT uid FROM users LIMIT 13")

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
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
    assert create.status_code == 201
    assert "Supplemental Hybrid Knowledge Candidates" in str(captured["rendered_text"])

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["configured_mode"] == "hybrid_candidate"
        assert trace["effective_mode"] == "hybrid_candidate"
        assert trace["prompt_injection_mode"] == "supplemental_candidates_v1"
        assert trace["final_generation_pass"] == "hybrid_candidate"
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["discarded"] is False
        assert trace["prompt_candidate_count"] > 0
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "hybrid_candidate",
            "prompt_injection_mode": "supplemental_candidates_v1",
            "source_context": "hybrid_candidate_attempt",
        }
        assert snapshot["context_hash"] == hashlib.sha256(str(captured["rendered_text"]).encode("utf-8")).hexdigest()


def test_revise_run_hybrid_shadow_writes_trace(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-revise", email="da-hybrid-revise@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-revise", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    responses = iter(
        [
            _stub_generate_result("SELECT uid FROM users LIMIT 9"),
            _stub_generate_result("SELECT uid FROM users LIMIT 11"),
        ]
    )

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", lambda *_args, **_kwargs: next(responses))

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

    revise = client.post(
        f"/api/data-agent/runs/{run_id}/revise",
        headers={"Authorization": f"Bearer {token}"},
        json={"comment": "请保留首贷语义"},
    )
    assert revise.status_code == 200

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["configured_mode"] == "hybrid_shadow"
        assert trace["effective_mode"] == "hybrid_shadow"


def test_create_run_hybrid_candidate_build_table_script_discards_candidate_and_reruns_deterministic(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-rerun", email="da-hybrid-rerun@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-rerun", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []
    responses = iter(
        [
            _stub_generate_result("CREATE TABLE tmp.hybrid_candidate AS SELECT uid FROM users", sql_kind="build_table_script"),
            _stub_generate_result("CREATE TABLE tmp.deterministic_rerun AS SELECT uid FROM users", sql_kind="build_table_script"),
        ]
    )

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return next(responses)

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
    )
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "请整理首贷用户 cohort",
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
        versions = db.scalars(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.asc())
        ).all()
        assert len(versions) == 1
        version = versions[-1]
        assert version.sql_text == "CREATE TABLE tmp.deterministic_rerun AS SELECT uid FROM users"
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["configured_mode"] == "hybrid_candidate"
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["prompt_injection_mode"] == "none"
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["fallback_reason"] == "unsupported_sql_kind"
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] == "post_sql_kind_mismatch"
        assert trace["candidate_attempt"]["output_sql_kind"] == "build_table_script"
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "deterministic_rerun",
            "prompt_injection_mode": "none",
            "source_context": "deterministic_rerun_attempt",
        }
        assert snapshot["context_hash"] == hashlib.sha256(prompts[1].encode("utf-8")).hexdigest()


def test_create_run_hybrid_candidate_generation_failure_falls_back_to_deterministic_rerun(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from data_acquisition_agent.orchestrator import OrchestratorError
    from data_acquisition_agent.schemas import ErrorType
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-failure", email="da-hybrid-failure@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-failure", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        rendered_text = getattr(prompt_context, "rendered_text", "")
        prompts.append(rendered_text)
        if "Supplemental Hybrid Knowledge Candidates" in rendered_text:
            raise OrchestratorError(ErrorType.UPSTREAM_LLM_ERROR, "candidate failed", request_id="candidate-failed")
        return _stub_generate_result("SELECT uid FROM users LIMIT 23")

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
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
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] == "candidate_generation_failed"


@pytest.mark.parametrize(
    ("case_label", "candidate_sql"),
    [("none", None), ("empty", ""), ("blank", "   ")],
)
def test_create_run_hybrid_candidate_empty_or_blank_sql_discards_candidate_and_reruns_deterministic(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
    case_label: str,
    candidate_sql: str | None,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    username = f"da-hybrid-empty-{case_label}"
    _register_privileged_user(username=username, email=f"{username}@example.com", role_codes=["data_admin"])
    token, _ = _login(client, username, "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []
    responses = iter(
        [
            {"sql": candidate_sql, "sql_kind": "query_only"},
            _stub_generate_result("SELECT uid FROM users LIMIT 29"),
        ]
    )

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return next(responses)

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
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
    assert create.status_code == 201
    assert len(prompts) == 2
    assert "Supplemental Hybrid Knowledge Candidates" in prompts[0]
    assert "Supplemental Hybrid Knowledge Candidates" not in prompts[1]

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        versions = db.scalars(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.asc())
        ).all()
        assert len(versions) == 1
        version = versions[-1]
        assert version.sql_text == "SELECT uid FROM users LIMIT 29"
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["prompt_injection_mode"] == "none"
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] == "candidate_sql_empty"
        assert trace["candidate_attempt"]["output_sql_hash"] is None
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "deterministic_rerun",
            "prompt_injection_mode": "none",
            "source_context": "deterministic_rerun_attempt",
        }
        assert snapshot["context_hash"] == hashlib.sha256(prompts[1].encode("utf-8")).hexdigest()


def test_create_run_hybrid_candidate_http_422_from_require_generated_sql_discards_candidate_and_reruns(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from app.data_agent.service import DataAgentService
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-http-422", email="da-hybrid-http-422@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-http-422", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []
    original_require_generated_sql = DataAgentService._require_generated_sql
    require_call_count = 0

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return _stub_generate_result("SELECT uid FROM users LIMIT 31")

    def _patched_require_generated_sql(generated, *, run_id=None):
        nonlocal require_call_count
        require_call_count += 1
        if require_call_count == 1:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "SQL_GENERATION_REQUIRED",
                    "stage": "data_agent_sql_generation",
                    "reason": "candidate returned unusable sql",
                    "retriable": True,
                },
            )
        return original_require_generated_sql(generated, run_id=run_id)

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
    )
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)
    monkeypatch.setattr(DataAgentService, "_require_generated_sql", staticmethod(_patched_require_generated_sql))

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
    assert require_call_count >= 2
    assert len(prompts) == 2
    assert "Supplemental Hybrid Knowledge Candidates" in prompts[0]
    assert "Supplemental Hybrid Knowledge Candidates" not in prompts[1]

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        versions = db.scalars(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.asc())
        ).all()
        assert len(versions) == 1
        version = versions[-1]
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] == "candidate_sql_empty"
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "deterministic_rerun",
            "prompt_injection_mode": "none",
            "source_context": "deterministic_rerun_attempt",
        }


def test_create_run_hybrid_candidate_invalid_candidate_plan_falls_back_to_deterministic_attempt(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from app.data_agent.sql_plan import SqlPlanValidationResult
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-plan-invalid", email="da-hybrid-plan-invalid@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-plan-invalid", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []
    original_validate = __import__("app.data_agent.service", fromlist=["validate_structured_sql_plan"]).validate_structured_sql_plan

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return _stub_generate_result("SELECT uid FROM users LIMIT 37")

    def _patched_validate_structured_sql_plan(*, plan, retrieval_snapshot):
        provenance = dict(retrieval_snapshot or {}).get("structured_sql_plan_provenance") or {}
        if provenance.get("source_context") == "hybrid_candidate_attempt":
            return SqlPlanValidationResult(
                valid=False,
                code="DATA_AGENT_SQL_PLAN_INVALID",
                reason="candidate plan invalid",
                missing=["candidate_plan"],
            )
        return original_validate(plan=plan, retrieval_snapshot=retrieval_snapshot)

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_candidate", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_source_namespace_raw", "m2b_legacy_v3", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "0.0", raising=False)
    monkeypatch.setattr(
        settings,
        "hybrid_retrieval_family_score_thresholds_json_raw",
        '{"catalog_table": 0.0, "catalog_field": 0.0, "glossary_term": 0.0, "sql_example": 0.0}',
        raising=False,
    )
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr("app.data_agent.service._generate_sql_response", _fake_generate)
    monkeypatch.setattr("app.data_agent.service.validate_structured_sql_plan", _patched_validate_structured_sql_plan)

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
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        assert trace is not None
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] == "candidate_generation_failed"
        assert snapshot["structured_sql_plan_provenance"] == {
            "plan_generation_pass": "deterministic_rerun",
            "prompt_injection_mode": "none",
            "source_context": "deterministic_rerun_attempt",
        }


def test_create_run_bucket_writeback_falls_back_with_unsupported_run_type_trace(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-writeback", email="da-hybrid-writeback@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-writeback", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result(
            "WITH target_users AS (SELECT uid FROM dwd_w_apply WHERE risk_level = 'high') "
            "SELECT b.uid, b.timestamp_, b.eventname FROM dwb_b1_data_burying_point b "
            "JOIN target_users t ON b.uid = t.uid"
        ),
    )

    create = client.post(
        "/api/data-agent/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "natural_language_request": "给首贷用户补齐 behavior 数据",
            "target_country": "mexico",
            "run_type": "bucket_writeback",
            "output_bucket": "behavior",
            "output_format": "json",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["fallback_reason"] == "unsupported_run_type"


def test_create_run_non_query_only_sql_marks_trace_as_unsupported_sql_kind(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-ddl", email="da-hybrid-ddl@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-ddl", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(index_path), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
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
            "natural_language_request": "建表保存首贷用户",
            "target_country": "mexico",
            "run_type": "cohort_query",
        },
    )
    assert create.status_code == 201
    run_id = create.json()["run_id"]

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["fallback_applied"] is True
        assert trace["fallback_reason"] == "unsupported_sql_kind"
        assert trace["prompt_injection_mode"] == "none"


def test_create_run_vector_index_failure_does_not_fail_request(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-bad-index", email="da-hybrid-bad-index@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-bad-index", "passw0rd123")

    broken_index = tmp_path / "broken_vector_index.json"
    broken_index.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_vector_index_path_raw", str(broken_index), raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 17"),
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

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["fallback_reason"] == "vector_backend_unavailable"


@pytest.mark.parametrize(
    ("setting_name", "setting_value"),
    [
        ("hybrid_retrieval_family_score_thresholds_json_raw", '{"catalog_field":"oops"}'),
        ("hybrid_retrieval_family_caps_json_raw", '{"catalog_field":"oops"}'),
    ],
)
def test_create_run_invalid_hybrid_config_does_not_fail_request(
    client: TestClient,
    monkeypatch,
    setting_name: str,
    setting_value: str,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username=f"da-hybrid-config-{setting_name}", email=f"{setting_name}@example.com", role_codes=["data_admin"])
    token, _ = _login(client, f"da-hybrid-config-{setting_name}", "passw0rd123")

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr(settings, setting_name, setting_value, raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 17"),
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

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        trace = (version.retrieval_snapshot_json or {}).get("hybrid_trace")
        assert trace is not None
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["fallback_reason"] == "config_invalid"


def test_create_run_audit_summary_preserves_audit_trace_unavailable_without_full_trace(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(username="da-hybrid-audit-fallback", email="da-hybrid-audit-fallback@example.com", role_codes=["data_admin"])
    token, _ = _login(client, "da-hybrid-audit-fallback", "passw0rd123")

    monkeypatch.setattr(settings, "hybrid_retrieval_enabled_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_mode_raw", "hybrid_shadow", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_countries_raw", "mx", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_allow_project_ids_raw", "1", raising=False)
    monkeypatch.setattr(settings, "hybrid_retrieval_shadow_sample_rate_raw", "1.0", raising=False)
    monkeypatch.setattr("app.data_agent.service.DataKnowledgeRetriever.retrieve", lambda *_args, **_kwargs: _retrieved_context())
    monkeypatch.setattr(
        "app.data_agent.service.build_shadow_trace",
        lambda **_kwargs: __import__("app.data_agent.hybrid_runtime", fromlist=["ShadowTraceBuildResult"]).ShadowTraceBuildResult(
            trace=None,
            audit_summary={
                "hybrid_configured_mode": "hybrid_shadow",
                "hybrid_effective_mode": "deterministic_only",
                "hybrid_fallback_reason": "audit_trace_unavailable",
                "hybrid_trace_present": False,
            },
        ),
    )
    monkeypatch.setattr(
        "app.data_agent.service._generate_sql_response",
        lambda *_args, **_kwargs: _stub_generate_result("SELECT uid FROM users LIMIT 21"),
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

    with AuthSessionLocal() as db:
        version = db.scalar(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.desc())
        )
        assert version is not None
        assert "hybrid_trace" not in (version.retrieval_snapshot_json or {})
        audit_event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.resource_id == run_id, AuditEvent.event_type == "data.query.run_created")
            .order_by(AuditEvent.id.desc())
        )
        assert audit_event is not None
        metadata = audit_event.metadata_json or {}
        assert metadata["hybrid_fallback_reason"] == "audit_trace_unavailable"
        assert metadata["hybrid_trace_present"] is False
        assert metadata["hybrid_effective_mode"] == "deterministic_only"
        assert metadata["hybrid_configured_mode"] == "hybrid_shadow"
