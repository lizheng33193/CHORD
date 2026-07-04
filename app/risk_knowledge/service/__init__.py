"""Risk knowledge consumer-facing service boundary for M2D-12."""

from __future__ import annotations

from typing import Any

__all__ = [
    "DeterministicAnswerSynthesizer",
    "ProfileExplanationAdapter",
    "RiskEvidencePipeline",
    "RiskKnowledgeRoutePolicy",
    "RiskKnowledgeService",
    "build_risk_knowledge_service_from_settings",
]


def __getattr__(name: str) -> Any:
    if name == "DeterministicAnswerSynthesizer":
        from app.risk_knowledge.service.answer_synthesizer import DeterministicAnswerSynthesizer

        return DeterministicAnswerSynthesizer
    if name == "ProfileExplanationAdapter":
        from app.risk_knowledge.service.profile_explanation_adapter import ProfileExplanationAdapter

        return ProfileExplanationAdapter
    if name == "RiskEvidencePipeline":
        from app.risk_knowledge.service.pipeline import RiskEvidencePipeline

        return RiskEvidencePipeline
    if name == "RiskKnowledgeRoutePolicy":
        from app.risk_knowledge.service.route_policy import RiskKnowledgeRoutePolicy

        return RiskKnowledgeRoutePolicy
    if name in {"RiskKnowledgeService", "build_risk_knowledge_service_from_settings"}:
        from app.risk_knowledge.service.risk_knowledge_service import (
            RiskKnowledgeService,
            build_risk_knowledge_service_from_settings,
        )

        return {
            "RiskKnowledgeService": RiskKnowledgeService,
            "build_risk_knowledge_service_from_settings": build_risk_knowledge_service_from_settings,
        }[name]
    raise AttributeError(name)
