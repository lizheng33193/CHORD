"""Feature builder layer for the Credit profile pipeline."""

from __future__ import annotations

from app.runtime_skills.credit_profile.contracts import (
    CreditFeatureBundle,
    CreditRawData,
    CreditRunContext,
)


class CreditFeatureBuilder:
    """Build deterministic Credit features from prepared repository data."""

    def build(
        self,
        raw_data: CreditRawData,
        context: CreditRunContext,
    ) -> CreditFeatureBundle:
        """v6.1 路径 Q：按 profile_mode 分支。"""
        if context.get("profile_mode") == "risk_features":
            return self._build_risk_features(raw_data, context)
        return self._build_buro_features(raw_data, context)

    def _build_buro_features(
        self,
        raw_data: CreditRawData,
        _context: CreditRunContext,
    ) -> CreditFeatureBundle:
        prepared = raw_data.get("prepared_record", {})
        summary = prepared.get("summary", {})
        delinquency = prepared.get("delinquency", {})
        inquiries = prepared.get("inquiries", {})
        score = prepared.get("score", {})
        account_details = prepared.get("account_details", [])
        source_meta = prepared.get("source_meta", {})

        oldest_account_age_months = int(summary.get("oldest_account_age_months", 0) or 0)
        total_outstanding_debt_mxn = int(summary.get("total_outstanding_debt_mxn", 0) or 0)
        monthly_payment_estimate_mxn = int(summary.get("monthly_payment_estimate_mxn", 0) or 0)
        avg_credit_utilization_pct = int(summary.get("avg_credit_utilization_pct", 0) or 0)
        max_credit_utilization_pct = int(summary.get("max_credit_utilization_pct", 0) or 0)
        total_accounts = int(summary.get("total_accounts", 0) or 0)
        active_accounts = int(summary.get("active_accounts", 0) or 0)

        max_delinquency_days = int(delinquency.get("max_delinquency_days", 0) or 0)
        total_delinquent_accounts = int(delinquency.get("total_delinquent_accounts", 0) or 0)
        inquiries_3m = int(inquiries.get("last_3_months", 0) or 0)
        inquiries_6m = int(inquiries.get("last_6_months", 0) or 0)
        inquiries_12m = int(inquiries.get("last_12_months", 0) or 0)

        credit_score_band = str(score.get("credit_score_band", "unknown") or "unknown").strip().upper()
        repayment_status = str(score.get("repayment_status", "unknown") or "unknown").strip().lower()
        score_value = int(score.get("score_value", 0) or 0)

        has_bank_credit_card = any(
            "bank" in str(item.get("institution", "")).lower()
            or "bbva" in str(item.get("institution", "")).lower()
            or "banorte" in str(item.get("institution", "")).lower()
            or "santander" in str(item.get("institution", "")).lower()
            for item in account_details
            if isinstance(item, dict)
        )
        utilization_values = [
            self._parse_percent(item.get("utilization_rate", ""))
            for item in account_details
            if isinstance(item, dict)
        ]
        high_utilization_accounts = sum(1 for value in utilization_values if value >= 80)
        revolving_accounts = sum(
            1
            for item in account_details
            if isinstance(item, dict)
            and str(item.get("type", "")).upper() in {"CC", "TC", "TDC"}
        )

        debt_pressure_level = self._derive_debt_pressure_level(
            total_debt=total_outstanding_debt_mxn,
            monthly_payment=monthly_payment_estimate_mxn,
            avg_utilization=avg_credit_utilization_pct,
        )
        credit_stability_grade = self._derive_credit_stability_grade(
            max_dpd=max_delinquency_days,
            total_delinquent=total_delinquent_accounts,
        )
        credit_stability_level = self._map_credit_stability_level(credit_stability_grade)
        borrowing_urgency_level = self._derive_borrowing_urgency_level(
            inquiries_3m=inquiries_3m,
            inquiries_6m=inquiries_6m,
        )
        financial_maturity_level = self._derive_financial_maturity_level(
            oldest_account_age_months=oldest_account_age_months,
            total_accounts=total_accounts,
            has_bank_credit_card=has_bank_credit_card,
        )
        risk_level = self._derive_credit_risk_level(
            debt_pressure_level=debt_pressure_level,
            credit_stability_grade=credit_stability_grade,
            borrowing_urgency_level=borrowing_urgency_level,
        )
        radar_scores = self._build_credit_radar_scores(
            oldest_account_age_months=oldest_account_age_months,
            avg_credit_utilization_pct=avg_credit_utilization_pct,
            debt_pressure_level=debt_pressure_level,
            credit_stability_level=credit_stability_level,
            borrowing_urgency_level=borrowing_urgency_level,
        )

        source_variant = str(source_meta.get("source_variant", "unknown") or "unknown")
        buro_cleaning_status = (
            "prepared_record_loaded"
            if source_variant == "prepared_json"
            else "raw_csv_normalized"
            if source_variant == "raw_credit_csv"
            else "legacy_summary_only"
        )

        return {
            "uid": raw_data["uid"],
            "country_code": raw_data["country_code"],
            "prepared_record": prepared,
            "summary_features": {
                "credit_score_band": credit_score_band,
                "repayment_status": repayment_status,
                "risk_level": risk_level,
                "score_value": score_value,
                "oldest_account_age_months": oldest_account_age_months,
                "total_outstanding_debt_mxn": total_outstanding_debt_mxn,
                "monthly_payment_estimate_mxn": monthly_payment_estimate_mxn,
                "avg_credit_utilization_pct": avg_credit_utilization_pct,
                "max_credit_utilization_pct": max_credit_utilization_pct,
                "inquiries_last_3_months": inquiries_3m,
                "inquiries_last_6_months": inquiries_6m,
                "inquiries_last_12_months": inquiries_12m,
                "financial_maturity_level": financial_maturity_level,
                "debt_pressure_level": debt_pressure_level,
                "credit_stability_level": credit_stability_level,
                "credit_stability_grade": credit_stability_grade,
                "borrowing_urgency_level": borrowing_urgency_level,
                "borrowing_hunger_level": borrowing_urgency_level,
            },
            "account_features": {
                "total_accounts": total_accounts,
                "active_accounts": active_accounts,
                "revolving_accounts": revolving_accounts,
                "high_utilization_accounts": high_utilization_accounts,
                "has_bank_credit_card": has_bank_credit_card,
                "account_details_count": len(account_details),
            },
            "derived_signals": {
                "buro_cleaning": {
                    "status": buro_cleaning_status,
                    "source_variant": source_variant,
                    "retained_groups": [
                        "profile_header",
                        "summary",
                        "delinquency",
                        "inquiries",
                        "account_details",
                        "score",
                        "repayment_timeline",
                        "repayment_amount_timeline",
                    ],
                    "note": "Credit runtime consumes a prepared Buro contract instead of direct page-driven parsing.",
                },
                "radar_scores": radar_scores,
                "trend_flags": {
                    "thin_credit_file": total_accounts <= 1 or oldest_account_age_months < 6,
                    "high_utilization": avg_credit_utilization_pct >= 80,
                    "recent_inquiry_heat": inquiries_3m >= 3 or inquiries_6m >= 5,
                    "delinquency_present": total_delinquent_accounts > 0,
                },
            },
            "feature_status": "ok",
            "errors": list(raw_data.get("errors", [])),
        }

    def _parse_percent(self, value: object) -> float:
        text = str(value or "").replace("%", "").strip()
        try:
            return float(text)
        except Exception:  # pylint: disable=broad-except
            return 0.0

    def _derive_debt_pressure_level(self, *, total_debt: int, monthly_payment: int, avg_utilization: int) -> str:
        score = 0
        if total_debt >= 50000:
            score += 2
        elif total_debt >= 25000:
            score += 1
        if monthly_payment >= 6000:
            score += 2
        elif monthly_payment >= 3000:
            score += 1
        if avg_utilization >= 80:
            score += 2
        elif avg_utilization >= 60:
            score += 1
        if score >= 5:
            return "high"
        if score >= 3:
            return "medium_high"
        if score >= 1:
            return "medium"
        return "low"

    def _derive_credit_stability_grade(self, *, max_dpd: int, total_delinquent: int) -> str:
        if max_dpd >= 90:
            return "bad"
        if max_dpd >= 60:
            return "poor"
        if max_dpd >= 30:
            return "fair"
        if total_delinquent >= 1:
            return "good"
        return "excellent"

    def _map_credit_stability_level(self, grade: str) -> str:
        return {
            "excellent": "high",
            "good": "medium_high",
            "fair": "medium",
            "poor": "low",
            "bad": "low",
        }.get(grade, "medium")

    def _derive_borrowing_urgency_level(self, *, inquiries_3m: int, inquiries_6m: int) -> str:
        if inquiries_3m >= 3 or inquiries_6m >= 5:
            return "high"
        if inquiries_3m >= 1 or inquiries_6m >= 3:
            return "medium"
        return "low"

    def _derive_financial_maturity_level(
        self,
        *,
        oldest_account_age_months: int,
        total_accounts: int,
        has_bank_credit_card: bool,
    ) -> str:
        if oldest_account_age_months >= 36 and has_bank_credit_card and total_accounts >= 2:
            return "mature"
        if oldest_account_age_months >= 12 or has_bank_credit_card:
            return "growing"
        return "thin_file"

    def _derive_credit_risk_level(
        self,
        *,
        debt_pressure_level: str,
        credit_stability_grade: str,
        borrowing_urgency_level: str,
    ) -> str:
        if debt_pressure_level in {"high", "medium_high"} and credit_stability_grade in {"bad", "poor"}:
            return "high"
        if borrowing_urgency_level == "high" and credit_stability_grade in {"fair", "poor", "bad"}:
            return "high"
        if debt_pressure_level in {"medium_high", "medium"} or borrowing_urgency_level == "high":
            return "medium"
        return "low"

    def _build_credit_radar_scores(
        self,
        *,
        oldest_account_age_months: int,
        avg_credit_utilization_pct: int,
        debt_pressure_level: str,
        credit_stability_level: str,
        borrowing_urgency_level: str,
    ) -> dict[str, int]:
        maturity = min(100, 20 + oldest_account_age_months)
        pressure_map = {"low": 25, "medium": 55, "medium_high": 75, "high": 90}
        stability_map = {"low": 30, "medium": 60, "medium_high": 78, "high": 90}
        urgency_map = {"low": 25, "medium": 55, "high": 82}
        history_depth = min(100, 18 + oldest_account_age_months)
        cash_tightness = min(95, int(avg_credit_utilization_pct * 0.9) + 12)
        return {
            "financial_maturity": maturity,
            "repayment_pressure_index": pressure_map.get(debt_pressure_level, 50),
            "credit_stability": stability_map.get(credit_stability_level, 50),
            "borrowing_urgency": urgency_map.get(borrowing_urgency_level, 50),
            "credit_history_depth": history_depth,
            "cash_tightness": max(15, cash_tightness),
        }

    def _build_risk_features(
        self,
        raw_data: CreditRawData,
        _context: CreditRunContext,
    ) -> CreditFeatureBundle:
        """v6.1 路径 Q：TH 风控特征聚合解读 V1 极简版。"""
        risk_record = raw_data.get("risk_features_record")
        feature_status = "ok" if risk_record else "missing"
        return {
            "uid": raw_data["uid"],
            "country_code": raw_data["country_code"],
            "prepared_record": raw_data.get("prepared_record", {}),
            "summary_features": {},
            "account_features": {},
            "derived_signals": {
                "risk_features_record": risk_record or {},
                "profile_mode": "risk_features",
            },
            "feature_status": feature_status,
            "errors": list(raw_data.get("errors", [])),
        }
