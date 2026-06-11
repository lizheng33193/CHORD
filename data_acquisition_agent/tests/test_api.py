"""test_api — Step 4 TDD."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from data_acquisition_agent.api import router
from data_acquisition_agent import api as api_mod
from data_acquisition_agent.orchestrator import OrchestratorError
from data_acquisition_agent.schemas import ErrorType


def _client():
    app = FastAPI(); app.include_router(router); return TestClient(app)


def test_generate_422_on_invalid_country_enum():
    # target_country="atlantis" 不在 TargetCountry 枚举内，FastAPI/Pydantic 自动 422
    r = _client().post("/api/data-acquisition/generate",
        json={"natural_language_request": "x", "target_country": "atlantis"})
    assert r.status_code == 422


class _StubMC:
    mode = "mock"; model_name = "stub"
    def generate_structured(self, **kw):
        return {"status": "ok", "structured_result": kw.get("fallback_result", {}),
                "model_name": "stub", "prompt_preview": ""}


def test_generate_400_on_placeholder_country(monkeypatch):
    # indonesia.yaml 当前为占位符 manifest（business_logic_md 等仍是 <PLACEHOLDER...）
    # 必须 monkeypatch orchestrator 避免 ModelClient.__init__ 依赖环境变量
    from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
    monkeypatch.setattr(api_mod, "_get_orchestrator",
        lambda: DataAcquisitionOrchestrator(model_client=_StubMC()))
    r = _client().post("/api/data-acquisition/generate",
        json={"natural_language_request": "x", "target_country": "indonesia"})
    assert r.status_code == 400
    assert r.json()["error_type"] == "bad_request"
    assert r.json()["request_id"]


def test_generate_422_on_credential_leak(monkeypatch):
    class Boom:
        def generate(self, req):
            raise OrchestratorError(ErrorType.CREDENTIAL_LEAK, "x", request_id="rid-test-1")
    monkeypatch.setattr(api_mod, "_get_orchestrator", lambda: Boom())
    r = _client().post("/api/data-acquisition/generate", json={"natural_language_request": "x", "target_country": "mexico"})
    assert r.status_code == 422
    body = r.json()
    assert body["error_type"] == "credential_leak"
    assert body["request_id"] == "rid-test-1"


import pytest
@pytest.mark.parametrize("etype,expected_status", [
    (ErrorType.BAD_REQUEST,                400),
    (ErrorType.PROMPT_TOO_LARGE,           400),
    (ErrorType.SCHEMA_VALIDATION_FAILED,   422),
    (ErrorType.CREDENTIAL_LEAK,            422),
    (ErrorType.DANGEROUS_CODE,             422),
    (ErrorType.DDL_POLICY_VIOLATION,       422),
    (ErrorType.UPSTREAM_LLM_ERROR,         502),
])
def test_error_type_to_http_status_mapping(monkeypatch, etype, expected_status):
    class Boom:
        def generate(self, req):
            raise OrchestratorError(etype, "x", request_id="rid-map")
    monkeypatch.setattr(api_mod, "_get_orchestrator", lambda: Boom())
    r = _client().post("/api/data-acquisition/generate",
        json={"natural_language_request": "x", "target_country": "mexico"})
    assert r.status_code == expected_status
    assert r.json()["error_type"] == etype.value
    assert r.json()["request_id"] == "rid-map"


def test_main_app_mounts_da_router():
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/data-acquisition/generate" in paths
    assert "/api/analyze" in paths or any(p.startswith("/api/analyze") for p in paths)
