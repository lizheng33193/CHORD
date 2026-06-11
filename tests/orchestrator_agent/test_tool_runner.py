from __future__ import annotations

import ast
import asyncio
from pathlib import Path

from app.services.orchestrator_agent.execution.tool_runner import ToolRunSpec, ToolRunner
from app.services.orchestrator_agent.runtime import session_lifecycle
from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.session_store import create_session


def test_tool_runner_sync_callable_success_persists_output(monkeypatch):
    session = create_session(country="mx")
    saves: list[str] = []
    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = ToolRunner(session=session, lifecycle=lifecycle, events=events)

    def _tool(arg):
        return {"value": arg}

    async def run():
        handle = await runner.start(
            ToolRunSpec(
                name="demo_tool",
                func=_tool,
                input_payload={"arg": 7},
                call_args=(7,),
            )
        )
        result = await handle.execute()
        return handle, result

    handle, result = asyncio.run(run())

    assert handle.started_event is not None
    assert handle.started_event["type"] == "tool_started"
    assert result.completed_event is not None
    assert result.completed_event["type"] == "tool_completed"
    assert result.completed_event["status"] == "ok"
    assert result.output == {"value": 7}
    tool_call = session.tool_calls[0]
    assert tool_call.tool_name == "demo_tool"
    assert tool_call.status == "done"
    assert tool_call.output == {"value": 7}
    assert tool_call.finished_at is not None
    assert saves


def test_tool_runner_async_callable_success():
    session = create_session(country="mx")
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = ToolRunner(session=session, lifecycle=lifecycle, events=events)

    async def _tool(arg):
        return {"value": arg * 2}

    async def run():
        handle = await runner.start(
            ToolRunSpec(
                name="async_tool",
                func=_tool,
                input_payload={"arg": 4},
                call_args=(4,),
            )
        )
        return await handle.execute()

    result = asyncio.run(run())

    assert result.status == "completed"
    assert result.output == {"value": 8}
    assert result.completed_event is not None
    assert result.completed_event["status"] == "ok"


def test_tool_runner_callable_error_persists_failure(monkeypatch):
    session = create_session(country="mx")
    saves: list[str] = []
    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = ToolRunner(session=session, lifecycle=lifecycle, events=events)

    def _tool(arg):
        raise RuntimeError(f"boom:{arg}")

    async def run():
        handle = await runner.start(
            ToolRunSpec(
                name="broken_tool",
                func=_tool,
                input_payload={"arg": 3},
                call_args=(3,),
            )
        )
        return await handle.execute()

    result = asyncio.run(run())

    assert result.status == "failed"
    assert result.error == "boom:3"
    assert result.completed_event is not None
    assert result.completed_event["status"] == "error"
    tool_call = session.tool_calls[0]
    assert tool_call.status == "error"
    assert tool_call.output == {"error": "boom:3"}
    assert tool_call.finished_at is not None
    assert saves


def test_tool_runner_start_emits_before_execute():
    session = create_session(country="mx")
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = ToolRunner(session=session, lifecycle=lifecycle, events=events)

    async def _tool():
        return {"ok": True}

    async def run():
        handle = await runner.start(
            ToolRunSpec(
                name="ordering_tool",
                func=_tool,
                input_payload={},
            )
        )
        started_seq = handle.started_event["event_seq"]
        completed = await handle.execute()
        return started_seq, completed.completed_event["event_seq"]

    started_seq, completed_seq = asyncio.run(run())
    assert started_seq < completed_seq


def test_tool_runner_module_does_not_import_agent_loop():
    path = Path("app/services/orchestrator_agent/execution/tool_runner.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.agent_loop":
            raise AssertionError("tool_runner.py imports agent_loop directly")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.orchestrator_agent.agent_loop":
                    raise AssertionError("tool_runner.py imports agent_loop directly")
