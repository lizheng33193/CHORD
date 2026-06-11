"""Standardized label builder.

Aggregates the 6 Skill ``structured_result`` outputs into the 17-dimension
standardized label payload defined in docs/specs/standardized-labels-design.md.

Pure dict-in / dict-out; no I/O; no LLM; never raises.
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)


# -----------------------------
# Public API
# -----------------------------


def build_standardized_labels(
    *,
    app_profile: dict[str, Any] | None,
    behavior_profile: dict[str, Any] | None,
    credit_profile: dict[str, Any] | None,
    comprehensive_profile: dict[str, Any] | None,
    product_advice: dict[str, Any] | None,
    ops_advice: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the 5-group / 17-key standardized label dict.

    Each leaf is a string. Missing or malformed inputs degrade to ``"unknown"``
    at the leaf level. A top-level uncaught exception degrades to a full
    default dict (all ``"unknown"``, ``data_completeness="unknown"``).
    """
    try:
        app_sr = _structured(app_profile)
        beh_sr = _structured(behavior_profile)
        cre_sr = _structured(credit_profile)
        com_sr = _structured(comprehensive_profile)
        prod_sr = _structured(product_advice)
        ops_sr = _structured(ops_advice)

        return {
            "basic_attributes": {
                "age_band": "unknown",
                "occupation_type": "unknown",
                "banking_level": _get_path(app_sr, ["financial_maturity", "level"]),
                "geo_region": "unknown",
            },
            "risk_labels": {
                "multi_loan_risk": _get_path(app_sr, ["risk_assessment", "level"]),
                "credit_stability": _get_priority_three_layer(
                    cre_sr, "credit_stability", "credit_stability_level", "credit_stability_level"
                ),
                "debt_pressure": _get_priority_three_layer(
                    cre_sr, "debt_pressure", "debt_pressure_level", "debt_pressure_level"
                ),
                "borrow_hunger": _first_non_empty(
                    _get_priority_three_layer(
                        cre_sr,
                        "borrowing_urgency",
                        "borrowing_urgency_level",
                        "borrowing_urgency_level",
                    ),
                    _get_path(cre_sr, ["metrics", "borrowing_hunger_level"]),
                ),
            },
            "behavior_labels": {
                "repayment_willingness": _get_priority_three_layer(
                    beh_sr,
                    "repayment_willingness",
                    "repayment_willingness_level",
                    "repayment_willingness_level",
                ),
                "credit_line_willingness": _get_priority_three_layer(
                    beh_sr,
                    "product_sensitivity",
                    "product_sensitivity_level",
                    "product_sensitivity_level",
                ),
                "churn_risk": _first_non_empty(
                    _get_priority_three_layer(
                        beh_sr, "churn_risk", "churn_risk_level", "churn_risk_level"
                    ),
                    _get_path(ops_sr, ["churn_warning", "level"]),
                ),
                "outreach_preference": _first_non_empty(
                    _get_path(ops_sr, ["outreach_channel", "primary"]),
                    _get_path(prod_sr, ["recommended_channel", "primary"]),
                    _get_path(beh_sr, ["contact_preference", "best_channel"]),
                    _get_path(beh_sr, ["evidence", "contact_preference", "best_channel"]),
                ),
            },
            "value_labels": {
                "consumption_power": _get_path(app_sr, ["consumption_profile", "level"]),
                "lifestyle": _truncate_label(_get_path(com_sr, ["persona"]), 15),
                "segment": _first_non_empty(
                    _get_path(com_sr, ["metrics", "segment"]),
                    _get_path(prod_sr, ["segment"]),
                    _get_path(ops_sr, ["segment"]),
                ),
            },
            "metadata": {
                "profile_confidence": _get_path(com_sr, ["metrics", "confidence_level"]),
                "data_completeness": _derive_data_completeness(
                    app_profile, behavior_profile, credit_profile,
                ),
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_standardized_labels failed, using defaults: %s", exc)
        return _default_labels()


# -----------------------------
# Helpers
# -----------------------------


def _structured(agent_output: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(agent_output, dict):
        return {}
    sr = agent_output.get("structured_result")
    return sr if isinstance(sr, dict) else {}


def _is_ok(agent_output: dict[str, Any] | None) -> bool:
    return _structured(agent_output).get("status") == "ok"


def _get_path(
    source: dict[str, Any],
    path: list[str],
    default: str = "unknown",
) -> str:
    cur: Any = source
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    if cur is None:
        return default
    text = str(cur).strip()
    return text if text else default


def _truncate_label(value: str, max_len: int) -> str:
    if not value or value == "unknown":
        return value
    if len(value) <= max_len:
        return value
    return value[:max_len] + "…"


def _first_non_empty(*candidates: str) -> str:
    for value in candidates:
        if value and value != "unknown":
            return value
    return "unknown"


def _get_priority_three_layer(
    source: dict[str, Any],
    sub_model_key: str,
    top_level_field: str,
    metrics_field: str,
) -> str:
    """Query with three-layer priority: sub-model.level > top-level.field > metrics.field.

    Used for credit/behavior profile fields that have been migrated to strong-typed sub-models
    while maintaining backward compatibility with legacy metrics paths.
    """
    # Layer 1: sub-model (new path)
    val = _get_path(source, [sub_model_key, "level"])
    if val != "unknown":
        return val
    # Layer 2: top-level level field (new path)
    val = _get_path(source, [top_level_field])
    if val != "unknown":
        return val
    # Layer 3: legacy metrics path (old fallback)
    return _get_path(source, ["metrics", metrics_field])


def _derive_data_completeness(
    app: dict[str, Any] | None,
    behavior: dict[str, Any] | None,
    credit: dict[str, Any] | None,
) -> str:
    app_ok = _is_ok(app)
    beh_ok = _is_ok(behavior)
    cre_ok = _is_ok(credit)
    if app_ok and beh_ok and cre_ok:
        return "三维完整"
    if app_ok and beh_ok and not cre_ok:
        return "缺征信"
    if app_ok and not beh_ok and not cre_ok:
        return "仅APP数据"
    return "不完整"


def _default_labels() -> dict[str, Any]:
    return {
        "basic_attributes": {
            "age_band": "unknown",
            "occupation_type": "unknown",
            "banking_level": "unknown",
            "geo_region": "unknown",
        },
        "risk_labels": {
            "multi_loan_risk": "unknown",
            "credit_stability": "unknown",
            "debt_pressure": "unknown",
            "borrow_hunger": "unknown",
        },
        "behavior_labels": {
            "repayment_willingness": "unknown",
            "credit_line_willingness": "unknown",
            "churn_risk": "unknown",
            "outreach_preference": "unknown",
        },
        "value_labels": {
            "consumption_power": "unknown",
            "lifestyle": "unknown",
            "segment": "unknown",
        },
        "metadata": {
            "profile_confidence": "unknown",
            "data_completeness": "unknown",
        },
    }
