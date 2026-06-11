"""Summarize key behavior signals from preprocessed behavior data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import dump_json, load_json


def _risk_signals(behavior_data: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    avg_session = int(behavior_data.get("avg_session_minutes", 0) or 0)
    login_days = int(behavior_data.get("login_days_30d", 0) or 0)
    preference = str(behavior_data.get("purchase_preference", "unknown") or "unknown")

    if login_days < 10:
        metrics.append("low_login_consistency")
    if avg_session < 15:
        metrics.append("shallow_sessions")
    if "discount" in preference or "value" in preference:
        metrics.append("price_sensitive_behavior")
    if not metrics:
        metrics.append("no_strong_behavior_risk_from_current_sample")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize behavior signals from preprocessed behavior data.")
    parser.add_argument("--input", required=True, help="JSON file containing preprocessed behavior data or wrapper payload.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    payload = load_json(args.input)
    behavior_data = payload.get("preprocessed_behavior_data", payload)

    avg_session = int(behavior_data.get("avg_session_minutes", 0) or 0)
    login_days = int(behavior_data.get("login_days_30d", 0) or 0)
    engagement_score = int(behavior_data.get("engagement_score", 0) or 0)
    engagement_level = str(behavior_data.get("engagement_level", "unknown") or "unknown")
    preference = str(behavior_data.get("purchase_preference", "unknown") or "unknown")

    repayment_willingness = (
        "medium_high"
        if login_days >= 20 and avg_session >= 25
        else "medium"
        if login_days >= 10
        else "low"
    )
    product_sensitivity = (
        "high"
        if "discount" in preference or "value" in preference
        else "medium_high"
        if "premium" in preference
        else "medium"
    )

    summary = {
        "repayment_willingness": {
            "level": repayment_willingness,
            "confidence": "low",
            "note": "Current sample behavior data provides proxy signals only, not explicit repayment events.",
        },
        "activity_level": {
            "engagement_level": engagement_level,
            "engagement_score": engagement_score,
            "login_days_30d": login_days,
            "avg_session_minutes": avg_session,
        },
        "product_sensitivity": {
            "level": product_sensitivity,
            "purchase_preference": preference,
        },
        "behavior_risk_signals": _risk_signals(behavior_data),
    }

    dump_json(summary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

