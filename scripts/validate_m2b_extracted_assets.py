from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - environment specific
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from scripts.run_m2b_retrieval_baseline import load_golden_cases


ASSET_FILE_ORDER = (
    "catalog_tables.yaml",
    "catalog_fields.yaml",
    "glossary_terms.yaml",
    "business_rules.yaml",
    "cohort_definitions.yaml",
    "sql_example_patterns.yaml",
    "sql_error_cases.yaml",
    "canonical_field_policies.yaml",
)

SOURCE_MAP_FILE = "asset_source_map.yaml"
RUNTIME_ALLOWED = {
    "sanitized_only",
    "eval_only",
    "future_profile_skill_only",
    "no_raw_runtime",
}
EXTRACTION_STATUSES = {
    "extracted",
    "partial",
    "deferred",
    "inventory_only",
    "future_profile_skill_only",
}
PRIORITY_CASE_IDS = {
    "mx-high-risk-cohort",
    "mx-recent-7d-risk-users",
    "mx-first-loan-never-overdue",
    "mx-mob1-settled-7d-churn",
    "mx-behavior-writeback",
    "mx-glossary-combo-writeback",
    "mx-app-profile-query",
    "mx-credit-profile-query",
    "th-asset-snapshot-query",
    "th-risk-apply-query",
    "th-ask-loan-risk-query",
    "th-third-party-risk-query",
    "dws-renewal-loan-segment-query",
    "dws-fox-boc-behavior-query",
}
DIRTY_SQL_PATTERN_REGEXES = (
    re.compile(r"\bdm_model\.yx_tmp_[a-zA-Z0-9_]*"),
    re.compile(r"\buid_str(?:_[A-Z])?\b"),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b20\d{6}\b"),
)
SENSITIVE_REGEXES = (
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\b\s*[:=]\s*['\"][^'\"]+['\"]")),
    ("connection_call", re.compile(r"(?i)\b(pymysql\.connect|create_engine)\b")),
    ("host", re.compile(r"(?i)\bhost\s*=\s*['\"][^'\"]+['\"]")),
    ("user", re.compile(r"(?i)\buser\s*=\s*['\"][^'\"]+['\"]")),
    ("jdbc", re.compile(r"(?i)\bjdbc:")),
)
IP_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

ASSET_REQUIRED_FIELDS: dict[str, set[str]] = {
    "catalog_table": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "table_name",
        "description",
        "grain",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "catalog_field": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "table_name",
        "field_name",
        "field_type",
        "semantic",
        "description",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "glossary_term": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "term",
        "definition",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "business_rule": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "name",
        "description",
        "rule_summary",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "cohort_definition": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "name",
        "definition",
        "required_conditions",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "sql_example_pattern": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "scenario",
        "pattern_summary",
        "required_output_fields",
        "forbidden_copy",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "sql_error_case": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "scenario",
        "bad_pattern_category",
        "risk",
        "expected_fix",
        "source_files",
        "confidence",
        "runtime_allowed",
    },
    "canonical_field_policy": {
        "asset_id",
        "asset_type",
        "country",
        "domain",
        "business_semantic",
        "table_name",
        "preferred_fields",
        "source_files",
        "confidence",
        "runtime_allowed",
        "review_status",
    },
}
SOURCE_MAP_REQUIRED_FIELDS = {
    "source_file",
    "source_group",
    "extraction_status",
    "extracted_asset_types",
    "risk_level",
    "runtime_policy",
}


def load_yaml_file(path: Path) -> Any:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to validate M2B extracted assets. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def flatten_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(flatten_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(flatten_strings(item))
    return strings


def detect_sensitive_pattern(text: str) -> str | None:
    for label, regex in SENSITIVE_REGEXES:
        if regex.search(text):
            return label
    for candidate in IP_REGEX.findall(text):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return "ip"
    return None


def ensure_list(value: Any, *, field_name: str, asset_id: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"Asset '{asset_id}' field '{field_name}' must be a list")


def validate_source_files(source_files: Any, *, asset_id: str) -> None:
    ensure_list(source_files, field_name="source_files", asset_id=asset_id)
    for source in source_files:
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"Asset '{asset_id}' has invalid source_files entry")
        if "/" in source or "\\" in source or "\n" in source:
            raise ValueError(f"Asset '{asset_id}' source_files must contain bare filenames only")


