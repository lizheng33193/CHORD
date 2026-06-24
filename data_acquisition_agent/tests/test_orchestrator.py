"""test_orchestrator — Step 4 TDD."""

import pytest, re
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator, OrchestratorError
from data_acquisition_agent.schemas import GenerateRequest, ErrorType


class StubModelClient:
    mode = "mock"; model_name = "stub"
    def __init__(self, payload, status="ok"): self._p = payload; self._s = status
    def generate_structured(self, **kw):
        return {"status": self._s, "structured_result": self._p, "model_name": "stub", "prompt_preview": ""}


PAYLOAD_OK = {"reasoning_summary": "x", "sql": "SELECT 1", "sql_kind": "query_only",
              "python": None, "audit_report": {"high_risk_ddl": False, "final_verdict": "ok"}}


def test_happy_path():
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(PAYLOAD_OK))
    resp = orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert resp.sql == "SELECT 1"
    assert resp.metadata.knowledge_files_loaded
    # request_id 是 uuid4 形态
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", resp.request_id)
    # demo0 已预脱敏，运行时 hits 可能为 0；只断非负，避免环境耦合（与 Task 5.2 同策略）
    assert isinstance(resp.metadata.redaction_events, int)
    assert resp.metadata.redaction_events >= 0
    assert resp.metadata.danger_scan_events == 0  # python is None, sql 干净


def test_generate_uses_local_dev_knowledge_files_when_enabled(monkeypatch):
    monkeypatch.setenv("DA_LOCAL_DEV", "1")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(PAYLOAD_OK))
    resp = orch.generate(
        GenerateRequest(
            natural_language_request="查高风险征信用户",
            target_country="mexico",
        )
    )
    assert any("data_acquisition_agent/configs/local_dev/scheme.md" in p for p in resp.metadata.knowledge_files_loaded)
    assert any("data_acquisition_agent/configs/local_dev/few.md" in p for p in resp.metadata.knowledge_files_loaded)
    assert not any("各国数据知识库汇总/墨西哥/scheme.md" in p for p in resp.metadata.knowledge_files_loaded)
    assert not any("各国数据知识库汇总/墨西哥/few.md" in p for p in resp.metadata.knowledge_files_loaded)


def test_leak_in_python_rejected():
    bad = dict(PAYLOAD_OK, sql=None, python="conn(host='198.51.100.10', password='FAKE')")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.CREDENTIAL_LEAK
    assert ei.value.request_id


def test_dangerous_python_rejected():
    bad = dict(PAYLOAD_OK, sql=None, python="import os\nos.system('rm -rf /')")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.DANGEROUS_CODE


def test_ddl_policy_violation_in_query_only():
    bad = dict(PAYLOAD_OK, sql="DROP TABLE x", sql_kind="query_only")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION


def test_model_unavailable_json_parse_to_schema_failed():
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(
        {"model_error": "json_parse: bad"}, status="model_unavailable"))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        ei.value.request_id,
    )


def test_invalid_audit_report_to_schema_failed():
    bad = dict(PAYLOAD_OK, audit_report="not_a_dict")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED


# 新增：OrchestratorError.message 不得回显 LLM 原文 / SQL 原文 / target 原文
_LEAK_SQL_BODY = "ATTACKER_SECRET_FRAGMENT_ZZZ"
_LEAK_TARGET = "prod_secret_db.dont_leak_me_xyz"
_LEAK_MODEL_ERROR = "json_parse: " + ("X" * 500) + " ATTACKER_LLM_PAYLOAD_ZZZ"


def test_ddl_violation_message_does_not_leak_sql():
    bad = dict(PAYLOAD_OK,
               sql=f"CREATE TABLE {_LEAK_TARGET} AS SELECT '{_LEAK_SQL_BODY}'",
               sql_kind="build_table_script",
               audit_report={"high_risk_ddl": True, "final_verdict": "ok"})
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        # NL must contain build intent so we reach the DDL policy layer
        # (the new NL→sql_kind consistency check otherwise short-circuits).
        orch.generate(GenerateRequest(
            natural_language_request="please build a table for the cohort",
            target_country="mexico"))
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION
    msg = ei.value.message
    assert _LEAK_SQL_BODY not in msg
    assert _LEAK_TARGET not in msg
    assert len(msg) < 200


def test_schema_failed_message_does_not_leak_model_error():
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(
        {"model_error": _LEAK_MODEL_ERROR}, status="model_unavailable"))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
    assert "ATTACKER_LLM_PAYLOAD_ZZZ" not in ei.value.message
    assert "X" * 100 not in ei.value.message
    assert len(ei.value.message) < 200


def test_upstream_llm_error_message_does_not_leak_model_error():
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(
        {"model_error": "rpc failed: " + ("Y" * 500) + " UPSTREAM_LEAK_ZZZ"},
        status="model_unavailable"))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.UPSTREAM_LLM_ERROR
    assert "UPSTREAM_LEAK_ZZZ" not in ei.value.message
    assert "Y" * 100 not in ei.value.message
    assert len(ei.value.message) < 200


def test_response_schema_failed_message_does_not_leak_payload():
    bad = dict(PAYLOAD_OK, audit_report=f"PAYLOAD_LEAK_{_LEAK_SQL_BODY}")
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
    assert _LEAK_SQL_BODY not in ei.value.message
    assert "PAYLOAD_LEAK" not in ei.value.message
    assert len(ei.value.message) < 200


def test_fenced_json_string_payload_is_repaired():
    payload = """```json
{"reasoning_summary":"ok","sql":"SELECT 1","sql_kind":"query_only","python":null,"audit_report":{"high_risk_ddl":false,"final_verdict":"ok"}}
```"""
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(payload))
    resp = orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert resp.sql == "SELECT 1"
    assert resp.audit_report.final_verdict == "ok"


def test_json_embedded_in_explanatory_text_is_repaired():
    payload = """Here is the final structured result:
{"reasoning_summary":"ok","sql":"SELECT 2","sql_kind":"query_only","python":null,"audit_report":{"high_risk_ddl":false,"final_verdict":"ok"}}
Please use it carefully.
"""
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(payload))
    resp = orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert resp.sql == "SELECT 2"


def test_non_json_payload_returns_controlled_schema_failure():
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient("not json at all"))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request="x", target_country="mexico"))
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
    assert "raw" not in ei.value.message.lower()
