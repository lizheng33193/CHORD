from __future__ import annotations

import json


def test_report_builder_writes_json_and_markdown(tmp_path) -> None:
    from app.risk_knowledge.evaluation.report_builder import write_report
    from app.risk_knowledge.evaluation.schemas import (
        EvaluationConfig,
        GoldenEvaluationReport,
        GoldenEvaluationSummary,
        RegressionDecision,
    )

    report = GoldenEvaluationReport(
        run_id="m2d-eval-test",
        created_at="2026-07-01T00:00:00Z",
        config=EvaluationConfig(mode="fixture", dataset_path="tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl"),
        summary=GoldenEvaluationSummary(
            status="completed",
            total_cases=1,
            answer_cases=1,
            refusal_cases=0,
            ambiguous_cases=0,
            retrieval_recall_at_5=1.0,
            retrieval_recall_at_10=1.0,
            retrieval_mrr=1.0,
            rerank_hit_at_3=1.0,
            evidence_precision=1.0,
            evidence_recall=1.0,
            gate_accuracy=1.0,
            refusal_accuracy=1.0,
            false_answer_rate=0.0,
            false_refusal_rate=0.0,
            citation_correctness=1.0,
            answer_point_recall=1.0,
        ),
        case_results=[],
        failures=[],
        regression_decision=RegressionDecision(advisory=True, passed=True, failed_thresholds=[], summary="ok"),
    )

    paths = write_report(report, tmp_path)

    assert paths.json_path.exists()
    assert paths.markdown_path.exists()
    assert json.loads(paths.json_path.read_text(encoding="utf-8"))["run_id"] == "m2d-eval-test"
    assert "M2D Golden Evaluation Report" in paths.markdown_path.read_text(encoding="utf-8")
