from __future__ import annotations

import json


def test_cli_fixture_mode_writes_report_without_runtime_dependencies(tmp_path, sample_golden_path) -> None:
    from app.risk_knowledge.evaluation.cli import main

    exit_code = main(
        [
            "--golden-set",
            str(sample_golden_path),
            "--output-dir",
            str(tmp_path),
            "--mode",
            "fixture",
        ]
    )

    assert exit_code == 0
    json_reports = list(tmp_path.glob("*.json"))
    assert json_reports
    payload = json.loads(json_reports[0].read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "completed"


def test_cli_runtime_mode_without_opt_in_returns_skipped_report(tmp_path, sample_golden_path, monkeypatch) -> None:
    from app.risk_knowledge.evaluation.cli import main

    monkeypatch.delenv("CHORD_RUN_M2D_RUNTIME_EVAL", raising=False)

    exit_code = main(
        [
            "--golden-set",
            str(sample_golden_path),
            "--output-dir",
            str(tmp_path),
            "--mode",
            "runtime",
        ]
    )

    assert exit_code == 0
    payload = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "skipped"
