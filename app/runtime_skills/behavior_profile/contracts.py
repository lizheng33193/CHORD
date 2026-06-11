"""Shared contracts and helpers for the layered Behavior profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.config import settings
from app.country_packs.behavior_profile import load_behavior_country_pack
from app.scripts.behavior_prepared_builder import BEHAVIOR_PREPARED_SCHEMA_VERSION


class BehaviorRunContext(TypedDict):
    """Context shared by all internal Behavior profile layers."""

    uid: str
    country_code: str
    application_time: str
    trace_id: str
    source_preference: str
    enable_llm_explanation: bool
    language: str
    channel: str


class BehaviorPreparedRecord(TypedDict):
    """Canonical prepared Behavior record used across runtime layers."""

    uid: str
    country_code: str
    schema_version: str
    profile_header: dict[str, Any]
    session_summary: dict[str, Any]
    engagement_signals: dict[str, Any]
    repayment_signals: dict[str, Any]
    product_intent_signals: dict[str, Any]
    churn_signals: dict[str, Any]
    contact_signals: dict[str, Any]
    timeline_sections: list[dict[str, Any]]
    timeline_sections_raw: list[dict[str, Any]]
    timeline_sections_compact: list[dict[str, Any]]
    timeline_insights: list[str]
    source_meta: dict[str, Any]


class BehaviorRawData(TypedDict):
    """Canonical raw-data contract used after repository access."""

    uid: str
    country_code: str
    source_meta: dict[str, Any]
    prepared_record: BehaviorPreparedRecord
    data_status: str
    errors: list[str]


class BehaviorFeatureBundle(TypedDict):
    """Deterministic Behavior feature bundle."""

    uid: str
    country_code: str
    prepared_record: BehaviorPreparedRecord
    summary_features: dict[str, Any]
    timeline_features: dict[str, Any]
    derived_signals: dict[str, Any]
    feature_status: str
    errors: list[str]


class BehaviorDecisionResult(TypedDict):
    """Rule-driven Behavior decision output."""

    uid: str
    country_code: str
    decision_status: str
    summary_seed: str
    evidence_seed: dict[str, Any]
    engagement_profile: dict[str, Any]
    repayment_willingness: dict[str, Any]
    product_sensitivity: dict[str, Any]
    churn_risk: dict[str, Any]
    contact_preference: dict[str, Any]
    behavior_signal_score: int
    metrics: dict[str, Any]
    tags_rule: list[str]
    llm_fallback_profile: dict[str, Any]
    errors: list[str]


class BehaviorExplanationResult(TypedDict):
    """LLM explanation output merged onto the deterministic fallback."""

    uid: str
    country_code: str
    explanation_status: str
    used_llm: bool
    summary: str
    tags: list[str]
    churn_root_cause: list[str]
    evidence_patch: dict[str, Any]
    report_markdown: str
    model_trace: dict[str, Any]
    errors: list[str]


class BehaviorPageResult(TypedDict):
    """Final Behavior page payload returned to orchestrator/API."""

    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_behavior_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    source_preference: str | None = None,
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> BehaviorRunContext:
    """Create a stable run context for the Behavior profile pipeline."""
    pack = load_behavior_country_pack(country_code or settings.default_country_code)
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
    }


def build_empty_prepared_record(uid: str, *, country_code: str) -> BehaviorPreparedRecord:
    """Create an empty prepared record for degraded or missing inputs."""
    normalized_country = str(country_code or settings.default_country_code).lower()
    pack = load_behavior_country_pack(normalized_country)
    return {
        "uid": uid,
        "country_code": normalized_country,
        "schema_version": BEHAVIOR_PREPARED_SCHEMA_VERSION,
        "profile_header": {
            "uid": uid,
            "event_span_start": "",
            "event_span_end": "",
            "event_days": 0,
            "channel": pack.default_contact_channel,
        },
        "session_summary": {
            "avg_session_minutes": 0,
            "session_count": 0,
            "deep_session_count": 0,
            "recent_7d_event_count": 0,
            "active_days_30d": 0,
            "total_events": 0,
        },
        "engagement_signals": {
            "engagement_score": 0,
            "engagement_level": "light",
            "active_days_30d": 0,
            "session_count": 0,
            "avg_session_minutes": 0,
            "deep_session_count": 0,
            "recent_7d_event_count": 0,
            "analysis_mode": "missing",
        },
        "repayment_signals": {
            "repayment_willingness_level": "medium",
            "repayment_event_count": 0,
            "has_overdue_signal": False,
            "evidence": [],
        },
        "product_intent_signals": {
            "product_sensitivity_level": "medium",
            "purchase_preference": "unknown",
            "pricing_event_count": 0,
            "apply_event_count": 0,
        },
        "churn_signals": {
            "churn_risk_level": "medium",
            "warning_event_count": 0,
            "dropoff_stage": "unknown",
            "risk_signals": [],
        },
        "contact_signals": {
            "best_channel": pack.default_contact_channel,
            "best_time": pack.default_contact_time,
            "confidence": "low",
            "reason": "缺少行为事件输入，使用默认触达建议。",
            "observed_channels": [],
        },
        "timeline_sections": [],
        "timeline_sections_raw": [],
        "timeline_sections_compact": [],
        "timeline_insights": [],
        "source_meta": {
            "source_type": "",
            "origin_ref": "",
            "source_variant": "missing",
            "source_display_name": pack.source_display_name,
            "event_count": 0,
            "timeline_section_count": 0,
        },
    }
