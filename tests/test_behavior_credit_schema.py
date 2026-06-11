"""Unit tests for typed sub-models in Behavior/Credit schemas."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.schemas.behavior_profile import BehaviorProfileStructuredResult
from app.schemas.credit_profile import CreditProfileStructuredResult
from app.runtime_skills.behavior_profile.assembler import BehaviorPageAssembler
from app.runtime_skills.credit_profile.assembler import CreditPageAssembler


# ============================================
# A. Default construction (2 tests)
# ============================================


def test_behavior_schema_default_construction():
    """Behavior schema constructs with default sub-models and top-level level fields."""
    r = BehaviorProfileStructuredResult(uid="u1")
    assert r.status == "ok"
    assert r.engagement_level == "unknown"
    assert r.repayment_willingness_level == "unknown"
    assert r.product_sensitivity_level == "unknown"
    assert r.churn_risk_level == "unknown"
    # Sub-models default-construct
    assert r.repayment_willingness.level == "unknown"
    assert r.product_sensitivity.level == "unknown"
    assert r.churn_risk.level == "unknown"
    assert r.contact_preference.best_channel == ""


def test_credit_schema_default_construction():
    """Credit schema constructs with default sub-models and top-level level fields."""
    r = CreditProfileStructuredResult(uid="u1")
    assert r.status == "ok"
    assert r.risk_level == "unknown"
    assert r.financial_maturity_level == "unknown"
    assert r.debt_pressure_level == "unknown"
    assert r.credit_stability_level == "unknown"
    assert r.borrowing_urgency_level == "unknown"
    # Sub-models default-construct
    assert r.financial_maturity.level == "unknown"
    assert r.debt_pressure.level == "unknown"
    assert r.credit_stability.level == "unknown"
    assert r.borrowing_urgency.level == "unknown"


# ============================================
# B. Sub-models from dict (2 tests)
# ============================================


def test_behavior_submodels_pydantic_coercion():
    """Pydantic auto-coerces dict -> RepaymentWillingness, ProductSensitivity, etc."""
    r = BehaviorProfileStructuredResult(
        uid="u1",
        repayment_willingness={"level": "high", "reasoning": "good history"},
        product_sensitivity={"level": "medium", "confidence": 0.85},
        churn_risk={"level": "low", "retention_signal_score": 0.9},
        contact_preference={"best_channel": "WhatsApp", "frequency_preference": "weekly"},
    )
    assert r.repayment_willingness.level == "high"
    assert r.repayment_willingness.reasoning == "good history"
    assert r.product_sensitivity.level == "medium"
    assert r.product_sensitivity.confidence == 0.85
    assert r.churn_risk.level == "low"
    assert r.churn_risk.retention_signal_score == 0.9
    assert r.contact_preference.best_channel == "WhatsApp"


def test_credit_submodels_pydantic_coercion():
    """Pydantic auto-coerces dict -> FinancialMaturity, DebtPressure, etc."""
    r = CreditProfileStructuredResult(
        uid="u1",
        financial_maturity={"level": "high", "financial_history_years": 5},
        debt_pressure={"level": "low", "debt_to_income_ratio": 0.2},
        credit_stability={"level": "stable", "inquiry_frequency": 1},
        borrowing_urgency={"level": "medium", "confidence": 0.8},
    )
    assert r.financial_maturity.level == "high"
    assert r.financial_maturity.financial_history_years == 5
    assert r.debt_pressure.level == "low"
    assert r.debt_pressure.debt_to_income_ratio == 0.2
    assert r.credit_stability.level == "stable"
    assert r.credit_stability.inquiry_frequency == 1
    assert r.borrowing_urgency.level == "medium"
    assert r.borrowing_urgency.confidence == 0.8


# ============================================
# C. Top-level + metrics co-existence (1 test)
# ============================================


def test_behavior_top_level_and_metrics_independent():
    """Top-level level field is independent of metrics value (assembler fills both)."""
    r = BehaviorProfileStructuredResult(
        uid="u1",
        repayment_willingness_level="high",
        metrics={"repayment_willingness_level": "high", "extra_metric": 42},
    )
    assert r.repayment_willingness_level == "high"
    assert r.metrics["repayment_willingness_level"] == "high"
    assert r.metrics["extra_metric"] == 42


# ============================================
# D. Assembler backfill (2 tests)
# ============================================


def test_behavior_assembler_backfills_top_level_and_submodels():
    """B1 assembler should mirror metrics levels into top-level fields and
    construct sub-models from decision_result dict blocks."""
    decision_result = {
        "uid": "u1",
        "country_code": "mx",
        "decision_status": "ok",
        "summary_seed": "test",
        "evidence_seed": {"contact_preference": {"best_channel": "WhatsApp"}},
        "engagement_profile": {"level": "balanced"},
        "repayment_willingness": {"level": "high", "repayment_event_count": 2},
        "product_sensitivity": {"level": "medium", "pricing_event_count": 1},
        "churn_risk": {"level": "low"},
        "contact_preference": {"best_channel": "WhatsApp", "best_time": "evening"},
        "behavior_signal_score": 80,
        "metrics": {
            "repayment_willingness_level": "high",
            "product_sensitivity_level": "medium",
            "churn_risk_level": "low",
        },
        "tags_rule": ["t1"],
        "llm_fallback_profile": {},
        "errors": [],
    }
    mock_client = MagicMock()
    assembler = BehaviorPageAssembler(model_client=mock_client)
    out = assembler.build_fallback_structured(
        uid="u1",
        _raw_data={},
        _feature_bundle={},
        decision_result=decision_result,
    )
    assert out["repayment_willingness_level"] == "high"
    assert out["product_sensitivity_level"] == "medium"
    assert out["churn_risk_level"] == "low"
    assert out["repayment_willingness"]["level"] == "high"
    assert out["contact_preference"]["best_channel"] == "WhatsApp"
    # metrics retained intact (DEPRECATED but compatible).
    assert out["metrics"]["repayment_willingness_level"] == "high"


def test_credit_assembler_backfills_top_level_and_submodels():
    """B2 assembler should mirror metrics levels into top-level fields and
    construct sub-models from decision_result dict blocks."""
    decision_result = {
        "uid": "u1",
        "country_code": "mx",
        "decision_status": "ok",
        "summary_seed": "test",
        "evidence_seed": {},
        "financial_maturity": {"level": "medium", "credit_history_years": 3.0},
        "debt_pressure": {"level": "medium", "total_debt_mxn": 12345},
        "credit_stability": {"level": "medium_high", "grade": "B"},
        "borrowing_urgency": {"level": "high", "inquiries_3m": 4},
        "credit_signal_score": 75,
        "metrics": {
            "risk_level": "medium",
            "financial_maturity_level": "medium",
            "debt_pressure_level": "medium",
            "credit_stability_level": "medium_high",
            "borrowing_urgency_level": "high",
        },
        "tags_rule": [],
        "llm_fallback_profile": {},
        "errors": [],
    }
    mock_client = MagicMock()
    assembler = CreditPageAssembler(model_client=mock_client)
    out = assembler.build_fallback_structured(
        uid="u1",
        _raw_data={},
        _feature_bundle={},
        decision_result=decision_result,
    )
    assert out["risk_level"] == "medium"
    assert out["credit_stability_level"] == "medium_high"
    assert out["borrowing_urgency_level"] == "high"
    assert out["credit_stability"]["level"] == "medium_high"
    assert out["debt_pressure"]["total_debt_mxn"] == 12345
    assert out["metrics"]["credit_stability_level"] == "medium_high"
