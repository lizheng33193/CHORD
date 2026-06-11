from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

from app.services.orchestrator_agent.execution.profile_runner import (
    ProfileProgressEvent,
    ProfileRunResult,
    ProfileRunSpec,
    ProfileRunner,
)
from app.services.orchestrator_agent.runtime import session_lifecycle
from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.session_store import create_session


def _make_runner(*, progress_logger, profile_executor):
    session = create_session(country="mx")
    lifecycle = SessionLifecycle(session)
    lifecycle.create_turn(turn_id="t1", client_turn_id=None, prompt="hello")
    lifecycle.create_turn_run(turn_id="t1", run_id="r1")
    events = EventRecorder(session, turn_id="t1", run_id="r1")
    runner = ProfileRunner(
        session=session,
        lifecycle=lifecycle,
        events=events,
        progress_logger=progress_logger,
        profile_executor=profile_executor,
    )
    return session, runner


@pytest.mark.timeout(3)
def test_profile_runner_start_and_success_persist(monkeypatch):
    saves: list[str] = []
    monkeypatch.setattr(session_lifecycle, "save_session", lambda sess: saves.append("saved"))

    def _executor(input_obj, progress_callback=None):
        if progress_callback:
            progress_callback(
                {
                    "progress_type": "profile_module_completed",
                    "uid": input_obj.uids[0],
                    "module": input_obj.modules[0],
                    "status": "ok",
                    "completed": 1,
                    "total": 1,
                }
            )
        return type(
            "X",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "results": [{"uid": input_obj.uids[0], "module": input_obj.modules[0]}],
                    "cache_hits": 0,
                    "cache_misses": 1,
                }
            },
        )()

    main_thread_id = threading.get_ident()
    logger_threads: list[int] = []

    def _logger(session_id, tool_call_id, payload):
        logger_threads.append(threading.get_ident())
        assert threading.get_ident() == main_thread_id

    session, runner = _make_runner(progress_logger=_logger, profile_executor=_executor)

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={
                    "uids": ["u1"],
                    "app_time": None,
                    "modules": ["app"],
                    "strict_data_mode": True,
                },
                execution_groups=[(["app"], ["u1"])],
                should_cancel=lambda: False,
            )
        )
        items = []
        async for item in handle.stream():
            items.append(item)
        return handle, items

    handle, items = asyncio.run(run())
    assert handle.started_event is not None
    assert handle.started_event["type"] == "tool_started"
    assert items
    assert isinstance(items[0], ProfileProgressEvent)
    assert items[0].tool_progress_event is not None
    assert items[0].tool_progress_event["type"] == "tool_progress"
    result = items[-1]
    assert isinstance(result, ProfileRunResult)
    assert result.status == "completed"
    assert result.completed_event is not None
    assert result.completed_event["status"] == "ok"
    assert session.tool_calls[0].status == "done"
    assert session.tool_calls[0].output == {
        "results": [{"uid": "u1", "module": "app"}],
        "cache_hits": 0,
        "cache_misses": 1,
    }
    assert logger_threads
    assert saves


@pytest.mark.timeout(3)
def test_profile_runner_merges_multiple_groups_and_preserves_extra_fields():
    def _executor(input_obj, progress_callback=None):
        if progress_callback:
            progress_callback(
                {
                    "progress_type": "profile_module_completed",
                    "uid": input_obj.uids[0],
                    "module": input_obj.modules[0],
                    "status": "ok",
                    "completed": 1,
                    "total": 1,
                }
            )
        return type(
            "X",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "results": [{"uid": input_obj.uids[0], "module": input_obj.modules[0]}],
                    "cache_hits": 1,
                    "cache_misses": 2,
                    "meta": {"country": "mx"},
                }
            },
        )()

    session, runner = _make_runner(progress_logger=lambda *args: None, profile_executor=_executor)

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={
                    "uids": ["u1", "u2"],
                    "app_time": None,
                    "modules": ["app", "behavior"],
                    "strict_data_mode": True,
                },
                execution_groups=[(["app"], ["u1"]), (["behavior"], ["u2"])],
            )
        )
        final = None
        async for item in handle.stream():
            if isinstance(item, ProfileRunResult):
                final = item
        return final

    result = asyncio.run(run())
    assert result is not None
    assert result.output == {
        "results": [{"uid": "u1", "module": "app"}, {"uid": "u2", "module": "behavior"}],
        "cache_hits": 2,
        "cache_misses": 4,
        "meta": {"country": "mx"},
    }


