from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REDUCER = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js"

REQUIRED = [
    "user_input", "session_started", "turn_started", "run_started", "tool_started", "tool_progress", "tool_completed",
    "assistant_thinking", "execution_plan", "plan_step_status", "review_result", "awaiting_user_ack", "awaiting_resolution", "budget_warning",
    "provider_fallback", "error", "run_cancel_requested", "run_cancelling", "run_cancelled", "run_failed", "toggle_turn_collapse", "final", "done",
]


def test_reducer_file_contains_required_cases() -> None:
    assert REDUCER.is_file(), f"missing {REDUCER}"
    body = REDUCER.read_text(encoding="utf-8")
    for action in REQUIRED:
        assert f"case '{action}'" in body or f'case "{action}"' in body
    assert "window.AppComponents.chatReducer" in body
    assert "window.AppComponents.chatInitialState" in body


def test_reducer_walks_full_session() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "user_input", "content": "hello"},
        {"type": "session_started", "session_id": "s-1"},
        {"type": "turn_started", "turn_id": "turn-1", "client_turn_id": "client-1", "run_id": "run-1", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-29T00:00:00Z"},
        {"type": "run_started", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-29T00:00:01Z"},
        {"type": "execution_plan", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "execution_id": "trace-1", "request_summary": "分析 UID", "intent": "profile_uid", "request_understanding": {"intent": "profile_uid", "route_label": "单 UID 画像分析", "rewritten_goal": "执行 UID u1 的画像分析", "focus": ["summary"], "requires_tools": True, "route_reason": "需要执行画像流程。", "answer_mode": "tool_execution"}, "availability": {"checked_uids": ["u1"]}, "steps": [{"step_id": "s1", "title": "检查数据", "status": "pending"}], "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-29T00:00:02Z"},
        {"type": "plan_step_status", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "execution_id": "trace-1", "step_id": "s1", "status": "done", "result_summary": "App 数据存在", "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-29T00:00:03Z"},
        {"type": "tool_started", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "tool_call_id": "tc-1", "tool_name": "run_trace", "input": {}, "event_id": "evt-5", "event_seq": 5, "timestamp": "2026-05-29T00:00:04Z"},
        {"type": "tool_progress", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "tool_call_id": "tc-1", "tool_name": "run_profile", "progress_type": "profile_module_completed", "uid": "u1", "module": "app", "status": "ok", "completed": 1, "total": 2, "result": {"status": "ok"}, "event_id": "evt-6", "event_seq": 6, "timestamp": "2026-05-29T00:00:05Z"},
        {"type": "assistant_thinking", "content_delta": "正在"},
        {"type": "assistant_thinking", "content_delta": "分析"},
        {"type": "tool_completed", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "tool_call_id": "tc-1", "status": "ok", "output": {"ok": True}, "event_id": "evt-7", "event_seq": 7, "timestamp": "2026-05-29T00:00:06Z"},
        {"type": "review_result", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "execution_id": "trace-1", "status": "warning", "issues": [{"type": "missing_data", "bucket": "credit"}], "confidence_impact": "信用相关结论降级", "can_answer": True, "event_id": "evt-8", "event_seq": 8, "timestamp": "2026-05-29T00:00:07Z"},
        {"type": "awaiting_user_ack", "turn_id": "turn-1", "run_id": "run-1", "ack_id": "ack-1", "tool_call_id": "tc-2", "sql_text": "SELECT 1", "rows_estimated": 10, "event_id": "evt-9", "event_seq": 9, "timestamp": "2026-05-29T00:00:08Z"},
        {"type": "awaiting_resolution", "turn_id": "turn-1", "run_id": "run-1", "execution_id": "trace-1", "step_id": "clarify_scope", "resolution_id": "res-1", "resolution_type": "clarification", "prompt": "请补充国家和时间范围", "required_slots": ["country", "time_window"], "candidate_defaults": {"country": "mx"}, "event_id": "evt-10", "event_seq": 10, "timestamp": "2026-05-29T00:00:09Z"},
        {"type": "tool_completed", "turn_id": "turn-1", "run_id": "run-1", "trace_id": "trace-1", "tool_call_id": "tc-2", "status": "ok", "output": {}, "event_id": "evt-11", "event_seq": 11, "timestamp": "2026-05-29T00:00:10Z"},
        {"type": "budget_warning", "used": 9000, "limit": 10000, "percentage": 90},
        {"type": "provider_fallback", "from": "claude", "to": "openai", "reason": "rate_limit"},
        {"type": "final", "turn_id": "turn-1", "run_id": "run-1", "final_message": "完成", "total_rounds": 1, "total_tokens": 100, "confidence": 0.8, "event_id": "evt-12", "event_seq": 12, "timestamp": "2026-05-29T00:00:11Z"},
        {"type": "done"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["sessionId"] == "s-1"
    assert len(state["turns"]) == 1
    turn = state["turns"][0]
    assert turn["turnId"] == "turn-1"
    assert turn["assistantMessage"]["content"] == "完成"
    assert len(turn["runs"]) == 1
    run = turn["runs"][0]
    assert run["runId"] == "run-1"
    assert run["trace"]["request_summary"] == "分析 UID"
    assert run["trace"]["request_understanding"]["route_label"] == "单 UID 画像分析"
    assert run["trace"]["steps"][0]["status"] == "done"
    assert run["review"]["status"] == "warning"
    assert run["toolCalls"][0]["status"] == "ok"
    assert run["toolCalls"][0]["progress"][0]["module"] == "app"
    assert run["toolCalls"][0]["progress"][0]["completed"] == 1
    assert state["pendingAck"] is None
    assert state["pendingResolution"]["resolution_type"] == "clarification"
    assert state["budget"]["percentage"] == 90
    assert state["providerFallback"]["from"] == "claude"
    assert state["final"]["final_message"] == "完成"
    assert state["streamEnded"] is True


def test_reducer_merges_updated_execution_plan_and_unknown_step() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-2", "run_id": "run-2", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-29T00:00:00Z"},
        {"type": "run_started", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-29T00:00:01Z"},
        {"type": "execution_plan", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "execution_id": "trace-2", "request_summary": "cohort", "intent": "query_data_then_profile", "availability": None, "steps": [{"step_id": "query_data", "title": "查询 cohort UID", "status": "pending"}], "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-29T00:00:02Z"},
        {"type": "plan_step_status", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "execution_id": "trace-2", "step_id": "query_data", "status": "done", "result_summary": "已获取 1 个 UID", "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-29T00:00:03Z"},
        {"type": "execution_plan", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "execution_id": "trace-2", "request_summary": "cohort", "intent": "query_data_then_profile", "availability": {"checked_uids": ["u1"]}, "steps": [{"step_id": "query_data", "title": "查询 cohort UID", "status": "done"}, {"step_id": "check_data", "title": "检查数据完整性", "status": "pending"}, {"step_id": "run_profile", "title": "执行画像分析", "status": "pending"}], "event_id": "evt-5", "event_seq": 5, "timestamp": "2026-05-29T00:00:04Z"},
        {"type": "plan_step_status", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "execution_id": "trace-2", "step_id": "repair_credit", "status": "blocked", "result_summary": "repair 目前仅支持 mx。", "event_id": "evt-6", "event_seq": 6, "timestamp": "2026-05-29T00:00:05Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    steps = state["turns"][0]["runs"][0]["trace"]["steps"]
    step_ids = [step["step_id"] for step in steps]
    assert step_ids[:3] == ["query_data", "check_data", "run_profile"]
    assert "repair_credit" in step_ids
    dynamic_step = next(step for step in steps if step["step_id"] == "repair_credit")
    assert dynamic_step["status"] == "blocked"


def test_reducer_tracks_pending_resolution_separately_from_ack() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-3", "run_id": "run-3", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-29T00:00:00Z"},
        {"type": "awaiting_user_ack", "turn_id": "turn-3", "run_id": "run-3", "ack_id": "ack-1", "tool_call_id": "tc-1", "sql_text": "SELECT 1", "rows_estimated": 1, "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-29T00:00:01Z"},
        {"type": "awaiting_resolution", "turn_id": "turn-3", "run_id": "run-3", "execution_id": "trace-3", "resolution_id": "res-1", "step_id": "repair_strategy", "resolution_type": "repair_strategy", "prompt": "请选择 repair 策略", "options": ["analyze_existing_only", "repair_behavior_only", "repair_all_missing", "refine_scope"], "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-29T00:00:02Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["pendingAck"]["tool_call_id"] == "tc-1"
    assert state["pendingResolution"]["step_id"] == "repair_strategy"


def test_reducer_restores_pending_state_from_turn_runs() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    restore_evt = {
        "type": "restore_session",
        "session_id": "s-restore",
        "messages": [],
        "tool_calls": [],
        "execution_traces": [],
        "turns": [
            {
                "turn_id": "turn-restore",
                "session_id": "s-restore",
                "user_message": {"role": "user", "content": "query", "timestamp": "2026-05-30T00:00:00Z"},
                "assistant_message": None,
                "status": "running",
                "created_at": "2026-05-30T00:00:00Z",
                "updated_at": "2026-05-30T00:00:01Z",
                "runs": [
                    {
                        "run_id": "run-restore",
                        "status": "awaiting_user_ack",
                        "trace_id": "trace-restore",
                        "started_at": "2026-05-30T00:00:00Z",
                        "pending_ack": {
                            "ack_id": "ack-restore",
                            "tool_call_id": "tc-restore",
                            "sql_text": "查询摘要：\n本次将筛选符合条件的用户。\n\n原始 SQL：\nSELECT 1",
                            "rows_estimated": 3,
                            "created_at": "2026-05-30T00:00:01Z",
                        },
                        "pending_resolution": {
                            "resolution_id": "res-restore",
                            "step_id": "clarify_scope",
                            "resolution_type": "clarification",
                            "message": "请补充国家",
                            "options": [],
                            "created_at": "2026-05-30T00:00:02Z",
                        },
                    }
                ],
            }
        ],
    }
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
state = window.AppComponents.chatReducer(state, {json.dumps(restore_evt)});
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["pendingAck"]["ack_id"] == "ack-restore"
    assert state["pendingAck"]["run_id"] == "run-restore"
    assert "查询摘要" in state["pendingAck"]["sql_text"]
    assert "原始 SQL" in state["pendingAck"]["sql_text"]
    assert "SELECT 1" in state["pendingAck"]["sql_text"]
    assert state["pendingResolution"]["resolution_id"] == "res-restore"
    assert state["pendingResolution"]["run_id"] == "run-restore"


def test_reducer_persists_final_artifacts_on_assistant_turn() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "user_input", "content": "用 Data Agent 生成 SQL", "client_turn_id": "client-turn-artifact"},
        {"type": "turn_started", "turn_id": "turn-artifact", "client_turn_id": "client-turn-artifact", "run_id": "run-artifact", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-06-12T01:00:00Z"},
        {"type": "run_started", "turn_id": "turn-artifact", "run_id": "run-artifact", "trace_id": "trace-artifact", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-06-12T01:00:01Z"},
        {"type": "final", "turn_id": "turn-artifact", "run_id": "run-artifact", "final_message": "我已创建 SQL 审核任务。", "artifacts": [{"type": "data_agent_run", "run_id": "da-run-1"}], "total_rounds": 1, "total_tokens": 10, "confidence": 0.9, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-06-12T01:00:02Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["turns"][0]["assistantMessage"]["content"] == "我已创建 SQL 审核任务。"
    assert state["turns"][0]["artifacts"] == [{"type": "data_agent_run", "run_id": "da-run-1"}]


def test_reducer_restore_session_keeps_turn_artifacts() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    restore_evt = {
        "type": "restore_session",
        "session_id": "s-artifact",
        "messages": [],
        "tool_calls": [],
        "execution_traces": [],
        "turns": [
            {
                "turn_id": "turn-artifact",
                "session_id": "s-artifact",
                "user_message": {"role": "user", "content": "用 Data Agent 生成 SQL", "timestamp": "2026-06-12T01:00:00Z"},
                "assistant_message": {"role": "assistant", "content": "我已创建 SQL 审核任务。", "timestamp": "2026-06-12T01:00:02Z"},
                "artifacts": [{"type": "data_agent_run", "run_id": "da-run-1"}],
                "status": "completed",
                "created_at": "2026-06-12T01:00:00Z",
                "updated_at": "2026-06-12T01:00:02Z",
                "runs": [],
            }
        ],
    }
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
state = window.AppComponents.chatReducer(state, {json.dumps(restore_evt)});
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["turns"][0]["artifacts"] == [{"type": "data_agent_run", "run_id": "da-run-1"}]


def test_reducer_dedupes_same_event_id_but_keeps_same_seq_different_type() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-4", "run_id": "run-4", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T00:00:00Z"},
        {"type": "run_started", "turn_id": "turn-4", "run_id": "run-4", "trace_id": "trace-4", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-30T00:00:01Z"},
        {"type": "tool_started", "turn_id": "turn-4", "run_id": "run-4", "trace_id": "trace-4", "tool_call_id": "tc-4", "tool_name": "run_profile", "input": {}, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-30T00:00:02Z"},
        {"type": "tool_progress", "turn_id": "turn-4", "run_id": "run-4", "trace_id": "trace-4", "tool_call_id": "tc-4", "tool_name": "run_profile", "progress_type": "profile_module_completed", "uid": "u1", "module": "app", "status": "ok", "completed": 1, "total": 2, "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-30T00:00:03Z"},
        {"type": "tool_progress", "turn_id": "turn-4", "run_id": "run-4", "trace_id": "trace-4", "tool_call_id": "tc-4", "tool_name": "run_profile", "progress_type": "profile_module_completed", "uid": "u1", "module": "app", "status": "ok", "completed": 1, "total": 2, "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-30T00:00:03Z"},
        {"type": "review_result", "turn_id": "turn-4", "run_id": "run-4", "trace_id": "trace-4", "execution_id": "trace-4", "status": "pass", "issues": [], "confidence_impact": None, "can_answer": True, "event_id": "evt-5", "event_seq": 4, "timestamp": "2026-05-30T00:00:04Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    run = state["turns"][0]["runs"][0]
    assert len(run["toolCalls"][0]["progress"]) == 1
    assert run["review"]["status"] == "pass"


def test_reducer_creates_optimistic_turn_and_merges_turn_started() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "user_input", "content": "这个用户一共安装了什么软件？", "client_turn_id": "client-turn-1"},
        {"type": "turn_started", "turn_id": "turn-server-1", "client_turn_id": "client-turn-1", "run_id": "run-1", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T01:00:00Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert len(state["turns"]) == 1
    turn = state["turns"][0]
    assert turn["turnId"] == "turn-server-1"
    assert turn["clientTurnId"] == "client-turn-1"
    assert turn["userMessage"]["content"] == "这个用户一共安装了什么软件？"
    assert turn["status"] == "running"
    assert turn["collapsed"] is False


def test_reducer_final_auto_collapses_turn_but_can_be_reopened() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "user_input", "content": "画像分析", "client_turn_id": "client-turn-2"},
        {"type": "turn_started", "turn_id": "turn-2", "client_turn_id": "client-turn-2", "run_id": "run-2", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T01:00:00Z"},
        {"type": "run_started", "turn_id": "turn-2", "run_id": "run-2", "trace_id": "trace-2", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-30T01:00:01Z"},
        {"type": "final", "turn_id": "turn-2", "run_id": "run-2", "final_message": "完成", "total_rounds": 1, "total_tokens": 10, "confidence": 0.9, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-30T01:00:02Z"},
        {"type": "toggle_turn_collapse", "turn_id": "turn-2"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["turns"][0]["assistantMessage"]["content"] == "完成"
    assert state["turns"][0]["collapsed"] is False


def test_reducer_restores_pending_from_run_events_when_turn_pending_fields_missing() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    restore_evt = {
        "type": "restore_session",
        "session_id": "s-fallback",
        "messages": [],
        "tool_calls": [],
        "execution_traces": [],
        "turns": [
            {
                "turn_id": "turn-fallback",
                "session_id": "s-fallback",
                "user_message": {"role": "user", "content": "query", "timestamp": "2026-05-30T00:00:00Z"},
                "assistant_message": None,
                "status": "running",
                "created_at": "2026-05-30T00:00:00Z",
                "updated_at": "2026-05-30T00:00:01Z",
                "runs": [
                    {
                        "run_id": "run-fallback",
                        "status": "awaiting_user_ack",
                        "trace_id": "trace-fallback",
                        "started_at": "2026-05-30T00:00:00Z",
                    }
                ],
            }
        ],
        "run_events": [
            {
                "event_id": "evt-await-ack",
                "event_seq": 10,
                "session_id": "s-fallback",
                "turn_id": "turn-fallback",
                "run_id": "run-fallback",
                "event_type": "awaiting_user_ack",
                "timestamp": "2026-05-30T00:00:02Z",
                "payload": {
                    "tool_call_id": "tc-fallback",
                    "ack_id": "ack-fallback",
                    "sql_text": "SELECT 1",
                    "rows_estimated": 2,
                },
            }
        ],
    }
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
state = window.AppComponents.chatReducer(state, {json.dumps(restore_evt)});
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["pendingAck"]["ack_id"] == "ack-fallback"
    assert state["pendingAck"]["tool_call_id"] == "tc-fallback"


def test_reducer_run_failed_marks_run_terminal_and_releases_input() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-failed", "run_id": "run-failed", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T02:00:00Z"},
        {"type": "run_started", "turn_id": "turn-failed", "run_id": "run-failed", "trace_id": "trace-failed", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-30T02:00:01Z"},
        {"type": "tool_started", "turn_id": "turn-failed", "run_id": "run-failed", "trace_id": "trace-failed", "tool_call_id": "tc-failed", "tool_name": "run_profile", "input": {}, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-30T02:00:02Z"},
        {"type": "run_failed", "turn_id": "turn-failed", "run_id": "run-failed", "message": "tool failed", "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-30T02:00:03Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    turn = state["turns"][0]
    run = turn["runs"][0]
    assert turn["status"] == "failed"
    assert turn["collapsed"] is True
    assert run["status"] == "failed"
    assert run["toolCalls"][0]["status"] == "error"


def test_reducer_tool_completed_accepts_cancelled_status() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-cancelled-tool", "run_id": "run-cancelled-tool", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T02:10:00Z"},
        {"type": "run_started", "turn_id": "turn-cancelled-tool", "run_id": "run-cancelled-tool", "trace_id": "trace-cancelled-tool", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-30T02:10:01Z"},
        {"type": "tool_started", "turn_id": "turn-cancelled-tool", "run_id": "run-cancelled-tool", "trace_id": "trace-cancelled-tool", "tool_call_id": "tc-cancelled-tool", "tool_name": "run_profile", "input": {}, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-30T02:10:02Z"},
        {"type": "tool_completed", "turn_id": "turn-cancelled-tool", "run_id": "run-cancelled-tool", "trace_id": "trace-cancelled-tool", "tool_call_id": "tc-cancelled-tool", "status": "cancelled", "output": {}, "event_id": "evt-4", "event_seq": 4, "timestamp": "2026-05-30T02:10:03Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["toolCalls"][0]["status"] == "cancelled"
    assert state["turns"][0]["runs"][0]["toolCalls"][0]["status"] == "cancelled"


def test_reducer_tool_started_normalizes_cancelled_status() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "turn_started", "turn_id": "turn-cancelled-start", "run_id": "run-cancelled-start", "event_id": "evt-1", "event_seq": 1, "timestamp": "2026-05-30T02:20:00Z"},
        {"type": "run_started", "turn_id": "turn-cancelled-start", "run_id": "run-cancelled-start", "trace_id": "trace-cancelled-start", "event_id": "evt-2", "event_seq": 2, "timestamp": "2026-05-30T02:20:01Z"},
        {"type": "tool_started", "turn_id": "turn-cancelled-start", "run_id": "run-cancelled-start", "trace_id": "trace-cancelled-start", "tool_call_id": "tc-cancelled-start", "tool_name": "run_profile", "status": "cancelled", "input": {}, "event_id": "evt-3", "event_seq": 3, "timestamp": "2026-05-30T02:20:02Z"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["toolCalls"][0]["status"] == "cancelled"
    assert state["turns"][0]["runs"][0]["toolCalls"][0]["status"] == "cancelled"
