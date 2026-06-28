from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "golden_set.yaml"
DETERMINISTIC_BASELINE_PATH = (
    REPO_ROOT / "data_knowledge_eval" / "m2b" / "baseline_results.m2b_legacy_v3.deterministic.json"
)
VECTOR_BASELINE_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "vector_results.m2b_legacy_v3.json"
VECTOR_COVERAGE_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "vector_coverage.m2b_legacy_v3.yaml"


def test_hybrid_baseline_fails_fast_when_required_inputs_are_missing(tmp_path: Path) -> None:
    from scripts.run_m2b_hybrid_baseline import build_hybrid_baseline_artifacts

    missing_vector = tmp_path / "missing-vector.json"
    with pytest.raises(FileNotFoundError, match="vector baseline"):
        build_hybrid_baseline_artifacts(
            golden_set_path=GOLDEN_SET_PATH,
            deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
            vector_baseline_path=missing_vector,
            vector_coverage_path=VECTOR_COVERAGE_PATH,
            generated_at="2026-06-28T00:00:00Z",
        )


def test_hybrid_baseline_generates_manifest_results_and_comparison(tmp_path: Path) -> None:
    from scripts.run_m2b_hybrid_baseline import build_hybrid_baseline_artifacts, write_hybrid_outputs

    artifacts = build_hybrid_baseline_artifacts(
        golden_set_path=GOLDEN_SET_PATH,
        deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
        vector_baseline_path=VECTOR_BASELINE_PATH,
        vector_coverage_path=VECTOR_COVERAGE_PATH,
        generated_at="2026-06-28T00:00:00Z",
    )

    output_path = tmp_path / "hybrid_results.json"
    coverage_path = tmp_path / "hybrid_coverage.yaml"
    manifest_path = tmp_path / "hybrid_manifest.yaml"
    comparison_path = tmp_path / "hybrid_comparison.md"
    write_hybrid_outputs(
        artifacts=artifacts,
        output_path=output_path,
        coverage_path=coverage_path,
        manifest_path=manifest_path,
        comparison_path=comparison_path,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "m2b_hybrid_baseline_v1"
    assert payload["run_mode"] == "hybrid_prototype"
    assert payload["fusion_strategy"] == "primary_merge_v1"
    assert payload["generated_at"] == "2026-06-28T00:00:00Z"
    assert payload["cases"]

    manifest = artifacts.manifest_payload
    assert manifest["schema_version"] == "m2b_hybrid_manifest_v1"
    assert manifest["fusion_strategy"] == "primary_merge_v1"
    assert set(manifest["input_hashes"].keys()) == {
        "deterministic_baseline_sha256",
        "vector_baseline_sha256",
        "golden_set_sha256",
    }

    first_case = payload["cases"][0]
    assert set(first_case.keys()) >= {
        "case_id",
        "request",
        "retrieved_tables",
        "retrieved_fields",
        "retrieved_glossary_terms",
        "retrieved_examples",
        "retrieved_error_cases",
        "vector_supplements",
        "rejected_vector_candidates",
        "matched_expected",
        "missing_expected",
        "unexpected",
        "judgment",
        "notes",
    }
    if first_case["vector_supplements"]:
        supplement = first_case["vector_supplements"][0]
        assert set(supplement.keys()) == {
            "record_id",
            "source_key",
            "asset_family",
            "title",
            "score",
            "rank",
            "accepted_reason",
        }
    if first_case["rejected_vector_candidates"]:
        rejected = first_case["rejected_vector_candidates"][0]
        assert set(rejected.keys()) == {
            "record_id",
            "source_key",
            "asset_family",
            "title",
            "score",
            "rank",
            "rejected_reason",
        }

    assert comparison_path.read_text(encoding="utf-8").strip()


def test_hybrid_baseline_never_regresses_deterministic_and_respects_pass_guard() -> None:
    from scripts.run_m2b_hybrid_baseline import build_hybrid_baseline_artifacts

    artifacts = build_hybrid_baseline_artifacts(
        golden_set_path=GOLDEN_SET_PATH,
        deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
        vector_baseline_path=VECTOR_BASELINE_PATH,
        vector_coverage_path=VECTOR_COVERAGE_PATH,
        generated_at="2026-06-28T00:00:00Z",
    )

    deterministic = {case["case_id"]: case for case in artifacts.deterministic_payload["cases"]}
    hybrid = {case["case_id"]: case for case in artifacts.results_payload["cases"]}

    judgment_rank = {"fail": 0, "partial": 1, "pass": 2}
    for case_id, hybrid_case in hybrid.items():
        deterministic_case = deterministic[case_id]
        assert len(hybrid_case["matched_expected"]) >= len(deterministic_case["matched_expected"])
        assert judgment_rank[hybrid_case["judgment"]] >= judgment_rank[deterministic_case["judgment"]]
        if deterministic_case["judgment"] == "pass":
            assert hybrid_case["vector_supplements"] == []
            assert all(
                item["rejected_reason"] == "deterministic_pass_guard"
                or item["rejected_reason"] == "duplicate_with_deterministic"
                for item in hybrid_case["rejected_vector_candidates"]
            )


def test_hybrid_baseline_tracks_vector_only_improvements_and_rejections() -> None:
    from scripts.run_m2b_hybrid_baseline import build_hybrid_baseline_artifacts

    artifacts = build_hybrid_baseline_artifacts(
        golden_set_path=GOLDEN_SET_PATH,
        deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
        vector_baseline_path=VECTOR_BASELINE_PATH,
        vector_coverage_path=VECTOR_COVERAGE_PATH,
        generated_at="2026-06-28T00:00:00Z",
    )

    comparison_cases = {case["case_id"]: case for case in artifacts.comparison_payload["cases"]}
    no_withdraw = comparison_cases["mx-no-withdraw-cohort"]
    assert "glossary:no_withdraw" in no_withdraw["vector_only_matches"]
    assert no_withdraw["hybrid_new_matches_from_vector"]
    assert no_withdraw["regression_risk"] in {"none", "low", "high"}

    hybrid_cases = {case["case_id"]: case for case in artifacts.results_payload["cases"]}
    app_profile = hybrid_cases["mx-app-profile-query"]
    assert app_profile["rejected_vector_candidates"]
    assert {item["rejected_reason"] for item in app_profile["rejected_vector_candidates"]}.issubset(
        {
            "duplicate_with_deterministic",
            "duplicate_with_accepted_supplement",
            "rank_above_limit",
            "below_family_threshold",
            "family_cap_reached",
            "case_cap_reached",
            "deterministic_pass_guard",
            "unsupported_family",
            "sql_error_case_disabled",
        }
    )


def test_hybrid_baseline_module_does_not_import_runtime_or_llm_paths() -> None:
    import scripts.run_m2b_hybrid_baseline as module

    source = inspect.getsource(module)
    forbidden_snippets = (
        "DataKnowledgeRetriever",
        "DataAgentService",
        "create_run",
        "sql_plan",
        "orchestrator",
        "openai",
        "gemini",
    )
    for snippet in forbidden_snippets:
        assert snippet not in source


def test_hybrid_selector_function_does_not_reference_golden_labels() -> None:
    import scripts.run_m2b_hybrid_baseline as module

    selector_source = inspect.getsource(module._select_vector_supplements)
    forbidden_snippets = ("expected_tables", "expected_fields", "expected_glossary_terms", "matched_expected", "missing_expected")
    for snippet in forbidden_snippets:
        assert snippet not in selector_source
