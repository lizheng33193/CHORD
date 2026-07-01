from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BUILD_FRONTEND = REPO / "app" / "ui" / "build_frontend.py"
APP = REPO / "app" / "static" / "js" / "app.jsx"
DASHBOARD = REPO / "app" / "static" / "js" / "components" / "DashboardView.jsx"
CONSOLE = REPO / "app" / "static" / "js" / "components" / "panels" / "knowledge" / "KnowledgeBaseConsole.jsx"
VERSION_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "knowledge" / "KnowledgeVersionJobsPanel.jsx"


def test_frontend_bundle_includes_risk_knowledge_console_assets() -> None:
    build_src = BUILD_FRONTEND.read_text(encoding="utf-8")

    assert "js/services/riskKnowledgeAdminApi.js" in build_src
    assert "js/components/panels/knowledge/KnowledgeBaseListPanel.jsx" in build_src
    assert "js/components/panels/knowledge/KnowledgeDocumentPanel.jsx" in build_src
    assert "js/components/panels/knowledge/KnowledgeVersionJobsPanel.jsx" in build_src
    assert "js/components/panels/knowledge/KnowledgeRetrievalDebugPanel.jsx" in build_src
    assert "js/components/panels/knowledge/KnowledgeBaseConsole.jsx" in build_src
    assert build_src.index('"js/components/panels/knowledge/KnowledgeBaseConsole.jsx"') < build_src.index('"js/components/DashboardView.jsx"')


def test_app_owns_guarded_knowledge_tab_routing() -> None:
    app_src = APP.read_text(encoding="utf-8")

    assert "'knowledge'" in app_src
    assert "VALID_DASHBOARD_TABS" in app_src
    assert "project:manage" in app_src
    assert "canManageProject" in app_src
    assert "params.get('tab')" in app_src
    assert "setActiveTab('comprehensive')" in app_src
    assert "tab === 'knowledge'" in app_src or '"knowledge"' in app_src


def test_dashboard_renders_guarded_knowledge_tab_and_console() -> None:
    dashboard_src = DASHBOARD.read_text(encoding="utf-8")

    assert "KnowledgeBaseConsole" in dashboard_src
    assert "project:manage" in dashboard_src
    assert "知识库管理" in dashboard_src
    assert "id: 'knowledge'" in dashboard_src
    assert "visibleActiveTab === 'knowledge'" in dashboard_src


def test_knowledge_console_contains_confirmation_and_polling_guards() -> None:
    console_src = CONSOLE.read_text(encoding="utf-8")
    version_src = VERSION_PANEL.read_text(encoding="utf-8")

    assert "window.confirm" in console_src
    assert "rebuild" in console_src
    assert "retry" in console_src
    assert "activate" in console_src
    assert "document.visibilityState === 'visible'" in console_src
    assert "activeTab === 'knowledge'" in console_src
    assert "setInterval" in console_src
    assert "clearInterval" in console_src
    assert "manual refresh" not in console_src.lower()
    assert "刷新" in version_src
