"""query_data HITL execution adapter."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder, log_internal_run_event
from app.services.orchestrator_agent.runtime.human_input import HumanInputController
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.schemas import ToolCallRecord


PreviewStatus = Literal["completed", "awaiting_ack"]
RunStatus = Literal["completed", "rejected", "expired", "cancelled", "failed"]


def _serialize_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        dumped = output.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
        return {"result": dumped}
    if isinstance(output, dict):
        return output
    return {"result": output}


@dataclass(slots=True)
class DataQueryPreview:
    status: PreviewStatus
    output: dict[str, Any] | None = None
    ack_payload: dict[str, Any] | None = None
    raw_preview: dict[str, Any] | None = None


@dataclass(slots=True, kw_only=True)
class DataQueryRunSpec:
    trace_id: str | None
    input_payload: dict[str, Any]
    preview_func: Callable[[], Awaitable[DataQueryPreview] | DataQueryPreview]
    complete_func: Callable[[DataQueryPreview], Awaitable[dict[str, Any]] | dict[str, Any]]
    step_id: str = "query_data"
    tool_name: Literal["query_data"] = "query_data"
    should_cancel: Callable[[], bool] | None = None


@dataclass(slots=True)
class DataQueryRunResult:
    tool_call_id: str
    status: RunStatus
    output: dict[str, Any] | None
    error: str | None


@dataclass(slots=True)
class DataQueryRunnerEvent:
    event: dict[str, Any] | None
    result: DataQueryRunResult | None


class DataQueryRunHandle:
    def __init__(
        self,
        *,
        runner: "DataQueryRunner",
        spec: DataQueryRunSpec,
        record: ToolCallRecord,
        started_event: dict[str, Any] | None,
    ) -> None:
        self._runner = runner
        self._spec = spec
        self.record = record
        self.started_event = started_event
        self._stream_started = False

    async def stream(self) -> AsyncIterator[DataQueryRunnerEvent]:
        if self._stream_started:
            raise RuntimeError("DataQueryRunHandle.stream() can only be consumed once")
        self._stream_started = True
        pending_open = False
        awaiting_status = False
        try:
            preview = await self._runner._invoke_preview(self._spec.preview_func)
            if preview.status == "completed":
                output = _serialize_output(preview.output or {})
                if self._spec.should_cancel and self._spec.should_cancel():
                    yield DataQueryRunnerEvent(
                        event=None,
                        result=DataQueryRunResult(
                            tool_call_id=self.record.tool_call_id,
                            status="cancelled",
                            output=None,
                            error=None,
                        ),
                    )
                    return
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
                yield DataQueryRunnerEvent(event=completed_event, result=None)
                yield DataQueryRunnerEvent(
                    event=None,
                    result=DataQueryRunResult(
                        tool_call_id=self.record.tool_call_id,
                        status="completed",
                        output=output,
                        error=None,
                    ),
                )
                return

            ack_payload = {
                **dict(preview.ack_payload or {}),
                "ack_id": self.record.tool_call_id,
                "tool_call_id": self.record.tool_call_id,
            }
            if not ack_payload:
                raise ValueError("query_data preview awaiting ACK requires ack_payload")

            await self._runner.human_input.request_ack(
                session_id=self._runner.session.session_id,
                ack_id=self.record.tool_call_id,
                run_id=self._runner.events.run_id,
                trace_id=self.record.trace_id,
                step_id=self._spec.step_id,
                tool_call_id=self.record.tool_call_id,
                sql_text=ack_payload.get("sql_text"),
                rows_estimated=ack_payload.get("rows_estimated"),
            )
            self._runner.lifecycle.set_pending_ack(
                run_id=self._runner.events.run_id,
                ack_id=self.record.tool_call_id,
                tool_call_id=self.record.tool_call_id,
                sql_text=ack_payload.get("sql_text") or "",
                rows_estimated=ack_payload.get("rows_estimated"),
                step_id=self._spec.step_id,
                tool_name=self._spec.tool_name,
            )
            pending_open = True
            self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="awaiting_user_ack")
            awaiting_status = True
            log_internal_run_event(
                self._runner.session,
                run_id=self._runner.events.run_id,
                event_type="awaiting_user_ack",
                payload={
                    "ack_id": self.record.tool_call_id,
                    "tool_call_id": self.record.tool_call_id,
                    "sql_text": ack_payload.get("sql_text") or "",
                    "rows_estimated": ack_payload.get("rows_estimated"),
                    "step_id": self._spec.step_id,
                    "tool_name": self._spec.tool_name,
                },
            )
            awaiting_event = self._runner.events.emit(
                "awaiting_user_ack",
                ack_payload,
            )
            yield DataQueryRunnerEvent(event=awaiting_event, result=None)

            ack_result = await self._runner.human_input.wait_for_ack(
                session_id=self._runner.session.session_id,
                timeout_seconds=600.0,
                poll_interval=0.25,
                should_cancel=self._spec.should_cancel,
            )
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
            self._runner.lifecycle.clear_pending_ack(run_id=self._runner.events.run_id)
            pending_open = False
            self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            awaiting_status = False

            if ack_result.status != "approved":
                self.record.output = {"ack_status": ack_result.status, "executed": False}
                self.record.status = "done"
                self.record.finished_at = datetime.now(timezone.utc)
                self._runner.lifecycle.update_tool_call_record(self.record)
                yield DataQueryRunnerEvent(
                    event=None,
                    result=DataQueryRunResult(
                        tool_call_id=self.record.tool_call_id,
                        status=ack_result.status,
                        output=dict(self.record.output),
                        error=None,
                    ),
                )
                return

            completed = await self._runner._invoke_complete(self._spec.complete_func, preview)
            output = _serialize_output(completed)
            if self._spec.should_cancel and self._spec.should_cancel():
                yield DataQueryRunnerEvent(
                    event=None,
                    result=DataQueryRunResult(
                        tool_call_id=self.record.tool_call_id,
                        status="cancelled",
                        output=None,
                        error=None,
                    ),
                )
                return
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
            yield DataQueryRunnerEvent(event=completed_event, result=None)
            yield DataQueryRunnerEvent(
                event=None,
                result=DataQueryRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="completed",
                    output=output,
                    error=None,
                ),
            )
        except asyncio.CancelledError:
            if pending_open:
                self._runner.lifecycle.clear_pending_ack(run_id=self._runner.events.run_id)
            if awaiting_status:
                self._runner.lifecycle.set_run_status(run_id=self._runner.events.run_id, status="running")
            self.record.output = {"ack_status": "cancelled", "executed": False}
            self.record.status = "done"
            self.record.finished_at = datetime.now(timezone.utc)
            self._runner.lifecycle.update_tool_call_record(self.record)
            yield DataQueryRunnerEvent(
                event=None,
                result=DataQueryRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="cancelled",
                    output=dict(self.record.output),
                    error=None,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            if pending_open:
                self._runner.lifecycle.clear_pending_ack(run_id=self._runner.events.run_id)
            if awaiting_status:
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
            yield DataQueryRunnerEvent(event=completed_event, result=None)
            yield DataQueryRunnerEvent(
                event=None,
                result=DataQueryRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="failed",
                    output={"error": str(exc)},
                    error=str(exc),
                ),
            )


class DataQueryRunner:
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

    async def start(self, spec: DataQueryRunSpec) -> DataQueryRunHandle:
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
                "input": spec.input_payload,
            },
        )
        return DataQueryRunHandle(
            runner=self,
            spec=spec,
            record=record,
            started_event=started_event,
        )

    async def _invoke_preview(self, func: Callable[[], Awaitable[DataQueryPreview] | DataQueryPreview]) -> DataQueryPreview:
        result = func()
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _invoke_complete(
        self,
        func: Callable[[DataQueryPreview], Awaitable[dict[str, Any]] | dict[str, Any]],
        preview: DataQueryPreview,
    ) -> dict[str, Any]:
        result = func(preview)
        if inspect.isawaitable(result):
            result = await result
        return result
