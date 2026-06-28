from __future__ import annotations

import argparse
import hashlib
import json
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

from scripts.run_m2b_retrieval_baseline import (
    FIELD_EQUIVALENCE_TOKENS,
    _normalize_table_name,
    _normalize_token,
    load_golden_cases,
)


DEFAULT_GENERATED_AT = "2026-06-28T00:00:00Z"
DEFAULT_FUSION_STRATEGY = "primary_merge_v1"
DEFAULT_VECTOR_RANK_LIMIT = 8
DEFAULT_CASE_SUPPLEMENT_CAP = 3
DEFAULT_FAMILY_THRESHOLDS = {
    "catalog_table": 0.18,
    "catalog_field": 0.16,
    "glossary_term": 0.17,
    "sql_example": 0.15,
}
DEFAULT_FAMILY_CAPS = {
    "catalog_table": 1,
    "catalog_field": 2,
    "glossary_term": 1,
    "sql_example": 1,
}
JUDGMENT_RANK = {"fail": 0, "partial": 1, "pass": 2}
ALLOWED_REJECTION_REASONS = {
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


@dataclass(slots=True)
class HybridBaselineArtifacts:
    results_payload: dict[str, Any]
    coverage_payload: dict[str, Any]
    manifest_payload: dict[str, Any]
    comparison_payload: dict[str, Any]
    comparison_markdown: str
    deterministic_payload: dict[str, Any]
    vector_payload: dict[str, Any]


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to build the M2B hybrid baseline. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    _require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def _read_yaml(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    _require_yaml()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a YAML mapping: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
    return result


def _extract_source_namespace(*, deterministic_payload: dict[str, Any], vector_payload: dict[str, Any]) -> str:
    namespaces = deterministic_payload.get("seed_namespaces") or []
    deterministic_namespace = str(namespaces[-1]) if namespaces else ""
    vector_namespace = str(vector_payload.get("source_namespace") or "")
    if deterministic_namespace and vector_namespace and deterministic_namespace != vector_namespace:
        raise ValueError("deterministic and vector baselines use different source namespaces")
    source_namespace = deterministic_namespace or vector_namespace
    if not source_namespace:
        raise ValueError("source namespace could not be resolved from baseline inputs")
    return source_namespace


def _vector_record_family(record: dict[str, Any]) -> str:
    family = str(record.get("asset_family") or "").strip()
    if family not in {"catalog_table", "catalog_field", "glossary_term", "sql_example", "sql_error_case"}:
        return "unsupported"
    return family


def _supplement_value_and_key(record: dict[str, Any]) -> tuple[str | None, str | None, str]:
    family = _vector_record_family(record)
    source_key = str(record.get("source_key") or "")
    title = str(record.get("title") or "")
    if family == "catalog_table":
        value = title.split(".")[-1].strip() or source_key.split(".")[-1].strip()
        return family, _normalize_table_name(value), value
    if family == "catalog_field":
        field_name = source_key.split(".")[-1].strip() or title.split(".")[-1].strip()
        return family, _normalize_token(field_name), field_name
    if family == "glossary_term":
        term = title.strip() or source_key.split(".")[-1].strip()
        return family, _normalize_token(term), term
    if family == "sql_example":
        return family, _normalize_token(source_key), source_key
    if family == "sql_error_case":
        return family, _normalize_token(source_key), source_key
    return None, None, ""


def _deterministic_existing_keys(case: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "catalog_table": {_normalize_table_name(item) for item in case.get("retrieved_tables", [])},
        "catalog_field": {_normalize_token(item) for item in case.get("retrieved_fields", [])},
        "glossary_term": {_normalize_token(item) for item in case.get("retrieved_glossary_terms", [])},
        "sql_example": {_normalize_token(item) for item in case.get("retrieved_examples", [])},
        "sql_error_case": {_normalize_token(item) for item in case.get("retrieved_error_cases", [])},
    }


def _append_supplement_value(case_result: dict[str, Any], *, family: str, value: str) -> None:
    family_to_key = {
        "catalog_table": "retrieved_tables",
        "catalog_field": "retrieved_fields",
        "glossary_term": "retrieved_glossary_terms",
        "sql_example": "retrieved_examples",
        "sql_error_case": "retrieved_error_cases",
    }
    target_key = family_to_key[family]
    case_result[target_key] = _dedupe_preserve_order([*case_result[target_key], value])


def _evaluate_case_result(case_definition: dict[str, Any], case_result: dict[str, Any]) -> tuple[list[str], list[str], list[str], str]:
    matched_expected: list[str] = []
    missing_expected: list[str] = []
    unexpected: list[str] = []

    table_tokens = {_normalize_table_name(value) for value in case_result["retrieved_tables"]}
    for expected in case_definition["expected_tables"]:
        label = f"table:{expected}"
        if _normalize_table_name(expected) in table_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    field_tokens = {_normalize_token(value) for value in case_result["retrieved_fields"]}
    for expected in case_definition["expected_fields"]:
        label = f"field:{expected}"
        token = _normalize_token(expected)
        equivalent_tokens = FIELD_EQUIVALENCE_TOKENS.get(token, {token})
        if equivalent_tokens.intersection(field_tokens):
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    glossary_tokens = {_normalize_token(value) for value in case_result["retrieved_glossary_terms"]}
    for expected in case_definition["expected_glossary_terms"]:
        label = f"glossary:{expected}"
        if _normalize_token(expected) in glossary_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    example_tokens = {_normalize_token(value) for value in case_result["retrieved_examples"]}
    for expected in case_definition["expected_sql_examples"]:
        label = f"example:{expected}"
        if _normalize_token(expected) in example_tokens:
            matched_expected.append(label)
        else:
            missing_expected.append(label)

    error_case_tokens = {_normalize_token(value) for value in case_result["retrieved_error_cases"]}
    for forbidden in case_definition["forbidden_examples"]:
        label = f"forbidden:{forbidden}"
        if _normalize_token(forbidden) in error_case_tokens:
            unexpected.append(label)

    if matched_expected and not missing_expected:
        judgment = "pass"
    elif matched_expected:
        judgment = "partial"
    else:
        judgment = "fail"
    return matched_expected, missing_expected, unexpected, judgment


def _ordered_expected_labels(case_definition: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    labels.extend(f"table:{value}" for value in case_definition["expected_tables"])
    labels.extend(f"field:{value}" for value in case_definition["expected_fields"])
    labels.extend(f"glossary:{value}" for value in case_definition["expected_glossary_terms"])
    labels.extend(f"example:{value}" for value in case_definition["expected_sql_examples"])
    return labels


def _select_vector_supplements(
    *,
    deterministic_case: dict[str, Any],
    vector_case: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, set[str]]]:
    existing_keys = _deterministic_existing_keys(deterministic_case)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    accepted_family_counts = {family: 0 for family in DEFAULT_FAMILY_CAPS}

    for record in vector_case.get("retrieved_records", []):
        family, canonical_key, value = _supplement_value_and_key(record)
        rejection_reason: str | None = None
        if family is None or canonical_key is None:
            rejection_reason = "unsupported_family"
        elif family == "sql_error_case":
            rejection_reason = "sql_error_case_disabled"
        elif canonical_key in existing_keys.get(family, set()):
            rejection_reason = "duplicate_with_deterministic"
        elif deterministic_case["judgment"] == "pass":
            rejection_reason = "deterministic_pass_guard"
        elif int(record["rank"]) > DEFAULT_VECTOR_RANK_LIMIT:
            rejection_reason = "rank_above_limit"
        elif float(record["score"]) < DEFAULT_FAMILY_THRESHOLDS.get(family, 1.0):
            rejection_reason = "below_family_threshold"
        elif accepted_family_counts.get(family, 0) >= DEFAULT_FAMILY_CAPS.get(family, 0):
            rejection_reason = "family_cap_reached"
        elif len(accepted) >= DEFAULT_CASE_SUPPLEMENT_CAP:
            rejection_reason = "case_cap_reached"
        elif canonical_key in {
            item["canonical_key"]
            for item in accepted
            if item["asset_family"] == family
        }:
            rejection_reason = "duplicate_with_accepted_supplement"

        if rejection_reason is not None:
            rejected.append(
                {
                    "record_id": record["record_id"],
                    "source_key": record["source_key"],
                    "asset_family": record["asset_family"],
                    "title": record["title"],
                    "score": float(record["score"]),
                    "rank": int(record["rank"]),
                    "rejected_reason": rejection_reason,
                }
            )
            continue

        accepted_family_counts[family] += 1
        existing_keys[family].add(canonical_key)
        accepted.append(
            {
                "record_id": record["record_id"],
                "source_key": record["source_key"],
                "asset_family": record["asset_family"],
                "title": record["title"],
                "score": float(record["score"]),
                "rank": int(record["rank"]),
                "accepted_reason": "vector_supplement_new_candidate",
                "canonical_key": canonical_key,
                "value": value,
            }
        )

    for item in rejected:
        if item["rejected_reason"] not in ALLOWED_REJECTION_REASONS:
            raise ValueError(f"unsupported rejected_reason: {item['rejected_reason']}")
    return accepted, rejected, existing_keys


def _build_hybrid_case_result(
    *,
    case_definition: dict[str, Any],
    deterministic_case: dict[str, Any],
    vector_case: dict[str, Any],
) -> dict[str, Any]:
    accepted, rejected, _ = _select_vector_supplements(
        deterministic_case=deterministic_case,
        vector_case=vector_case,
    )
    hybrid_case = {
        "case_id": deterministic_case["case_id"],
        "request": deterministic_case["request"],
        "retrieved_tables": list(deterministic_case["retrieved_tables"]),
        "retrieved_fields": list(deterministic_case["retrieved_fields"]),
        "retrieved_glossary_terms": list(deterministic_case["retrieved_glossary_terms"]),
        "retrieved_examples": list(deterministic_case["retrieved_examples"]),
        "retrieved_error_cases": list(deterministic_case["retrieved_error_cases"]),
        "vector_supplements": [
            {
                "record_id": item["record_id"],
                "source_key": item["source_key"],
                "asset_family": item["asset_family"],
                "title": item["title"],
                "score": item["score"],
                "rank": item["rank"],
                "accepted_reason": item["accepted_reason"],
            }
            for item in accepted
        ],
        "rejected_vector_candidates": rejected,
        "notes": [
            "primary_merge_v1: deterministic primary with vector supplement",
            "fusion selection uses rank/score/family caps only; no golden label leakage",
        ],
    }
    for item in accepted:
        _append_supplement_value(hybrid_case, family=item["asset_family"], value=item["value"])

    matched_expected, missing_expected, unexpected, judgment = _evaluate_case_result(case_definition, hybrid_case)
    deterministic_matched = list(deterministic_case["matched_expected"])
    merged_matched = list(deterministic_matched)
    for label in matched_expected:
        if label not in merged_matched:
            merged_matched.append(label)
    ordered_expected = _ordered_expected_labels(case_definition)
    merged_missing = [label for label in ordered_expected if label not in merged_matched]
    merged_unexpected = _dedupe_preserve_order(
        [*deterministic_case.get("unexpected", []), *unexpected]
    )
    if merged_matched and not merged_missing:
        merged_judgment = "pass"
    elif merged_matched:
        merged_judgment = "partial"
    else:
        merged_judgment = "fail"

    hybrid_case["matched_expected"] = merged_matched
    hybrid_case["missing_expected"] = merged_missing
    hybrid_case["unexpected"] = merged_unexpected
    hybrid_case["judgment"] = merged_judgment

    deterministic_judgment = deterministic_case["judgment"]
    if len(hybrid_case["matched_expected"]) < len(deterministic_matched):
        raise ValueError(f"hybrid matched_expected regressed for case {hybrid_case['case_id']}")
    if JUDGMENT_RANK[hybrid_case["judgment"]] < JUDGMENT_RANK[deterministic_judgment]:
        raise ValueError(f"hybrid judgment regressed for case {hybrid_case['case_id']}")
    return hybrid_case


def _build_coverage_payload(results_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "m2b_hybrid_coverage_v1",
        "run_mode": "hybrid_prototype",
        "fusion_strategy": results_payload["fusion_strategy"],
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


def _count_judgments(cases: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(case["judgment"] for case in cases)
    return {key: counter.get(key, 0) for key in ("pass", "partial", "fail")}


def _build_comparison_payload(
    *,
    deterministic_payload: dict[str, Any],
    vector_payload: dict[str, Any],
    hybrid_payload: dict[str, Any],
) -> dict[str, Any]:
    deterministic_cases = {case["case_id"]: case for case in deterministic_payload["cases"]}
    vector_cases = {case["case_id"]: case for case in vector_payload["cases"]}
    hybrid_cases = {case["case_id"]: case for case in hybrid_payload["cases"]}

    comparison_cases: list[dict[str, Any]] = []
    for case_id, hybrid_case in hybrid_cases.items():
        deterministic_case = deterministic_cases[case_id]
        vector_case = vector_cases[case_id]

        deterministic_matches = set(deterministic_case["matched_expected"])
        vector_matches = set(vector_case["matched_expected"])
        hybrid_matches = set(hybrid_case["matched_expected"])
        deterministic_only = sorted(deterministic_matches - vector_matches)
        vector_only = sorted(vector_matches - deterministic_matches)
        shared = sorted(deterministic_matches & vector_matches)
        hybrid_new_vs_det = sorted(hybrid_matches - deterministic_matches)
        hybrid_new_from_vector = sorted((hybrid_matches - deterministic_matches) & vector_matches)
        remaining_missing = list(hybrid_case["missing_expected"])

        if JUDGMENT_RANK[hybrid_case["judgment"]] < JUDGMENT_RANK[deterministic_case["judgment"]]:
            regression_risk = "high"
        elif len(hybrid_case["unexpected"]) > len(deterministic_case["unexpected"]):
            regression_risk = "low"
        else:
            regression_risk = "none"

        comparison_cases.append(
            {
                "case_id": case_id,
                "deterministic_judgment": deterministic_case["judgment"],
                "vector_judgment": vector_case["judgment"],
                "hybrid_judgment": hybrid_case["judgment"],
                "deterministic_only_matches": deterministic_only,
                "vector_only_matches": vector_only,
                "shared_matches": shared,
                "hybrid_new_matches_vs_deterministic": hybrid_new_vs_det,
                "hybrid_new_matches_from_vector": hybrid_new_from_vector,
                "remaining_missing_after_hybrid": remaining_missing,
                "accepted_vector_supplements": [item["source_key"] for item in hybrid_case["vector_supplements"]],
                "regression_risk": regression_risk,
                "notes": [
                    f"deterministic matched: {len(deterministic_matches)}",
                    f"vector matched: {len(vector_matches)}",
                    f"hybrid matched: {len(hybrid_matches)}",
                ],
            }
        )

    return {
        "schema_version": "m2b_hybrid_comparison_v1",
        "fusion_strategy": DEFAULT_FUSION_STRATEGY,
        "deterministic_baseline": hybrid_payload["deterministic_baseline"],
        "vector_baseline": hybrid_payload["vector_baseline"],
        "cases": comparison_cases,
    }


def _build_comparison_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# M2B-5 Deterministic vs Vector vs Hybrid Comparison",
        "",
        "This comparison evaluates conservative offline hybrid fusion only.",
        "",
        f"- deterministic_baseline: `{payload['deterministic_baseline']}`",
        f"- vector_baseline: `{payload['vector_baseline']}`",
        f"- fusion_strategy: `{payload['fusion_strategy']}`",
        "",
        "| case_id | deterministic_judgment | vector_judgment | hybrid_judgment | deterministic_only_matches | vector_only_matches | shared_matches | hybrid_new_matches_vs_deterministic | hybrid_new_matches_from_vector | remaining_missing_after_hybrid | accepted_vector_supplements | regression_risk | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case in payload["cases"]:
        lines.append(
            "| {case_id} | {det} | {vec} | {hybrid} | {det_only} | {vec_only} | {shared} | {new_vs_det} | {new_from_vec} | {remaining} | {accepted} | {risk} | {notes} |".format(
                case_id=case["case_id"],
                det=case["deterministic_judgment"],
                vec=case["vector_judgment"],
                hybrid=case["hybrid_judgment"],
                det_only=", ".join(case["deterministic_only_matches"]) or "-",
                vec_only=", ".join(case["vector_only_matches"]) or "-",
                shared=", ".join(case["shared_matches"]) or "-",
                new_vs_det=", ".join(case["hybrid_new_matches_vs_deterministic"]) or "-",
                new_from_vec=", ".join(case["hybrid_new_matches_from_vector"]) or "-",
                remaining=", ".join(case["remaining_missing_after_hybrid"]) or "-",
                accepted=", ".join(case["accepted_vector_supplements"]) or "-",
                risk=case["regression_risk"],
                notes="; ".join(case["notes"]) or "-",
            )
        )
    return "\n".join(lines)


def _build_results_review_markdown(results_payload: dict[str, Any], comparison_payload: dict[str, Any]) -> str:
    hybrid_counts = _count_judgments(results_payload["cases"])
    improved_cases = [case for case in comparison_payload["cases"] if case["hybrid_new_matches_vs_deterministic"]]
    lines = [
        "# M2B-5 Hybrid Retrieval Fusion Results",
        "",
        "This stage validates offline hybrid fusion only. It does not change runtime retrieval or Data Agent behavior.",
        "",
        "## Summary",
        "",
        f"- fusion_strategy: `{results_payload['fusion_strategy']}`",
        f"- source_namespace: `{results_payload['source_namespace']}`",
        f"- pass: `{hybrid_counts['pass']}`",
        f"- partial: `{hybrid_counts['partial']}`",
        f"- fail: `{hybrid_counts['fail']}`",
        f"- improved_cases_vs_deterministic: `{len(improved_cases)}`",
        "",
        "## Interpretation",
        "",
        "- deterministic remains the primary retrieval source in `primary_merge_v1`.",
        "- vector supplements are accepted only through conservative rank, threshold, and cap guards.",
        "- fusion selection does not read golden expected/missing labels; golden signals are only used after fusion for evaluation.",
    ]
    if improved_cases:
        lines.extend(
            [
                "",
                "## Cases With Hybrid Gains",
                "",
            ]
        )
        for case in improved_cases:
            lines.append(
                f"- `{case['case_id']}` -> {', '.join(case['hybrid_new_matches_vs_deterministic']) or 'none'}"
            )
    return "\n".join(lines)


def build_hybrid_baseline_artifacts(
    *,
    golden_set_path: Path,
    deterministic_baseline_path: Path,
    vector_baseline_path: Path,
    vector_coverage_path: Path,
    generated_at: str | None = None,
) -> HybridBaselineArtifacts:
    cases = load_golden_cases(golden_set_path)
    deterministic_payload = _read_json(deterministic_baseline_path, label="deterministic baseline")
    vector_payload = _read_json(vector_baseline_path, label="vector baseline")
    _read_yaml(vector_coverage_path, label="vector coverage")

    source_namespace = _extract_source_namespace(
        deterministic_payload=deterministic_payload,
        vector_payload=vector_payload,
    )

    deterministic_cases = {case["case_id"]: case for case in deterministic_payload.get("cases", [])}
    vector_cases = {case["case_id"]: case for case in vector_payload.get("cases", [])}
    if set(deterministic_cases) != set(vector_cases):
        raise ValueError("deterministic and vector baseline case ids do not match")

    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    hybrid_cases: list[dict[str, Any]] = []
    for case_definition in cases:
        case_id = str(case_definition["case_id"])
        hybrid_cases.append(
            _build_hybrid_case_result(
                case_definition=case_definition,
                deterministic_case=deterministic_cases[case_id],
                vector_case=vector_cases[case_id],
            )
        )

    results_payload = {
        "schema_version": "m2b_hybrid_baseline_v1",
        "run_mode": "hybrid_prototype",
        "fusion_strategy": DEFAULT_FUSION_STRATEGY,
        "deterministic_baseline": str(deterministic_baseline_path),
        "vector_baseline": str(vector_baseline_path),
        "generated_at": timestamp,
        "source_namespace": source_namespace,
        "cases": hybrid_cases,
    }
    coverage_payload = _build_coverage_payload(results_payload)
    comparison_payload = _build_comparison_payload(
        deterministic_payload=deterministic_payload,
        vector_payload=vector_payload,
        hybrid_payload=results_payload,
    )
    comparison_markdown = _build_comparison_markdown(comparison_payload)

    manifest_payload = {
        "schema_version": "m2b_hybrid_manifest_v1",
        "source_namespace": source_namespace,
        "fusion_strategy": DEFAULT_FUSION_STRATEGY,
        "deterministic_baseline": str(deterministic_baseline_path),
        "vector_baseline": str(vector_baseline_path),
        "generated_at": timestamp,
        "fusion_config": {
            "vector_rank_limit": DEFAULT_VECTOR_RANK_LIMIT,
            "family_score_thresholds": DEFAULT_FAMILY_THRESHOLDS,
            "family_caps": DEFAULT_FAMILY_CAPS,
            "total_vector_supplement_cap": DEFAULT_CASE_SUPPLEMENT_CAP,
            "deterministic_pass_guard": True,
            "threshold_policy": "conservative prototype defaults",
        },
        "case_count": len(hybrid_cases),
        "deterministic_pass_partial_fail": _count_judgments(deterministic_payload["cases"]),
        "vector_pass_partial_fail": _count_judgments(vector_payload["cases"]),
        "hybrid_pass_partial_fail": _count_judgments(hybrid_cases),
        "input_hashes": {
            "deterministic_baseline_sha256": _sha256_file(deterministic_baseline_path),
            "vector_baseline_sha256": _sha256_file(vector_baseline_path),
            "golden_set_sha256": _sha256_file(golden_set_path),
        },
        "sanity_checks_passed": True,
    }
    return HybridBaselineArtifacts(
        results_payload=results_payload,
        coverage_payload=coverage_payload,
        manifest_payload=manifest_payload,
        comparison_payload=comparison_payload,
        comparison_markdown=comparison_markdown,
        deterministic_payload=deterministic_payload,
        vector_payload=vector_payload,
    )


def write_hybrid_outputs(
    *,
    artifacts: HybridBaselineArtifacts,
    output_path: Path,
    coverage_path: Path,
    manifest_path: Path,
    comparison_path: Path,
) -> None:
    _write_json(output_path, artifacts.results_payload)
    _write_yaml(coverage_path, artifacts.coverage_payload)
    _write_yaml(manifest_path, artifacts.manifest_payload)
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(artifacts.comparison_markdown + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the M2B offline hybrid retrieval fusion baseline.")
    parser.add_argument("--golden-set", required=True, type=Path)
    parser.add_argument("--deterministic-baseline", required=True, type=Path)
    parser.add_argument("--vector-baseline", required=True, type=Path)
    parser.add_argument(
        "--vector-coverage",
        type=Path,
        default=Path("data_knowledge_eval/m2b/vector_coverage.m2b_legacy_v3.yaml"),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage-yaml", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--comparison-output", required=True, type=Path)
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    args = parser.parse_args()

    artifacts = build_hybrid_baseline_artifacts(
        golden_set_path=args.golden_set,
        deterministic_baseline_path=args.deterministic_baseline,
        vector_baseline_path=args.vector_baseline,
        vector_coverage_path=args.vector_coverage,
        generated_at=args.generated_at,
    )
    write_hybrid_outputs(
        artifacts=artifacts,
        output_path=args.output,
        coverage_path=args.coverage_yaml,
        manifest_path=args.manifest_output,
        comparison_path=args.comparison_output,
    )

    review_path = Path("docs/reviews/m2b-5-hybrid-retrieval-fusion-results.md")
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        _build_results_review_markdown(artifacts.results_payload, artifacts.comparison_payload) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
