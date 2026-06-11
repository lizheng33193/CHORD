"""Verify /api/analyze-stream is mounted on the main FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_analyze_stream_route_registered():
    routes = [getattr(r, 'path', None) for r in app.routes]
    assert "/api/analyze-stream" in routes


def test_analyze_stream_smoke(monkeypatch):
    """End-to-end smoke: real app routes a real SSE request."""
    from app.api import analyze_stream as stream_module
    from app.core.config import settings

    monkeypatch.setattr(settings, "model_mode", "mock")
    monkeypatch.setattr(stream_module.shared_orchestrator.model_client, "mode", "mock")

    client = TestClient(app)
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.read().decode("utf-8")
    assert "analysis_started" in body
    assert "analysis_completed" in body


def test_progress_view_in_frontend_bundle():
    from app.ui.build_frontend import BUILT_FRONTEND_HTML
    # marker is only emitted when the file is in LOAD_ORDER
    assert "=== js/components/ProgressView.jsx ===" in BUILT_FRONTEND_HTML
