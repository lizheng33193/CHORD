from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


ASSET_FILES = (
    "catalog_tables.yaml",
    "catalog_fields.yaml",
    "glossary_terms.yaml",
    "business_rules.yaml",
    "cohort_definitions.yaml",
    "sql_example_patterns.yaml",
    "sql_error_cases.yaml",
    "canonical_field_policies.yaml",
)

RUNTIME_IMPORTABLE_TYPES = {
    "catalog_table",
    "catalog_field",
    "glossary_term",
    "sql_example_pattern",
    "sql_error_case",
}

PROMOTION_DECISIONS = {
    "promote_now",
    "defer_needs_review",
    "eval_only",
    "future_profile_skill_only",
    "rejected",
}

SEED_IMPORT_DECISIONS = {
    "import_now",
    "manifest_only",
    "not_imported",
}

SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|pwd)\b"),
    re.compile(r"(?i)pymysql\.connect"),
    re.compile(r"(?i)create_engine"),
    re.compile(r"(?i)\bhost\s*="),
    re.compile(r"(?i)\buser\s*="),
    re.compile(r"(?i)jdbc:"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
)

DIRTY_SQL_PATTERNS = (
    re.compile(r"\bdm_model\.yx_tmp_[a-z0-9_]*", re.IGNORECASE),
    re.compile(r"\buid_str\b", re.IGNORECASE),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b20\d{6}\b"),
)


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to promote M2B extracted assets. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def write_yaml(path: Path, payload: Any) -> None:
    _require_yaml()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path) -> Any:
    _require_yaml()
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_candidate_assets(assets_dir: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for name in ASSET_FILES:
        payload = _read_yaml(assets_dir / name) or []
        if not isinstance(payload, list):
            raise ValueError(f"{name} must contain a top-level list")
        assets.extend(payload)
    return assets


def _normalize_country(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"", "common"}:
        return None
    return normalized


def _short_table_name(table_name: str | None) -> str | None:
    if not table_name:
        return None
    normalized = str(table_name).strip()
    if not normalized:
        return None
    return normalized.split(".")[-1]


def _normalize_field_hint(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip()


def _stable_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(data.encode('utf-8')).hexdigest()}"


def _seed_status_for_country(country: str | None) -> str:
    return "active"


def _promotion_for_asset(asset: dict[str, Any]) -> tuple[str, str]:
    runtime_allowed = str(asset.get("runtime_allowed") or "").strip()
    confidence = str(asset.get("confidence") or "").strip().lower()
    asset_type = str(asset.get("asset_type") or "").strip()
    review_status = str(asset.get("review_status") or "").strip().lower()

    if runtime_allowed == "eval_only" or asset_type == "sql_error_case":
        return "eval_only", "not_imported"
    if runtime_allowed == "future_profile_skill_only":
        return "future_profile_skill_only", "not_imported"
    if asset_type == "canonical_field_policy" or review_status == "needs_human_review":
        return "defer_needs_review", "not_imported"
    if asset_type in {"business_rule", "cohort_definition"}:
        if confidence in {"high", "medium"}:
            return "promote_now", "manifest_only"
        return "defer_needs_review", "not_imported"
    if asset_type in {"catalog_table", "catalog_field", "glossary_term", "sql_example_pattern"}:
        if runtime_allowed == "sanitized_only" and confidence == "high":
            return "promote_now", "import_now"
        return "defer_needs_review", "not_imported"
    return "rejected", "not_imported"


def build_promotion_manifest(assets: list[dict[str, Any]], *, source_namespace: str) -> dict[str, Any]:
    manifest_assets: list[dict[str, Any]] = []
    for asset in sorted(assets, key=lambda item: str(item["asset_id"])):
        promotion_decision, seed_import_decision = _promotion_for_asset(asset)
        manifest_assets.append(
            {
                "asset_id": asset["asset_id"],
                "asset_type": asset["asset_type"],
                "country": asset.get("country"),
                "domain": asset.get("domain"),
                "confidence": asset.get("confidence"),
                "runtime_allowed": asset.get("runtime_allowed"),
                "promotion_decision": promotion_decision,
                "seed_import_decision": seed_import_decision,
                "source_namespace": source_namespace,
                "source_key": asset["asset_id"],
                "review_status": asset.get("review_status"),
                "source_files": asset.get("source_files") or [],
            }
        )
    return {
        "schema_version": "m2b_seed_promotion_manifest_v1",
        "source_namespace": source_namespace,
        "assets": manifest_assets,
    }


def _build_catalog_table_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    full_table_name = str(asset["table_name"])
    short_table_name = _short_table_name(full_table_name)
    time_fields = list(asset.get("time_fields") or [])
    partition_fields = list(asset.get("partition_fields") or [])
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "table_name": short_table_name,
        "domain": asset.get("domain"),
        "description": asset.get("description"),
        "purpose": "Promoted from M2B structured extraction candidate asset.",
        "grain": asset.get("grain"),
        "time_field": _normalize_field_hint(time_fields[0] if time_fields else None),
        "partition_field": _normalize_field_hint(partition_fields[0] if partition_fields else None),
        "join_keys": list(asset.get("join_keys") or []),
        "common_filters": [],
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "physical_table_names": [full_table_name],
            "primary_entities": list(asset.get("primary_entities") or []),
            "notes": list(asset.get("notes") or []),
        },
    }


