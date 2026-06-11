"""Summarize dashboard field mapping from a payload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import dump_json, load_json


def _get_first_result(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("results")
    if isinstance(results, list) and results:
        first_result = results[0]
        if isinstance(first_result, dict):
            return first_result
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Map the fields the dashboard consumes from a user result payload.")
    parser.add_argument("--input", required=True, help="JSON file containing a full API payload or a single user result.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    payload = load_json(args.input)
    result_payload = _get_first_result(payload)

    mapping = {
        "home_view": {
            "uid_input": "uid",
            "file_upload": "analyze-file request payload",
        },
        "dashboard_tabs": {
            "comprehensive": {
                "summary": "comprehensive_profile.summary",
                "persona": "comprehensive_profile.structured_result.persona",
                "tags": "comprehensive_profile.structured_result.tags",
                "risk_level": "comprehensive_profile.structured_result.metrics.risk_level",
            },
            "app": {
                "summary": "app_profile.summary",
                "activity_level": "app_profile.structured_result.activity_level",
                "metrics": "app_profile.structured_result.metrics",
                "evidence": "app_profile.structured_result.evidence",
            },
            "behavior": {
                "summary": "behavior_profile.summary",
                "engagement_level": "behavior_profile.structured_result.engagement_level",
                "metrics": "behavior_profile.structured_result.metrics",
                "evidence": "behavior_profile.structured_result.evidence",
            },
            "credit": {
                "summary": "credit_profile.summary",
                "credit_score_band": "credit_profile.structured_result.metrics.credit_score_band",
                "repayment_status": "credit_profile.structured_result.metrics.repayment_status",
                "risk_level": "credit_profile.structured_result.metrics.risk_level",
            },
        },
        "resolved_preview": {
            "uid": result_payload.get("uid"),
            "available_sections": [
                section
                for section in (
                    "app_profile",
                    "behavior_profile",
                    "credit_profile",
                    "comprehensive_profile",
                )
                if isinstance(result_payload.get(section), dict)
            ],
        },
    }
    dump_json(mapping, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
