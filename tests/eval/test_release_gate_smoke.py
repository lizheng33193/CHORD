from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


def test_release_gate_smoke_evaluator_preserves_gate_status_matrix() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.release_gate_smoke import ReleaseGateSmokeEvaluator

    evaluator = ReleaseGateSmokeEvaluator()
    cases = load_eval_cases(FIXTURES / "release_gate_smoke_status_matrix.yaml")
    results = {case.case_id: evaluator.evaluate_case(case) for case in cases}

    assert results["pr_warn_not_run"].status == "WARN"
    assert results["pr_warn_not_run"].passed is True
    assert results["pr_warn_not_run"].artifacts["actual_exit_code"] == 0

    assert results["production_blocked_not_run"].status == "BLOCKED"
    assert results["production_blocked_not_run"].passed is True
    assert results["production_blocked_not_run"].artifacts["actual_exit_code"] == 1

    assert results["pr_fail_failed"].status == "FAIL"
    assert results["pr_fail_failed"].passed is True
    assert results["production_pass_passed"].status == "PASS"
    assert results["production_pass_passed"].passed is True


def test_release_gate_smoke_result_contains_release_gate_artifacts() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.release_gate_smoke import ReleaseGateSmokeEvaluator

    case = load_eval_cases(FIXTURES / "sample_cases.yaml")[0]
    result = ReleaseGateSmokeEvaluator().evaluate_case(case)

    assert result.artifacts["release_gate_status"] == "WARN"
    assert result.artifacts["expected_status"] == "WARN"
    assert result.artifacts["expected_exit_code"] == 0
    assert result.artifacts["actual_exit_code"] == 0
    assert result.artifacts["release_gate_checks"][0]["check_name"] == "full_repo_regression"
