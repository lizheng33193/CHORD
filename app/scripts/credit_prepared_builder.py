"""Build standardized Credit prepared records from local or upstream payloads."""

from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.country_packs.credit_profile import load_credit_country_pack


CREDIT_PREPARED_SCHEMA_VERSION = "credit-prepared-v1"
MEXICO_OFFSET = timezone(timedelta(hours=-6))
_PREPARED_REQUIRED_KEYS = {
    "uid",
    "country_code",
    "schema_version",
    "profile_header",
    "summary",
    "delinquency",
    "inquiries",
    "account_details",
    "score",
    "repayment_timeline",
    "repayment_amount_timeline",
    "repayment_amount_notes",
    "source_meta",
}


def is_credit_prepared_record(payload: Any) -> bool:
    """Return whether the payload already matches the prepared-record contract."""
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != CREDIT_PREPARED_SCHEMA_VERSION:
        return False
    return _PREPARED_REQUIRED_KEYS.issubset(set(payload.keys()))


def prepare_credit_record_from_csv_file(
    file_path: Path,
    uid: str,
    *,
    country_code: str = "mx",
) -> tuple[dict[str, Any], list[str]]:
    """Parse a uid-scoped raw credit CSV file into a prepared record."""
    rows: list[dict[str, Any]] = []
    try:
        with Path(file_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
    except Exception as exc:  # pylint: disable=broad-except
        return {}, [f"csv_read_failed:{exc}"]

    if not rows:
        return {}, ["credit_csv_empty"]

    return prepare_credit_record_from_payload(
        uid,
        {
            "uid": uid,
            "source_kind": "raw_credit_csv",
            "source_type": "local_file",
            "source_file": str(file_path),
            "rows": rows,
        },
        country_code=country_code,
    )


def prepare_credit_record_from_payload(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str = "mx",
) -> tuple[dict[str, Any], list[str]]:
    """Convert repository payload variants into a standardized prepared record."""
    normalized_uid = str(uid or "").strip()
    if not isinstance(payload, dict):
        return {}, ["credit_payload_not_object"]

    if is_credit_prepared_record(payload):
        prepared = deepcopy(payload)
        prepared["uid"] = normalized_uid or str(prepared.get("uid", "") or "")
        prepared["country_code"] = str(prepared.get("country_code", country_code) or country_code).lower()
        return prepared, []

    if payload.get("schema_version"):
        return {}, ["prepared_schema_mismatch"]

    source_kind = str(payload.get("source_kind", "") or "").strip().lower()
    if source_kind == "raw_credit_csv" or isinstance(payload.get("rows"), list):
        return _prepare_from_raw_credit_payload(normalized_uid, payload, country_code=country_code)

    return _prepare_from_legacy_summary(normalized_uid, payload, country_code=country_code)


def _prepare_from_raw_credit_payload(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str,
) -> tuple[dict[str, Any], list[str]]:
    pack = load_credit_country_pack(country_code)
    warnings: list[str] = []
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    if not rows and isinstance(payload.get("row"), dict):
        rows = [payload["row"]]
    scoped_rows = _filter_credit_rows_by_uid(rows, uid)
    if not scoped_rows:
        return {}, ["credit_csv_rows_missing"]

    latest_row = max(scoped_rows, key=lambda row: _to_float(row.get("timestamp_", 0)))
    if str(latest_row.get("credit_score_band", "") or "").strip() and not str(
        latest_row.get("creditos_detail_json", "") or ""
    ).strip():
        return _prepare_from_legacy_summary(
            uid,
            {
                **latest_row,
                "uid": uid,
                "source_type": payload.get("source_type", "local_file"),
                "source_kind": "legacy_summary_csv",
                "source_file": payload.get("source_file", ""),
            },
            country_code=country_code,
        )

    consultas_records = _parse_credit_json_list(latest_row.get("consultas_detail_json", ""))
    credit_records = _parse_credit_json_list(latest_row.get("creditos_detail_json", ""))

    account_details = [_normalize_credit_account(record, pack=pack) for record in credit_records]
    account_details = [item for item in account_details if item]
    inquiries = [_normalize_credit_inquiry(record) for record in consultas_records]
    inquiries = [item for item in inquiries if item]

    summary = _build_credit_summary(account_details)
    delinquency = _build_credit_delinquency(account_details)
    inquiry_summary = _build_credit_inquiry_summary(inquiries)
    score_value = _to_int(latest_row.get("valor"))
    credit_score_band = _score_to_band(score_value, pack=pack)
    repayment_status = _derive_repayment_status(
        delinquency.get("max_delinquency_days", 0),
        delinquency.get("total_delinquent_accounts", 0),
    )

    if not account_details:
        warnings.append("credit_accounts_empty_after_normalization")
    if not consultas_records:
        warnings.append("credit_inquiries_empty_after_normalization")

    repayment_amount = _build_repayment_amount_timeline(credit_records, account_details)
    prepared = {
        "uid": uid,
        "country_code": pack.country_code,
        "schema_version": CREDIT_PREPARED_SCHEMA_VERSION,
        "profile_header": {
            "uid": uid,
            "name": _build_credit_name(latest_row),
            "age": _estimate_age(latest_row.get("fechanacimiento", "")),
            "city": str(
                latest_row.get("ciudad", "")
                or latest_row.get("residencia", "")
                or "Unknown"
            ).strip(),
            "occupation": str(latest_row.get("ocupacion", "") or "Unknown").strip(),
        },
        "summary": summary,
        "delinquency": delinquency,
        "inquiries": inquiry_summary,
        "account_details": account_details[:12],
        "score": {
            "score_model": str(latest_row.get("nombrescore", "") or "FICO").strip(),
            "score_value": score_value,
            "score_reasons": _split_score_reasons(latest_row.get("razones", "")),
            "credit_score_band": credit_score_band,
            "repayment_status": repayment_status,
        },
        "repayment_timeline": _build_repayment_timeline(account_details, delinquency),
        "repayment_amount_timeline": repayment_amount["amounts"],
        "repayment_amount_notes": repayment_amount["notes"],
        "source_meta": {
            "source_type": str(payload.get("source_type", "local_file") or "local_file"),
            "origin_ref": str(
                payload.get("source_file", "")
                or payload.get("source_ref", "")
                or ""
            ),
            "source_variant": "raw_credit_csv",
            "credit_report_date": _normalize_credit_date(latest_row.get("dt", "")),
            "currency_code": pack.currency_code,
            "source_display_name": pack.source_display_name,
        },
    }
    return prepared, warnings


def _prepare_from_legacy_summary(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str,
) -> tuple[dict[str, Any], list[str]]:
    pack = load_credit_country_pack(country_code)
    credit_score_band = str(payload.get("credit_score_band", "unknown") or "unknown").strip().upper()
    repayment_status = str(payload.get("repayment_status", "unknown") or "unknown").strip().lower()
    risk_level = str(payload.get("risk_level", "unknown") or "unknown").strip().lower()
    warnings = [
        "legacy_credit_summary_only",
        "buro_detail_missing",
    ]
    default_radar = _build_credit_radar_scores(
        summary={
            "total_accounts": 0,
            "active_accounts": 0,
            "closed_accounts": 0,
            "oldest_account_age_months": 0,
            "total_outstanding_debt_mxn": 0,
            "monthly_payment_estimate_mxn": 0,
            "avg_credit_utilization_pct": 0,
            "max_credit_utilization_pct": 0,
        },
        debt_pressure_level={"high": "high", "medium": "medium", "low": "low"}.get(risk_level, "medium"),
        credit_stability_level={"stable": "high", "normal": "medium", "watchlist": "low"}.get(repayment_status, "medium"),
        borrowing_urgency_level="medium",
    )
    prepared = {
        "uid": uid,
        "country_code": pack.country_code,
        "schema_version": CREDIT_PREPARED_SCHEMA_VERSION,
        "profile_header": {
            "uid": uid,
            "name": "Unknown User",
            "age": 0,
            "city": "Unknown",
            "occupation": "Unknown",
        },
        "summary": {
            "total_accounts": 0,
            "active_accounts": 0,
            "closed_accounts": 0,
            "oldest_account_age_months": 0,
            "total_outstanding_debt_mxn": 0,
            "monthly_payment_estimate_mxn": 0,
            "avg_credit_utilization_pct": 0,
            "max_credit_utilization_pct": 0,
        },
        "delinquency": {
            "total_delinquent_accounts": 0,
            "max_delinquency_days": 0,
            "most_recent_delinquency": "",
            "delinquency_history": [],
        },
        "inquiries": {
            "last_3_months": 0,
            "last_6_months": 0,
            "last_12_months": 0,
            "inquiry_sources": [],
        },
        "account_details": [],
        "score": {
            "score_model": "legacy_summary",
            "score_value": 0,
            "score_reasons": [],
            "credit_score_band": credit_score_band,
            "repayment_status": repayment_status,
            "legacy_risk_level": risk_level,
        },
        "repayment_timeline": [0] * 12,
        "repayment_amount_timeline": [0] * 12,
        "repayment_amount_notes": [
            "No repayment amount detail was available in the legacy summary payload."
        ]
        * 12,
        "source_meta": {
            "source_type": str(payload.get("source_type", "") or "legacy_summary"),
            "origin_ref": str(payload.get("source_file", "") or payload.get("source_ref", "") or ""),
            "source_variant": str(payload.get("source_kind", "") or "legacy_summary"),
            "credit_report_date": "",
            "currency_code": pack.currency_code,
            "source_display_name": pack.source_display_name,
        },
    }
    prepared["summary"]["radar_seed"] = default_radar
    return prepared, warnings


def _filter_credit_rows_by_uid(rows: list[dict[str, Any]], uid: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        row_uid = str(row.get("uid", "") or row.get("user_uuid", "") or row.get("user_id", "")).strip()
        if not row_uid or row_uid == uid:
            matched.append(row)
    return matched or rows


def _parse_credit_json_list(raw: Any) -> list[dict[str, Any]]:
    text = str(raw or "").strip()
    if not text:
        return []
    parsed = _safe_parse_json(text)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("data", "records", "items", "list", "result"):
            nested = parsed.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [parsed]
    recovered_list = _recover_json_object_list(text)
    if recovered_list:
        return recovered_list
    repaired_list = _repair_truncated_json_list(text)
    if repaired_list:
        return repaired_list
    return []


def _recover_json_object_list(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    in_str = False
    escaped = False
    depth = 0
    start: int | None = None
    for idx, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue
        if ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    snippet = text[start : idx + 1]
                    try:
                        parsed = json.loads(snippet)
                    except Exception:  # pylint: disable=broad-except
                        parsed = None
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                    start = None
    return objects


def _repair_truncated_json_list(text: str) -> list[dict[str, Any]]:
    candidate = text.strip()
    if not candidate:
        return []
    if not candidate.startswith("["):
        candidate = f"[{candidate}"
    if not candidate.endswith("]"):
        candidate = f"{candidate}]"
    candidate = re.sub(r'"([^"]+)"\s*\]$', r'"\1":"" ]', candidate)
    candidate = re.sub(r'"([^"]+)"\s*\}$', r'"\1":""}', candidate)
    open_count = candidate.count("{")
    close_count = candidate.count("}")
    if close_count < open_count and candidate.endswith("]"):
        candidate = candidate[:-1] + ("}" * (open_count - close_count)) + "]"
    parsed = _safe_parse_json(candidate)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _safe_parse_json(text: str) -> Any:
    candidate = text.strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # pylint: disable=broad-except
        pass
    normalized = candidate.replace("None", "null").replace("True", "true").replace("False", "false")
    normalized = normalized.replace("'", '"')
    normalized = re.sub(r"\},\s*,\s*\{", "},{", normalized)
    normalized = re.sub(r"\[\s*,\s*\{", "[{", normalized)
    normalized = re.sub(r"\}\s*,\s*\]", "}]", normalized)
    normalized = re.sub(r",\s*,+", ",", normalized)
    try:
        return json.loads(normalized)
    except Exception:  # pylint: disable=broad-except
        return None


def _normalize_credit_account(raw: dict[str, Any], *, pack: Any) -> dict[str, Any]:
    institution = _pick_first(
        raw,
        "institution",
        "institucion",
        "grantor",
        "otorgante",
        "nombreotorgante",
        "credito_nombreotorgante",
    )
    account_type = _pick_first(
        raw,
        "type",
        "tipo",
        "product_type",
        "tipocredito",
        "credito_tipocredito",
        "tipocuenta",
    )
    if not institution and not account_type:
        return {}

    limit_primary = _to_float(
        _pick_first(
            raw,
            "credit_limit_mxn",
            "credit_limit",
            "linea_credito",
            "limite",
            "limitecredito",
        )
    )
    original_amount = _to_float(_pick_first(raw, "original_amount_mxn", "creditomaximo", "max_credit", "maximo"))
    credit_limit = limit_primary if limit_primary > 0 else original_amount
    current_balance = _to_float(
        _pick_first(
            raw,
            "current_balance_mxn",
            "saldo_actual",
            "balance",
            "saldo",
            "saldoactual",
        )
    )
    monthly_payment = _to_float(
        _pick_first(
            raw,
            "monthly_payment_mxn",
            "pago_mensual",
            "payment",
            "pago",
            "montopagar",
        )
    )
    dpd = _to_int(
        _pick_first(
            raw,
            "days_past_due",
            "dpd",
            "atraso_dias",
            "dias_atraso",
            "peoratraso",
            "numeropagosvencidos",
        )
    )
    payment_status = _pick_first(raw, "payment_status", "estatus_pago", "status", "estado")
    open_date = _normalize_credit_date(
        _pick_first(
            raw,
            "open_date",
            "fecha_apertura",
            "apertura",
            "fechaaperturacuenta",
        )
    )
    report_date = _normalize_credit_date(
        _pick_first(raw, "fechaactualizacion", "fechareporte", "report_date")
    )

    if not payment_status:
        current_payment = _pick_first(raw, "pagoactual", "historicopagos")
        cleaned_current = str(current_payment or "").strip().upper()
        if cleaned_current.startswith("V"):
            payment_status = "current"
        elif cleaned_current:
            payment_status = cleaned_current
        elif dpd > 0:
            payment_status = "past_due"
        else:
            payment_status = "current"

    account_age_months = _months_since(open_date)
    utilization = 0.0
    if credit_limit > 0:
        utilization = max(0.0, min(100.0, (current_balance / credit_limit) * 100))
    elif current_balance > 0 and account_type.upper() in {"CC", "TC", "TDC", "CREDIT_CARD"}:
        utilization = 100.0

    return {
        "institution": institution or "未知机构",
        "type": account_type or "UNKNOWN",
        "account_type_label": pack.account_type_labels.get(str(account_type or "").upper(), account_type or "未知类型"),
        "credit_limit_mxn": int(round(credit_limit)),
        "original_amount_mxn": int(round(original_amount)),
        "current_balance_mxn": int(round(current_balance)),
        "monthly_payment_mxn": int(round(monthly_payment)),
        "utilization_rate": f"{int(round(utilization))}%" if credit_limit > 0 else "N/A",
        "payment_status": payment_status or "current",
        "account_age_months": account_age_months,
        "days_past_due": max(0, dpd),
        "open_date": open_date,
        "report_date": report_date,
    }


def _normalize_credit_inquiry(raw: dict[str, Any]) -> dict[str, Any]:
    source = _pick_first(
        raw,
        "institution",
        "institucion",
        "grantor",
        "otorgante",
        "nombreotorgante",
        "consultas_nombreotorgante",
    )
    date_value = _normalize_credit_date(
        _pick_first(
            raw,
            "query_date",
            "fecha_consulta",
            "date",
            "fecha",
            "fechaconsulta",
        )
    )
    if not source and not date_value:
        return {}
    return {
        "source": source or "未知机构",
        "date": date_value,
    }


def _build_credit_summary(account_details: list[dict[str, Any]]) -> dict[str, Any]:
    if not account_details:
        return {
            "total_accounts": 0,
            "active_accounts": 0,
            "closed_accounts": 0,
            "oldest_account_age_months": 0,
            "total_outstanding_debt_mxn": 0,
            "monthly_payment_estimate_mxn": 0,
            "avg_credit_utilization_pct": 0,
            "max_credit_utilization_pct": 0,
        }

    total_accounts = len(account_details)
    active_accounts = sum(1 for item in account_details if item.get("current_balance_mxn", 0) > 0)
    oldest_age = max(int(item.get("account_age_months", 0) or 0) for item in account_details)
    total_debt = sum(int(item.get("current_balance_mxn", 0) or 0) for item in account_details)
    monthly_payment = sum(int(item.get("monthly_payment_mxn", 0) or 0) for item in account_details)
    utilization_values = [
        _to_float(str(item.get("utilization_rate", "0")).replace("%", ""))
        for item in account_details
        if str(item.get("utilization_rate", "")).endswith("%")
    ]
    avg_util = int(round(sum(utilization_values) / len(utilization_values))) if utilization_values else 0
    max_util = int(round(max(utilization_values))) if utilization_values else 0
    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "closed_accounts": max(0, total_accounts - active_accounts),
        "oldest_account_age_months": oldest_age,
        "total_outstanding_debt_mxn": total_debt,
        "monthly_payment_estimate_mxn": monthly_payment,
        "avg_credit_utilization_pct": avg_util,
        "max_credit_utilization_pct": max_util,
    }


def _build_credit_delinquency(account_details: list[dict[str, Any]]) -> dict[str, Any]:
    delinquent = [item for item in account_details if int(item.get("days_past_due", 0) or 0) > 0]
    max_dpd = max((int(item.get("days_past_due", 0) or 0) for item in delinquent), default=0)
    return {
        "total_delinquent_accounts": len(delinquent),
        "max_delinquency_days": max_dpd,
        "most_recent_delinquency": "",
        "delinquency_history": [
            {
                "account": item.get("institution", "Unknown"),
                "days_past_due": int(item.get("days_past_due", 0) or 0),
                "date": item.get("open_date", ""),
                "status": item.get("payment_status", "unknown"),
            }
            for item in delinquent[:8]
        ],
    }


def _build_credit_inquiry_summary(inquiries: list[dict[str, Any]]) -> dict[str, Any]:
    if not inquiries:
        return {
            "last_3_months": 0,
            "last_6_months": 0,
            "last_12_months": 0,
            "inquiry_sources": [],
        }

    today = datetime.now(tz=MEXICO_OFFSET).date()
    count_3m = 0
    count_6m = 0
    count_12m = 0
    sources: dict[str, int] = {}
    for record in inquiries:
        source = str(record.get("source", "Unknown") or "Unknown").strip()
        if source:
            sources[source] = sources.get(source, 0) + 1
        record_date = _to_date(record.get("date", ""))
        if not record_date:
            continue
        months_delta = (today.year - record_date.year) * 12 + (today.month - record_date.month)
        if months_delta <= 3:
            count_3m += 1
        if months_delta <= 6:
            count_6m += 1
        if months_delta <= 12:
            count_12m += 1

    sorted_sources = [name for name, _ in sorted(sources.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "last_3_months": count_3m,
        "last_6_months": count_6m,
        "last_12_months": count_12m,
        "inquiry_sources": sorted_sources[:8],
    }


def _build_credit_radar_scores(
    *,
    summary: dict[str, Any],
    debt_pressure_level: str,
    credit_stability_level: str,
    borrowing_urgency_level: str,
) -> dict[str, int]:
    maturity = min(100, 20 + int(summary.get("oldest_account_age_months", 0) or 0))
    pressure_map = {"low": 25, "medium": 55, "medium_high": 75, "high": 90}
    stability_map = {"low": 30, "medium": 60, "medium_high": 78, "high": 90}
    urgency_map = {"low": 25, "medium": 55, "high": 82}
    history_depth = min(100, 18 + int(summary.get("oldest_account_age_months", 0) or 0))
    cash_tightness = min(
        95,
        int(int(summary.get("avg_credit_utilization_pct", 0) or 0) * 0.9) + 12,
    )
    return {
        "financial_maturity": maturity,
        "repayment_pressure_index": pressure_map.get(debt_pressure_level, 50),
        "credit_stability": stability_map.get(credit_stability_level, 50),
        "borrowing_urgency": urgency_map.get(borrowing_urgency_level, 50),
        "credit_history_depth": history_depth,
        "cash_tightness": max(15, cash_tightness),
    }


def _build_repayment_timeline(
    account_details: list[dict[str, Any]],
    delinquency: dict[str, Any],
) -> list[int]:
    base = 78
    if delinquency.get("max_delinquency_days", 0) >= 30:
        base -= 15
    if delinquency.get("total_delinquent_accounts", 0) >= 2:
        base -= 8
    utilization_values = [
        _to_float(str(item.get("utilization_rate", "0")).replace("%", ""))
        for item in account_details
        if str(item.get("utilization_rate", "")).endswith("%")
    ]
    avg_util = sum(utilization_values) / len(utilization_values) if utilization_values else 0
    if avg_util >= 75:
        base -= 12
    elif avg_util >= 55:
        base -= 6
    values = []
    for idx in range(12):
        wave = ((idx % 5) - 2) * 3
        values.append(max(35, min(96, int(base + wave))))
    return values


def _build_repayment_amount_timeline(
    credit_records: list[dict[str, Any]],
    account_details: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    today = datetime.now(tz=MEXICO_OFFSET).date()
    months: list[tuple[int, int]] = []
    anchor = today.replace(day=1)
    for offset in range(11, -1, -1):
        month_date = _shift_month(anchor, -offset)
        months.append((month_date.year, month_date.month))

    amount_map: dict[tuple[int, int], int] = {item: 0 for item in months}
    note_map: dict[tuple[int, int], str] = {
        item: "当月暂无可识别的还款或应还金额记录。" for item in months
    }

    for record in credit_records:
        pay_amount = _to_int(_pick_first(record, "montoultimopago", "montopagar", "payment", "pago"))
        date_text = _pick_first(
            record,
            "fechaultimopago",
            "fechaactualizacion",
            "fechareporte",
            "fechaaperturacuenta",
        )
        pay_date = _to_date(date_text)
        if not pay_date:
            continue
        key = (pay_date.year, pay_date.month)
        if key not in amount_map:
            continue
        amount_map[key] += max(0, pay_amount)
        institution = _pick_first(record, "credito_nombreotorgante", "nombreotorgante", "institution")
        note_map[key] = (
            f"{pay_date.strftime('%Y-%m-%d')} 识别到 {institution or '该账户'} 的还款/应还金额约 "
            f"{max(0, pay_amount)} MXN。"
        )

    if sum(amount_map.values()) == 0:
        fallback_monthly = sum(int(item.get("monthly_payment_mxn", 0) or 0) for item in account_details)
        if fallback_monthly > 0:
            latest_key = months[-1]
            amount_map[latest_key] = fallback_monthly
            note_map[latest_key] = (
                f"未识别到明确的月度还款流水，当前在最近月份展示估算月还款 "
                f"{fallback_monthly} MXN。"
            )

    return {
        "amounts": [amount_map[item] for item in months],
        "notes": [note_map[item] for item in months],
    }


def _shift_month(date_value: date, delta_months: int) -> date:
    month_index = (date_value.month - 1) + delta_months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    return date_value.replace(year=year, month=month, day=1)


def _derive_repayment_status(max_dpd: int, total_delinquent: int) -> str:
    if max_dpd >= 60 or total_delinquent >= 2:
        return "watchlist"
    if max_dpd >= 30 or total_delinquent == 1:
        return "normal"
    return "stable"


def _build_credit_name(row: dict[str, Any]) -> str:
    full_name = " ".join(
        [
            str(row.get("nombres", "") or "").strip(),
            str(row.get("apellidopaterno", "") or "").strip(),
            str(row.get("apellidomaterno", "") or "").strip(),
        ]
    ).strip()
    return full_name or "Unknown User"


def _estimate_age(birth_raw: Any) -> int:
    birth = _to_date(birth_raw)
    if not birth:
        return 0
    today = datetime.now(tz=MEXICO_OFFSET).date()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return max(0, years)


def _split_score_reasons(reasons_raw: Any) -> list[str]:
    text = str(reasons_raw or "").strip()
    if not text:
        return []
    normalized = text.replace("|", ",").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _score_to_band(score_value: int, *, pack: Any) -> str:
    if score_value <= 0:
        return "unknown"
    for band, threshold in pack.score_band_thresholds:
        if score_value >= int(threshold):
            return band
    return pack.score_band_thresholds[-1][0]


def _normalize_credit_date(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y%m%d", "%d-%m-%Y"):
        try:
            if fmt == "%Y%m%d":
                return datetime.strptime(text[:8], fmt).strftime("%Y-%m-%d")
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except Exception:  # pylint: disable=broad-except
            continue
    timestamp_value = _to_float(text)
    if timestamp_value > 1_000_000_000:
        if timestamp_value > 10_000_000_000:
            timestamp_value = timestamp_value / 1000
        try:
            return datetime.fromtimestamp(timestamp_value, tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:  # pylint: disable=broad-except
            return ""
    return text[:10]


def _to_date(raw: Any) -> date | None:
    normalized = _normalize_credit_date(raw)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except Exception:  # pylint: disable=broad-except
        return None


def _months_since(normalized_date: str) -> int:
    date_value = _to_date(normalized_date)
    if not date_value:
        return 0
    today = datetime.now(tz=MEXICO_OFFSET).date()
    return max(0, (today.year - date_value.year) * 12 + (today.month - date_value.month))


def _pick_first(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value or 0).replace(",", "").strip()))
    except Exception:  # pylint: disable=broad-except
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value or 0).replace(",", "").strip())
    except Exception:  # pylint: disable=broad-except
        return 0.0
