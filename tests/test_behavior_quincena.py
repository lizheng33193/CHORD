"""Tests for Quincena pay-cycle alignment analysis (Mexico market)."""

from __future__ import annotations

import pytest

from app.runtime_skills.behavior_profile.decision_engine import (
    BehaviorDecisionEngine,
)
from app.runtime_skills.behavior_profile.feature_builder import (
    BehaviorFeatureBuilder,
)


@pytest.fixture
def builder() -> BehaviorFeatureBuilder:
    return BehaviorFeatureBuilder()


class TestAnalyzeQuincenaPattern:
    def test_all_days_in_window_returns_strong(self, builder: BehaviorFeatureBuilder) -> None:
        assert builder._analyze_quincena_pattern([16, 1, 17, 2]) == "strong"

    def test_partial_match_returns_moderate(self, builder: BehaviorFeatureBuilder) -> None:
        # 16, 1 in window; 10, 22 outside -> ratio = 0.5
        assert builder._analyze_quincena_pattern([16, 10, 1, 22]) == "moderate"

    def test_no_match_returns_none(self, builder: BehaviorFeatureBuilder) -> None:
        # 5, 10, 22, 8 all outside [1-3, 15-18, 28-31]
        assert builder._analyze_quincena_pattern([5, 10, 22, 8]) == "none"

    def test_empty_returns_unknown(self, builder: BehaviorFeatureBuilder) -> None:
        assert builder._analyze_quincena_pattern([]) == "unknown"

    def test_month_end_boundary_returns_strong(self, builder: BehaviorFeatureBuilder) -> None:
        assert builder._analyze_quincena_pattern([28, 29, 30, 31]) == "strong"

    def test_payday_anchors_return_strong(self, builder: BehaviorFeatureBuilder) -> None:
        assert builder._analyze_quincena_pattern([15, 31]) == "strong"

    def test_weak_when_single_match_in_many(self, builder: BehaviorFeatureBuilder) -> None:
        # 1 in window; 5, 10, 22 outside -> ratio = 0.25 -> weak
        assert builder._analyze_quincena_pattern([1, 5, 10, 22]) == "weak"


class TestRepaymentWillingnessReasoning:
    @pytest.fixture
    def engine(self) -> BehaviorDecisionEngine:
        return BehaviorDecisionEngine()

    def test_strong_alignment_appends_quincena_reasoning(
        self, engine: BehaviorDecisionEngine
    ) -> None:
        summary_features = {
            "repayment_willingness_level": "medium",
            "quincena_alignment": "strong",
        }
        result = engine._build_repayment_willingness(summary_features, prepared={})
        assert "Quincena" in result["reasoning"]
        assert "高度吻合" in result["reasoning"]

    def test_moderate_alignment_appends_partial_reasoning(
        self, engine: BehaviorDecisionEngine
    ) -> None:
        summary_features = {
            "repayment_willingness_level": "medium",
            "quincena_alignment": "moderate",
        }
        result = engine._build_repayment_willingness(summary_features, prepared={})
        assert "Quincena" in result["reasoning"]
        assert "部分" in result["reasoning"]

    def test_none_alignment_does_not_mention_quincena(
        self, engine: BehaviorDecisionEngine
    ) -> None:
        summary_features = {
            "repayment_willingness_level": "medium",
            "quincena_alignment": "none",
        }
        result = engine._build_repayment_willingness(summary_features, prepared={})
        assert "Quincena" not in result["reasoning"]

    def test_custom_pay_window_parameter(
        self, builder: BehaviorFeatureBuilder
    ) -> None:
        """Thailand-style month-end only payday: custom window = {28,29,30,31,1}."""
        thai_window = frozenset({28, 29, 30, 31, 1})
        result = builder._analyze_quincena_pattern([29, 30, 1], pay_window=thai_window)
        assert result == "strong"

    def test_custom_pay_window_no_match(
        self, builder: BehaviorFeatureBuilder
    ) -> None:
        """Custom window should reject days not in window."""
        narrow_window = frozenset({1, 2, 15, 16})
        result = builder._analyze_quincena_pattern([5, 10, 22], pay_window=narrow_window)
        assert result == "none"
