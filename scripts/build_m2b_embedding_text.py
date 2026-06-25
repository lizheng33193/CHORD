from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
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


SUPPORTED_FAMILIES: dict[str, str] = {
    "catalog_tables": "catalog_table",
    "catalog_fields": "catalog_field",
    "glossary_terms": "glossary_term",
    "sql_examples": "sql_example",
    "sql_error_cases": "sql_error_case",
}
EXCLUDED_FAMILIES = [
    "business_rules",
    "cohort_definitions",
    "canonical_field_policies",
]
PREVIEW_PRIORITY_KEYS = [
    "glossary.common.mob1.mx_runtime",
    "field.mx.dwd_w_apply.withdraw_uuid",
    "field.mx.dwd_w_apply.user_uuid",
    "field.mx.dwd_w_apply.asset_finish_at",
    "glossary.mx.credit_profile",
    "sql_pattern.mx.behavior_writeback_target_cohort",
]
SENSITIVE_REGEXES = (
    re.compile(r"(?i)\bpymysql\.connect\b"),
    re.compile(r"(?i)\bcreate_engine\b"),
    re.compile(r"(?i)\bjdbc:"),
    re.compile(r"(?i)\bhost\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)\buser\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]+['\"]"),
)
DIRTY_SQL_REGEXES = (
    re.compile(r"\bdm_model\.yx_tmp_[a-zA-Z0-9_]*"),
    re.compile(r"\buid_str(?:_[A-Z])?\b"),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b20\d{6}\b"),
)
IP_REGEX = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


@dataclass(slots=True)
class EmbeddingArtifacts:
    records: list[dict[str, Any]]
    manifest: dict[str, Any]
    preview_markdown: str


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to build M2B embedding records. Install project dependencies before running this script."
        ) from YAML_IMPORT_ERROR


