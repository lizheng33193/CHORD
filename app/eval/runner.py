"""CLI runner for the shared eval foundation."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from app.eval.cases import EvalCaseLoadError, load_eval_cases
from app.eval.evaluators.release_gate_smoke import ReleaseGateSmokeEvaluator
from app.eval.profiles import get_profile
from app.eval.registry import REPO_ROOT, get_suite
from app.eval.report import write_report
from app.eval.schemas import EvalCase, EvalReport, EvalResult, EvalStatus


DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "evals" / "shared"


def eval_status_to_exit_code(status: EvalStatus, *, strict: bool) -> int:
    if status == "PASS":
        return 0
    if status == "WARN":
        return 1 if strict else 0
    return 1


def build_evaluator(evaluator_name: str):
    if evaluator_name == "release_gate_smoke":
        return ReleaseGateSmokeEvaluator()
    raise KeyError(f"unknown evaluator: {evaluator_name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run shared eval suites.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--suite")
    target.add_argument("--profile")
    parser.add_argument("--case-file")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    try:
        selection = _resolve_selection(suite_id=args.suite, profile_id=args.profile, strict_override=args.strict)
        suite = selection["suite"]
        profile = selection["profile"]
        strict = selection["strict"]
        case_file = Path(args.case_file or suite.case_path)
        cases = load_eval_cases(case_file)
        cases = _filter_cases_for_profile(cases, profile.profile_id if profile else None)
        evaluator = build_evaluator(suite.evaluator)
    except (KeyError, EvalCaseLoadError, ValueError) as exc:
        report = _build_error_report(
            suite_id=args.suite,
            profile_id=args.profile,
            case_file=args.case_file or "",
            strict=args.strict,
            failure=str(exc),
            runner_status="config_error",
        )
        write_report(report, Path(args.output_dir))
        return 2

    try:
        results = [evaluator.evaluate_case(case) for case in cases]
    except Exception as exc:  # pragma: no cover - covered via test monkeypatch
        report = _build_error_report(
            suite_id=suite.suite_id,
            profile_id=profile.profile_id if profile else None,
            case_file=str(case_file),
            strict=strict,
            failure=str(exc),
            runner_status="execution_error",
        )
        write_report(report, Path(args.output_dir))
        return 2

    report = _build_report(
        suite_id=suite.suite_id,
        profile_id=profile.profile_id if profile else None,
        case_file=str(case_file),
        strict=strict,
        results=results,
    )
    write_report(report, Path(args.output_dir))

    if report.failed_cases > 0:
        return 1
    return eval_status_to_exit_code(report.overall_status, strict=strict)


def _resolve_selection(*, suite_id: str | None, profile_id: str | None, strict_override: bool) -> dict[str, object]:
    if profile_id:
        profile = get_profile(profile_id)
        if len(profile.suites) != 1:
            raise ValueError("M5-1 only supports profiles with exactly one suite")
        suite = get_suite(profile.suites[0])
        return {
            "suite": suite,
            "profile": profile,
            "strict": strict_override or profile.strict_by_default,
        }
    if not suite_id:
        raise ValueError("suite_id is required when profile is not provided")
    return {
        "suite": get_suite(suite_id),
        "profile": None,
        "strict": strict_override,
    }


def _filter_cases_for_profile(cases: list[EvalCase], profile_id: str | None) -> list[EvalCase]:
    if not profile_id:
        return cases
    filtered = [case for case in cases if case.input.get("profile") == profile_id]
    return filtered or cases


def _build_report(
    *,
    suite_id: str,
    profile_id: str | None,
    case_file: str,
    strict: bool,
    results: list[EvalResult],
) -> EvalReport:
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    overall_status = _max_status([result.status for result in results] or ["PASS"])
    return EvalReport(
        run_id=datetime.now(timezone.utc).strftime("shared_eval_%Y%m%dT%H%M%SZ"),
        created_at=datetime.now(timezone.utc).isoformat(),
        suite_id=suite_id,
        profile_id=profile_id,
        case_file=case_file,
        strict=strict,
        overall_status=overall_status,
        runner_status="completed",
        total_cases=len(results),
        passed_cases=sum(1 for result in results if result.passed),
        failed_cases=sum(1 for result in results if not result.passed),
        status_counts=status_counts,
        results=results,
        failures=[],
        warnings=[],
    )


def _build_error_report(
    *,
    suite_id: str | None,
    profile_id: str | None,
    case_file: str,
    strict: bool,
    failure: str,
    runner_status,
) -> EvalReport:
    return EvalReport(
        run_id=datetime.now(timezone.utc).strftime("shared_eval_%Y%m%dT%H%M%SZ"),
        created_at=datetime.now(timezone.utc).isoformat(),
        suite_id=suite_id,
        profile_id=profile_id,
        case_file=case_file or "unknown",
        strict=strict,
        overall_status="FAIL",
        runner_status=runner_status,
        total_cases=0,
        passed_cases=0,
        failed_cases=0,
        status_counts={},
        results=[],
        failures=[failure],
        warnings=[],
    )


def _max_status(statuses: list[EvalStatus]) -> EvalStatus:
    order = {"PASS": 0, "WARN": 1, "FAIL": 2, "BLOCKED": 3}
    return max(statuses, key=lambda status: order[status])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
