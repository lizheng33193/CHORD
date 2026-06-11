"""Session lifecycle mutations and persistence ownership."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.orchestrator_agent.schemas import (
    ConversationTurn,
    OrchestratorMessage,
    OrchestratorSession,
    PendingAckState,
    PendingResolutionState,
    RunEvent,
    ToolCallRecord,
    TurnRunRecord,
)
from app.services.orchestrator_agent.session_store import save_session


def find_turn(session: OrchestratorSession, turn_id: str | None) -> ConversationTurn | None:
    if not turn_id:
        return None
    for turn in session.turns:
        if turn.turn_id == turn_id:
            return turn
    return None


def find_run(session: OrchestratorSession, run_id: str | None) -> TurnRunRecord | None:
    if not run_id:
        return None
    for turn in session.turns:
        for run in turn.runs:
            if run.run_id == run_id:
                return run
    return None


def find_turn_id_for_run(session: OrchestratorSession, run_id: str | None) -> str | None:
    if not run_id:
        return None
    for turn in session.turns:
        for run in turn.runs:
            if run.run_id == run_id:
                return turn.turn_id
    return None


def next_event_seq(session: OrchestratorSession, run_id: str | None) -> int:
    run = find_run(session, run_id)
    if run is None:
        return 1
    run.last_event_seq += 1
    return run.last_event_seq


def create_turn(
    session: OrchestratorSession,
    *,
    turn_id: str,
    client_turn_id: str | None,
    prompt: str,
) -> ConversationTurn:
    now = datetime.now(timezone.utc)
    user_message = OrchestratorMessage(
        role="user",
        content=prompt,
        turn_id=turn_id,
        timestamp=now,
    )
    turn = ConversationTurn(
        turn_id=turn_id,
        client_turn_id=client_turn_id,
        session_id=session.session_id,
        user_message=user_message,
        created_at=now,
        updated_at=now,
    )
    session.turns.append(turn)
    session.messages.append(user_message)
    session.active_turn_id = turn_id
    save_session(session)
    return turn


def create_turn_run(
    session: OrchestratorSession,
    *,
    turn_id: str,
    run_id: str,
) -> TurnRunRecord:
    turn = find_turn(session, turn_id)
    now = datetime.now(timezone.utc)
    run = TurnRunRecord(run_id=run_id, status="running", started_at=now)
    if turn is not None:
        turn.runs.append(run)
        turn.updated_at = now
    session.active_turn_id = turn_id
    session.active_run_id = run_id
    session.active_run_status = "running"
    save_session(session)
    return run


def create_tool_call_record(
    session: OrchestratorSession,
    *,
    turn_id: str | None,
    run_id: str | None,
    trace_id: str | None,
    tool_name: str,
    tool_call_id: str,
    input_payload: dict[str, object],
    status: str = "running",
) -> ToolCallRecord:
    record = ToolCallRecord(
        turn_id=turn_id,
        run_id=run_id,
        trace_id=trace_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        input=input_payload,
        status=status,
        started_at=datetime.now(timezone.utc),
    )
    session.tool_calls.append(record)
    run = find_run(session, run_id)
    if run is not None and tool_call_id not in run.tool_call_ids:
        run.tool_call_ids.append(tool_call_id)
    save_session(session)
    return record


def update_tool_call_record(
    session: OrchestratorSession,
    record: ToolCallRecord,
) -> ToolCallRecord:
    save_session(session)
    return record


def mark_tool_call_done(
    session: OrchestratorSession,
    record: ToolCallRecord,
    *,
    output: object,
) -> ToolCallRecord:
    record.output = output
    record.status = "done"
    record.finished_at = datetime.now(timezone.utc)
    save_session(session)
    return record


def mark_tool_call_error(
    session: OrchestratorSession,
    record: ToolCallRecord,
    *,
    error: str,
) -> ToolCallRecord:
    record.output = {"error": error}
    record.status = "error"
    record.finished_at = datetime.now(timezone.utc)
    save_session(session)
    return record


def append_tool_observation(
    session: OrchestratorSession,
    *,
    turn_id: str | None,
    run_id: str | None,
    tool_call_id: str,
    content: str,
) -> OrchestratorMessage:
    message = OrchestratorMessage(
        role="tool",
        tool_call_id=tool_call_id,
        turn_id=turn_id,
        run_id=run_id,
        content=content,
        timestamp=datetime.now(timezone.utc),
    )
    session.messages.append(message)
    save_session(session)
    return message


def set_run_status(
    session: OrchestratorSession,
    *,
    run_id: str | None,
    status: str,
    completeness: str | None = None,
) -> None:
    run = find_run(session, run_id)
    now = datetime.now(timezone.utc)
    if run is not None:
        run.status = status
        if completeness is not None:
            run.completeness = completeness
        if status in {"completed", "failed", "cancelled"}:
            run.ended_at = now
    turn = find_turn(session, session.active_turn_id if session.active_run_id == run_id else None)
    if turn is not None:
        turn.updated_at = now
        if status in {"completed", "failed", "cancelled"}:
            turn.status = status
    if session.active_run_id == run_id:
        session.active_run_status = status
        if status in {"completed", "failed", "cancelled"}:
            session.active_run_id = None
            session.active_turn_id = None
    save_session(session)


def mark_run_failed(
    session: OrchestratorSession,
    *,
    run_id: str | None,
    session_status: str,
) -> None:
    set_run_status(session, run_id=run_id, status="failed")
    session.status = session_status
    save_session(session)


def set_pending_ack(
    session: OrchestratorSession,
    *,
    run_id: str | None,
    ack_id: str,
    tool_call_id: str,
    sql_text: str,
    rows_estimated: int | None,
    step_id: str | None = None,
    tool_name: str | None = None,
    title: str | None = None,
) -> None:
    run = find_run(session, run_id)
    if run is None:
        return
    now = datetime.now(timezone.utc)
    run.pending_ack = PendingAckState(
        ack_id=ack_id,
        tool_call_id=tool_call_id,
        step_id=step_id,
        tool_name=tool_name,
        title=title,
        sql_text=sql_text,
        rows_estimated=rows_estimated,
        created_at=now,
        updated_at=now,
    )
    save_session(session)


def clear_pending_ack(session: OrchestratorSession, *, run_id: str | None) -> None:
    run = find_run(session, run_id)
    if run is None:
        return
    run.pending_ack = None
    save_session(session)


def set_pending_resolution(
    session: OrchestratorSession,
    *,
    run_id: str | None,
    resolution_id: str,
    step_id: str,
    resolution_type: str,
    message: str | None,
    options: list[str] | None = None,
    title: str | None = None,
) -> None:
    run = find_run(session, run_id)
    if run is None:
        return
    now = datetime.now(timezone.utc)
    run.pending_resolution = PendingResolutionState(
        resolution_id=resolution_id,
        step_id=step_id,
        resolution_type=resolution_type,
        title=title,
        message=message,
        options=list(options or []),
        created_at=now,
        updated_at=now,
    )
    save_session(session)


def clear_pending_resolution(session: OrchestratorSession, *, run_id: str | None) -> None:
    run = find_run(session, run_id)
    if run is None:
        return
    run.pending_resolution = None
    save_session(session)


def open_ack_with_run(open_ack_fn, session_id: str, *, ack_id: str, run_id: str | None) -> None:
    try:
        open_ack_fn(session_id, ack_id=ack_id, run_id=run_id)
    except TypeError:
        open_ack_fn(session_id)


def open_resolution_with_run(open_resolution_fn, session_id: str, *, resolution_id: str, run_id: str | None) -> None:
    try:
        open_resolution_fn(session_id, resolution_id=resolution_id, run_id=run_id)
    except TypeError:
        open_resolution_fn(session_id, resolution_id)


class SessionLifecycle:
    """Thin OO facade used by FlowContext."""

    def __init__(self, session: OrchestratorSession):
        self.session = session

    def create_turn(self, **kwargs):
        return create_turn(self.session, **kwargs)

    def create_turn_run(self, **kwargs):
        return create_turn_run(self.session, **kwargs)

    def create_tool_call_record(self, **kwargs):
        return create_tool_call_record(self.session, **kwargs)

    def update_tool_call_record(self, record: ToolCallRecord):
        return update_tool_call_record(self.session, record)

    def mark_tool_call_done(self, record: ToolCallRecord, **kwargs):
        return mark_tool_call_done(self.session, record, **kwargs)

    def mark_tool_call_error(self, record: ToolCallRecord, **kwargs):
        return mark_tool_call_error(self.session, record, **kwargs)

    def append_tool_observation(self, **kwargs):
        return append_tool_observation(self.session, **kwargs)

    def set_run_status(self, **kwargs):
        return set_run_status(self.session, **kwargs)

    def mark_run_failed(self, **kwargs):
        return mark_run_failed(self.session, **kwargs)

    def set_pending_ack(self, **kwargs):
        return set_pending_ack(self.session, **kwargs)

    def clear_pending_ack(self, **kwargs):
        return clear_pending_ack(self.session, **kwargs)

    def set_pending_resolution(self, **kwargs):
        return set_pending_resolution(self.session, **kwargs)

    def clear_pending_resolution(self, **kwargs):
        return clear_pending_resolution(self.session, **kwargs)
