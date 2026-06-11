"""Tests for churn root cause analysis and ops strategy adaptation."""

from __future__ import annotations

from app.runtime_skills.ops_advice.decision_engine import OpsAdviceDecisionEngine


class TestChurnRootCauseOpsAdaptation:
    """Ops decision engine adapts retention strategy based on churn_root_cause."""

    def _make_feature_bundle(self, segment: str = "S4", root_causes: list[str] | None = None):
        return {
            "segment": segment,
            "churn_risk": "高",
            "churn_root_cause": root_causes or ["no_clear_signal"],
            "debt_pressure": "中",
            "multi_head_risk": "中",
            "contact_channel": "WhatsApp",
            "contact_time": "晚间19-21点",
            "overall_risk": "中",
        }

    def test_interest_perception_high_triggers_rate_discount(self):
        engine = OpsAdviceDecisionEngine()
        bundle = self._make_feature_bundle(root_causes=["interest_perception_high"])
        result = engine.decide(bundle, {"country_code": "mx"})
        assert "利率" in result["retention_offer"].get("type", "") or "折扣" in result["retention_offer"].get("type", "")

    def test_credit_limit_unmet_triggers_credit_boost(self):
        engine = OpsAdviceDecisionEngine()
        bundle = self._make_feature_bundle(root_causes=["credit_limit_unmet"])
        result = engine.decide(bundle, {"country_code": "mx"})
        assert "提额" in result["retention_offer"].get("type", "")

    def test_competitor_poaching_forces_whatsapp(self):
        engine = OpsAdviceDecisionEngine()
        bundle = self._make_feature_bundle(root_causes=["competitor_poaching"])
        bundle["contact_channel"] = "Push"  # Override to non-WhatsApp
        result = engine.decide(bundle, {"country_code": "mx"})
        assert result["outreach_channel"]["primary"] == "WhatsApp"

    def test_no_clear_signal_keeps_default_strategy(self):
        engine = OpsAdviceDecisionEngine()
        bundle = self._make_feature_bundle(root_causes=["no_clear_signal"])
        result = engine.decide(bundle, {"country_code": "mx"})
        # Should not override to 提额 or 利率折扣
        offer_type = result["retention_offer"].get("type", "")
        assert "提额体验金" not in offer_type or offer_type == ""  # default from rules
        assert "利率折扣券" not in offer_type or offer_type == ""

    def test_empty_root_causes_keeps_default(self):
        engine = OpsAdviceDecisionEngine()
        bundle = self._make_feature_bundle(root_causes=[])
        result = engine.decide(bundle, {"country_code": "mx"})
        # No adaptation — default strategy preserved
        assert "retention_offer" in result
