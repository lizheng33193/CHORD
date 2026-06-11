"""GET /api/trace/{uid} route — independent endpoint.

Not coupled to /api/analyze. Invoked on-demand by frontend.
See docs/specs/trace-analyzer-design.md §2.Q1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_permission
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
from app.schemas.trace_analyzer import TraceAnalyzeResponse

router = APIRouter(tags=["trace_analyzer"])


@router.get("/api/trace/{uid}")
def get_trace(
    request: Request,
    uid: str,
    ctx: UserContext = Depends(require_permission("trace:run")),
) -> JSONResponse:
    analyzer = TraceAnalyzer()
    raw = analyzer.analyze(uid, build_context(uid))
    validated = TraceAnalyzeResponse.model_validate(raw)
    payload = validated.model_dump(by_alias=True)
    record_runtime_audit_event(
        user=ctx,
        request_id=request.headers.get("X-Request-ID"),
        event_type="trace.view",
        action="view",
        status="not_found" if payload["status"] == "data_missing" else "success",
        resource_type="trace",
        resource_id=uid,
        metadata={"trace_status": payload["status"]},
    )
    if payload["status"] == "data_missing":
        return JSONResponse(content=payload, status_code=404)
    return JSONResponse(content=payload, status_code=200)
