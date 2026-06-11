from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app" / "static" / "js" / "app.jsx"
CHAT_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatPanel.jsx"
API = REPO / "app" / "static" / "js" / "services" / "api.js"
MEMORY_INSPECTOR = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "MemoryInspector.jsx"
DASHBOARD = REPO / "app" / "static" / "js" / "components" / "DashboardView.jsx"
MODULE_STATUS = REPO / "app" / "static" / "js" / "components" / "common" / "ModuleStatusPanel.jsx"


def test_app_owns_tab_url_routing() -> None:
    src = APP.read_text(encoding="utf-8")
    assert "VALID_DASHBOARD_TABS" in src
    assert "function getInitialDashboardTab()" in src
    assert "function getInitialViewFromUrl()" in src
    assert re.search(r"new\s+URLSearchParams\s*\(\s*window\.location\.search\s*\)", src)
    assert re.search(r"\.get\(\s*['\"]tab['\"]\s*\)", src)
    assert re.search(r"\.get\(\s*['\"]session['\"]\s*\)", src)
    assert re.search(r"useState\s*\(\s*getInitialViewFromUrl\s*\)", src)
    assert re.search(r"useState\s*\(\s*getInitialDashboardTab\s*\)", src)
    assert re.search(r"tab\s*===\s*['\"]chat['\"]\s*\|\|\s*params\.get\(\s*['\"]session['\"]\s*\)", src)
    assert "window.history.replaceState" in src


def test_app_persists_workspace_snapshot_in_session_storage() -> None:
    src = APP.read_text(encoding="utf-8")

    assert "WORKSPACE_SNAPSHOT_STORAGE_KEY" in src
    assert "buildWorkspaceSnapshotFromAppState" in src
    assert "restoreWorkspaceFromSession" in src
    assert "window.sessionStorage.getItem" in src
    assert "window.sessionStorage.setItem" in src


def test_chat_panel_restores_and_writes_session_url() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")
    assert re.search(r"\.get\(\s*['\"]session['\"]\s*\)", src)
    assert "fetchOrchestratorSession" in src
    assert re.search(r"\.set\(\s*['\"]session['\"]", src)
    assert re.search(r"\.set\(\s*['\"]tab['\"]\s*,\s*['\"]chat['\"]", src)
    assert "window.history.replaceState" in src


def test_memory_inspector_wires_management_api() -> None:
    api_src = API.read_text(encoding="utf-8")
    inspector_src = MEMORY_INSPECTOR.read_text(encoding="utf-8")
    panel_src = CHAT_PANEL.read_text(encoding="utf-8")

    assert "function fetchMemoryStatus" in api_src
    assert "/api/orchestrator/memory/status" in api_src
    assert "function queryMemory" in api_src
    assert "/api/orchestrator/memory/query" in api_src
    assert "function listMemories" in api_src
    assert "/api/orchestrator/memory/list" in api_src
    assert "function createMemory" in api_src
    assert "function updateMemory" in api_src
    assert "function archiveMemory" in api_src
    assert "function restoreMemory" in api_src
    assert "function deleteMemory" in api_src
    assert "window.AppComponents.MemoryInspector = MemoryInspector;" in inspector_src
    assert "fetchMemoryStatus" in inspector_src
    assert "queryMemory" in inspector_src
    assert "listMemories" in inspector_src
    assert "createMemory" in inspector_src
    assert "updateMemory" in inspector_src
    assert "archiveMemory" in inspector_src
    assert "restoreMemory" in inspector_src
    assert "deleteMemory" in inspector_src
    assert "MemoryInspector" in panel_src


def test_memory_inspector_switches_chat_history_without_full_page_navigation() -> None:
    inspector_src = MEMORY_INSPECTOR.read_text(encoding="utf-8")

    assert "onOpenSession" in inspector_src
    assert "onRestoreSession" in inspector_src
    assert "window.location.assign" not in inspector_src
    assert "恢复该次分析结果" in inspector_src


