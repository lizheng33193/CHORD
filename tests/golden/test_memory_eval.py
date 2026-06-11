from __future__ import annotations

from pathlib import Path

import pytest

from tests.golden.memory_eval import DEFAULT_DATASET, run_eval


@pytest.mark.timeout(3)
def test_memory_eval_runner_passes_with_temp_sqlite(tmp_path):
    result = run_eval(
        dataset_path=DEFAULT_DATASET,
        db_path=tmp_path / "memory.sqlite3",
        report_dir=tmp_path / "reports",
    )
    assert result["passed"] is True
    assert result["metrics"]["policy_accuracy"] == 1.0
    assert result["metrics"]["no_leak_rate"] == 1.0
    assert result["metrics"]["redaction_pass_rate"] == 1.0
    assert result["metrics"]["management_pass_rate"] == 1.0
    assert result["metrics"]["recall_at_8"] >= 0.9
    assert Path(result["report_path"]).exists()
