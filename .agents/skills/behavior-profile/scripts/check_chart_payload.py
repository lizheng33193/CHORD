"""Validate behavior-profile chart payloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, load_json, unwrap_charts, unwrap_structured_result


bootstrap_repo_root()

from app.schemas.final_response import ChartData
from app.scripts.chart_builder import build_behavior_charts


def main() -> int:
    parser = argparse.ArgumentParser(description="Check behavior-profile chart payloads.")
    parser.add_argument("--input", required=True, help="JSON file containing charts, a module output, or a structured_result.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    try:
        payload = load_json(args.input)
        charts = unwrap_charts(payload)
        if not charts and isinstance(payload, dict):
            charts = build_behavior_charts(unwrap_structured_result(payload))

        if not charts:
            raise ValueError("No chart payloads found or generated.")

        validated = [ChartData.model_validate(chart).model_dump() for chart in charts]
        dump_json({"ok": True, "chart_count": len(validated), "charts": validated}, args.output)
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"behavior chart check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
