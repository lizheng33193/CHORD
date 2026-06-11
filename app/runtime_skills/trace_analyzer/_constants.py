"""Constants for trace_analyzer pipeline.

Locks the 8 numbers deferred from docs/specs/trace-analyzer-design.md §11.
Single source of truth — change here propagates to all six pipeline layers.
"""
from __future__ import annotations

# Threshold below which we skip LLM call and return status=insufficient_events.
INSUFFICIENT_EVENTS_THRESHOLD: int = 10

# Path graph top-N
TOP_N_TRANSITIONS: int = 10
TOP_N_PAGES: int = 8

# Friction hotspots top-K (severity-sorted)
TOP_K_FRICTION_HOTSPOTS: int = 5

# Key events tail length (most recent N events, post-redaction, exposed in API)
KEY_EVENTS_TAIL_N: int = 30

# Pre-dropoff key events length (matches product doc "last 10 steps")
KEY_EVENTS_PRE_DROPOFF_N: int = 10

# Token budgets (CJK-weighted estimate). See design §2.Q6.
TOTAL_TOKEN_BUDGET: int = 8000
TIER_2_TOKEN_BUDGET: int = 1500   # friction hotspot details
TIER_3_TOKEN_BUDGET: int = 5000   # key events sequence
# Tier 1 (aggregate summary) is implicit: TOTAL - TIER_2 - TIER_3 = 1500 ceiling, never trimmed.

# Churn root cause whitelist — must match ops_advice/decision_engine.py 6-value set
CHURN_ROOT_CAUSE_ENUM: frozenset[str] = frozenset({
    "credit_limit_unmet",
    "interest_perception_high",
    "competitor_poaching",
    "ux_friction",
    "repayment_burden",
    "no_clear_signal",
})
