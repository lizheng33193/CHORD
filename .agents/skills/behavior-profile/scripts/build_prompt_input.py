"""Build behavior-profile prompt input from repository data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, get_local_repository


bootstrap_repo_root()

from app.scripts.behavior_preprocessor import preprocess_behavior_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Build behavior-profile prompt input JSON.")
    parser.add_argument("--uid", required=True, help="User id to load from the local repository.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    repository = get_local_repository()
    raw_behavior = repository.get_behavior_data(args.uid) or {}
    preprocessed = preprocess_behavior_data(raw_behavior)
    payload = {
        "uid": args.uid,
        "prompt_variables": {
            "uid": args.uid,
            "behavior_data": preprocessed,
        },
        "raw_behavior_data": raw_behavior,
        "behavior_data_preprocessed": preprocessed,
    }
    dump_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

