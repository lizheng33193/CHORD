"""Tests for CreditExplainer._build_llm_prompt_input token trimming."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.runtime_skills.credit_profile.explainer import CreditExplainer


def _make_explainer() -> CreditExplainer:
    mock_client = MagicMock()
    mock_client.mode = "mock"
    mock_client.model_name = "test"
    return CreditExplainer(model_client=mock_client, prompt_path=Path("/dev/null"))


class TestCreditTokenTrim:
    """CreditExplainer._build_llm_prompt_input token trimming tests."""

    def test_truncate_15_accounts_to_10(self):
        explainer = _make_explainer()
        payload = {
            "summary": {"total_accounts": 15},
            "account_details": [
                {"institution": f"Bank_{i}", "account_age_months": i * 3}
                for i in range(15)
            ],
            "delinquency": {"total_delinquent_accounts": 0},
            "inquiries": {"last_3_months": 2},
        }
        result = explainer._build_llm_prompt_input(payload)
        assert len(result["account_details"]) == 10

    def test_zero_accounts_no_error(self):
        explainer = _make_explainer()
        payload = {
            "summary": {},
            "account_details": [],
            "delinquency": {},
        }
        result = explainer._build_llm_prompt_input(payload)
        assert result["account_details"] == []

    def test_five_accounts_not_truncated(self):
        explainer = _make_explainer()
        payload = {
            "account_details": [
                {"institution": f"Bank_{i}", "account_age_months": i}
                for i in range(5)
            ],
        }
        result = explainer._build_llm_prompt_input(payload)
        assert len(result["account_details"]) == 5

    def test_raw_credit_json_removed(self):
        explainer = _make_explainer()
        payload = {
            "summary": {"total_accounts": 1},
            "account_details": [{"institution": "BBVA"}],
            "raw_credit_json": '{"very_large": "raw data that wastes tokens"}',
            "raw_report": "another large field",
        }
        result = explainer._build_llm_prompt_input(payload)
        assert "raw_credit_json" not in result
        assert "raw_report" not in result
        # Structured fields preserved
        assert "summary" in result
        assert "account_details" in result

    def test_preserves_summary_delinquency_inquiries(self):
        explainer = _make_explainer()
        payload = {
            "summary": {"total_accounts": 3, "total_outstanding_debt_mxn": 35000},
            "delinquency": {"max_delinquency_days": 30},
            "inquiries": {"last_3_months": 4, "last_6_months": 7},
            "risk_flags": ["high inquiry count"],
            "account_details": [],
        }
        result = explainer._build_llm_prompt_input(payload)
        assert result["summary"]["total_accounts"] == 3
        assert result["delinquency"]["max_delinquency_days"] == 30
        assert result["inquiries"]["last_3_months"] == 4
        assert result["risk_flags"] == ["high inquiry count"]

    def test_empty_dict_input(self):
        explainer = _make_explainer()
        result = explainer._build_llm_prompt_input({})
        assert result == {}

    def test_non_dict_input_returns_empty(self):
        explainer = _make_explainer()
        result = explainer._build_llm_prompt_input(None)  # type: ignore
        assert result == {}

    def test_does_not_mutate_original(self):
        explainer = _make_explainer()
        original = {
            "account_details": [{"institution": f"B{i}"} for i in range(15)],
            "raw_credit_json": "big",
        }
        explainer._build_llm_prompt_input(original)
        # Original should be unchanged
        assert len(original["account_details"]) == 15
        assert "raw_credit_json" in original
