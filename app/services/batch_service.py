"""Batch analysis service shared by analyze and analyze-file APIs."""

from __future__ import annotations

from app.schemas.final_response import AnalyzeResponse
from app.schemas.request import AnalyzeRequest
from app.services.orchestrator import AnalysisOrchestrator


class BatchAnalysisService:
    """Provide one place for single/batch uid orchestration."""

    def __init__(self, orchestrator: AnalysisOrchestrator) -> None:
        self.orchestrator = orchestrator

    def analyze_request(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """Analyze request object with uid/uids."""
        return self.orchestrator.analyze(
            request.get_uid_list(),
            application_time=request.application_time,
            country_code=request.country,
        )

    def analyze_uids(self, uids: list[str], country_code: str = "mx") -> AnalyzeResponse:
        """Analyze a normalized uid list."""
        return self.orchestrator.analyze(uids, country_code=country_code)