def _build_catalog_field_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    aliases = list(asset.get("aliases") or [])
    semantic = str(asset.get("semantic") or "").strip()
    usage = list(asset.get("usage") or [])
    description = str(asset.get("description") or "").strip()
    business_meaning_parts = []
    if semantic:
        business_meaning_parts.append(f"semantic={semantic}")
    if aliases:
        business_meaning_parts.append(f"aliases={', '.join(aliases)}")
    if usage:
        business_meaning_parts.append(f"usage={', '.join(usage)}")
    if asset.get("is_join_key"):
        business_meaning_parts.append("join_key=true")
    if asset.get("is_partition_field"):
        business_meaning_parts.append("partition_field=true")
    if asset.get("is_business_time"):
        business_meaning_parts.append("business_time=true")
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "table_name": _short_table_name(asset.get("table_name")),
        "field_name": asset.get("field_name"),
        "field_type": asset.get("field_type"),
        "description": description,
        "business_meaning": "; ".join(business_meaning_parts) or None,
        "is_sensitive": False,
        "join_hint": "primary join key" if asset.get("is_join_key") else None,
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "aliases": aliases,
            "semantic": semantic or None,
            "usage": usage,
            "table_name_full": asset.get("table_name"),
            "is_join_key": bool(asset.get("is_join_key")),
            "is_partition_field": bool(asset.get("is_partition_field")),
            "is_business_time": bool(asset.get("is_business_time")),
        },
    }


def _build_glossary_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "term": asset.get("term"),
        "synonyms": list(asset.get("aliases") or []),
        "definition": asset.get("definition"),
        "mapped_tables": [_short_table_name(name) for name in asset.get("mapped_tables", []) if _short_table_name(name)],
        "mapped_fields": [str(name).strip() for name in asset.get("mapped_fields", []) if str(name).strip()],
        "suggested_filters": list(asset.get("suggested_filters") or []),
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "runtime_allowed": asset.get("runtime_allowed"),
            "aliases": list(asset.get("aliases") or []),
            "related_rules": list(asset.get("related_rules") or []),
            "domain": asset.get("domain"),
        },
    }


def _build_sql_example_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    tables_used = [_short_table_name(asset.get("table_name"))] if asset.get("table_name") else []
    scenario = str(asset.get("scenario") or asset.get("asset_id")).strip()
    required_fields = [str(name).strip() for name in asset.get("required_output_fields", []) if str(name).strip()]
    hash_payload = {
        "asset_id": asset["asset_id"],
        "scenario": scenario,
        "pattern_summary": list(asset.get("pattern_summary") or []),
        "required_output_fields": required_fields,
    }
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": _seed_status_for_country(asset.get("country")),
        "natural_language_request": scenario.replace("_", " "),
        "run_type": "bucket_writeback" if asset.get("domain") == "behavior" else "cohort_query",
        "output_bucket": "behavior" if asset.get("domain") == "behavior" else None,
        "sql_hash": _stable_hash(hash_payload),
        "sql_text": None,
        "tables_used": tables_used,
        "fields_used": required_fields,
        "pattern_summary": " | ".join(asset.get("pattern_summary") or []),
        "reviewer_username": "m2b_seed_promotion",
        "execution_status": "pattern_only",
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "kind": "sql_example_pattern",
            "scenario": scenario,
            "pattern_summary": list(asset.get("pattern_summary") or []),
            "required_output_fields": required_fields,
            "forbidden_copy": list(asset.get("forbidden_copy") or []),
            "executable": False,
            "raw_sql_available": False,
        },
    }


