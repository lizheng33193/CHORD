"""Internal PR-A Risk QA pipeline."""

from __future__ import annotations

from typing import Any

__all__ = [
    "CitationValidationResult",
    "EvidenceSufficiencyResult",
    "RiskQaPipeline",
    "RiskQaPipelineResult",
    "RiskQaRequest",
]


def __getattr__(name: str) -> Any:
    if name == "RiskQaPipeline":
        from app.risk_knowledge.qa.pipeline import RiskQaPipeline

        return RiskQaPipeline
    if name in {
        "CitationValidationResult",
        "EvidenceSufficiencyResult",
        "RiskQaPipelineResult",
        "RiskQaRequest",
    }:
        from app.risk_knowledge.qa.schemas import (
            CitationValidationResult,
            EvidenceSufficiencyResult,
            RiskQaPipelineResult,
            RiskQaRequest,
        )

        return {
            "CitationValidationResult": CitationValidationResult,
            "EvidenceSufficiencyResult": EvidenceSufficiencyResult,
            "RiskQaPipelineResult": RiskQaPipelineResult,
            "RiskQaRequest": RiskQaRequest,
        }[name]
    raise AttributeError(name)
