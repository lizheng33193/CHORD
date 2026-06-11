"""Unified entry point for explicit local data preparation."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.scripts.data_prep.applist_joiner import prepare_joined_applist_by_uid
from app.scripts.data_prep.behavior_preparer import (
    prepare_behavior_prepared_json_directory,
)
from app.scripts.data_prep.credit_preparer import prepare_credit_prepared_json_directory
from app.scripts.data_prep.uid_csv_splitter import prepare_uid_csv_directory


logger = get_logger(__name__)
SUPPORTED_MODULES = ("app", "behavior", "credit", "all")


def prepare_local_data(
    module: str,
    *,
    max_open_files: int = 96,
) -> dict[str, dict[str, Any]]:
    """Prepare local source data into uid-scoped outputs."""
    normalized_module = str(module or "").strip().lower()
    if normalized_module not in SUPPORTED_MODULES:
        raise ValueError(f"Unsupported module: {module}")

    target_modules = (
        ("app", "behavior", "credit")
        if normalized_module == "all"
        else (normalized_module,)
    )
    results: dict[str, dict[str, Any]] = {}
    for module_name in target_modules:
        if module_name == "app":
            results[module_name] = _prepare_app(max_open_files=max_open_files)
        elif module_name == "behavior":
            results[module_name] = _prepare_behavior(max_open_files=max_open_files)
        else:
            results[module_name] = _prepare_credit(max_open_files=max_open_files)
    return results


def _prepare_app(*, max_open_files: int) -> dict[str, Any]:
    output_dir = settings.resolve_path(settings.app_by_uid_dir)
    source_dir = _resolve_app_source_dir()
    if source_dir is None:
        logger.info("Skip app data prepare: no source csv detected")
        return {
            "module": "app",
            "status": "skipped",
            "source_dir": "",
            "output_dir": str(output_dir),
            "reason": "no_source_csv",
        }

    stats = prepare_joined_applist_by_uid(
        source_dir=source_dir,
        output_dir=output_dir,
        max_open_files=max_open_files,
    )
    if stats is None:
        return {
            "module": "app",
            "status": "skipped",
            "source_dir": str(source_dir),
            "output_dir": str(output_dir),
            "reason": "missing_usage_or_label_file",
        }

    return {
        "module": "app",
        "status": "prepared",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "stats": asdict(stats),
    }


def _prepare_generic_module(
    *,
    module_name: str,
    source_dir: Path,
    output_dir: Path,
    max_open_files: int,
) -> dict[str, Any]:
    if not _has_csv_files(source_dir):
        logger.info("Skip %s data prepare: no source csv detected in %s", module_name, source_dir)
        return {
            "module": module_name,
            "status": "skipped",
            "source_dir": str(source_dir),
            "output_dir": str(output_dir),
            "reason": "no_source_csv",
        }

    stats_list = prepare_uid_csv_directory(
        source_dir=source_dir,
        output_dir=output_dir,
        uid_column="uid",
        max_open_files=max_open_files,
    )
    return {
        "module": module_name,
        "status": "prepared" if stats_list else "skipped",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "stats": [asdict(item) for item in stats_list],
        "reason": "" if stats_list else "already_prepared",
    }


def _prepare_behavior(*, max_open_files: int) -> dict[str, Any]:
    source_dir = settings.resolve_path(settings.behavior_source_dir)
    output_dir = settings.resolve_path(settings.behavior_by_uid_dir)

    split_stats: list[dict[str, Any]] = []
    if _has_csv_files(source_dir):
        uid_column = _detect_uid_column(source_dir, ("user_uuid", "uid", "user_id"))
        stats_list = prepare_uid_csv_directory(
            source_dir=source_dir,
            output_dir=output_dir,
            uid_column=uid_column,
            max_open_files=max_open_files,
        )
        split_stats = [asdict(item) for item in stats_list]

    prepared_json_stats = prepare_behavior_prepared_json_directory(
        by_uid_dir=output_dir,
        country_code=settings.default_country_code,
    )

    prepared = bool(split_stats) or prepared_json_stats.get("prepared_count", 0) > 0
    return {
        "module": "behavior",
        "status": "prepared" if prepared else "skipped",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "stats": split_stats,
        "prepared_json": prepared_json_stats,
        "reason": "" if prepared else prepared_json_stats.get("reason", "no_source_csv"),
    }


def _prepare_credit(*, max_open_files: int) -> dict[str, Any]:
    source_dir = settings.resolve_path(settings.credit_source_dir)
    output_dir = settings.resolve_path(settings.credit_by_uid_dir)

    split_stats: list[dict[str, Any]] = []
    if _has_csv_files(source_dir):
        uid_column = _detect_uid_column(source_dir, ("user_uuid", "uid", "user_id"))
        stats_list = prepare_uid_csv_directory(
            source_dir=source_dir,
            output_dir=output_dir,
            uid_column=uid_column,
            max_open_files=max_open_files,
        )
        split_stats = [asdict(item) for item in stats_list]

    prepared_json_stats = prepare_credit_prepared_json_directory(
        by_uid_dir=output_dir,
        country_code=settings.default_country_code,
    )

    prepared = bool(split_stats) or prepared_json_stats.get("prepared_count", 0) > 0
    return {
        "module": "credit",
        "status": "prepared" if prepared else "skipped",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "stats": split_stats,
        "prepared_json": prepared_json_stats,
        "reason": "" if prepared else prepared_json_stats.get("reason", "no_source_csv"),
    }


def _resolve_app_source_dir() -> Path | None:
    primary_dir = settings.resolve_path(settings.app_source_dir)
    if _has_csv_files(primary_dir):
        return primary_dir

    legacy_candidates = [
        settings.resolve_path(settings.data_dir) / "data" / "data" / "appData",
    ]
    for candidate in legacy_candidates:
        if _has_csv_files(candidate):
            return candidate
    return None


def _has_csv_files(path: Path) -> bool:
    return path.exists() and any(file_path.is_file() for file_path in path.glob("*.csv"))


def _detect_uid_column(source_dir: Path, candidates: tuple[str, ...]) -> str:
    source_files = sorted(source_dir.glob("*.csv")) if source_dir.exists() else []
    if not source_files:
        return candidates[0]
    try:
        with source_files[0].open("r", encoding="utf-8-sig", newline="") as csv_file:
            headers = set(csv.DictReader(csv_file).fieldnames or [])
    except Exception:  # pylint: disable=broad-except
        return candidates[0]
    for candidate in candidates:
        if candidate in headers:
            return candidate
    return candidates[0]


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for local data preparation."""
    parser = argparse.ArgumentParser(description="Prepare local profiling data into uid-scoped files.")
    parser.add_argument(
        "--module",
        choices=SUPPORTED_MODULES,
        required=True,
        help="Which module to prepare.",
    )
    parser.add_argument(
        "--max-open-files",
        type=int,
        default=96,
        help="Maximum number of uid output files kept open while splitting.",
    )
    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()
    result = prepare_local_data(args.module, max_open_files=args.max_open_files)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
