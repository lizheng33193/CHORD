"""Pydantic response schema for GET /api/trace/{uid}.

See docs/specs/trace-analyzer-design.md §4.1.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EventWindow(BaseModel):
    start: str = ""
    end: str = ""
    total_events: int = 0
    analyzed_events: int = 0


class PageVisit(BaseModel):
    page: str
    visit_count: int
    avg_stay_seconds: float


class Transition(BaseModel):
    from_page: str = Field(alias="from")
    to_page: str = Field(alias="to")
    count: int

    model_config = {"populate_by_name": True}


class PathGraph(BaseModel):
    top_transitions: list[Transition] = Field(default_factory=list)
    top_pages: list[PageVisit] = Field(default_factory=list)


class FrictionHotspot(BaseModel):
    step: str
    retry_count: int = 0
    error_count: int = 0
    avg_stay_seconds: float = 0.0
    severity: Literal["high", "medium", "low"] = "low"


class TimePattern(BaseModel):
    hour_histogram: list[int] = Field(default_factory=lambda: [0] * 24)
    active_window_label: str = ""


class InterventionSuggestion(BaseModel):
    hotspot: str
    advice: str
    channel_hint: str = ""


class KeyEvent(BaseModel):
    ts_offset: float
    page: str
    event: str
    field: str = ""


class ModelTrace(BaseModel):
    mode: str = "mock"
    used_llm: bool = False
    model_name: str = ""
    fallback_reason: str = ""


class TraceAnalyzeResponse(BaseModel):
    uid: str
    status: Literal[
        "ok",
        "data_missing",
        "insufficient_events",
        "model_unavailable",
        "error",
    ]
    event_window: EventWindow = Field(default_factory=EventWindow)
    path_graph: PathGraph = Field(default_factory=PathGraph)
    friction_hotspots: list[FrictionHotspot] = Field(default_factory=list)
    time_pattern: TimePattern = Field(default_factory=TimePattern)
    churn_root_cause: list[str] = Field(default_factory=list)
    churn_story: str = ""
    intervention_suggestions: list[InterventionSuggestion] = Field(default_factory=list)
    key_events_tail: list[KeyEvent] = Field(default_factory=list)
    model_trace: ModelTrace = Field(default_factory=ModelTrace)
    errors: list[str] = Field(default_factory=list)
