from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app" / "static" / "js" / "app.jsx"
BUILD_FRONTEND = REPO / "app" / "ui" / "build_frontend.py"
API = REPO / "app" / "static" / "js" / "services" / "api.js"
AUTH_API = REPO / "app" / "static" / "js" / "services" / "authApi.js"
AUTH_STORE = REPO / "app" / "static" / "js" / "state" / "authStore.js"
HOME = REPO / "app" / "static" / "js" / "components" / "HomeView.jsx"
DASHBOARD = REPO / "app" / "static" / "js" / "components" / "DashboardView.jsx"


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


def test_auth_runtime_uses_my_projects_and_preserves_session_on_403() -> None:
    auth_api_src = AUTH_API.read_text(encoding="utf-8")
    auth_store_src = AUTH_STORE.read_text(encoding="utf-8")

    assert "/api/auth/my-projects" in auth_api_src
    assert "error.status === 403" in auth_api_src
    assert "clearSession()" in auth_api_src
    assert "authorizedScopes" in auth_store_src


def test_scope_selectors_are_driven_by_authorized_scope_data() -> None:
    home_src = HOME.read_text(encoding="utf-8")
    dashboard_src = DASHBOARD.read_text(encoding="utf-8")
    api_src = API.read_text(encoding="utf-8")

    assert "supported_countries" in api_src
    assert "authorizedScopes" in home_src
    assert "authorizedScopes" in dashboard_src
    assert "墨西哥 (MX)" not in home_src
    assert "泰国 (TH)" not in home_src
    assert "墨西哥 (MX)" not in dashboard_src
    assert "泰国 (TH)" not in dashboard_src