def _build_sql_error_case_seed(asset: dict[str, Any], *, source_key: str) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "country": asset.get("country"),
        "status": "open",
        "natural_language_request": asset.get("scenario"),
        "run_type": "cohort_query",
        "output_bucket": None,
        "error_type": asset.get("bad_pattern_category") or asset.get("scenario"),
        "error_message": asset.get("risk"),
        "failed_sql_hash": _stable_hash({"asset_id": asset["asset_id"], "risk": asset.get("risk")}),
        "failed_sql_text": None,
        "fixed_sql_hash": None,
        "fixed_sql_text": None,
        "fix_summary": asset.get("expected_fix"),
        "detected_tables": [],
        "detected_fields": [],
        "source_files": list(asset.get("source_files") or []),
        "confidence": asset.get("confidence"),
        "review_status": asset.get("review_status"),
        "metadata": {
            "asset_id": asset["asset_id"],
            "kind": "sql_error_case",
            "warning_categories": list(asset.get("warning_categories") or []),
            "executable": False,
            "raw_sql_available": False,
        },
    }


def build_seed_patch_payload(
    *,
    assets: list[dict[str, Any]],
    manifest: dict[str, Any],
    source_namespace: str,
    generated_from_manifest: str,
) -> dict[str, Any]:
    by_asset_id = {asset["asset_id"]: asset for asset in assets}
    payload = {
        "schema_version": "m2b_seed_patch_v1",
        "source_namespace": source_namespace,
        "generated_from_manifest": generated_from_manifest,
        "catalog_tables": [],
        "catalog_fields": [],
        "glossary_terms": [],
        "sql_examples": [],
        "sql_error_cases": [],
    }
    for decision in manifest["assets"]:
        if decision["seed_import_decision"] != "import_now":
            continue
        asset = by_asset_id[decision["asset_id"]]
        source_key = decision["source_key"]
        asset_type = asset["asset_type"]
        if asset_type == "catalog_table":
            payload["catalog_tables"].append(_build_catalog_table_seed(asset, source_key=source_key))
        elif asset_type == "catalog_field":
            payload["catalog_fields"].append(_build_catalog_field_seed(asset, source_key=source_key))
        elif asset_type == "glossary_term":
            payload["glossary_terms"].append(_build_glossary_seed(asset, source_key=source_key))
        elif asset_type == "sql_example_pattern":
            payload["sql_examples"].append(_build_sql_example_seed(asset, source_key=source_key))
        elif asset_type == "sql_error_case":
            payload["sql_error_cases"].append(_build_sql_error_case_seed(asset, source_key=source_key))
    return payload


def validate_seed_patch_payload(payload: dict[str, Any]) -> None:
    required_top_level = {
        "schema_version",
        "source_namespace",
        "generated_from_manifest",
        "catalog_tables",
        "catalog_fields",
        "glossary_terms",
        "sql_examples",
        "sql_error_cases",
    }
    missing = required_top_level - set(payload)
    if missing:
        raise ValueError(f"seed patch missing top-level keys: {sorted(missing)}")
    if payload["source_namespace"] != "m2b_legacy_v1":
        raise ValueError("seed patch source_namespace must be m2b_legacy_v1")

    seen_source_keys: set[str] = set()
    for family_name in ("catalog_tables", "catalog_fields", "glossary_terms", "sql_examples", "sql_error_cases"):
        items = payload.get(family_name) or []
        if not isinstance(items, list):
            raise ValueError(f"{family_name} must be a list")
        for item in items:
            source_key = str(item.get("source_key") or "").strip()
            if not source_key:
                raise ValueError(f"{family_name} entry missing source_key")
            if source_key in seen_source_keys:
                raise ValueError(f"duplicate source_key in seed patch: {source_key}")
            seen_source_keys.add(source_key)
            text = json.dumps(item, ensure_ascii=False, sort_keys=True)
            for pattern in SENSITIVE_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"sensitive content detected in seed patch entry: {source_key}")
            for pattern in DIRTY_SQL_PATTERNS:
                if pattern.search(text):
                    raise ValueError(f"dirty SQL template detected in seed patch entry: {source_key}")
            if family_name == "sql_examples":
                metadata = dict(item.get("metadata") or {})
                if item.get("sql_text") is not None:
                    raise ValueError("sql example pattern seed must keep sql_text as null")
                if metadata.get("kind") != "sql_example_pattern":
                    raise ValueError("sql example pattern seed metadata.kind must be sql_example_pattern")
                if metadata.get("executable") is not False:
                    raise ValueError("sql example pattern seed metadata.executable must be false")
                if metadata.get("raw_sql_available") is not False:
                    raise ValueError("sql example pattern seed metadata.raw_sql_available must be false")


