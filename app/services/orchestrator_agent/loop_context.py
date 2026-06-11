"""Shared runtime context and dependency injection seams for orchestrator flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from app.core.model_client import ModelClient
from app.services.orchestrator_agent.schemas import NormalizedRequest


class HumanInputResult(BaseModel):
    """Structured HITL outcome for ACK and resolution flows."""

    status: Literal["approved", "rejected", "expired", "cancelled", "resolved"]
    action: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


@dataclass(slots=True)
class MemoryFacade:
    """Thin memory wrapper; Phase 6 can swap in richer implementations."""

    read: Callable[..., Any] | None = None
    write: Callable[..., Any] | None = None
    build_context: Callable[..., Any] | None = None
    fit_context: Callable[..., Any] | None = None


@dataclass(slots=True)
class LoopDependencies:
    """Compatibility bridge for old monkeypatch entrypoints."""

    model_client_factory: Callable[[], ModelClient]
    normalize_request: Callable[..., NormalizedRequest]
    refine_normalized_request: Callable[..., NormalizedRequest]
    build_request_understanding: Callable[..., Any]
    check_data_availability: Callable[..., Any]
    get_data_acquisition_capability: Callable[..., Any]
    prepare_repair_query: Callable[..., Any]
    execute_repair_query: Callable[..., Any]
    original_repair_profile_data: Callable[..., Any]
    repair_profile_data: Callable[..., Any]
    execute_query_data_cohort: Callable[..., Any]
    complete_query_data_cohort: Callable[..., Any]


@dataclass(slots=True)
class FlowContext:
    """Per-run context shared by migrated flows."""

    session: Any
    prompt: str
    turn_id: str
    run_id: str
    detected_country: str | None
    client: ModelClient
    lifecycle: Any
    events: Any
    trace: Any
    human_input: Any
    tools: Any
    memory: MemoryFacade | None
    deps: LoopDependencies
    system_prompt: str | None = None
