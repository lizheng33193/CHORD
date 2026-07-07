"""Release-gate smoke evaluator for the shared eval foundation."""

from __future__ import annotations

from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult
from app.release.pre_m3_gate import (
    build_release_gate_report,
    default_check_runner,
    determine_release_gate_exit_code,
)


class ReleaseGateSmokeEvaluator(BaseEvaluator):
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        profile = str(case.input.get("profile") or "").strip()
        strict = bool(case.input.get("strict", False))
        full_regression_status = str(case.input.get("full_regression_status") or "not_run").strip() or "not_run"

        checks = default_check_runner(profile, full_regression_status=full_regression_status)  # type: ignore[arg-type]
        release_report = build_release_gate_report(profile=profile, checks=checks)  # type: ignore[arg-type]
        actual_status = release_report.release_gate_status
        actual_exit_code = determine_release_gate_exit_code(release_report.release_gate_status, strict=strict)

        expected_status = case.expected.get("status")
        expected_exit_code = case.expected.get("exit_code")
        required_check_ids = [str(item) for item in case.expected.get("must_include_check_ids", [])]
        actual_check_ids = [check.check_name for check in release_report.checks]

        failures: list[str] = []
        if actual_status != expected_status:
            failures.append(f"expected status {expected_status} but got {actual_status}")
        if actual_exit_code != expected_exit_code:
            failures.append(f"expected exit_code {expected_exit_code} but got {actual_exit_code}")
        missing_check_ids = [check_id for check_id in required_check_ids if check_id not in actual_check_ids]
        if missing_check_ids:
            failures.append(f"missing required checks: {', '.join(missing_check_ids)}")

        return EvalResult(
            case_id=case.case_id,
            suite=case.suite,
            status=actual_status,
            passed=not failures,
            score=1.0 if not failures else 0.0,
            failures=failures,
            artifacts={
                "release_gate_status": actual_status,
                "expected_status": expected_status,
                "actual_exit_code": actual_exit_code,
                "expected_exit_code": expected_exit_code,
                "release_gate_checks": [check.model_dump(mode="json") for check in release_report.checks],
            },
        )
