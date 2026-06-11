"""Shared tool-call lifecycle runner for non-HITL orchestrator paths."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.schemas import OrchestratorSession, ToolCallRecord


ToolStatus = Literal["completed", "failed", "cancelled"]


def _serialize_tool_output(output: Any) -> Any:
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    return output


@dataclass(slots=True)
class ToolRunSpec:
    name: str
    func: Callable[..., Any]
    input_payload: dict[str, Any]
    call_args: tuple[Any, ...] = ()
    call_kwargs: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    emit_started: bool = True
    emit_completed: bool = True
    run_in_thread: bool = True


@dataclass(slots=True)
class ToolRunResult:
    name: str
    tool_call_id: str
    status: ToolStatus
    output: Any = None
    error: str | None = None
    completed_event: dict[str, Any] | None = None


class ToolRunHandle:
    def __init__(
        self,
        *,
        runner: "ToolRunner",
        spec: ToolRunSpec,
        record: ToolCallRecord,
        started_event: dict[str, Any] | None,
    ) -> None:
        self._runner = runner
        self._spec = spec
        self.record = record
        self.started_event = started_event

    async def execute(self) -> ToolRunResult:
        try:
            raw_output = await self._runner._invoke(self._spec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._runner.lifecycle.mark_tool_call_error(self.record, error=str(exc))
            completed_event = None
            if self._spec.emit_completed:
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
            return ToolRunResult(
                name=self._spec.name,
                tool_call_id=self.record.tool_call_id,
                status="failed",
                output={"error": str(exc)},
                error=str(exc),
                completed_event=completed_event,
            )

        output = _serialize_tool_output(raw_output)
        self._runner.lifecycle.mark_tool_call_done(self.record, output=output)
        completed_event = None
        if self._spec.emit_completed:
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
        return ToolRunResult(
            name=self._spec.name,
            tool_call_id=self.record.tool_call_id,
            status="completed",
            output=output,
            completed_event=completed_event,
        )


class ToolRunner:
    def __init__(
        self,
        *,
        session: OrchestratorSession,
        lifecycle: SessionLifecycle,
        events: EventRecorder,
    ) -> None:
        self.session = session
        self.lifecycle = lifecycle
        self.events = events

    async def start(self, spec: ToolRunSpec) -> ToolRunHandle:
        tool_call_id = uuid.uuid4().hex
        record = self.lifecycle.create_tool_call_record(
            turn_id=self.events.turn_id,
            run_id=self.events.run_id,
            trace_id=spec.trace_id,
            tool_name=spec.name,
            tool_call_id=tool_call_id,
            input_payload=spec.input_payload,
        )
        started_event = None
        if spec.emit_started:
            started_event = self.events.emit(
                "tool_started",
                {
                    "trace_id": spec.trace_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": spec.name,
                    "input": spec.input_payload,
                },
            )
        return ToolRunHandle(
            runner=self,
            spec=spec,
            record=record,
            started_event=started_event,
        )

    async def _invoke(self, spec: ToolRunSpec) -> Any:
        if spec.run_in_thread and not inspect.iscoroutinefunction(spec.func):
            result = await asyncio.to_thread(
                spec.func,
                *spec.call_args,
                **spec.call_kwargs,
            )
            if inspect.isawaitable(result):
                return await result
            return result

        result = spec.func(*spec.call_args, **spec.call_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
