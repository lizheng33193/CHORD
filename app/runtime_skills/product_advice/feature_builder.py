"""Feature builder layer for the Product Advice pipeline."""

from __future__ import annotations

from app.runtime_skills.product_advice.contracts import (
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)


class ProductAdviceFeatureBuilder:
    """Normalize upstream fields into a feature bundle for the decision engine."""

    def build(
        self,
        upstream: ProductAdviceUpstreamBundle,
        context: ProductAdviceRunContext,
    ) -> ProductAdviceFeatureBundle:
        bt = upstream.get("behavior_tags", {}) or {}
        ft = upstream.get("financial_tags", {}) or {}
        return {
            "segment": str(upstream.get("segment", "")).strip().upper(),
            "overall_risk": str(upstream.get("overall_risk", "")),
            "overall_value": str(upstream.get("overall_value", "")),
            "multi_head_risk": str(ft.get("multi_head_risk", "")),
            "debt_pressure": str(ft.get("debt_pressure", "")),
            "borrowing_urgency": str(ft.get("borrowing_urgency", "")),
            "product_activity": str(bt.get("product_activity", "")),
            "contact_channel": str(bt.get("best_contact_channel", "")),
            "contact_time": str(bt.get("best_contact_time", "")),
        }
