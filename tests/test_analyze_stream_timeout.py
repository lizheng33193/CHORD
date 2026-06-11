"""Total-timeout watchdog tests for /api/analyze-stream."""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import analyze_stream as stream_module
from app.core.config import settings


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


@pytest.fixture
def client_with_short_timeout(monkeypatch):
    monkeypatch.setattr(settings, "model_mode", "mock")
    monkeypatch.setattr(stream_module.shared_orchestrator.model_client, "mode", "mock")
    monkeypatch.setattr(stream_module, "TOTAL_TIMEOUT_SEC", 1)
    monkeypatch.setattr(stream_module, "HEARTBEAT_INTERVAL_SEC", 1)
    app = FastAPI()
    app.include_router(stream_module.router, prefix="/api")
    return TestClient(app)


def test_stream_emits_stream_error_on_total_timeout(monkeypatch, client_with_short_timeout):
    """When background thread takes longer than TOTAL_TIMEOUT_SEC, stream_error fires."""

    def slow_run(uids, application_time, q):
        time.sleep(5)  # exceeds 1s timeout
        q.put(None)

    monkeypatch.setattr(stream_module, "_run_analysis_in_thread", slow_run)

    with client_with_short_timeout.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert "stream_error" in types
    err = next(e for e in events if e["type"] == "stream_error")
    assert "timeout" in err["error_message"].lower()


def test_stream_error_on_orchestrator_exception(monkeypatch):
    """If orchestrator.analyze raises, the queue gets a stream_error event."""
    monkeypatch.setattr(settings, "model_mode", "mock")
    monkeypatch.setattr(stream_module.shared_orchestrator.model_client, "mode", "mock")

    def boom(*args, **kwargs):
        raise RuntimeError("orchestrator boom")

    monkeypatch.setattr(stream_module.shared_orchestrator, "analyze", boom)

    app = FastAPI()
    app.include_router(stream_module.router, prefix="/api")
    client = TestClient(app)

    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert "stream_error" in types
    err = next(e for e in events if e["type"] == "stream_error")
    assert "boom" in err["error_message"]
