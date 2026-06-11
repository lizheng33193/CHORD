"""Shared data contract helpers for availability and output validation."""

from __future__ import annotations

import re
from typing import Any, Iterable


UID_ALIASES = {
    "uid",
    "user_id",
    "userid",
    "user_uuid",
    "useruuid",
    "customer_id",
    "customerid",
}

BEHAVIOR_TIME_FIELDS = {
    "event_time",
    "event_timestamp",
    "timestamp_",
    "servertimestamp",
    "timestamp",
    "ts",
    "time",
    "occurred_at",
    "created_at",
}

BEHAVIOR_EVENT_FIELDS = {
    "event_name",
    "eventname",
    "page_name",
    "page",
    "event",
    "action",
    "event_type",
    "name",
    "scenetype",
    "processtype",
    "url",
}

CREDIT_STRONG_RAW_SIGNAL_FIELDS = {
    "valor",
    "nombrescore",
    "razones",
    "consultas_detail_json",
    "creditos_detail_json",
}

CREDIT_WEAK_META_FIELDS = {
    "timestamp_",
    "code",
    "apply_risk_id",
    "folioconsulta",
}

CREDIT_SUMMARY_SIGNAL_FIELDS = {
    "credit_score",
    "credit_score_band",
    "risk_level",
    "repayment_status",
    "loan_amount",
    "payment_amount",
    "overdue_days",
    "debt_amount",
    "balance",
}

CREDIT_PROFILE_SIGNAL_FIELDS = CREDIT_STRONG_RAW_SIGNAL_FIELDS | CREDIT_SUMMARY_SIGNAL_FIELDS


def normalize_column_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def normalize_field_set(fields: Iterable[str]) -> set[str]:
    return {normalize_column_name(field) for field in fields if field}


UID_ALIASES_NORMALIZED = normalize_field_set(UID_ALIASES)
BEHAVIOR_TIME_FIELDS_NORMALIZED = normalize_field_set(BEHAVIOR_TIME_FIELDS)
BEHAVIOR_EVENT_FIELDS_NORMALIZED = normalize_field_set(BEHAVIOR_EVENT_FIELDS)
CREDIT_STRONG_RAW_SIGNAL_FIELDS_NORMALIZED = normalize_field_set(CREDIT_STRONG_RAW_SIGNAL_FIELDS)
CREDIT_WEAK_META_FIELDS_NORMALIZED = normalize_field_set(CREDIT_WEAK_META_FIELDS)
CREDIT_SUMMARY_SIGNAL_FIELDS_NORMALIZED = normalize_field_set(CREDIT_SUMMARY_SIGNAL_FIELDS)
CREDIT_PROFILE_SIGNAL_FIELDS_NORMALIZED = normalize_field_set(CREDIT_PROFILE_SIGNAL_FIELDS)


def normalized_column_map(columns: Iterable[Any]) -> dict[str, Any]:
    return {
        normalize_column_name(column): column
        for column in columns
        if normalize_column_name(column)
    }


def row_has_any(row: dict[str, Any], candidate_fields: set[str]) -> bool:
    for field in candidate_fields:
        value = row.get(field)
        if value is None:
            continue
        if str(value).strip():
            return True
    return False


def get_uid_from_row(row: dict[str, Any], candidate_fields: set[str]) -> str:
    for field in candidate_fields:
        value = row.get(field)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def detect_credit_source_shape(fieldnames: set[str]) -> str | None:
    has_raw_shape = bool(CREDIT_STRONG_RAW_SIGNAL_FIELDS_NORMALIZED & fieldnames)
    has_summary_shape = bool(CREDIT_SUMMARY_SIGNAL_FIELDS_NORMALIZED & fieldnames)
    if has_raw_shape and has_summary_shape:
        return "mixed"
    if has_raw_shape:
        return "raw_buro"
    if has_summary_shape:
        return "summary"
    return None
