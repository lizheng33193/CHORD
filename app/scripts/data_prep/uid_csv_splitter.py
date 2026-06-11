"""Utilities for splitting merged CSV data into uid-scoped CSV files."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger


logger = get_logger(__name__)
STATE_FILE_NAME = ".split_state.json"


@dataclass
class SplitStats:
    """Basic split statistics for one source file."""

    source_file: str
    row_count: int
    uid_count: int
    skipped_rows: int


def ensure_uid_csv_exists(
    *,
    source_dir: Path,
    output_dir: Path,
    target_uid: str,
    uid_column: str = "uid",
    max_open_files: int = 96,
) -> Path | None:
    """Ensure ``output_dir/<uid>.csv`` exists by splitting merged source CSV files when needed."""
    normalized_uid = str(target_uid or "").strip()
    if not normalized_uid:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{normalized_uid}.csv"
    if target_path.exists():
        return target_path

    prepare_uid_csv_directory(
        source_dir=source_dir,
        output_dir=output_dir,
        uid_column=uid_column,
        max_open_files=max_open_files,
    )
    return target_path if target_path.exists() else None


def prepare_uid_csv_directory(
    *,
    source_dir: Path,
    output_dir: Path,
    uid_column: str = "uid",
    max_open_files: int = 96,
) -> list[SplitStats]:
    """Split every eligible merged CSV under ``source_dir`` into ``output_dir/<uid>.csv`` files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_files = _list_merged_source_csvs(source_dir)
    if not source_files:
        return []

    split_state = _load_split_state(output_dir)
    split_state = _reset_state_if_sources_changed(
        output_dir=output_dir,
        source_files=source_files,
        split_state=split_state,
    )
    stats_list: list[SplitStats] = []
    for source_file in source_files:
        signature = _source_signature(source_file)
        signature_key = f"{signature}|{uid_column}"
        signature_state = split_state.get(signature_key, {})
        if signature_state.get("status") == "done":
            continue

        stats = split_csv_by_uid(
            source_file=source_file,
            output_dir=output_dir,
            uid_column=uid_column,
            max_open_files=max_open_files,
        )
        split_state[signature_key] = {
            "status": "done",
            "source_file": source_file.name,
            "uid_column": uid_column,
            "row_count": stats.row_count,
            "uid_count": stats.uid_count,
            "skipped_rows": stats.skipped_rows,
            "finished_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        _save_split_state(output_dir, split_state)
        stats_list.append(stats)

    return stats_list


def split_csv_by_uid(
    *,
    source_file: Path,
    output_dir: Path,
    uid_column: str = "uid",
    max_open_files: int = 96,
) -> SplitStats:
    """Split one merged CSV into many uid CSV files under ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Start split source csv by uid: %s", source_file)

    row_count = 0
    skipped_rows = 0
    seen_uids: set[str] = set()

    open_files: dict[str, Any] = {}
    writers: dict[str, csv.DictWriter] = {}
    lru_order: list[str] = []

    def close_uid_file(uid: str) -> None:
        file_obj = open_files.pop(uid, None)
        writers.pop(uid, None)
        if file_obj is not None:
            file_obj.close()
        if uid in lru_order:
            lru_order.remove(uid)

    def get_writer(uid: str, fieldnames: list[str]) -> csv.DictWriter:
        if uid in writers:
            if uid in lru_order:
                lru_order.remove(uid)
            lru_order.append(uid)
            return writers[uid]

        while len(open_files) >= max_open_files and lru_order:
            close_uid_file(lru_order[0])

        uid_file = output_dir / f"{uid}.csv"
        file_exists = uid_file.exists()
        file_obj = uid_file.open("a", encoding="utf-8", newline="")
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        if not file_exists or uid_file.stat().st_size == 0:
            writer.writeheader()

        open_files[uid] = file_obj
        writers[uid] = writer
        lru_order.append(uid)
        return writer

    try:
        with source_file.open("r", encoding="utf-8-sig", newline="") as in_csv:
            reader = csv.DictReader(in_csv)
            fieldnames = list(reader.fieldnames or [])
            if uid_column not in fieldnames:
                logger.warning(
                    "Skip split for %s: uid column `%s` not found",
                    source_file,
                    uid_column,
                )
                return SplitStats(
                    source_file=str(source_file),
                    row_count=0,
                    uid_count=0,
                    skipped_rows=0,
                )

            for row in reader:
                row_count += 1
                uid_value = str(row.get(uid_column, "")).strip()
                if not uid_value:
                    skipped_rows += 1
                    continue

                writer = get_writer(uid_value, fieldnames)
                writer.writerow(row)
                seen_uids.add(uid_value)
    finally:
        for uid in list(open_files.keys()):
            close_uid_file(uid)

    logger.info(
        "Finished split source csv: %s rows=%s uids=%s skipped=%s",
        source_file,
        row_count,
        len(seen_uids),
        skipped_rows,
    )
    return SplitStats(
        source_file=str(source_file),
        row_count=row_count,
        uid_count=len(seen_uids),
        skipped_rows=skipped_rows,
    )


def _list_merged_source_csvs(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    return sorted(
        [
            path
            for path in source_dir.glob("*.csv")
            if path.is_file() and not path.name.startswith(".")
        ],
        key=lambda file_path: file_path.stat().st_mtime,
    )


def _source_signature(source_file: Path) -> str:
    stat = source_file.stat()
    return f"{source_file.name}:{stat.st_size}:{stat.st_mtime_ns}"


def _state_file_path(output_dir: Path) -> Path:
    return output_dir / STATE_FILE_NAME


def _load_split_state(output_dir: Path) -> dict[str, Any]:
    state_file = _state_file_path(output_dir)
    if not state_file.exists():
        return {}
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-except
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_split_state(output_dir: Path, state: dict[str, Any]) -> None:
    state_file = _state_file_path(output_dir)
    state_file.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _reset_state_if_sources_changed(
    *,
    output_dir: Path,
    source_files: list[Path],
    split_state: dict[str, Any],
) -> dict[str, Any]:
    """Reset split outputs when a known source file changed signature."""
    known_by_name: dict[str, str] = {}
    for signature, meta in split_state.items():
        source_name = str(meta.get("source_file", "")).strip()
        if source_name:
            known_by_name[source_name] = signature.split("|", maxsplit=1)[0]

    changed = False
    for source_file in source_files:
        old_signature = known_by_name.get(source_file.name)
        if old_signature is None:
            continue
        new_signature = _source_signature(source_file)
        if old_signature != new_signature:
            changed = True
            break

    if not changed:
        return split_state

    logger.info("Detected updated merged source file. Resetting uid-split output directory: %s", output_dir)
    for csv_file in output_dir.glob("*.csv"):
        csv_file.unlink(missing_ok=True)
    state_file = _state_file_path(output_dir)
    state_file.unlink(missing_ok=True)
    return {}
