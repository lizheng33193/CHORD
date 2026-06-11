"""Phase 2 RED contract tests: session_store / resilience / budget / uid_whitelist."""

from __future__ import annotations

import threading
import time

import pytest

from app.services.orchestrator_agent.session_store import (
    create_session, get_session, save_session, flush,
)
from app.services.orchestrator_agent.budget import (
    check_and_increment, BudgetExceeded, DEFAULT_BUDGET,
)
from app.services.orchestrator_agent.uid_whitelist import validate_uid
from app.services.orchestrator_agent.resilience import (
    check_consecutive_failures, ConsecutiveFailures, CONSECUTIVE_FAILURE_LIMIT,
)


# ---- session_store ----

def test_session_create_and_load_round_trip(tmp_path, monkeypatch):
    sess = create_session()
    save_session(sess)
    flush()
    loaded = get_session(sess.session_id)
    assert loaded is not None
    assert loaded.session_id == sess.session_id


def test_get_session_returns_none_for_unknown():
    assert get_session("definitely-not-existing-xxx") is None


def test_session_round_trip_preserves_query_cancelled_and_consecutive():
    sess = create_session()
    sess.query_cancelled = True
    sess.consecutive_failures = 2
    save_session(sess)
    flush()
    loaded = get_session(sess.session_id)
    assert loaded.query_cancelled is True
    assert loaded.consecutive_failures == 2


# ---- budget ----

def test_budget_warning_at_80_percent():
    sess = create_session()
    out = check_and_increment(sess, int(DEFAULT_BUDGET * 0.85))
    assert out["warn"] is True
    assert out["percentage"] >= 0.8


def test_budget_below_80_no_warning():
    sess = create_session()
    out = check_and_increment(sess, int(DEFAULT_BUDGET * 0.5))
    assert out["warn"] is False


def test_budget_hard_stop_over_100_percent():
    sess = create_session()
    sess.total_tokens = 0
    with pytest.raises(BudgetExceeded):
        check_and_increment(sess, DEFAULT_BUDGET + 1)


# ---- uid_whitelist ----

def test_uid_whitelist_th_valid():
    assert validate_uid("TH000123", "th") is True


def test_uid_whitelist_th_too_short():
    assert validate_uid("TH0", "th") is False  # th 要求长度 8-32


def test_uid_whitelist_mx_valid():
    assert validate_uid("MX0001", "mx") is True


def test_uid_whitelist_unknown_country():
    assert validate_uid("U001", "us") is False


# ---- resilience: consecutive_failures ----

def test_consecutive_failures_resets_on_ok():
    sess = create_session()
    sess.consecutive_failures = 2
    check_consecutive_failures(sess, "ok")
    assert sess.consecutive_failures == 0


def test_consecutive_failures_increments_on_error():
    sess = create_session()
    sess.consecutive_failures = 0
    check_consecutive_failures(sess, "error")
    assert sess.consecutive_failures == 1


def test_consecutive_failures_raises_at_limit():
    sess = create_session()
    sess.consecutive_failures = CONSECUTIVE_FAILURE_LIMIT - 1
    with pytest.raises(ConsecutiveFailures):
        check_consecutive_failures(sess, "error")
