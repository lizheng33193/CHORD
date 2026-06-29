from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy import select

from app.auth.database import AuthSessionLocal
from app.data_agent.models import DataAgentRun
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


def test_create_run_hybrid_candidate_invalid_candidate_plan_discards_candidate_and_persists_only_rerun(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-preflight-plan-invalid",
        email="da-hybrid-preflight-plan-invalid@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-preflight-plan-invalid", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
    prompts: list[str] = []
    service_module = __import__("app.data_agent.service", fromlist=["build_structured_sql_plan"])
    original_build_structured_sql_plan = service_module.build_structured_sql_plan

    def _patched_build_structured_sql_plan(**kwargs):
        plan = original_build_structured_sql_plan(**kwargs)
        provenance = dict(kwargs.get("retrieval_snapshot") or {}).get("structured_sql_plan_provenance") or {}
        if provenance.get("source_context") != "hybrid_candidate_attempt":
            return plan
        return plan.model_copy(
            update={
                "task_type": "bucket_writeback",
                "output_bucket": "behavior",
                "source_tables": ["dwd_w_apply"],
                "target_cohort_conditions": [],
                "uid_boundary_required": False,
            }
        )

    def _fake_generate(**kwargs):
        prompt_context = kwargs.get("knowledge_prompt_context")
        prompts.append(getattr(prompt_context, "rendered_text", ""))
        return _stub_generate_result("SELECT uid FROM users LIMIT 41")

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
    monkeypatch.setattr("app.data_agent.service.build_structured_sql_plan", _patched_build_structured_sql_plan)
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
    assert create.json()["current_sql"]["sql_text"] == "SELECT uid FROM users LIMIT 41"
    assert "candidate_attempt" not in create.text
    assert "hybrid_trace" not in create.text

    run_id = create.json()["run_id"]
    with AuthSessionLocal() as db:
        versions = db.scalars(
            select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(DataAgentSqlVersion.id.asc())
        ).all()
        assert len(versions) == 1
        version = versions[0]
        assert version.sql_text == "SELECT uid FROM users LIMIT 41"
        snapshot = version.retrieval_snapshot_json or {}
        trace = snapshot.get("hybrid_trace")
        provenance = snapshot.get("structured_sql_plan_provenance")

        assert trace is not None
        assert trace["candidate_attempt"]["attempted"] is True
        assert trace["candidate_attempt"]["discarded"] is True
        assert trace["candidate_attempt"]["discard_reason"] in {"candidate_generation_failed", "candidate_plan_invalid"}
        assert trace["effective_mode"] == "deterministic_only"
        assert trace["final_generation_pass"] == "deterministic_rerun"
        assert trace["prompt_injection_mode"] == "none"

        assert provenance == {
            "plan_generation_pass": "deterministic_rerun",
            "prompt_injection_mode": "none",
            "source_context": "deterministic_rerun_attempt",
        }
        assert trace["final_generation_pass"] == provenance["plan_generation_pass"]
        assert trace["prompt_injection_mode"] == provenance["prompt_injection_mode"]


def test_create_run_hybrid_candidate_rerun_failure_surfaces_final_error_without_persisting_run(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from data_acquisition_agent.orchestrator import OrchestratorError
    from data_acquisition_agent.schemas import ErrorType
    from tests.data_agent.test_api import _login, _register_privileged_user, _retrieved_context, _stub_generate_result

    _register_privileged_user(
        username="da-hybrid-preflight-rerun-failure",
        email="da-hybrid-preflight-rerun-failure@example.com",
        role_codes=["data_admin"],
    )
    token, _ = _login(client, "da-hybrid-preflight-rerun-failure", "passw0rd123")

    index_path = tmp_path / "vector_index.json"
    _write_vector_index(index_path)
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
            request_id="rid-deterministic-rerun-final-failure",
        )

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
    assert create.status_code == 502
    assert len(prompts) == 2
    assert "Supplemental Hybrid Knowledge Candidates" in prompts[0]
    assert "Supplemental Hybrid Knowledge Candidates" not in prompts[1]

    body = create.json()
    assert body["detail"]["code"] == "UPSTREAM_LLM_ERROR"
    assert body["detail"]["stage"] == "generation"
    assert body["detail"]["reason"] == "deterministic rerun final failure"
    assert "current_sql" not in body

    with AuthSessionLocal() as db:
        run_count = db.scalar(select(func.count()).select_from(DataAgentRun))
        version_count = db.scalar(select(func.count()).select_from(DataAgentSqlVersion))
        assert run_count == 0
        assert version_count == 0
