from __future__ import annotations

import importlib

from app.services.orchestrator_agent.schemas import RunTraceInput


def test_run_trace_returns_dashboard_payload(monkeypatch):
    run_trace_mod = importlib.import_module("app.services.orchestrator_agent.tools.run_trace")

    class _FakeAnalyzer:
        def analyze(self, uid, context):
            return {
                "uid": uid,
                "status": "ok",
                "event_window": {
                    "start": "2026-05-01T00:00:00Z",
                    "end": "2026-05-02T00:00:00Z",
                    "total_events": 2,
                    "analyzed_events": 2,
                },
                "path_graph": {
                    "top_pages": [],
                    "top_transitions": [],
                },
                "churn_story": "用户在关键步骤流失。",
            }

    monkeypatch.setattr(run_trace_mod, "TraceAnalyzer", lambda: _FakeAnalyzer())

    output = run_trace_mod.run_trace(RunTraceInput(uid="MX0001"))
    dumped = output.model_dump(mode="json")

    assert dumped["uid"] == "MX0001"
    assert dumped["status"] == "ok"
    assert dumped["event_window"]["total_events"] == 2
    assert dumped["path_graph"]["top_pages"] == []
    assert dumped["summary"]["total_events"] == 2
