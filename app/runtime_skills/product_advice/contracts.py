"""Shared contracts for the Product Advice skill (stage=2)."""

from __future__ import annotations

from typing import Any, TypedDict

class ProductAdviceRunContext(TypedDict):
    """Context shared by all internal Product Advice layers."""

    uid: str
    trace_id: str
    channel: str
    country_code: str


class ProductAdviceUpstreamBundle(TypedDict):
    """Subset of comprehensive_profile fields consumed by Product Advice."""

    data_status: str
    segment: str
    segment_name: str
    overall_risk: str
    overall_value: str
    behavior_tags: dict[str, Any]
    financial_tags: dict[str, Any]
    confidence: str
    data_completeness: dict[str, Any]
    raw: dict[str, Any]


class ProductAdviceFeatureBundle(TypedDict):
    """Normalized features feeding the decision engine."""

    segment: str
    overall_risk: str
    overall_value: str
    multi_head_risk: str
    debt_pressure: str
    borrowing_urgency: str
    product_activity: str
    contact_channel: str
    contact_time: str


class ProductAdviceDecisionResult(TypedDict):
    """Deterministic rules-engine output."""

    segment: str
    renewal_strategy: dict[str, Any]
    credit_line_action: dict[str, Any]
    rate_plan: dict[str, Any]
    recommended_channel: dict[str, Any]
    priority: str
    tags: list[str]


class ProductAdviceExplanationResult(TypedDict):
    """LLM enhancement output (status + payload)."""

    status: str
    payload: dict[str, Any]
    fallback_reason: str
    used_llm: bool
    model_name: str


class ProductAdvicePageResult(TypedDict):
    """Final AgentOutput-shaped payload."""

    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_product_advice_run_context(
    uid: str,
    *,
    trace_id: str = "",
    channel: str = "api",
    country_code: str | None = None,
) -> ProductAdviceRunContext:
    from app.core.config import settings
    return {
        "uid": uid,
        "trace_id": trace_id,
        "channel": channel or "api",
        "country_code": country_code or settings.default_country_code,
    }
