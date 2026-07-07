from __future__ import annotations


def test_report_writer_persists_json_and_markdown_with_failure_reasons(tmp_path) -> None:
    from app.eval.report import write_report
    from app.eval.schemas import EvalReport, EvalResult

    report = EvalReport(
        run_id="eval_test",
        created_at="2026-07-07T00:00:00Z",
        suite_id="release_gate_smoke",
        profile_id=None,
        case_file="memory://inline",
        strict=False,
        overall_status="WARN",
        runner_status="completed",
        total_cases=1,
        passed_cases=0,
        failed_cases=1,
        status_counts={"WARN": 1},
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
    assert "expected PASS but got WARN" in written.markdown_path.read_text(encoding="utf-8")
