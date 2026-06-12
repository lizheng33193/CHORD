"""Final message persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.orchestrator_agent.memory_context import maybe_write_task_memory
from app.services.orchestrator_agent.runtime.session_lifecycle import find_run, find_turn
from app.services.orchestrator_agent.schemas import OrchestratorMessage, OrchestratorSession
from app.services.orchestrator_agent.session_store import save_session


def append_summary_line(existing: str | None, prompt: str, final_message: str) -> str:
    line = f"- User: {prompt[:220].strip()} | Assistant: {final_message[:320].strip()}"
    combined = "\n".join(part for part in [existing, line] if part)
    return combined[-2500:]


def persist_final_message(
    session: OrchestratorSession,
    *,
    prompt: str,
    final_message: str,
    confidence: float,
    detected_country: str | None,
    artifacts: list[dict[str, object]] | None = None,
    turn_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    turn_id = turn_id or session.active_turn_id
    run_id = run_id or session.active_run_id
    session.final_message = final_message
    session.confidence = confidence
    session.status = "completed"
    assistant_message = OrchestratorMessage(
        role="assistant",
        content=final_message,
        turn_id=turn_id,
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
    )
    session.messages.append(assistant_message)
    if turn_id:
        turn = find_turn(session, turn_id)
        if turn is not None:
            turn.assistant_message = assistant_message
            turn.artifacts = list(artifacts or turn.artifacts or [])
            turn.updated_at = assistant_message.timestamp
            turn.status = "completed"
            turn.collapsed = False
    if run_id:
        run = find_run(session, run_id)
        if run is not None:
            run.final_message = final_message
            run.ended_at = assistant_message.timestamp
            run.status = "completed"
            run.completeness = "complete"
        if session.active_run_id == run_id:
            session.active_run_status = "completed"
            session.active_run_id = None
            session.active_turn_id = None
    session.rolling_summary = append_summary_line(session.rolling_summary, prompt, final_message)
    maybe_write_task_memory(
        session=session,
        user_text=prompt,
        assistant_text=final_message,
        country=detected_country,
    )
    save_session(session)
    return {
        "type": "final",
        "final_message": final_message,
        "artifacts": list(artifacts or []),
        "total_rounds": 1,
        "total_tokens": session.total_tokens,
        "confidence": confidence,
    }
