from __future__ import annotations

import builtins
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTRACTED_ASSETS_DIR = REPO_ROOT / "data_knowledge_eval" / "m2b" / "extracted_assets"
GOLDEN_SET_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "golden_set.yaml"


def _build_seed_payload(*, tmp_path: Path, namespace: str):
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
        build_seed_patch_payload,
        load_candidate_assets,
        write_yaml,
    )

    assets = load_candidate_assets(EXTRACTED_ASSETS_DIR)
    if namespace == "m2b_legacy_v1":
        manifest_name = "seed_promotion_manifest.yaml"
    elif namespace == "m2b_legacy_v2":
        manifest_name = "seed_promotion_manifest.v2.yaml"
    else:
        manifest_name = "seed_promotion_manifest.v3.yaml"
    manifest = build_promotion_manifest(assets, source_namespace=namespace)
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace=namespace,
        generated_from_manifest=f"data_knowledge_eval/m2b/{manifest_name}",
    )
    seed_path = tmp_path / f"{namespace}.yaml"
    write_yaml(seed_path, seed_payload)
    return seed_path


def test_deterministic_baseline_runs_in_isolated_db_without_data_agent_paths(tmp_path, monkeypatch) -> None:
    from scripts.promote_m2b_extracted_assets import (
        build_promotion_manifest,
    )
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    seed_path = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v1")

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
    assert len(high_risk["retrieved_tables"]) == len(set(high_risk["retrieved_tables"]))


def test_deterministic_baseline_marks_manifest_only_assets_as_explained_missing(tmp_path) -> None:
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    seed_path = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v1")

    payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=seed_path,
        generated_at="deterministic-test",
    )

    mob1_case = next(case for case in payload["cases"] if case["case_id"] == "mx-mob1-settled-7d-churn")
    assert any("not_runtime_imported_in_m2b_2" in note for note in mob1_case["notes"])


def test_deterministic_baseline_supports_seed_patch_switching_and_v2_improves_credit_case(tmp_path) -> None:
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    v1_seed = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v1")
    v2_seed = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v2")

    v1_payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=v1_seed,
        generated_at="deterministic-v1",
    )
    v2_payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=v2_seed,
        generated_at="deterministic-v2",
    )

    assert v1_payload["seed_patch"].endswith("m2b_legacy_v1.yaml")
    assert v2_payload["seed_patch"].endswith("m2b_legacy_v2.yaml")
    assert "m2b_legacy_v2" in v2_payload["seed_namespaces"]

    v1_case = next(case for case in v1_payload["cases"] if case["case_id"] == "mx-credit-profile-query")
    v2_case = next(case for case in v2_payload["cases"] if case["case_id"] == "mx-credit-profile-query")

    assert v1_case["judgment"] == "fail"
    assert v2_case["judgment"] in {"partial", "pass"}
    assert "table:hive.dwb.dwb_r_apply" in v2_case["matched_expected"]
    assert "glossary:credit_profile" in v2_case["matched_expected"]


def test_deterministic_baseline_supports_v3_seed_and_shrinks_mob1_and_overdue_gaps(tmp_path) -> None:
    from scripts.run_m2b_retrieval_baseline import build_deterministic_results

    v2_seed = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v2")
    v3_seed = _build_seed_payload(tmp_path=tmp_path, namespace="m2b_legacy_v3")

    v2_payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=v2_seed,
        generated_at="deterministic-v2",
    )
    v3_payload = build_deterministic_results(
        golden_set_path=GOLDEN_SET_PATH,
        seed_patch_path=v3_seed,
        generated_at="deterministic-v3",
    )

    v2_mob1 = next(case for case in v2_payload["cases"] if case["case_id"] == "mx-mob1-settled-7d-churn")
    v3_mob1 = next(case for case in v3_payload["cases"] if case["case_id"] == "mx-mob1-settled-7d-churn")
    assert len(v3_mob1["missing_expected"]) < len(v2_mob1["missing_expected"])
    assert "glossary:mob1" in v3_mob1["matched_expected"]
    assert "glossary:fully_settled" in v3_mob1["matched_expected"]
    assert "glossary:seven_day_no_reborrow_churn" in v3_mob1["matched_expected"]

    v2_withdraw = next(case for case in v2_payload["cases"] if case["case_id"] == "mx-withdraw-cohort")
    v3_withdraw = next(case for case in v3_payload["cases"] if case["case_id"] == "mx-withdraw-cohort")
    assert len(v3_withdraw["missing_expected"]) < len(v2_withdraw["missing_expected"])
    assert "field:withdraw_uuid" in v3_withdraw["matched_expected"]
    assert "field:asset_grant_at" in v3_withdraw["matched_expected"]


def test_build_baseline_comparison_marks_v2_to_v3_improvements() -> None:
    from scripts.run_m2b_retrieval_baseline import build_baseline_comparison_markdown

    comparison = build_baseline_comparison_markdown(
        {
            "seed_namespaces": ["mx", "ph", "common", "m2b_legacy_v2"],
            "cases": [
                {
                    "case_id": "mx-mob1-settled-7d-churn",
                    "judgment": "partial",
                    "matched_expected": ["table:hive.dwd.dwd_w_apply"],
                    "missing_expected": ["glossary:mob1", "field:withdraw_uuid"],
                    "unexpected": [],
                }
            ]
        },
        {
            "seed_namespaces": ["mx", "ph", "common", "m2b_legacy_v3"],
            "cases": [
                {
                    "case_id": "mx-mob1-settled-7d-churn",
                    "judgment": "pass",
                    "matched_expected": ["table:hive.dwd.dwd_w_apply", "glossary:mob1", "field:withdraw_uuid"],
                    "missing_expected": [],
                    "unexpected": [],
                }
            ]
        },
    )

    assert "M2B-2.2 V2 vs V3" in comparison
    assert "mx-mob1-settled-7d-churn" in comparison
    assert "m2b_legacy_v2" in comparison
    assert "m2b_legacy_v3" in comparison
    assert "partial" in comparison
    assert "pass" in comparison
    assert "improved" in comparison

    regression = build_baseline_comparison_markdown(
        {
            "seed_namespaces": ["mx", "ph", "common", "m2b_legacy_v2"],
            "cases": [
                {
                    "case_id": "mx-credit-profile-query",
                    "judgment": "pass",
                    "matched_expected": ["table:hive.dwb.dwb_r_apply", "field:apply_id"],
                    "missing_expected": [],
                    "unexpected": [],
                }
            ],
        },
        {
            "seed_namespaces": ["mx", "ph", "common", "m2b_legacy_v3"],
            "cases": [
                {
                    "case_id": "mx-credit-profile-query",
                    "judgment": "partial",
                    "matched_expected": ["table:hive.dwb.dwb_r_apply"],
                    "missing_expected": ["field:apply_id"],
                    "unexpected": [],
                }
            ],
        },
    )
    assert "regressed" in regression
