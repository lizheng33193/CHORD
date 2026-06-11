"""Behavior data preprocessing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def preprocess_behavior_data(raw_behavior: dict[str, Any]) -> dict[str, Any]:
    """Normalize, aggregate and enrich behavior-related fields."""
    if not raw_behavior:
        return {}

    avg_session_minutes = int(raw_behavior.get("avg_session_minutes", 0) or 0)
    login_days_30d = int(raw_behavior.get("login_days_30d", 0) or 0)
    purchase_preference = str(raw_behavior.get("purchase_preference", "") or "")

    engagement_score = min(100, avg_session_minutes * 2 + login_days_30d)
    engagement_level = _to_engagement_level(avg_session_minutes)
    repayment_willingness = _to_repayment_willingness(
        avg_session_minutes=avg_session_minutes,
        login_days_30d=login_days_30d,
        purchase_preference=purchase_preference,
    )
    product_sensitivity = _to_product_sensitivity(purchase_preference)
    churn_risk = _to_churn_risk(
        avg_session_minutes=avg_session_minutes,
        login_days_30d=login_days_30d,
        engagement_level=engagement_level,
    )
    value_signal = _to_value_signal(
        avg_session_minutes=avg_session_minutes,
        login_days_30d=login_days_30d,
        purchase_preference=purchase_preference,
    )
    risk_signals = _to_behavior_risk_signals(
        avg_session_minutes=avg_session_minutes,
        login_days_30d=login_days_30d,
        purchase_preference=purchase_preference,
    )
    contact_preference = _build_contact_preference(
        purchase_preference=purchase_preference,
        login_days_30d=login_days_30d,
    )

    return {
        **raw_behavior,
        "avg_session_minutes": avg_session_minutes,
        "login_days_30d": login_days_30d,
        "purchase_preference": purchase_preference[:64],
        "engagement_score": engagement_score,
        "engagement_level": engagement_level,
        "repayment_willingness": repayment_willingness,
        "product_sensitivity": product_sensitivity,
        "churn_risk": churn_risk,
        "value_signal": value_signal,
        "behavior_risk_signals": risk_signals,
        "contact_preference": contact_preference,
        "analysis_mode": "proxy_from_sample_metrics",
        "market_context": "mexico_cash_loan_behavior",
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _to_engagement_level(avg_session_minutes: int) -> str:
    """Map average session length to engagement level."""
    if avg_session_minutes >= 45:
        return "deep"
    if avg_session_minutes >= 25:
        return "balanced"
    return "light"


def _to_repayment_willingness(
    avg_session_minutes: int,
    login_days_30d: int,
    purchase_preference: str,
) -> str:
    """Estimate repayment willingness from proxy behavior signals."""
    normalized_preference = purchase_preference.lower()
    score = login_days_30d + min(avg_session_minutes, 40)

    if "premium" in normalized_preference:
        score += 5
    if "discount" in normalized_preference:
        score -= 6
    if "value" in normalized_preference:
        score -= 3

    if score >= 55:
        return "high"
    if score >= 35:
        return "medium_high"
    if score >= 22:
        return "medium"
    return "low"


def _to_product_sensitivity(purchase_preference: str) -> str:
    """Map preference text to a product sensitivity level."""
    normalized_preference = purchase_preference.lower()
    if "discount" in normalized_preference or "value" in normalized_preference:
        return "high"
    if "premium" in normalized_preference:
        return "medium_high"
    return "medium"


def _to_churn_risk(
    avg_session_minutes: int,
    login_days_30d: int,
    engagement_level: str,
) -> str:
    """Estimate churn risk from engagement depth and consistency."""
    if login_days_30d <= 8 or avg_session_minutes <= 12:
        return "high"
    if engagement_level == "light" or login_days_30d <= 15:
        return "medium"
    return "low"


def _to_value_signal(
    avg_session_minutes: int,
    login_days_30d: int,
    purchase_preference: str,
) -> str:
    """Estimate commercial value signal from engagement and preference."""
    normalized_preference = purchase_preference.lower()
    score = login_days_30d * 2 + min(avg_session_minutes, 30)
    if "premium" in normalized_preference:
        score += 8

    if score >= 65:
        return "high"
    if score >= 38:
        return "medium_high"
    if score >= 22:
        return "medium"
    return "low"


def _to_behavior_risk_signals(
    avg_session_minutes: int,
    login_days_30d: int,
    purchase_preference: str,
) -> list[str]:
    """Return compact behavior risk tags suitable for runtime evidence."""
    risk_signals: list[str] = []
    normalized_preference = purchase_preference.lower()

    if login_days_30d < 10:
        risk_signals.append("low_login_consistency")
    if avg_session_minutes < 15:
        risk_signals.append("shallow_sessions")
    if avg_session_minutes >= 45 and login_days_30d >= 24:
        risk_signals.append("high_cash_loan_engagement_proxy")
    if "discount" in normalized_preference or "value" in normalized_preference:
        risk_signals.append("price_sensitive_behavior")
    if not risk_signals:
        risk_signals.append("no_strong_behavior_risk_from_current_sample")

    return risk_signals


def _build_contact_preference(
    purchase_preference: str,
    login_days_30d: int,
) -> dict[str, str]:
    """Return a lightweight Mexico-market contact preference suggestion."""
    normalized_preference = purchase_preference.lower()
    best_time = "19:00-21:00" if login_days_30d >= 15 else "12:00-14:00"
    if "premium" in normalized_preference:
        best_time = "18:00-20:00"
    return {
        "best_channel": "WhatsApp",
        "best_time": best_time,
        "confidence": "low",
        "reason": (
            "Mexico-market default prioritizes WhatsApp when direct event-channel data is unavailable."
        ),
    }
