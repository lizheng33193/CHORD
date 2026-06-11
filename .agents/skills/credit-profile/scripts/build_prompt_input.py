"""Build credit-profile prompt input from repository data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import dump_json, get_local_repository


RISK_SCORE_MAP = {"low": 1, "medium": 2, "high": 3}


def _build_payload(uid: str, credit_data: dict[str, Any]) -> dict[str, Any]:
    risk_level = str(credit_data.get("risk_level", "unknown") or "unknown")
    credit_score_band = str(credit_data.get("credit_score_band", "unknown") or "unknown")
    repayment_status = str(credit_data.get("repayment_status", "unknown") or "unknown")

    return {
        "uid": uid,
        "prompt_variables": {
            "uid": uid,
            "credit_data": credit_data,
        },
        "credit_data": credit_data,
        "derived_signals": {
            "credit_score_band": credit_score_band,
            "repayment_status": repayment_status,
            "risk_level": risk_level,
            "debt_pressure": {
                "status": "not_directly_available_in_current_sample",
                "proxy": RISK_SCORE_MAP.get(risk_level, 0),
            },
            "credit_stability": {
                "status": "partially_available_from_repayment_status",
                "repayment_status": repayment_status,
            },
            "borrowing_hunger": {
                "status": "not_directly_available_in_current_sample",
                "note": "Current local sample lacks Buró inquiry detail and active-loan counts.",
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build credit-profile prompt input JSON.")
    parser.add_argument("--uid", required=True, help="User id to load from the local repository.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    repository = get_local_repository()
    credit_data = repository.get_credit_data(args.uid) or {}
    payload = _build_payload(args.uid, credit_data)
    dump_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

