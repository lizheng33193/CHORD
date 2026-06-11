"""Rule-based decision derivation for the comprehensive pipeline.

规则函数体（_assign_segment / _build_conflict_explanations / _derive_value_signal /
_derive_confidence_level / _build_persona / _build_tags）原样搬自
app/runtime_skills/comprehensive_agent.py，输入仍为上游 structured_result dict。
"""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveDecisionEngine:
    """Rules: segment / risk / value / confidence / conflicts / persona_seed / tags."""

    def decide(
        self,
        feature_bundle: ComprehensiveFeatureBundle,
        upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveDecisionResult:
        app_structured = self._structured(upstream["app_result"])
        behavior_structured = self._structured(upstream["behavior_result"])
        credit_structured = self._structured(upstream["credit_result"])

        credit_metrics = (
            credit_structured.get("metrics", {})
            if isinstance(credit_structured, dict)
            else {}
        )

        segment = self._assign_segment(app_structured, behavior_structured, credit_structured)
        risk = str(credit_metrics.get("risk_level", "unknown") or "unknown")
        value = self._derive_value_signal(app_structured, behavior_structured)
        confidence = self._derive_confidence_level(
            app_structured, behavior_structured, credit_structured,
        )
        conflicts = self._build_conflict_explanations(
            app_structured, behavior_structured, credit_structured,
        )
        persona_seed = self._build_persona(
            segment, app_structured, behavior_structured, credit_structured,
        )
        tags_rule = self._build_tags(
            segment, value, risk, confidence, conflicts,
            app_structured, behavior_structured, credit_structured,
        )
        flat_metrics = self._flatten_metrics(
            feature_bundle, segment, risk, value, confidence, conflicts,
        )

        return ComprehensiveDecisionResult(
            uid=feature_bundle["uid"],
            country_code=context["country_code"],
            decision_status="ok",
            segment=segment,
            overall_risk_level=risk,
            value_signal_level=value,
            confidence_level=confidence,
            conflict_explanations=conflicts,
            persona_seed=persona_seed,
            tags_rule=tags_rule,
            metrics=flat_metrics,
            errors=[],
        )

    def build_prompt_payload(
        self,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
    ) -> dict[str, Any]:
        return {
            "uid": feature_bundle["uid"],
            "segment": decision_result["segment"],
            "overall_risk_level": decision_result["overall_risk_level"],
            "value_signal_level": decision_result["value_signal_level"],
            "confidence_level": decision_result["confidence_level"],
            "dimension_scores": {
                "app": feature_bundle["app_score"],
                "behavior": feature_bundle["behavior_score"],
                "credit": feature_bundle["credit_score"],
            },
            "conflict_seed": decision_result["conflict_explanations"],
            "persona_seed": decision_result["persona_seed"],
            "tags_rule": decision_result["tags_rule"],
            "upstream_summaries": feature_bundle["upstream_summaries"],
            "missing_modules": upstream["missing_modules"],
        }

    # --- helpers ---

    @staticmethod
    def _structured(skill_result: dict[str, Any]) -> dict[str, Any]:
        sr = skill_result.get("structured_result") if isinstance(skill_result, dict) else None
        return sr if isinstance(sr, dict) else {}

    # --- 原样搬自 comprehensive_agent.py ---

    @staticmethod
    def _assign_segment(
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
        credit_structured: dict[str, Any],
    ) -> str:
        app_metrics = app_structured.get("metrics", {}) if isinstance(app_structured, dict) else {}
        behavior_metrics = (
            behavior_structured.get("metrics", {}) if isinstance(behavior_structured, dict) else {}
        )
        credit_metrics = (
            credit_structured.get("metrics", {}) if isinstance(credit_structured, dict) else {}
        )

        app_activity = str(app_structured.get("activity_level", "unknown") or "unknown")
        multi_loan = str(app_metrics.get("multi_loan_risk_level", "low") or "low")
        product_sensitivity = str(
            behavior_metrics.get("product_sensitivity_level", "medium") or "medium"
        )
        churn_risk = str(behavior_metrics.get("churn_risk_level", "medium") or "medium")
        credit_risk = str(credit_metrics.get("risk_level", "unknown") or "unknown")
        debt_pressure = str(credit_metrics.get("debt_pressure_level", "unknown") or "unknown")
        stability = str(credit_metrics.get("credit_stability_level", "unknown") or "unknown")

        if multi_loan == "high" or (credit_risk == "high" and debt_pressure in {"high", "medium_high"}):
            return "S5"
        if churn_risk == "high":
            return "S4"
        if credit_risk == "low" and app_activity == "high" and stability in {"high", "medium_high"}:
            return "S1"
        if credit_risk in {"low", "medium"} and stability in {"high", "medium_high", "medium"}:
            return "S2"
        if product_sensitivity in {"high", "medium_high"} or multi_loan == "medium":
            return "S3"
        return "S6"

    @staticmethod
    def _build_conflict_explanations(
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
        credit_structured: dict[str, Any],
    ) -> list[str]:
        conflicts: list[str] = []
        app_metrics = app_structured.get("metrics", {}) if isinstance(app_structured, dict) else {}
        behavior_metrics = (
            behavior_structured.get("metrics", {}) if isinstance(behavior_structured, dict) else {}
        )
        credit_metrics = (
            credit_structured.get("metrics", {}) if isinstance(credit_structured, dict) else {}
        )

        multi_loan = str(app_metrics.get("multi_loan_risk_level", "low") or "low")
        credit_risk = str(credit_metrics.get("risk_level", "unknown") or "unknown")
        product_sensitivity = str(
            behavior_metrics.get("product_sensitivity_level", "medium") or "medium"
        )
        behavior_engagement = str(
            behavior_structured.get("engagement_level", "unknown") or "unknown"
        )

        if multi_loan in {"medium", "high"} and credit_risk == "low":
            conflicts.append(
                "App-side multi-loan pressure appears earlier than credit deterioration; treat as early warning rather than confirmed hard risk."
            )
        if credit_structured.get("status") != "ok":
            conflicts.append(
                "Credit module is missing or degraded, so final confidence relies more on app and behavior signals."
            )
        if (
            product_sensitivity in {"high", "medium_high"}
            and behavior_engagement in {"balanced", "deep", "medium", "heavy"}
            and multi_loan in {"medium", "high"}
        ):
            conflicts.append(
                "Active and price-sensitive behavior plus risky app installs may reflect comparison shopping, not immediate default pressure."
            )
        if not conflicts:
            conflicts.append("No major cross-signal conflict detected in the current upstream outputs.")
        return conflicts

    @staticmethod
    def _derive_value_signal(
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
    ) -> str:
        app_metrics = app_structured.get("metrics", {}) if isinstance(app_structured, dict) else {}
        behavior_metrics = (
            behavior_structured.get("metrics", {}) if isinstance(behavior_structured, dict) else {}
        )
        app_activity = str(app_structured.get("activity_level", "unknown") or "unknown")
        consumption = str(app_metrics.get("consumption_ability_level", "low") or "low")
        engagement = int(behavior_metrics.get("engagement_score", 0) or 0)

        if app_activity == "high" and consumption in {"medium_high", "high"} and engagement >= 70:
            return "high"
        if app_activity in {"high", "medium"} or engagement >= 45:
            return "medium"
        return "low"

    @staticmethod
    def _derive_confidence_level(
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
        credit_structured: dict[str, Any],
    ) -> str:
        ok_count = sum(
            1
            for result in (app_structured, behavior_structured, credit_structured)
            if isinstance(result, dict) and result.get("status") == "ok"
        )
        return "high" if ok_count == 3 else "medium" if ok_count == 2 else "low"

    @staticmethod
    def _build_persona(
        segment: str,
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
        credit_structured: dict[str, Any],
    ) -> str:
        app_activity = str(app_structured.get("activity_level", "unknown") or "unknown")
        behavior_engagement = str(behavior_structured.get("engagement_level", "unknown") or "unknown")
        credit_risk = str(
            credit_structured.get("metrics", {}).get("risk_level", "unknown") or "unknown"
        )
        return f"{segment} / {app_activity}-activity / {behavior_engagement}-engagement / {credit_risk}-risk"

    @staticmethod
    def _build_tags(
        segment: str,
        value_signal: str,
        risk_level: str,
        confidence_level: str,
        conflicts: list[str],
        app_structured: dict[str, Any],
        behavior_structured: dict[str, Any],
        credit_structured: dict[str, Any],
    ) -> list[str]:
        merged_tags = sorted(
            set(
                app_structured.get("tags", [])
                + behavior_structured.get("tags", [])
                + credit_structured.get("tags", [])
            )
        )
        merged_tags.extend(
            [
                f"segment-{segment.lower()}",
                f"overall-risk-{risk_level}",
                f"value-{value_signal}",
                f"confidence-{confidence_level}",
            ]
        )
        if conflicts and not (len(conflicts) == 1 and conflicts[0].startswith("No major cross-signal conflict")):
            merged_tags.append("cross-signal-conflict")
        return sorted(set(merged_tags))

    @staticmethod
    def _flatten_metrics(
        feature_bundle: ComprehensiveFeatureBundle,
        segment: str,
        risk: str,
        value: str,
        confidence: str,
        conflicts: list[str],
    ) -> dict[str, Any]:
        return {
            "segment": segment,
            "risk_level": risk,
            "value_signal_level": value,
            "confidence_level": confidence,
            "dimension_scores": {
                "app": feature_bundle["app_score"],
                "behavior": feature_bundle["behavior_score"],
                "credit": feature_bundle["credit_score"],
            },
            "conflict_count": len(conflicts),
            "conflict_explanations": list(conflicts),
        }
