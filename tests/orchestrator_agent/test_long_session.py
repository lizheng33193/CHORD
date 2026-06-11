"""Phase 5 Task 5.1 — 长会话触发压缩 (Plan 10 v3.2 验收)。

模拟 15 轮膨胀消息，超过 COMPRESSION_THRESHOLD * MODEL_MAX_TOKENS_PER_TURN，
ensure_context_fits 应返回 True 且压缩后 token 数 < max_tokens。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.orchestrator_agent.context_fit import (
    MODEL_MAX_TOKENS_PER_TURN,
    ensure_context_fits,
    estimate_tokens,
)
from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage,
    OrchestratorSession,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.mark.timeout(10)
def test_long_session_triggers_compression_under_max_tokens():
    # 构造 15 轮膨胀消息：每条 ~250k 字符 → token ~83k；15 条 ~ 1.25M token > 800k * 0.80
    bloat = "x" * 250_000
    msgs = [
        OrchestratorMessage(role="user", content=f"q{i} {bloat}", timestamp=_now())
        for i in range(15)
    ]
    session = OrchestratorSession(
        session_id="sess_long",
        created_at=_now(),
        updated_at=_now(),
        messages=msgs,
    )

    assert estimate_tokens(session.messages) > MODEL_MAX_TOKENS_PER_TURN * 0.80

    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "user": [], "feedback": [], "project": [], "reference": [],
        },
    }

    with patch("app.services.orchestrator_agent.memory_flush.ModelClient", return_value=mock_client), \
         patch("app.services.orchestrator_agent.summarizer.ModelClient", return_value=mock_client):
        # summarizer 返回的 structured_result 也兼容（取 "summary" 字段，不存在则走 fallback 文本）
        mock_client.generate_structured.return_value = {
            "status": "ok",
            "structured_result": {"summary": "压缩摘要"},
        }
        triggered = ensure_context_fits(
            session, country="mx", max_tokens=MODEL_MAX_TOKENS_PER_TURN,
        )

    assert triggered is True
    assert estimate_tokens(session.messages) < MODEL_MAX_TOKENS_PER_TURN
