"""TypedDict contracts for the trace_analyzer pipeline.

Trace analyzer is an independent service module (not a SkillRegistry Skill).
See docs/specs/trace-analyzer-design.md §3 governance boundary.
"""
from __future__ import annotations

from typing import Any, TypedDict


class TraceRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    enable_llm_explanation: bool


class TraceRawData(TypedDict):
    uid: str
    events_df: Any  # pandas DataFrame
    data_status: str  # ok | data_missing | error
    errors: list[str]


class TraceFeatureBundle(TypedDict):
    uid: str
    event_window: dict[str, Any]
    path_graph: dict[str, Any]
    friction_hotspots: list[dict[str, Any]]
    time_pattern: dict[str, Any]
    key_events_tail: list[dict[str, Any]]
    churn_root_cause_candidates: list[dict[str, Any]]
    feature_status: str
    errors: list[str]


class TraceDecisionResult(TypedDict):
    uid: str
    decision_status: str
    prompt_payload: dict[str, Any]
    fallback_story: str
    fallback_interventions: list[dict[str, Any]]
    errors: list[str]


class TraceExplanationResult(TypedDict):
    uid: str
    explanation_status: str  # ok | model_unavailable | skipped
    used_llm: bool
    churn_story: str
    intervention_suggestions: list[dict[str, Any]]
    churn_root_cause: list[str]
    model_trace: dict[str, Any]
    errors: list[str]
