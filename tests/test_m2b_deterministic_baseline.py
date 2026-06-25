from __future__ import annotations

import builtins
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_ASSETS_DIR = REPO_ROOT / "data_knowledge_eval" / "m2b" / "extracted_assets"
GOLDEN_SET_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "golden_set.yaml"


def test_deterministic_baseline_runs_in_isolated_db_without_data_agent_paths(tmp_path, monkeypatch) -> None:
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        write_yaml,
    )
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v1")
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v1",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.yaml",
    )
    seed_path = tmp_path / "m2b_legacy_v1.yaml"
    write_yaml(seed_path, seed_payload)

    blocked_imports = {
        "app.data_agent.service",
        "data_acquisition_agent.orchestrator",
    }
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked_imports:
            raise AssertionError(f"deterministic baseline must not import {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=seed_path,
        generated_at="deterministic-test",
    )

    assert payload["schema_version"] == "m2b_baseline_result_v1"
    assert payload["run_mode"] == "deterministic"
    assert payload["generated_at"] == "deterministic-test"
    assert "m2b_legacy_v1" in payload["seed_namespaces"]
    assert payload["seed_patch"].endswith("m2b_legacy_v1.yaml")
    assert payload["cases"]

    high_risk = next(case for case in payload["cases"] if case["case_id"] == "mx-high-risk-cohort")
    assert high_risk["retrieved_tables"]
    assert high_risk["retrieved_glossary_terms"]
    assert high_risk["judgment"] in {"pass", "partial", "fail"}
    assert isinstance(high_risk["matched_expected"], list)
    assert isinstance(high_risk["missing_expected"], list)
    assert isinstance(high_risk["notes"], list)


def test_deterministic_baseline_marks_manifest_only_assets_as_explained_missing(tmp_path) -> None:
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        write_yaml,
    )
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    manifest = build_promotion_manifest(assets, source_namespace="m2b_legacy_v1")
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace="m2b_legacy_v1",
        generated_from_manifest="data_knowledge_eval/m2b/seed_promotion_manifest.yaml",
    )
    seed_path = tmp_path / "m2b_legacy_v1.yaml"
    write_yaml(seed_path, seed_payload)

    payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=seed_path,
        generated_at="deterministic-test",
    )

    mob1_case = next(case for case in payload["cases"] if case["case_id"] == "mx-mob1-settled-7d-churn")
    assert any("not_runtime_imported_in_m2b_2" in note for note in mob1_case["notes"])
