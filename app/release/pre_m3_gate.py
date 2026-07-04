"""Pre-M3 release gate entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from app.release.schemas import (
    FullRegressionStatus,
    ReleaseGateCheckResult,
    ReleaseGateProfile,
    ReleaseGateReport,
)


CheckRunner = Callable[[ReleaseGateProfile], list[ReleaseGateCheckResult]]


def build_release_gate_report(
    *,
    profile: ReleaseGateProfile,
    checks: list[ReleaseGateCheckResult],
) -> ReleaseGateReport:
    warnings: list[str] = []
    failed_checks: list[str] = []
    gate_status = "PASS"

    for check in checks:
        if check.status == "NOT_RUN" and check.check_name == "full_repo_regression":
            warnings.append(check.summary)
            if profile == "production_release":
                gate_status = "BLOCKED"
                failed_checks.append(check.check_name)
            elif gate_status == "PASS":
                gate_status = "WARN"
            continue

        if check.status == "BLOCKED":
            gate_status = "BLOCKED"
            failed_checks.append(check.check_name)
            continue
        if check.status == "FAIL":
            if gate_status != "BLOCKED":
                gate_status = "FAIL"
            failed_checks.append(check.check_name)
            continue
        if check.status == "WARN" and gate_status == "PASS":
            gate_status = "WARN"
            warnings.append(check.summary)

    recommendation = {
        "PASS": "Proceed with the next planned acceptance step.",
        "WARN": "Proceed only with explicit reviewer awareness of outstanding non-blocking risk.",
        "FAIL": "Do not proceed until required runtime checks pass.",
        "BLOCKED": "Production release must not proceed until blocking checks are resolved.",
    }[gate_status]

    full_regression_status = _extract_full_regression_status(checks)

    return ReleaseGateReport(
        profile=profile,
        release_gate_status=gate_status,  # type: ignore[arg-type]
        full_regression_status=full_regression_status,
        checks=checks,
        failed_checks=failed_checks,
        warnings=warnings,
        recommendation=recommendation,
    )


def _build_full_regression_check(
    profile: ReleaseGateProfile,
    full_regression_status: FullRegressionStatus,
) -> ReleaseGateCheckResult:
    if full_regression_status == "passed":
        return ReleaseGateCheckResult(
            check_name="full_repo_regression",
            category="test_coverage",
            status="PASS",
            summary="full repository regression passed",
            blocking=False,
            details={"profile": profile, "full_regression_status": full_regression_status},
        )

    if full_regression_status == "failed":
        return ReleaseGateCheckResult(
            check_name="full_repo_regression",
            category="test_coverage",
            status="BLOCKED" if profile == "production_release" else "FAIL",
            summary="full repository regression failed",
            blocking=profile == "production_release",
            details={"profile": profile, "full_regression_status": full_regression_status},
        )

    return ReleaseGateCheckResult(
        check_name="full_repo_regression",
        category="test_coverage",
        status="NOT_RUN",
        summary="full repository regression not run",
        blocking=False,
        details={"profile": profile, "full_regression_status": full_regression_status},
    )


def _upsert_full_regression_check(
    *,
    profile: ReleaseGateProfile,
    checks: list[ReleaseGateCheckResult],
    full_regression_status: FullRegressionStatus,
) -> list[ReleaseGateCheckResult]:
    full_regression_check = _build_full_regression_check(profile, full_regression_status)
    merged_checks = [check for check in checks if check.check_name != "full_repo_regression"]
    merged_checks.insert(0, full_regression_check)
    return merged_checks


def _extract_full_regression_status(
    checks: list[ReleaseGateCheckResult],
) -> FullRegressionStatus | None:
    for check in checks:
        if check.check_name != "full_repo_regression":
            continue
        value = check.details.get("full_regression_status")
        if value in {"not_run", "passed", "failed"}:
            return value
        if check.status == "NOT_RUN":
            return "not_run"
        if check.status == "PASS":
            return "passed"
        if check.status in {"FAIL", "BLOCKED"}:
            return "failed"
    return None


def default_check_runner(
    profile: ReleaseGateProfile,
    *,
    full_regression_status: FullRegressionStatus = "not_run",
) -> list[ReleaseGateCheckResult]:
    return _upsert_full_regression_check(
        profile=profile,
        checks=[],
        full_regression_status=full_regression_status,
    )


def main(argv: list[str] | None = None, *, check_runner: CheckRunner | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Pre-M3 release gate.")
    parser.add_argument("--profile", choices=["pr_acceptance", "production_release"], default="pr_acceptance")
    parser.add_argument("--output-json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--full-regression-status",
        choices=["not_run", "passed", "failed"],
        default="not_run",
    )
    args = parser.parse_args(argv)

    if check_runner is None:
        checks = default_check_runner(
            args.profile,
            full_regression_status=args.full_regression_status,
        )
    else:
        checks = _upsert_full_regression_check(
            profile=args.profile,
            checks=check_runner(args.profile),
            full_regression_status=args.full_regression_status,
        )
    report = build_release_gate_report(profile=args.profile, checks=checks)

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if args.strict:
        return 0 if report.release_gate_status == "PASS" else 1
    return 0 if report.release_gate_status in {"PASS", "WARN"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
