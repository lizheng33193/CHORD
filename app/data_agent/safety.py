"""Safety gate wrapper for Data Agent SQL HITL."""

from __future__ import annotations

import hashlib

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


def resolve_country_names(target_country: str) -> tuple[str, str]:
    normalized = normalize_country_scope_value(target_country) or str(target_country or "").strip().lower()
    full = _COUNTRY_NAME_MAP.get(normalized, normalized)
    return normalized, full


def run_sql_safety_gate(sql_text: str, sql_kind: str, target_country: str) -> dict:
    normalized_country, full_country = resolve_country_names(target_country)
    sql_hash = hashlib.sha256((sql_text or "").encode("utf-8")).hexdigest()
    normalized_sql = (sql_text or "").strip()
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

