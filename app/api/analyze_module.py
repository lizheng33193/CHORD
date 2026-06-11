"""Module-level analysis endpoint for progressive frontend loading."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.auth.dependencies import require_permission
from app.auth.permissions import require_country_access
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.services.orchestrator import shared_orchestrator

router = APIRouter()


@router.get("/analyze-module", summary="Analyze one module for one uid")
def analyze_user_module(
    request: Request,
    uid: str = Query(..., description="Single uid"),
    module: str = Query(
        ...,
        description="One of: app, behavior, credit, comprehensive, product, ops",
    ),
    application_time: str | None = Query(
        None, description="Optional ISO datetime for App install decay"
    ),
    country: Literal["mx", "th"] = Query(
        "mx", description="Country code"
    ),
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    """Run one page module and return a structured status payload."""
    require_country_access(ctx, country, project_id=ctx.project_id)
    response = shared_orchestrator.analyze_module(
        uid.strip(),
        module.strip().lower(),
        application_time=application_time,
        country_code=country,
    )
    record_runtime_audit_event(
        user=ctx,
        request_id=request.headers.get("X-Request-ID"),
        event_type="profile.run",
        action="run",
        resource_type="profile_module",
        resource_id=f"{uid.strip()}:{module.strip().lower()}",
        metadata={"country": country},
    )
    return response
