"""Build comprehensive-profile prompt input from upstream module outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import dump_json, load_json


def _summary_text(payload: dict[str, Any]) -> str:
    return str(payload.get("summary", "") or "")


def _risk_level(payload: dict[str, Any]) -> str:
    structured_result = payload.get("structured_result", payload)
    metrics = structured_result.get("metrics", {}) if isinstance(structured_result, dict) else {}
    return str(metrics.get("risk_level", "unknown") or "unknown")


def _build_conflict_hints(
    app_payload: dict[str, Any],
    behavior_payload: dict[str, Any],
    credit_payload: dict[str, Any],
) -> list[str]:
    hints: list[str] = []
    app_summary = _summary_text(app_payload).lower()
    behavior_summary = _summary_text(behavior_payload).lower()
    credit_risk = _risk_level(credit_payload)

    if "high" in app_summary and credit_risk == "low":
        hints.append("App-side risk tone is stronger than credit risk; explain possible early-warning behavior.")
    if not _summary_text(credit_payload):
        hints.append("Credit summary missing; lower confidence and lean on app plus behavior.")
    if "engagement" in behavior_summary and "low" not in behavior_summary and "risk" in app_summary:
        hints.append("Active behavior and risky app signals may indicate comparison shopping rather than immediate deterioration.")
    return hints


def main() -> int:
    parser = argparse.ArgumentParser(description="Build comprehensive-profile prompt input JSON.")
    parser.add_argument("--uid", required=True, help="User id represented by the upstream outputs.")
    parser.add_argument("--app-input", required=True, help="JSON file containing the app-profile output.")
    parser.add_argument("--behavior-input", required=True, help="JSON file containing the behavior-profile output.")
    parser.add_argument("--credit-input", required=True, help="JSON file containing the credit-profile output.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    app_payload = load_json(args.app_input)
    behavior_payload = load_json(args.behavior_input)
    credit_payload = load_json(args.credit_input)

    payload = {
        "uid": args.uid,
        "prompt_variables": {
            "uid": args.uid,
            "app_result": app_payload,
            "behavior_result": behavior_payload,
            "credit_result": credit_payload,
        },
        "upstream_results": {
            "app_profile": app_payload,
            "behavior_profile": behavior_payload,
            "credit_profile": credit_payload,
        },
        "fusion_hints": {
            "conflict_hints": _build_conflict_hints(app_payload, behavior_payload, credit_payload),
            "upstream_summaries": {
                "app_profile": _summary_text(app_payload),
                "behavior_profile": _summary_text(behavior_payload),
                "credit_profile": _summary_text(credit_payload),
            },
        },
    }
    dump_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

