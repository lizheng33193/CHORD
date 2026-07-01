from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
API = REPO / "app" / "static" / "js" / "services" / "riskKnowledgeAdminApi.js"
DEBUG_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "knowledge" / "KnowledgeRetrievalDebugPanel.jsx"
VERSION_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "knowledge" / "KnowledgeVersionJobsPanel.jsx"
CONSOLE = REPO / "app" / "static" / "js" / "components" / "panels" / "knowledge" / "KnowledgeBaseConsole.jsx"


def test_risk_knowledge_admin_api_reuses_http_client_and_declares_routes() -> None:
    api_src = API.read_text(encoding="utf-8")

    assert "httpClient" in api_src
    assert "fetch(" not in api_src
    assert "/api/risk-knowledge/admin/kbs" in api_src
    assert "/api/risk-knowledge/admin/documents/" in api_src
    assert "/versions:upload" in api_src
    assert ":index" in api_src
    assert ":rebuild" in api_src
    assert ":activate" in api_src
    assert ":retry" in api_src
    assert "/debug/retrieve" in api_src
    assert "detail.message" in api_src
    assert "detail.code" in api_src


def test_risk_knowledge_admin_api_uses_form_data_for_uploads() -> None:
    api_src = API.read_text(encoding="utf-8")

    assert "new FormData()" in api_src
    assert "formData.append('file'" in api_src
    assert "formData.append('version_label'" in api_src
    assert "formData.append('auto_index'" in api_src


def test_retrieval_debug_ui_stays_retrieval_only() -> None:
    debug_src = DEBUG_PANEL.read_text(encoding="utf-8")

    assert "top_k" in debug_src
    assert "Math.min(50" in debug_src
    assert "text_preview" in debug_src
    assert "candidates" in debug_src
    assert "diagnostics" in debug_src
    assert "rerank_items" not in debug_src
    assert "selected_evidence" not in debug_src
    assert "citations" not in debug_src
    assert "gate_decision" not in debug_src
    assert "answer" not in debug_src
    assert "RiskKnowledgeService" not in debug_src


def test_version_jobs_panel_uses_lightweight_metadata_textarea() -> None:
    version_src = VERSION_PANEL.read_text(encoding="utf-8")
    console_src = CONSOLE.read_text(encoding="utf-8")

    assert "metadataText" in version_src
    assert "JSON.parse" in console_src
    assert "textarea" in version_src
    assert "FormData" not in version_src
