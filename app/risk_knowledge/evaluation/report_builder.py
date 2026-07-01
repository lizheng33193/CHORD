"""Report builder for M2D-13."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.risk_knowledge.evaluation.errors import GoldenEvaluationReportError
from app.risk_knowledge.evaluation.schemas import GoldenEvaluationReport


@dataclass(frozen=True)
class ReportPaths:
    json_path: Path
    markdown_path: Path


def write_report(report: GoldenEvaluationReport, output_dir: Path) -> ReportPaths:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"{report.run_id}.json"
        markdown_path = output_dir / f"{report.run_id}.md"
        json_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        markdown_path.write_text(_build_markdown(report), encoding="utf-8")
        return ReportPaths(json_path=json_path, markdown_path=markdown_path)
    except OSError as exc:  # pragma: no cover - filesystem failure path
        raise GoldenEvaluationReportError(str(exc)) from exc


def _build_markdown(report: GoldenEvaluationReport) -> str:
    summary = report.summary
    lines = [
        "# M2D Golden Evaluation Report",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: `{summary.status}`",
        f"- Mode: `{report.config.mode}`",
        f"- Dataset: `{report.config.dataset_path}`",
        f"- Advisory regression: `{report.regression_decision.summary}`",
        "",
        "## Summary",
        "",
        f"- Total cases: `{summary.total_cases}`",
        f"- Answer cases: `{summary.answer_cases}`",
        f"- Refusal cases: `{summary.refusal_cases}`",
        f"- Ambiguous cases: `{summary.ambiguous_cases}`",
        f"- Retrieval recall@5: `{summary.retrieval_recall_at_5:.3f}`",
        f"- Gate accuracy: `{summary.gate_accuracy:.3f}`",
        f"- Citation correctness: `{summary.citation_correctness:.3f}`",
        f"- Answer point recall: `{summary.answer_point_recall:.3f}`",
        "",
        "> `answer_point_recall` in v1 is deterministic lexical matching, not a semantic groundedness judge.",
    ]
    return "\n".join(lines) + "\n"
