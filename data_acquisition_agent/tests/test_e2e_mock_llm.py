"""test_e2e_mock_llm — Step 4 TDD."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from data_acquisition_agent.api import router
from data_acquisition_agent import api as api_mod
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator


class StubModelClient:
    mode = "mock"; model_name = "stub-mock"
    def generate_structured(self, **kw):
        return {"status": "ok", "model_name": "stub-mock", "prompt_preview": "",
            "structured_result": {
                "reasoning_summary": "mob1 mexico extract",
                "sql": "SELECT uid FROM dwb.dwb_b1_data_burying_point WHERE channel='MEX017' LIMIT 100",
                "sql_kind": "query_only", "python": None,
                "audit_report": {"high_risk_ddl": False, "final_verdict": "ok"}}}


def test_e2e_mock_llm_mexico_happy(monkeypatch):
    monkeypatch.setattr(api_mod, "_get_orchestrator",
        lambda: DataAcquisitionOrchestrator(model_client=StubModelClient()))
    app = FastAPI(); app.include_router(router); c = TestClient(app)
    r = c.post("/api/data-acquisition/generate",
        json={"natural_language_request": "建表墨西哥 mob1 取 100 uid", "target_country": "mexico"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "MEX017" in body["sql"]
    assert body["sql_kind"] == "query_only"
    assert body["audit_report"]["high_risk_ddl"] is False
    assert len(body["metadata"]["knowledge_files_loaded"]) >= 3
    assert any("system_prompt" in f for f in body["metadata"]["knowledge_files_loaded"])
