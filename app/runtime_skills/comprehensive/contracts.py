"""Type contracts for the comprehensive six-step pipeline.

fallback_reason 已知取值（自由字符串，不强枚举）：
    ""                                       LLM 被采纳
    "upstream_all_missing"                   data_missing 路径
    "model_mode_mock"
    "empty_explanation_payload"
    "schema_validation_failed: <exc>"
    "<model_client status>"                  例如 timeout / json_parse_error / http_<code>
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from app.core.config import settings
from app.country_packs.app_profile import load_app_country_pack


class ComprehensiveRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    trace_id: str
    enable_llm_explanation: bool
    language: str
    channel: str


class ComprehensiveUpstreamBundle(TypedDict):
    uid: str
    country_code: str
    app_result: dict[str, Any]
    behavior_result: dict[str, Any]
    credit_result: dict[str, Any]
    app_status: str
    behavior_status: str
    credit_status: str
    ok_count: int
    missing_modules: list[str]
    data_status: str
    errors: list[str]


class ComprehensiveFeatureBundle(TypedDict):
    uid: str
    country_code: str
    app_metrics: dict[str, Any]
    behavior_metrics: dict[str, Any]
    credit_metrics: dict[str, Any]
    app_score: int
    behavior_score: int
    credit_score: int
    upstream_summaries: dict[str, str]
    feature_status: str
    errors: list[str]


class ComprehensiveDecisionResult(TypedDict):
    uid: str
    country_code: str
    decision_status: str
    segment: str
    overall_risk_level: str
    value_signal_level: str
    confidence_level: str
    conflict_explanations: list[str]
    persona_seed: str
    tags_rule: list[str]
    metrics: dict[str, Any]
    errors: list[str]


class ComprehensiveExplanationResult(TypedDict):
    uid: str
    country_code: str
    explanation_status: str
    used_llm: bool
    summary: str
    persona: str
    tags_addon: list[str]
    conflict_explanations: list[str]
    reasoning_texts: dict[str, str]
    model_trace: dict[str, Any]
    errors: list[str]


class ComprehensivePageResult(TypedDict):
    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_comprehensive_run_context(
    uid: str,
    *,
    application_time: str | None = None,
    country_code: str | None = None,
    trace_id: str = "",
    enable_llm_explanation: bool = True,
    language: str | None = None,
    channel: str = "api",
) -> ComprehensiveRunContext:
    """Create a stable run context for the comprehensive pipeline.

    Mirrors build_app_run_context in app/runtime_skills/app_profile/contracts.py.
    """
    pack = load_app_country_pack(country_code or settings.default_country_code)
    application_time_value = application_time or datetime.now(timezone.utc).isoformat()
    return {
        "uid": uid,
        "country_code": pack.country_code,
        "application_time": application_time_value,
        "trace_id": trace_id,
        "enable_llm_explanation": enable_llm_explanation,
        "language": language or pack.default_language,
        "channel": channel or "api",
    }
