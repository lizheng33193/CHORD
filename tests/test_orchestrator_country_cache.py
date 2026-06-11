"""Plan 05 v6.1 §3.11 — module cache must be isolated by country_code.

Same (uid, module, application_time) but different country_code MUST yield
two distinct cache entries; otherwise mx and th would alias each other and a
country switch would silently return the wrong country's data.
"""

from __future__ import annotations

from app.services.orchestrator import AnalysisOrchestrator


def test_module_cache_isolated_by_country() -> None:
    orch = AnalysisOrchestrator()
    uid = "U" * 18
    application_time = "2026-05-06 12:00:00"

    mx_payload = {"country": "mx", "score": 1}
    th_payload = {"country": "th", "score": 2}

    orch._set_cached(uid, "app", application_time, "mx", mx_payload)
    orch._set_cached(uid, "app", application_time, "th", th_payload)

    mx_hit = orch._get_cached(uid, "app", application_time, "mx")
    th_hit = orch._get_cached(uid, "app", application_time, "th")

    assert mx_hit == mx_payload
    assert th_hit == th_payload
    assert mx_hit != th_hit

    # Cross-country lookups must miss when only the other country is cached.
    other_orch = AnalysisOrchestrator()
    other_orch._set_cached(uid, "behavior", application_time, "mx", {"v": 1})
    assert other_orch._get_cached(uid, "behavior", application_time, "th") is None
