"""Suite registry for the shared eval foundation."""

from __future__ import annotations

from pathlib import Path

from app.eval.schemas import EvalSuite


REPO_ROOT = Path(__file__).resolve().parents[2]

_SUITES: dict[str, EvalSuite] = {
    "release_gate_smoke": EvalSuite(
        suite_id="release_gate_smoke",
        description="Smoke coverage for release-gate status semantics.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "release_gate_smoke.yaml"),
        evaluator="release_gate_smoke",
        blocking=True,
        advisory=False,
    )
}


def get_suite(suite_id: str) -> EvalSuite:
    try:
        return _SUITES[suite_id]
    except KeyError as exc:
        raise KeyError(f"unknown eval suite: {suite_id}") from exc


def list_suites() -> list[EvalSuite]:
    return list(_SUITES.values())
