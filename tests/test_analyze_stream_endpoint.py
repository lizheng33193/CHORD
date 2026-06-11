"""End-to-end tests for the /api/analyze-stream SSE endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import analyze_stream as stream_module
from app.api.analyze_stream import router as stream_router
from app.core.config import settings


def _make_app() -> FastAPI:
    """Replicate app/main.py's RequestValidationError -> 400 normalization
    so the SSE endpoint's input validation behavior matches production."""
    app = FastAPI()

    @app.exception_handler(RequestValidationError)
    async def _ve(_, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(status_code=400, content={"detail": str(first.get("msg") or "Invalid request payload.")})

    app.include_router(stream_router, prefix="/api")
    return app


@pytest.fixture
def client(monkeypatch):
    # Force mock mode BEFORE the module-level shared_orchestrator picks it up.
    # shared_orchestrator was instantiated at import time, so we also have to
    # patch its already-created ModelClient.mode.
    monkeypatch.setattr(settings, "model_mode", "mock")
    monkeypatch.setattr(stream_module.shared_orchestrator.model_client, "mode", "mock")
    return TestClient(_make_app())


def _parse_sse(text: str) -> list[dict]:
    """Split SSE wire format into a list of event dicts (skip heartbeat lines)."""
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_stream_emits_full_event_sequence(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [e["type"] for e in events]

    assert types[0] == "analysis_started"
    assert "skill_started" in types
    assert "skill_completed" in types
    assert "analysis_progress" in types
    assert types[-1] == "analysis_completed"


def test_stream_analysis_completed_carries_full_results(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    completed = next(e for e in events if e["type"] == "analysis_completed")
    assert "results" in completed
    assert isinstance(completed["results"], list)
    assert completed["results"][0]["uid"] == "824812551379353600"


def test_stream_started_event_carries_uids_and_total_skills(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uids": ["824812551379353600", "824812551379353601"]},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    started = events[0]
    assert started["type"] == "analysis_started"
    assert started["uids"] == ["824812551379353600", "824812551379353601"]
    assert started["total_skills_per_uid"] == 6


def test_stream_invalid_uid_returns_400_not_sse(client):
    """Input validation failure must go HTTP 400, not enter the stream (Q6.4)."""
    resp = client.post("/api/analyze-stream", json={"uid": "not-an-18-digit"})
    assert resp.status_code == 400
    assert "text/event-stream" not in resp.headers.get("content-type", "")
