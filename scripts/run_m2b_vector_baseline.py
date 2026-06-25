from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
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

from scripts.build_m2b_vector_index import (
    DEFAULT_FIELD_WEIGHTS,
    DEFAULT_VECTOR_DIM,
    vectorize_record,
)
from scripts.run_m2b_retrieval_baseline import (
    FIELD_EQUIVALENCE_TOKENS,
    _normalize_table_name,
    _normalize_token,
    load_golden_cases,
)


@dataclass(slots=True)
class VectorBaselineArtifacts:
    results_payload: dict[str, Any]
    coverage_payload: dict[str, Any]
    comparison_payload: dict[str, Any]
    comparison_markdown: str


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to build the M2B vector baseline. Install project dependencies before running this script."
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
    return records


def _load_index(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("vector index must be a JSON object")
    return payload


def _sparse_dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, value in left.items():
        score += value * right.get(key, 0.0)
    return round(score, 6)


def _parse_embedding_list_line(record: dict[str, Any], label: str) -> list[str]:
    prefix = f"{label}:"
    for line in str(record.get("embedding_text") or "").splitlines():
        if not line.startswith(prefix):
            continue
        value = line.split(":", 1)[1].strip()
        if not value or value == "none":
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _field_match_tokens(record: dict[str, Any]) -> set[str]:
    tokens = {_normalize_token(record.get("metadata", {}).get("field_name", ""))}
    tokens.update(_normalize_token(value) for value in (record.get("search_hints") or []))
    return {token for token in tokens if token}


def _glossary_match_tokens(record: dict[str, Any]) -> set[str]:
    tokens = {_normalize_token(record.get("title", ""))}
    tokens.update(_normalize_token(value) for value in (record.get("search_hints") or []))
    return {token for token in tokens if token}


def _example_match_tokens(record: dict[str, Any]) -> set[str]:
    tokens = {_normalize_token(record.get("source_key", ""))}
    title = _normalize_token(record.get("title", ""))
    if title:
        tokens.add(title)
    tokens.update(_normalize_token(value) for value in (record.get("search_hints") or []))
    return {token for token in tokens if token}


def _error_case_match_tokens(record: dict[str, Any]) -> set[str]:
    tokens = {_normalize_token(record.get("source_key", ""))}
    tokens.update(_normalize_token(value) for value in (record.get("search_hints") or []))
    return {token for token in tokens if token}


def _table_match_tokens(record: dict[str, Any]) -> set[str]:
    metadata = dict(record.get("metadata") or {})
    table_name = metadata.get("table_name") or record.get("title") or ""
    physical_names = metadata.get("physical_table_names") or []
    tokens = {_normalize_table_name(table_name), _normalize_token(table_name)}
    for name in physical_names:
        tokens.add(_normalize_table_name(name))
        tokens.add(_normalize_token(name))
    return {token for token in tokens if token}


def _build_query_record(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": case["request"],
        "embedding_text": "\n".join(
            [
                f"Request: {case['request']}",
                f"Country: {case['country']}",
                f"Domain: {case['domain']}",
                f"Run type: {case['run_type']}",
                f"Output bucket: {case['output_bucket']}",
            ]
        ),
        "search_hints": [case["country"], case["domain"], case["run_type"], case["output_bucket"]],
    }


def _rank_records_for_case(
    *,
    case: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
    index_records: list[dict[str, Any]],
    vector_dim: int,
    top_k: int,
) -> list[dict[str, Any]]:
    query_vector = vectorize_record(
        record=_build_query_record(case),
        vector_dim=vector_dim,
        field_weights=DEFAULT_FIELD_WEIGHTS,
    )
    candidates: list[dict[str, Any]] = []
    for entry in index_records:
        record = records_by_id[entry["record_id"]]
        country = str(record.get("country") or "common").lower()
        if country not in {str(case["country"]).lower(), "common"}:
            continue
        score = _sparse_dot(query_vector, entry["vector"])
        candidates.append(
            {
                "record_id": entry["record_id"],
                "source_key": entry["source_key"],
                "asset_family": entry["asset_family"],
                "title": entry["title"],
                "score": float(score),
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["asset_family"], item["source_key"]))
    top_candidates = candidates[:top_k]
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rank, item in enumerate(top_candidates, start=1):
        dedupe_key = (item["title"], item["asset_family"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(
            {
                "rank": len(deduped) + 1,
                "record_id": item["record_id"],
                "source_key": item["source_key"],
                "asset_family": item["asset_family"],
                "title": item["title"],
                "score": round(float(item["score"]), 6),
            }
        )
    return deduped


def _build_case_result(
    *,
    case: dict[str, Any],
    retrieved_records: list[dict[str, Any]],
    records_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    matched_expected: list[str] = []
    missing_expected: list[str] = []
    unexpected: list[str] = []

    table_tokens: set[str] = set()
    field_tokens: set[str] = set()
    glossary_tokens: set[str] = set()
    example_tokens: set[str] = set()
    error_tokens: set[str] = set()

    for item in retrieved_records:
        record = records_by_id[item["record_id"]]
        family = record["asset_family"]
        if family == "catalog_table":
            table_tokens.update(_table_match_tokens(record))
        elif family == "catalog_field":
            field_tokens.update(_field_match_tokens(record))
        elif family == "glossary_term":
            glossary_tokens.update(_glossary_match_tokens(record))
        elif family == "sql_example":
            example_tokens.update(_example_match_tokens(record))
        elif family == "sql_error_case":
            error_tokens.update(_error_case_match_tokens(record))

    for expected in case["expected_tables"]:
        label = f"table:{expected}"
        if _normalize_table_name(expected) in table_tokens or _normalize_token(expected) in table_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    for expected in case["expected_fields"]:
        label = f"field:{expected}"
        token = _normalize_token(expected)
        equivalent_tokens = FIELD_EQUIVALENCE_TOKENS.get(token, {token})
        if equivalent_tokens.intersection(field_tokens):
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    for expected in case["expected_glossary_terms"]:
        label = f"glossary:{expected}"
        if _normalize_token(expected) in glossary_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    for expected in case["expected_sql_examples"]:
        label = f"example:{expected}"
        if _normalize_token(expected) in example_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    for forbidden in case["forbidden_examples"]:
        label = f"forbidden:{forbidden}"
        if _normalize_token(forbidden) in error_tokens:
            unexpected.append(label)

    if matched_expected and not missing_expected:
        judgment = "pass"
    elif matched_expected:
        judgment = "partial"
    else:
        judgment = "fail"

    notes = [
        "fake/local vector prototype only",
        "comparison normalization only; no synthetic retrieved assets added",
    ]
    return {
        "case_id": case["case_id"],
        "request": case["request"],
        "retrieved_records": retrieved_records,
        "matched_expected": matched_expected,
        "missing_expected": missing_expected,
        "unexpected": unexpected,
        "judgment": judgment,
        "notes": notes,
    }


def _build_coverage_payload(results_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "m2b_vector_coverage_v1",
        "run_mode": "vector_prototype",
        "source_namespace": results_payload["source_namespace"],
        "vector_index": results_payload["vector_index"],
        "cases": [
            {
                "case_id": case["case_id"],
                "matched_expected": list(case["matched_expected"]),
                "missing_expected": list(case["missing_expected"]),
                "unexpected": list(case["unexpected"]),
                "coverage_judgment": case["judgment"],
                "notes": list(case["notes"]),
            }
            for case in results_payload["cases"]
        ],
    }


def _hybrid_potential(*, vector_only_matches: list[str], unexpected: list[str], vector_judgment: str) -> str:
    if vector_only_matches and not unexpected and vector_judgment in {"pass", "partial"}:
        return "high"
    if vector_only_matches or (vector_judgment == "partial" and not unexpected):
        return "medium"
    return "low"


def _build_comparison_payload(
    *,
    deterministic_payload: dict[str, Any],
    vector_payload: dict[str, Any],
) -> dict[str, Any]:
    deterministic_cases = {case["case_id"]: case for case in deterministic_payload["cases"]}
    comparison_cases: list[dict[str, Any]] = []
    for vector_case in vector_payload["cases"]:
        deterministic_case = deterministic_cases[vector_case["case_id"]]
        deterministic_matches = set(deterministic_case["matched_expected"])
        vector_matches = set(vector_case["matched_expected"])
        deterministic_only = sorted(deterministic_matches - vector_matches)
        vector_only = sorted(vector_matches - deterministic_matches)
        shared = sorted(deterministic_matches & vector_matches)
        comparison_cases.append(
            {
                "case_id": vector_case["case_id"],
                "deterministic_judgment": deterministic_case["judgment"],
                "vector_judgment": vector_case["judgment"],
                "deterministic_only_matches": deterministic_only,
                "vector_only_matches": vector_only,
                "shared_matches": shared,
                "hybrid_potential": _hybrid_potential(
                    vector_only_matches=vector_only,
                    unexpected=vector_case["unexpected"],
                    vector_judgment=vector_case["judgment"],
                ),
                "notes": [
                    f"deterministic matched: {len(deterministic_matches)}",
                    f"vector matched: {len(vector_matches)}",
                ],
            }
        )
    return {
        "schema_version": "m2b_vector_comparison_v1",
        "deterministic_baseline": vector_payload["deterministic_baseline"],
        "vector_results": vector_payload["vector_results_path"],
        "cases": comparison_cases,
    }


def _build_comparison_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M2B-4 Deterministic vs Vector Comparison",
        "",
        "This is a fake/local vector prototype comparison, not a formal embedding benchmark.",
        "",
        f"- deterministic_baseline: `{payload['deterministic_baseline']}`",
        f"- vector_results: `{payload['vector_results']}`",
        "",
        "| case_id | deterministic_judgment | vector_judgment | deterministic_only_matches | vector_only_matches | shared_matches | hybrid_potential | notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in payload["cases"]:
        lines.append(
            "| {case_id} | {det} | {vec} | {det_only} | {vec_only} | {shared} | {hybrid} | {notes} |".format(
                case_id=case["case_id"],
                det=case["deterministic_judgment"],
                vec=case["vector_judgment"],
                det_only=", ".join(case["deterministic_only_matches"]) or "-",
                vec_only=", ".join(case["vector_only_matches"]) or "-",
                shared=", ".join(case["shared_matches"]) or "-",
                hybrid=case["hybrid_potential"],
                notes="; ".join(case["notes"]) or "-",
            )
        )
    return "\n".join(lines)


def build_vector_baseline_artifacts(
    *,
    golden_set_path: Path,
    records_path: Path,
    index_path: Path,
    index_manifest_path: Path,
    deterministic_baseline_path: Path,
    top_k: int = 10,
    generated_at: str | None = None,
) -> VectorBaselineArtifacts:
    cases = load_golden_cases(golden_set_path)
    records = _load_records(records_path)
    records_by_id = {record["record_id"]: record for record in records}
    index_payload = _load_index(index_path)
    index_manifest = _read_yaml(index_manifest_path)
    deterministic_payload = json.loads(deterministic_baseline_path.read_text(encoding="utf-8"))

    if index_manifest.get("record_count") != len(index_payload.get("records") or []):
        raise ValueError("vector index manifest record_count mismatch")

    source_namespace = str(index_manifest.get("source_namespace") or "").strip()
    vector_dim = int(index_manifest.get("vector_dim") or DEFAULT_VECTOR_DIM)
    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    case_results: list[dict[str, Any]] = []
    for case in cases:
        retrieved_records = _rank_records_for_case(
            case=case,
            records_by_id=records_by_id,
            index_records=index_payload["records"],
            vector_dim=vector_dim,
            top_k=top_k,
        )
        case_results.append(
            _build_case_result(
                case=case,
                retrieved_records=retrieved_records,
                records_by_id=records_by_id,
            )
        )

    results_payload = {
        "schema_version": "m2b_vector_baseline_v1",
        "generated_at": timestamp,
        "run_mode": "vector_prototype",
        "source_namespace": source_namespace,
        "vectorizer_name": index_manifest["vectorizer_name"],
        "vector_index": str(index_path),
        "top_k": top_k,
        "deterministic_baseline": str(deterministic_baseline_path),
        "vector_results_path": "data_knowledge_eval/m2b/vector_results.m2b_legacy_v3.json",
        "cases": case_results,
    }
    coverage_payload = _build_coverage_payload(results_payload)
    comparison_payload = _build_comparison_payload(
        deterministic_payload=deterministic_payload,
        vector_payload=results_payload,
    )
    comparison_markdown = _build_comparison_markdown(comparison_payload)
    return VectorBaselineArtifacts(
        results_payload=results_payload,
        coverage_payload=coverage_payload,
        comparison_payload=comparison_payload,
        comparison_markdown=comparison_markdown,
    )


def write_vector_baseline_outputs(
    *,
    artifacts: VectorBaselineArtifacts,
    output_path: Path,
    coverage_path: Path,
    comparison_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(artifacts.results_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _require_yaml()
    coverage_path.write_text(
        yaml.safe_dump(artifacts.coverage_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    comparison_path.write_text(artifacts.comparison_markdown + "\n", encoding="utf-8")


def _build_results_review_markdown(results_payload: dict[str, Any], comparison_payload: dict[str, Any]) -> str:
    counter = Counter(case["judgment"] for case in results_payload["cases"])
    vector_only_cases = [case for case in comparison_payload["cases"] if case["vector_only_matches"]]
    if len(vector_only_cases) >= 3:
        next_step = "M2B-5 Hybrid Retrieval Fusion"
    else:
        next_step = "M2B-4.1 Vector Text / Tokenizer / Local Vectorizer Patch"
    lines = [
        "# M2B-4 Vector Index Prototype Results",
        "",
        "This is a fake/local vector prototype, not a real embedding benchmark.",
        "",
        "## Summary",
        "",
        f"- run_mode: `{results_payload['run_mode']}`",
        f"- vectorizer_name: `{results_payload['vectorizer_name']}`",
        f"- source_namespace: `{results_payload['source_namespace']}`",
        f"- top_k: `{results_payload['top_k']}`",
        f"- pass: `{counter['pass']}`",
        f"- partial: `{counter['partial']}`",
        f"- fail: `{counter['fail']}`",
        f"- vector_only_cases: `{len(vector_only_cases)}`",
        "",
        "## Vector-only Signals",
        "",
    ]
    if vector_only_cases:
        for case in vector_only_cases:
            lines.append(
                f"- `{case['case_id']}` -> {', '.join(case['vector_only_matches']) or 'none'} (`hybrid_potential={case['hybrid_potential']}`)"
            )
    else:
        lines.append("- No meaningful vector-only matches were observed in this run.")
    lines.extend(
        [
            "",
        "## Interpretation",
        "",
        "- This stage only validates whether M2B-3 embedding records can support an offline vector retrieval chain.",
        "- The local vectorizer is deterministic and reproducible, but it does not represent the ceiling of a real embedding model.",
        "- The current vector-only baseline should not replace deterministic retrieval because its pass count remains lower.",
        f"- Recommended next step: `{next_step}`",
        "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the M2B offline vector baseline prototype.")
    parser.add_argument("--golden-set", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--index-manifest", required=True, type=Path)
    parser.add_argument("--deterministic-baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage-yaml", required=True, type=Path)
    parser.add_argument("--comparison-output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    artifacts = build_vector_baseline_artifacts(
        golden_set_path=args.golden_set,
        records_path=args.records,
        index_path=args.index,
        index_manifest_path=args.index_manifest,
        deterministic_baseline_path=args.deterministic_baseline,
        top_k=args.top_k,
        generated_at=args.generated_at,
    )
    artifacts.results_payload["vector_results_path"] = str(args.output)
    artifacts.comparison_payload["vector_results"] = str(args.output)
    artifacts.comparison_markdown = _build_comparison_markdown(artifacts.comparison_payload)
    write_vector_baseline_outputs(
        artifacts=artifacts,
        output_path=args.output,
        coverage_path=args.coverage_yaml,
        comparison_path=args.comparison_output,
    )

    review_path = Path("docs/reviews/m2b-4-vector-index-prototype-results.md")
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        _build_results_review_markdown(artifacts.results_payload, artifacts.comparison_payload) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