def validate_asset_item(asset: dict[str, Any]) -> None:
    asset_id = str(asset.get("asset_id", "")).strip()
    asset_type = str(asset.get("asset_type", "")).strip()
    if asset_type not in ASSET_REQUIRED_FIELDS:
        raise ValueError(f"Asset '{asset_id or '<missing>'}' has unsupported asset_type: {asset_type}")
    missing = [field for field in ASSET_REQUIRED_FIELDS[asset_type] if field not in asset]
    if missing:
        raise ValueError(f"Asset '{asset_id}' is missing required fields: {', '.join(sorted(missing))}")
    if not asset_id:
        raise ValueError("Asset is missing asset_id")
    runtime_allowed = asset.get("runtime_allowed")
    if runtime_allowed not in RUNTIME_ALLOWED:
        raise ValueError(f"Asset '{asset_id}' has invalid runtime_allowed: {runtime_allowed}")
    validate_source_files(asset.get("source_files"), asset_id=asset_id)
    for key in ("country", "domain", "confidence"):
        if not str(asset.get(key, "")).strip():
            raise ValueError(f"Asset '{asset_id}' field '{key}' must be non-empty")
    for field_name in (
        "aliases",
        "pattern_summary",
        "required_output_fields",
        "forbidden_copy",
        "rule_summary",
        "required_conditions",
        "preferred_fields",
    ):
        if field_name in asset:
            ensure_list(asset[field_name], field_name=field_name, asset_id=asset_id)

    sensitive_hit = detect_sensitive_pattern("\n".join(flatten_strings(asset)))
    if sensitive_hit:
        raise ValueError(f"Asset '{asset_id}' contains sensitive pattern: {sensitive_hit}")

    if asset_type == "sql_example_pattern":
        sql_text = "\n".join(flatten_strings(asset))
        for regex in DIRTY_SQL_PATTERN_REGEXES:
            if regex.search(sql_text):
                raise ValueError(f"Asset '{asset_id}' contains dirty sql pattern")


def validate_source_map(source_map_items: list[dict[str, Any]], *, docs_dir: Path | None) -> None:
    seen_sources: set[str] = set()
    for item in source_map_items:
        missing = [field for field in SOURCE_MAP_REQUIRED_FIELDS if field not in item]
        if missing:
            source_name = item.get("source_file", "<missing>")
            raise ValueError(f"Source map item '{source_name}' missing fields: {', '.join(sorted(missing))}")
        source_file = str(item["source_file"]).strip()
        if not source_file:
            raise ValueError("Source map item has empty source_file")
        if source_file in seen_sources:
            raise ValueError(f"duplicate source_file in source map: {source_file}")
        seen_sources.add(source_file)
        if item["extraction_status"] not in EXTRACTION_STATUSES:
            raise ValueError(f"Source map item '{source_file}' has invalid extraction_status: {item['extraction_status']}")
        if item["runtime_policy"] not in RUNTIME_ALLOWED:
            raise ValueError(f"Source map item '{source_file}' has invalid runtime_policy: {item['runtime_policy']}")
        ensure_list(item["extracted_asset_types"], field_name="extracted_asset_types", asset_id=source_file)
        if item["extraction_status"] == "deferred" and not str(item.get("deferred_reason", "")).strip():
            raise ValueError(f"Source map item '{source_file}' must include deferred_reason")

    if docs_dir and docs_dir.exists():
        valid_sources = []
        for path in docs_dir.iterdir():
            if not path.is_file():
                continue
            if path.name == "README.md" or path.name == ".DS_Store":
                continue
            valid_sources.append(path.name)
        missing_sources = sorted(set(valid_sources) - seen_sources)
        if missing_sources:
            raise ValueError(f"asset_source_map.yaml is missing source files: {', '.join(missing_sources)}")


def build_indexes(assets: list[dict[str, Any]]) -> dict[str, Any]:
    tables = {asset["table_name"]: asset for asset in assets if asset["asset_type"] == "catalog_table"}
    fields_by_lookup: dict[str, list[dict[str, Any]]] = {}
    glossary_by_term: dict[str, dict[str, Any]] = {}
    patterns_by_key: dict[str, dict[str, Any]] = {}
    errors_by_key: dict[str, dict[str, Any]] = {}
    cohorts = [asset for asset in assets if asset["asset_type"] == "cohort_definition"]
    rules = [asset for asset in assets if asset["asset_type"] == "business_rule"]

    for asset in assets:
        if asset["asset_type"] == "catalog_field":
            lookups = [asset["field_name"], str(asset.get("semantic", ""))]
            lookups.extend(str(alias) for alias in asset.get("aliases", []))
            for lookup in lookups:
                if lookup:
                    fields_by_lookup.setdefault(lookup, []).append(asset)
        elif asset["asset_type"] == "glossary_term":
            glossary_by_term[asset["term"]] = asset
            for alias in asset.get("aliases", []):
                glossary_by_term[str(alias)] = asset
        elif asset["asset_type"] == "sql_example_pattern":
            patterns_by_key[asset["asset_id"]] = asset
            patterns_by_key[str(asset.get("scenario", ""))] = asset
        elif asset["asset_type"] == "sql_error_case":
            errors_by_key[asset["asset_id"]] = asset
            errors_by_key[str(asset.get("bad_pattern_category", ""))] = asset
            errors_by_key[str(asset.get("scenario", ""))] = asset

    return {
        "tables": tables,
        "fields_by_lookup": fields_by_lookup,
        "glossary_by_term": glossary_by_term,
        "patterns_by_key": patterns_by_key,
        "errors_by_key": errors_by_key,
        "cohorts": cohorts,
        "rules": rules,
    }


