from __future__ import annotations

import json
import subprocess
import sys


def test_release_gate_warns_for_missing_full_regression_in_pr_acceptance_mode(tmp_path) -> None:
    from app.release.pre_m3_gate import build_release_gate_report
    from app.release.schemas import ReleaseGateCheckResult

    report = build_release_gate_report(
        profile="pr_acceptance",
        checks=[
            ReleaseGateCheckResult(
                check_name="full_repo_regression",
                category="test_coverage",
                status="NOT_RUN",
                summary="full repository regression not run",
                blocking=False,
                details={},
            )
        ],
    )

    assert report.release_gate_status == "WARN"
    assert report.failed_checks == []
    assert "full repository regression not run" in report.warnings[0]


def test_release_gate_blocks_for_missing_full_regression_in_production_mode(tmp_path) -> None:
    from app.release.pre_m3_gate import build_release_gate_report
    from app.release.schemas import ReleaseGateCheckResult

    report = build_release_gate_report(
        profile="production_release",
        checks=[
            ReleaseGateCheckResult(
                check_name="full_repo_regression",
                category="test_coverage",
                status="NOT_RUN",
                summary="full repository regression not run",
                blocking=False,
                details={},
            )
        ],
    )

    assert report.release_gate_status == "BLOCKED"
    assert report.failed_checks == ["full_repo_regression"]


def test_release_gate_cli_writes_structured_report(tmp_path) -> None:
    from app.release.pre_m3_gate import main

    output_path = tmp_path / "pre_m3_gate.json"
    exit_code = main(
        ["--profile", "pr_acceptance", "--output-json", str(output_path)],
        check_runner=lambda _profile: [],
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["release_gate_status"] == "PASS"
    assert payload["checks"] == []


def test_release_gate_default_runner_marks_full_regression_not_run_as_warn() -> None:
    from app.release.pre_m3_gate import default_check_runner, build_release_gate_report

    report = build_release_gate_report(
        profile="pr_acceptance",
        checks=default_check_runner("pr_acceptance"),
    )

    assert report.release_gate_status == "WARN"
    assert report.failed_checks == []
    assert any("full repository regression not run" in item for item in report.warnings)


def test_release_gate_module_entrypoint_runs_without_runtime_warning(tmp_path) -> None:
    output_path = tmp_path / "pre_m3_gate.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.release.pre_m3_gate",
            "--profile",
            "pr_acceptance",
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "RuntimeWarning" not in proc.stderr

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["release_gate_status"] == "WARN"
