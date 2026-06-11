from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT_DIR = REPO / "app" / "static" / "js" / "components" / "panels" / "chat"

EXPECTED_COMPONENTS = [
    "ChatPanel",
    "ChatMessageList",
    "ChatInputBox",
    "ChatToolCallStream",
    "ChatExecutionTraceCard",
    "ChatAckCard",
    "ChatBudgetBanner",
    "ChatProviderFallbackBanner",
    "MemoryInspector",
]


def test_chat_component_files_exist_and_register() -> None:
    assert CHAT_DIR.is_dir(), f"missing dir: {CHAT_DIR}"
    for name in EXPECTED_COMPONENTS:
        path = CHAT_DIR / f"{name}.jsx"
        assert path.is_file(), f"missing component: {path}"
        body = path.read_text(encoding="utf-8")
        assert f"window.AppComponents.{name} = {name};" in body


def test_load_order_contains_chat_files_before_dashboard() -> None:
    bf = (REPO / "app" / "ui" / "build_frontend.py").read_text(encoding="utf-8")
    dash = bf.index('"js/components/DashboardView.jsx"')
    for name in EXPECTED_COMPONENTS:
        needle = f'"js/components/panels/chat/{name}.jsx"'
        assert needle in bf, f"LOAD_ORDER missing {needle}"
        assert bf.index(needle) < dash, f"{needle} must load before DashboardView"


def test_dashboard_has_html_reference_workspace_shell() -> None:
    template = (REPO / "app" / "ui" / "build_frontend.py").read_text(encoding="utf-8")
    src = (REPO / "app" / "static" / "js" / "components" / "DashboardView.jsx").read_text(encoding="utf-8")
    assert 'body class="h-screen overflow-hidden bg-[#F4F7F9] font-sans text-slate-800"' in template
    assert '<div id="root" class="h-full"></div>' in template
    assert "ChatPanel," in src
    assert not re.search(r"id:\s*'chat'", src)
    assert 'id="workspace"' in src
    assert 'id="left-panel"' in src
    assert 'id="module-grid"' in src
    assert 'id="resize-handle"' in src
    assert "dashboard-module-card" in src
    assert "dashboard-module-card--active" in src
    assert "desktopChatCollapsed" in src
    assert "flex h-screen flex-col overflow-hidden bg-[#F4F7F9] font-sans text-slate-800" in src
    assert "max-w-5xl mx-auto w-full" in src
    assert "module-grid-shell" in src
    assert "detail-scroll-shell" in src
    assert "overflow-x-auto pb-1" in src
    assert "grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" in src
    assert "text-lg font-semibold text-slate-800 mb-4" in src
    assert "text-lg font-semibold flex items-center gap-2" in src
    assert 'id="detail-content" className="text-sm text-slate-600"' not in src
    assert "text-[2rem]" not in src
    assert "text-[1.75rem]" not in src
    assert "@container" not in src
    assert "max-w-[1500px]" not in src
    assert "<ChatPanel" in src
