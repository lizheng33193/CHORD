from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path

from app.services.orchestrator_agent.execution.data_query_runner import (
    DataQueryPreview,
    DataQueryRunResult,
    DataQueryRunner,
    DataQueryRunSpec,
)
from app.services.orchestrator_agent.runtime import session_lifecycle
from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
from app.services.orchestrator_agent.runtime.human_input import HumanInputController
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.session_store import create_session


class _FakeHumanInput:
    def __init__(self, *, ack_status: str = "approved", call_order: list[str] | None = None):
        self.ack_status = ack_status
        self.call_order = call_order if call_order is not None else []
        self.requested = 0
        self.waited = 0

    async def request_ack(self, **kwargs):
        self.requested += 1
        self.call_order.append("open_ack")
        return kwargs

    async def wait_for_ack(self, **kwargs):
        self.waited += 1
        self.call_order.append("wait_ack")
        return type("Ack", (), {"status": self.ack_status})()


def _make_runner(*, human_input):
    session = create_session(country="mx")
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = DataQueryRunner(
        session=session,
        lifecycle=lifecycle,
        events=events,
        human_input=human_input,
    )
    return session, runner


def test_human_input_wait_for_ack_returns_cancelled_when_should_cancel():
    controller = HumanInputController()
    session_id = "ack-cancel-test"

    async def run():
        await controller.request_ack(session_id=session_id, ack_id="ack-1", run_id="r1")
        checks = {"count": 0}

        def _should_cancel():
            checks["count"] += 1
            return checks["count"] >= 2

        return await controller.wait_for_ack(
            session_id=session_id,
            timeout_seconds=1.0,
            poll_interval=0.01,
            should_cancel=_should_cancel,
        )

    started = time.monotonic()
    result = asyncio.run(run())
    assert result.status == "cancelled"
    assert time.monotonic() - started < 0.5


def test_data_query_runner_preview_completed_skips_ack(monkeypatch):
    saves: list[str] = []
    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))
    human_input = _FakeHumanInput()
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="completed",
                    output={"uids": ["u1"], "rows_actual": 1},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(AssertionError("complete_func should not run")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert items[0]["type"] == "tool_started"
    assert items[1]["type"] == "tool_completed"
    assert items[1]["status"] == "ok"
    assert isinstance(items[2], DataQueryRunResult)
    assert items[2].status == "completed"
    assert human_input.requested == 0
    assert human_input.waited == 0
    assert session.tool_calls[0].status == "done"
    assert saves


def test_data_query_runner_streams_awaiting_ack_before_wait():
    call_order: list[str] = []
    human_input = _FakeHumanInput(ack_status="approved", call_order=call_order)
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder-ignored",
                        "tool_call_id": "placeholder-ignored",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: {"uids": ["u1"], "rows_actual": 1},
            )
        )
        seen = [handle.started_event]
        async for item in handle.stream():
            if item.event is not None:
                seen.append(item.event)
                if item.event["type"] == "awaiting_user_ack":
                    call_order.append("awaiting_user_ack")
            if item.result is not None:
                seen.append(item.result)
        return seen

    seen = asyncio.run(run())
    awaiting = next(evt for evt in seen if isinstance(evt, dict) and evt.get("type") == "awaiting_user_ack")
    assert awaiting["sql_text"] == "SELECT uid FROM t"
    assert awaiting["rows_estimated"] == 1
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert isinstance(seen[-1], DataQueryRunResult)
    assert seen[-1].status == "completed"


def test_data_query_runner_keeps_display_sql_text_separate_from_raw_preview_sql():
    call_order: list[str] = []
    human_input = _FakeHumanInput(ack_status="approved", call_order=call_order)
    session, runner = _make_runner(human_input=human_input)
    display_sql_text = (
        "查询摘要：\n本次将筛选符合条件的用户，并返回 UID 列表。\n\n"
        "确认提示：\n该查询仅会在你确认后执行。\n\n"
        "原始 SQL：\nSELECT uid FROM t"
    )
    observed_preview_sql: list[str] = []
    observed_raw_sql: list[str] = []

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder-ignored",
                        "tool_call_id": "placeholder-ignored",
                        "sql_text": display_sql_text,
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (
                    observed_preview_sql.append(str((preview.ack_payload or {}).get("sql_text") or "")),
                    observed_raw_sql.append(str((preview.raw_preview or {}).get("sql_text") or "")),
                    {"uids": ["u1"], "rows_actual": 1},
                )[-1],
            )
        )
        seen = [handle.started_event]
        async for item in handle.stream():
            if item.event is not None:
                seen.append(item.event)
                if item.event["type"] == "awaiting_user_ack":
                    call_order.append("awaiting_user_ack")
            if item.result is not None:
                seen.append(item.result)
        return seen

    seen = asyncio.run(run())
    awaiting = next(evt for evt in seen if isinstance(evt, dict) and evt.get("type") == "awaiting_user_ack")
    assert set(awaiting) == {
        "type",
        "ack_id",
        "tool_call_id",
        "sql_text",
        "rows_estimated",
        "event_id",
        "event_seq",
        "session_id",
        "turn_id",
        "run_id",
        "event_type",
        "timestamp",
    }
    assert awaiting["sql_text"] == display_sql_text
    assert awaiting["sql_text"] != "SELECT uid FROM t"
    assert "查询摘要" in awaiting["sql_text"]
    assert "原始 SQL" in awaiting["sql_text"]
    assert "SELECT uid FROM t" in awaiting["sql_text"]
    assert observed_preview_sql == [display_sql_text]
    assert observed_raw_sql == ["SELECT uid FROM t"]
    assert "查询摘要" not in observed_raw_sql[0]
    assert "确认提示" not in observed_raw_sql[0]
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]


