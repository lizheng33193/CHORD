from __future__ import annotations

import inspect


def test_evaluator_computes_case_results_and_skips_ambiguous_threshold_denominator() -> None:
    from app.risk_knowledge.evaluation.evaluator import RiskKnowledgeGoldenEvaluator
    from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase
    from tests.risk_knowledge.evaluation.conftest import build_answer_trace

    cases = [
        GoldenEvaluationCase(
            case_id="answer_case",
            query="什么是多头借贷风险？",
            kb_id="risk_domain_knowledge",
            expected_behavior="answer",
            expected_evidence=[{"chunk_id": "risk_chunk_001", "text_contains": ["多个平台"]}],
            expected_answer_points=["多个平台"],
            expected_citation_refs=[{"chunk_id": "risk_chunk_001"}],
            tags=[],
            difficulty="easy",
        ),
        GoldenEvaluationCase(
            case_id="ambiguous_case",
            query="这个风险高吗？",
            kb_id="risk_domain_knowledge",
            expected_behavior="ambiguous",
            expected_evidence=[],
            expected_answer_points=[],
            expected_citation_refs=[],
            tags=[],
            difficulty="hard",
        ),
    ]

    traces = {
        "answer_case": build_answer_trace(),
        "ambiguous_case": build_answer_trace(should_answer=False),
    }

    evaluator = RiskKnowledgeGoldenEvaluator(executor=lambda case: traces[case.case_id])
    report = evaluator.evaluate(cases)

    assert report.summary.total_cases == 2
    assert report.summary.ambiguous_cases == 1
    assert report.case_results[1].passed is None
    assert report.summary.gate_accuracy == 1.0


def test_app_evaluation_package_does_not_import_tests_golden() -> None:
    import app.risk_knowledge.evaluation.evaluator as evaluator_module

    assert "tests.golden" not in inspect.getsource(evaluator_module)
