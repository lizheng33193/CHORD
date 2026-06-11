"""Build app-profile prompt input from repository data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import dump_json, get_local_repository


LENDING_KEYWORDS = (
    "loan",
    "credit",
    "cash",
    "kueski",
    "moneyman",
    "creditea",
    "dineria",
    "okredito",
)
FINANCE_KEYWORDS = (
    "bbva",
    "banorte",
    "stori",
    "nu",
    "wallet",
    "pay",
    "bank",
)


def _build_payload(uid: str, app_data: dict[str, Any]) -> dict[str, Any]:
    installed_apps = list(app_data.get("installed_apps", []))
    normalized_apps = [str(app_name).lower() for app_name in installed_apps]
    lending_app_count = sum(
        1
        for app_name in normalized_apps
        if any(keyword in app_name for keyword in LENDING_KEYWORDS)
    )
    finance_app_count = sum(
        1
        for app_name in normalized_apps
        if any(keyword in app_name for keyword in FINANCE_KEYWORDS)
    )
    active_days = int(app_data.get("active_days_30d", 0) or 0)
    installed_app_count = len(installed_apps)
    top_category = str(app_data.get("top_category", "unknown") or "unknown")

    consumption_level = (
        "medium_high"
        if top_category in {"lifestyle", "shopping", "commerce"} and installed_app_count >= 3
        else "medium"
        if installed_app_count >= 2
        else "low"
    )
    multi_loan_risk_level = (
        "high" if lending_app_count >= 3 else "medium" if lending_app_count >= 1 else "low"
    )
    financial_maturity_level = (
        "banked"
        if finance_app_count >= 2
        else "semi_banked"
        if finance_app_count == 1
        else "unbanked_or_unknown"
    )

    return {
        "uid": uid,
        "prompt_variables": {
            "uid": uid,
            "app_data": app_data,
        },
        "app_data": app_data,
        "derived_signals": {
            "installed_app_count": installed_app_count,
            "active_days_30d": active_days,
            "top_category": top_category,
            "installation_time_decay": {
                "status": "unavailable_from_sample_data",
                "note": "Current sample app data has no install timestamps. Keep recency weighting logic in prompt design only.",
            },
            "multi_loan_risk": {
                "level": multi_loan_risk_level,
                "lending_app_count": lending_app_count,
            },
            "consumption_ability": {
                "level": consumption_level,
                "based_on_top_category": top_category,
            },
            "financial_maturity": {
                "level": financial_maturity_level,
                "finance_app_count": finance_app_count,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build app-profile prompt input JSON.")
    parser.add_argument("--uid", required=True, help="User id to load from the local repository.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    repository = get_local_repository()
    app_data = repository.get_app_data(args.uid) or {}
    payload = _build_payload(args.uid, app_data)
    dump_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

