from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


def test_status_to_exit_code_matrix() -> None:
    from app.eval.runner import eval_status_to_exit_code

    assert eval_status_to_exit_code("PASS", strict=False) == 0
    assert eval_status_to_exit_code("WARN", strict=False) == 0
    assert eval_status_to_exit_code("WARN", strict=True) == 1
    assert eval_status_to_exit_code("FAIL", strict=False) == 1
    assert eval_status_to_exit_code("BLOCKED", strict=True) == 1


def test_runner_returns_zero_for_default_suite_cases(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "release_gate_smoke",
            "--case-file",
            str(FIXTURES / "sample_cases.yaml"),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_pr_profile(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--profile",
            "pr_acceptance",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_memory_governance_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "memory_governance",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_data_agent_sql_safety_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "data_agent_sql_safety",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_data_agent_sql_grounding_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "data_agent_sql_grounding",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_risk_qa_groundedness_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "risk_qa_groundedness",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_profile_dag_contract_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "profile_dag_contract",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_profile_memory_snapshot_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "profile_memory_snapshot",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_zero_for_production_profile_strict(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--profile",
            "production_release",
            "--strict",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0


def test_runner_returns_one_for_blocked_matrix_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "release_gate_smoke",
            "--strict",
            "--case-file",
            str(FIXTURES / "release_gate_smoke_status_matrix.yaml"),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 1


def test_runner_returns_two_for_missing_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(["--suite", "missing_suite", "--output-dir", str(tmp_path)])

    assert exit_code == 2


def test_runner_profile_report_includes_multi_suite_summary(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--profile",
            "pr_acceptance",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    report_paths = list(tmp_path.glob("shared_eval_*.json"))
    assert report_paths
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert payload["selected_suites"] == [
        "release_gate_smoke",
        "memory_governance",
        "data_agent_sql_safety",
        "data_agent_sql_grounding",
        "risk_qa_groundedness",
        "profile_dag_contract",
        "profile_memory_snapshot",
    ]
    assert {item["suite_id"] for item in payload["suite_summaries"]} == {
        "release_gate_smoke",
        "memory_governance",
        "data_agent_sql_safety",
        "data_agent_sql_grounding",
        "risk_qa_groundedness",
        "profile_dag_contract",
        "profile_memory_snapshot",
    }
    assert "memory_governance" in payload["suite_metrics"]
    assert "memory_governance_pass_rate" in payload["suite_metrics"]["memory_governance"]
    assert "data_agent_sql_safety" in payload["suite_metrics"]
    assert "data_agent_sql_safety_pass_rate" in payload["suite_metrics"]["data_agent_sql_safety"]
    assert "data_agent_sql_grounding" in payload["suite_metrics"]
    assert "data_agent_sql_grounding_pass_rate" in payload["suite_metrics"]["data_agent_sql_grounding"]
    assert "risk_qa_groundedness" in payload["suite_metrics"]
    assert "risk_qa_groundedness_pass_rate" in payload["suite_metrics"]["risk_qa_groundedness"]
    assert "profile_dag_contract" in payload["suite_metrics"]
    assert "profile_dag_contract_pass_rate" in payload["suite_metrics"]["profile_dag_contract"]
    assert "profile_memory_snapshot" in payload["suite_metrics"]
    assert "profile_memory_snapshot_pass_rate" in payload["suite_metrics"]["profile_memory_snapshot"]


def test_runner_returns_two_for_malformed_case_file(tmp_path) -> None:
    from app.eval.runner import main

    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text("cases:\n  - case_id: only_id\n", encoding="utf-8")

    exit_code = main(
        [
            "--suite",
            "release_gate_smoke",
            "--case-file",
            str(broken_path),
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 2


def test_runner_returns_two_for_evaluator_crash(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.eval import runner as eval_runner

    class CrashingEvaluator:
        def evaluate_case(self, case):  # pragma: no cover - executed in runner
            raise RuntimeError("boom")

    monkeypatch.setattr(eval_runner, "build_evaluator", lambda _name: CrashingEvaluator())

    exit_code = eval_runner.main(
        [
            "--suite",
            "release_gate_smoke",
            "--case-file",
            str(FIXTURES / "sample_cases.yaml"),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 2


def test_runner_module_entrypoint_runs_without_runtime_warning(tmp_path) -> None:
    output_dir = tmp_path / "reports"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.eval.runner",
            "--suite",
            "release_gate_smoke",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "RuntimeWarning" not in proc.stderr

    report_paths = list(output_dir.glob("shared_eval_*.json"))
    assert report_paths
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert payload["overall_status"] == "WARN"