def test_chat_panel_uses_memory_drawer_instead_of_inline_block() -> None:
    panel_src = CHAT_PANEL.read_text(encoding="utf-8")
    inspector_src = MEMORY_INSPECTOR.read_text(encoding="utf-8")

    assert "memoryOpen" in panel_src
    assert "setMemoryOpen" in panel_src
    assert "onOpenMemory" in panel_src
    assert "collapsed = false" in panel_src
    assert "onToggleCollapse" in panel_src
    assert 'id="chat-panel-header"' in panel_src
    assert 'id="chat-panel-body"' in panel_src
    assert 'id="chat-panel-footer"' in panel_src
    assert 'id="chat-container"' in panel_src
    assert 'id="collapse-chat-btn"' in panel_src
    assert 'id="chat-history-btn"' in panel_src
    assert "chatStatusText" not in panel_src
    assert "等待提问" not in panel_src
    assert 'text-[11px]' not in panel_src
    assert 'text-[10px]' in panel_src
    assert '<MemoryInspector open={memoryOpen}' in panel_src or '<MemoryInspector\n' in panel_src
    assert "function MemoryInspector({ open, onClose" in inspector_src
    assert "fixed inset-0" in inspector_src
    assert "createPortal" in inspector_src
    assert "document.body" in inspector_src
    assert "历史记忆" in inspector_src
    assert "onClose" in inspector_src
    assert '<ChatAckCard pending={state.pendingAck}' not in panel_src


