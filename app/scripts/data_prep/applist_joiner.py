"""Build uid-scoped applist CSVs by joining usage data with applist label metadata."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger


logger = get_logger(__name__)
JOIN_STATE_FILE = ".join_state.json"
COLUMNS_TO_KEEP = [
    "uid",
    "app_name",
    "app_package",
    "first_install_time",
    "last_update_time",
    "gp_category",
    "ai_category_level_2_CN",
]


@dataclass
class JoinStats:
    """Basic join statistics for applist enrichment."""

    usage_file: str
    label_file: str
    row_count: int
    matched_rows: int
    uid_count: int
    skipped_rows: int


def prepare_joined_applist_by_uid(
    *,
    source_dir: Path,
    output_dir: Path,
    max_open_files: int = 96,
) -> JoinStats | None:
    """Create uid CSV files from joined applist usage + label metadata files."""
    usage_file = _detect_usage_file(source_dir)
    label_file = _detect_label_file(source_dir)
    if usage_file is None or label_file is None:
        logger.warning(
            "Skip applist join prepare. usage_file=%s label_file=%s source_dir=%s",
            usage_file,
            label_file,
            source_dir,
        )
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / JOIN_STATE_FILE
    state = _load_state(state_path)
    signatures = {
        "usage": _source_signature(usage_file),
        "label": _source_signature(label_file),
    }
    if state.get("signatures") == signatures and state.get("status") == "done":
        return JoinStats(
            usage_file=state.get("usage_file", usage_file.name),
            label_file=state.get("label_file", label_file.name),
            row_count=int(state.get("row_count", 0) or 0),
            matched_rows=int(state.get("matched_rows", 0) or 0),
            uid_count=int(state.get("uid_count", 0) or 0),
            skipped_rows=int(state.get("skipped_rows", 0) or 0),
        )

    for csv_file in output_dir.glob("*.csv"):
        csv_file.unlink(missing_ok=True)

    label_map = _build_label_map(label_file)
    stats = _join_and_split(
        usage_file=usage_file,
        label_map=label_map,
        output_dir=output_dir,
        max_open_files=max_open_files,
    )
    _save_state(
        state_path,
        {
            "status": "done",
            "signatures": signatures,
            "usage_file": usage_file.name,
            "label_file": label_file.name,
            "row_count": stats.row_count,
            "matched_rows": stats.matched_rows,
            "uid_count": stats.uid_count,
            "skipped_rows": stats.skipped_rows,
            "finished_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    logger.info(
        "Prepared joined applist by uid. usage=%s label=%s rows=%s matched=%s uids=%s skipped=%s",
        usage_file.name,
        label_file.name,
        stats.row_count,
        stats.matched_rows,
        stats.uid_count,
        stats.skipped_rows,
    )
    return stats


def _join_and_split(
    *,
    usage_file: Path,
    label_map: dict[str, dict[str, str]],
    output_dir: Path,
    max_open_files: int,
) -> JoinStats:
    row_count = 0
    matched_rows = 0
    fallback_rows = 0
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

    def get_writer(uid: str) -> csv.DictWriter:
        if uid in writers:
            if uid in lru_order:
                lru_order.remove(uid)
            lru_order.append(uid)
            return writers[uid]

        while len(open_files) >= max_open_files and lru_order:
            close_uid_file(lru_order[0])

        uid_file = output_dir / f"{uid}.csv"
        file_obj = uid_file.open("a", encoding="utf-8", newline="")
        writer = csv.DictWriter(file_obj, fieldnames=COLUMNS_TO_KEEP)
        if uid_file.stat().st_size == 0:
            writer.writeheader()
        open_files[uid] = file_obj
        writers[uid] = writer
        lru_order.append(uid)
        return writer

    try:
        with usage_file.open("r", encoding="utf-8-sig", newline="") as in_csv:
            reader = csv.DictReader(in_csv)
            for row in reader:
                row_count += 1
                uid = str(row.get("uid", "")).strip()
                package = _normalize_package(row.get("app_package", ""))
                if not uid:
                    skipped_rows += 1
                    continue
                label_row = label_map.get(package) if package else None

                joined_row = {
                    "uid": uid,
                    "app_name": str(row.get("app_name", "")).strip()
                    or str((label_row or {}).get("app_name", "")).strip()
                    or "",
                    "app_package": str(row.get("app_package", "")).strip(),
                    "first_install_time": str(row.get("first_install_time", "")).strip(),
                    "last_update_time": str(row.get("last_update_time", "")).strip(),
                    "gp_category": str((label_row or {}).get("gp_category", "")).strip() or "unknown",
                    "ai_category_level_2_CN": str((label_row or {}).get("ai_category_level_2_CN", "")).strip()
                    or "unknown",
                }
                writer = get_writer(uid)
                writer.writerow(joined_row)
                if label_row is not None:
                    matched_rows += 1
                else:
                    fallback_rows += 1
                seen_uids.add(uid)
    finally:
        for uid in list(open_files.keys()):
            close_uid_file(uid)

    return JoinStats(
        usage_file=str(usage_file),
        label_file="in-memory-label-map",
        row_count=row_count,
        matched_rows=matched_rows,
        uid_count=len(seen_uids),
        skipped_rows=skipped_rows + fallback_rows,
    )


def _build_label_map(label_file: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    with label_file.open("r", encoding="utf-8-sig", newline="") as in_csv:
        reader = csv.DictReader(in_csv)
        for row in reader:
            package = _normalize_package(row.get("app_package", ""))
            if not package:
                continue
            if package not in mapping:
                mapping[package] = {
                    "app_name": str(row.get("app_name", "")).strip(),
                    "gp_category": str(row.get("gp_category", "")).strip(),
                    "ai_category_level_2_CN": str(row.get("ai_category_level_2_CN", "")).strip(),
                }
    return mapping


def _normalize_package(value: Any) -> str:
    return str(value or "").strip().lower()


def _detect_usage_file(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    candidates = sorted(path for path in source_dir.glob("*.csv") if path.is_file())
    for candidate in candidates:
        name = candidate.name.lower()
        if "label" in name:
            continue
        if _has_columns(candidate, {"uid", "app_package", "first_install_time", "last_update_time"}):
            return candidate
    return None


def _detect_label_file(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None
    candidates = sorted(path for path in source_dir.glob("*.csv") if path.is_file())
    for candidate in candidates:
        name = candidate.name.lower()
        if "label" not in name:
            continue
        if _has_columns(candidate, {"app_package", "gp_category", "ai_category_level_2_CN"}):
            return candidate
    for candidate in candidates:
        if _has_columns(candidate, {"app_package", "gp_category", "ai_category_level_2_CN"}):
            return candidate
    return None


def _has_columns(csv_file: Path, required: set[str]) -> bool:
    try:
        with csv_file.open("r", encoding="utf-8-sig", newline="") as in_csv:
            reader = csv.DictReader(in_csv)
            columns = {str(field or "").strip() for field in (reader.fieldnames or [])}
    except Exception:  # pylint: disable=broad-except
        return False
    return required.issubset(columns)


def _source_signature(source_file: Path) -> str:
    stat = source_file.stat()
    return f"{source_file.name}:{stat.st_size}:{stat.st_mtime_ns}"


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-except
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
