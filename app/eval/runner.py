"""CLI runner for the shared eval foundation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.eval.cases import EvalCaseLoadError, load_eval_cases
from app.eval.evaluators.data_agent import DataAgentEvaluator
from app.eval.evaluators.memory import MemoryGovernanceEvaluator
from app.eval.evaluators.profile import ProfileEvaluator
from app.eval.evaluators.risk_qa import RiskQAEvaluator
from app.eval.evaluators.release_gate_smoke import ReleaseGateSmokeEvaluator
from app.eval.profiles import get_profile
from app.eval.registry import REPO_ROOT, get_suite
from app.eval.report import write_report
from app.eval.schemas import EvalCase, EvalReport, EvalResult, EvalStatus, EvalSuite, EvalSuiteSummary


DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "evals" / "shared"


@dataclass(frozen=True)
class SuiteExecution:
    suite: EvalSuite
    case_file: Path
    results: list[EvalResult]
    metrics: dict[str, Any]


def eval_status_to_exit_code(status: EvalStatus, *, strict: bool) -> int:
    if status == "PASS":
        return 0
    if status == "WARN":
        return 1 if strict else 0
    return 1


def build_evaluator(evaluator_name: str):
    if evaluator_name == "release_gate_smoke":
        return ReleaseGateSmokeEvaluator()
    if evaluator_name == "memory_governance":
        return MemoryGovernanceEvaluator()
    if evaluator_name == "data_agent":
        return DataAgentEvaluator()
    if evaluator_name == "risk_qa":
        return RiskQAEvaluator()
    if evaluator_name == "profile":
        return ProfileEvaluator()
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
        selection = _resolve_selection(
            suite_id=args.suite,
            profile_id=args.profile,
            strict_override=args.strict,
        )
        suites = selection["suites"]
        profile = selection["profile"]
        strict = selection["strict"]
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
        suite_runs = _execute_suites(
            suites=suites,
            profile_id=profile.profile_id if profile else None,
            case_file_override=args.case_file,
        )
        report = _build_report(
            suite_runs=suite_runs,
            profile_id=profile.profile_id if profile else None,
            strict=strict,
        )
    except (KeyError, EvalCaseLoadError, ValueError) as exc:
        report = _build_error_report(
            suite_id=suites[0].suite_id if len(suites) == 1 else None,
            profile_id=profile.profile_id if profile else None,
            case_file=args.case_file or "",
            strict=strict,
            failure=str(exc),
            runner_status="config_error",
        )
        write_report(report, Path(args.output_dir))
        return 2
    except Exception as exc:  # pragma: no cover - covered via test monkeypatch
        report = _build_error_report(
            suite_id=suites[0].suite_id if len(suites) == 1 else None,
            profile_id=profile.profile_id if profile else None,
            case_file=_case_file_label(
                [run.case_file for run in suite_runs] if "suite_runs" in locals() else []
            ),
            strict=strict,
            failure=str(exc),
            runner_status="execution_error",
        )
        write_report(report, Path(args.output_dir))
        return 2

    write_report(report, Path(args.output_dir))

    if report.failed_cases > 0:
        return 1
    return eval_status_to_exit_code(report.overall_status, strict=strict)


def _resolve_selection(*, suite_id: str | None, profile_id: str | None, strict_override: bool) -> dict[str, object]:
    if profile_id:
        profile = get_profile(profile_id)
        return {
            "suites": [get_suite(selected_suite) for selected_suite in profile.suites],
            "profile": profile,
            "strict": strict_override or profile.strict_by_default,
        }
    if not suite_id:
        raise ValueError("suite_id is required when profile is not provided")
    return {
        "suites": [get_suite(suite_id)],
        "profile": None,
        "strict": strict_override,
    }


def _execute_suites(
    *,
    suites: list[EvalSuite],
    profile_id: str | None,
    case_file_override: str | None,
) -> list[SuiteExecution]:
    if case_file_override and len(suites) != 1:
        raise ValueError("--case-file is only supported for single-suite runs")

    suite_runs: list[SuiteExecution] = []
    for suite in suites:
        case_file = Path(case_file_override or suite.case_path)
        cases = load_eval_cases(case_file)
        filtered_cases = _filter_cases_for_profile(cases, profile_id)
        evaluator = build_evaluator(suite.evaluator)
        results = [evaluator.evaluate_case(case) for case in filtered_cases]
        suite_runs.append(
            SuiteExecution(
                suite=suite,
                case_file=case_file,
                results=results,
                metrics=evaluator.build_suite_metrics(results),
            )
        )
    return suite_runs


def _filter_cases_for_profile(cases: list[EvalCase], profile_id: str | None) -> list[EvalCase]:
    if not profile_id:
        return cases
    filtered = [case for case in cases if case.input.get("profile") == profile_id]
    return filtered or cases


def _build_report(
    *,
    suite_runs: list[SuiteExecution],
    profile_id: str | None,
    strict: bool,
) -> EvalReport:
    results = [result for suite_run in suite_runs for result in suite_run.results]
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1

    overall_status = _max_status([result.status for result in results] or ["PASS"])
    selected_suites = [suite_run.suite.suite_id for suite_run in suite_runs]
    suite_summaries = [
        _build_suite_summary(
            suite_id=suite_run.suite.suite_id,
            results=suite_run.results,
            metrics=suite_run.metrics,
        )
        for suite_run in suite_runs
    ]
    return EvalReport(
        run_id=datetime.now(timezone.utc).strftime("shared_eval_%Y%m%dT%H%M%SZ"),
        created_at=datetime.now(timezone.utc).isoformat(),
        suite_id=selected_suites[0] if len(selected_suites) == 1 else None,
        profile_id=profile_id,
        case_file=_case_file_label([suite_run.case_file for suite_run in suite_runs]),
        strict=strict,
        selected_suites=selected_suites,
        suite_summaries=suite_summaries,
        suite_metrics={summary.suite_id: dict(summary.metrics) for summary in suite_summaries},
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


def _build_suite_summary(
    *,
    suite_id: str,
    results: list[EvalResult],
    metrics: dict[str, Any],
) -> EvalSuiteSummary:
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = sum(1 for result in results if not result.passed)
    score = 1.0 if total_cases == 0 else round(sum(result.score for result in results) / total_cases, 6)
    status = _max_status([result.status for result in results] or ["PASS"])
    return EvalSuiteSummary(
        suite_id=suite_id,
        status=status,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        score=score,
        metrics=metrics,
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


def _case_file_label(case_files: list[Path]) -> str:
    if not case_files:
        return "unknown"
    labels = [str(case_file) for case_file in case_files]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
