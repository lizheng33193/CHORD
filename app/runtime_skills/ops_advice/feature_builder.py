"""Feature builder layer for the Ops Advice pipeline."""

from __future__ import annotations

from app.runtime_skills.ops_advice.contracts import (
    OpsAdviceFeatureBundle,
    OpsAdviceRunContext,
    OpsAdviceUpstreamBundle,
)


class OpsAdviceFeatureBuilder:
    """Normalize upstream fields into a feature bundle for the decision engine."""

    def build(
        self,
        upstream: OpsAdviceUpstreamBundle,
        context: OpsAdviceRunContext,
    ) -> OpsAdviceFeatureBundle:
        bt = upstream.get("behavior_tags", {}) or {}
        ft = upstream.get("financial_tags", {}) or {}
        return {
            "segment": str(upstream.get("segment", "")).strip().upper(),
            "churn_risk": str(bt.get("churn_risk", "")),
            "churn_root_cause": upstream.get("churn_root_cause", ["no_clear_signal"]),
            "debt_pressure": str(ft.get("debt_pressure", "")),
            "multi_head_risk": str(ft.get("multi_head_risk", "")),
            "contact_channel": str(bt.get("best_contact_channel", "")),
            "contact_time": str(bt.get("best_contact_time", "")),
            "overall_risk": str(upstream.get("overall_risk", "")),
        }
