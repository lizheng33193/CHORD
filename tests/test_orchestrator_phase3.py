"""Phase 3 RED contract tests: ack_bus + agent_loop main loop + ACK branch + routes."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone

import pytest


def _assert_lifecycle_prefix(types: list[str]) -> None:
    assert types[:3] == ["session_started", "turn_started", "run_started"]


def _assert_ordered(types: list[str], *expected: str) -> None:
    positions = [types.index(item) for item in expected]
    assert positions == sorted(positions)


# ---- ack_bus ----

def test_ack_bus_resolve_returns_value():
    from app.services.orchestrator_agent.ack_bus import (
        open_ack, resolve_ack, wait_ack,
    )
    sid = "phase3-ack-1"
    ev = open_ack(sid)
    # 在另一个线程 resolve
    def resolver():
        time.sleep(0.05)
        resolve_ack(sid, True)
    t = threading.Thread(target=resolver)
    t.start()
    result = wait_ack(sid, timeout_sec=2.0)
    t.join()
    assert result is True


def test_ack_bus_timeout_returns_none():
    from app.services.orchestrator_agent.ack_bus import open_ack, wait_ack
    sid = "phase3-ack-timeout"
    open_ack(sid)
    result = wait_ack(sid, timeout_sec=0.1)
    assert result is None


def test_ack_bus_unknown_session_resolve_returns_false():
    from app.services.orchestrator_agent.ack_bus import resolve_ack
    assert resolve_ack("definitely-not-opened", True) is False


# ---- agent_loop main loop (mock LLM) ----

# R8 P0-A：用 asyncio.run 同步驱动 async generator，不依赖 pytest-asyncio
# （requirements.txt 未含 pytest-asyncio，与 Task 4.2 Golden runner 风格一致）。
def test_agent_loop_mock_run_trace_completes(monkeypatch):
    """Mock LLM 返回 run_trace tool_call → 然后 final → 验证 SSE 事件序列。"""
    import asyncio

    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    # Patch ModelClient.generate_structured 返回 deterministic decisions
    decisions = iter([
        {"status": "ok", "structured_result": {
            "tool_call": {"name": "run_trace", "arguments": {"uid": "MX0001", "days": 7}},
        }},
        {"status": "ok", "structured_result": {
            "final_message": "## 用户请求理解\n查 MX0001 轨迹\n", "confidence": 0.7,
        }},
    ])
    class _FakeClient:
        last_token_usage = {"prompt": 100, "completion": 50, "total": 150}
        def generate_structured(self, **kwargs):
            return next(decisions)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _FakeClient(),
    )
    # Patch run_trace 直接返回固定值，避免依赖 trace_analyzer 真实数据
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_trace",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {"events": [], "summary": {}},
        })(),
    )

    sess = create_session()

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=sess, prompt="看 MX0001 轨迹"):
            events.append(evt)
        return events

    events = asyncio.run(_drive())

    types = [e.get("type") for e in events]
    assert "session_started" in types
    assert "tool_started" in types
    assert "tool_completed" in types
    assert "final" in types
    assert types.count("tool_started") == 1
    assert types.count("tool_completed") == 1


def test_agent_loop_run_profile_emits_module_progress(monkeypatch, caplog):
    """run_profile should stream module-level progress before final completion."""
    import asyncio
    import logging

    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    def _fake_run_profile(inp, progress_callback=None):
        results = []
        for idx, mod in enumerate(inp.modules or ["app"], start=1):
            result = {
                "uid": inp.uids[0],
                "module": mod,
                "status": "ok",
                "data": {"summary": f"{mod} done", "structured_result": {}, "charts": [], "report_markdown": ""},
                "error": None,
            }
            if progress_callback:
                progress_callback({
                    "progress_type": "profile_module_completed",
                    "uid": inp.uids[0],
                    "module": mod,
                    "result": result,
                    "status": "ok",
                    "completed": idx,
                    "total": 2,
                })
            results.append({"uid": inp.uids[0], "module": mod, "result": result})
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": results,
                "cache_hits": 0,
                "cache_misses": 2,
            },
        })()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=["824812551379353600"],
            modules=["app", "behavior"],
            request_summary="分析 UID 824812551379353600 的 app/behavior 画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=["824812551379353600"],
            per_uid=[
                UidAvailability(
                    uid="824812551379353600",
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        _fake_run_profile,
    )

    sess = create_session()

    async def _drive():
        return [evt async for evt in run_agent_loop(session=sess, prompt="帮我分析一下824812551379353600这个用户")]

    with caplog.at_level(logging.INFO, logger="app.services.orchestrator_agent.agent_loop"):
        events = asyncio.run(_drive())
    types = [e.get("type") for e in events]

    assert types.index("tool_started") < types.index("tool_progress") < types.index("tool_completed")
    progress_events = [e for e in events if e.get("type") == "tool_progress"]
    assert [e["module"] for e in progress_events] == ["app", "behavior"]
    assert progress_events[-1]["completed"] == 2
    assert events[-1]["type"] == "final"
    progress_logs = [
        record for record in caplog.records
        if record.name == "app.services.orchestrator_agent.agent_loop"
        and getattr(record, "event", "") == "run_profile_module_completed"
    ]
    assert [getattr(record, "profile_module", None) for record in progress_logs] == ["app", "behavior"]
    assert progress_logs[-1].uid == "824812551379353600"
    assert progress_logs[-1].completed == 2
    assert progress_logs[-1].total == 2


def test_agent_loop_reuses_existing_run_profile_results_for_read_only_follow_up(monkeypatch):
    """Read-only follow-up should reuse prior run_profile results without rerunning tools."""
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import ToolCallRecord
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")
    session.tool_calls.append(ToolCallRecord(
        tool_name="run_profile",
        tool_call_id="tc-existing",
        input={
            "uids": ["824812551379353600"],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
        },
        output={
            "results": [
                {"uid": "824812551379353600", "module": "app", "result": {"status": "ok", "data": {"summary": "App 已有结论", "structured_result": {}, "charts": [], "report_markdown": ""}, "error": None}},
                {"uid": "824812551379353600", "module": "behavior", "result": {"status": "ok", "data": {"summary": "Behavior 已有结论", "structured_result": {}, "charts": [], "report_markdown": ""}, "error": None}},
                {"uid": "824812551379353600", "module": "credit", "result": {"status": "ok", "data": {"summary": "Credit 已有结论", "structured_result": {}, "charts": [], "report_markdown": ""}, "error": None}},
                {"uid": "824812551379353600", "module": "comprehensive", "result": {"status": "ok", "data": {"summary": "综合画像：S4 潜在流失", "structured_result": {"segment": "S4"}, "charts": [], "report_markdown": ""}, "error": None}},
                {"uid": "824812551379353600", "module": "product", "result": {"status": "ok", "data": {"summary": "产品策略：挽回式续贷", "structured_result": {}, "charts": [], "report_markdown": ""}, "error": None}},
                {"uid": "824812551379353600", "module": "ops", "result": {"status": "ok", "data": {"summary": "运营策略：WhatsApp 晚间触达", "structured_result": {}, "charts": [], "report_markdown": ""}, "error": None}},
            ],
            "cache_hits": 6,
            "cache_misses": 0,
        },
        status="done",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    ))

    model_calls: list[dict] = []

    class _EvidenceClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            model_calls.append(kwargs)
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "这是基于已有画像证据的回答：综合画像显示该用户属于 S4 潜在流失。",
                    "confidence": 0.9,
                },
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _EvidenceClient(),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你能跟我简单描述一下这个用户的综合画像吗？")]

    events = asyncio.run(_drive())
    types = [e.get("type") for e in events]
    _assert_lifecycle_prefix(types)
    _assert_ordered(types, "run_started", "execution_plan", "review_result", "final")
    assert types.count("plan_step_status") >= 2
    assert types[-1] == "final"
    assert model_calls
    assert "已有画像证据" in events[-1]["final_message"]
    assert "S4" in events[-1]["final_message"]


def test_agent_loop_reuses_workspace_snapshot_before_tool_dispatch(monkeypatch):
    """Workspace snapshot attached to the session should satisfy read-only follow-ups."""
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像：近30天登录2天，总互动593次，流失风险高。",
                "structured_result": {"risk_level": "high"},
            }
        ],
    }

    model_calls: list[dict] = []

    class _EvidenceClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            model_calls.append(kwargs)
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "这是基于已有画像证据的回答：该用户近30天登录偏低，流失风险高。",
                    "confidence": 0.88,
                },
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _EvidenceClient(),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我总结一下这个用户的行为画像特点")]

    events = asyncio.run(_drive())
    types = [e.get("type") for e in events]
    _assert_lifecycle_prefix(types)
    _assert_ordered(types, "run_started", "execution_plan", "review_result", "final")
    assert types.count("plan_step_status") >= 2
    assert types[-1] == "final"
    assert model_calls
    assert "已有画像证据" in events[-1]["final_message"]
    assert "流失风险高" in events[-1]["final_message"]


def test_agent_loop_snapshot_guard_respects_explicit_rerun_request(monkeypatch):
    """Explicit rerun keywords must bypass snapshot reuse and call run_profile again."""
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=["824812551379353600"],
            per_uid=[
                UidAvailability(
                    uid="824812551379353600",
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 1},
        })(),
    )

    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {"uid": "824812551379353600", "module": "comprehensive", "summary": "旧综合画像", "structured_result": {"segment": "S4"}},
        ],
    }

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请重新分析一下这个用户的综合画像")]

    events = asyncio.run(_drive())
    types = [e.get("type") for e in events]
    assert "tool_started" in types
    assert events[-1]["type"] == "final"


def test_agent_loop_snapshot_guard_blocks_read_only_followup_when_required_module_missing(monkeypatch):
    """Missing modules in the reusable workspace should block read-only follow-up without an explicit UID."""
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    class _ShouldNotCallModelClient:
        last_token_usage = {"prompt": 0, "completion": 0, "total": 0}

        def generate_structured(self, **kwargs):
            raise AssertionError("LLM should not run when reusable workspace is insufficient and no UID is provided")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _ShouldNotCallModelClient(),
    )

    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {"uid": "824812551379353600", "module": "app", "summary": "只有 app 模块", "structured_result": {}},
        ],
    }

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你能跟我简单描述一下这个用户的综合画像吗？")]

    events = asyncio.run(_drive())
    types = [e.get("type") for e in events]
    _assert_lifecycle_prefix(types)
    _assert_ordered(types, "run_started", "execution_plan", "review_result", "final")
    assert types.count("plan_step_status") >= 2
    assert types[-1] == "final"
    assert "先分析 UID" in events[-1]["final_message"]


# ---- FastAPI routes ----

def test_orchestrator_chat_route_returns_sse(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    with client.stream(
        "POST", "/api/orchestrator/chat",
        json={"prompt": "你好"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")


def test_get_session_returns_404_for_unknown():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/orchestrator/sessions/definitely-not-existing")
    assert r.status_code == 404


def test_ack_route_unresolved_returns_false():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/never-opened/ack",
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": False}
