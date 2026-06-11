"""Run the current behavior preprocessor on repository data or a JSON file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


COMMON_DIR = Path(__file__).resolve().parents[2] / "_common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from skill_script_utils import bootstrap_repo_root, dump_json, get_local_repository, load_json


bootstrap_repo_root()

from app.scripts.behavior_preprocessor import preprocess_behavior_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess behavior data into a prompt-friendly JSON shape.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--uid", help="User id to load from the local repository.")
    group.add_argument("--input", help="Raw behavior JSON file.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    if args.uid:
        repository = get_local_repository()
        raw_behavior = repository.get_behavior_data(args.uid) or {}
    else:
        raw_behavior = load_json(args.input)

    payload = {
        "raw_behavior_data": raw_behavior,
        "preprocessed_behavior_data": preprocess_behavior_data(raw_behavior),
    }
    dump_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

