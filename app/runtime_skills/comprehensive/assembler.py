"""Final page assembly for the comprehensive pipeline."""
from __future__ import annotations

from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)
from app.schemas.comprehensive_profile import ComprehensiveProfileStructuredResult
from app.scripts.chart_builder import build_comprehensive_charts
from app.services.report_renderer import render_agent_report
from app.utils.pydantic_compat import model_validate_compat


class ComprehensivePageAssembler:
    """Assembles structured_result / charts / report_markdown for the API layer."""

    def __init__(self, model_client: ModelClient) -> None:
        # 仅读取 mode/model_name 用于 fallback 判断，不调用 generate_structured
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: ComprehensiveRunContext,
        upstream: ComprehensiveUpstreamBundle,
    ) -> ComprehensivePageResult:
        structured = {
            "uid": uid,
            "status": "data_missing",
            "persona": "unknown",
            "upstream_summaries": {},
            "metrics": {"dimension_scores": {"app": 0, "behavior": 0, "credit": 0}},
            "tags": ["upstream-data-missing"],
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": "upstream_all_missing",
            },
        }
        summary = "No upstream profile data was available for comprehensive analysis."
        return ComprehensivePageResult(
            summary=summary,
            structured_result=structured,
            charts=[],
            report_markdown=render_agent_report(
                "Comprehensive Profile Report", uid, summary, structured,
            ),
        )

    def build_fallback_structured(
        self,
        uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
    ) -> dict[str, Any]:
        summary = self._fallback_summary(decision_result)
        return {
            "uid": uid,
            "status": "ok",
            "persona": decision_result["persona_seed"],
            "upstream_summaries": dict(feature_bundle["upstream_summaries"]),
            "metrics": dict(decision_result["metrics"]),
            "tags": list(decision_result["tags_rule"]),
            "summary": summary,
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": (
                    "model_mode_mock" if self.model_client.mode == "mock" else ""
                ),
            },
        }

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: ComprehensiveExplanationResult,
    ) -> ComprehensivePageResult:
        structured = dict(fallback_structured)

        if explanation_result["used_llm"] and explanation_result["explanation_status"] == "ok":
            if explanation_result["summary"]:
                structured["summary"] = explanation_result["summary"]
            if explanation_result["persona"]:
                structured["persona"] = explanation_result["persona"]
            if explanation_result["conflict_explanations"]:
                metrics = dict(structured.get("metrics") or {})
                metrics["conflict_explanations"] = list(
                    explanation_result["conflict_explanations"]
                )
                structured["metrics"] = metrics
            if explanation_result["reasoning_texts"]:
                structured["reasoning_texts"] = dict(explanation_result["reasoning_texts"])

            merged_tags: list[str] = list(structured.get("tags") or [])
            seen = set(merged_tags)
            for t in explanation_result["tags_addon"]:
                if t not in seen:
                    merged_tags.append(t)
                    seen.add(t)
            structured["tags"] = merged_tags
            structured["status"] = "ok"

        elif explanation_result["explanation_status"] == "model_unavailable":
            structured["status"] = "model_unavailable"

        # status="skipped"（mock 模式）保持 fallback 的 status="ok"

        structured["model_trace"] = explanation_result["model_trace"]

        try:
            self._validate_against_schema(structured)
        except Exception as exc:  # noqa: BLE001
            structured["status"] = "model_unavailable"
            structured["model_trace"] = dict(structured["model_trace"])
            structured["model_trace"]["fallback_reason"] = (
                f"schema_validation_failed: {exc}"
            )

        summary = str(structured.get("summary") or "")
        return ComprehensivePageResult(
            summary=summary,
            structured_result=structured,
            charts=(
                build_comprehensive_charts(structured)
                if structured.get("status") != "data_missing"
                else []
            ),
            report_markdown=render_agent_report(
                "Comprehensive Profile Report", uid, summary, structured,
            ),
        )

    @staticmethod
    def _fallback_summary(decision: ComprehensiveDecisionResult) -> str:
        return (
            f"Segment {decision['segment']}, risk={decision['overall_risk_level']}, "
            f"value={decision['value_signal_level']}, "
            f"confidence={decision['confidence_level']}."
        )

    @staticmethod
    def _validate_against_schema(structured: dict[str, Any]) -> None:
        model_validate_compat(ComprehensiveProfileStructuredResult, structured)
