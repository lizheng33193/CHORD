"""Comprehensive profile pipeline (six-step structure)."""
from __future__ import annotations

from app.runtime_skills.comprehensive.assembler import ComprehensivePageAssembler
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)
from app.runtime_skills.comprehensive.data_access import ComprehensiveUpstreamProvider
from app.runtime_skills.comprehensive.decision_engine import ComprehensiveDecisionEngine
from app.runtime_skills.comprehensive.explainer import ComprehensiveExplainer
from app.runtime_skills.comprehensive.feature_builder import ComprehensiveFeatureBuilder

__all__ = [
    "ComprehensiveDecisionEngine",
    "ComprehensiveDecisionResult",
    "ComprehensiveExplainer",
    "ComprehensiveExplanationResult",
    "ComprehensiveFeatureBuilder",
    "ComprehensiveFeatureBundle",
    "ComprehensivePageAssembler",
    "ComprehensivePageResult",
    "ComprehensiveRunContext",
    "ComprehensiveUpstreamBundle",
    "ComprehensiveUpstreamProvider",
    "build_comprehensive_run_context",
]
