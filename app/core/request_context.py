"""Per-request metadata for agent harness flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.user_context import UserContext


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    user: UserContext | None
    session_id: str | None = None
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "user": self.user.to_dict() if self.user else None,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
        }
