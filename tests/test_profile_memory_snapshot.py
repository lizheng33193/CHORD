from __future__ import annotations

from app.services.memory.contracts import MemoryUsePurpose
from app.services.profile_dag.contracts import ProfileNodeRun, ProfileRun, ProfileRunResultSnapshot, utcnow
from app.services.profile_dag.memory_snapshot import build_profile_memory_snapshot


def _node_run(node_key: str, status: str) -> ProfileNodeRun:
    now = utcnow()
    return ProfileNodeRun(
        node_run_id=f"pnr_{node_key}",
        profile_run_id="pr_test",
        uid="U1",
        node_key=node_key,
        skill_name=f"{node_key}_skill",
        stage=0,
        depends_on=[],
        upstream_node_run_ids=[],
        status=status,
        attempt=1,
        started_at=now,
        finished_at=now,
        result_status="ok" if status in {"completed", "degraded"} else "failed",
    )


def _profile_run() -> ProfileRun:
    now = utcnow()
    return ProfileRun(
        run_id="pr_test",
        source="test",
        uids=["U1"],
        requested_modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        country_code="mx",
        application_time="2026-04-15T12:00:00",
        strict_data_mode=True,
        status="completed_with_degradation",
        trace_id=None,
        session_id=None,
        turn_id=None,
        request_id=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )


def test_build_profile_memory_snapshot_uses_stable_fields_and_boundaries():
    snapshot = ProfileRunResultSnapshot(
        uid="U1",
        requested_modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
        module_outputs={
            "app": {"summary": "app ok", "structured_result": {"status": "ok"}, "charts": [], "report_markdown": ""},
            "behavior": {"summary": "behavior ok", "structured_result": {"status": "ok"}, "charts": [], "report_markdown": ""},
            "credit": {"summary": "credit missing", "structured_result": {"status": "data_missing"}, "charts": [], "report_markdown": ""},
            "comprehensive": {
                "summary": "stable summary",
                "structured_result": {
                    "uid": "U1",
                    "status": "ok",
                    "summary": "stable summary",
                    "persona": "persona",
                    "segment": "S2",
                    "segment_name": "稳健经营客",
                    "overall_risk": "medium",
                    "overall_value": "high",
                    "confidence": "medium",
                    "behavior_tags": {"churn_risk": "low"},
                    "financial_tags": {"debt_pressure": "medium"},
                    "data_completeness": {
                        "app": "available",
                        "behavior": "available",
                        "credit": "missing",
                        "overall": "partial",
                    },
                    "metrics": {
                        "segment": "S2",
                        "segment_name": "稳健经营客",
                        "overall_risk": "medium",
                        "overall_value": "high",
                        "confidence": "medium",
                        "behavior_tags": {"churn_risk": "low"},
                        "financial_tags": {"debt_pressure": "medium"},
                        "data_completeness": {
                            "app": "available",
                            "behavior": "available",
                            "credit": "missing",
                            "overall": "partial",
                        },
                        "confidence_level": "medium",
                    },
                    "model_trace": {"mode": "mock", "used_llm": False, "model_name": "test", "fallback_reason": ""},
                },
                "charts": [],
                "report_markdown": "",
            },
            "product": {"summary": "product ok", "structured_result": {"status": "ok"}, "charts": [], "report_markdown": ""},
            "ops": {"summary": "ops ok", "structured_result": {"status": "ok"}, "charts": [], "report_markdown": ""},
        },
        node_runs=[
            _node_run("app", "completed"),
            _node_run("behavior", "degraded"),
            _node_run("credit", "failed"),
            _node_run("comprehensive", "completed"),
            _node_run("product", "completed"),
            _node_run("ops", "completed"),
        ],
    )

    memory_snapshot = build_profile_memory_snapshot(_profile_run(), snapshot)

    assert memory_snapshot["uid"] == "U1"
    assert memory_snapshot["profile_run_id"] == "pr_test"
    assert memory_snapshot["summary"] == "stable summary"
    assert memory_snapshot["segment"] == "S2"
    assert memory_snapshot["risk_level"] == "medium"
    assert memory_snapshot["value_level"] == "high"
    assert memory_snapshot["confidence"] == "medium"
    assert set(memory_snapshot["completed_modules"]) == {"app", "comprehensive", "product", "ops"}
    assert memory_snapshot["degraded_modules"] == ["behavior"]
    assert memory_snapshot["failed_modules"] == ["credit"]
    assert memory_snapshot["standardized_labels"]["metadata"]["profile_confidence"] == "medium"
    assert memory_snapshot["source"] == "profile_dag"
    assert memory_snapshot["memory_source_type"] == "profile_result"
    assert memory_snapshot["authority_level"] == "system_generated"
    assert memory_snapshot["allowed_memory_use"] == [
        MemoryUsePurpose.PROFILE_RESULT_RECALL.value,
        MemoryUsePurpose.PROFILE_FOLLOWUP_CONTEXT.value,
        MemoryUsePurpose.USER_PROFILE_HISTORY.value,
    ]
    assert memory_snapshot["forbidden_memory_use"] == [
        MemoryUsePurpose.DATA_AGENT_FIELD_GROUNDING.value,
        MemoryUsePurpose.RISK_KNOWLEDGE_DOCUMENT_EVIDENCE.value,
        MemoryUsePurpose.RISK_KNOWLEDGE_SOURCE_DOCUMENT.value,
        MemoryUsePurpose.APPROVED_STRATEGY_POLICY.value,
        MemoryUsePurpose.SQL_GENERATION_GROUNDING.value,
    ]
    assert all(isinstance(use, str) for use in memory_snapshot["allowed_memory_use"])
    assert all(isinstance(use, str) for use in memory_snapshot["forbidden_memory_use"])
    assert memory_snapshot["evidence_status"] == "risk_domain_not_integrated"


def test_build_profile_memory_snapshot_marks_unknown_without_meaningful_profile_result():
    snapshot = ProfileRunResultSnapshot(
        uid="U1",
        requested_modules=["comprehensive"],
        module_outputs={
            "comprehensive": {
                "summary": "",
                "structured_result": {"status": "data_missing", "metrics": {}, "model_trace": {}},
                "charts": [],
                "report_markdown": "",
            },
        },
        node_runs=[_node_run("comprehensive", "degraded")],
    )

    memory_snapshot = build_profile_memory_snapshot(_profile_run(), snapshot)

    assert memory_snapshot["summary"] is None
    assert memory_snapshot["segment"] is None
    assert memory_snapshot["evidence_status"] == "unknown"
