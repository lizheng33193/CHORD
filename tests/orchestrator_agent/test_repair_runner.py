from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

from app.services.orchestrator_agent.execution.repair_runner import (
    RepairPrepare,
    RepairRunResult,
    RepairRunSpec,
    RepairRunner,
)
from app.services.orchestrator_agent.loop_context import HumanInputResult
from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
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
        return HumanInputResult(status=self.ack_status)


class _BlockingHumanInput:
    def __init__(self):
        self.requested = 0
        self.waited = 0
        self.wait_started = asyncio.Event()
        self.release = asyncio.Event()

    async def request_ack(self, **kwargs):
        self.requested += 1
        return kwargs

    async def wait_for_ack(self, **kwargs):
        self.waited += 1
        self.wait_started.set()
        await self.release.wait()
        return HumanInputResult(status="approved")


def _make_runner(*, human_input):
    session = create_session(country="mx")
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = RepairRunner(
        session=session,
        lifecycle=lifecycle,
        events=events,
        human_input=human_input,
    )
    return session, runner


@pytest.mark.timeout(3)
def test_repair_runner_prepare_then_execute_approved():
    call_order: list[str] = []
    human_input = _FakeHumanInput(ack_status="approved", call_order=call_order)
    session, runner = _make_runner(human_input=human_input)
    executed: list[str] = []

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="prepare_then_execute",
                prepare_func=lambda: RepairPrepare(
                    sql_text="UPDATE t SET x=1",
                    rows_estimated=1,
                    raw_prepared={"prepared": True},
                ),
                execute_func=lambda prepared: (executed.append(prepared.sql_text) or {"written_uids": ["u1"]}),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            if item.event is not None:
                items.append(item.event)
                if item.event["type"] == "awaiting_user_ack":
                    call_order.append("awaiting_user_ack")
            if item.result is not None:
                items.append(item.result)
        return items

    items = asyncio.run(run())
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert executed == ["UPDATE t SET x=1"]
    completed = next(item for item in items if isinstance(item, dict) and item.get("type") == "tool_completed")
    assert completed["status"] == "ok"
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == "completed"
    assert session.tool_calls[0].status == "done"


@pytest.mark.timeout(3)
@pytest.mark.parametrize("ack_status", ["rejected", "expired", "cancelled"])
def test_repair_runner_prepare_then_execute_non_approved_closes_record(ack_status: str):
    human_input = _FakeHumanInput(ack_status=ack_status)
    session, runner = _make_runner(human_input=human_input)
    executed = []

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="prepare_then_execute",
                prepare_func=lambda: RepairPrepare(
                    sql_text="UPDATE t SET x=1",
                    rows_estimated=1,
                ),
                execute_func=lambda prepared: (executed.append(prepared.sql_text) or {"written_uids": ["u1"]}),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert executed == []
    assert not any(isinstance(item, dict) and item.get("type") == "tool_completed" and item.get("status") == "ok" for item in items)
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == ack_status
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": ack_status, "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


@pytest.mark.timeout(3)
def test_repair_runner_legacy_before_ack_blocks_until_approved():
    call_order: list[str] = []
    human_input = _FakeHumanInput(ack_status="approved", call_order=call_order)
    session, runner = _make_runner(human_input=human_input)
    gate_seen = threading.Event()
    gate_released = threading.Event()
    state = {"continued": False}

    def _legacy_execute(before_ack):
        gate_seen.set()
        before_ack("UPDATE credit SET ok=1", 1)
        state["continued"] = True
        gate_released.set()
        return {"written_uids": ["u1"]}

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="legacy_ack_inside_tool",
                legacy_execute_func=_legacy_execute,
            )
        )
        assert handle.started_event is not None
        seen = [handle.started_event]
        async for item in handle.stream():
            if item.event is not None:
                seen.append(item.event)
                if item.event["type"] == "awaiting_user_ack":
                    call_order.append("awaiting_user_ack")
                    assert gate_seen.wait(0.5)
                    assert state["continued"] is False
            if item.result is not None:
                seen.append(item.result)
        return seen

    seen = asyncio.run(run())
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert gate_released.wait(0.5)
    assert state["continued"] is True
    result = next(item for item in seen if isinstance(item, RepairRunResult))
    assert result.status == "completed"


