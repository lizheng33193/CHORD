"""repair_profile_data HITL execution adapter."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

from app.services.orchestrator_agent.loop_context import HumanInputResult
from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder, log_internal_run_event
from app.services.orchestrator_agent.runtime.human_input import HumanInputController
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.schemas import ToolCallRecord


RunStatus = Literal["completed", "rejected", "expired", "cancelled", "failed"]
CompatMode = Literal["prepare_then_execute", "legacy_ack_inside_tool"]


def _serialize_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        dumped = output.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
        return {"result": dumped}
    if isinstance(output, dict):
        return output
    return {"result": output}


@dataclass(slots=True, kw_only=True)
class RepairPrepare:
    sql_text: str
    rows_estimated: int
    raw_prepared: Any | None = None
    ack_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class RepairRunSpec:
    trace_id: str | None
    input_payload: dict[str, Any]
    compat_mode: CompatMode
    prepare_func: Callable[[], Awaitable[RepairPrepare] | RepairPrepare] | None = None
    execute_func: Callable[[RepairPrepare | None], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None
    legacy_execute_func: Callable[[Callable[[str, int], None]], Awaitable[dict[str, Any]] | dict[str, Any]] | None = None
    tool_name: Literal["repair_profile_data"] = "repair_profile_data"
    should_cancel: Callable[[], bool] | None = None


@dataclass(slots=True)
class RepairRunResult:
    tool_call_id: str
    status: RunStatus
    output: dict[str, Any] | None
    error: str | None


@dataclass(slots=True)
class RepairRunnerEvent:
    event: dict[str, Any] | None
    result: RepairRunResult | None


@dataclass(slots=True)
class _BeforeAckRequest:
    sql_text: str
    rows_estimated: int
    decision: threading.Event
    result: HumanInputResult | None = None


@dataclass(slots=True)
class _WorkerDone:
    output: dict[str, Any]


@dataclass(slots=True)
class _WorkerFailed:
    error: Exception


@dataclass(slots=True)
class _WorkerAborted:
    status: Literal["rejected", "expired", "cancelled"]


class _RepairAckAborted(Exception):
    def __init__(self, status: Literal["rejected", "expired", "cancelled"]) -> None:
        super().__init__(status)
        self.status = status


class RepairRunHandle:
    def __init__(
        self,
        *,
        runner: "RepairRunner",
        spec: RepairRunSpec,
        record: ToolCallRecord,
        started_event: dict[str, Any] | None,
    ) -> None:
        self._runner = runner
        self._spec = spec
        self.record = record
        self.started_event = started_event
        self._stream_started = False

    async def stream(self) -> AsyncIterator[RepairRunnerEvent]:
        if self._stream_started:
            raise RuntimeError("RepairRunHandle.stream() can only be consumed once")
        self._stream_started = True
        if self._spec.compat_mode == "prepare_then_execute":
            async for item in self._stream_prepare_then_execute():
                yield item
            return
        async for item in self._stream_legacy_ack_inside_tool():
            yield item

    async def _stream_prepare_then_execute(self) -> AsyncIterator[RepairRunnerEvent]:
        pending_open = False
        awaiting_status = False
        try:
            if self._spec.prepare_func is None or self._spec.execute_func is None:
                raise ValueError("prepare_then_execute requires prepare_func and execute_func")
            prepared = await self._runner._invoke_prepare(self._spec.prepare_func)
            ack_payload = self._runner._build_ack_payload(
                tool_call_id=self.record.tool_call_id,
                sql_text=prepared.sql_text,
                rows_estimated=prepared.rows_estimated,
                extra=prepared.ack_payload,
            )
            await self._runner._open_ack(
                tool_call_id=self.record.tool_call_id,
                sql_text=prepared.sql_text,
                rows_estimated=prepared.rows_estimated,
            )
            pending_open = True
            awaiting_status = True
            yield RepairRunnerEvent(event=self._runner.events.emit("awaiting_user_ack", ack_payload), result=None)

            ack_result = await self._runner._wait_for_ack(self._spec.should_cancel)
            log_internal_run_event(
                self._runner.session,
                run_id=self._runner.events.run_id,
                event_type={
                    "approved": "ack_received",
                    "rejected": "ack_rejected",
                    "expired": "ack_expired",
                    "cancelled": "ack_cancelled",
                }[ack_result.status],
                payload={"ack_id": self.record.tool_call_id, "tool_call_id": self.record.tool_call_id},
            )
            self._runner._clear_ack_state()
            pending_open = False
            awaiting_status = False

            if ack_result.status != "approved":
                yield RepairRunnerEvent(event=None, result=self._runner._close_non_approved(self.record, ack_result.status))
                return

            output = _serialize_output(await self._runner._invoke_execute(self._spec.execute_func, prepared))
            self._runner.lifecycle.mark_tool_call_done(self.record, output=output)
            completed_event = self._runner.events.emit(
                "tool_completed",
                {
                    "trace_id": self.record.trace_id,
                    "tool_call_id": self.record.tool_call_id,
                    "tool_name": self.record.tool_name,
                    "output": output,
                    "status": "ok",
                },
            )
            yield RepairRunnerEvent(event=completed_event, result=None)
            yield RepairRunnerEvent(
                event=None,
                result=RepairRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="completed",
                    output=output,
                    error=None,
                ),
            )
        except asyncio.CancelledError:
            if pending_open:
                self._runner._clear_ack_state()
            elif awaiting_status:
                self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            self.record.output = {"ack_status": "cancelled", "executed": False}
            self.record.status = "done"
            self.record.finished_at = datetime.now(timezone.utc)
            self._runner.lifecycle.update_tool_call_record(self.record)
            yield RepairRunnerEvent(
                event=None,
                result=RepairRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="cancelled",
                    output=dict(self.record.output),
                    error=None,
                ),
            )
            return
        except Exception as exc:  # noqa: BLE001
            if pending_open:
                self._runner._clear_ack_state()
            elif awaiting_status:
                self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            self._runner.lifecycle.mark_tool_call_error(self.record, error=str(exc))
            completed_event = self._runner.events.emit(
                "tool_completed",
                {
                    "trace_id": self.record.trace_id,
                    "tool_call_id": self.record.tool_call_id,
                    "tool_name": self.record.tool_name,
                    "output": {"error": str(exc)},
                    "status": "error",
                },
            )
            yield RepairRunnerEvent(event=completed_event, result=None)
            yield RepairRunnerEvent(
                event=None,
                result=RepairRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="failed",
                    output={"error": str(exc)},
                    error=str(exc),
                ),
            )

    async def _stream_legacy_ack_inside_tool(self) -> AsyncIterator[RepairRunnerEvent]:
        if self._spec.legacy_execute_func is None:
            raise ValueError("legacy_ack_inside_tool requires legacy_execute_func")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[_BeforeAckRequest | _WorkerDone | _WorkerFailed | _WorkerAborted] = asyncio.Queue()
        pending_open = False
        awaiting_status = False
        pending_gate: _BeforeAckRequest | None = None

        def _enqueue(item: _BeforeAckRequest | _WorkerDone | _WorkerFailed | _WorkerAborted) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def _before_ack(sql_text: str, rows_estimated: int) -> None:
            request = _BeforeAckRequest(
                sql_text=sql_text,
                rows_estimated=rows_estimated,
                decision=threading.Event(),
            )
            _enqueue(request)
            request.decision.wait()
            if request.result is None or request.result.status != "approved":
                raise _RepairAckAborted((request.result.status if request.result is not None else "cancelled"))

        def _worker() -> None:
            try:
                output_obj = self._spec.legacy_execute_func(_before_ack)
                if inspect.isawaitable(output_obj):
                    output_obj = asyncio.run(output_obj)
                _enqueue(_WorkerDone(output=_serialize_output(output_obj)))
            except _RepairAckAborted as aborted:
                _enqueue(_WorkerAborted(status=aborted.status))
            except Exception as exc:  # noqa: BLE001
                _enqueue(_WorkerFailed(error=exc))

        worker_task = asyncio.create_task(asyncio.to_thread(_worker))
        try:
            while True:
                item = await queue.get()
                if isinstance(item, _BeforeAckRequest):
                    pending_gate = item
                    ack_payload = self._runner._build_ack_payload(
                        tool_call_id=self.record.tool_call_id,
                        sql_text=item.sql_text,
                        rows_estimated=item.rows_estimated,
                    )
                    await self._runner._open_ack(
                        tool_call_id=self.record.tool_call_id,
                        sql_text=item.sql_text,
                        rows_estimated=item.rows_estimated,
                    )
                    pending_open = True
                    awaiting_status = True
                    yield RepairRunnerEvent(event=self._runner.events.emit("awaiting_user_ack", ack_payload), result=None)

                    ack_result = await self._runner._wait_for_ack(self._spec.should_cancel)
                    log_internal_run_event(
                        self._runner.session,
                        run_id=self._runner.events.run_id,
                        event_type={
                            "approved": "ack_received",
                            "rejected": "ack_rejected",
                            "expired": "ack_expired",
                            "cancelled": "ack_cancelled",
                        }[ack_result.status],
                        payload={"ack_id": self.record.tool_call_id, "tool_call_id": self.record.tool_call_id},
                    )
                    self._runner._clear_ack_state()
                    pending_open = False
                    awaiting_status = False
                    item.result = ack_result
                    item.decision.set()
                    pending_gate = None

                    if ack_result.status != "approved":
                        yield RepairRunnerEvent(event=None, result=self._runner._close_non_approved(self.record, ack_result.status))
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(worker_task, timeout=0.5)
                        return
                    continue

                if isinstance(item, _WorkerAborted):
                    yield RepairRunnerEvent(event=None, result=self._runner._close_non_approved(self.record, item.status))
                    return

                if isinstance(item, _WorkerFailed):
                    raise item.error

                self._runner.lifecycle.mark_tool_call_done(self.record, output=item.output)
                completed_event = self._runner.events.emit(
                    "tool_completed",
                    {
                        "trace_id": self.record.trace_id,
                        "tool_call_id": self.record.tool_call_id,
                        "tool_name": self.record.tool_name,
                        "output": item.output,
                        "status": "ok",
                    },
                )
                yield RepairRunnerEvent(event=completed_event, result=None)
                yield RepairRunnerEvent(
                    event=None,
                    result=RepairRunResult(
                        tool_call_id=self.record.tool_call_id,
                        status="completed",
                        output=item.output,
                        error=None,
                    ),
                )
                return
        except asyncio.CancelledError:
            if pending_open:
                self._runner._clear_ack_state()
            elif awaiting_status:
                self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            self.record.output = {"ack_status": "cancelled", "executed": False}
            self.record.status = "done"
            self.record.finished_at = datetime.now(timezone.utc)
            self._runner.lifecycle.update_tool_call_record(self.record)
            yield RepairRunnerEvent(
                event=None,
                result=RepairRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="cancelled",
                    output=dict(self.record.output),
                    error=None,
                ),
            )
            return
        except Exception as exc:  # noqa: BLE001
            if pending_open:
                self._runner._clear_ack_state()
            elif awaiting_status:
                self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            self._runner.lifecycle.mark_tool_call_error(self.record, error=str(exc))
            completed_event = self._runner.events.emit(
                "tool_completed",
                {
                    "trace_id": self.record.trace_id,
                    "tool_call_id": self.record.tool_call_id,
                    "tool_name": self.record.tool_name,
                    "output": {"error": str(exc)},
                    "status": "error",
                },
            )
            yield RepairRunnerEvent(event=completed_event, result=None)
            yield RepairRunnerEvent(
                event=None,
                result=RepairRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="failed",
                    output={"error": str(exc)},
                    error=str(exc),
                ),
            )
        finally:
            if pending_gate is not None and not pending_gate.decision.is_set():
                pending_gate.result = HumanInputResult(status="cancelled")
                pending_gate.decision.set()
            if not worker_task.done():
                worker_task.cancel()


class RepairRunner:
    def __init__(
        self,
        *,
        session: Any,
        lifecycle: SessionLifecycle,
        events: EventRecorder,
        human_input: HumanInputController,
    ) -> None:
        self.session = session
        self.lifecycle = lifecycle
        self.events = events
        self.human_input = human_input

    async def start(self, spec: RepairRunSpec) -> RepairRunHandle:
        tool_call_id = uuid.uuid4().hex
        record = self.lifecycle.create_tool_call_record(
            turn_id=self.events.turn_id,
            run_id=self.events.run_id,
            trace_id=spec.trace_id,
            tool_name=spec.tool_name,
            tool_call_id=tool_call_id,
            input_payload=spec.input_payload,
        )
        started_event = self.events.emit(
            "tool_started",
            {
                "trace_id": spec.trace_id,
                "tool_call_id": tool_call_id,
                "tool_name": spec.tool_name,
                "input": dict(spec.input_payload),
            },
        )
        return RepairRunHandle(
            runner=self,
            spec=spec,
            record=record,
            started_event=started_event,
        )

    async def _invoke_prepare(
        self,
        func: Callable[[], Awaitable[RepairPrepare] | RepairPrepare],
    ) -> RepairPrepare:
        result = func()
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _invoke_execute(
        self,
        func: Callable[[RepairPrepare | None], Awaitable[dict[str, Any]] | dict[str, Any]],
        prepared: RepairPrepare | None,
    ) -> dict[str, Any]:
        result = func(prepared)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _build_ack_payload(
        self,
        *,
        tool_call_id: str,
        sql_text: str,
        rows_estimated: int,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(extra or {})
        payload.setdefault("ack_id", tool_call_id)
        payload.setdefault("tool_call_id", tool_call_id)
        payload.setdefault("sql_text", sql_text)
        payload.setdefault("rows_estimated", rows_estimated)
        return payload

    async def _open_ack(
        self,
        *,
        tool_call_id: str,
        sql_text: str,
        rows_estimated: int,
    ) -> None:
        await self.human_input.request_ack(
            session_id=self.session.session_id,
            ack_id=tool_call_id,
            run_id=self.events.run_id,
            trace_id=None,
            step_id=None,
            tool_call_id=tool_call_id,
            sql_text=sql_text,
            rows_estimated=rows_estimated,
        )
        self.lifecycle.set_pending_ack(
            run_id=self.events.run_id,
            ack_id=tool_call_id,
            tool_call_id=tool_call_id,
            sql_text=sql_text,
            rows_estimated=rows_estimated,
            step_id=None,
            tool_name="repair_profile_data",
        )
        self.lifecycle.set_run_status(run_id=self.events.run_id, status="awaiting_user_ack")
        log_internal_run_event(
            self.session,
            run_id=self.events.run_id,
            event_type="awaiting_user_ack",
            payload={
                "ack_id": tool_call_id,
                "tool_call_id": tool_call_id,
                "sql_text": sql_text,
                "rows_estimated": rows_estimated,
                "tool_name": "repair_profile_data",
            },
        )

    async def _wait_for_ack(self, should_cancel: Callable[[], bool] | None) -> HumanInputResult:
        return await self.human_input.wait_for_ack(
            session_id=self.session.session_id,
            timeout_seconds=600.0,
            poll_interval=0.25,
            should_cancel=should_cancel,
        )

    def _clear_ack_state(self) -> None:
        self.lifecycle.clear_pending_ack(run_id=self.events.run_id)
        self.lifecycle.set_run_status(run_id=self.events.run_id, status="running")

    def _close_non_approved(
        self,
        record: ToolCallRecord,
        status: Literal["rejected", "expired", "cancelled"],
    ) -> RepairRunResult:
        record.output = {"ack_status": status, "executed": False}
        record.status = "done"
        record.finished_at = datetime.now(timezone.utc)
        self.lifecycle.update_tool_call_record(record)
        return RepairRunResult(
            tool_call_id=record.tool_call_id,
            status=status,
            output=dict(record.output),
            error=None,
        )
