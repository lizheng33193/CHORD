"""CLI entrypoint for M2D-13 evaluation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.risk_knowledge.evaluation.evaluator import RiskKnowledgeGoldenEvaluator, build_fixture_executor
from app.risk_knowledge.evaluation.golden_set_loader import load_golden_cases
from app.risk_knowledge.evaluation.regression import decide_regression
from app.risk_knowledge.evaluation.report_builder import write_report
from app.risk_knowledge.evaluation.schemas import (
    EvaluationConfig,
    GoldenEvaluationReport,
    GoldenEvaluationSummary,
    RegressionDecision,
)
from app.risk_knowledge.service.risk_knowledge_service import build_risk_knowledge_service_from_settings
from app.risk_knowledge.service.schemas import RiskKnowledgeQuery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run M2D golden-set evaluation.")
    parser.add_argument("--golden-set", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["fixture", "runtime"], required=True)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    cases = load_golden_cases(Path(args.golden_set))
    config = EvaluationConfig(
        mode=args.mode,
        dataset_path=args.golden_set,
        output_dir=args.output_dir,
        report_only=True,
    )
    if args.mode == "runtime" and os.getenv("CHORD_RUN_M2D_RUNTIME_EVAL", "").strip() != "1":
        report = _build_skipped_report(config)
    else:
        evaluator = RiskKnowledgeGoldenEvaluator(
            executor=build_fixture_executor() if args.mode == "fixture" else _runtime_executor(),
            config=config,
        )
        report = evaluator.evaluate(cases)

    if not args.no_report:
        write_report(report, Path(args.output_dir))
    return 0


def _runtime_executor():
    service = build_risk_knowledge_service_from_settings()

    def _execute(case):
        return service.answer_with_trace(
            RiskKnowledgeQuery(
                query=case.query,
                kb_id=case.kb_id,
                document_id=case.document_id,
                version_id=case.version_id,
                intent=case.intent,
            )
        )

    return _execute


def _build_skipped_report(config: EvaluationConfig) -> GoldenEvaluationReport:
    summary = GoldenEvaluationSummary(status="skipped")
    decision = RegressionDecision(advisory=True, passed=True, failed_thresholds=[], summary="runtime evaluation skipped")
    return GoldenEvaluationReport(
        run_id="m2d_eval_skipped",
        created_at="1970-01-01T00:00:00Z",
        config=config,
        summary=summary,
        case_results=[],
        failures=[],
        regression_decision=decision,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