@pytest.mark.timeout(3)
@pytest.mark.parametrize("ack_status", ["rejected", "expired", "cancelled"])
def test_repair_runner_legacy_before_ack_non_approved_aborts_worker(ack_status: str):
    human_input = _FakeHumanInput(ack_status=ack_status)
    session, runner = _make_runner(human_input=human_input)
    state = {"continued": False}

    def _legacy_execute(before_ack):
        before_ack("UPDATE credit SET ok=1", 1)
        state["continued"] = True
        return {"written_uids": ["u1"]}

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="legacy_ack_inside_tool",
                legacy_execute_func=_legacy_execute,
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert state["continued"] is False
    assert not any(isinstance(item, dict) and item.get("type") == "tool_completed" and item.get("status") == "ok" for item in items)
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == ack_status
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": ack_status, "executed": False}


@pytest.mark.timeout(3)
def test_repair_runner_legacy_without_before_ack_keeps_direct_completion():
    human_input = _FakeHumanInput(ack_status="approved")
    session, runner = _make_runner(human_input=human_input)

    def _legacy_execute(before_ack):
        del before_ack
        return {"written_uids": ["u1"]}

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="legacy_ack_inside_tool",
                legacy_execute_func=_legacy_execute,
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    assert human_input.requested == 0
    assert human_input.waited == 0
    assert not any(isinstance(item, dict) and item.get("type") == "awaiting_user_ack" for item in items)
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == "completed"


@pytest.mark.timeout(3)
def test_repair_runner_execute_error_cleans_pending_and_marks_error():
    human_input = _FakeHumanInput(ack_status="approved")
    session, runner = _make_runner(human_input=human_input)

    async def run():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="prepare_then_execute",
                prepare_func=lambda: RepairPrepare(sql_text="UPDATE t SET x=1", rows_estimated=1),
                execute_func=lambda prepared: (_ for _ in ()).throw(RuntimeError("boom")),
            )
        )
        items = [handle.started_event]
        async for item in handle.stream():
            items.append(item.event or item.result)
        return items

    items = asyncio.run(run())
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == "failed"
    assert session.tool_calls[0].status == "error"
    assert session.tool_calls[0].output == {"error": "boom"}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"
    completed = next(item for item in items if isinstance(item, dict) and item.get("type") == "tool_completed")
    assert completed["status"] == "error"


@pytest.mark.timeout(3)
def test_repair_runner_prepare_then_execute_external_cancel_cleans_pending_and_marks_done():
    human_input = _BlockingHumanInput()
    session, runner = _make_runner(human_input=human_input)

    async def run_and_cancel():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="prepare_then_execute",
                prepare_func=lambda: RepairPrepare(sql_text="UPDATE t SET x=1", rows_estimated=1),
                execute_func=lambda prepared: {"written_uids": ["u1"]},
            )
        )
        seen: list[object] = [handle.started_event]

        async def _consume():
            async for item in handle.stream():
                seen.append(item.event or item.result)

        task = asyncio.create_task(_consume())
        await human_input.wait_started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            seen.append("cancelled-error")
        return seen

    items = asyncio.run(run_and_cancel())
    assert "cancelled-error" not in items
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == "cancelled"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": "cancelled", "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


@pytest.mark.timeout(3)
def test_repair_runner_legacy_before_ack_external_cancel_cleans_pending_and_marks_done():
    human_input = _BlockingHumanInput()
    session, runner = _make_runner(human_input=human_input)

    def _legacy_execute(before_ack):
        before_ack("UPDATE credit SET ok=1", 1)
        return {"written_uids": ["u1"]}

    async def run_and_cancel():
        handle = await runner.start(
            RepairRunSpec(
                trace_id="trace-1",
                input_payload={"bucket": "credit"},
                compat_mode="legacy_ack_inside_tool",
                legacy_execute_func=_legacy_execute,
            )
        )
        seen: list[object] = [handle.started_event]

        async def _consume():
            async for item in handle.stream():
                seen.append(item.event or item.result)

        task = asyncio.create_task(_consume())
        await human_input.wait_started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            seen.append("cancelled-error")
        return seen

    items = asyncio.run(run_and_cancel())
    assert "cancelled-error" not in items
    result = next(item for item in items if isinstance(item, RepairRunResult))
    assert result.status == "cancelled"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {"ack_status": "cancelled", "executed": False}
    run = session.turns[0].runs[0]
    assert run.pending_ack is None
    assert run.status == "running"


def test_repair_runner_module_does_not_import_agent_loop():
    path = Path("app/services/orchestrator_agent/execution/repair_runner.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.agent_loop":
            raise AssertionError("repair_runner.py imports agent_loop directly")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.orchestrator_agent.agent_loop":
                    raise AssertionError("repair_runner.py imports agent_loop directly")
