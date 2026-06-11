"""Decision engine layer for the Ops Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.country_packs.mx.ops_advice_rules import MX_OPS_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.ops_advice.contracts import (
    OpsAdviceDecisionResult,
    OpsAdviceFeatureBundle,
    OpsAdviceRunContext,
)


_LEVEL_ORDER = ["无", "轻", "中", "强"]


def _escalate_churn(level: str) -> str:
    if level not in _LEVEL_ORDER:
        return level
    idx = _LEVEL_ORDER.index(level)
    return _LEVEL_ORDER[min(idx + 1, len(_LEVEL_ORDER) - 1)]


class OpsAdviceDecisionEngine:
    """Deterministic S1-S6 → ops strategy lookup with churn-risk escalation."""

    def decide(
        self,
        feature_bundle: OpsAdviceFeatureBundle,
        context: OpsAdviceRunContext,
    ) -> OpsAdviceDecisionResult:
        seg = feature_bundle["segment"]
        rule = deepcopy(MX_OPS_ADVICE_RULES.get(seg, {}))

        churn_warning = deepcopy(rule.get("churn_warning", {})) or {"level": "无", "signals": []}
        if str(feature_bundle.get("churn_risk", "")) == "高":
            churn_warning["level"] = _escalate_churn(str(churn_warning.get("level", "无")))
            signals = churn_warning.setdefault("signals", [])
            if "行为侧 churn_risk=高" not in signals:
                signals.append("行为侧 churn_risk=高")

        outreach = deepcopy(rule.get("outreach_channel", {})) or {"primary": "", "best_time": ""}
        contact_channel_override = feature_bundle.get("contact_channel", "")
        contact_time_override = feature_bundle.get("contact_time", "")
        if contact_channel_override and seg not in ("S5",):
            outreach["primary"] = contact_channel_override
        if contact_time_override:
            outreach["best_time"] = contact_time_override

        # Adapt retention strategy based on churn root cause
        retention = deepcopy(rule.get("retention_offer", {}))
        root_causes = feature_bundle.get("churn_root_cause", [])
        if isinstance(root_causes, list):
            if "credit_limit_unmet" in root_causes:
                retention["type"] = "提额体验金"
                retention["reasoning"] = "用户频繁访问提额页但未提交，推测额度不及预期，推荐提额体验金激活意愿"
            elif "interest_perception_high" in root_causes:
                retention["type"] = "利率折扣券"
                retention["reasoning"] = "用户在利率说明页停留较久后退出，推测利息感知过高，推荐利率折扣券降低感知成本"
            if "competitor_poaching" in root_causes:
                outreach["primary"] = "WhatsApp"
                if not retention.get("reasoning"):
                    retention["reasoning"] = "用户安装竞品APP后活跃度下降，推测被竞品挖角，通过WhatsApp紧急挽回"

        return {
            "segment": seg,
            "collection_strategy": deepcopy(rule.get("collection_strategy", {})),
            "churn_warning": churn_warning,
            "outreach_channel": outreach,
            "retention_offer": retention,
            "tags": [str(t) for t in rule.get("tags", [])],
        }

    def build_prompt_payload(
        self,
        feature_bundle: OpsAdviceFeatureBundle,
        decision_result: OpsAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = feature_bundle["segment"]
        return {
            "segment": seg,
            "segment_name": MX_SEGMENT_NAMES.get(seg, ""),
            "feature_bundle": dict(feature_bundle),
            "collection_strategy": decision_result.get("collection_strategy", {}),
            "churn_warning": decision_result.get("churn_warning", {}),
            "outreach_channel": decision_result.get("outreach_channel", {}),
            "retention_offer": decision_result.get("retention_offer", {}),
        }
