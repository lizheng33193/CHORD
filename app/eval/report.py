"""Report writing for shared eval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.eval.schemas import EvalReport


@dataclass(frozen=True)
class ReportWriteResult:
    json_path: Path
    markdown_path: Path
    report: EvalReport


def write_report(report: EvalReport, output_dir: Path) -> ReportWriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report.run_id}.json"
    markdown_path = output_dir / f"{report.run_id}.md"
    final_report = report.model_copy(
        update={
            "artifact_paths": {
                **report.artifact_paths,
                "json": str(json_path),
                "markdown": str(markdown_path),
            }
        }
    )
    json_path.write_text(json.dumps(final_report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_markdown(final_report), encoding="utf-8")
    return ReportWriteResult(json_path=json_path, markdown_path=markdown_path, report=final_report)


def _build_markdown(report: EvalReport) -> str:
    lines = [
        "# Shared Eval Report",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Suite: `{report.suite_id or '-'}`",
        f"- Profile: `{report.profile_id or '-'}`",
        f"- Overall status: `{report.overall_status}`",
        f"- Runner status: `{report.runner_status}`",
        f"- Strict: `{report.strict}`",
        f"- Case file: `{report.case_file}`",
        f"- Selected suites: `{', '.join(report.selected_suites) if report.selected_suites else '-'}`",
        "",
        "## Summary",
        "",
        f"- Total cases: `{report.total_cases}`",
        f"- Passed cases: `{report.passed_cases}`",
        f"- Failed cases: `{report.failed_cases}`",
    ]
    if report.suite_summaries:
        lines.extend(["", "## Suite Summaries", ""])
        for summary in report.suite_summaries:
            lines.append(
                f"- `{summary.suite_id}` status=`{summary.status}` "
                f"passed=`{summary.passed_cases}/{summary.total_cases}` score=`{summary.score:.3f}`"
            )
            for metric_name, metric_value in summary.metrics.items():
                lines.append(f"  metric `{metric_name}`=`{metric_value}`")
    if report.failures:
        lines.extend(["", "## Runner Failures", ""])
        lines.extend(f"- {failure}" for failure in report.failures)
    if report.results:
        lines.extend(["", "## Case Results", ""])
    for result in report.results:
        lines.append(
            f"- `{result.case_id}` status=`{result.status}` passed=`{result.passed}`"
        )
        for failure in result.failures:
            lines.append(f"  failure: {failure}")
    return "\n".join(lines) + "\n"
