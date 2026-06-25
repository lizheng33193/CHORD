from __future__ import annotations

import inspect
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SET_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "golden_set.yaml"
RECORDS_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "embedding_records.m2b_legacy_v3.jsonl"
EMBEDDING_MANIFEST_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "embedding_manifest.m2b_legacy_v3.yaml"
DETERMINISTIC_BASELINE_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "baseline_results.m2b_legacy_v3.deterministic.json"


def test_vector_baseline_runs_and_emits_expected_schema(tmp_path: Path) -> None:
    from scripts.build_m2b_vector_index import build_vector_index_artifacts, write_vector_index_outputs
    from scripts.run_m2b_vector_baseline import build_vector_baseline_artifacts, write_vector_baseline_outputs

    index_artifacts = build_vector_index_artifacts(
        records_path=RECORDS_PATH,
        embedding_manifest_path=EMBEDDING_MANIFEST_PATH,
        generated_at="2026-06-25T00:00:00Z",
        vector_dim=512,
    )
    index_path = tmp_path / "vector_index.json"
    index_manifest_path = tmp_path / "vector_index_manifest.yaml"
    write_vector_index_outputs(
        artifacts=index_artifacts,
        index_path=index_path,
        manifest_path=index_manifest_path,
    )

    baseline_artifacts = build_vector_baseline_artifacts(
        golden_set_path=GOLDEN_SET_PATH,
        records_path=RECORDS_PATH,
        index_path=index_path,
        index_manifest_path=index_manifest_path,
        deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
        top_k=10,
        generated_at="2026-06-25T00:00:00Z",
    )
    output_path = tmp_path / "vector_results.json"
    coverage_path = tmp_path / "vector_coverage.yaml"
    comparison_path = tmp_path / "comparison.md"
    write_vector_baseline_outputs(
        artifacts=baseline_artifacts,
        output_path=output_path,
        coverage_path=coverage_path,
        comparison_path=comparison_path,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "m2b_vector_baseline_v1"
    assert payload["run_mode"] == "vector_prototype"
    assert payload["top_k"] == 10
    assert payload["generated_at"] == "2026-06-25T00:00:00Z"
    assert payload["deterministic_baseline"] == str(DETERMINISTIC_BASELINE_PATH)
    assert payload["cases"]

    first_case = payload["cases"][0]
    assert set(first_case.keys()) >= {
        "case_id",
        "request",
        "retrieved_records",
        "matched_expected",
        "missing_expected",
        "unexpected",
        "judgment",
        "notes",
    }
    assert first_case["retrieved_records"]
    first_retrieved = first_case["retrieved_records"][0]
    assert set(first_retrieved.keys()) == {
        "rank",
        "record_id",
        "source_key",
        "asset_family",
        "title",
        "score",
    }
    assert isinstance(first_retrieved["score"], float)

    retrieved_titles = [item["title"] for item in first_case["retrieved_records"]]
    assert len(retrieved_titles) == len(set(retrieved_titles))
    assert comparison_path.read_text(encoding="utf-8").strip()


def test_vector_comparison_report_classifies_match_sets(tmp_path: Path) -> None:
    from scripts.build_m2b_vector_index import build_vector_index_artifacts, write_vector_index_outputs
    from scripts.run_m2b_vector_baseline import build_vector_baseline_artifacts

    index_artifacts = build_vector_index_artifacts(
        records_path=RECORDS_PATH,
        embedding_manifest_path=EMBEDDING_MANIFEST_PATH,
        generated_at="2026-06-25T00:00:00Z",
        vector_dim=512,
    )
    index_path = tmp_path / "vector_index.json"
    index_manifest_path = tmp_path / "vector_index_manifest.yaml"
    write_vector_index_outputs(
        artifacts=index_artifacts,
        index_path=index_path,
        manifest_path=index_manifest_path,
    )

    artifacts = build_vector_baseline_artifacts(
        golden_set_path=GOLDEN_SET_PATH,
        records_path=RECORDS_PATH,
        index_path=index_path,
        index_manifest_path=index_manifest_path,
        deterministic_baseline_path=DETERMINISTIC_BASELINE_PATH,
        top_k=10,
        generated_at="2026-06-25T00:00:00Z",
    )

    comparison = artifacts.comparison_payload
    assert comparison["schema_version"] == "m2b_vector_comparison_v1"
    assert comparison["cases"]
    first_case = comparison["cases"][0]
    assert set(first_case.keys()) == {
        "case_id",
        "deterministic_judgment",
        "vector_judgment",
        "deterministic_only_matches",
        "vector_only_matches",
        "shared_matches",
        "hybrid_potential",
        "notes",
    }
    assert first_case["hybrid_potential"] in {"high", "medium", "low"}


def test_vector_baseline_module_does_not_import_runtime_retriever_or_data_agent() -> None:
    import scripts.run_m2b_vector_baseline as module

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