def add_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


def add_case_hints(case_id: str, indexes: dict[str, Any], covered_assets: list[str]) -> None:
    hint_map = {
        "mx-mob1-settled-7d-churn": [
            "glossary.common.mob1",
            "rule.common.full_settlement",
            "rule.common.seven_day_no_reborrow",
            "cohort.mx.mob1_settled_7d_churn",
            "sql_pattern.mx.mob1_churn_cte",
            "error_case.common.missing_reborrow_anti_join",
            "error_case.common.missing_settlement_7d_observation",
        ],
        "mx-behavior-writeback": [
            "glossary.mx.writeback_behavior",
            "glossary.mx.uid_cohort_required",
            "sql_pattern.mx.behavior_writeback_target_cohort",
            "error_case.mx.broad_behavior_scan",
        ],
        "mx-glossary-combo-writeback": [
            "glossary.mx.high_risk",
            "glossary.mx.recent_7d",
            "glossary.mx.writeback_behavior",
            "sql_pattern.mx.behavior_writeback_target_cohort",
            "error_case.common.historical_template_drift",
        ],
        "dws-renewal-loan-segment-query": [
            "glossary.common.mob1",
            "glossary.multi.settled_over_3m",
        ],
        "dws-fox-boc-behavior-query": [
            "glossary.multi.collection_behavior",
            "glossary.multi.contact_outcome",
        ],
    }
    known_ids = {asset["asset_id"] for asset in indexes["cohorts"] + indexes["rules"]}
    known_ids.update(asset["asset_id"] for asset in indexes["tables"].values())
    known_ids.update(asset["asset_id"] for assets in indexes["fields_by_lookup"].values() for asset in assets)
    known_ids.update(asset["asset_id"] for asset in indexes["glossary_by_term"].values())
    known_ids.update(asset["asset_id"] for asset in indexes["patterns_by_key"].values())
    known_ids.update(asset["asset_id"] for asset in indexes["errors_by_key"].values())
    for asset_id in hint_map.get(case_id, []):
        if asset_id in known_ids:
            add_unique(covered_assets, asset_id)


def build_case_coverage(case: dict[str, Any], indexes: dict[str, Any]) -> dict[str, Any]:
    covered_assets: list[str] = []
    missing_assets: list[str] = []

    for table_name in case["expected_tables"]:
        asset = indexes["tables"].get(table_name)
        if asset:
            add_unique(covered_assets, asset["asset_id"])
        else:
            missing_assets.append(f"table:{table_name}")

    for field_name in case["expected_fields"]:
        field_assets = indexes["fields_by_lookup"].get(field_name, [])
        if field_assets:
            add_unique(covered_assets, field_assets[0]["asset_id"])
        else:
            missing_assets.append(f"field:{field_name}")

    for term in case["expected_glossary_terms"]:
        asset = indexes["glossary_by_term"].get(term)
        if asset:
            add_unique(covered_assets, asset["asset_id"])
        else:
            missing_assets.append(f"glossary:{term}")

    for pattern_key in case["expected_sql_examples"]:
        asset = indexes["patterns_by_key"].get(pattern_key)
        if asset:
            add_unique(covered_assets, asset["asset_id"])
        else:
            missing_assets.append(f"sql_example:{pattern_key}")

    for error_key in case["forbidden_examples"]:
        asset = indexes["errors_by_key"].get(error_key)
        if asset:
            add_unique(covered_assets, asset["asset_id"])

    add_case_hints(case["case_id"], indexes, covered_assets)

    if case["case_id"] not in PRIORITY_CASE_IDS and not covered_assets:
        coverage_judgment = "deferred"
        notes = ["Not part of the first-batch priority scope for M2B-1."]
    elif not covered_assets:
        coverage_judgment = "none"
        notes = ["No first-batch extracted assets currently match this case."]
    elif not missing_assets:
        coverage_judgment = "covered"
        notes = ["All expected grounding dimensions have at least one matching extracted asset."]
    else:
        coverage_judgment = "partial"
        notes = ["Case has partial first-batch coverage; missing assets should be revisited in later extraction rounds."]

    return {
        "case_id": case["case_id"],
        "covered_assets": covered_assets,
        "missing_assets": missing_assets,
        "coverage_judgment": coverage_judgment,
        "notes": notes,
    }


