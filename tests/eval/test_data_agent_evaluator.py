from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "eval_cases"


def test_data_agent_eval_suites_are_runtime_or_adapter_backed_and_pass() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.data_agent import DataAgentEvaluator

    evaluator = DataAgentEvaluator()
    safety_cases = load_eval_cases(FIXTURES / "data_agent_sql_safety.yaml")
    grounding_cases = load_eval_cases(FIXTURES / "data_agent_sql_grounding.yaml")

    safety_results = [evaluator.evaluate_case(case) for case in safety_cases]
    grounding_results = [evaluator.evaluate_case(case) for case in grounding_cases]
    all_results = [*safety_results, *grounding_results]

    assert len(safety_results) >= 8
    assert len(grounding_results) >= 8
    assert all(result.passed for result in all_results)
    assert all(result.artifacts["policy_source"] in {"runtime", "adapter"} for result in all_results)


def test_data_agent_evaluator_preserves_raw_codes_and_normalizes_report_codes() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.data_agent import DataAgentEvaluator

    safety_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "data_agent_sql_safety.yaml")
    }
    grounding_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "data_agent_sql_grounding.yaml")
    }
    evaluator = DataAgentEvaluator()

    dangerous_result = evaluator.evaluate_case(safety_cases["data_agent_dangerous_delete_blocked"])
    unsupported_result = evaluator.evaluate_case(grounding_cases["data_agent_unsupported_field_warning"])

    assert dangerous_result.metrics["actual_decision"] == "blocked"
    assert dangerous_result.metrics["actual_failure_codes"] == ["DANGEROUS_SQL_BLOCKED"]
    assert dangerous_result.artifacts["raw_failures"] == ["RISKY_SQL_OPERATION"]
    assert dangerous_result.artifacts["normalized_failures"] == ["DANGEROUS_SQL_BLOCKED"]

    assert unsupported_result.metrics["actual_decision"] == "warning"
    assert unsupported_result.metrics["actual_warning_codes"] == ["UNSUPPORTED_FIELD"]
    assert unsupported_result.artifacts["raw_warnings"] == ["UNSUPPORTED_FIELD"]
    assert unsupported_result.artifacts["normalized_warnings"] == ["UNSUPPORTED_FIELD"]


def test_data_agent_evaluator_uses_hitl_and_case_policy_adapters_without_side_effects() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.data_agent import DataAgentEvaluator

    safety_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "data_agent_sql_safety.yaml")
    }
    grounding_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "data_agent_sql_grounding.yaml")
    }
    evaluator = DataAgentEvaluator()

    execute_blocked = evaluator.evaluate_case(safety_cases["data_agent_execute_without_approved_sql_blocked"])
    approved_example = evaluator.evaluate_case(
        grounding_cases["data_agent_approved_sql_example_classification_allowed"]
    )
    failed_case = evaluator.evaluate_case(
        grounding_cases["data_agent_failed_sql_error_case_classification_only"]
    )

    assert execute_blocked.metrics["check_kind"] == "hitl_boundary"
    assert execute_blocked.artifacts["policy_source"] == "adapter"
    assert execute_blocked.artifacts["raw_failures"] == ["SQL_APPROVAL_REQUIRED"]
    assert execute_blocked.artifacts["execute_allowed"] is False

    assert approved_example.metrics["check_kind"] == "sql_case_policy"
    assert approved_example.artifacts["policy_source"] == "adapter"
    assert approved_example.artifacts["approved_example_eligible"] is True
    assert approved_example.artifacts["error_case_eligible"] is False

    assert failed_case.metrics["check_kind"] == "sql_case_policy"
    assert failed_case.artifacts["policy_source"] == "adapter"
    assert failed_case.artifacts["approved_example_eligible"] is False
    assert failed_case.artifacts["error_case_eligible"] is True
