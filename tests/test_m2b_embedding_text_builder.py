from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
V3_SEED_PATH = REPO_ROOT / "data_knowledge_seed" / "m2b" / "m2b_legacy_v3.yaml"


def test_embedding_text_builder_generates_deterministic_records_and_manifest(tmp_path: Path) -> None:
    from scripts.build_m2b_embedding_text import build_embedding_artifacts

    first = build_embedding_artifacts(
        seed_patch_path=V3_SEED_PATH,
        generated_at="2026-06-25T00:00:00Z",
        strict=True,
    )
    second = build_embedding_artifacts(
        seed_patch_path=V3_SEED_PATH,
        generated_at="2026-06-25T00:00:00Z",
        strict=True,
    )

    assert first.records == second.records
    assert first.manifest == second.manifest
    assert first.preview_markdown == second.preview_markdown

    assert first.manifest["schema_version"] == "m2b_embedding_manifest_v1"
    assert first.manifest["builder_schema_version"] == "embedding_text_v1"
    assert first.manifest["source_namespace"] == "m2b_legacy_v3"
    assert first.manifest["generated_at"] == "2026-06-25T00:00:00Z"
    assert first.manifest["record_id_hash_algorithm"] == "sha256"
    assert first.manifest["record_id_hash_input"] == "source_namespace + source_key + asset_family"
    assert first.manifest["record_count"] == len(first.records)
    assert first.manifest["sanitization_checks_passed"] is True
    assert first.manifest["excluded_families"] == [
        "business_rules",
        "cohort_definitions",
        "canonical_field_policies",
    ]

    record_ids = [record["record_id"] for record in first.records]
    assert len(record_ids) == len(set(record_ids))

    sort_keys = [(record["asset_family"], record["country"], record["source_key"]) for record in first.records]
    assert sort_keys == sorted(sort_keys)

    by_family: dict[str, int] = {}
    for record in first.records:
        by_family[record["asset_family"]] = by_family.get(record["asset_family"], 0) + 1
    for family_name in ("catalog_table", "catalog_field", "glossary_term", "sql_example", "sql_error_case"):
        by_family.setdefault(family_name, 0)
    assert first.manifest["family_counts"] == by_family


def test_embedding_text_builder_outputs_valid_jsonl_and_priority_preview(tmp_path: Path) -> None:
    from scripts.build_m2b_embedding_text import build_embedding_artifacts, write_embedding_outputs

    artifacts = build_embedding_artifacts(
        seed_patch_path=V3_SEED_PATH,
        generated_at="2026-06-25T00:00:00Z",
        strict=True,
    )
    jsonl_path = tmp_path / "embedding_records.jsonl"
    manifest_path = tmp_path / "embedding_manifest.yaml"
    preview_path = tmp_path / "embedding_preview.md"
    write_embedding_outputs(
        artifacts=artifacts,
        jsonl_path=jsonl_path,
        manifest_path=manifest_path,
        preview_path=preview_path,
    )

    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == artifacts.manifest["record_count"]
    for line in lines:
        payload = json.loads(line)
        assert payload["embedding_text"].strip()

    preview = preview_path.read_text(encoding="utf-8")
    assert "mob1" in preview
    assert "withdraw_uuid" in preview
    assert "user_uuid" in preview
    assert "asset_finish_at" in preview
    assert "credit_profile" in preview
    assert "Non-executable pattern guidance." in preview


def test_embedding_text_builder_sanitizes_content_and_marks_sql_examples_non_executable() -> None:
    from scripts.build_m2b_embedding_text import build_embedding_artifacts

    artifacts = build_embedding_artifacts(
        seed_patch_path=V3_SEED_PATH,
        generated_at="2026-06-25T00:00:00Z",
        strict=True,
    )

    sql_example_record = next(record for record in artifacts.records if record["asset_family"] == "sql_example")
    assert "Non-executable pattern guidance." in sql_example_record["embedding_text"]
    assert "This record is not executable SQL." in sql_example_record["embedding_text"]
    assert sql_example_record["metadata"]["kind"] == "sql_example_pattern"
    assert sql_example_record["metadata"]["executable"] is False
    assert sql_example_record["metadata"]["raw_sql_available"] is False

    serialized = json.dumps([record["embedding_text"] for record in artifacts.records], ensure_ascii=False)
    lowered = serialized.lower()
    forbidden_snippets = (
        "pymysql.connect",
        "create_engine",
        "jdbc:",
        "dm_model.yx_tmp_",
        "password=",
        "host=",
        "user=",
    )
    for snippet in forbidden_snippets:
        assert snippet not in lowered


def test_embedding_text_builder_fails_on_unknown_family_in_strict_mode(tmp_path: Path) -> None:
    from scripts.build_m2b_embedding_text import build_embedding_artifacts

    seed_path = tmp_path / "bad_seed.yaml"
    seed_path.write_text(
        "\n".join(
            [
                "schema_version: m2b_seed_patch_v1",
                "source_namespace: m2b_legacy_v3",
                "generated_from_manifest: test.yaml",
                "catalog_tables: []",
                "catalog_fields: []",
                "glossary_terms: []",
                "sql_examples: []",
                "sql_error_cases: []",
                "business_rules:",
                "  - source_key: rule.test.example",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported seed family"):
        build_embedding_artifacts(
            seed_patch_path=seed_path,
            generated_at="2026-06-25T00:00:00Z",
            strict=True,
        )
