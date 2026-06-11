"""Internal-only execution trace metadata helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.services.orchestrator_agent.schemas import ExecutionTraceRecord


logger = logging.getLogger(__name__)


def update_internal_trace_metadata(
    trace: ExecutionTraceRecord | None,
    values: Mapping[str, Any] | None,
) -> None:
    """Best-effort merge into trace.internal_metadata without side effects."""

    if trace is None or values is None:
        return
    if not isinstance(values, Mapping):
        logger.debug("trace metadata update ignored: values is not a mapping")
        return

    try:
        current = getattr(trace, "internal_metadata", None)
        if not isinstance(current, dict):
            current = {}
            trace.internal_metadata = current
        current.update(dict(values))
    except Exception:
        logger.debug("failed to update internal trace metadata", exc_info=True)
