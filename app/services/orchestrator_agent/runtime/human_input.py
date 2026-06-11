"""Human-in-the-loop controller for ACK and resolution waits."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.services.orchestrator_agent import ack_bus, resolve_bus
from app.services.orchestrator_agent.loop_context import HumanInputResult
from app.services.orchestrator_agent.runtime.session_lifecycle import open_ack_with_run, open_resolution_with_run


class HumanInputController:
    """Async wrapper around thread-based ACK and resolution buses."""

    async def request_ack(
        self,
        *,
        session_id: str,
        ack_id: str,
        run_id: str | None,
        trace_id: str | None = None,
        step_id: str | None = None,
        tool_call_id: str | None = None,
        sql_text: str | None = None,
        rows_estimated: int | None = None,
    ) -> HumanInputResult:
        del trace_id, step_id, tool_call_id, sql_text, rows_estimated
        open_ack_with_run(ack_bus.open_ack, session_id, ack_id=ack_id, run_id=run_id)
        return HumanInputResult(status="resolved", action="ack_requested")

    async def wait_for_ack(
        self,
        *,
        session_id: str,
        timeout_seconds: float = 600.0,
        poll_interval: float = 0.25,
        should_cancel: Any = None,
    ) -> HumanInputResult:
        wait_task = asyncio.create_task(asyncio.to_thread(ack_bus.wait_ack, session_id, timeout_seconds))
        deadline = time.monotonic() + timeout_seconds
        try:
            while not wait_task.done():
                if should_cancel and should_cancel():
                    ack_bus.abort_ack(session_id)
                    await wait_task
                    return HumanInputResult(status="cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(poll_interval, remaining))
            confirmed = await wait_task
        finally:
            if not wait_task.done():
                wait_task.cancel()
        if confirmed is True:
            return HumanInputResult(status="approved")
        if confirmed is False:
            return HumanInputResult(status="rejected")
        return HumanInputResult(status="expired")

    async def request_resolution(
        self,
        *,
        session_id: str,
        resolution_id: str,
        run_id: str | None,
    ) -> HumanInputResult:
        open_resolution_with_run(resolve_bus.open_resolution, session_id, resolution_id=resolution_id, run_id=run_id)
        return HumanInputResult(status="resolved", action="resolution_requested")

    async def wait_for_resolution(self, *, session_id: str, timeout_seconds: float = 600.0) -> HumanInputResult:
        resolution = await asyncio.to_thread(resolve_bus.wait_resolution, session_id, timeout_seconds)
        if not resolution:
            return HumanInputResult(status="expired")
        return HumanInputResult(status="resolved", payload=dict((resolution or {}).get("answers") or {}))
