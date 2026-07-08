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
