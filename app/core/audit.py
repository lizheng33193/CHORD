"""Audit helpers for auth and harness actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.auth.database import AuthSessionLocal
from app.auth.models import AuditEvent
from app.core.request_context import RequestContext
from app.core.user_context import UserContext


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


def _to_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    return int(text) if text.isdigit() else None


def record_runtime_audit_event(
    *,
    user: UserContext | None = None,
    request_context: RequestContext | None = None,
    user_id: int | str | None = None,
    project_id: int | str | None = None,
    country: str | None = None,
    event_type: str,
    action: str,
    status: str = "success",
    resource_type: str | None = None,
    resource_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    suppress_errors: bool = True,
) -> AuditEvent | None:
    try:
        with AuthSessionLocal() as db:
            event = record_audit_event(
                db,
                user_id=_to_int(user_id if user_id is not None else (user.user_id if user is not None else None)),
                project_id=_to_int(project_id if project_id is not None else (user.project_id if user is not None else None)),
                country=country if country is not None else (user.country if user is not None else None),
                event_type=event_type,
                action=action,
                status=status,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id if request_id is not None else (request_context.request_id if request_context is not None else None),
                session_id=session_id if session_id is not None else (request_context.session_id if request_context is not None else None),
                trace_id=trace_id if trace_id is not None else (request_context.trace_id if request_context is not None else None),
                metadata=metadata,
            )
            db.commit()
            db.refresh(event)
            return event
    except Exception:
        if suppress_errors:
            return None
        raise
