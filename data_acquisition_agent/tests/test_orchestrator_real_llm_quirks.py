"""V1 follow-up: real-LLM JSON stability fixes.

Covers:
1. _RESPONSE_SCHEMA carries a "required" array listing all 5 top-level keys
   so Gemini's response_json_schema enforces presence.
2. NL→sql_kind consistency: when the request has no build/persist intent,
   an LLM-emitted sql_kind=build_table_script must be hard-rejected as
   SCHEMA_VALIDATION_FAILED — not silently rewritten.
3. When NL request DOES contain build intent, build_table_script flows
   through the existing DDL policy check (no early reject).
"""

from __future__ import annotations

import pytest

from data_acquisition_agent.orchestrator import (
    DataAcquisitionOrchestrator,
    OrchestratorError,
    _RESPONSE_SCHEMA,
)
from data_acquisition_agent.schemas import ErrorType, GenerateRequest


class StubModelClient:
    mode = "mock"
    model_name = "stub"

    def __init__(self, payload, status="ok"):
        self._p = payload
        self._s = status

    def generate_structured(self, **kw):
        return {
            "status": self._s,
            "structured_result": self._p,
            "model_name": "stub",
            "prompt_preview": "",
        }


def test_response_schema_marks_all_5_keys_required():
    required = _RESPONSE_SCHEMA.get("required")
    assert required is not None, "_RESPONSE_SCHEMA must carry a 'required' list"
    assert set(required) == {
        "reasoning_summary",
        "sql",
        "sql_kind",
        "python",
        "audit_report",
    }


def test_unrequested_build_table_hard_rejected_as_schema_failed():
    # NL request has no build/persist intent — but LLM returns build_table_script.
    # Must hard-reject (no silent rewrite).
    bad = {
        "reasoning_summary": "x",
        "sql": "CREATE TABLE dwb_pri_dm.tmp_x AS SELECT uid FROM dwb.t",
        "sql_kind": "build_table_script",
        "python": None,
        "audit_report": {"high_risk_ddl": True, "final_verdict": ""},
    }
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(
            GenerateRequest(
                natural_language_request="查询墨西哥最近 7 天的活跃用户",
                target_country="mexico",
            )
        )
    assert ei.value.error_type == ErrorType.SCHEMA_VALIDATION_FAILED
    # message must remain a fixed safe short string (no SQL leak).
    assert "CREATE TABLE" not in ei.value.message
    assert "dwb_pri_dm" not in ei.value.message
    assert len(ei.value.message) < 200


@pytest.mark.parametrize(
    "nl",
    [
        "请帮我建一张表保存最近 30 天活跃用户",  # 建表
        "create a table that persists the cohort",  # create
        "build a result table for the analysts",  # build
        "save the cohort into a new table",  # save
        "materialize the daily aggregate",  # materialize
        "物化每日聚合到一个新表",  # 物化
    ],
)
def test_explicit_build_intent_passes_consistency_check(nl):
    # NL has build intent → consistency check passes; flow continues to
    # the existing DDL policy check (and trips on prefix violation here,
    # which is the *expected* downstream behavior — not a consistency reject).
    bad_prefix = {
        "reasoning_summary": "x",
        "sql": "CREATE TABLE not_in_prefix.x AS SELECT 1",
        "sql_kind": "build_table_script",
        "python": None,
        "audit_report": {"high_risk_ddl": True, "final_verdict": ""},
    }
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(bad_prefix))
    with pytest.raises(OrchestratorError) as ei:
        orch.generate(GenerateRequest(natural_language_request=nl, target_country="mexico"))
    # Reaches DDL policy layer, not consistency layer.
    assert ei.value.error_type == ErrorType.DDL_POLICY_VIOLATION


def test_query_only_with_no_build_intent_passes():
    ok = {
        "reasoning_summary": "x",
        "sql": "SELECT 1",
        "sql_kind": "query_only",
        "python": None,
        "audit_report": {"high_risk_ddl": False, "final_verdict": ""},
    }
    orch = DataAcquisitionOrchestrator(model_client=StubModelClient(ok))
    resp = orch.generate(
        GenerateRequest(
            natural_language_request="查询墨西哥最近 7 天活跃用户",
            target_country="mexico",
        )
    )
    assert resp.sql == "SELECT 1"
    assert resp.sql_kind == "query_only"
