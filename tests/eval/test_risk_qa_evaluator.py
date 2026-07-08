from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "eval_cases"


def test_risk_qa_groundedness_suite_is_adapter_or_runtime_backed_and_passes_cases() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.risk_qa import RiskQAEvaluator

    cases = load_eval_cases(FIXTURES / "risk_qa_groundedness.yaml")
    evaluator = RiskQAEvaluator()
    results = [evaluator.evaluate_case(case) for case in cases]

    assert len(results) >= 14
    assert all(result.passed for result in results)
    assert all(result.artifacts["policy_source"] in {"runtime", "adapter"} for result in results)


def test_risk_qa_groundedness_preserves_raw_codes_and_normalizes_report_codes() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.risk_qa import RiskQAEvaluator

    cases = {case.case_id: case for case in load_eval_cases(FIXTURES / "risk_qa_groundedness.yaml")}
    evaluator = RiskQAEvaluator()

    invalid_citation = evaluator.evaluate_case(cases["risk_qa_invalid_citation_chunk_blocked"])
    metadata_warning = evaluator.evaluate_case(cases["risk_qa_citation_missing_metadata_warning"])

    assert invalid_citation.metrics["actual_decision"] == "blocked"
    assert invalid_citation.artifacts["raw_failures"] == ["RISK_QA_CITATION_NOT_IN_SELECTED_EVIDENCE"]
    assert invalid_citation.artifacts["normalized_failures"] == ["RISK_QA_CITATION_INVALID"]

    assert metadata_warning.metrics["actual_decision"] == "warning"
    assert metadata_warning.artifacts["raw_warnings"] == ["RISK_QA_CITATION_PAGE_MISSING"]
    assert metadata_warning.artifacts["normalized_warnings"] == ["RISK_QA_CITATION_METADATA_INCOMPLETE"]


def test_risk_qa_groundedness_source_boundary_cases_preserve_raw_labels_and_mapped_types() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.risk_qa import RiskQAEvaluator

    cases = {case.case_id: case for case in load_eval_cases(FIXTURES / "risk_qa_groundedness.yaml")}
    evaluator = RiskQAEvaluator()

    history_result = evaluator.evaluate_case(cases["risk_qa_history_not_source_document"])
    leakage_result = evaluator.evaluate_case(cases["risk_qa_data_knowledge_sql_example_leakage_blocked"])

    assert history_result.artifacts["policy_source"] == "runtime"
    assert history_result.artifacts["raw_source_labels"] == ["risk_qa_answer"]
    assert history_result.artifacts["mapped_source_types"] == ["memory_as_authority"]
    assert history_result.artifacts["normalized_failures"] == ["RISK_QA_HISTORY_NOT_SOURCE_DOCUMENT"]

    assert leakage_result.artifacts["raw_source_labels"] == ["data_sql_example"]
    assert leakage_result.artifacts["mapped_source_types"] == ["sql_examples"]
    assert leakage_result.artifacts["normalized_failures"] == ["RISK_QA_DATA_KNOWLEDGE_LEAKAGE"]
