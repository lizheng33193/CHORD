"""SSE streaming endpoint for /api/analyze-stream.

Implementation per docs/plans/sse-progress-plan.md Task 3.
Design: docs/specs/sse-progress-design.md §4.

Architecture:
    POST request
       │
       ├─ background threading.Thread runs orchestrator.analyze(...,
       │       progress_callback=lambda evt: q.put(evt))
       │       Final events: analysis_completed, then None sentinel.
       │
       └─ event_gen() main coroutine reads queue via run_in_executor,
          yields SSE wire format. On HEARTBEAT_INTERVAL_SEC idle yields
          ': keepalive' comment line.

Total-timeout watchdog and stream_error guards land in Task 4.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import require_permission
from app.auth.permissions import require_country_access
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.schemas.request import AnalyzeRequest
from app.services.batch_service import BatchAnalysisService
from app.services.orchestrator import shared_orchestrator


router = APIRouter()
_batch_service = BatchAnalysisService(shared_orchestrator)

HEARTBEAT_INTERVAL_SEC = 15
TOTAL_SKILLS_PER_UID = 6
TOTAL_TIMEOUT_SEC = 600  # 10-minute hard cap (Design Doc §6.1)


def _format_event(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _run_analysis_in_thread(
    uids: list[str],
    application_time: str | None,
    q: queue.Queue,
    country_code: str = "mx",
) -> None:
    """Background thread entry: run orchestrator + push events into queue."""
    try:
        q.put({
            "type": "analysis_started",
            "uids": uids,
            "total_skills_per_uid": TOTAL_SKILLS_PER_UID,
        })

        def cb(evt: dict[str, Any]) -> None:
            q.put(evt)

        response = shared_orchestrator.analyze(
            uids,
            application_time=application_time,
            country_code=country_code,
            progress_callback=cb,
        )

        q.put({
            "type": "analysis_completed",
            "results": [r.model_dump(mode="json") for r in response.results],
        })
    except Exception as exc:  # noqa: BLE001 — bottom-of-stack guard
        q.put({"type": "stream_error", "error_message": str(exc)})
    finally:
        q.put(None)  # sentinel


@router.post("/analyze-stream", summary="Stream analysis progress as Server-Sent Events")
async def analyze_stream(
    http_request: Request,
    request: AnalyzeRequest,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> StreamingResponse:
    """Return text/event-stream of skill-level progress events.

    Input validation failures raise 400 via the global RequestValidationError
    handler in app/main.py — they never enter the stream.
    """
    require_country_access(ctx, request.country, project_id=ctx.project_id)
    uids = request.get_uid_list()
    application_time = request.application_time
    country_code = request.country
    record_runtime_audit_event(
        user=ctx,
        request_id=http_request.headers.get("X-Request-ID"),
        event_type="profile.run",
        action="run",
        resource_type="profile_stream",
        resource_id="batch_stream",
        metadata={"country": country_code, "uid_count": len(uids), "stream": True},
    )
    q: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_analysis_in_thread,
        args=(uids, application_time, q),
        kwargs={"country_code": country_code},
        daemon=True,
    )
    thread.start()

    async def event_gen():
        loop = asyncio.get_event_loop()
        deadline = loop.time() + TOTAL_TIMEOUT_SEC
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                yield _format_event({
                    "type": "stream_error",
                    "error_message": f"stream timeout after {TOTAL_TIMEOUT_SEC}s",
                })
                return
            wait_for = min(HEARTBEAT_INTERVAL_SEC, remaining)
            try:
                evt = await asyncio.wait_for(
                    loop.run_in_executor(None, q.get),
                    timeout=wait_for,
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if evt is None:
                break
            yield _format_event(evt)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
