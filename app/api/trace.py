"""GET /api/trace/{uid} route — independent endpoint.

Not coupled to /api/analyze. Invoked on-demand by frontend.
See docs/specs/trace-analyzer-design.md §2.Q1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import require_permission
from app.core.user_context import UserContext
from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
from app.schemas.trace_analyzer import TraceAnalyzeResponse

router = APIRouter(tags=["trace_analyzer"])


@router.get("/api/trace/{uid}")
def get_trace(
    uid: str,
    _ctx: UserContext = Depends(require_permission("trace:run")),
) -> JSONResponse:
    analyzer = TraceAnalyzer()
    raw = analyzer.analyze(uid, build_context(uid))
    validated = TraceAnalyzeResponse.model_validate(raw)
    payload = validated.model_dump(by_alias=True)
    if payload["status"] == "data_missing":
        return JSONResponse(content=payload, status_code=404)
    return JSONResponse(content=payload, status_code=200)
