"""API routes for user profile analysis."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse
from app.services.batch_service import BatchAnalysisService
from app.services.orchestrator import shared_orchestrator
from app.utils.file_parser import parse_uid_file


router = APIRouter()
batch_service = BatchAnalysisService(shared_orchestrator)


@router.get("/ui-config", summary="Return frontend runtime configuration")
def get_ui_config() -> dict:
    """Expose UI timing knobs that should be backend-configurable."""
    return {
        "uid_transition_duration_ms": settings.uid_transition_duration_ms,
    }


@router.post("/analyze", response_model=AnalyzeResponse, summary="Analyze one or more users")
def analyze_users(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run the orchestrator and return analysis based on local sample data."""
    return batch_service.analyze_request(request)


@router.post(
    "/analyze-file",
    response_model=AnalyzeResponse,
    summary="Analyze users from an uploaded txt or csv file",
)
async def analyze_users_from_file(
    file: UploadFile = File(...),
    country: Literal["mx", "th"] = Form("mx"),
) -> AnalyzeResponse:
    """Parse uid values from an uploaded file and reuse the existing orchestrator."""
    raw_bytes = await file.read()
    try:
        normalized_uids = parse_uid_file(file.filename or "", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return batch_service.analyze_uids(normalized_uids, country_code=country)
