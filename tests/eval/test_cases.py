from __future__ import annotations

from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_cases_supports_yaml() -> None:
    from app.eval.cases import load_eval_cases

    cases = load_eval_cases(FIXTURES / "sample_cases.yaml")

    assert [case.case_id for case in cases] == ["yaml_warn_case"]
    assert cases[0].expected["status"] == "WARN"


def test_load_cases_supports_json() -> None:
    from app.eval.cases import load_eval_cases

    cases = load_eval_cases(FIXTURES / "sample_cases.json")

    assert [case.case_id for case in cases] == ["json_pass_case"]
    assert cases[0].input["full_regression_status"] == "passed"


def test_load_cases_rejects_malformed_payload(tmp_path) -> None:
    from app.eval.cases import EvalCaseLoadError, load_eval_cases

    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text("cases:\n  - case_id: missing_fields_only\n", encoding="utf-8")

    with pytest.raises(EvalCaseLoadError):
        load_eval_cases(broken_path)