def render_coverage_markdown(case_coverages: list[dict[str, Any]]) -> str:
    lines = [
        "# M2B-1 Golden Set Coverage",
        "",
        "This report summarizes first-batch structured knowledge coverage for the current `M2B-1` extracted assets.",
        "Coverage is lightweight and case-oriented; it is not a real retriever benchmark.",
        "",
        "| case_id | coverage_judgment | covered_assets | missing_assets | notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in case_coverages:
        covered = ", ".join(item["covered_assets"]) if item["covered_assets"] else "-"
        missing = ", ".join(item["missing_assets"]) if item["missing_assets"] else "-"
        notes = " ".join(item["notes"])
        lines.append(f"| {item['case_id']} | {item['coverage_judgment']} | {covered} | {missing} | {notes} |")
    lines.append("")
    return "\n".join(lines)


def load_assets_dir(assets_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assets: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    for filename in ASSET_FILE_ORDER:
        path = assets_dir / filename
        payload = load_yaml_file(path)
        if not isinstance(payload, list):
            raise ValueError(f"{filename} must contain a top-level list")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"{filename} entries must be mappings")
            validate_asset_item(item)
            asset_id = item["asset_id"]
            if asset_id in seen_asset_ids:
                raise ValueError(f"duplicate asset_id: {asset_id}")
            seen_asset_ids.add(asset_id)
            assets.append(item)

    source_map_path = assets_dir / SOURCE_MAP_FILE
    source_map_payload = load_yaml_file(source_map_path)
    if not isinstance(source_map_payload, list):
        raise ValueError(f"{SOURCE_MAP_FILE} must contain a top-level list")
    if not all(isinstance(item, dict) for item in source_map_payload):
        raise ValueError(f"{SOURCE_MAP_FILE} entries must be mappings")
    return assets, source_map_payload


def validate_assets_dir(
    assets_dir: Path,
    golden_set: Path,
    *,
    coverage_output: Path | None = None,
    coverage_yaml: Path | None = None,
) -> dict[str, Any]:
    assets, source_map_payload = load_assets_dir(assets_dir)
    docs_dir = assets_dir.parents[2] / "docs" / "knowledge-base" if len(assets_dir.parents) >= 3 else None
    validate_source_map(source_map_payload, docs_dir=docs_dir)
    cases = load_golden_cases(golden_set)
    indexes = build_indexes(assets)
    case_coverages = [build_case_coverage(case, indexes) for case in cases]

    if coverage_output:
        coverage_output.parent.mkdir(parents=True, exist_ok=True)
        coverage_output.write_text(render_coverage_markdown(case_coverages), encoding="utf-8")
    if coverage_yaml:
        coverage_yaml.parent.mkdir(parents=True, exist_ok=True)
        if yaml is None:  # pragma: no cover - same as load_yaml_file
            raise RuntimeError("PyYAML is required to write coverage YAML.") from YAML_IMPORT_ERROR
        coverage_yaml.write_text(yaml.safe_dump(case_coverages, allow_unicode=True, sort_keys=False), encoding="utf-8")

    covered_case_count = sum(
        1
        for item in case_coverages
        if item["case_id"] in PRIORITY_CASE_IDS and item["coverage_judgment"] in {"partial", "covered"}
    )
    return {
        "asset_count": len(assets),
        "source_count": len(source_map_payload),
        "case_count": len(case_coverages),
        "covered_case_count": covered_case_count,
        "coverage": case_coverages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate M2B-1 structured extracted assets and generate a coverage report.")
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--golden-set", required=True, type=Path)
    parser.add_argument("--coverage-output", required=True, type=Path)
    parser.add_argument("--coverage-yaml", type=Path)
    args = parser.parse_args()

    result = validate_assets_dir(
        args.assets_dir,
        args.golden_set,
        coverage_output=args.coverage_output,
        coverage_yaml=args.coverage_yaml,
    )
    print(
        json.dumps(
            {
                "asset_count": result["asset_count"],
                "source_count": result["source_count"],
                "case_count": result["case_count"],
                "covered_case_count": result["covered_case_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
