"""Mexico Product Advice country pack — S1-S6 strategy table."""

from __future__ import annotations

from typing import Any, Final

MX_PRODUCT_ADVICE_RULES: Final[dict[str, dict[str, Any]]] = {
    "S1": {
        "renewal_strategy": {"action": "主动续贷", "trigger_offset_days": -7, "reason": "优质客群提前 7 天触达"},
        "credit_line_action": {"action": "主动提额", "delta_pct_range": (30, 50), "reason": "高价值低风险，VIP 提额"},
        "rate_plan": {"plan": "VIP 专属低利率", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": "Push"},
        "priority": "P0",
        "tags": ["S1", "主动续贷", "主动提额", "VIP"],
    },
    "S2": {
        "renewal_strategy": {"action": "续贷优惠", "trigger_offset_days": -3, "reason": "稳健客群满期前 3 天触达"},
        "credit_line_action": {"action": "适度提额", "delta_pct_range": (10, 20), "reason": "信用稳定，适度上调"},
        "rate_plan": {"plan": "标准利率 + 优惠券", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": None},
        "priority": "P1",
        "tags": ["S2", "续贷优惠", "适度提额", "WhatsApp"],
    },
    "S3": {
        "renewal_strategy": {"action": "限时利率优惠续贷", "trigger_offset_days": -5, "reason": "价格敏感客群比价中"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "比价中不刺激额度"},
        "rate_plan": {"plan": "比竞品低", "anchor_competitor": "Kueski"},
        "recommended_channel": {"primary": "Push", "secondary": "Email"},
        "priority": "P1",
        "tags": ["S3", "限时优惠", "比价锚点", "Push"],
    },
    "S4": {
        "renewal_strategy": {"action": "挽回式续贷", "trigger_offset_days": -10, "reason": "潜在流失需提前挽回"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "活跃下降不动额度"},
        "rate_plan": {"plan": "挽回券（首期免息）", "anchor_competitor": None},
        "recommended_channel": {"primary": "WhatsApp", "secondary": None},
        "priority": "P0",
        "tags": ["S4", "挽回续贷", "首期免息", "WhatsApp 专属关怀"],
    },
    "S5": {
        "renewal_strategy": {"action": "不主动续贷 / 缩短账期", "trigger_offset_days": 0, "reason": "多头高风险不主动"},
        "credit_line_action": {"action": "控额", "delta_pct_range": None, "reason": "多头借贷需控风险敞口"},
        "rate_plan": {"plan": "不发券", "anchor_competitor": None},
        "recommended_channel": {"primary": "SMS", "secondary": None},
        "priority": "—",
        "tags": ["S5", "不主动续贷", "控额", "风控通知"],
    },
    "S6": {
        "renewal_strategy": {"action": "场景化续贷（Buen Fin 唤醒）", "trigger_offset_days": -14, "reason": "沉默客群场景唤醒"},
        "credit_line_action": {"action": "维持额度", "delta_pct_range": None, "reason": "无明确意图"},
        "rate_plan": {"plan": "标准利率", "anchor_competitor": None},
        "recommended_channel": {"primary": "Push", "secondary": None},
        "priority": "P2",
        "tags": ["S6", "场景化", "Buen Fin", "轻触达"],
    },
}
