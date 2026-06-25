from __future__ import annotations

import inspect
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "embedding_records.m2b_legacy_v3.jsonl"
MANIFEST_PATH = REPO_ROOT / "data_knowledge_eval" / "m2b" / "embedding_manifest.m2b_legacy_v3.yaml"


def test_vector_index_builder_is_deterministic_and_manifest_is_complete() -> None:
    from scripts.build_m2b_vector_index import build_vector_index_artifacts

    first = build_vector_index_artifacts(
        records_path=RECORDS_PATH,
        embedding_manifest_path=MANIFEST_PATH,
        generated_at="2026-06-25T00:00:00Z",
        vector_dim=512,
    )
    second = build_vector_index_artifacts(
        records_path=RECORDS_PATH,
        embedding_manifest_path=MANIFEST_PATH,
        generated_at="2026-06-25T00:00:00Z",
        vector_dim=512,
    )

    assert first.index_payload == second.index_payload
    assert first.manifest_payload == second.manifest_payload

    manifest = first.manifest_payload
    assert manifest["schema_version"] == "m2b_vector_index_manifest_v1"
    assert manifest["source_namespace"] == "m2b_legacy_v3"
    assert manifest["vectorizer_name"] == "local_hashing_bow_v1"
    assert manifest["vector_dim"] == 512
    assert manifest["vector_format"] == "sparse_hash_weight_map"
    assert manifest["normalization"] == "l2"
    assert manifest["tokenizer"] == "unicode_lower_snake_camel_cjk_bigram"
    assert manifest["input_fields"] == ["title", "embedding_text", "search_hints"]
    assert manifest["field_weights"] == {"title": 2.0, "search_hints": 2.0, "embedding_text": 1.0}
    assert manifest["similarity"] == "cosine"
    assert manifest["generated_at"] == "2026-06-25T00:00:00Z"
    assert manifest["record_count"] == len(first.index_payload["records"])

    source_keys = [record["source_key"] for record in first.index_payload["records"]]
    record_ids = [record["record_id"] for record in first.index_payload["records"]]
    assert len(source_keys) == len(set(source_keys))
    assert len(record_ids) == len(set(record_ids))


def test_vector_index_builder_outputs_expected_sparse_vectors(tmp_path: Path) -> None:
    from scripts.build_m2b_vector_index import (
        build_vector_index_artifacts,
        write_vector_index_outputs,
    )

    artifacts = build_vector_index_artifacts(
        records_path=RECORDS_PATH,
        embedding_manifest_path=MANIFEST_PATH,
        generated_at="2026-06-25T00:00:00Z",
        vector_dim=512,
    )
    index_path = tmp_path / "vector_index.json"
    manifest_path = tmp_path / "vector_index_manifest.yaml"
    write_vector_index_outputs(
        artifacts=artifacts,
        index_path=index_path,
        manifest_path=manifest_path,
    )

    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "m2b_vector_index_v1"
    assert payload["vector_dim"] == 512
    assert len(payload["records"]) == artifacts.manifest_payload["record_count"]

    first_record = payload["records"][0]
    assert set(first_record.keys()) >= {
        "record_id",
        "source_key",
        "asset_family",
        "country",
        "title",
        "vector",
        "metadata",
    }
    assert isinstance(first_record["vector"], dict)
    assert first_record["vector"]
    assert all(str(key).isdigit() for key in first_record["vector"])


def test_vector_index_builder_does_not_depend_on_raw_docs_or_embedding_api() -> None:
    import scripts.build_m2b_vector_index as module

    source = inspect.getsource(module)
    forbidden_snippets = (
        "docs/knowledge-base",
        "OpenAI",
        "openai",
        "Gemini",
        "embedding API",
        "faiss",
        "milvus",
        "pgvector",
    )
    for snippet in forbidden_snippets:
        assert snippet not in source
