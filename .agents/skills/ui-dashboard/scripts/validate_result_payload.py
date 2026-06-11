"""Validate a full dashboard-facing analysis payload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, load_json


bootstrap_repo_root()

from app.schemas.final_response import AnalyzeResponse


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a full AnalyzeResponse payload for the dashboard.")
    parser.add_argument("--input", required=True, help="JSON file containing the full API response payload.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    try:
        payload = load_json(args.input)
        validated = AnalyzeResponse.model_validate(payload).model_dump()
        result_count = len(validated.get("results", []))
        first_uid = validated["results"][0]["uid"] if result_count else None
        dump_json(
            {
                "ok": True,
                "result_count": result_count,
                "first_uid": first_uid,
            },
            args.output,
        )
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ui-dashboard result payload validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

