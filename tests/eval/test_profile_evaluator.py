from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "eval_cases"


def test_profile_eval_suites_are_runtime_or_adapter_backed_and_pass() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.profile import ProfileEvaluator

    evaluator = ProfileEvaluator()
    dag_cases = load_eval_cases(FIXTURES / "profile_dag_contract.yaml")
    snapshot_cases = load_eval_cases(FIXTURES / "profile_memory_snapshot.yaml")

    dag_results = [evaluator.evaluate_case(case) for case in dag_cases]
    snapshot_results = [evaluator.evaluate_case(case) for case in snapshot_cases]
    all_results = [*dag_results, *snapshot_results]

    assert len(dag_results) >= 10
    assert len(snapshot_results) >= 6
    assert all(result.passed for result in all_results)
    assert all(result.artifacts["policy_source"] in {"runtime", "adapter"} for result in all_results)


def test_profile_evaluator_preserves_runtime_status_and_memory_policy_raw_codes() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.profile import ProfileEvaluator

    dag_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "profile_dag_contract.yaml")
    }
    snapshot_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "profile_memory_snapshot.yaml")
    }
    evaluator = ProfileEvaluator()

    degraded_result = evaluator.evaluate_case(
        dag_cases["profile_dag_base_degraded_yields_comprehensive_degraded"]
    )
    blocked_result = evaluator.evaluate_case(
        snapshot_cases["profile_memory_snapshot_blocks_data_agent_grounding"]
    )

    assert degraded_result.metrics["actual_decision"] == "allowed"
    assert degraded_result.artifacts["run_status"] == "completed_with_degradation"
    assert degraded_result.artifacts["node_statuses"]["credit"] == "degraded"
    assert degraded_result.artifacts["node_statuses"]["comprehensive"] == "degraded"

    assert blocked_result.metrics["actual_decision"] == "blocked"
    assert blocked_result.artifacts["policy_source"] == "runtime"
    assert blocked_result.artifacts["raw_failures"] == ["explicit_forbidden_use"]
    assert blocked_result.artifacts["normalized_failures"] == [
        "PROFILE_DAG_PROFILE_RESULT_NOT_DATA_GROUNDING"
    ]
    assert blocked_result.artifacts["memory_boundary_decisions"]["requested_use"] == "data_agent_field_grounding"


def test_profile_evaluator_validates_event_and_legacy_adapter_contracts() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.profile import ProfileEvaluator

    dag_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "profile_dag_contract.yaml")
    }
    snapshot_cases = {
        case.case_id: case for case in load_eval_cases(FIXTURES / "profile_memory_snapshot.yaml")
    }
    evaluator = ProfileEvaluator()

    event_result = evaluator.evaluate_case(dag_cases["profile_dag_event_contract_contains_required_events"])
    analysis_result = evaluator.evaluate_case(
        snapshot_cases["profile_memory_snapshot_user_analysis_result_contract"]
    )
    rows_result = evaluator.evaluate_case(
        snapshot_cases["profile_memory_snapshot_run_profile_rows_contract"]
    )

    assert event_result.artifacts["policy_source"] == "runtime"
    assert "profile_run_started" in event_result.artifacts["event_types"]
    assert "profile_node_started" in event_result.artifacts["event_types"]
    assert "profile_node_completed" in event_result.artifacts["event_types"]
    assert "profile_run_completed" in event_result.artifacts["event_types"]

    assert analysis_result.artifacts["policy_source"] == "adapter"
    assert analysis_result.artifacts["legacy_adapter_target"] == "user_analysis_result"
    assert analysis_result.artifacts["module_output_keys"] == [
        "app_profile",
        "behavior_profile",
        "credit_profile",
        "comprehensive_profile",
        "product_advice",
        "ops_advice",
    ]

    assert rows_result.artifacts["policy_source"] == "adapter"
    assert rows_result.artifacts["legacy_adapter_target"] == "run_profile_rows"
    assert rows_result.artifacts["row_modules"] == ["product"]
