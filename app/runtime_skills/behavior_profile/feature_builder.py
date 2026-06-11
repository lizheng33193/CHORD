"""Feature builder layer for the Behavior profile pipeline."""

from __future__ import annotations

from app.runtime_skills.behavior_profile.contracts import (
    BehaviorFeatureBundle,
    BehaviorRawData,
    BehaviorRunContext,
)


class BehaviorFeatureBuilder:
    """Build deterministic Behavior features from prepared repository data."""

    def build(
        self,
        raw_data: BehaviorRawData,
        _context: BehaviorRunContext,
    ) -> BehaviorFeatureBundle:
        prepared = raw_data.get("prepared_record", {})
        session_summary = prepared.get("session_summary", {})
        engagement_signals = prepared.get("engagement_signals", {})
        repayment_signals = prepared.get("repayment_signals", {})
        product_signals = prepared.get("product_intent_signals", {})
        churn_signals = prepared.get("churn_signals", {})
        contact_signals = prepared.get("contact_signals", {})
        timeline_sections = prepared.get("timeline_sections", [])
        timeline_sections_raw = prepared.get("timeline_sections_raw", timeline_sections)
        timeline_sections_compact = prepared.get(
            "timeline_sections_compact",
            timeline_sections,
        )
        timeline_insights = prepared.get("timeline_insights", [])
        source_meta = prepared.get("source_meta", {})

        timeline_event_count_raw = sum(
            len(section.get("events", []))
            for section in timeline_sections_raw
            if isinstance(section, dict)
        )
        timeline_event_count_compact = sum(
            len(section.get("events", []))
            for section in timeline_sections_compact
            if isinstance(section, dict)
        )
        journey_risk_count = sum(
            int(section.get("warning_count", 0) or 0)
            for section in timeline_sections_compact
            if isinstance(section, dict)
        )
        active_days_30d = int(engagement_signals.get("active_days_30d", 0) or 0)
        avg_session_minutes = int(session_summary.get("avg_session_minutes", 0) or 0)
        recent_7d_event_count = int(session_summary.get("recent_7d_event_count", 0) or 0)
        pricing_event_count = int(product_signals.get("pricing_event_count", 0) or 0)
        apply_event_count = int(product_signals.get("apply_event_count", 0) or 0)
        repayment_event_count = int(repayment_signals.get("repayment_event_count", 0) or 0)
        warning_event_count = int(churn_signals.get("warning_event_count", 0) or 0)

        repayment_days_raw = repayment_signals.get("repayment_days", []) or []
        repayment_days: list[int] = [
            int(day)
            for day in repayment_days_raw
            if isinstance(day, (int, float)) and 1 <= int(day) <= 31
        ]
        quincena_alignment = self._analyze_quincena_pattern(repayment_days)

        active_trend_level = self._derive_active_trend_level(
            active_days_30d=active_days_30d,
            recent_7d_event_count=recent_7d_event_count,
        )
        value_signal_level = self._derive_value_signal_level(
            active_days_30d=active_days_30d,
            avg_session_minutes=avg_session_minutes,
            apply_event_count=apply_event_count,
            pricing_event_count=pricing_event_count,
        )
        contact_recommendation_level = self._derive_contact_level(contact_signals)

        source_variant = str(source_meta.get("source_variant", "unknown") or "unknown")
        event_cleaning_status = (
            "prepared_record_loaded"
            if source_variant == "prepared_json"
            else "raw_csv_normalized"
            if source_variant == "raw_behavior_csv"
            else "legacy_summary_only"
        )

        return {
            "uid": raw_data["uid"],
            "country_code": raw_data["country_code"],
            "prepared_record": prepared,
            "summary_features": {
                "engagement_score": int(engagement_signals.get("engagement_score", 0) or 0),
                "engagement_level": str(engagement_signals.get("engagement_level", "light") or "light"),
                "avg_session_minutes": avg_session_minutes,
                "login_days_30d": active_days_30d,
                "session_count": int(session_summary.get("session_count", 0) or 0),
                "repayment_willingness_level": str(
                    repayment_signals.get("repayment_willingness_level", "medium") or "medium"
                ),
                "product_sensitivity_level": str(
                    product_signals.get("product_sensitivity_level", "medium") or "medium"
                ),
                "purchase_preference": str(
                    product_signals.get("purchase_preference", "unknown") or "unknown"
                ),
                "churn_risk_level": str(churn_signals.get("churn_risk_level", "medium") or "medium"),
                "value_signal_level": value_signal_level,
                "active_trend_level": active_trend_level,
                "contact_recommendation_level": contact_recommendation_level,
                "quincena_alignment": quincena_alignment,
            },
            "timeline_features": {
                "timeline_section_count": len(timeline_sections_compact),
                "timeline_event_count": timeline_event_count_raw,
                "timeline_event_count_compact": timeline_event_count_compact,
                "journey_risk_count": journey_risk_count,
                "timeline_sections": timeline_sections,
                "timeline_sections_raw": timeline_sections_raw,
                "timeline_sections_compact": timeline_sections_compact,
                "timeline_insights": timeline_insights,
            },
            "derived_signals": {
                "event_cleaning": {
                    "status": event_cleaning_status,
                    "source_variant": source_variant,
                    "retained_groups": [
                        "profile_header",
                        "session_summary",
                        "engagement_signals",
                        "repayment_signals",
                        "product_intent_signals",
                        "churn_signals",
                        "contact_signals",
                        "timeline_sections",
                        "timeline_sections_raw",
                        "timeline_sections_compact",
                        "timeline_insights",
                    ],
                },
                "risk_signals": list(churn_signals.get("risk_signals", [])),
                "contact_preference": dict(contact_signals),
                "repayment_event_count": repayment_event_count,
                "warning_event_count": warning_event_count,
                "pricing_event_count": pricing_event_count,
                "quincena_alignment": quincena_alignment,
            },
            "feature_status": "ok",
            "errors": list(raw_data.get("errors", [])),
        }

    def _derive_active_trend_level(self, *, active_days_30d: int, recent_7d_event_count: int) -> str:
        if active_days_30d >= 18 and recent_7d_event_count >= 6:
            return "high"
        if active_days_30d >= 9 or recent_7d_event_count >= 3:
            return "medium"
        return "low"

    def _derive_value_signal_level(
        self,
        *,
        active_days_30d: int,
        avg_session_minutes: int,
        apply_event_count: int,
        pricing_event_count: int,
    ) -> str:
        score = min(100, active_days_30d * 3 + avg_session_minutes + apply_event_count * 5)
        if pricing_event_count >= 3:
            score -= 6
        if score >= 80:
            return "high"
        if score >= 55:
            return "medium_high"
        if score >= 30:
            return "medium"
        return "low"

    def _derive_contact_level(self, contact_signals: dict[str, object]) -> str:
        confidence = str(contact_signals.get("confidence", "low") or "low")
        if confidence == "medium":
            return "high"
        if confidence == "low":
            return "medium"
        return "low"

    # Quincena = double-monthly Mexican payday (15th + month-end). Window covers
    # payday + 1-3 days after, since repayment lands shortly after wages clear.
    # Default window loaded from country_packs/mx; can be overridden for other countries.
    _QUINCENA_WINDOW_DAYS = frozenset({1, 2, 3, 15, 16, 17, 18, 28, 29, 30, 31})

    def _analyze_quincena_pattern(self, repayment_days: list[int], pay_window: frozenset[int] | None = None) -> str:
        if not repayment_days:
            return "unknown"
        window = pay_window if pay_window is not None else self._QUINCENA_WINDOW_DAYS
        match_count = sum(1 for day in repayment_days if day in window)
        ratio = match_count / len(repayment_days)
        if ratio >= 0.7:
            return "strong"
        if ratio >= 0.4:
            return "moderate"
        if ratio > 0:
            return "weak"
        return "none"
