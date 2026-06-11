"""Validate app-profile structured output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, load_json, unwrap_structured_result


bootstrap_repo_root()

from app.schemas.app_profile import AppProfileStructuredResult


REQUIRED_KEYS = ["uid", "status", "activity_level", "metrics", "tags", "evidence"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate app-profile output JSON.")
    parser.add_argument("--input", required=True, help="JSON file containing a module output or structured_result.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    try:
        payload = load_json(args.input)
        structured_result = unwrap_structured_result(payload)
        missing = [key for key in REQUIRED_KEYS if key not in structured_result]
        if missing:
            raise ValueError(f"Missing required keys: {', '.join(missing)}")

        validated = AppProfileStructuredResult.model_validate(structured_result).model_dump()
        dump_json({"ok": True, "validated": validated}, args.output)
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(f"app-profile validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

