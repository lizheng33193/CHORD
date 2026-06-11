"""Shared contracts and helpers for the layered Credit profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.config import settings
from app.country_packs.credit_profile import load_credit_country_pack
from app.scripts.credit_prepared_builder import CREDIT_PREPARED_SCHEMA_VERSION


class CreditRunContext(TypedDict):
    """Context shared by all internal Credit profile layers."""

    uid: str
    country_code: str
    application_time: str
    trace_id: str
    source_preference: str
    enable_llm_explanation: bool
    language: str
    channel: str
    profile_mode: str


class CreditPreparedRecord(TypedDict):
    """Canonical prepared Credit record used across runtime layers."""

    uid: str
    country_code: str
    schema_version: str
    profile_header: dict[str, Any]
    summary: dict[str, Any]
    delinquency: dict[str, Any]
    inquiries: dict[str, Any]
    account_details: list[dict[str, Any]]
    score: dict[str, Any]
    repayment_timeline: list[int]
    repayment_amount_timeline: list[int]
    repayment_amount_notes: list[str]
    source_meta: dict[str, Any]


class CreditRawData(TypedDict):
    """Canonical raw-data contract used after repository access.

    v6.1 路径 Q：新增 risk_features_record 字段，承载 TH 风控特征聚合表原始数据。
    - mx (profile_mode="buro"): risk_features_record 永远为 None
    - th (profile_mode="risk_features"): risk_features_record 填 11 维原始 dict
    """

    uid: str
    country_code: str
    source_meta: dict[str, Any]
    prepared_record: CreditPreparedRecord
    risk_features_record: dict[str, Any] | None
    data_status: str
    errors: list[str]


class CreditFeatureBundle(TypedDict):
    """Deterministic Credit feature bundle."""

    uid: str
    country_code: str
    prepared_record: CreditPreparedRecord
    summary_features: dict[str, Any]
    account_features: dict[str, Any]
    derived_signals: dict[str, Any]
    feature_status: str
    errors: list[str]


class CreditDecisionResult(TypedDict):
    """Rule-driven Credit decision output."""

    uid: str
    country_code: str
    decision_status: str
    summary_seed: str
    evidence_seed: dict[str, Any]
    financial_maturity: dict[str, Any]
    debt_pressure: dict[str, Any]
    credit_stability: dict[str, Any]
    borrowing_urgency: dict[str, Any]
    credit_signal_score: int
    metrics: dict[str, Any]
    tags_rule: list[str]
    llm_fallback_profile: dict[str, Any]
    errors: list[str]


class CreditExplanationResult(TypedDict):
    """LLM explanation output merged onto the deterministic fallback."""

    uid: str
    country_code: str
    explanation_status: str
    used_llm: bool
    summary: str
    tags: list[str]
    evidence_patch: dict[str, Any]
    report_markdown: str
    model_trace: dict[str, Any]
    errors: list[str]


class CreditPageResult(TypedDict):
    """Final Credit page payload returned to orchestrator/API."""

    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_credit_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    source_preference: str | None = None,
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> CreditRunContext:
    """Create a stable run context for the Credit profile pipeline."""
    pack = load_credit_country_pack(country_code or settings.default_country_code)
    application_time_value = application_time or datetime.now(timezone.utc).isoformat()
    return {
        "uid": uid,
        "country_code": pack.country_code,
        "application_time": application_time_value,
        "trace_id": trace_id,
        "source_preference": source_preference or settings.data_source,
        "enable_llm_explanation": enable_llm_explanation,
        "language": language or pack.default_language,
        "channel": channel or "api",
        "profile_mode": pack.profile_mode,
    }


def build_empty_prepared_record(uid: str, *, country_code: str) -> CreditPreparedRecord:
    """Create an empty prepared record for degraded or missing inputs."""
    normalized_country = str(country_code or settings.default_country_code).lower()
    return {
        "uid": uid,
        "country_code": normalized_country,
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
            "score_model": "unknown",
            "score_value": 0,
            "score_reasons": [],
            "credit_score_band": "unknown",
            "repayment_status": "unknown",
        },
        "repayment_timeline": [0] * 12,
        "repayment_amount_timeline": [0] * 12,
        "repayment_amount_notes": ["No repayment detail available."] * 12,
        "source_meta": {
            "source_type": "",
            "origin_ref": "",
            "source_variant": "missing",
            "credit_report_date": "",
            "currency_code": "MXN",
            "source_display_name": "Buro de Credito (MX)",
        },
    }