@pytest.mark.timeout(3)
def test_profile_runner_non_completed_progress_does_not_emit_tool_progress():
    def _executor(input_obj, progress_callback=None):
        if progress_callback:
            progress_callback({"progress_type": "profile_module_started", "uid": "u1", "module": "app"})
        return type(
            "X",
            (),
            {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 0}},
        )()

    session, runner = _make_runner(progress_logger=lambda *args: None, profile_executor=_executor)

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={"uids": ["u1"], "app_time": None, "modules": ["app"], "strict_data_mode": True},
                execution_groups=[(["app"], ["u1"])],
            )
        )
        items = []
        async for item in handle.stream():
            items.append(item)
        return items

    items = asyncio.run(run())
    progress = [item for item in items if isinstance(item, ProfileProgressEvent)]
    assert len(progress) == 1
    assert progress[0].tool_progress_event is None


@pytest.mark.timeout(3)
def test_profile_runner_error_path_marks_record_error():
    def _executor(input_obj, progress_callback=None):
        raise RuntimeError("boom")

    session, runner = _make_runner(progress_logger=lambda *args: None, profile_executor=_executor)

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={"uids": ["u1"], "app_time": None, "modules": ["app"], "strict_data_mode": True},
                execution_groups=[(["app"], ["u1"])],
            )
        )
        async for item in handle.stream():
            if isinstance(item, ProfileRunResult):
                return item
        raise AssertionError("expected ProfileRunResult")

    result = asyncio.run(run())
    assert result.status == "failed"
    assert result.completed_event is not None
    assert result.completed_event["status"] == "error"
    assert session.tool_calls[0].status == "error"
    assert session.tool_calls[0].output == {"error": "boom"}


@pytest.mark.timeout(3)
def test_profile_runner_cancelled_error_propagates():
    def _executor(input_obj, progress_callback=None):
        raise asyncio.CancelledError()

    _, runner = _make_runner(progress_logger=lambda *args: None, profile_executor=_executor)

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={"uids": ["u1"], "app_time": None, "modules": ["app"], "strict_data_mode": True},
                execution_groups=[(["app"], ["u1"])],
            )
        )
        async for _item in handle.stream():
            pass

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


@pytest.mark.timeout(3)
def test_profile_runner_stream_cancels_via_should_cancel():
    def _executor(input_obj, progress_callback=None):
        if progress_callback:
            progress_callback({"progress_type": "profile_module_started", "uid": "u1", "module": "app"})
        import time
        time.sleep(0.3)
        return type(
            "X",
            (),
            {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 0}},
        )()

    _, runner = _make_runner(progress_logger=lambda *args: None, profile_executor=_executor)
    checks = {"count": 0}

    def _should_cancel():
        checks["count"] += 1
        return checks["count"] >= 2

    async def run():
        handle = await runner.start(
            ProfileRunSpec(
                trace_id="trace-1",
                input_payload={"uids": ["u1"], "app_time": None, "modules": ["app"], "strict_data_mode": True},
                execution_groups=[(["app"], ["u1"])],
                should_cancel=_should_cancel,
            )
        )
        async for _item in handle.stream():
            pass

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())


def test_profile_runner_module_does_not_import_agent_loop():
    path = Path("app/services/orchestrator_agent/execution/profile_runner.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.orchestrator_agent.agent_loop":
            raise AssertionError("profile_runner.py imports agent_loop directly")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "app.services.orchestrator_agent.agent_loop":
                    raise AssertionError("profile_runner.py imports agent_loop directly")
