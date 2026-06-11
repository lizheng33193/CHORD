"""Per-session token budget with 80% warning + 100% hard stop."""

from __future__ import annotations


DEFAULT_BUDGET = 500_000


class BudgetExceeded(Exception):
    pass


def check_and_increment(session, used_tokens: int, limit: int = DEFAULT_BUDGET) -> dict:
    """Add used_tokens to session.total_tokens; raise BudgetExceeded if over limit."""
    session.total_tokens += used_tokens
    pct = session.total_tokens / limit
    if pct >= 1.0:
        raise BudgetExceeded(
            f"Session {session.session_id} exceeded budget {limit}; total={session.total_tokens}"
        )
    return {
        "used": session.total_tokens,
        "limit": limit,
        "percentage": pct,
        "warn": pct >= 0.8,
    }
