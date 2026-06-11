"""Shared contracts and helpers for the layered App profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.config import settings
from app.country_packs.app_profile import load_app_country_pack


class AppRunContext(TypedDict):
    """Context shared by all internal App profile layers."""

    uid: str
    country_code: str
    application_time: str
    trace_id: str
    source_preference: str
    enable_llm_explanation: bool
    language: str
    channel: str


class AppRawData(TypedDict):
    """Canonical raw-data contract used after repository access."""

    uid: str
    country_code: str
    source_meta: dict[str, Any]
    records: list[dict[str, Any]]
    data_status: str
    errors: list[str]


class AppFeatureBundle(TypedDict):
    """Deterministic App feature bundle."""

    uid: str
    country_code: str
    application_time: str
    normalized_apps: list[dict[str, Any]]
    aggregate_features: dict[str, Any]
    signal_features: dict[str, Any]
    evidence_features: dict[str, Any]
    visual_features: dict[str, Any]
    feature_status: str
    errors: list[str]


class AppDecisionResult(TypedDict):
    """Rule-driven App decision output."""

    uid: str
    country_code: str
    decision_status: str
    summary_seed: str
    app_insight_seed: dict[str, Any]
    activity_level: str
    risk_assessment: dict[str, Any]
    financial_maturity: dict[str, Any]
    consumption_profile: dict[str, Any]
    metrics: dict[str, Any]
    tags_rule: list[str]
    recommendation: dict[str, Any]
    visuals: dict[str, Any]
    timeline: list[dict[str, Any]]
    errors: list[str]


class AppExplanationResult(TypedDict):
    """LLM explanation output merged onto the deterministic fallback."""

    uid: str
    country_code: str
    explanation_status: str
    used_llm: bool
    summary: str
    tags: list[str]
    app_insight: dict[str, Any]
    reasoning_texts: dict[str, str]
    report_markdown: str
    model_trace: dict[str, Any]
    errors: list[str]


class AppPageResult(TypedDict):
    """Final App page payload returned to orchestrator/API."""

    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_app_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    source_preference: str | None = None,
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> AppRunContext:
    """Create a stable run context for the App profile pipeline."""
    pack = load_app_country_pack(country_code or settings.default_country_code)
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
