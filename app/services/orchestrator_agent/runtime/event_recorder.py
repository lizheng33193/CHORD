"""Run-event recording and decorated SSE event helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.orchestrator_agent.runtime.session_lifecycle import (
    find_turn_id_for_run,
    next_event_seq,
)
from app.services.orchestrator_agent.schemas import OrchestratorSession, RunEvent
from app.services.orchestrator_agent.session_store import save_session


def log_internal_run_event(
    session: OrchestratorSession,
    *,
    run_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    turn_id = find_turn_id_for_run(session, run_id)
    if not turn_id or not run_id:
        return
    session.run_events.append(
        RunEvent(
            event_id=uuid.uuid4().hex,
            event_seq=next_event_seq(session, run_id),
            session_id=session.session_id,
            turn_id=turn_id,
            run_id=run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=dict(payload or {}),
        )
    )
    save_session(session)


def record_run_event(
    session: OrchestratorSession,
    *,
    turn_id: str,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> RunEvent:
    event = RunEvent(
        event_id=uuid.uuid4().hex,
        event_seq=next_event_seq(session, run_id),
        session_id=session.session_id,
        turn_id=turn_id,
        run_id=run_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        payload=payload,
    )
    session.run_events.append(event)
    save_session(session)
    return event


def decorate_event(
    session: OrchestratorSession,
    evt: dict[str, Any],
    *,
    turn_id: str,
    run_id: str,
) -> dict[str, Any]:
    event_type = str(evt.get("type") or evt.get("event_type") or "unknown")
    payload = dict(evt)
    payload.setdefault("trace_id", payload.get("execution_id"))
    event = record_run_event(
        session,
        turn_id=turn_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
    )
    enriched = dict(evt)
    enriched["event_id"] = event.event_id
    enriched["event_seq"] = event.event_seq
    enriched["session_id"] = session.session_id
    enriched["turn_id"] = turn_id
    enriched["run_id"] = run_id
    enriched["event_type"] = event_type
    enriched["timestamp"] = event.timestamp.isoformat()
    if "trace_id" not in enriched and evt.get("execution_id"):
        enriched["trace_id"] = evt["execution_id"]
    return enriched


def emit_run_status_event(
    session: OrchestratorSession,
    *,
    turn_id: str,
    run_id: str,
    event_type: str,
    trace_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = dict(payload or {})
    if trace_id:
        body["trace_id"] = trace_id
    return decorate_event(session, {"type": event_type, **body}, turn_id=turn_id, run_id=run_id)


class EventRecorder:
    """Thin recorder facade used by FlowContext and future flows."""

    def __init__(self, session: OrchestratorSession, *, turn_id: str, run_id: str):
        self.session = session
        self.turn_id = turn_id
        self.run_id = run_id

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return decorate_event(
            self.session,
            {"type": event_type, **dict(payload or {})},
            turn_id=self.turn_id,
            run_id=self.run_id,
        )
