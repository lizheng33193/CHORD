from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.runtime_skills.base import BaseSkill
from app.schemas.final_response import UserAnalysisResult
from app.services.orchestrator import AnalysisOrchestrator
from app.services.orchestrator_agent.schemas import RunProfileInput
from app.services.orchestrator_agent.tools.run_profile import run_profile


class _FakeSkill(BaseSkill):
    def __init__(
        self,
        *,
        name: str,
        stage: int,
        depends_on: list[str] | None = None,
        result: dict[str, Any] | None = None,
        raise_exc: bool = False,
    ) -> None:
        self.name = name
        self.stage = stage
        self.depends_on = depends_on or []
        self._result = result or {
            "summary": f"{name} ok",
            "structured_result": {"status": "ok"},
            "charts": [],
            "report_markdown": "",
        }
        self._raise_exc = raise_exc

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        if self._raise_exc:
            raise RuntimeError(f"{self.name} boom")
        return {
            **self._result,
            "structured_result": {
                **(self._result.get("structured_result") or {}),
                "uid": uid,
            },
        }


def _make_executor_with_fake_skills():
    from app.services.profile_dag.executor import ProfileDagExecutor
    from app.services.profile_dag.node_registry import PROFILE_NODE_SPECS

    skill_map = {
        "app_profile": _FakeSkill(name="app_profile", stage=0),
        "behavior_profile": _FakeSkill(name="behavior_profile", stage=0),
        "credit_profile": _FakeSkill(
            name="credit_profile",
            stage=0,
            result={
                "summary": "credit degraded",
                "structured_result": {"status": "data_missing"},
                "charts": [],
                "report_markdown": "",
            },
        ),
        "comprehensive_profile": _FakeSkill(name="comprehensive_profile", stage=1, depends_on=["app_profile", "behavior_profile", "credit_profile"]),
        "product_advice": _FakeSkill(name="product_advice", stage=2, depends_on=["comprehensive_profile"]),
        "ops_advice": _FakeSkill(name="ops_advice", stage=2, depends_on=["comprehensive_profile"]),
    }
    return ProfileDagExecutor(node_specs=PROFILE_NODE_SPECS, skill_map=skill_map)


def test_profile_node_registry_fixed_graph_contract():
    from app.services.profile_dag.node_registry import (
        NODE_KEY_TO_SPEC,
        PROFILE_NODE_SPECS,
    )

    assert [spec.node_key for spec in PROFILE_NODE_SPECS] == [
        "app",
        "behavior",
        "credit",
        "comprehensive",
        "product",
        "ops",
    ]
    assert NODE_KEY_TO_SPEC["app"].skill_name == "app_profile"
    assert NODE_KEY_TO_SPEC["behavior"].skill_name == "behavior_profile"
    assert NODE_KEY_TO_SPEC["credit"].skill_name == "credit_profile"
    assert NODE_KEY_TO_SPEC["comprehensive"].depends_on == ["app", "behavior", "credit"]
    assert NODE_KEY_TO_SPEC["product"].depends_on == ["comprehensive"]
    assert NODE_KEY_TO_SPEC["ops"].depends_on == ["comprehensive"]


def test_profile_dag_executor_marks_comprehensive_degraded_and_unrequested_nodes_skipped():
    executor = _make_executor_with_fake_skills()

    run, snapshots = executor.run(
        uids=["824812551379353600"],
        requested_modules=["comprehensive"],
        application_time="2026-04-15T12:00:00",
        country_code="mx",
        strict_data_mode=True,
        source="test",
    )

    assert run.status == "completed_with_degradation"
    snapshot = snapshots[0]
    by_node = {node_run.node_key: node_run for node_run in snapshot.node_runs}
    assert by_node["app"].status == "completed"
    assert by_node["behavior"].status == "completed"
    assert by_node["credit"].status == "degraded"
    assert by_node["comprehensive"].status == "degraded"
    assert by_node["product"].status == "skipped"
    assert by_node["ops"].status == "skipped"


