"""run_profile execution adapter with progress streaming."""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Literal

from app.services.orchestrator_agent.runtime.event_recorder import EventRecorder
from app.services.orchestrator_agent.runtime.session_lifecycle import SessionLifecycle
from app.services.orchestrator_agent.schemas import RunProfileInput, ToolCallRecord


LOGGER = logging.getLogger("app.services.orchestrator_agent.agent_loop")

ProfileStatus = Literal["completed", "failed"]
ProfileExecutor = Callable[[RunProfileInput, Callable[[dict[str, Any]], None] | None], Any]
ProgressLogger = Callable[[str, str, dict[str, Any]], None]


def call_tool_with_optional_progress(tool_fn, input_obj, progress_callback):
    """Call tools that may support a progress_callback without breaking old fakes."""
    try:
        params = inspect.signature(tool_fn).parameters.values()
        supports_progress = any(
            p.name == "progress_callback" or p.kind == inspect.Parameter.VAR_KEYWORD
            for p in params
        )
    except (TypeError, ValueError):
        supports_progress = False
    if supports_progress:
        return tool_fn(input_obj, progress_callback=progress_callback)
    return tool_fn(input_obj)


def log_run_profile_progress(session_id: str, tool_call_id: str, payload: dict[str, Any]) -> None:
    progress_type = payload.get("progress_type") or "profile_module_progress"
    event = {
        "profile_module_started": "run_profile_module_started",
        "profile_module_completed": "run_profile_module_completed",
        "profile_module_error": "run_profile_module_error",
    }.get(progress_type, "run_profile_module_progress")
    extra = {
        "event": event,
        "session_id": session_id,
        "tool_call_id": tool_call_id,
        "uid": payload.get("uid"),
        "profile_module": payload.get("module"),
        "completed": payload.get("completed"),
        "total": payload.get("total"),
        "status": payload.get("status"),
        "elapsed_ms": payload.get("elapsed_ms"),
    }
    LOGGER.info(
        "%s session_id=%s tool_call_id=%s uid=%s module=%s completed=%s total=%s status=%s elapsed_ms=%s",
        event,
        session_id,
        tool_call_id,
        payload.get("uid"),
        payload.get("module"),
        payload.get("completed"),
        payload.get("total"),
        payload.get("status"),
        payload.get("elapsed_ms"),
        extra=extra,
    )


def _serialize_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        dumped = output.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
        return {"result": dumped}
    if isinstance(output, dict):
        return output
    return {"result": output}


def merge_profile_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "results": [],
        "cache_hits": 0,
        "cache_misses": 0,
    }
    for chunk in outputs:
        merged["results"].extend(list(chunk.get("results") or []))
        merged["cache_hits"] += int(chunk.get("cache_hits") or 0)
        merged["cache_misses"] += int(chunk.get("cache_misses") or 0)
        for key, value in chunk.items():
            if key in {"results", "cache_hits", "cache_misses"}:
                continue
            merged.setdefault(key, value)
    return merged


@dataclass(slots=True, kw_only=True)
class ProfileRunSpec:
    trace_id: str | None
    input_payload: dict[str, Any]
    execution_groups: list[tuple[list[str], list[str]]]
    application_time_hint: str | None = None
    run_in_thread: bool = True
    tool_name: Literal["run_profile"] = "run_profile"
    should_cancel: Callable[[], bool] | None = None


@dataclass(slots=True)
class ProfileProgressEvent:
    payload: dict[str, Any]
    tool_progress_event: dict[str, Any] | None


@dataclass(slots=True)
class ProfileRunResult:
    tool_call_id: str
    status: ProfileStatus
    output: dict[str, Any] | None
    error: str | None
    completed_event: dict[str, Any] | None


@dataclass(slots=True)
class _ProgressSentinel:
    payload: dict[str, Any]


@dataclass(slots=True)
class _DoneSentinel:
    output: dict[str, Any]


@dataclass(slots=True)
class _ErrorSentinel:
    error: Exception


@dataclass(slots=True)
class _CancelledSentinel:
    pass


