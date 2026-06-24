"""Deterministic review for SQL vs intent-plan consistency."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.data_knowledge.canonical_fields import normalize_field_name, normalize_table_name


_FIXED_DATE_RE = re.compile(r"'(\d{8}|\d{4}-\d{2}-\d{2})'")
_SOURCE_EQUALITY_RE = re.compile(
    r"\b(?:apply_source|source|channel)\b\s*=\s*'([^']+)'",
    re.IGNORECASE,
)
_SOURCE_IN_RE = re.compile(
    r"\b(?:apply_source|source|channel)\b\s+in\s*\(([^)]+)\)",
    re.IGNORECASE,
)
_BEHAVIOR_TABLE_RE = re.compile(r"\bdwb_b1_data_burying_point\b", re.IGNORECASE)
_JOIN_UID_RE = re.compile(r"\bjoin\b[\s\S]+?\bon\b[\s\S]*?\buid\b", re.IGNORECASE)
_WHERE_UID_RE = re.compile(r"\bwhere\b[\s\S]*?\buid\b", re.IGNORECASE)
_UID_PLACEHOLDER_RE = re.compile(r"<\s*([A-Za-z0-9_{}-]+)\s*>", re.IGNORECASE)


def review_sql_against_intent_plan(
    *,
    sql_text: str,
    retrieval_snapshot: dict,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
) -> list[dict]:
    sql = str(sql_text or "").strip()
    if not sql:
        return []

    request_text = str(natural_language_request or "")
    lowered_request = request_text.lower()
    snapshot = dict(retrieval_snapshot or {})
    intent_plan = dict(snapshot.get("sql_intent_plan_summary") or {})
    forbidden_patterns = {
        str(pattern or "").strip().lower()
        for pattern in (intent_plan.get("forbidden_patterns") or [])
        if str(pattern or "").strip()
    }
    canonical_map = {
        normalize_table_name(table_name): {
            normalize_field_name(field_name): normalize_field_name(preferred_field)
            for field_name, preferred_field in (field_map or {}).items()
            if normalize_field_name(field_name) and normalize_field_name(preferred_field)
        }
        for table_name, field_map in (snapshot.get("canonical_alternative_to_preferred_by_table") or {}).items()
        if normalize_table_name(table_name)
    }

    warnings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _append(category: str, risk_level: str, message: str, evidence: str) -> None:
        key = (category, evidence)
        if key in seen:
            return
        warnings.append(
            {
                "category": category,
                "risk_level": risk_level,
                "message": message,
                "evidence": evidence,
            }
        )
        seen.add(key)

    fixed_dates = [match.group(1) for match in _FIXED_DATE_RE.finditer(sql)]
    for date_literal in fixed_dates:
        if date_literal not in request_text:
            _append(
                "PLAN_DATE_DRIFT",
                "medium",
                "SQL contains fixed date partition not requested by the current request or sql_intent_plan.",
                date_literal,
            )

    for source_value in _extract_source_filter_values(sql):
        if source_value.lower() not in lowered_request:
            _append(
                "PLAN_SOURCE_FILTER_DRIFT",
                "medium",
                "SQL contains fixed source/channel filtering not requested by the current request or sql_intent_plan.",
                source_value,
            )

    for table_name, field_map in canonical_map.items():
        for alternative, preferred in field_map.items():
            if re.search(rf"\b{re.escape(alternative)}\b", sql, re.IGNORECASE):
                _append(
                    "PLAN_CANONICAL_FIELD_DRIFT",
                    "low",
                    f"SQL uses {alternative} for {table_name} even though current guidance prefers {preferred}.",
                    f"{table_name}.{alternative}->{preferred}",
                )

    if output_bucket == "behavior":
        required_fields = [
            normalize_field_name(field_name)
            for field_name in (intent_plan.get("required_fields") or [])
            if normalize_field_name(field_name)
        ]
        if required_fields:
            selected_fields = _extract_selected_output_fields(sql)
            missing_fields = [field_name for field_name in required_fields if field_name not in selected_fields]
            if missing_fields:
                _append(
                    "PLAN_REQUIRED_FIELD_MISSING",
                    "medium",
                    "SQL is missing required output fields from the current sql_intent_plan.",
                    ",".join(missing_fields),
                )

        if _BEHAVIOR_TABLE_RE.search(sql) and not _has_behavior_cohort_constraint(sql):
            _append(
                "PLAN_BROAD_SCAN_RISK",
                "medium",
                "Behavior writeback SQL scans the behavior table without a target cohort / uid join constraint.",
                "dwb_b1_data_burying_point",
            )

    placeholder_match = _UID_PLACEHOLDER_RE.search(sql)
    if (
        placeholder_match
        and any(token in placeholder_match.group(1).lower() for token in ("uid", "user", "target_users"))
        and "unresolved_uid_placeholder" in forbidden_patterns
    ):
        _append(
            "PLAN_FORBIDDEN_PATTERN",
            "medium",
            "SQL matches a forbidden pattern from the current sql_intent_plan.",
            "unresolved_uid_placeholder",
        )

    return warnings


def _extract_source_filter_values(sql: str) -> list[str]:
    values: list[str] = []
    for match in _SOURCE_EQUALITY_RE.finditer(sql):
        value = match.group(1).strip()
        if value:
            values.append(value)
    for match in _SOURCE_IN_RE.finditer(sql):
        values.extend(
            item.strip().strip("'").strip('"')
            for item in match.group(1).split(",")
            if item.strip().strip("'").strip('"')
        )
    return values


def _extract_selected_output_fields(sql: str) -> set[str]:
    select_clause = _extract_top_level_select_clause(sql)
    if not select_clause:
        return set()
    expressions = _split_top_level_csv(select_clause)
    fields: set[str] = set()
    for expression in expressions:
        normalized = expression.strip()
        if not normalized:
            continue
        alias_match = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\b", normalized, re.IGNORECASE)
        if alias_match:
            fields.add(normalize_field_name(alias_match.group(1)))
        tokens = [
            normalize_field_name(token)
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", normalized)
            if normalize_field_name(token)
        ]
        if tokens:
            fields.add(tokens[-1])
        dot_match = re.search(r"\.([A-Za-z_][A-Za-z0-9_]*)\b", normalized)
        if dot_match:
            fields.add(normalize_field_name(dot_match.group(1)))
    return {field_name for field_name in fields if field_name}


def _extract_top_level_select_clause(sql: str) -> str:
    lowered = sql.lower()
    depth = 0
    select_start = -1
    from_start = -1
    index = 0
    while index < len(lowered):
        char = lowered[index]
        if char == "'":
            index += 1
            while index < len(lowered):
                if lowered[index] == "'" and (index + 1 >= len(lowered) or lowered[index + 1] != "'"):
                    break
                if lowered[index] == "'" and lowered[index + 1:index + 2] == "'":
                    index += 2
                    continue
                index += 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and lowered.startswith("select", index) and _is_word_boundary(lowered, index, index + 6):
            select_start = index + 6
            from_start = -1
        elif depth == 0 and select_start >= 0 and lowered.startswith("from", index) and _is_word_boundary(lowered, index, index + 4):
            from_start = index
        index += 1
    if select_start >= 0 and from_start > select_start:
        return sql[select_start:from_start]
    return ""


def _split_top_level_csv(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            chunks.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def _has_behavior_cohort_constraint(sql: str) -> bool:
    lowered = sql.lower()
    if _JOIN_UID_RE.search(sql):
        return True
    if _WHERE_UID_RE.search(sql):
        return True
    if "with target_users as" in lowered and "join target_users" in lowered:
        return True
    return False


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    before = start == 0 or not text[start - 1].isalnum()
    after = end >= len(text) or not text[end:end + 1].isalnum()
    return before and after
