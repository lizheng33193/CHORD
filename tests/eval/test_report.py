from __future__ import annotations


def test_report_writer_persists_json_and_markdown_with_failure_reasons(tmp_path) -> None:
    from app.eval.report import write_report
    from app.eval.schemas import EvalReport, EvalResult, EvalSuiteSummary

    report = EvalReport(
        run_id="eval_test",
        created_at="2026-07-07T00:00:00Z",
        suite_id="release_gate_smoke",
        profile_id=None,
        selected_suites=["release_gate_smoke"],
        case_file="memory://inline",
        strict=False,
        overall_status="WARN",
        runner_status="completed",
        total_cases=1,
        passed_cases=0,
        failed_cases=1,
        status_counts={"WARN": 1},
        suite_summaries=[
            EvalSuiteSummary(
                suite_id="release_gate_smoke",
                status="WARN",
                total_cases=1,
                passed_cases=0,
                failed_cases=1,
                score=0.0,
                metrics={"smoke_pass_rate": 0.0},
            )
        ],
        suite_metrics={"release_gate_smoke": {"smoke_pass_rate": 0.0}},
        results=[
            EvalResult(
                case_id="case-1",
                suite="release_gate_smoke",
                status="WARN",
                passed=False,
                failures=["expected PASS but got WARN"],
            )
        ],
    )

    written = write_report(report, tmp_path)

    assert written.json_path.exists()
    assert written.markdown_path.exists()
    payload = written.report.model_dump(mode="json")
    assert payload["selected_suites"] == ["release_gate_smoke"]
    assert payload["suite_metrics"]["release_gate_smoke"]["smoke_pass_rate"] == 0.0
    assert "expected PASS but got WARN" in written.markdown_path.read_text(encoding="utf-8")


def test_report_writer_serializes_risk_qa_suite_metrics(tmp_path) -> None:
    from app.eval.report import write_report
    from app.eval.schemas import EvalReport, EvalResult, EvalSuiteSummary

    report = EvalReport(
        run_id="risk_qa_eval_test",
        created_at="2026-07-08T00:00:00Z",
        suite_id=None,
        profile_id="pr_acceptance",
        selected_suites=["risk_qa_groundedness"],
        case_file="memory://risk_qa",
        strict=False,
        overall_status="PASS",
        runner_status="completed",
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        status_counts={"PASS": 1},
        suite_summaries=[
            EvalSuiteSummary(
                suite_id="risk_qa_groundedness",
                status="PASS",
                total_cases=1,
                passed_cases=1,
                failed_cases=0,
                score=1.0,
                metrics={
                    "risk_qa_groundedness_pass_rate": 1.0,
                    "citation_validity_rate": 1.0,
                },
            )
        ],
        suite_metrics={
            "risk_qa_groundedness": {
                "risk_qa_groundedness_pass_rate": 1.0,
                "citation_validity_rate": 1.0,
            }
        },
        results=[
            EvalResult(
                case_id="risk_qa_case_1",
                suite="risk_qa_groundedness",
                status="PASS",
                passed=True,
                warnings=["citation metadata warning preserved"],
                failures=[],
            )
        ],
    )

    written = write_report(report, tmp_path)

    payload = written.report.model_dump(mode="json")
    markdown = written.markdown_path.read_text(encoding="utf-8")
    assert payload["suite_metrics"]["risk_qa_groundedness"]["citation_validity_rate"] == 1.0
    assert "risk_qa_groundedness_pass_rate" in markdown
    assert "warning: citation metadata warning preserved" in markdown
