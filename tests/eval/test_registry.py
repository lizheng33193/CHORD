from __future__ import annotations

from pathlib import Path


def test_registry_exposes_release_gate_smoke_suite() -> None:
    from app.eval.registry import get_suite

    suite = get_suite("release_gate_smoke")

    assert suite.suite_id == "release_gate_smoke"
    assert Path(suite.case_path).name == "release_gate_smoke.yaml"
    assert suite.evaluator == "release_gate_smoke"


def test_registry_exposes_memory_governance_suite() -> None:
    from app.eval.registry import get_suite

    suite = get_suite("memory_governance")

    assert suite.suite_id == "memory_governance"
    assert Path(suite.case_path).name == "memory_governance.yaml"
    assert suite.evaluator == "memory_governance"


def test_registry_exposes_data_agent_eval_suites() -> None:
    from app.eval.registry import get_suite

    safety_suite = get_suite("data_agent_sql_safety")
    grounding_suite = get_suite("data_agent_sql_grounding")

    assert safety_suite.suite_id == "data_agent_sql_safety"
    assert Path(safety_suite.case_path).name == "data_agent_sql_safety.yaml"
    assert safety_suite.evaluator == "data_agent"

    assert grounding_suite.suite_id == "data_agent_sql_grounding"
    assert Path(grounding_suite.case_path).name == "data_agent_sql_grounding.yaml"
    assert grounding_suite.evaluator == "data_agent"


def test_registry_exposes_risk_qa_groundedness_suite() -> None:
    from app.eval.registry import get_suite

    suite = get_suite("risk_qa_groundedness")

    assert suite.suite_id == "risk_qa_groundedness"
    assert Path(suite.case_path).name == "risk_qa_groundedness.yaml"
    assert suite.evaluator == "risk_qa"


def test_profiles_map_to_release_gate_smoke() -> None:
    from app.eval.profiles import get_profile

    pr_profile = get_profile("pr_acceptance")
    production_profile = get_profile("production_release")

    assert pr_profile.suites == [
        "release_gate_smoke",
        "memory_governance",
        "data_agent_sql_safety",
        "data_agent_sql_grounding",
        "risk_qa_groundedness",
    ]
    assert pr_profile.strict_by_default is False
    assert production_profile.suites == ["release_gate_smoke"]
    assert production_profile.strict_by_default is True
