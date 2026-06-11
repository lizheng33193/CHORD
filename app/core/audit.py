"""Audit helpers for auth and harness actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.auth.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    user_id: int | None,
    project_id: int | None,
    country: str | None,
    event_type: str,
    action: str,
    status: str = "success",
    resource_type: str | None = None,
    resource_id: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        project_id=project_id,
        country=country,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        status=status,
        request_id=request_id,
        session_id=session_id,
        trace_id=trace_id,
        metadata_json=metadata or {},
    )
    db.add(event)
    return event
