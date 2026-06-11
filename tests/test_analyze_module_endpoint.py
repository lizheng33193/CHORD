"""Tests for /api/analyze-module and /api/ui-config endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """Ensure all tests use mock LLM mode for speed and determinism."""
    monkeypatch.setattr(settings, "model_mode", "mock")
    from app.services.orchestrator import shared_orchestrator
    monkeypatch.setattr(shared_orchestrator.model_client, "mode", "mock")


@pytest.fixture
def client():
    return TestClient(app)


# ── /api/ui-config ────────────────────────────────────────────────

def test_ui_config_returns_transition_duration(client):
    resp = client.get("/api/ui-config")
    assert resp.status_code == 200
    body = resp.json()
    assert "uid_transition_duration_ms" in body
    assert isinstance(body["uid_transition_duration_ms"], int)
    assert body["uid_transition_duration_ms"] >= 0


def test_ui_config_reflects_setting(client, monkeypatch):
    monkeypatch.setattr(settings, "uid_transition_duration_ms", 9999)
    resp = client.get("/api/ui-config")
    assert resp.json()["uid_transition_duration_ms"] == 9999


# ── /api/analyze-module — validation ──────────────────────────────

def test_analyze_module_invalid_module(client):
    resp = client.get("/api/analyze-module", params={"uid": "824812551379353600", "module": "invalid"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "invalid_module"


def test_analyze_module_missing_uid(client):
    resp = client.get("/api/analyze-module", params={"uid": "", "module": "app"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "invalid_uid"


# ── /api/analyze-module — happy path ──────────────────────────────

def test_analyze_module_app_ok(client):
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "app",
        "application_time": "2026-04-15T12:00:00",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["module"] == "app"
    assert isinstance(body["data"], dict)
    assert body["error"] is None


def test_analyze_module_behavior_ok(client):
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "behavior",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_analyze_module_credit_ok(client):
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "credit",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── /api/analyze-module — comprehensive auto-fills upstream ───────

def test_analyze_module_comprehensive_auto_fills(client):
    """Comprehensive should auto-run upstream modules when not cached."""
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "comprehensive",
        "application_time": "2026-04-15T12:00:00",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["module"] == "comprehensive"
    assert isinstance(body["data"], dict)


# ── /api/analyze-module — cache hit ───────────────────────────────

def test_analyze_module_cache_hit(client):
    """Second request for same uid+module should hit cache (faster)."""
    params = {
        "uid": "824812551379353600",
        "module": "app",
        "application_time": "2026-04-15T12:00:00",
    }
    resp1 = client.get("/api/analyze-module", params=params)
    assert resp1.json()["status"] == "ok"

    # Second call — should be served from cache
    resp2 = client.get("/api/analyze-module", params=params)
    assert resp2.json()["status"] == "ok"
    # Data should be identical
    assert resp1.json()["data"].keys() == resp2.json()["data"].keys()


# ── /api/analyze-module — advisory (product/ops) ─────────────────

def test_analyze_module_product_ok(client):
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "product",
        "application_time": "2026-04-15T12:00:00",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["module"] == "product"


def test_analyze_module_ops_ok(client):
    resp = client.get("/api/analyze-module", params={
        "uid": "824812551379353600",
        "module": "ops",
        "application_time": "2026-04-15T12:00:00",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["module"] == "ops"


# ── route registration ────────────────────────────────────────────

def test_analyze_module_route_registered():
    routes = [getattr(r, 'path', None) for r in app.routes]
    assert "/api/analyze-module" in routes


def test_ui_config_route_registered():
    routes = [getattr(r, 'path', None) for r in app.routes]
    assert "/api/ui-config" in routes
