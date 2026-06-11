from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app" / "static" / "js" / "app.jsx"
BUILD_FRONTEND = REPO / "app" / "ui" / "build_frontend.py"
API = REPO / "app" / "static" / "js" / "services" / "api.js"


def test_frontend_bundle_includes_auth_components_and_store() -> None:
    build_src = BUILD_FRONTEND.read_text(encoding="utf-8")

    assert "js/services/httpClient.js" in build_src
    assert "js/services/authApi.js" in build_src
    assert "js/state/authStore.js" in build_src
    assert "js/components/AuthGate.jsx" in build_src
    assert "js/components/LoginPage.jsx" in build_src
    assert "js/components/RegisterPage.jsx" in build_src


def test_app_uses_auth_gate_and_logout_capabilities() -> None:
    app_src = APP.read_text(encoding="utf-8")

    assert "AuthGate" in app_src
    assert "access_token" in app_src
    assert "authStore" in app_src
    assert "logout" in app_src


def test_api_layer_routes_requests_through_http_client() -> None:
    api_src = API.read_text(encoding="utf-8")

    assert "httpClient" in api_src
    assert "Authorization" in api_src
    assert "/api/auth/me" in api_src
