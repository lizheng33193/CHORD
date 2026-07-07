from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_eval_case_defaults_are_applied() -> None:
    from app.eval.schemas import EvalCase

    case = EvalCase(
        case_id="case-1",
        suite="release_gate_smoke",
        task_type="release_gate_smoke",
        input={"profile": "pr_acceptance"},
        expected={"status": "WARN", "exit_code": 0},
    )

    assert case.tags == []
    assert case.severity == "major"
    assert case.source == "manual"
    assert case.metadata == {}


def test_eval_result_rejects_unknown_status() -> None:
    from app.eval.schemas import EvalResult

    with pytest.raises(ValidationError):
        EvalResult(
            case_id="case-1",
            suite="release_gate_smoke",
            status="UNKNOWN",
            passed=True,
        )


def test_eval_profile_requires_at_least_one_suite() -> None:
    from app.eval.schemas import EvalProfile

    with pytest.raises(ValidationError):
        EvalProfile(profile_id="empty", suites=[])
