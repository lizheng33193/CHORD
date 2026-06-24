"""Code-level canonical field policy for runtime quality follow-ups."""

from __future__ import annotations


CANONICAL_FIELD_POLICY = {
    "dwd_w_apply": {
        "user_identifier": {
            "preferred": "uid",
            "alternatives": ["user_uuid"],
        },
        "apply_time": {
            "preferred": "apply_time",
            "alternatives": ["apply_create_at"],
        },
        "risk_level": {
            "preferred": "risk_level",
            "alternatives": ["risk_label"],
        },
    },
}


def normalize_table_name(table_name: str | None) -> str:
    text = str(table_name or "").strip().strip("`").strip('"').lower()
    if not text:
        return ""
    parts = [part.strip().strip("`").strip('"').lower() for part in text.split(".") if part.strip()]
    return parts[-1] if parts else ""


def normalize_field_name(field_name: str | None) -> str:
    return str(field_name or "").strip().strip("`").strip('"').lower()


def build_canonical_alternative_to_preferred_by_table(
    grounded_fields_by_table: dict[str, list[str]] | dict[str, set[str]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for table_name, semantics in CANONICAL_FIELD_POLICY.items():
        grounded_fields = {
            normalize_field_name(field_name)
            for field_name in (grounded_fields_by_table.get(table_name) or [])
            if normalize_field_name(field_name)
        }
        if not grounded_fields:
            continue
        table_mapping: dict[str, str] = {}
        for field_group in semantics.values():
            preferred = normalize_field_name(field_group.get("preferred"))
            if preferred not in grounded_fields:
                continue
            for alternative in field_group.get("alternatives") or []:
                normalized_alternative = normalize_field_name(alternative)
                if normalized_alternative in grounded_fields:
                    table_mapping[normalized_alternative] = preferred
        if table_mapping:
            result[table_name] = table_mapping
    return result


def build_canonical_guidance_rows(
    grounded_fields_by_table: dict[str, list[str]] | dict[str, set[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for table_name, semantics in CANONICAL_FIELD_POLICY.items():
        grounded_fields = {
            normalize_field_name(field_name)
            for field_name in (grounded_fields_by_table.get(table_name) or [])
            if normalize_field_name(field_name)
        }
        if not grounded_fields:
            continue
        for semantic, field_group in semantics.items():
            preferred = normalize_field_name(field_group.get("preferred"))
            if preferred not in grounded_fields:
                continue
            grounded_alternatives = [
                normalize_field_name(alternative)
                for alternative in (field_group.get("alternatives") or [])
                if normalize_field_name(alternative) in grounded_fields
            ]
            rows.append(
                {
                    "table": table_name,
                    "semantic": semantic,
                    "preferred": preferred,
                    "alternatives": ",".join(grounded_alternatives),
                }
            )
    return rows
