"""Cancellation helpers for orchestrator runs."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.orchestrator_agent.runtime.event_recorder import emit_run_status_event, log_internal_run_event
from app.services.orchestrator_agent.runtime.session_lifecycle import (
    clear_pending_ack,
    clear_pending_resolution,
    find_run,
    set_run_status,
)
from app.services.orchestrator_agent.runtime.trace_store import save_trace
from app.services.orchestrator_agent.schemas import ExecutionTraceRecord, OrchestratorSession
from app.services.orchestrator_agent.session import (
    clear_run_cancel,
    is_run_cancel_requested,
    mark_run_cancelling,
)


def maybe_cancel_run(
    session: OrchestratorSession,
    *,
    turn_id: str,
    run_id: str,
    trace: ExecutionTraceRecord | None = None,
) -> list[dict[str, object]] | None:
    if not is_run_cancel_requested(session.session_id, run_id):
        return None
    mark_run_cancelling(session.session_id, run_id)
    run = find_run(session, run_id)
    if run is not None and run.pending_ack is not None:
        log_internal_run_event(
            session,
            run_id=run_id,
            event_type="ack_cancelled",
            payload={"ack_id": run.pending_ack.ack_id, "tool_call_id": run.pending_ack.tool_call_id},
        )
    if run is not None and run.pending_resolution is not None:
        log_internal_run_event(
            session,
            run_id=run_id,
            event_type="resolution_cancelled",
            payload={"resolution_id": run.pending_resolution.resolution_id, "step_id": run.pending_resolution.step_id},
        )
    for record in session.tool_calls:
        if record.run_id == run_id and record.status in {"pending", "running"}:
            record.status = "cancelled"
            record.finished_at = datetime.now(timezone.utc)
    clear_pending_ack(session, run_id=run_id)
    clear_pending_resolution(session, run_id=run_id)
    set_run_status(session, run_id=run_id, status="cancelling")
    events = [
        emit_run_status_event(
            session,
            turn_id=turn_id,
            run_id=run_id,
            event_type="run_cancelling",
            trace_id=(trace.trace_id or trace.execution_id) if trace else None,
        ),
    ]
    if trace is not None:
        trace.final_status = "blocked"
        trace.final_message = "用户已停止当前执行，本轮结果不完整。"
        save_trace(session, trace)
    set_run_status(session, run_id=run_id, status="cancelled", completeness="partial")
    if run is not None:
        run.final_message = None
    clear_run_cancel(session.session_id, run_id)
    events.append(
        emit_run_status_event(
            session,
            turn_id=turn_id,
            run_id=run_id,
            event_type="run_cancelled",
            trace_id=(trace.trace_id or trace.execution_id) if trace else None,
            payload={"completeness": "partial", "workspace_committed": False},
        )
    )
    return events


def cancel_requested(
    session: OrchestratorSession,
    *,
    turn_id: str | None,
    run_id: str | None,
    trace: ExecutionTraceRecord | None = None,
) -> list[dict[str, object]] | None:
    if not turn_id or not run_id:
        return None
    return maybe_cancel_run(session, turn_id=turn_id, run_id=run_id, trace=trace)
