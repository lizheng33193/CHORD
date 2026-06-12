"""API routes for user profile analysis."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.auth.dependencies import require_permission
from app.auth.permissions import require_country_access
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.core.config import settings
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services.batch_service import BatchAnalysisService
from app.services.orchestrator import shared_orchestrator
from app.utils.file_parser import parse_uid_file


router = APIRouter()
batch_service = BatchAnalysisService(shared_orchestrator)


def _supported_countries() -> list[str]:
    try:
        from app.country_packs.app_profile import _APP_COUNTRY_PACKS
        from app.country_packs.behavior_profile import _BEHAVIOR_COUNTRY_PACKS
        from app.country_packs.credit_profile import _CREDIT_COUNTRY_PACKS

        return sorted(set(_APP_COUNTRY_PACKS) | set(_BEHAVIOR_COUNTRY_PACKS) | set(_CREDIT_COUNTRY_PACKS))
    except Exception:
        return ["mx", "th"]


@router.get("/ui-config", summary="Return frontend runtime configuration")
def get_ui_config() -> dict:
    """Expose UI timing knobs that should be backend-configurable."""
    return {
        "uid_transition_duration_ms": settings.uid_transition_duration_ms,
        "auth_enabled": settings.auth_enabled,
        "supported_countries": _supported_countries(),
    }


@router.post("/analyze", response_model=AnalyzeResponse, summary="Analyze one or more users")
def analyze_users(
    request: AnalyzeRequest,
    http_request: Request,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> AnalyzeResponse:
    """Run the orchestrator and return analysis based on local sample data."""
    require_country_access(ctx, request.country, project_id=ctx.project_id)
    response = batch_service.analyze_request(request)
    record_runtime_audit_event(
        user=ctx,
        request_context=None,
        request_id=http_request.headers.get("X-Request-ID"),
        event_type="profile.run",
        action="run",
        resource_type="profile",
        resource_id=request.uid or "batch",
        metadata={"country": request.country, "uid_count": len(response.results)},
    )
    return response


@router.post(
    "/analyze-file",
    response_model=AnalyzeResponse,
    summary="Analyze users from an uploaded txt or csv file",
)
async def analyze_users_from_file(
    request: Request,
    file: UploadFile = File(...),
    country: Literal["mx", "th"] = Form("mx"),
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> AnalyzeResponse:
    """Parse uid values from an uploaded file and reuse the existing orchestrator."""
    require_country_access(ctx, country, project_id=ctx.project_id)
    raw_bytes = await file.read()
    try:
        normalized_uids = parse_uid_file(file.filename or "", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = batch_service.analyze_uids(normalized_uids, country_code=country)
    record_runtime_audit_event(
        user=ctx,
        request_id=request.headers.get("X-Request-ID"),
        event_type="profile.run",
        action="run",
        resource_type="profile",
        resource_id=file.filename or "uploaded_file",
        metadata={"country": country, "uid_count": len(normalized_uids)},
    )
    return response
