"""Fixed node registry for the first Profile DAG runtime."""

from __future__ import annotations

from app.services.profile_dag.contracts import ProfileNodeSpec


PROFILE_NODE_SPECS: tuple[ProfileNodeSpec, ...] = (
    ProfileNodeSpec(
        node_key="app",
        module="app",
        skill_name="app_profile",
        result_key="app_profile",
        label="App 画像",
        stage=0,
        depends_on=[],
    ),
    ProfileNodeSpec(
        node_key="behavior",
        module="behavior",
        skill_name="behavior_profile",
        result_key="behavior_profile",
        label="行为画像",
        stage=0,
        depends_on=[],
    ),
    ProfileNodeSpec(
        node_key="credit",
        module="credit",
        skill_name="credit_profile",
        result_key="credit_profile",
        label="征信画像",
        stage=0,
        depends_on=[],
    ),
    ProfileNodeSpec(
        node_key="comprehensive",
        module="comprehensive",
        skill_name="comprehensive_profile",
        result_key="comprehensive_profile",
        label="综合画像",
        stage=1,
        depends_on=["app", "behavior", "credit"],
    ),
    ProfileNodeSpec(
        node_key="product",
        module="product",
        skill_name="product_advice",
        result_key="product_advice",
        label="产品策略",
        stage=2,
        depends_on=["comprehensive"],
    ),
    ProfileNodeSpec(
        node_key="ops",
        module="ops",
        skill_name="ops_advice",
        result_key="ops_advice",
        label="运营策略",
        stage=2,
        depends_on=["comprehensive"],
    ),
)

NODE_KEY_TO_SPEC = {spec.node_key: spec for spec in PROFILE_NODE_SPECS}
SKILL_NAME_TO_SPEC = {spec.skill_name: spec for spec in PROFILE_NODE_SPECS}
RESULT_KEY_TO_SPEC = {spec.result_key: spec for spec in PROFILE_NODE_SPECS}


def resolve_execution_closure(requested_modules: list[str]) -> set[str]:
    requested = {module for module in requested_modules if module in NODE_KEY_TO_SPEC}
    closure: set[str] = set()

    def _add(node_key: str) -> None:
        if node_key in closure:
            return
        spec = NODE_KEY_TO_SPEC[node_key]
        for dep in spec.depends_on:
            _add(dep)
        closure.add(node_key)

    for node_key in requested:
        _add(node_key)
    return closure