def test_orchestrator_analyze_emits_profile_node_events_and_keeps_legacy_skill_events(monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")
    orchestrator = AnalysisOrchestrator()
    monkeypatch.setattr(orchestrator.model_client, "mode", "mock")

    events: list[dict[str, Any]] = []
    response = orchestrator.analyze(
        ["824812551379353600"],
        application_time="2026-04-15T12:00:00",
        progress_callback=events.append,
    )

    assert isinstance(response.results[0], UserAnalysisResult)
    event_types = [event["type"] for event in events]
    assert "profile_run_started" in event_types
    assert "profile_node_completed" in event_types
    assert "profile_run_completed" in event_types
    assert "skill_started" in event_types
    assert "skill_completed" in event_types
    assert "analysis_progress" in event_types


def test_profile_dag_executor_skips_product_and_ops_when_comprehensive_fails():
    from app.services.profile_dag.executor import ProfileDagExecutor
    from app.services.profile_dag.node_registry import PROFILE_NODE_SPECS

    skill_map = {
        "app_profile": _FakeSkill(name="app_profile", stage=0),
        "behavior_profile": _FakeSkill(name="behavior_profile", stage=0),
        "credit_profile": _FakeSkill(name="credit_profile", stage=0),
        "comprehensive_profile": _FakeSkill(
            name="comprehensive_profile",
            stage=1,
            depends_on=["app_profile", "behavior_profile", "credit_profile"],
            raise_exc=True,
        ),
        "product_advice": _FakeSkill(name="product_advice", stage=2, depends_on=["comprehensive_profile"]),
        "ops_advice": _FakeSkill(name="ops_advice", stage=2, depends_on=["comprehensive_profile"]),
    }
    executor = ProfileDagExecutor(node_specs=PROFILE_NODE_SPECS, skill_map=skill_map)

    run, snapshots = executor.run(
        uids=["824812551379353600"],
        requested_modules=["product", "ops"],
        application_time="2026-04-15T12:00:00",
        country_code="mx",
        strict_data_mode=True,
        source="test",
    )

    assert run.status == "completed_with_degradation"
    by_node = {node_run.node_key: node_run for node_run in snapshots[0].node_runs}
    assert by_node["comprehensive"].status == "failed"
    assert by_node["product"].status == "skipped"
    assert by_node["ops"].status == "skipped"


def test_profile_dag_executor_event_contract_contains_fixed_fields():
    executor = _make_executor_with_fake_skills()
    events: list[dict[str, Any]] = []

    executor.run(
        uids=["824812551379353600"],
        requested_modules=["app"],
        application_time="2026-04-15T12:00:00",
        country_code="mx",
        strict_data_mode=True,
        source="test",
        progress_callback=events.append,
    )

    started = next(event for event in events if event["type"] == "profile_node_started")
    terminal = next(event for event in events if event["type"] == "profile_node_completed")
    for event in (started, terminal):
        assert "profile_run_id" in event
        assert "node_run_id" in event
        assert event["uid"] == "824812551379353600"
        assert event["node_key"] == "app"
        assert event["skill_name"] == "app_profile"
        assert event["stage"] == 0
        assert "status" in event
        assert "cache_status" in event
        assert "upstream_node_run_ids" in event


def test_run_profile_tool_emits_profile_node_events_and_preserves_legacy_module_progress(monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")

    progress_events: list[dict[str, Any]] = []
    result = run_profile(
        RunProfileInput(
            uids=["824812551379353600"],
            app_time="2026-04-15T12:00:00",
            modules=["app", "comprehensive"],
            strict_data_mode=True,
        ),
        progress_callback=progress_events.append,
    )

    assert result.results
    assert any(event.get("type") == "profile_node_started" for event in progress_events)
    assert any(event.get("type") == "profile_node_completed" for event in progress_events)
    assert any(event.get("progress_type") == "profile_module_completed" for event in progress_events)


def test_analyze_module_uses_profile_dag_runtime_and_preserves_response_shape(monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")
    orchestrator = AnalysisOrchestrator()
    monkeypatch.setattr(orchestrator.model_client, "mode", "mock")

    response = orchestrator.analyze_module(
        uid="824812551379353600",
        module="comprehensive",
        application_time="2026-04-15T12:00:00",
    )

    assert response["uid"] == "824812551379353600"
    assert response["module"] == "comprehensive"
    assert response["status"] in {"ok", "error"}
    assert "data" in response
    assert "error" in response