def _load_seed_payload(seed_patch_path: Path) -> dict[str, Any]:
    _require_yaml()
    payload = yaml.safe_load(seed_patch_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("seed patch must be a mapping")
    return payload


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_strings(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_strings(item))
        return flattened
    return []


def _has_sensitive_text(text: str) -> bool:
    for regex in SENSITIVE_REGEXES:
        if regex.search(text):
            return True
    for candidate in IP_REGEX.findall(text):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        return True
    return False


def _has_dirty_sql(text: str) -> bool:
    for regex in DIRTY_SQL_REGEXES:
        if regex.search(text):
            return True
    return False


def _sorted_unique_tokens(values: list[str], *, limit: int = 30) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if "\n" in value:
            continue
        key = value.lower()
        if key in seen:
            continue
        result.append(value)
        seen.add(key)
        if len(result) >= limit:
            break
    return result


def _stable_record_id(*, source_namespace: str, source_key: str, asset_family: str) -> str:
    digest = hashlib.sha256(
        f"{source_namespace}|{source_key}|{asset_family}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_catalog_table_record(entry: dict[str, Any], source_namespace: str) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {})
    hints = _sorted_unique_tokens(
        [
            entry.get("table_name", ""),
            entry.get("domain", ""),
            entry.get("time_field", ""),
            entry.get("partition_field", ""),
            *(entry.get("join_keys") or []),
            *(metadata.get("physical_table_names") or []),
        ]
    )
    lines = [
        "Asset family: catalog_table",
        f"Country: {entry.get('country') or 'common'}",
        f"Title: {entry.get('table_name', '')}",
        f"Description: {entry.get('description', '')}",
        f"Purpose: {entry.get('purpose', '')}",
        f"Grain: {entry.get('grain', '')}",
        f"Join keys: {', '.join(entry.get('join_keys') or []) or 'none'}",
        f"Time field: {entry.get('time_field') or 'none'}",
        f"Partition field: {entry.get('partition_field') or 'none'}",
        f"Physical table names: {', '.join(metadata.get('physical_table_names') or []) or 'none'}",
        f"Notes: {' | '.join(metadata.get('notes') or []) or 'none'}",
    ]
    return _base_record(
        source_namespace=source_namespace,
        source_key=entry["source_key"],
        asset_family="catalog_table",
        country=entry.get("country"),
        title=entry.get("table_name", ""),
        embedding_text="\n".join(lines),
        search_hints=hints,
        metadata={
            "table_name": entry.get("table_name"),
            "domain": entry.get("domain"),
            "status": entry.get("status"),
            "source_files": entry.get("source_files") or [],
            "confidence": entry.get("confidence"),
            "review_status": entry.get("review_status"),
            "physical_table_names": metadata.get("physical_table_names") or [],
            "source_key": entry["source_key"],
        },
    )


def _build_catalog_field_record(entry: dict[str, Any], source_namespace: str) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {})
    aliases = metadata.get("aliases") or []
    usage = metadata.get("usage") or []
    lines = [
        "Asset family: catalog_field",
        f"Country: {entry.get('country') or 'common'}",
        f"Title: {entry.get('table_name', '')}.{entry.get('field_name', '')}",
        f"Description: {entry.get('description', '')}",
        f"Business meaning: {entry.get('business_meaning') or 'none'}",
        f"Field type: {entry.get('field_type') or 'unknown'}",
        f"Join hint: {entry.get('join_hint') or 'none'}",
        f"Aliases: {', '.join(aliases) or 'none'}",
        f"Usage: {', '.join(usage) or 'none'}",
        f"Physical table names: {', '.join(metadata.get('physical_table_names') or []) or 'none'}",
    ]
    return _base_record(
        source_namespace=source_namespace,
        source_key=entry["source_key"],
        asset_family="catalog_field",
        country=entry.get("country"),
        title=f"{entry.get('table_name', '')}.{entry.get('field_name', '')}",
        embedding_text="\n".join(lines),
        search_hints=_sorted_unique_tokens(
            [
                entry.get("table_name", ""),
                entry.get("field_name", ""),
                *(aliases or []),
                *(usage or []),
                entry.get("business_meaning") or "",
            ]
        ),
        metadata={
            "table_name": entry.get("table_name"),
            "field_name": entry.get("field_name"),
            "domain": metadata.get("domain") or entry.get("domain"),
            "status": entry.get("status"),
            "source_files": entry.get("source_files") or [],
            "confidence": entry.get("confidence"),
            "review_status": entry.get("review_status"),
            "physical_table_names": metadata.get("physical_table_names") or [],
            "source_key": entry["source_key"],
        },
    )


def _build_glossary_record(entry: dict[str, Any], source_namespace: str) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {})
    lines = [
        "Asset family: glossary_term",
        f"Country: {entry.get('country') or 'common'}",
        f"Title: {entry.get('term', '')}",
        f"Definition: {entry.get('definition', '')}",
        f"Synonyms: {', '.join(entry.get('synonyms') or []) or 'none'}",
        f"Mapped tables: {', '.join(entry.get('mapped_tables') or []) or 'none'}",
        f"Mapped fields: {', '.join(entry.get('mapped_fields') or []) or 'none'}",
        f"Suggested filters: {', '.join(entry.get('suggested_filters') or []) or 'none'}",
    ]
    return _base_record(
        source_namespace=source_namespace,
        source_key=entry["source_key"],
        asset_family="glossary_term",
        country=entry.get("country"),
        title=entry.get("term", ""),
        embedding_text="\n".join(lines),
        search_hints=_sorted_unique_tokens(
            [
                entry.get("term", ""),
                *(entry.get("synonyms") or []),
                *(entry.get("mapped_fields") or []),
                *(entry.get("mapped_tables") or []),
            ]
        ),
        metadata={
            "domain": metadata.get("domain"),
            "status": entry.get("status"),
            "source_files": entry.get("source_files") or [],
            "confidence": entry.get("confidence"),
            "review_status": entry.get("review_status"),
            "source_key": entry["source_key"],
        },
    )


