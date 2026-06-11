"""Orchestrator Agent resilience: tenacity retry + consecutive failure tripwire.

Note: Plan #01 已在 Provider 层做 retry；本模块仅做 agent_loop 级别的
连续失败 tripwire。tenacity import 保留供未来 agent_loop 重试 LLM 决策时用。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 连续工具失败上限：达此值则强制结束 session
CONSECUTIVE_FAILURE_LIMIT = 3


class ConsecutiveFailures(Exception):
    """Raised when too many tool calls return error in a row."""


def check_consecutive_failures(session, tool_status: str) -> None:
    """Update session.consecutive_failures and raise if exceeds limit.

    Call this after every tool execution in agent_loop.
    - tool_status == 'ok'    → reset to 0
    - tool_status == 'error' → +1; raise ConsecutiveFailures at limit
    """
    if tool_status == "ok":
        session.consecutive_failures = 0
        return
    session.consecutive_failures = getattr(session, "consecutive_failures", 0) + 1
    if session.consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
        raise ConsecutiveFailures(
            f"{CONSECUTIVE_FAILURE_LIMIT} consecutive tool failures; aborting session"
        )
