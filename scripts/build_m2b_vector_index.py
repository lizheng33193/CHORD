from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_VECTOR_DIM = 512
DEFAULT_VECTORIZER_NAME = "local_hashing_bow_v1"
DEFAULT_VECTOR_FORMAT = "sparse_hash_weight_map"
DEFAULT_NORMALIZATION = "l2"
DEFAULT_TOKENIZER = "unicode_lower_snake_camel_cjk_bigram"
DEFAULT_SIMILARITY = "cosine"
DEFAULT_INPUT_FIELDS = ["title", "embedding_text", "search_hints"]
DEFAULT_FIELD_WEIGHTS = {"title": 2.0, "search_hints": 2.0, "embedding_text": 1.0}
EXPECTED_MANIFEST_SCHEMA = "m2b_embedding_manifest_v1"
EXPECTED_BUILDER_SCHEMA = "embedding_text_v1"

CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
WORD_TOKEN = re.compile(r"[a-z0-9_]+")
CJK_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(slots=True)
class VectorIndexArtifacts:
    index_payload: dict[str, Any]
    manifest_payload: dict[str, Any]


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to build the M2B vector index. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def _read_yaml(path: Path) -> dict[str, Any]:
    _require_yaml()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("embedding record lines must be JSON objects")
        records.append(payload)
    if not records:
        raise ValueError("embedding records JSONL is empty")
    return records


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).lower().strip()


def _split_token_variants(token: str) -> list[str]:
    normalized = _normalize_text(token)
    if not normalized:
        return []
    variants = [normalized]
    camel_split = CAMEL_BOUNDARY.sub(" ", token)
    camel_normalized = _normalize_text(camel_split)
    if camel_normalized and camel_normalized != normalized:
        variants.extend(camel_normalized.split())
    if "_" in normalized:
        variants.extend(part for part in normalized.split("_") if part)
    return variants


def _tokenize_text(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    tokens: list[str] = []
    for raw in WORD_TOKEN.findall(normalized):
        tokens.extend(_split_token_variants(raw))

    compact_cjk = "".join(CJK_CHAR.findall(normalized))
    if compact_cjk:
        if len(compact_cjk) == 1:
            tokens.append(compact_cjk)
        else:
            for index in range(len(compact_cjk) - 1):
                tokens.append(compact_cjk[index : index + 2])

    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        value = token.strip()
        if not value:
            continue
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _hash_token(token: str, *, vector_dim: int) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return str(int.from_bytes(digest[:8], "big") % vector_dim)


def _l2_normalize_sparse(vector: dict[str, float]) -> dict[str, float]:
    if not vector:
        return {}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return {}
    return {
        key: round(value / norm, 6)
        for key, value in sorted(vector.items(), key=lambda item: int(item[0]))
        if value
    }


def vectorize_record(
    *,
    record: dict[str, Any],
    vector_dim: int,
    field_weights: dict[str, float],
) -> dict[str, float]:
    weighted_counts: dict[str, float] = {}
    for field_name in DEFAULT_INPUT_FIELDS:
        weight = float(field_weights[field_name])
        value = record.get(field_name)
        if field_name == "search_hints":
            source_values = value if isinstance(value, list) else []
            field_text = " ".join(str(item) for item in source_values)
        else:
            field_text = str(value or "")
        for token in _tokenize_text(field_text):
            bucket = _hash_token(token, vector_dim=vector_dim)
            weighted_counts[bucket] = weighted_counts.get(bucket, 0.0) + weight
    return _l2_normalize_sparse(weighted_counts)


def _validate_embedding_manifest(manifest: dict[str, Any], *, record_count: int) -> None:
    if manifest.get("schema_version") != EXPECTED_MANIFEST_SCHEMA:
        raise ValueError("unexpected embedding manifest schema_version")
    if manifest.get("builder_schema_version") != EXPECTED_BUILDER_SCHEMA:
        raise ValueError("unexpected embedding builder schema version")
    if int(manifest.get("record_count") or -1) != record_count:
        raise ValueError("embedding manifest record_count does not match records JSONL")


def build_vector_index_artifacts(
    *,
    records_path: Path,
    embedding_manifest_path: Path,
    generated_at: str | None = None,
    vector_dim: int = DEFAULT_VECTOR_DIM,
) -> VectorIndexArtifacts:
    records = _load_records(records_path)
    embedding_manifest = _read_yaml(embedding_manifest_path)
    _validate_embedding_manifest(embedding_manifest, record_count=len(records))

    source_namespace = str(embedding_manifest.get("source_namespace") or "").strip()
    if not source_namespace:
        raise ValueError("embedding manifest source_namespace is required")

    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sorted_records = sorted(
        records,
        key=lambda item: (str(item["asset_family"]), str(item["country"]), str(item["source_key"])),
    )

    index_records: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    seen_source_keys: set[str] = set()
    for record in sorted_records:
        record_id = str(record["record_id"])
        source_key = str(record["source_key"])
        if record_id in seen_record_ids:
            raise ValueError(f"duplicate record_id in embedding records: {record_id}")
        if source_key in seen_source_keys:
            raise ValueError(f"duplicate source_key in embedding records: {source_key}")
        seen_record_ids.add(record_id)
        seen_source_keys.add(source_key)
        vector = vectorize_record(
            record=record,
            vector_dim=vector_dim,
            field_weights=DEFAULT_FIELD_WEIGHTS,
        )
        if not vector:
            raise ValueError(f"empty vector generated for {source_key}")
        index_records.append(
            {
                "record_id": record_id,
                "source_key": source_key,
                "source_namespace": source_namespace,
                "asset_family": record["asset_family"],
                "country": record["country"],
                "title": record["title"],
                "vector": vector,
                "metadata": record.get("metadata") or {},
            }
        )

    index_payload = {
        "schema_version": "m2b_vector_index_v1",
        "source_namespace": source_namespace,
        "vectorizer_name": DEFAULT_VECTORIZER_NAME,
        "vector_dim": vector_dim,
        "vector_format": DEFAULT_VECTOR_FORMAT,
        "records": index_records,
    }
    manifest_payload = {
        "schema_version": "m2b_vector_index_manifest_v1",
        "source_namespace": source_namespace,
        "record_count": len(index_records),
        "vectorizer_name": DEFAULT_VECTORIZER_NAME,
        "vector_dim": vector_dim,
        "vector_format": DEFAULT_VECTOR_FORMAT,
        "normalization": DEFAULT_NORMALIZATION,
        "tokenizer": DEFAULT_TOKENIZER,
        "input_fields": list(DEFAULT_INPUT_FIELDS),
        "field_weights": dict(DEFAULT_FIELD_WEIGHTS),
        "similarity": DEFAULT_SIMILARITY,
        "generated_at": timestamp,
    }
    return VectorIndexArtifacts(index_payload=index_payload, manifest_payload=manifest_payload)


def write_vector_index_outputs(
    *,
    artifacts: VectorIndexArtifacts,
    index_path: Path,
    manifest_path: Path,
) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(artifacts.index_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _require_yaml()
    manifest_path.write_text(
        yaml.safe_dump(artifacts.manifest_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline M2B vector index prototype.")
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--index-manifest", required=True, type=Path)
    parser.add_argument("--vector-dim", type=int, default=DEFAULT_VECTOR_DIM)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    artifacts = build_vector_index_artifacts(
        records_path=args.records,
        embedding_manifest_path=args.manifest,
        generated_at=args.generated_at,
        vector_dim=args.vector_dim,
    )
    write_vector_index_outputs(
        artifacts=artifacts,
        index_path=args.output,
        manifest_path=args.index_manifest,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