def _build_sql_example_record(entry: dict[str, Any], source_namespace: str) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {})
    lines = [
        "Asset family: sql_example",
        f"Country: {entry.get('country') or 'common'}",
        f"Title: {entry.get('source_key', '')}",
        f"Request: {entry.get('natural_language_request', '')}",
        f"Pattern summary: {entry.get('pattern_summary') or 'none'}",
        f"Tables used: {', '.join(entry.get('tables_used') or []) or 'none'}",
        f"Fields used: {', '.join(entry.get('fields_used') or []) or 'none'}",
        f"Run type: {entry.get('run_type') or 'unknown'}",
        f"Output bucket: {entry.get('output_bucket') or 'none'}",
        "Non-executable pattern guidance.",
        "This record is not executable SQL.",
    ]
    return _base_record(
        source_namespace=source_namespace,
        source_key=entry["source_key"],
        asset_family="sql_example",
        country=entry.get("country"),
        title=entry.get("source_key", ""),
        embedding_text="\n".join(lines),
        search_hints=_sorted_unique_tokens(
            [
                entry.get("natural_language_request", ""),
                *(entry.get("fields_used") or []),
                *(metadata.get("match_tokens") or []),
                *(entry.get("tables_used") or []),
            ]
        ),
        metadata={
            "domain": None,
            "status": entry.get("status"),
            "source_files": entry.get("source_files") or [],
            "confidence": entry.get("confidence"),
            "review_status": entry.get("review_status"),
            "source_key": entry["source_key"],
            "kind": metadata.get("kind"),
            "executable": metadata.get("executable"),
            "raw_sql_available": metadata.get("raw_sql_available"),
        },
    )


def _build_sql_error_case_record(entry: dict[str, Any], source_namespace: str) -> dict[str, Any]:
    metadata = dict(entry.get("metadata") or {})
    lines = [
        "Asset family: sql_error_case",
        f"Country: {entry.get('country') or 'common'}",
        f"Title: {entry.get('source_key', '')}",
        f"Error type: {entry.get('error_type', '')}",
        f"Safe summary: {entry.get('error_message') or 'none'}",
        f"Risk: {metadata.get('risk') or 'none'}",
        f"Expected fix: {metadata.get('expected_fix') or 'none'}",
        f"Bad pattern category: {metadata.get('bad_pattern_category') or 'none'}",
    ]
    return _base_record(
        source_namespace=source_namespace,
        source_key=entry["source_key"],
        asset_family="sql_error_case",
        country=entry.get("country"),
        title=entry.get("source_key", ""),
        embedding_text="\n".join(lines),
        search_hints=_sorted_unique_tokens(
            [
                entry.get("error_type", ""),
                metadata.get("bad_pattern_category", ""),
            ]
        ),
        metadata={
            "domain": None,
            "status": entry.get("status"),
            "source_files": entry.get("source_files") or [],
            "confidence": entry.get("confidence"),
            "review_status": entry.get("review_status"),
            "source_key": entry["source_key"],
        },
    )


def _base_record(
    *,
    source_namespace: str,
    source_key: str,
    asset_family: str,
    country: str | None,
    title: str,
    embedding_text: str,
    search_hints: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": _stable_record_id(
            source_namespace=source_namespace,
            source_key=source_key,
            asset_family=asset_family,
        ),
        "source_namespace": source_namespace,
        "source_key": source_key,
        "asset_family": asset_family,
        "country": country or "common",
        "title": title,
        "embedding_text": embedding_text.strip(),
        "search_hints": _sorted_unique_tokens(search_hints),
        "metadata": metadata,
    }


def _validate_record(record: dict[str, Any]) -> None:
    if not record["embedding_text"].strip():
        raise ValueError(f"empty embedding_text for {record['source_key']}")
    if len(record["search_hints"]) > 30:
        raise ValueError(f"too many search_hints for {record['source_key']}")
    combined_text = "\n".join(_flatten_strings(record))
    if _has_sensitive_text(combined_text):
        raise ValueError(f"sensitive content detected in embedding record {record['source_key']}")
    if _has_dirty_sql(combined_text):
        raise ValueError(f"dirty SQL content detected in embedding record {record['source_key']}")


