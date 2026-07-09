"""Profile registry for the shared eval foundation."""

from __future__ import annotations

from app.eval.schemas import EvalProfile


_PROFILES: dict[str, EvalProfile] = {
    "pr_acceptance": EvalProfile(
        profile_id="pr_acceptance",
        suites=[
            "release_gate_smoke",
            "memory_governance",
            "memory_semantic_retrieval",
            "data_agent_sql_safety",
            "data_agent_sql_grounding",
            "risk_qa_groundedness",
            "profile_dag_contract",
            "profile_memory_snapshot",
        ],
        description="PR acceptance profile over shared eval foundation, memory governance, Data Agent regression, Risk QA groundedness, and Profile DAG regression suites.",
        strict_by_default=False,
    ),
    "production_release": EvalProfile(
        profile_id="production_release",
        suites=[
            "release_gate_smoke",
            "memory_governance",
            "memory_semantic_retrieval",
            "data_agent_sql_safety",
            "data_agent_sql_grounding",
            "risk_qa_groundedness",
            "profile_dag_contract",
            "profile_memory_snapshot",
        ],
        description="Strict production-release profile over the full deterministic M5 shared eval regression gate.",
        strict_by_default=True,
    ),
}


def get_profile(profile_id: str) -> EvalProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise KeyError(f"unknown eval profile: {profile_id}") from exc


def list_profiles() -> list[EvalProfile]:
    return list(_PROFILES.values())
