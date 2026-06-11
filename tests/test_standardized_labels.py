"""Unit tests for app.services.label_builder.build_standardized_labels."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.label_builder import build_standardized_labels


# -----------------------------
# Fixtures (plain dicts mirroring AgentOutput.model_dump())
# -----------------------------


def _agent_output(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "",
        "structured_result": structured,
        "charts": [],
        "report_markdown": "",
    }


def _full_app_ok() -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "app_profile_agent",
            "uid": "u1",
            "status": "ok",
            "activity_level": "high",
            "risk_assessment": {"level": "medium"},
            "financial_maturity": {"level": "medium"},
            "consumption_profile": {"level": "high"},
        }
    )


def _full_behavior_ok() -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "behavior_profile_agent",
            "uid": "u1",
            "status": "ok",
            "engagement_level": "balanced",
            "metrics": {
                "repayment_willingness_level": "medium_high",
                "product_sensitivity_level": "high",
                "churn_risk_level": "low",
            },
            "evidence": {
                "contact_preference": {"best_channel": "WhatsApp"},
            },
        }
    )


def _full_credit_ok() -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "credit_profile_agent",
            "uid": "u1",
            "status": "ok",
            "metrics": {
                "credit_stability_level": "medium_high",
                "debt_pressure_level": "medium",
                "borrowing_urgency_level": "high",
            },
        }
    )


def _full_comprehensive_ok(segment: str = "S2") -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "comprehensive_profile_agent",
            "uid": "u1",
            "status": "ok",
            "persona": "S2 / high-activity / balanced-engagement / low-risk",
            "metrics": {
                "segment": segment,
                "confidence_level": "high",
            },
        }
    )


def _full_product_advice(segment: str = "S2") -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "product_advice_agent",
            "uid": "u1",
            "status": "ok",
            "segment": segment,
            "segment_name": "稳健经营客",
            "recommended_channel": {"primary": "Push"},
        }
    )


def _full_ops_advice(segment: str = "S2") -> dict[str, Any]:
    return _agent_output(
        {
            "agent_name": "ops_advice_agent",
            "uid": "u1",
            "status": "ok",
            "segment": segment,
            "segment_name": "稳健经营客",
            "churn_warning": {"level": "low"},
            "outreach_channel": {"primary": "WhatsApp"},
        }
    )


def _missing(reason: str = "data_missing") -> dict[str, Any]:
    return _agent_output({"status": reason, "metrics": {}})


# -----------------------------
# A. Happy path
# -----------------------------


def test_happy_path_full_17_keys():
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )

    assert set(labels.keys()) == {
        "basic_attributes",
        "risk_labels",
        "behavior_labels",
        "value_labels",
        "metadata",
    }

    assert labels["basic_attributes"] == {
        "age_band": "unknown",
        "occupation_type": "unknown",
        "banking_level": "medium",
        "geo_region": "unknown",
    }
    assert labels["risk_labels"] == {
        "multi_loan_risk": "medium",
        "credit_stability": "medium_high",
        "debt_pressure": "medium",
        "borrow_hunger": "high",
    }
    assert labels["behavior_labels"] == {
        "repayment_willingness": "medium_high",
        "credit_line_willingness": "high",
        "churn_risk": "low",
        "outreach_preference": "WhatsApp",
    }
    assert labels["value_labels"] == {
        "consumption_power": "high",
        "lifestyle": "S2 / high-activ…",
        "segment": "S2",
    }
    assert labels["metadata"] == {
        "profile_confidence": "high",
        "data_completeness": "三维完整",
    }


# -----------------------------
# B. not_available 永久 unknown
# -----------------------------


def test_not_available_always_unknown():
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["basic_attributes"]["age_band"] == "unknown"
    assert labels["basic_attributes"]["occupation_type"] == "unknown"
    assert labels["basic_attributes"]["geo_region"] == "unknown"


# -----------------------------
# C. data missing 降级
# -----------------------------


def test_credit_missing_unknowns_and_缺征信():
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_missing(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "unknown"
    assert labels["risk_labels"]["debt_pressure"] == "unknown"
    assert labels["risk_labels"]["borrow_hunger"] == "unknown"
    assert labels["metadata"]["data_completeness"] == "缺征信"


def test_only_app_ok_仅APP数据():
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_missing(),
        credit_profile=_missing(),
        comprehensive_profile=_missing(),
        product_advice=None,
        ops_advice=None,
    )
    assert labels["metadata"]["data_completeness"] == "仅APP数据"
    assert labels["behavior_labels"]["repayment_willingness"] == "unknown"
    assert labels["risk_labels"]["multi_loan_risk"] == "medium"  # app 仍可读


def test_app_missing_不完整():
    labels = build_standardized_labels(
        app_profile=_missing(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=None,
        ops_advice=None,
    )
    assert labels["metadata"]["data_completeness"] == "不完整"


# -----------------------------
# D. fallback 4 组
# -----------------------------


def test_borrow_hunger_fallback_to_borrowing_hunger_level():
    credit = _agent_output(
        {
            "status": "ok",
            "metrics": {
                "credit_stability_level": "medium",
                "debt_pressure_level": "medium",
                # 主 key 缺
                "borrowing_hunger_level": "medium_high",
            },
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["borrow_hunger"] == "medium_high"


def test_churn_risk_fallback_to_ops_advice():
    behavior = _agent_output(
        {
            "status": "ok",
            "engagement_level": "balanced",
            "metrics": {
                "repayment_willingness_level": "medium",
                "product_sensitivity_level": "medium",
                # churn_risk_level 缺
            },
            "evidence": {"contact_preference": {"best_channel": "Push"}},
        }
    )
    ops = _agent_output(
        {
            "status": "ok",
            "segment": "S4",
            "churn_warning": {"level": "high"},
            "outreach_channel": {"primary": "SMS"},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=behavior,
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=ops,
    )
    assert labels["behavior_labels"]["churn_risk"] == "high"


def test_outreach_preference_three_source_cascade():
    # 1) 主源 ops_advice 命中
    labels1 = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels1["behavior_labels"]["outreach_preference"] == "WhatsApp"

    # 2) ops 缺 → product 命中
    ops_no_channel = _agent_output(
        {"status": "ok", "segment": "S2", "churn_warning": {"level": "low"}}
    )
    labels2 = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=ops_no_channel,
    )
    assert labels2["behavior_labels"]["outreach_preference"] == "Push"

    # 3) ops + product 都缺 → behavior.evidence 命中
    product_no_channel = _agent_output(
        {"status": "ok", "segment": "S2"}
    )
    labels3 = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=product_no_channel,
        ops_advice=ops_no_channel,
    )
    assert labels3["behavior_labels"]["outreach_preference"] == "WhatsApp"


def test_segment_three_source_cascade():
    # 1) comprehensive 缺 → product 命中
    comp_no_segment = _agent_output(
        {
            "status": "ok",
            "persona": "x",
            "metrics": {"confidence_level": "medium"},
        }
    )
    labels1 = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=comp_no_segment,
        product_advice=_full_product_advice("S3"),
        ops_advice=_full_ops_advice("S6"),
    )
    assert labels1["value_labels"]["segment"] == "S3"

    # 2) comprehensive + product 都缺 → ops 命中
    product_no_segment = _agent_output({"status": "ok"})
    labels2 = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=comp_no_segment,
        product_advice=product_no_segment,
        ops_advice=_full_ops_advice("S6"),
    )
    assert labels2["value_labels"]["segment"] == "S6"


# -----------------------------
# E. bad input
# -----------------------------


def test_structured_result_not_a_dict_does_not_raise():
    bad = {"summary": "", "structured_result": "not_a_dict",
           "charts": [], "report_markdown": ""}
    labels = build_standardized_labels(
        app_profile=bad,
        behavior_profile=bad,
        credit_profile=bad,
        comprehensive_profile=bad,
        product_advice=bad,
        ops_advice=bad,
    )
    # 17 key 形状仍完整
    assert set(labels.keys()) == {
        "basic_attributes", "risk_labels", "behavior_labels",
        "value_labels", "metadata",
    }
    # 所有可读维度全 unknown
    for group in ("basic_attributes", "risk_labels", "behavior_labels", "value_labels"):
        for v in labels[group].values():
            assert v == "unknown"
    # data_completeness：app status 不存在 → 不属于"全 ok"也不属于其它有效组合 → 不完整
    assert labels["metadata"]["profile_confidence"] == "unknown"
    assert labels["metadata"]["data_completeness"] == "不完整"


def test_all_none_inputs():
    labels = build_standardized_labels(
        app_profile=None, behavior_profile=None, credit_profile=None,
        comprehensive_profile=None, product_advice=None, ops_advice=None,
    )
    assert set(labels.keys()) == {
        "basic_attributes", "risk_labels", "behavior_labels",
        "value_labels", "metadata",
    }
    for v in labels["risk_labels"].values():
        assert v == "unknown"
    assert labels["metadata"]["data_completeness"] == "不完整"


# -----------------------------
# F. schema compatibility (Phase 2 will add F1/F2; placeholders kept here)
# -----------------------------


def test_F1_user_analysis_result_accepts_standardized_labels():
    from app.schemas.final_response import AgentOutput, UserAnalysisResult

    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )

    empty = AgentOutput(summary="", structured_result={}, charts=[], report_markdown="")
    result = UserAnalysisResult(
        uid="u1",
        app_profile=empty,
        behavior_profile=empty,
        credit_profile=empty,
        comprehensive_profile=empty,
        standardized_labels=labels,
    )
    assert result.standardized_labels is not None
    assert result.standardized_labels["metadata"]["data_completeness"] == "三维完整"


def test_F2_user_analysis_result_default_none():
    from app.schemas.final_response import AgentOutput, UserAnalysisResult

    empty = AgentOutput(summary="", structured_result={}, charts=[], report_markdown="")
    result = UserAnalysisResult(
        uid="u1",
        app_profile=empty,
        behavior_profile=empty,
        credit_profile=empty,
        comprehensive_profile=empty,
    )
    assert result.standardized_labels is None


# ============================================
# G. New schema paths take precedence
# ============================================


def test_G1_new_path_wins_over_metrics_for_credit():
    """When credit.credit_stability.level (new) and metrics.credit_stability_level (old)
    both exist, new path wins."""
    credit = _agent_output(
        {
            "status": "ok",
            "credit_stability": {"level": "high"},
            "credit_stability_level": "medium",
            "metrics": {"credit_stability_level": "low"},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "high"


def test_G2_top_level_mirror_wins_when_submodel_missing():
    """When sub-model missing but top-level level field exists,
    top-level field wins over metrics."""
    credit = _agent_output(
        {
            "status": "ok",
            "credit_stability_level": "medium_high",
            "metrics": {"credit_stability_level": "low"},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "medium_high"


def test_G3_legacy_metrics_path_still_works_when_new_paths_absent():
    """When new paths missing, legacy metrics path is the fallback."""
    credit = _agent_output(
        {
            "status": "ok",
            "metrics": {"credit_stability_level": "low"},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=_full_behavior_ok(),
        credit_profile=credit,
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["risk_labels"]["credit_stability"] == "low"


def test_G4_behavior_repayment_three_path_priority():
    """Behavior repayment_willingness: sub-model > top-level > metrics."""
    behavior = _agent_output(
        {
            "status": "ok",
            "engagement_level": "balanced",
            "repayment_willingness": {"level": "high"},
            "repayment_willingness_level": "medium_high",
            "metrics": {
                "repayment_willingness_level": "low",
                "product_sensitivity_level": "medium",
                "churn_risk_level": "low",
            },
            "evidence": {"contact_preference": {"best_channel": "WhatsApp"}},
        }
    )
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=behavior,
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=_full_product_advice(),
        ops_advice=_full_ops_advice(),
    )
    assert labels["behavior_labels"]["repayment_willingness"] == "high"


def test_G5_outreach_falls_through_to_contact_preference():
    """When ops/product outreach channels missing, behavior contact_preference.best_channel
    (new top-level sub-model) is queried."""
    behavior = _agent_output(
        {
            "status": "ok",
            "engagement_level": "balanced",
            "metrics": {
                "repayment_willingness_level": "medium",
                "product_sensitivity_level": "medium",
                "churn_risk_level": "low",
            },
            "contact_preference": {"best_channel": "Push"},
            "evidence": {"contact_preference": {"best_channel": "SMS"}},
        }
    )
    ops_no_channel = _agent_output(
        {"status": "ok", "segment": "S2", "churn_warning": {"level": "low"}}
    )
    product_no_channel = _agent_output({"status": "ok", "segment": "S2"})
    labels = build_standardized_labels(
        app_profile=_full_app_ok(),
        behavior_profile=behavior,
        credit_profile=_full_credit_ok(),
        comprehensive_profile=_full_comprehensive_ok(),
        product_advice=product_no_channel,
        ops_advice=ops_no_channel,
    )
    assert labels["behavior_labels"]["outreach_preference"] == "Push"
