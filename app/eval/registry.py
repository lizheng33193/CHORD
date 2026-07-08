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
    ),
    "memory_governance": EvalSuite(
        suite_id="memory_governance",
        description="Contract-backed M4 memory governance regression coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "memory_governance.yaml"),
        evaluator="memory_governance",
        blocking=True,
        advisory=False,
    ),
    "data_agent_sql_safety": EvalSuite(
        suite_id="data_agent_sql_safety",
        description="Deterministic Data Agent SQL safety regression coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "data_agent_sql_safety.yaml"),
        evaluator="data_agent",
        blocking=True,
        advisory=False,
    ),
    "data_agent_sql_grounding": EvalSuite(
        suite_id="data_agent_sql_grounding",
        description="Deterministic Data Agent grounding and plan-review regression coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "data_agent_sql_grounding.yaml"),
        evaluator="data_agent",
        blocking=True,
        advisory=False,
    ),
    "risk_qa_groundedness": EvalSuite(
        suite_id="risk_qa_groundedness",
        description="Deterministic Risk QA groundedness regression coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "risk_qa_groundedness.yaml"),
        evaluator="risk_qa",
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
