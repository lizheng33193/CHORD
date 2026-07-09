from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request


RUNTIME_DIRS = [
    "outputs",
    "outputs/memory",
    "outputs/risk_knowledge",
    "outputs/orchestrator_sessions",
    "outputs/evals",
    "storage",
    "storage/risk_knowledge",
    "storage/risk_knowledge/uploads",
]

BACKUP_MANIFEST_GLOBS = [
    "backups/chord-state-backup-*.manifest.json",
    "/tmp/chord-m7b-backups/chord-state-backup-*.manifest.json",
]


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str
    status: str
    detail: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "severity": self.severity,
            "status": self.status,
            "detail": self.detail,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a minimum local runtime status snapshot for CHORD.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default="outputs/monitoring", type=Path)
    parser.add_argument("--timeout-seconds", default=30, type=int)
    parser.add_argument("--project-root", default=Path("."), type=Path)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--probe", action="append", default=[])
    return parser.parse_args()


def _resolve_path(path: Path, *, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _fetch(base_url: str, endpoint: str, *, timeout_seconds: int) -> tuple[int, str]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read(512).decode("utf-8", errors="replace").strip()
        return resp.status, body


def _check_required_health(base_url: str, *, timeout_seconds: int) -> CheckResult:
    try:
        status, body = _fetch(base_url, "/health", timeout_seconds=timeout_seconds)
    except Exception as exc:
        return CheckResult("api_health", "required", "fail", f"GET /health failed: {exc}")
    if status == 200:
        return CheckResult("api_health", "required", "pass", f"GET /health returned 200 {body}")
    return CheckResult("api_health", "required", "fail", f"GET /health returned {status}")


def _check_advisory_docs(base_url: str, *, timeout_seconds: int) -> CheckResult:
    try:
        status, body = _fetch(base_url, "/docs", timeout_seconds=timeout_seconds)
    except error.HTTPError as exc:
        if exc.code >= 500:
            return CheckResult("api_docs", "advisory", "warn", f"GET /docs returned {exc.code}")
        return CheckResult("api_docs", "advisory", "warn", f"GET /docs returned {exc.code}")
    except Exception as exc:
        return CheckResult("api_docs", "advisory", "warn", f"GET /docs failed: {exc}")
    if status == 200:
        detail = "GET /docs returned 200"
        if body:
            detail = f"{detail} {body[:80]}"
        return CheckResult("api_docs", "advisory", "pass", detail)
    if status >= 500:
        return CheckResult("api_docs", "advisory", "warn", f"GET /docs returned {status}")
    return CheckResult("api_docs", "advisory", "warn", f"GET /docs returned {status}")


def _check_runtime_dirs(project_root: Path) -> CheckResult:
    missing: list[str] = []
    existing: list[str] = []
    for item in RUNTIME_DIRS:
        path = project_root / item
        if path.exists():
            existing.append(item)
        else:
            missing.append(item)
    if missing:
        return CheckResult(
            "runtime_directories",
            "required",
            "fail",
            "missing runtime directories",
            {"missing": missing, "existing": existing},
        )
    return CheckResult(
        "runtime_directories",
        "required",
        "pass",
        "all required runtime directories exist",
        {"existing": existing},
    )


def _check_disk_usage(project_root: Path) -> CheckResult:
    total, used, free = shutil.disk_usage(project_root)
    free_percent = round((free / total) * 100, 2) if total else 0.0
    detail = f"disk free percent={free_percent}"
    metadata = {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "free_percent": free_percent,
    }
    if free_percent < 5:
        return CheckResult("disk_availability", "required", "fail", detail, metadata)
    if free_percent < 10:
        return CheckResult("disk_availability", "required", "pass", detail, metadata)
    return CheckResult("disk_availability", "required", "pass", detail, metadata)


def _advisory_disk_warning(project_root: Path) -> CheckResult | None:
    total, used, free = shutil.disk_usage(project_root)
    free_percent = round((free / total) * 100, 2) if total else 0.0
    if free_percent < 10 and free_percent >= 5:
        return CheckResult(
            "disk_availability_warning",
            "advisory",
            "warn",
            f"disk free percent below warning threshold: {free_percent}",
            {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "free_percent": free_percent,
            },
        )
    return None


def _check_backup_manifest(project_root: Path) -> CheckResult:
    candidates: list[Path] = []
    for pattern in BACKUP_MANIFEST_GLOBS:
        if pattern.startswith("/"):
            candidates.extend(sorted(Path("/").glob(pattern.lstrip("/"))))
        else:
            candidates.extend(sorted(project_root.glob(pattern)))
    candidates = [path for path in candidates if path.exists()]
    if not candidates:
        return CheckResult("latest_backup_manifest", "advisory", "not_available", "no backup manifest found")
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return CheckResult("latest_backup_manifest", "advisory", "warn", f"failed to parse manifest: {exc}")
    if not payload.get("archive_sha256"):
        return CheckResult(
            "latest_backup_manifest",
            "advisory",
            "warn",
            "backup manifest is missing archive_sha256",
            {"path": str(latest)},
        )
    return CheckResult(
        "latest_backup_manifest",
        "advisory",
        "pass",
        "backup manifest found",
        {"path": str(latest), "archive_sha256": payload.get("archive_sha256")},
    )


def _dir_size_without_symlinks(path: Path) -> tuple[int, list[str]]:
    total = 0
    warnings: list[str] = []
    if not path.exists():
        return total, warnings
    for current_root, dirnames, filenames in os.walk(path, followlinks=False):
        root_path = Path(current_root)
        kept_dirs: list[str] = []
        for dirname in dirnames:
            candidate = root_path / dirname
            if candidate.is_symlink():
                warnings.append(f"symlink skipped during size scan: {candidate}")
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in filenames:
            candidate = root_path / filename
            if candidate.is_symlink():
                warnings.append(f"symlink file skipped during size scan: {candidate}")
                continue
            try:
                total += candidate.stat().st_size
            except OSError as exc:
                warnings.append(f"failed to stat file during size scan: {candidate} ({exc})")
    return total, warnings


def _check_dir_size(project_root: Path, relative: str) -> CheckResult:
    path = project_root / relative
    if not path.exists():
        return CheckResult(relative.replace("/", "_") + "_size", "advisory", "not_available", f"{relative} does not exist")
    total_bytes, warnings = _dir_size_without_symlinks(path)
    status = "warn" if warnings else "pass"
    detail = f"{relative} size collected"
    return CheckResult(
        relative.replace("/", "_") + "_size",
        "advisory",
        status,
        detail,
        {"path": str(path), "total_bytes": total_bytes, "warnings": warnings},
    )


def _check_optional_probe(base_url: str, endpoint: str, *, timeout_seconds: int) -> CheckResult:
    try:
        status, body = _fetch(base_url, endpoint, timeout_seconds=timeout_seconds)
    except error.HTTPError as exc:
        if exc.code in {401, 403, 404, 501}:
            return CheckResult(
                f"probe:{endpoint}",
                "advisory",
                "not_available",
                f"optional probe returned {exc.code}",
            )
        if exc.code >= 500:
            return CheckResult(
                f"probe:{endpoint}",
                "advisory",
                "warn",
                f"optional probe returned {exc.code}",
            )
        return CheckResult(
            f"probe:{endpoint}",
            "advisory",
            "warn",
            f"optional probe returned {exc.code}",
        )
    except Exception as exc:
        return CheckResult(f"probe:{endpoint}", "advisory", "warn", f"optional probe failed: {exc}")
    if status == 200:
        return CheckResult(f"probe:{endpoint}", "advisory", "pass", f"optional probe returned 200 {body[:80]}")
    if status >= 500:
        return CheckResult(f"probe:{endpoint}", "advisory", "warn", f"optional probe returned {status}")
    return CheckResult(f"probe:{endpoint}", "advisory", "warn", f"optional probe returned {status}")


def _check_memory_vector_status(project_root: Path) -> CheckResult:
    vector_root = project_root / "outputs" / "memory" / "vector"
    if not vector_root.exists():
        return CheckResult("memory_vector_status", "advisory", "not_available", "memory vector directory does not exist")
    manifest_paths = [path for path in vector_root.rglob("manifest.json") if not path.is_symlink()]
    index_paths = [path for path in vector_root.rglob("index.faiss") if not path.is_symlink()]
    if not manifest_paths and not index_paths:
        return CheckResult(
            "memory_vector_status",
            "advisory",
            "not_available",
            "no memory vector artifacts found under outputs/memory/vector",
            {"path": str(vector_root)},
        )
    if manifest_paths and index_paths:
        return CheckResult(
            "memory_vector_status",
            "advisory",
            "pass",
            "memory vector artifacts discovered",
            {
                "path": str(vector_root),
                "manifest_paths": [str(path) for path in manifest_paths[:5]],
                "index_paths": [str(path) for path in index_paths[:5]],
            },
        )
    return CheckResult(
        "memory_vector_status",
        "advisory",
        "warn",
        "partial memory vector artifacts discovered",
        {
            "path": str(vector_root),
            "manifest_paths": [str(path) for path in manifest_paths[:5]],
            "index_paths": [str(path) for path in index_paths[:5]],
        },
    )


def _check_latest_release_gate_report(project_root: Path) -> CheckResult:
    eval_dir = project_root / "outputs" / "evals" / "shared"
    if not eval_dir.exists():
        return CheckResult("latest_release_gate_report", "advisory", "not_available", "shared eval output directory does not exist")
    candidates = sorted(eval_dir.glob("shared_eval_*.json"))
    if not candidates:
        return CheckResult("latest_release_gate_report", "advisory", "not_available", "no shared eval report found")
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return CheckResult(
        "latest_release_gate_report",
        "advisory",
        "pass",
        "latest shared eval report discovered",
        {"path": str(latest)},
    )


def _overall_status(checks: list[CheckResult]) -> str:
    required_failures = [check for check in checks if check.severity == "required" and check.status == "fail"]
    if required_failures:
        return "fail"
    advisory_issues = [check for check in checks if check.severity == "advisory" and check.status in {"warn", "fail"}]
    if advisory_issues:
        return "warn"
    return "pass"


def _resolve_snapshot_path(output_dir: Path) -> Path:
    stem = datetime.now(UTC).strftime("runtime-status-%Y%m%d-%H%M%S")
    candidate = output_dir / f"{stem}.json"
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = output_dir / f"{stem}-{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def _build_next_actions(checks: list[CheckResult]) -> list[str]:
    actions: list[str] = []
    if any(check.name == "api_health" and check.status == "fail" for check in checks):
        actions.append("Run startup smoke and inspect docker compose logs for the API service.")
    if any(check.name == "disk_availability" and check.status == "fail" for check in checks):
        actions.append("Free disk space before continuing deployment or restore operations.")
    if any(check.name == "latest_backup_manifest" and check.status == "warn" for check in checks):
        actions.append("Recreate a local backup and verify manifest archive_sha256 before the next deployment.")
    if not actions:
        actions.append("Review advisory warnings and operator checklist before the next production-facing change.")
    return actions


def main() -> int:
    args = _parse_args()
    project_root = args.project_root.resolve()
    if args.timeout_seconds <= 0:
        print("error: --timeout-seconds must be greater than 0", file=sys.stderr)
        return 2

    for probe in args.probe:
        if not probe.startswith("/"):
            print(f"error: invalid probe path, expected relative endpoint starting with '/': {probe}", file=sys.stderr)
            return 2
        if "://" in probe:
            print(f"error: invalid probe path, external URLs are not allowed: {probe}", file=sys.stderr)
            return 2

    checks: list[CheckResult] = []
    checks.append(_check_required_health(args.base_url, timeout_seconds=args.timeout_seconds))
    checks.append(_check_runtime_dirs(project_root))
    checks.append(_check_disk_usage(project_root))

    disk_warning = _advisory_disk_warning(project_root)
    if disk_warning is not None:
        checks.append(disk_warning)

    checks.append(_check_advisory_docs(args.base_url, timeout_seconds=args.timeout_seconds))
    checks.append(_check_backup_manifest(project_root))
    checks.append(_check_dir_size(project_root, "outputs"))
    checks.append(_check_dir_size(project_root, "storage"))
    checks.append(_check_memory_vector_status(project_root))
    checks.append(_check_latest_release_gate_report(project_root))

    for probe in args.probe:
        checks.append(_check_optional_probe(args.base_url, probe, timeout_seconds=args.timeout_seconds))

    overall_status = _overall_status(checks)
    required_failures = [check.to_dict() for check in checks if check.severity == "required" and check.status == "fail"]
    advisory_failures = [check.to_dict() for check in checks if check.severity == "advisory" and check.status == "warn"]
    warnings = []
    for check in checks:
        if check.status in {"warn", "not_available"}:
            warnings.append({"name": check.name, "detail": check.detail, "status": check.status})

    disk_total, disk_used, disk_free = shutil.disk_usage(project_root)
    disk_free_percent = round((disk_free / disk_total) * 100, 2) if disk_total else 0.0

    payload: dict[str, Any] = {
        "snapshot_version": "m7c-v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "base_url": args.base_url,
        "overall_status": overall_status,
        "checks": [check.to_dict() for check in checks],
        "warnings": warnings,
        "required_failures": required_failures,
        "advisory_failures": advisory_failures,
        "runtime_dirs": RUNTIME_DIRS,
        "disk_usage": {
            "total_bytes": disk_total,
            "used_bytes": disk_used,
            "free_bytes": disk_free,
            "free_percent": disk_free_percent,
        },
        "next_actions": _build_next_actions(checks),
    }

    if args.no_write:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        output_dir = _resolve_path(args.output_dir, project_root=project_root)
        output_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = _resolve_snapshot_path(output_dir)
        payload["snapshot_path"] = str(snapshot_path)
        snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"snapshot: {snapshot_path}")
        print(f"overall_status: {overall_status}")

    if overall_status == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
