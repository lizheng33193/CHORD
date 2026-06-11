"""Numeric feature extraction for the comprehensive pipeline (no judgement)."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


class ComprehensiveFeatureBuilder:
    """Extract metrics + summaries from upstream results, derive 1-5 scores.

    搬自原 comprehensive_agent._build_*_score / _extract_metrics 逻辑。
    缺失上游：metrics 置空 dict，score=0。
    """

    def build(
        self,
        upstream: ComprehensiveUpstreamBundle,
        context: ComprehensiveRunContext,
    ) -> ComprehensiveFeatureBundle:
        errors: list[str] = []

        app_metrics = self._extract_metrics(upstream["app_result"], "app_profile") if upstream["app_status"] == "ok" else {}
        behavior_metrics = self._extract_metrics(upstream["behavior_result"], "behavior_profile") if upstream["behavior_status"] == "ok" else {}
        credit_metrics = self._extract_metrics(upstream["credit_result"], "credit_profile") if upstream["credit_status"] == "ok" else {}

        app_score = self._build_app_score(app_metrics) if app_metrics else 0
        behavior_score = self._build_behavior_score(behavior_metrics) if behavior_metrics else 0
        credit_score = self._build_credit_score(credit_metrics) if credit_metrics else 0

        summaries = self._build_upstream_summaries(upstream)

        return ComprehensiveFeatureBundle(
            uid=upstream["uid"],
            country_code=context["country_code"],
            app_metrics=app_metrics,
            behavior_metrics=behavior_metrics,
            credit_metrics=credit_metrics,
            app_score=app_score,
            behavior_score=behavior_score,
            credit_score=credit_score,
            upstream_summaries=summaries,
            feature_status="ok",
            errors=errors,
        )

    @staticmethod
    def _extract_metrics(skill_result: dict[str, Any], _module: str) -> dict[str, Any]:
        sr = skill_result.get("structured_result") if isinstance(skill_result, dict) else None
        if not isinstance(sr, dict):
            return {}
        metrics = sr.get("metrics")
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _build_upstream_summaries(upstream: ComprehensiveUpstreamBundle) -> dict[str, str]:
        out: dict[str, str] = {}
        for result_key, module in (
            ("app_result", "app_profile"),
            ("behavior_result", "behavior_profile"),
            ("credit_result", "credit_profile"),
        ):
            res = upstream[result_key]  # type: ignore[literal-required]
            summary = ""
            if isinstance(res, dict):
                # Try structured_result.summary first, then top-level summary
                sr = res.get("structured_result")
                if isinstance(sr, dict):
                    raw = sr.get("summary")
                    if isinstance(raw, str) and raw.strip():
                        summary = raw
                if not summary:
                    top = res.get("summary")
                    if isinstance(top, str) and top.strip():
                        summary = top
            out[module] = summary
        return out

    @staticmethod
    def _build_app_score(metrics: dict[str, Any]) -> int:
        active_days = int(metrics.get("active_days_30d", 0) or 0)
        consumption_level = str(metrics.get("consumption_ability_level", "low") or "low")
        financial_maturity = str(metrics.get("financial_maturity_level", "unknown") or "unknown")
        score = min(5, max(1, active_days // 8 + 1)) if active_days else 0
        if consumption_level in {"medium", "medium_high", "high"}:
            score = min(5, score + 1)
        if financial_maturity in {"semi_banked", "banked"}:
            score = min(5, score + 1)
        return score

    @staticmethod
    def _build_behavior_score(metrics: dict[str, Any]) -> int:
        engagement = int(metrics.get("engagement_score", 0) or 0)
        repayment = str(metrics.get("repayment_willingness_level", "medium") or "medium")
        churn = str(metrics.get("churn_risk_level", "medium") or "medium")
        score = min(5, max(1, engagement // 20 + 1)) if engagement else 0
        if repayment in {"high", "medium_high"}:
            score = min(5, score + 1)
        if churn == "high":
            score = max(1, score - 1)
        return score

    @staticmethod
    def _build_credit_score(metrics: dict[str, Any]) -> int:
        risk_level = str(metrics.get("risk_level", "unknown") or "unknown")
        stability = str(metrics.get("credit_stability_level", "unknown") or "unknown")
        score = {"low": 5, "medium": 3, "high": 1}.get(risk_level, 0)
        if stability in {"high", "medium_high"}:
            score = min(5, score + 0)
        if stability == "low" and score > 0:
            score = max(1, score - 1)
        return score
