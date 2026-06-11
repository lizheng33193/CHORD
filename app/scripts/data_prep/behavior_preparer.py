"""Prepare standardized Behavior JSON payloads from uid-scoped CSV files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.scripts.behavior_prepared_builder import prepare_behavior_record_from_csv_file


logger = get_logger(__name__)


def prepare_behavior_prepared_json_directory(
    *,
    by_uid_dir: Path,
    country_code: str,
) -> dict[str, Any]:
    """Generate prepared Behavior JSON files next to uid-scoped raw CSV files."""
    output_dir = Path(by_uid_dir)
    if not output_dir.exists():
        return {
            "status": "skipped",
            "prepared_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "reason": "missing_by_uid_dir",
        }

    prepared_count = 0
    skipped_count = 0
    error_count = 0

    for csv_path in sorted(output_dir.glob("*.csv")):
        uid = csv_path.stem
        json_path = output_dir / f"{uid}.json"
        prepared_record, errors = prepare_behavior_record_from_csv_file(
            csv_path,
            uid,
            country_code=country_code,
        )
        if not prepared_record:
            error_count += 1
            logger.warning(
                "Skip prepared Behavior JSON for uid=%s path=%s errors=%s",
                uid,
                csv_path,
                ",".join(errors),
            )
            continue

        serialized = json.dumps(
            prepared_record,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if json_path.exists():
            existing = json_path.read_text(encoding="utf-8")
            if existing == serialized:
                skipped_count += 1
                continue

        json_path.write_text(serialized, encoding="utf-8")
        prepared_count += 1

    return {
        "status": "prepared" if prepared_count else "skipped",
        "prepared_count": prepared_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "reason": "" if prepared_count else "already_prepared_or_no_csv",
    }
