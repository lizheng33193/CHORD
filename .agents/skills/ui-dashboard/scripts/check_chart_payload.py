"""Validate chart payloads used by the dashboard."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, load_json, unwrap_charts


bootstrap_repo_root()

from app.schemas.final_response import ChartData


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate chart payloads from a module output or full API payload.")
    parser.add_argument("--input", required=True, help="JSON file containing charts, a module output, or a full API payload.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    try:
        payload = load_json(args.input)
        charts = unwrap_charts(payload)
        if not charts:
            raise ValueError("No charts found in the provided payload.")

        validated = [ChartData.model_validate(chart).model_dump() for chart in charts]
        chart_type_counts = dict(Counter(chart["chart_type"] for chart in validated))
        dump_json(
            {
                "ok": True,
                "chart_count": len(validated),
                "chart_type_counts": chart_type_counts,
            },
            args.output,
        )
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ui-dashboard chart payload validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

