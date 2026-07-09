from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the minimum M7D release check wrapper for CHORD.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/release_checks"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--production-release-timeout-seconds", type=int, default=600)
    parser.add_argument("--run-production-release", action="store_true")
    parser.add_argument("--skip-runtime-checks", action="store_true")
    parser.add_argument("--skip-load-smoke", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args()


def _resolve_path(path: Path, *, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _validate_args(args: argparse.Namespace) -> tuple[bool, str | None]:
    if args.timeout_seconds <= 0:
        return False, "--timeout-seconds must be greater than 0"
    if args.production_release_timeout_seconds <= 0:
        return False, "--production-release-timeout-seconds must be greater than 0"
    return True, None


def _resolve_report_path(output_dir: Path) -> Path:
    stem = datetime.now(UTC).strftime("m7d-release-check-%Y%m%d-%H%M%S")
    candidate = output_dir / f"{stem}.json"
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = output_dir / f"{stem}-{suffix}.json"
        if not candidate.exists():
            return candidate
        suffix += 1


def _find_latest(pattern: str, directory: Path) -> str:
    matches = sorted(directory.glob(pattern))
    if not matches:
        return "not_found"
    latest = max(matches, key=lambda item: item.stat().st_mtime)
    return str(latest)


def _artifact_value(path: str, *, no_write: bool) -> str:
    if no_write:
        return "stdout_only"
    return path


def _run_command(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    required: bool,
    timeout_seconds: int | None,
) -> tuple[dict[str, Any], subprocess.CompletedProcess[str] | None]:
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        duration_seconds = round(time.perf_counter() - start, 3)
        return (
            {
                "name": name,
                "command": " ".join(command),
                "required": required,
                "status": "fail",
                "exit_code": 124,
                "duration_seconds": duration_seconds,
                "detail": f"command timed out after {timeout_seconds} seconds",
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
            },
            None,
        )

    duration_seconds = round(time.perf_counter() - start, 3)
    status = "pass" if completed.returncode == 0 else "fail"
    return (
        {
            "name": name,
            "command": " ".join(command),
            "required": required,
            "status": status,
            "exit_code": completed.returncode,
            "duration_seconds": duration_seconds,
            "detail": "command completed successfully" if completed.returncode == 0 else "command exited non-zero",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
        completed,
    )


def _append_skip(checks: list[dict[str, Any]], warnings: list[str], *, name: str, reason: str, required: bool) -> None:
    checks.append(
        {
            "name": name,
            "command": "",
            "required": required,
            "status": "skipped",
            "exit_code": None,
            "duration_seconds": 0.0,
            "detail": reason,
        }
    )
    warnings.append(reason)


def main() -> int:
    args = _parse_args()
    valid, error_message = _validate_args(args)
    if not valid:
        print(f"error: {error_message}", file=sys.stderr)
        return 2

    project_root = args.project_root.resolve()
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    required_failures: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {
        "runtime_status_report": "not_run",
        "load_smoke_report": "not_run",
        "production_release_report": "not_run",
    }

    output_root = _resolve_path(args.output_dir, project_root=project_root)
    runtime_output_dir = output_root / "runtime_status"
    load_output_dir = output_root / "load_smoke"
    production_output_dir = output_root / "production_release"

    if not args.no_write:
        output_root.mkdir(parents=True, exist_ok=True)

    compile_check, _ = _run_command(
        name="compileall",
        command=[sys.executable, "-m", "compileall", "-q", "app", "data_acquisition_agent", "tests", "scripts"],
        cwd=project_root,
        required=True,
        timeout_seconds=None,
    )
    checks.append(compile_check)

    bootstrap_check, _ = _run_command(
        name="bootstrap_runtime_dirs",
        command=[sys.executable, "scripts/bootstrap_runtime_dirs.py"],
        cwd=project_root,
        required=True,
        timeout_seconds=None,
    )
    checks.append(bootstrap_check)

    if args.skip_runtime_checks:
        _append_skip(
            checks,
            warnings,
            name="startup_smoke",
            reason="startup smoke skipped via --skip-runtime-checks",
            required=True,
        )
        _append_skip(
            checks,
            warnings,
            name="runtime_status_snapshot",
            reason="runtime status snapshot skipped via --skip-runtime-checks",
            required=True,
        )
    else:
        smoke_check, _ = _run_command(
            name="startup_smoke",
            command=[
                sys.executable,
                "scripts/smoke_startup_check.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            cwd=project_root,
            required=True,
            timeout_seconds=args.timeout_seconds + 45,
        )
        checks.append(smoke_check)

        runtime_command = [
            sys.executable,
            "scripts/collect_runtime_status.py",
            "--base-url",
            args.base_url,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
        if args.no_write:
            runtime_command.append("--no-write")
        else:
            runtime_command.extend(["--output-dir", str(runtime_output_dir)])
        runtime_check, runtime_completed = _run_command(
            name="runtime_status_snapshot",
            command=runtime_command,
            cwd=project_root,
            required=True,
            timeout_seconds=args.timeout_seconds + 45,
        )
        checks.append(runtime_check)
        if runtime_completed is not None:
            if args.no_write:
                artifacts["runtime_status_report"] = _artifact_value("stdout_only", no_write=True)
            else:
                artifacts["runtime_status_report"] = _find_latest("runtime-status-*.json", runtime_output_dir)

    if args.skip_load_smoke:
        _append_skip(
            checks,
            warnings,
            name="load_smoke",
            reason="load smoke skipped via --skip-load-smoke",
            required=True,
        )
    else:
        load_command = [
            sys.executable,
            "scripts/load_smoke.py",
            "--base-url",
            args.base_url,
            "--requests",
            "50",
            "--concurrency",
            "5",
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
        if args.no_write:
            load_command.append("--no-write")
        else:
            load_command.extend(["--output-dir", str(load_output_dir)])
        load_check, load_completed = _run_command(
            name="load_smoke",
            command=load_command,
            cwd=project_root,
            required=True,
            timeout_seconds=args.timeout_seconds + 60,
        )
        checks.append(load_check)
        if load_completed is not None:
            if args.no_write:
                artifacts["load_smoke_report"] = _artifact_value("stdout_only", no_write=True)
            else:
                artifacts["load_smoke_report"] = _find_latest("load-smoke-*.json", load_output_dir)

    if args.run_production_release:
        if args.no_write:
            with tempfile.TemporaryDirectory(prefix="chord-m7d-production-release-") as temp_dir:
                temp_output_dir = Path(temp_dir)
                production_check, _ = _run_command(
                    name="production_release_strict",
                    command=[
                        sys.executable,
                        "-m",
                        "app.eval.runner",
                        "--profile",
                        "production_release",
                        "--strict",
                        "--output-dir",
                        str(temp_output_dir),
                    ],
                    cwd=project_root,
                    required=True,
                    timeout_seconds=args.production_release_timeout_seconds,
                )
                checks.append(production_check)
                artifacts["production_release_report"] = _artifact_value("stdout_only", no_write=True)
        else:
            production_check, _ = _run_command(
                name="production_release_strict",
                command=[
                    sys.executable,
                    "-m",
                    "app.eval.runner",
                    "--profile",
                    "production_release",
                    "--strict",
                    "--output-dir",
                    str(production_output_dir),
                ],
                cwd=project_root,
                required=True,
                timeout_seconds=args.production_release_timeout_seconds,
            )
            checks.append(production_check)
            artifacts["production_release_report"] = _find_latest("shared_eval_*.json", production_output_dir)
    else:
        warnings.append("production release strict gate not run; re-run with --run-production-release for release acceptance")

    for check in checks:
        if check["required"] and check["status"] == "fail":
            required_failures.append(
                {
                    "name": check["name"],
                    "command": check["command"],
                    "exit_code": check["exit_code"],
                    "detail": check["detail"],
                }
            )

    overall_status = "fail" if required_failures else "warn" if warnings else "pass"
    next_actions: list[str] = []
    if required_failures:
        next_actions.append("Fix required release checks before proceeding with any release decision.")
    if any(check["name"] == "startup_smoke" and check["status"] == "fail" for check in checks):
        next_actions.append("Ensure the service is running with docker compose up -d before re-running the wrapper.")
    if not next_actions:
        next_actions.append("Review generated artifacts and continue with the release decision runbook.")

    payload: dict[str, Any] = {
        "report_version": "m7d-release-check-v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "overall_status": overall_status,
        "go": not required_failures,
        "checks": checks,
        "required_failures": required_failures,
        "warnings": warnings,
        "artifacts": artifacts,
        "next_actions": next_actions,
    }

    if args.no_write:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        report_path = _resolve_report_path(output_root)
        payload["report_path"] = str(report_path)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {report_path}")
        print(f"overall_status: {overall_status}")

    return 1 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
