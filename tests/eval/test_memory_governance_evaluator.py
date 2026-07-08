from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "eval_cases"


def test_memory_governance_suite_is_runtime_backed_and_passes_all_cases() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.memory import MemoryGovernanceEvaluator

    cases = load_eval_cases(FIXTURES / "memory_governance.yaml")
    evaluator = MemoryGovernanceEvaluator()
    results = [evaluator.evaluate_case(case) for case in cases]

    assert len(results) >= 14
    assert all(result.passed for result in results)
    assert all(result.artifacts["policy_source"] in {"runtime", "adapter"} for result in results)


def test_memory_governance_normalizes_reason_codes_and_preserves_raw_reason() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.memory import MemoryGovernanceEvaluator

    cases = {case.case_id: case for case in load_eval_cases(FIXTURES / "memory_governance.yaml")}
    result = MemoryGovernanceEvaluator().evaluate_case(cases["profile_result_blocked_for_data_grounding"])

    assert result.metrics["actual_decision"] == "blocked"
    assert result.metrics["actual_reason_code"] == "MEMORY_USE_FORBIDDEN"
    assert result.artifacts["raw_reason_code"] == "explicit_forbidden_use"
    assert result.artifacts["normalized_reason_code"] == "MEMORY_USE_FORBIDDEN"
    assert result.artifacts["policy_source"] == "runtime"


def test_memory_governance_retrieval_and_context_cases_exercise_runtime_seams() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.memory import MemoryGovernanceEvaluator

    cases = {case.case_id: case for case in load_eval_cases(FIXTURES / "memory_governance.yaml")}
    evaluator = MemoryGovernanceEvaluator()

    retrieval_result = evaluator.evaluate_case(cases["sql_grounding_rejects_unapproved_sql_case"])
    context_result = evaluator.evaluate_case(cases["context_rendering_preserves_provenance"])

    assert retrieval_result.metrics["check_kind"] == "retrieval_policy"
    assert retrieval_result.artifacts["raw_decision"] == "blocked"
    assert retrieval_result.artifacts["policy_source"] == "adapter"
    assert retrieval_result.artifacts["rejected_memory_ids"] == ["sql-draft-1"]

    assert context_result.metrics["check_kind"] == "context_rendering"
    assert context_result.artifacts["policy_source"] == "adapter"
    assert "source_type=user_preference" in context_result.artifacts["rendered_text"]
    assert "forbidden_memory_use" not in context_result.artifacts["rendered_text"]