def test_data_query_runner_rejected_closes_record_without_tool_completed_ok():
    human_input = _FakeHumanInput(ack_status="rejected")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder",
                        "tool_call_id": "placeholder",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(AssertionError("complete_func should not run")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert not any(isinstance(item, dict) and item.get("type") == "tool_completed" and item.get("status") == "ok" for item in items)
    result = next(item for item in items if isinstance(item, DataQueryRunResult))
    assert result.status == "rejected"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": "rejected", "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


def test_data_query_runner_expired_closes_record_without_tool_completed_ok():
    human_input = _FakeHumanInput(ack_status="expired")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder",
                        "tool_call_id": "placeholder",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(AssertionError("complete_func should not run")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert not any(isinstance(item, dict) and item.get("type") == "tool_completed" and item.get("status") == "ok" for item in items)
    result = next(item for item in items if isinstance(item, DataQueryRunResult))
    assert result.status == "expired"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": "expired", "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


def test_data_query_runner_cancelled_closes_record_without_tool_completed_ok():
    human_input = _FakeHumanInput(ack_status="cancelled")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder",
                        "tool_call_id": "placeholder",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(AssertionError("complete_func should not run")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert not any(isinstance(item, dict) and item.get("type") == "tool_completed" and item.get("status") == "ok" for item in items)
    result = next(item for item in items if isinstance(item, DataQueryRunResult))
    assert result.status == "cancelled"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": "cancelled", "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


def test_data_query_runner_complete_error_clears_pending_and_marks_error():
    human_input = _FakeHumanInput(ack_status="approved")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder",
                        "tool_call_id": "placeholder",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    result = next(item for item in items if isinstance(item, DataQueryRunResult))
    assert result.status == "failed"
    assert session.tool_calls[0].status == "error"
    assert session.tool_calls[0].output == {"error": "boom"}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"
    completed = next(item for item in items if isinstance(item, dict) and item.get("type") == "tool_completed")
    assert completed["status"] == "error"


def test_data_query_runner_missing_uid_output_marks_error_without_tool_completed_ok():
    human_input = _FakeHumanInput(ack_status="approved")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            DataQueryRunSpec(
                trace_id="trace-1",
                input_payload={"request": "拉一批用户", "country": "mx"},
                preview_func=lambda: DataQueryPreview(
                    status="awaiting_ack",
                    ack_payload={
                        "ack_id": "placeholder",
                        "tool_call_id": "placeholder",
                        "sql_text": "SELECT uid FROM t",
                        "rows_estimated": 1,
                    },
                    raw_preview={"child": object(), "sql_text": "SELECT uid FROM t"},
                ),
                complete_func=lambda preview: (_ for _ in ()).throw(
                    ValueError("query_data result missing uid column")
                ),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())

    assert not any(
        isinstance(item, dict)
        and item.get("type") == "tool_completed"
        and item.get("status") == "ok"
        for item in items
    )
    result = next(item for item in items if isinstance(item, DataQueryRunResult))
    assert result.status == "failed"
    assert result.error == "query_data result missing uid column"
    assert session.tool_calls[0].status == "error"
    assert session.tool_calls[0].output == {"error": "query_data result missing uid column"}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


def test_data_query_runner_module_does_not_import_agent_loop():
    path = Path("app/services/orchestrator_agent/execution/data_query_runner.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.agent_loop":
            raise AssertionError("data_query_runner.py imports agent_loop directly")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.orchestrator_agent.agent_loop":
                    raise AssertionError("data_query_runner.py imports agent_loop directly")