def _family_counts(manifest: dict[str, Any]) -> dict[str, Counter]:
    counters: dict[str, Counter] = defaultdict(Counter)
    for item in manifest["assets"]:
        counters[item["asset_type"]][item["promotion_decision"]] += 1
        counters[item["asset_type"]][f"seed::{item['seed_import_decision']}"] += 1
    return counters


def build_review_markdown(*, manifest: dict[str, Any], seed_payload: dict[str, Any]) -> str:
    promotion_counts = Counter(item["promotion_decision"] for item in manifest["assets"])
    import_counts = Counter(item["seed_import_decision"] for item in manifest["assets"])
    family_counts = _family_counts(manifest)
    lines = [
        "# M2B-2 Seed Promotion Review",
        "",
        "This review records the M2B-2 promotion decisions for M2B-1 candidate assets.",
        "",
        "## Summary",
        "",
        f"- source_namespace: `{manifest['source_namespace']}`",
        f"- total candidate assets: `{len(manifest['assets'])}`",
        f"- promote_now: `{promotion_counts['promote_now']}`",
        f"- defer_needs_review: `{promotion_counts['defer_needs_review']}`",
        f"- eval_only: `{promotion_counts['eval_only']}`",
        f"- future_profile_skill_only: `{promotion_counts['future_profile_skill_only']}`",
        f"- rejected: `{promotion_counts['rejected']}`",
        f"- import_now: `{import_counts['import_now']}`",
        f"- manifest_only: `{import_counts['manifest_only']}`",
        f"- not_imported: `{import_counts['not_imported']}`",
        "",
        "## Runtime Seed Families",
        "",
        f"- catalog_tables: `{len(seed_payload['catalog_tables'])}`",
        f"- catalog_fields: `{len(seed_payload['catalog_fields'])}`",
        f"- glossary_terms: `{len(seed_payload['glossary_terms'])}`",
        f"- sql_examples: `{len(seed_payload['sql_examples'])}`",
        f"- sql_error_cases: `{len(seed_payload['sql_error_cases'])}`",
        "",
        "## Asset-Type Decisions",
        "",
    ]
    for asset_type in sorted(family_counts):
        counter = family_counts[asset_type]
        lines.append(
            f"- `{asset_type}`: promote_now={counter['promote_now']}, defer_needs_review={counter['defer_needs_review']}, eval_only={counter['eval_only']}, import_now={counter['seed::import_now']}, manifest_only={counter['seed::manifest_only']}, not_imported={counter['seed::not_imported']}"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Pattern examples are non-executable guidance, not SQL candidates.",
            "- Canonical policies marked `needs_human_review` stay out of runtime seed import.",
            "- Business rules and cohort definitions remain manifest-only in M2B-2 because the current runtime seed schema does not support them directly.",
            "- Eval-only error cases remain outside the runtime deterministic retriever unless a later phase adds a safe import shape.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote M2B extracted candidate assets into an isolated seed patch.")
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--seed-output", required=True, type=Path)
    parser.add_argument("--review-output", required=True, type=Path)
    parser.add_argument("--source-namespace", default="m2b_legacy_v1")
    args = parser.parse_args()

    assets = load_candidate_assets(args.assets_dir)
    manifest = build_promotion_manifest(assets, source_namespace=args.source_namespace)
    seed_payload = build_seed_patch_payload(
        assets=assets,
        manifest=manifest,
        source_namespace=args.source_namespace,
        generated_from_manifest=str(args.manifest),
    )
    validate_seed_patch_payload(seed_payload)

    write_yaml(args.manifest, manifest)
    write_yaml(args.seed_output, seed_payload)
    args.review_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_output.write_text(
        build_review_markdown(manifest=manifest, seed_payload=seed_payload) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
