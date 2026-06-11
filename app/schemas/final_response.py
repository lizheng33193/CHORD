"""Final outward API response schema (compatibility target)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChartData(BaseModel):
    """Structured chart payload for frontend rendering."""

    chart_type: str
    title: str
    x_axis: list[str] | None = None
    indicators: list[str] | None = None
    series: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Unified output shape from each skill."""

    summary: str
    structured_result: dict[str, Any] = Field(default_factory=dict)
    charts: list[ChartData] = Field(default_factory=list)
    report_markdown: str


class UserAnalysisResult(BaseModel):
    """Single-user profile result with four core sections plus stage-2 advisory outputs."""

    uid: str
    app_profile: AgentOutput
    behavior_profile: AgentOutput
    credit_profile: AgentOutput
    comprehensive_profile: AgentOutput
    product_advice: AgentOutput | None = None
    ops_advice: AgentOutput | None = None
    standardized_labels: dict[str, Any] | None = None


class AnalyzeResponse(BaseModel):
    """Batch result wrapper."""

    results: list[UserAnalysisResult]

