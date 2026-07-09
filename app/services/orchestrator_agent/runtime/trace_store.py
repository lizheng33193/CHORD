"""Execution trace mutations and plan/trace event builders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.memory.observability import (
    EXECUTION_TRACE_SEMANTIC_MEMORY_KEY,
    SEMANTIC_MEMORY_TRACE_HANDOFF_KEY,
)
from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata
from app.services.orchestrator_agent.schemas import (
    DataAvailability,
    ExecutionPlan,
    ExecutionTraceRecord,
    NormalizedRequest,
    OrchestratorSession,
    PlanStep,
    ReviewResult,
)
from app.services.orchestrator_agent.session_store import save_session
from app.services.orchestrator_agent.runtime.session_lifecycle import find_run


def create_execution_trace(
    session: OrchestratorSession,
    *,
    execution_id: str,
    turn_id: str | None = None,
    run_id: str | None = None,
    prompt: str,
    normalized_request: NormalizedRequest,
    availability: DataAvailability | None,
    steps: list[PlanStep],
) -> ExecutionTraceRecord:
    turn_id = turn_id or session.active_turn_id
    run_id = run_id or session.active_run_id
    now = datetime.now(timezone.utc)
    request_context = session.active_entities.get("request_context")
    user_snapshot = session.active_entities.get("user_context_snapshot")
    trace = ExecutionTraceRecord(
        turn_id=turn_id,
        run_id=run_id,
        execution_id=execution_id,
        trace_id=execution_id,
        request_id=(request_context or {}).get("request_id") if isinstance(request_context, dict) else None,
        prompt=prompt,
        request_summary=normalized_request.request_summary,
        intent=normalized_request.intent,
        request_understanding=normalized_request.request_understanding,
        availability=availability,
        steps=steps,
        created_at=now,
        updated_at=now,
    )
    update_internal_trace_metadata(
        trace,
        {
            "request_id": trace.request_id,
            "session_id": session.session_id,
            "actor": user_snapshot if isinstance(user_snapshot, dict) else None,
        },
    )
    semantic_summary = None
    active_entities = getattr(session, "active_entities", None)
    if isinstance(active_entities, dict):
        handoff = active_entities.pop(SEMANTIC_MEMORY_TRACE_HANDOFF_KEY, None)
        if isinstance(handoff, dict):
            semantic_summary = dict(handoff)
    if semantic_summary is not None:
        update_internal_trace_metadata(
            trace,
            {
                EXECUTION_TRACE_SEMANTIC_MEMORY_KEY: semantic_summary,
            },
        )
    session.execution_traces.append(trace)
    run = find_run(session, run_id)
    if run is not None:
        run.trace_id = execution_id
        run.summary = normalized_request.request_summary
    save_session(session)
    return trace


def save_trace(session: OrchestratorSession, trace: ExecutionTraceRecord) -> None:
    trace.updated_at = datetime.now(timezone.utc)
    save_session(session)


def set_trace_availability(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    availability: DataAvailability,
) -> None:
    trace.availability = availability
    save_trace(session, trace)


def append_trace_steps(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    steps: list[PlanStep],
) -> None:
    trace.steps.extend(steps)
    save_trace(session, trace)


def replace_trace_steps(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    steps: list[PlanStep],
) -> None:
    trace.steps = list(steps)
    save_trace(session, trace)


def update_trace_step(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    *,
    step_id: str,
    status: str,
    result_summary: str | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    for step in trace.steps:
        if step.step_id != step_id:
            continue
        step.status = status
        if result_summary is not None:
            step.result_summary = result_summary
        if tool_call_id is not None:
            step.tool_call_id = tool_call_id
        save_trace(session, trace)
        return {
            "type": "plan_step_status",
            "execution_id": trace.execution_id,
            "trace_id": trace.trace_id or trace.execution_id,
            "step_id": step_id,
            "status": status,
            "result_summary": step.result_summary,
            "tool_call_id": step.tool_call_id,
        }
    return {
        "type": "plan_step_status",
        "execution_id": trace.execution_id,
        "trace_id": trace.trace_id or trace.execution_id,
        "step_id": step_id,
        "status": status,
        "result_summary": result_summary,
        "tool_call_id": tool_call_id,
    }


def set_trace_review(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    review: ReviewResult,
) -> dict[str, Any]:
    trace.review = review
    save_trace(session, trace)
    return {
        "type": "review_result",
        "execution_id": trace.execution_id,
        "trace_id": trace.trace_id or trace.execution_id,
        "status": review.status,
        "issues": review.issues,
        "confidence_impact": review.confidence_impact,
        "can_answer": review.can_answer,
    }


def finalize_trace(
    session: OrchestratorSession,
    trace: ExecutionTraceRecord,
    *,
    final_status: str,
    final_message: str,
) -> None:
    trace.final_status = final_status
    trace.final_message = final_message
    run = find_run(session, trace.run_id)
    if run is not None:
        run.final_message = final_message
        run.review_status = trace.review.status if trace.review else None
    save_trace(session, trace)


def build_execution_plan_event(trace: ExecutionTraceRecord) -> dict[str, Any]:
    plan = ExecutionPlan(
        execution_id=trace.execution_id,
        request_summary=trace.request_summary,
        intent=trace.intent,
        request_understanding=trace.request_understanding,
        availability=trace.availability,
        steps=trace.steps,
    )
    return {
        "type": "execution_plan",
        "trace_id": trace.trace_id or trace.execution_id,
        **plan.model_dump(mode="json"),
    }


def build_awaiting_resolution_event(
    trace: ExecutionTraceRecord,
    *,
    step_id: str,
    resolution_id: str | None = None,
    resolution_type: str,
    prompt: str,
    required_slots: list[str] | None = None,
    candidate_defaults: dict[str, Any] | None = None,
    options: list[str] | None = None,
    missing_bucket_counts: dict[str, int] | None = None,
    cohort_size: int | None = None,
) -> dict[str, Any]:
    return {
        "type": "awaiting_resolution",
        "execution_id": trace.execution_id,
        "trace_id": trace.trace_id or trace.execution_id,
        "step_id": step_id,
        "resolution_id": resolution_id,
        "resolution_type": resolution_type,
        "prompt": prompt,
        "required_slots": list(required_slots or []),
        "candidate_defaults": dict(candidate_defaults or {}),
        "options": list(options or []),
        "missing_bucket_counts": dict(missing_bucket_counts or {}),
        "cohort_size": cohort_size,
        "selected_option": None,
    }


class TraceStore:
    """Thin trace facade used by FlowContext and future flows."""

    def __init__(self, session: OrchestratorSession):
        self.session = session

    def create_execution_trace(self, **kwargs):
        return create_execution_trace(self.session, **kwargs)

    def update_step(self, trace: ExecutionTraceRecord, **kwargs):
        return update_trace_step(self.session, trace, **kwargs)

    def finalize(self, trace: ExecutionTraceRecord, **kwargs):
        return finalize_trace(self.session, trace, **kwargs)
