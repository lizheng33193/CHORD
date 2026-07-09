from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_TARGETS = [
    "outputs/memory",
    "outputs/risk_knowledge",
    "outputs/orchestrator_sessions",
    "outputs/evals",
    "storage/risk_knowledge",
]

OPTIONAL_TARGETS = ["data"]

EXCLUDED_PATTERNS = [
    ".env",
    ".env.*",
    "key.json",
    "app/key.json",
    "*.pem",
    "*.key",
    "*.crt",
    "*.p12",
    "*.p8",
]


@dataclass
class BackupStats:
    file_count: int = 0
    total_bytes: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local CHORD state backup archive.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--include-data", action="store_true")
    return parser.parse_args()


def _matches_excluded(relative_path: str) -> bool:
    path_obj = Path(relative_path)
    candidates = {
        relative_path,
        path_obj.as_posix(),
        path_obj.name,
    }
    return any(
        fnmatch.fnmatch(candidate, pattern)
        for candidate in candidates
        for pattern in EXCLUDED_PATTERNS
    )


def _archive_prefix() -> str:
    return datetime.now(UTC).strftime("chord-state-backup-%Y%m%d-%H%M%S")


def _ensure_within_root(path: Path, *, project_root: Path) -> bool:
    try:
        path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return False
    return True


def _iter_entries(root: Path) -> list[Path]:
    entries: list[Path] = [root]
    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current_root)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                continue
            kept_dirs.append(dirname)
            entries.append(candidate)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            entries.append(current_path / filename)
    return entries


def _sha256_for_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = list(DEFAULT_TARGETS)
    if args.include_data:
        targets.extend(OPTIONAL_TARGETS)

    prefix = _archive_prefix()
    archive_path = output_dir / f"{prefix}.tar.gz"
    manifest_path = output_dir / f"{prefix}.manifest.json"

    warnings: list[str] = []
    included_paths: list[str] = []
    skipped_paths: list[str] = []
    stats = BackupStats()

    with tarfile.open(archive_path, "w:gz") as archive:
        for target in targets:
            target_path = (project_root / target).resolve()
            if not target_path.exists():
                warning = f"missing target: {target}"
                warnings.append(warning)
                print(f"warning: {warning}")
                continue
            if not _ensure_within_root(target_path, project_root=project_root):
                warning = f"target escaped project root and was skipped: {target}"
                warnings.append(warning)
                print(f"warning: {warning}")
                continue
            if target_path.is_symlink():
                warning = f"symlink target root skipped: {target}"
                warnings.append(warning)
                print(f"warning: {warning}")
                continue

            included_paths.append(target)
            for entry in _iter_entries(target_path):
                relative_path = entry.relative_to(project_root).as_posix()
                if entry.is_symlink():
                    warning = f"symlink skipped: {relative_path}"
                    warnings.append(warning)
                    skipped_paths.append(relative_path)
                    print(f"warning: {warning}")
                    continue
                if _matches_excluded(relative_path):
                    warning = f"excluded secret-like path skipped: {relative_path}"
                    warnings.append(warning)
                    skipped_paths.append(relative_path)
                    print(f"warning: {warning}")
                    continue
                archive.add(entry, arcname=relative_path, recursive=False)
                if entry.is_file():
                    stats.file_count += 1
                    stats.total_bytes += entry.stat().st_size
                    print(f"included file: {relative_path}")
                else:
                    print(f"included dir: {relative_path}")

    archive_sha256 = _sha256_for_file(archive_path)
    manifest_payload = {
        "backup_version": "m7b-v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "project_root": str(project_root),
        "archive_name": archive_path.name,
        "included_paths": included_paths,
        "excluded_patterns": EXCLUDED_PATTERNS,
        "include_data": args.include_data,
        "file_count": stats.file_count,
        "total_bytes": stats.total_bytes,
        "archive_sha256": archive_sha256,
        "warnings": warnings,
        "skipped_paths": skipped_paths,
        "notes": [
            "Secrets are excluded from local state backup archives.",
            "External auth databases and other operator-owned external databases are not backed up by M7B local state scripts.",
        ],
    }
    _write_manifest(manifest_path, manifest_payload)

    print(f"archive: {archive_path}")
    print(f"manifest: {manifest_path}")
    print(f"archive sha256: {archive_sha256}")
    print(f"included targets: {len(included_paths)}")
    print(f"file count: {stats.file_count}")
    print(f"warnings: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