def _build_preview_markdown(records: list[dict[str, Any]], *, source_namespace: str, generated_at: str) -> str:
    by_key = {record["source_key"]: record for record in records}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in PREVIEW_PRIORITY_KEYS:
        record = by_key.get(key)
        if record is None or record["source_key"] in seen:
            continue
        selected.append(record)
        seen.add(record["source_key"])
    for record in records:
        if len(selected) >= 8:
            break
        if record["source_key"] in seen:
            continue
        selected.append(record)
        seen.add(record["source_key"])

    lines = [
        "# M2B-3 Embedding Text Preview",
        "",
        f"- source_namespace: `{source_namespace}`",
        f"- generated_at: `{generated_at}`",
        f"- sample_count: `{len(selected)}`",
        "",
    ]
    for record in selected:
        lines.extend(
            [
                f"## `{record['source_key']}`",
                "",
                f"- asset_family: `{record['asset_family']}`",
                f"- country: `{record['country']}`",
                f"- title: `{record['title']}`",
                "",
                "```text",
                record["embedding_text"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_embedding_artifacts(
    *,
    seed_patch_path: Path,
    generated_at: str | None = None,
    strict: bool = True,
) -> EmbeddingArtifacts:
    payload = _load_seed_payload(seed_patch_path)
    source_namespace = str(payload.get("source_namespace") or "").strip()
    if not source_namespace:
        raise ValueError("seed patch source_namespace is required")

    unknown_families = sorted(
        key for key in payload.keys() if key not in {"schema_version", "source_namespace", "generated_from_manifest", *SUPPORTED_FAMILIES}
    )
    if unknown_families and strict:
        raise ValueError(f"unsupported seed family: {unknown_families[0]}")

    timestamp = generated_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    builders = {
        "catalog_tables": _build_catalog_table_record,
        "catalog_fields": _build_catalog_field_record,
        "glossary_terms": _build_glossary_record,
        "sql_examples": _build_sql_example_record,
        "sql_error_cases": _build_sql_error_case_record,
    }

    records: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    skipped_counts = {
        "unsupported_family": 0,
        "inactive_status": 0,
        "empty_embedding_text": 0,
    }
    for family_name, asset_family in SUPPORTED_FAMILIES.items():
        entries = payload.get(family_name) or []
        if not isinstance(entries, list):
            raise ValueError(f"{family_name} must be a list")
        builder = builders[family_name]
        family_records: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{family_name} entries must be mappings")
            if entry.get("status") != "active":
                skipped_counts["inactive_status"] += 1
                continue
            record = builder(entry, source_namespace)
            if not record["embedding_text"].strip():
                skipped_counts["empty_embedding_text"] += 1
                if strict:
                    raise ValueError(f"empty embedding_text for {record['source_key']}")
                continue
            _validate_record(record)
            family_records.append(record)
        family_records.sort(key=lambda item: (item["asset_family"], item["country"], item["source_key"]))
        records.extend(family_records)
        family_counts[asset_family] = len(family_records)

    records.sort(key=lambda item: (item["asset_family"], item["country"], item["source_key"]))
    record_ids = [record["record_id"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("duplicate record_id detected")

    preview_markdown = _build_preview_markdown(records, source_namespace=source_namespace, generated_at=timestamp)
    manifest = {
        "schema_version": "m2b_embedding_manifest_v1",
        "source_namespace": source_namespace,
        "seed_patch": str(seed_patch_path),
        "builder_schema_version": "embedding_text_v1",
        "generated_at": timestamp,
        "record_count": len(records),
        "family_counts": family_counts,
        "skipped_counts": skipped_counts,
        "input_families": list(SUPPORTED_FAMILIES.keys()),
        "excluded_families": EXCLUDED_FAMILIES,
        "record_id_hash_algorithm": "sha256",
        "record_id_hash_input": "source_namespace + source_key + asset_family",
        "sanitization_checks_passed": True,
    }
    return EmbeddingArtifacts(records=records, manifest=manifest, preview_markdown=preview_markdown)


def write_embedding_outputs(
    *,
    artifacts: EmbeddingArtifacts,
    jsonl_path: Path,
    manifest_path: Path,
    preview_path: Path,
) -> None:
    _require_yaml()
    jsonl_lines = [_compact_json(record) for record in artifacts.records]
    jsonl_path.write_text("\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""), encoding="utf-8")
    manifest_path.write_text(
        yaml.safe_dump(artifacts.manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    preview_path.write_text(artifacts.preview_markdown, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build M2B embedding text records from a runtime seed patch.")
    parser.add_argument("--seed-patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--preview-output", type=Path, required=True)
    parser.add_argument("--generated-at", type=str, default=None)
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifacts = build_embedding_artifacts(
        seed_patch_path=args.seed_patch,
        generated_at=args.generated_at,
        strict=args.strict,
    )
    write_embedding_outputs(
        artifacts=artifacts,
        jsonl_path=args.output,
        manifest_path=args.manifest_output,
        preview_path=args.preview_output,
    )
    print(
        json.dumps(
            {
                "record_count": artifacts.manifest["record_count"],
                "source_namespace": artifacts.manifest["source_namespace"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
