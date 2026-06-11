"""Shared contracts for the Ops Advice skill (stage=2)."""

from __future__ import annotations

from typing import Any, TypedDict


class OpsAdviceRunContext(TypedDict):
    """Context shared by all internal Ops Advice layers."""

    uid: str
    trace_id: str
    channel: str
    country_code: str


class OpsAdviceUpstreamBundle(TypedDict):
    """Subset of comprehensive_profile fields consumed by Ops Advice."""

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


class OpsAdviceFeatureBundle(TypedDict):
    """Normalized features feeding the decision engine."""

    segment: str
    churn_risk: str
    churn_root_cause: list[str]
    debt_pressure: str
    multi_head_risk: str
    contact_channel: str
    contact_time: str
    overall_risk: str


class OpsAdviceDecisionResult(TypedDict):
    """Deterministic rules-engine output."""

    segment: str
    collection_strategy: dict[str, Any]
    churn_warning: dict[str, Any]
    outreach_channel: dict[str, Any]
    retention_offer: dict[str, Any]
    tags: list[str]


class OpsAdviceExplanationResult(TypedDict):
    """LLM enhancement output (status + payload)."""

    status: str
    payload: dict[str, Any]
    fallback_reason: str
    used_llm: bool
    model_name: str


class OpsAdvicePageResult(TypedDict):
    """Final AgentOutput-shaped payload."""

    summary: str
    structured_result: dict[str, Any]
    charts: list[dict[str, Any]]
    report_markdown: str


def build_ops_advice_run_context(
    uid: str,
    *,
    trace_id: str = "",
    channel: str = "api",
    country_code: str | None = None,
) -> OpsAdviceRunContext:
    from app.core.config import settings
    return {
        "uid": uid,
        "trace_id": trace_id,
        "channel": channel or "api",
        "country_code": country_code or settings.default_country_code,
    }
