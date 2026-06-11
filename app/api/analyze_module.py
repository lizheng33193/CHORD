"""Module-level analysis endpoint for progressive frontend loading."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.services.orchestrator import shared_orchestrator

router = APIRouter()


@router.get("/analyze-module", summary="Analyze one module for one uid")
def analyze_user_module(
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
) -> dict:
    """Run one page module and return a structured status payload."""
    return shared_orchestrator.analyze_module(
        uid.strip(),
        module.strip().lower(),
        application_time=application_time,
        country_code=country,
    )
