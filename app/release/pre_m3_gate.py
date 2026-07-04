"""Pre-M3 release gate entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from app.release.schemas import ReleaseGateCheckResult, ReleaseGateProfile, ReleaseGateReport


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

    return ReleaseGateReport(
        profile=profile,
        release_gate_status=gate_status,  # type: ignore[arg-type]
        checks=checks,
        failed_checks=failed_checks,
        warnings=warnings,
        recommendation=recommendation,
    )


def default_check_runner(profile: ReleaseGateProfile) -> list[ReleaseGateCheckResult]:
    return [
        ReleaseGateCheckResult(
            check_name="full_repo_regression",
            category="test_coverage",
            status="NOT_RUN",
            summary="full repository regression not run",
            blocking=False,
            details={"profile": profile},
        )
    ]


def main(argv: list[str] | None = None, *, check_runner: CheckRunner | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Pre-M3 release gate.")
    parser.add_argument("--profile", choices=["pr_acceptance", "production_release"], default="pr_acceptance")
    parser.add_argument("--output-json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    runner = check_runner or default_check_runner
    report = build_release_gate_report(profile=args.profile, checks=runner(args.profile))

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
