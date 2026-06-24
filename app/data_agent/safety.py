"""Safety gate wrapper for Data Agent SQL HITL."""

from __future__ import annotations

import hashlib
import re

from app.auth.permissions import normalize_country_scope_value
from data_acquisition_agent.executor import ExecutorError, enforce_pre_execution_gates
from data_acquisition_agent.manifest import load_manifest


_COUNTRY_NAME_MAP = {
    "mx": "mexico",
    "th": "thailand",
    "id": "indonesia",
    "pk": "pakistan",
    "ph": "philippines",
}

_ANGLE_PLACEHOLDER_RE = re.compile(r"<\s*[A-Za-z_][A-Za-z0-9_\- ]{0,63}\s*>")
_DOUBLE_BRACE_PLACEHOLDER_RE = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_.-]{0,63}\s*\}\}")
_BRACE_PLACEHOLDER_RE = re.compile(r"\{\s*[A-Za-z_][A-Za-z0-9_.-]{0,63}\s*\}")
_DOLLAR_PLACEHOLDER_RE = re.compile(r"\$\{\s*[A-Za-z_][A-Za-z0-9_.-]{0,63}\s*\}")
_KEYWORD_PLACEHOLDER_RE = re.compile(
    r"\b(TODO|TBD|PLACEHOLDER|replace_me|your_table|some_table|xxx_here)\b",
    re.IGNORECASE,
)


def resolve_country_names(target_country: str) -> tuple[str, str]:
    normalized = normalize_country_scope_value(target_country) or str(target_country or "").strip().lower()
    full = _COUNTRY_NAME_MAP.get(normalized, normalized)
    return normalized, full


def _find_unresolved_placeholders(sql_text: str) -> list[str]:
    normalized_sql = str(sql_text or "")
    matches: list[str] = []
    for pattern in (
        _ANGLE_PLACEHOLDER_RE,
        _DOUBLE_BRACE_PLACEHOLDER_RE,
        _DOLLAR_PLACEHOLDER_RE,
        _BRACE_PLACEHOLDER_RE,
        _KEYWORD_PLACEHOLDER_RE,
    ):
        for match in pattern.finditer(normalized_sql):
            token = match.group(0).strip()
            if token not in matches:
                matches.append(token)
    return matches


def run_sql_safety_gate(sql_text: str, sql_kind: str, target_country: str) -> dict:
    normalized_country, full_country = resolve_country_names(target_country)
    normalized_sql = (sql_text or "").strip()
    sql_hash = hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()
    if sql_kind == "build_table_script":
        return {
            "status": "review_only",
            "risk_level": "high",
            "blocked_reasons": ["build_table_script execution is not supported in M1"],
            "warnings": [],
            "normalized_sql": normalized_sql,
            "sql_hash": sql_hash,
            "target_country": normalized_country,
        }

    unresolved_placeholders = _find_unresolved_placeholders(normalized_sql)
    if unresolved_placeholders:
        return {
            "status": "blocked",
            "risk_level": "high",
            "blocked_reasons": [
                f"SQL contains unresolved placeholders: {', '.join(unresolved_placeholders)}"
            ],
            "warnings": [],
            "normalized_sql": normalized_sql,
            "sql_hash": sql_hash,
            "target_country": normalized_country,
            "rule_category": "UNRESOLVED_PLACEHOLDER",
        }

    manifest = load_manifest(full_country)
    try:
        enforce_pre_execution_gates(
            approved_sql=normalized_sql,
            sql_kind=sql_kind,
            analyst_private_prefix=manifest.analyst_private_prefix,
            request_id="data-agent-safety",
        )
    except ExecutorError as exc:
        return {
            "status": "blocked",
            "risk_level": "high",
            "blocked_reasons": [getattr(exc, "message", str(exc))],
            "warnings": [],
            "normalized_sql": normalized_sql,
            "sql_hash": sql_hash,
            "target_country": normalized_country,
        }

    return {
        "status": "passed",
        "risk_level": "low",
        "blocked_reasons": [],
        "warnings": [],
        "normalized_sql": normalized_sql,
        "sql_hash": sql_hash,
        "target_country": normalized_country,
    }
