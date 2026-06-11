"""Build structured chart payloads from skill results."""

from __future__ import annotations

from typing import Any


def build_app_charts(structured_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Create app profile charts."""
    metrics = structured_result.get("metrics", {})
    visuals = structured_result.get("visuals", {})
    risk_assessment = structured_result.get("risk_assessment", {})
    financial_maturity = structured_result.get("financial_maturity", {})
    consumption_profile = structured_result.get("consumption_profile", {})
    evidence = structured_result.get("evidence", {})

    category_distribution = evidence.get("localized_category_distribution") or evidence.get(
        "category_distribution", []
    )
    install_distribution = evidence.get("install_time_distribution", [])
    progress_metrics = visuals.get("progress_metrics", [])

    return [
        {
            "chart_type": "donut",
            "title": "Installed Apps Category Share",
            "series": [
                {
                    "name": "category_share",
                    "data": [
                        {
                            "label": item.get("label", "Unknown"),
                            "value": int(item.get("count", 0) or 0),
                            "share": int(item.get("share", 0) or 0),
                            "color_token": item.get("color_token", "blue"),
                        }
                        for item in category_distribution
                    ],
                }
            ],
            "meta": {
                "top_category": visuals.get("top_category", "unknown"),
                "main_preference_share": int(visuals.get("main_preference_share", 0) or 0),
                "palette": visuals.get("chart_palette", []),
            },
        },
        {
            "chart_type": "bar",
            "title": "Install Time Distribution",
            "x_axis": [item.get("bucket", "unknown") for item in install_distribution],
            "series": [
                {
                    "name": "value",
                    "data": [int(item.get("count", 0) or 0) for item in install_distribution],
                }
            ],
            "meta": {
                "application_time": metrics.get("application_time", ""),
            },
        },
        {
            "chart_type": "progress",
            "title": "Risk / Maturity / Consumption Signals",
            "series": [
                {
                    "name": "progress_metrics",
                    "data": progress_metrics,
                }
            ],
            "meta": {
                "levels": {
                    "multi_loan_risk": risk_assessment.get("level", "unknown"),
                    "consumption_ability": consumption_profile.get("level", "unknown"),
                    "financial_maturity": financial_maturity.get("level", "unknown"),
                }
            },
        },
    ]


def build_behavior_charts(structured_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Create behavior profile charts."""
    metrics = structured_result.get("metrics", {})
    evidence = structured_result.get("evidence", {}) if isinstance(structured_result.get("evidence"), dict) else {}
    timeline_sections = evidence.get("timeline_sections", []) if isinstance(evidence, dict) else []
    timeline_insights = evidence.get("timeline_insights", []) if isinstance(evidence, dict) else []
    contact_preference = evidence.get("contact_preference", {}) if isinstance(evidence, dict) else {}
    repayment_score_map = {"high": 90, "medium_high": 72, "medium": 52, "low": 28}
    sensitivity_score_map = {"high": 85, "medium_high": 68, "medium": 50, "low": 30}
    churn_score_map = {"low": 25, "medium": 55, "high": 85}
    repayment_level = str(metrics.get("repayment_willingness_level", "medium"))
    sensitivity_level = str(metrics.get("product_sensitivity_level", "medium"))
    churn_level = str(metrics.get("churn_risk_level", "medium"))
    return [
        {
            "chart_type": "bar",
            "title": "Behavior Metrics",
            "x_axis": ["avg_session_minutes", "login_days_30d", "engagement_score"],
            "series": [
                {
                    "name": "value",
                    "data": [
                        int(metrics.get("avg_session_minutes", 0) or 0),
                        int(metrics.get("login_days_30d", 0) or 0),
                        int(metrics.get("engagement_score", 0) or 0),
                    ],
                }
            ],
            "meta": {},
        },
        {
            "chart_type": "radar",
            "title": "Behavior Proxy Signals",
            "indicators": [
                "repayment_willingness",
                "product_sensitivity",
                "churn_risk",
            ],
            "series": [
                {
                    "name": "behavior_proxy",
                    "data": [
                        repayment_score_map.get(repayment_level, 50),
                        sensitivity_score_map.get(sensitivity_level, 50),
                        churn_score_map.get(churn_level, 55),
                    ],
                }
            ],
            "meta": {
                "levels": {
                    "repayment_willingness": repayment_level,
                    "product_sensitivity": sensitivity_level,
                    "churn_risk": churn_level,
                }
            },
        },
        {
            "chart_type": "bar",
            "title": "Journey Sections Overview",
            "x_axis": [
                str(section.get("title", f"section_{index + 1}"))
                for index, section in enumerate(timeline_sections[:6])
                if isinstance(section, dict)
            ],
            "series": [
                {
                    "name": "events",
                    "data": [
                        len(section.get("events", []))
                        for section in timeline_sections[:6]
                        if isinstance(section, dict)
                    ],
                },
                {
                    "name": "warnings",
                    "data": [
                        int(section.get("warning_count", 0) or 0)
                        for section in timeline_sections[:6]
                        if isinstance(section, dict)
                    ],
                },
            ],
            "meta": {
                "timeline_insights": timeline_insights[:4],
            },
        },
        {
            "chart_type": "table",
            "title": "Contact Recommendation",
            "series": [
                {
                    "name": "contact_preference",
                    "data": [
                        {
                            "best_channel": str(contact_preference.get("best_channel", "WhatsApp") or "WhatsApp"),
                            "best_time": str(contact_preference.get("best_time", "19:00-21:00") or "19:00-21:00"),
                            "confidence": str(contact_preference.get("confidence", "low") or "low"),
                            "reason": str(contact_preference.get("reason", "") or ""),
                        }
                    ],
                }
            ],
            "meta": {},
        },
    ]


def build_credit_charts(structured_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Create credit profile charts."""
    metrics = structured_result.get("metrics", {})
    evidence = structured_result.get("evidence", {})
    risk_level = str(metrics.get("risk_level", "unknown"))
    debt_pressure = str(metrics.get("debt_pressure_level", "unknown"))
    credit_stability = str(metrics.get("credit_stability_level", "unknown"))
    borrowing_hunger = str(metrics.get("borrowing_hunger_level", "unknown"))
    radar_scores = metrics.get("radar_scores", {}) if isinstance(metrics.get("radar_scores"), dict) else {}
    repayment_amount_timeline = metrics.get("repayment_amount_timeline", [])
    repayment_notes = metrics.get("repayment_amount_notes", [])
    account_details = evidence.get("account_details", []) if isinstance(evidence, dict) else []
    score_value = int(metrics.get("score_value", 0) or 0)

    risk_score_map = {"low": 1, "medium": 2, "high": 3}
    debt_score_map = {"low": 30, "medium_low": 45, "medium": 60, "medium_high": 75, "high": 90}
    stability_score_map = {"low": 25, "medium": 50, "medium_high": 70, "high": 85}
    hunger_score_map = {"low": 25, "medium_low": 45, "medium": 60, "high": 80}

    return [
        {
            "chart_type": "gauge",
            "title": "Credit Risk Level",
            "series": [{"name": "risk", "data": [risk_score_map.get(risk_level, 0)]}],
            "meta": {"labels": {"1": "low", "2": "medium", "3": "high"}},
        },
        {
            "chart_type": "gauge",
            "title": "Buro Score Gauge",
            "series": [{"name": "score_value", "data": [score_value]}],
            "meta": {"min": 0, "max": 900, "score_model": str(metrics.get("score_model", "unknown"))},
        },
        {
            "chart_type": "radar",
            "title": "Credit Proxy Signals",
            "indicators": ["debt_pressure", "credit_stability", "borrowing_hunger"],
            "series": [
                {
                    "name": "credit_proxy",
                    "data": [
                        debt_score_map.get(debt_pressure, 35),
                        stability_score_map.get(credit_stability, 30),
                        hunger_score_map.get(borrowing_hunger, 35),
                    ],
                }
            ],
            "meta": {
                "levels": {
                    "debt_pressure": debt_pressure,
                    "credit_stability": credit_stability,
                    "borrowing_hunger": borrowing_hunger,
                    "buro_cleaning_status": str(metrics.get("buro_cleaning_status", "unknown")),
                }
            },
        },
        {
            "chart_type": "radar",
            "title": "Credit 4D Evaluation",
            "indicators": [
                "financial_maturity",
                "credit_stability",
                "repayment_pressure_index",
                "borrowing_urgency",
            ],
            "series": [
                {
                    "name": "credit_4d",
                    "data": [
                        int(radar_scores.get("financial_maturity", 0) or 0),
                        int(radar_scores.get("credit_stability", 0) or 0),
                        int(radar_scores.get("repayment_pressure_index", 0) or 0),
                        int(radar_scores.get("borrowing_urgency", 0) or 0),
                    ],
                }
            ],
            "meta": {"radar_scores": radar_scores},
        },
        {
            "chart_type": "bar",
            "title": "Repayment Amount Timeline",
            "x_axis": [f"M{index + 1}" for index in range(len(repayment_amount_timeline))],
            "series": [
                {
                    "name": "repayment_amount_mxn",
                    "data": [int(value or 0) for value in repayment_amount_timeline],
                }
            ],
            "meta": {
                "notes": repayment_notes,
            },
        },
        {
            "chart_type": "table",
            "title": "Active Accounts Snapshot",
            "series": [
                {
                    "name": "accounts",
                    "data": [
                        {
                            "institution": item.get("institution", ""),
                            "type": item.get("type", ""),
                            "credit_limit_mxn": int(item.get("credit_limit_mxn", 0) or 0),
                            "current_balance_mxn": int(item.get("current_balance_mxn", 0) or 0),
                            "utilization_rate": item.get("utilization_rate", ""),
                        }
                        for item in account_details[:6]
                        if isinstance(item, dict)
                    ],
                }
            ],
            "meta": {"account_count": len(account_details)},
        },
    ]


def build_comprehensive_charts(structured_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Create comprehensive charts from merged metrics."""
    metrics = structured_result.get("metrics", {})
    scores = metrics.get("dimension_scores", {})
    segment = str(metrics.get("segment", "unknown"))
    conflict_count = int(metrics.get("conflict_count", 0) or 0)
    value_signal = str(metrics.get("value_signal_level", "unknown"))
    risk_level = str(metrics.get("risk_level", "unknown"))

    value_score_map = {"low": 30, "medium": 60, "high": 85}
    risk_score_map = {"low": 80, "medium": 55, "high": 25, "unknown": 40}

    return [
        {
            "chart_type": "radar",
            "title": "Comprehensive Profile Overview",
            "indicators": ["app", "behavior", "credit"],
            "series": [
                {
                    "name": "profile_strength",
                    "data": [
                        int(scores.get("app", 0) or 0),
                        int(scores.get("behavior", 0) or 0),
                        int(scores.get("credit", 0) or 0),
                    ],
                }
            ],
            "meta": {
                "segment": segment,
                "conflict_count": conflict_count,
            },
        },
        {
            "chart_type": "bar",
            "title": "Segment Risk And Value",
            "x_axis": ["value_signal", "risk_buffer", "conflict_count"],
            "series": [
                {
                    "name": "value_and_risk",
                    "data": [
                        value_score_map.get(value_signal, 40),
                        risk_score_map.get(risk_level, 40),
                        conflict_count,
                    ],
                }
            ],
            "meta": {
                "segment": segment,
                "risk_level": risk_level,
                "value_signal_level": value_signal,
            },
        },
    ]
