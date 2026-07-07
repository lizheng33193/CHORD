from __future__ import annotations

from pathlib import Path


def test_registry_exposes_release_gate_smoke_suite() -> None:
    from app.eval.registry import get_suite

    suite = get_suite("release_gate_smoke")

    assert suite.suite_id == "release_gate_smoke"
    assert Path(suite.case_path).name == "release_gate_smoke.yaml"
    assert suite.evaluator == "release_gate_smoke"


def test_profiles_map_to_release_gate_smoke() -> None:
    from app.eval.profiles import get_profile

    pr_profile = get_profile("pr_acceptance")
    production_profile = get_profile("production_release")

    assert pr_profile.suites == ["release_gate_smoke"]
    assert pr_profile.strict_by_default is False
    assert production_profile.suites == ["release_gate_smoke"]
    assert production_profile.strict_by_default is True
