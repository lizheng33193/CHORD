"""Product Advice pipeline (six-step structure)."""
from __future__ import annotations

from app.runtime_skills.product_advice.assembler import ProductAdvicePageAssembler
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceExplanationResult,
    ProductAdviceFeatureBundle,
    ProductAdvicePageResult,
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
    build_product_advice_run_context,
)
from app.runtime_skills.product_advice.data_access import ProductAdviceUpstreamProvider
from app.runtime_skills.product_advice.decision_engine import ProductAdviceDecisionEngine
from app.runtime_skills.product_advice.explainer import ProductAdviceExplainer
from app.runtime_skills.product_advice.feature_builder import ProductAdviceFeatureBuilder

__all__ = [
    "ProductAdviceDecisionEngine",
    "ProductAdviceDecisionResult",
    "ProductAdviceExplainer",
    "ProductAdviceExplanationResult",
    "ProductAdviceFeatureBuilder",
    "ProductAdviceFeatureBundle",
    "ProductAdvicePageAssembler",
    "ProductAdvicePageResult",
    "ProductAdviceRunContext",
    "ProductAdviceUpstreamBundle",
    "ProductAdviceUpstreamProvider",
    "build_product_advice_run_context",
]
