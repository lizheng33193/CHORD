"""run_profile — thin compatibility wrapper over the Profile DAG runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.profile_dag.adapters import profile_event_to_legacy_module_event
from app.services.orchestrator import AnalysisOrchestrator
from app.services.orchestrator_agent.schemas import (
    RunProfileInput, RunProfileOutput,
)


def run_profile(
    input_data: RunProfileInput,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> RunProfileOutput:
    orch = AnalysisOrchestrator(strict_data_mode=input_data.strict_data_mode)
    requested_modules = list(input_data.modules or ["app"])
    total = len(input_data.uids) * len(requested_modules)
    progress_state = {"completed": 0}

    def _progress_bridge(event: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        progress_callback(event)
        legacy_payload, next_completed = profile_event_to_legacy_module_event(
            event,
            requested_modules=requested_modules,
            completed=progress_state["completed"],
            total=total,
        )
        if legacy_payload is not None:
            progress_state["completed"] = next_completed
            progress_callback(legacy_payload)

    return orch.run_profile_request(
        input_data,
        progress_callback=_progress_bridge if progress_callback is not None else None,
    )
