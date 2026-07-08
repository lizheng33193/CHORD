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
    "memory_semantic_retrieval": EvalSuite(
        suite_id="memory_semantic_retrieval",
        description="Hermetic M6B semantic retrieval and context injection regression coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "memory_semantic_retrieval.yaml"),
        evaluator="memory_semantic_retrieval",
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
    ),
    "profile_dag_contract": EvalSuite(
        suite_id="profile_dag_contract",
        description="Deterministic Profile DAG node registry, execution, degraded, and event contract coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "profile_dag_contract.yaml"),
        evaluator="profile",
        blocking=True,
        advisory=False,
    ),
    "profile_memory_snapshot": EvalSuite(
        suite_id="profile_memory_snapshot",
        description="Deterministic Profile DAG snapshot, legacy adapter, and profile-result memory boundary coverage.",
        case_path=str(REPO_ROOT / "tests" / "eval_cases" / "profile_memory_snapshot.yaml"),
        evaluator="profile",
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
