"""Mexico Ops Advice country pack — S1-S6 strategy table."""

from __future__ import annotations

from typing import Any, Final

MX_OPS_ADVICE_RULES: Final[dict[str, dict[str, Any]]] = {
    "S1": {
        "collection_strategy": {"trigger": "无", "reminder_steps": [], "intensity": "none"},
        "churn_warning": {"level": "无", "signals": []},
        "outreach_channel": {"primary": "—", "best_time": ""},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S1", "无需催收"],
    },
    "S2": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["WhatsApp soft"], "intensity": "soft"},
        "churn_warning": {"level": "无", "signals": []},
        "outreach_channel": {"primary": "WhatsApp", "best_time": "晚间19-21点"},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S2", "T+1 软提醒", "WhatsApp"],
    },
    "S3": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["Push soft"], "intensity": "soft"},
        "churn_warning": {"level": "轻", "signals": ["竞品APP安装", "比价行为"]},
        "outreach_channel": {"primary": "Push", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "利率券", "valid_days": 14},
        "tags": ["S3", "轻流失预警", "利率券"],
    },
    "S4": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["WhatsApp soft", "WhatsApp + Push D+3"], "intensity": "soft"},
        "churn_warning": {"level": "强", "signals": ["竞品APP安装", "活跃度下降"]},
        "outreach_channel": {"primary": "WhatsApp", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "首期免息+挽回礼包", "valid_days": 14},
        "tags": ["S4", "强流失预警", "WhatsApp", "挽回礼包"],
    },
    "S5": {
        "collection_strategy": {"trigger": "D-3", "reminder_steps": ["SMS D-3", "Phone T+1", "Phone T+7"], "intensity": "strong"},
        "churn_warning": {"level": "强", "signals": ["多头借贷", "高负债"]},
        "outreach_channel": {"primary": "SMS+Phone", "best_time": "工作日10-18点"},
        "retention_offer": {"type": None, "valid_days": None},
        "tags": ["S5", "提前提醒", "SMS+Phone", "强催收"],
    },
    "S6": {
        "collection_strategy": {"trigger": "T+1", "reminder_steps": ["Push light"], "intensity": "soft"},
        "churn_warning": {"level": "中", "signals": ["沉默 30 天"]},
        "outreach_channel": {"primary": "Push", "best_time": "晚间19-21点"},
        "retention_offer": {"type": "唤醒券", "valid_days": 30},
        "tags": ["S6", "中预警", "唤醒券", "轻触达"],
    },
}
