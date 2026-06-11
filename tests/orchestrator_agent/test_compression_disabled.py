"""Phase 5 Task 5.4 — env 短路 (Plan 10 v3.2 验收)。

MEMORY_COMPRESSION_ENABLED=0 → ensure_context_fits 返回 False，messages 完全不变。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.orchestrator_agent.context_fit import (
    MODEL_MAX_TOKENS_PER_TURN,
    ensure_context_fits,
)
from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage,
    OrchestratorSession,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.timeout(2)
def test_compression_disabled_via_env(monkeypatch):
    monkeypatch.setenv("MEMORY_COMPRESSION_ENABLED", "0")

    bloat = "x" * 250_000
    msgs = [
        OrchestratorMessage(role="user", content=f"q{i} {bloat}", timestamp=_now())
        for i in range(15)
    ]
    session = OrchestratorSession(
        session_id="sess_disabled",
        created_at=_now(),
        updated_at=_now(),
        messages=list(msgs),
    )

    snapshot = [(m.role, m.content) for m in session.messages]
    triggered = ensure_context_fits(
        session, country="mx", max_tokens=MODEL_MAX_TOKENS_PER_TURN,
    )

    assert triggered is False
    assert [(m.role, m.content) for m in session.messages] == snapshot
