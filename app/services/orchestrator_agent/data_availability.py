"""Deterministic local bucket availability checks for orchestrator fast paths."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.data_contracts import (
    BEHAVIOR_EVENT_FIELDS_NORMALIZED,
    BEHAVIOR_TIME_FIELDS_NORMALIZED,
    CREDIT_PROFILE_SIGNAL_FIELDS_NORMALIZED,
    CREDIT_STRONG_RAW_SIGNAL_FIELDS_NORMALIZED,
    CREDIT_SUMMARY_SIGNAL_FIELDS_NORMALIZED,
    UID_ALIASES_NORMALIZED,
    detect_credit_source_shape,
    get_uid_from_row,
    normalize_column_name,
    normalize_field_set,
    row_has_any,
)
from app.scripts.behavior_prepared_builder import BEHAVIOR_PREPARED_SCHEMA_VERSION
from app.scripts.credit_prepared_builder import CREDIT_PREPARED_SCHEMA_VERSION
from app.services.orchestrator_agent.schemas import (
    BucketAvailability,
    DataAvailability,
    UidAvailability,
)


_APP_REQUIRED_FIELDS = {
    "uid",
    "app_name",
    "app_package",
    "first_install_time",
    "last_update_time",
    "gp_category",
    "ai_category_level_2_CN",
}
_APP_REQUIRED_FIELDS_NORMALIZED = normalize_field_set(_APP_REQUIRED_FIELDS)


def check_data_availability(uids: list[str], country: str | None = None) -> DataAvailability:
    """Inspect real by_uid buckets only.

    This intentionally ignores repository sample fallbacks so the orchestrator can
    decide whether it has durable local data or must trigger a repair flow.
    """
    rows = [_check_uid(uid) for uid in uids]
    return DataAvailability(
        country=country,
        checked_uids=[str(uid).strip() for uid in uids if str(uid).strip()],
        per_uid=rows,
    )


def _check_uid(uid: str) -> UidAvailability:
    normalized_uid = str(uid or "").strip()
    app_status = _check_app_bucket(normalized_uid)
    behavior_status = _check_behavior_bucket(normalized_uid)
    credit_status = _check_credit_bucket(normalized_uid)

    available_buckets = [
        bucket_name
        for bucket_name, bucket_status in (
            ("app", app_status),
            ("behavior", behavior_status),
            ("credit", credit_status),
        )
        if bucket_status.usable_for_profile
    ]
    missing_buckets = [
        bucket_name
        for bucket_name, bucket_status in (
            ("app", app_status),
            ("behavior", behavior_status),
            ("credit", credit_status),
        )
        if not bucket_status.usable_for_profile
    ]
    return UidAvailability(
        uid=normalized_uid,
        app=app_status,
        behavior=behavior_status,
        credit=credit_status,
        available_buckets=available_buckets,
        missing_buckets=missing_buckets,
    )


def _check_app_bucket(uid: str) -> BucketAvailability:
    csv_path = settings.resolve_path(settings.app_by_uid_dir) / f"{uid}.csv"
    if not csv_path.exists():
        return _missing_bucket()
    return _check_csv_bucket(
        csv_path,
        uid=uid,
        required_fields=_APP_REQUIRED_FIELDS,
        source_type="csv",
        validator=_app_rows_usable,
    )


def _check_behavior_bucket(uid: str) -> BucketAvailability:
    checked_sources: list[str] = []
    last_invalid: BucketAvailability | None = None
    json_path = settings.resolve_path(settings.behavior_by_uid_dir) / f"{uid}.json"
    if json_path.exists():
        prepared = _check_prepared_json(
            json_path,
            expected_schema=BEHAVIOR_PREPARED_SCHEMA_VERSION,
            bucket="behavior",
        )
        checked_sources.extend(prepared.checked_sources)
        if prepared.available:
            return prepared
        last_invalid = prepared

    csv_path = settings.resolve_path(settings.behavior_by_uid_dir) / f"{uid}.csv"
    if csv_path.exists():
        csv_result = _check_csv_bucket(
            csv_path,
            uid=uid,
            required_fields=set(),
            uid_aliases={"uid"},
            source_type="csv",
            validator=_behavior_rows_usable,
        )
        csv_result.checked_sources = checked_sources + csv_result.checked_sources
        if csv_result.available:
            return csv_result
        last_invalid = csv_result
        return csv_result

    if last_invalid is not None:
        last_invalid.checked_sources = checked_sources or last_invalid.checked_sources
        return last_invalid
    return _missing_bucket()


def _check_credit_bucket(uid: str) -> BucketAvailability:
    checked_sources: list[str] = []
    last_invalid: BucketAvailability | None = None
    json_path = settings.resolve_path(settings.credit_by_uid_dir) / f"{uid}.json"
    if json_path.exists():
        prepared = _check_prepared_json(
            json_path,
            expected_schema=CREDIT_PREPARED_SCHEMA_VERSION,
            bucket="credit",
        )
        checked_sources.extend(prepared.checked_sources)
        if prepared.available:
            return prepared
        last_invalid = prepared

        legacy = _check_legacy_credit_json(json_path)
        checked_sources.extend(legacy.checked_sources)
        if legacy.available:
            legacy.checked_sources = checked_sources
            return legacy
        last_invalid = legacy

    csv_path = settings.resolve_path(settings.credit_by_uid_dir) / f"{uid}.csv"
    if csv_path.exists():
        csv_result = _check_csv_bucket(
            csv_path,
            uid=uid,
            required_fields=set(),
            uid_aliases=UID_ALIASES_NORMALIZED,
            source_type="csv",
            validator=_credit_rows_usable,
        )
        csv_result.checked_sources = checked_sources + csv_result.checked_sources
        if csv_result.available:
            return csv_result
        last_invalid = csv_result
        return csv_result

    if last_invalid is not None:
        last_invalid.checked_sources = checked_sources or last_invalid.checked_sources
        return last_invalid
    return _missing_bucket()


def _check_csv_bucket(
    path: Path,
    *,
    uid: str,
    required_fields: set[str],
    uid_aliases: set[str] | None = None,
    source_type: str,
    validator,
) -> BucketAvailability:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            normalized_fieldnames = {
                normalize_column_name(name)
                for name in (reader.fieldnames or [])
                if name
            }
            required_fields_normalized = normalize_field_set(required_fields)
            uid_aliases_normalized = normalize_field_set(uid_aliases or {"uid"})
            if not (uid_aliases_normalized & normalized_fieldnames):
                return BucketAvailability(
                    status="invalid",
                    available=False,
                    usable_for_profile=False,
                    checked_sources=[f"{source_type}:invalid"],
                    source_type=source_type,
                    path=str(path),
                    detail="missing_uid_alias",
                    quality_score=0.0,
                    weak_reasons=["missing_uid_alias"],
                )
            if not required_fields_normalized.issubset(normalized_fieldnames):
                missing = sorted(required_fields_normalized.difference(normalized_fieldnames))
                return BucketAvailability(
                    status="invalid",
                    available=False,
                    usable_for_profile=False,
                    checked_sources=[f"{source_type}:invalid"],
                    source_type=source_type,
                    path=str(path),
                    detail=f"missing_fields:{','.join(missing)}",
                    quality_score=0.0,
                    weak_reasons=["missing_required_fields"],
                )
            rows = []
            for row in reader:
                normalized = {
                    normalize_column_name(key): value
                    for key, value in row.items()
                    if key
                }
                if get_uid_from_row(normalized, uid_aliases_normalized) == uid:
                    rows.append(normalized)
            if not rows:
                return BucketAvailability(
                    status="invalid",
                    available=False,
                    usable_for_profile=False,
                    checked_sources=[f"{source_type}:invalid"],
                    source_type=source_type,
                    path=str(path),
                    detail="uid_rows_missing",
                    row_count=0,
                    quality_score=0.0,
                    weak_reasons=["uid_rows_missing"],
                )
            usable, detail, metadata = validator(normalized_fieldnames, rows)
            if not usable:
                return BucketAvailability(
                    status="invalid",
                    available=False,
                    usable_for_profile=False,
                    checked_sources=[f"{source_type}:invalid"],
                    source_type=source_type,
                    path=str(path),
                    detail=detail,
                    row_count=len(rows),
                    source_shape=metadata.get("source_shape"),
                    quality_score=float(metadata.get("quality_score", 0.0) or 0.0),
                    weak_reasons=list(metadata.get("weak_reasons") or ([detail] if detail else [])),
                )
    except Exception as exc:  # noqa: BLE001
        return BucketAvailability(
            status="invalid",
            available=False,
            usable_for_profile=False,
            checked_sources=[f"{source_type}:invalid"],
            source_type=source_type,
            path=str(path),
            detail=str(exc),
            quality_score=0.0,
            weak_reasons=[str(exc)],
        )
    return BucketAvailability(
        status="available",
        available=True,
        usable_for_profile=True,
        checked_sources=[f"{source_type}:available"],
        source_type=source_type,
        path=str(path),
        row_count=len(rows),
        source_shape=metadata.get("source_shape"),
        quality_score=float(metadata.get("quality_score", 1.0) or 1.0),
        weak_reasons=list(metadata.get("weak_reasons") or []),
    )


def _app_rows_usable(fieldnames: set[str], rows: list[dict[str, Any]]) -> tuple[bool, str | None, dict[str, Any]]:
    del fieldnames
    return (bool(rows), None if rows else "empty_csv", {"quality_score": 1.0 if rows else 0.0})


def _behavior_rows_usable(fieldnames: set[str], rows: list[dict[str, Any]]) -> tuple[bool, str | None, dict[str, Any]]:
    if not (BEHAVIOR_TIME_FIELDS_NORMALIZED & fieldnames):
        return False, "missing_behavior_time_field", {"quality_score": 0.0}
    if not (BEHAVIOR_EVENT_FIELDS_NORMALIZED & fieldnames):
        return False, "missing_behavior_event_field", {"quality_score": 0.0}
    for row in rows:
        if row_has_any(row, BEHAVIOR_TIME_FIELDS_NORMALIZED) and row_has_any(row, BEHAVIOR_EVENT_FIELDS_NORMALIZED):
            return True, None, {"quality_score": 1.0, "source_shape": "raw_events"}
    return False, "weak_behavior_rows", {"quality_score": 0.0}


def _credit_rows_usable(fieldnames: set[str], rows: list[dict[str, Any]]) -> tuple[bool, str | None, dict[str, Any]]:
    if not (
        (CREDIT_STRONG_RAW_SIGNAL_FIELDS_NORMALIZED & fieldnames)
        or (CREDIT_SUMMARY_SIGNAL_FIELDS_NORMALIZED & fieldnames)
    ):
        return False, "missing_credit_signal_field", {"quality_score": 0.0}
    source_shape = detect_credit_source_shape(fieldnames)
    weak_reasons = ["legacy_credit_summary_fallback"] if source_shape == "summary" else []
    quality_score = 0.8 if source_shape == "summary" else 1.0
    for row in rows:
        if row_has_any(row, CREDIT_PROFILE_SIGNAL_FIELDS_NORMALIZED):
            return True, None, {
                "source_shape": source_shape,
                "quality_score": quality_score,
                "weak_reasons": weak_reasons,
            }
    return False, "weak_credit_rows", {"quality_score": 0.0, "source_shape": source_shape}


def _check_prepared_json(path: Path, *, expected_schema: str, bucket: str) -> BucketAvailability:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return BucketAvailability(
            status="invalid",
            available=False,
            usable_for_profile=False,
            checked_sources=["prepared_json:invalid"],
            source_type="prepared_json",
            path=str(path),
            detail=str(exc),
            quality_score=0.0,
            weak_reasons=[str(exc)],
        )
    if isinstance(payload, dict) and payload.get("schema_version") == expected_schema and isinstance(payload.get("source_meta"), dict):
        quality = _prepared_payload_quality(bucket, payload)
        if quality["usable"]:
            return BucketAvailability(
                status="available",
                available=True,
                usable_for_profile=True,
                checked_sources=["prepared_json:available"],
                source_type="prepared_json",
                source_shape="prepared",
                path=str(path),
                quality_score=quality["quality_score"],
                weak_reasons=[],
                row_count=quality["row_count"],
            )
        return BucketAvailability(
            status="invalid",
            available=False,
            usable_for_profile=False,
            checked_sources=["prepared_json:invalid"],
            source_type="prepared_json",
            path=str(path),
            detail="prepared_payload_empty",
            quality_score=quality["quality_score"],
            weak_reasons=list(quality["weak_reasons"]),
            row_count=quality["row_count"],
        )
    return BucketAvailability(
        status="invalid",
        available=False,
        usable_for_profile=False,
        checked_sources=["prepared_json:invalid"],
        source_type="prepared_json",
        path=str(path),
        detail="schema_mismatch",
        quality_score=0.0,
        weak_reasons=["schema_mismatch"],
    )


def _check_legacy_credit_json(path: Path) -> BucketAvailability:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return BucketAvailability(
            status="invalid",
            available=False,
            usable_for_profile=False,
            checked_sources=["legacy_json:invalid"],
            source_type="legacy_json",
            path=str(path),
            detail=str(exc),
        )
    if isinstance(payload, dict) and (
        CREDIT_SUMMARY_SIGNAL_FIELDS_NORMALIZED & {
        normalize_column_name(key)
        for key in payload.keys()
    }):
        return BucketAvailability(
            status="available",
            available=True,
            usable_for_profile=True,
            checked_sources=["legacy_json:available"],
            source_type="legacy_json",
            source_shape="summary",
            path=str(path),
            row_count=1,
            quality_score=0.8,
            weak_reasons=["legacy_credit_summary_fallback"],
        )
    return BucketAvailability(
        status="invalid",
        available=False,
        usable_for_profile=False,
        checked_sources=["legacy_json:invalid"],
        source_type="legacy_json",
        path=str(path),
        detail="schema_mismatch",
        quality_score=0.0,
        weak_reasons=["schema_mismatch"],
    )


def _missing_bucket() -> BucketAvailability:
    return BucketAvailability(
        status="missing",
        available=False,
        usable_for_profile=False,
        checked_sources=["missing"],
        source_type="missing",
        weak_reasons=[],
    )


def _prepared_payload_quality(bucket: str, payload: dict[str, Any]) -> dict[str, Any]:
    if bucket == "behavior":
        source_meta = payload.get("source_meta") or {}
        session_summary = payload.get("session_summary") or {}
        timeline_sections = payload.get("timeline_sections") or []
        event_count = _positive_int(source_meta.get("event_count"))
        total_events = _positive_int(session_summary.get("total_events"))
        has_timeline = bool(timeline_sections)
        row_count = event_count or total_events or (len(timeline_sections) if has_timeline else 0)
        if event_count or total_events or has_timeline:
            return {"usable": True, "quality_score": 1.0, "weak_reasons": [], "row_count": row_count}
        return {
            "usable": False,
            "quality_score": 0.0,
            "weak_reasons": ["empty_behavior_prepared_payload"],
            "row_count": row_count,
        }

    source_meta = payload.get("source_meta") or {}
    credit_summary = payload.get("credit_summary") or {}
    delinquency_summary = payload.get("delinquency_summary") or {}
    repayment_timeline = payload.get("repayment_timeline") or []
    repayment_amount_timeline = payload.get("repayment_amount_timeline") or []
    total_accounts = _positive_int(credit_summary.get("total_accounts"))
    total_delinquent = _positive_int(delinquency_summary.get("total_delinquent_accounts"))
    source_rows = _positive_int(source_meta.get("row_count"))
    has_repayment_signal = _sequence_has_nonzero(repayment_timeline) or _sequence_has_nonzero(repayment_amount_timeline)
    row_count = source_rows or total_accounts or total_delinquent or 0
    if total_accounts or total_delinquent or has_repayment_signal or source_rows:
        return {"usable": True, "quality_score": 1.0, "weak_reasons": [], "row_count": row_count}
    return {
        "usable": False,
        "quality_score": 0.0,
        "weak_reasons": ["empty_credit_prepared_payload"],
        "row_count": row_count,
    }


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _sequence_has_nonzero(values: Any) -> bool:
    if not isinstance(values, list):
        return False
    for value in values:
        try:
            if float(value) != 0.0:
                return True
        except (TypeError, ValueError):
            if str(value).strip():
                return True
    return False
