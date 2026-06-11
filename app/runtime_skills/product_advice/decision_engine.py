"""Decision engine layer for the Product Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.country_packs.mx.product_advice_rules import MX_PRODUCT_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
)


class ProductAdviceDecisionEngine:
    """Deterministic S1-S6 → product strategy lookup."""

    def decide(
        self,
        feature_bundle: ProductAdviceFeatureBundle,
        context: ProductAdviceRunContext,
    ) -> ProductAdviceDecisionResult:
        seg = feature_bundle["segment"]
        rule = deepcopy(MX_PRODUCT_ADVICE_RULES.get(seg, {}))
        channel = deepcopy(rule.get("recommended_channel", {})) or {"primary": "", "secondary": None}
        channel["best_time"] = feature_bundle.get("contact_time", "")
        contact_channel_override = feature_bundle.get("contact_channel", "")
        if contact_channel_override and seg not in ("S5",):
            channel["primary"] = contact_channel_override

        rng = rule.get("credit_line_action", {}).get("delta_pct_range")
        credit_line = deepcopy(rule.get("credit_line_action", {}))
        if isinstance(rng, tuple):
            credit_line["delta_pct_range"] = list(rng)

        return {
            "segment": seg,
            "renewal_strategy": deepcopy(rule.get("renewal_strategy", {})),
            "credit_line_action": credit_line,
            "rate_plan": deepcopy(rule.get("rate_plan", {})),
            "recommended_channel": channel,
            "priority": str(rule.get("priority", "")),
            "tags": [str(t) for t in rule.get("tags", [])],
        }

    def build_prompt_payload(
        self,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = feature_bundle["segment"]
        return {
            "segment": seg,
            "segment_name": MX_SEGMENT_NAMES.get(seg, ""),
            "feature_bundle": dict(feature_bundle),
            "renewal_strategy": decision_result.get("renewal_strategy", {}),
            "credit_line_action": decision_result.get("credit_line_action", {}),
            "rate_plan": decision_result.get("rate_plan", {}),
            "recommended_channel": decision_result.get("recommended_channel", {}),
            "priority": decision_result.get("priority", ""),
        }