class ProfileRunHandle:
    def __init__(
        self,
        *,
        runner: "ProfileRunner",
        spec: ProfileRunSpec,
        record: ToolCallRecord,
        started_event: dict[str, Any] | None,
    ) -> None:
        self._runner = runner
        self._spec = spec
        self.record = record
        self.started_event = started_event
        self._stream_started = False

    async def stream(self) -> AsyncIterator[ProfileProgressEvent | ProfileRunResult]:
        if self._stream_started:
            raise RuntimeError("ProfileRunHandle.stream() can only be consumed once")
        self._stream_started = True
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[
            _ProgressSentinel | _DoneSentinel | _ErrorSentinel | _CancelledSentinel
        ] = asyncio.Queue()

        def _enqueue(
            item: _ProgressSentinel | _DoneSentinel | _ErrorSentinel | _CancelledSentinel,
        ) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, item)

        def _progress_callback(payload: dict[str, Any]) -> None:
            _enqueue(_ProgressSentinel(payload=dict(payload or {})))

        def _worker() -> None:
            try:
                outputs: list[dict[str, Any]] = []
                total = sum(len(modules) * len(uids) for modules, uids in self._spec.execution_groups)
                completed_offset = 0
                for modules, group_uids in self._spec.execution_groups:
                    group_input = RunProfileInput(
                        uids=group_uids,
                        app_time=self._spec.application_time_hint,
                        modules=modules,
                        strict_data_mode=True,
                    )

                    def _group_progress(progress_evt: dict[str, Any], *, offset: int = completed_offset) -> None:
                        payload = {
                            **(progress_evt or {}),
                            "completed": offset + int((progress_evt or {}).get("completed", 0)),
                            "total": total,
                        }
                        _progress_callback(payload)

                    result = self._runner._invoke_executor(
                        group_input,
                        _group_progress,
                        run_in_thread=self._spec.run_in_thread,
                    )
                    outputs.append(_serialize_output(result))
                    completed_offset += len(group_uids) * len(modules)
                _enqueue(_DoneSentinel(output=merge_profile_outputs(outputs)))
            except asyncio.CancelledError:
                _enqueue(_CancelledSentinel())
            except Exception as exc:  # noqa: BLE001
                _enqueue(_ErrorSentinel(error=exc))

        worker_task = asyncio.create_task(asyncio.to_thread(_worker))
        try:
            while True:
                if self._spec.should_cancel and self._spec.should_cancel():
                    raise asyncio.CancelledError()
                try:
                    item = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                if isinstance(item, _ProgressSentinel):
                    payload = item.payload
                    try:
                        self._runner.progress_logger(
                            self._runner.session.session_id,
                            self.record.tool_call_id,
                            payload,
                        )
                    except Exception:  # noqa: BLE001
                        LOGGER.warning("progress_logger failed for run_profile", exc_info=True)
                    tool_progress_event = None
                    if payload.get("progress_type") == "profile_module_completed":
                        tool_progress_event = self._runner.events.emit(
                            "tool_progress",
                            {
                                "trace_id": self.record.trace_id,
                                "tool_call_id": self.record.tool_call_id,
                                "tool_name": self.record.tool_name,
                                **payload,
                            },
                        )
                    yield ProfileProgressEvent(payload=payload, tool_progress_event=tool_progress_event)
                    continue

                if isinstance(item, _ErrorSentinel):
                    self._runner.lifecycle.mark_tool_call_error(self.record, error=str(item.error))
                    completed_event = self._runner.events.emit(
                        "tool_completed",
                        {
                            "trace_id": self.record.trace_id,
                            "tool_call_id": self.record.tool_call_id,
                            "tool_name": self.record.tool_name,
                            "output": {"error": str(item.error)},
                            "status": "error",
                        },
                    )
                    yield ProfileRunResult(
                        tool_call_id=self.record.tool_call_id,
                        status="failed",
                        output={"error": str(item.error)},
                        error=str(item.error),
                        completed_event=completed_event,
                    )
                    return

                if isinstance(item, _CancelledSentinel):
                    raise asyncio.CancelledError()

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
                yield ProfileRunResult(
                    tool_call_id=self.record.tool_call_id,
                    status="completed",
                    output=item.output,
                    error=None,
                    completed_event=completed_event,
                )
                return
        finally:
            if not worker_task.done():
                worker_task.cancel()


class ProfileRunner:
    def __init__(
        self,
        *,
        session: Any,
        lifecycle: SessionLifecycle,
        events: EventRecorder,
        progress_logger: ProgressLogger,
        profile_executor: ProfileExecutor,
    ) -> None:
        self.session = session
        self.lifecycle = lifecycle
        self.events = events
        self.progress_logger = progress_logger
        self.profile_executor = profile_executor

    async def start(self, spec: ProfileRunSpec) -> ProfileRunHandle:
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
        return ProfileRunHandle(
            runner=self,
            spec=spec,
            record=record,
            started_event=started_event,
        )

    def _invoke_executor(
        self,
        input_obj: RunProfileInput,
        progress_callback: Callable[[dict[str, Any]], None],
        *,
        run_in_thread: bool,
    ) -> Any:
        if run_in_thread and not inspect.iscoroutinefunction(self.profile_executor):
            return self.profile_executor(input_obj, progress_callback)
        result = self.profile_executor(input_obj, progress_callback)
        if inspect.isawaitable(result):
            raise TypeError("async profile_executor is not supported with worker-thread execution")
        return result
