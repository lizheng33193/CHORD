from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BUILD_FRONTEND = REPO / "app" / "ui" / "build_frontend.py"
API = REPO / "app" / "static" / "js" / "services" / "api.js"
CHAT_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatPanel.jsx"
RUN_FORM = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "DataAgentRunForm.jsx"
REVIEW_CARD = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "SQLReviewCard.jsx"


def test_frontend_bundle_includes_data_agent_chat_components() -> None:
    build_src = BUILD_FRONTEND.read_text(encoding="utf-8")

    assert "js/components/panels/chat/DataAgentRunForm.jsx" in build_src
    assert "js/components/panels/chat/SQLReviewCard.jsx" in build_src


def test_api_layer_exposes_data_agent_routes() -> None:
    api_src = API.read_text(encoding="utf-8")

    assert "/api/data-agent/runs" in api_src
    assert "createDataAgentRun" in api_src
    assert "fetchDataAgentRuns" in api_src
    assert "approveDataAgentRun" in api_src
    assert "editDataAgentRun" in api_src
    assert "reviseDataAgentRun" in api_src
    assert "rejectDataAgentRun" in api_src
    assert "executeDataAgentRun" in api_src


def test_chat_panel_contains_explicit_data_agent_mode() -> None:
    chat_panel_src = CHAT_PANEL.read_text(encoding="utf-8")

    assert "Data Agent" in chat_panel_src
    assert "DataAgentRunForm" in chat_panel_src
    assert "SQLReviewCard" in chat_panel_src
    assert "dataAgentMode" in chat_panel_src
    assert "createDataAgentRun" in chat_panel_src
    assert "fetchDataAgentRuns" in chat_panel_src


def test_data_agent_components_render_expected_actions() -> None:
    form_src = RUN_FORM.read_text(encoding="utf-8")
    review_src = REVIEW_CARD.read_text(encoding="utf-8")

    assert "bucket_writeback" in form_src
    assert "生成 SQL 草稿" in form_src
    assert "Execute Query" in review_src
    assert "Execute & Write Back" in review_src
    assert "Edit SQL" in review_src
    assert "Ask Agent Revise" in review_src