def test_chat_panel_wires_profile_progress_and_safe_success_copy() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")
    assert "tool_progress" in (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js").read_text(encoding="utf-8")
    assert "execution_plan" in (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js").read_text(encoding="utf-8")
    assert "ChatExecutionTraceCard" in src
    assert "profile_module_completed" in src
    assert "dispatchProfileRow" in src
    assert "dispatchProfileRow({" in src
    assert "完整画像已生成" in src
    assert "画像分析进行中" in src
    assert "可查看完整 dashboard" not in src
    assert "state.pendingAck?.run_id === run.runId" in src
    assert "state.pendingResolution?.run_id === run.runId" in src


def test_tool_call_stream_supports_cancelled_status() -> None:
    src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatToolCallStream.jsx").read_text(encoding="utf-8")
    assert "cancelled" in src
    assert "CANCELLED" in src


def test_chat_panel_restores_request_understanding_and_trace_card_uses_explanation_blocks() -> None:
    panel_src = CHAT_PANEL.read_text(encoding="utf-8")
    trace_card_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatExecutionTraceCard.jsx").read_text(encoding="utf-8")

    assert "request_understanding: trace.request_understanding || null" in panel_src
    assert "需求理解" in trace_card_src
    assert "路径说明" in trace_card_src
    assert "为什么这样做" in trace_card_src
    assert "观察结果" in trace_card_src
    assert "后续" in trace_card_src
    assert "等待执行" in trace_card_src


def test_chat_panel_clarification_uses_editable_form_and_resolution_controls() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")

    assert "time_window" in src
    assert "auto_profile" in src
    assert "国家" in src
    assert "时间范围" in src
    assert "自动继续画像" in src
    assert "使用默认国家 + 最近 7 天" not in src


def test_memory_inspector_separates_session_history_and_long_term_memory() -> None:
    api_src = API.read_text(encoding="utf-8")
    inspector_src = MEMORY_INSPECTOR.read_text(encoding="utf-8")

    assert "function fetchOrchestratorSessions" in api_src
    assert "/api/orchestrator/sessions" in api_src
    assert "短期会话历史" in inspector_src
    assert "长期记忆" in inspector_src
    assert "不参与长期记忆召回" in inspector_src
    assert "移入已删除" in inspector_src
    assert "active 会被召回" in inspector_src


def test_memory_inspector_explains_session_filters_and_recall_reason() -> None:
    inspector_src = MEMORY_INSPECTOR.read_text(encoding="utf-8")

    assert "搜索会话" in inspector_src
    assert "会话状态" in inspector_src
    assert "会话国家" in inspector_src
    assert "为什么会被召回" in inspector_src
    assert "会被召回：active + 当前 identity + 查询相关" in inspector_src
    assert "不参与召回" in inspector_src


def test_dashboard_loading_states_use_skeleton_progress() -> None:
    dashboard_src = DASHBOARD.read_text(encoding="utf-8")
    module_status_src = MODULE_STATUS.read_text(encoding="utf-8")

    assert "skeleton-shimmer" in dashboard_src
    assert "loading-progress-bar" in dashboard_src
    assert "模块分析骨架屏" in module_status_src
    assert "skeleton-shimmer" in module_status_src


def test_dashboard_uses_split_workspace_with_persistent_chat() -> None:
    dashboard_src = DASHBOARD.read_text(encoding="utf-8")

    assert 'id="workspace"' in dashboard_src
    assert 'id="left-panel"' in dashboard_src
    assert "dashboard-chat-column" in dashboard_src
    assert "dashboard-resize-rail" in dashboard_src
    assert "dashboard-resize-handle" in dashboard_src
    assert "dashboard-module-card" in dashboard_src
    assert "dashboard-module-card--active" in dashboard_src
    assert "module-grid-shell" in dashboard_src
    assert "detail-scroll-shell" in dashboard_src
    assert "h-14 shrink-0" in dashboard_src
    assert "minWidth: 800" not in dashboard_src
    assert "setFloatingChatOpen" in dashboard_src
    assert "desktopChatCollapsed" in dashboard_src
    assert "max-w-[1500px]" not in dashboard_src
    assert "display: activeTab === 'chat'" not in dashboard_src


def test_chat_message_list_uses_larger_readable_chat_typography() -> None:
    src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatMessageList.jsx").read_text(encoding="utf-8")

    assert "text-[14px]" in src
    assert "leading-7" in src
    assert "text-[13px]" not in src


def test_chat_panel_restores_on_session_change_and_resets_local_state() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")

    assert "externalSessionId" in src
    assert "dispatch({ type: 'reset_session' })" in src
    assert "onOpenSession" in src
    assert "onRestoreSession" in src


def test_chat_panel_hydrates_history_only_when_session_id_changes() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")

    assert "lastHydratedSessionIdRef" in src
    assert "onSessionChangeRef" in src
    assert "onRestoreWorkspaceSessionRef" in src
    assert "if (lastHydratedSessionIdRef.current === sessionId) return undefined;" in src
    assert "}, [externalSessionId, resetSessionArtifacts]);" in src
    assert "}, [externalSessionId, onSessionChange, resetSessionArtifacts]);" not in src


def test_chat_panel_marks_history_tool_calls_and_filters_live_callbacks() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")
    reducer_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js").read_text(encoding="utf-8")

    assert "source: 'history'" in src
    assert "source: 'live'" in reducer_src
    assert src.count("if (t.source !== 'live') return;") >= 3
    assert "const hasPending = state.toolCalls.some((t) => t.source === 'live' && t.status === 'pending');" in src


def test_chat_panel_uses_optimistic_turn_and_stop_feedback_copy() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")
    reducer_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js").read_text(encoding="utf-8")

    assert "client-turn-" in src
    assert "dispatch({ type: 'user_input', content, client_turn_id: clientTurnId })" in src
    assert "cancel_requested" in src
    assert "cancelling" in src
    assert "已发送停止请求" in src
    assert "正在停止本轮执行" in src
    assert "toggle_turn_collapse" in reducer_src
    assert "展开执行过程" in src


def test_chat_panel_uses_derived_run_stopping_and_failed_trace_summary_copy() -> None:
    panel_src = CHAT_PANEL.read_text(encoding="utf-8")
    trace_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatExecutionTraceCard.jsx").read_text(encoding="utf-8")
    input_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatInputBox.jsx").read_text(encoding="utf-8")
    reducer_src = (REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js").read_text(encoding="utf-8")

    assert "runStopping" in panel_src
    assert "already_finished" in panel_src
    assert "not_found" in panel_src
    assert "run_failed" in reducer_src
    assert "因停止而跳过" in trace_src
    assert "因失败而未执行" in trace_src
    assert "计划步骤未执行" in trace_src
    assert "title={stopping ? '停止中...' : running ? '停止当前执行' : '发送'}" in input_src


def test_app_stabilizes_chat_session_callbacks() -> None:
    src = APP.read_text(encoding="utf-8")

    assert "useCallback" in src
    assert "const handleChatSessionChange = useCallback(" in src
    assert "const handleRestoreWorkspaceSession = useCallback(" in src
