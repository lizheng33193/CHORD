"""AnalysisOrchestrator progress_callback transparency tests."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.orchestrator import AnalysisOrchestrator


@pytest.fixture
def orchestrator(monkeypatch):
    # Force mock mode BEFORE instantiating the orchestrator so the
    # ModelClient created inside __init__ picks mode='mock'.
    monkeypatch.setattr(settings, "model_mode", "mock")
    return AnalysisOrchestrator()


def test_analyze_without_callback_unchanged(orchestrator):
    """No callback -> behavior identical to current /api/analyze path."""
    resp = orchestrator.analyze(["824812551379353600"])
    assert len(resp.results) == 1


def test_analyze_passes_callback_through(orchestrator):
    events: list[dict] = []
    orchestrator.analyze(
        ["824812551379353600"],
        progress_callback=events.append,
    )

    types = [e["type"] for e in events]
    # Must contain at least one skill_started, one skill_completed, one analysis_progress
    assert "skill_started" in types
    assert "skill_completed" in types
    assert "analysis_progress" in types

    progress = next(e for e in events if e["type"] == "analysis_progress")
    assert progress["uid"] == "824812551379353600"
    assert "result" in progress
    assert progress["result"]["uid"] == "824812551379353600"


def test_analyze_emits_progress_per_uid(orchestrator):
    events: list[dict] = []
    uids = ["824812551379353600", "824812551379353601"]
    orchestrator.analyze(uids, progress_callback=events.append)

    progress_events = [e for e in events if e["type"] == "analysis_progress"]
    assert len(progress_events) == 2
    assert {e["uid"] for e in progress_events} == set(uids)


def test_analyze_progress_result_is_jsonable(orchestrator):
    """analysis_progress.result must be JSON-serializable (mode='json')."""
    import json
    events: list[dict] = []
    orchestrator.analyze(["824812551379353600"], progress_callback=events.append)

    progress = next(e for e in events if e["type"] == "analysis_progress")
    json.dumps(progress["result"])  # must not raise
