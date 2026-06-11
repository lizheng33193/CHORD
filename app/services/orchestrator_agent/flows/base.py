"""Base flow protocol for migrated orchestrator intent handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol, TypeAlias

from app.services.orchestrator_agent.loop_context import FlowContext
from app.services.orchestrator_agent.schemas import NormalizedRequest


@dataclass(slots=True)
class FlowControlSignal:
    kind: Literal["clarification_resume"]
    payload: dict[str, Any]


FlowOutput: TypeAlias = dict[str, Any] | FlowControlSignal


class KnownFlow(Protocol):
    intent: str

    async def can_handle(
        self,
        ctx: FlowContext,
        request: NormalizedRequest,
    ) -> bool:
        ...

    async def run(
        self,
        ctx: FlowContext,
        request: NormalizedRequest,
    ) -> AsyncIterator[FlowOutput]:
        ...
