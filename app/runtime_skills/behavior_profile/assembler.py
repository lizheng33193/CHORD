"""Assembly layer for the Behavior profile pipeline."""

from __future__ import annotations

from copy import deepcopy

from app.core.model_client import ModelClient
from app.runtime_skills.behavior_profile.contracts import (
    BehaviorDecisionResult,
    BehaviorExplanationResult,
    BehaviorFeatureBundle,
    BehaviorPageResult,
    BehaviorRawData,
    BehaviorRunContext,
)
from app.schemas.behavior_profile import BehaviorProfileStructuredResult
from app.scripts.chart_builder import build_behavior_charts
from app.services.report_renderer import render_agent_report
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


class BehaviorPageAssembler:
    """Merge rule outputs and explanation outputs into the final Behavior page payload."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: BehaviorRunContext,
        *,
        data_status: str = "missing",
        errors: list[str] | None = None,
    ) -> BehaviorPageResult:
        summary = (
            "当前行为事件输入无效，页面已回退为缺失数据提示。"
            if data_status == "invalid"
            else "当前 uid 暂未找到可用的行为数据。"
        )
        tags = ["behavior-data-missing"]
        if data_status == "invalid":
            tags.append("behavior-data-invalid")
        structured = BehaviorProfileStructuredResult(
            uid=uid,
            status="data_missing",
            evidence={
                "market_context": "mexico_behavior_timeline_profile",
                "analysis_mode": "behavior-data-missing",
                "errors": errors or [],
                "source_country": context.get("country_code", ""),
                "used_llm_profile": False,
                "used_llm_timeline": False,
                "fallback_reason": (
                    "invalid_behavior_data"
                    if data_status == "invalid"
                    else "missing_behavior_data"
                ),
            },
            metrics={},
            tags=tags,
            model_trace={
                "mode": self.model_client.mode,
                "used_llm": False,
                "used_llm_profile": False,
                "used_llm_timeline": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": (
                    "invalid_behavior_data"
                    if data_status == "invalid"
                    else "missing_behavior_data"
                ),
            },
        )
        structured_dict = model_dump_compat(structured)
        report_markdown = render_agent_report(
            "行为画像分析报告",
            uid,
            summary,
            structured_dict,
        )
        return {
            "summary": summary,
            "structured_result": structured_dict,
            "charts": [],
            "report_markdown": report_markdown,
        }

    def build_fallback_structured(
        self,
        uid: str,
        _raw_data: BehaviorRawData,
        _feature_bundle: BehaviorFeatureBundle,
        decision_result: BehaviorDecisionResult,
    ) -> dict[str, object]:
        structured = BehaviorProfileStructuredResult(
            uid=uid,
            status="ok",
            engagement_level=str(
                decision_result.get("engagement_profile", {}).get("level", "light")
                or "light"
            ),
            evidence=decision_result.get("evidence_seed", {}),
            metrics=decision_result.get("metrics", {}),
            tags=[
                str(tag)
                for tag in decision_result.get("tags_rule", [])
                if str(tag).strip()
            ],
            # New top-level level fields for label_builder convenience
            repayment_willingness_level=str(
                decision_result.get("repayment_willingness", {}).get("level", "unknown")
                or "unknown"
            ),
            product_sensitivity_level=str(
                decision_result.get("product_sensitivity", {}).get("level", "unknown")
                or "unknown"
            ),
            churn_risk_level=str(
                decision_result.get("churn_risk", {}).get("level", "unknown")
                or "unknown"
            ),
            # New nested sub-models (Pydantic auto-coerces dict → model)
            repayment_willingness=decision_result.get("repayment_willingness", {}),
            product_sensitivity=decision_result.get("product_sensitivity", {}),
            churn_risk=decision_result.get("churn_risk", {}),
            contact_preference=decision_result.get("contact_preference", {}),
        )
        return model_dump_compat(structured)

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, object],
        explanation_result: BehaviorExplanationResult,
    ) -> BehaviorPageResult:
        structured = deepcopy(fallback_structured)
        self._apply_explanation(structured, explanation_result)

        if structured.get("status") != "data_missing":
            structured["status"] = "ok"

        structured["model_trace"] = explanation_result.get("model_trace", {})

        validated = model_dump_compat(
            model_validate_compat(BehaviorProfileStructuredResult, structured)
        )
        summary = str(explanation_result.get("summary") or self._build_summary(validated))
        charts = (
            build_behavior_charts(validated)
            if validated.get("status") != "data_missing"
            else []
        )
        report_markdown = str(
            explanation_result.get("report_markdown")
            or render_agent_report(
                "行为画像分析报告",
                uid,
                summary,
                {
                    **validated,
                    "model_trace": explanation_result.get("model_trace", {}),
                },
            )
        )
        return {
            "summary": summary,
            "structured_result": validated,
            "charts": charts,
            "report_markdown": report_markdown,
        }

    def _apply_explanation(
        self,
        structured: dict[str, object],
        explanation_result: BehaviorExplanationResult,
    ) -> None:
        churn_root_cause = explanation_result.get("churn_root_cause")
        if isinstance(churn_root_cause, list) and churn_root_cause:
            structured["churn_root_cause"] = [str(c) for c in churn_root_cause if str(c).strip()]

        evidence_patch = explanation_result.get("evidence_patch", {})
        if isinstance(evidence_patch, dict) and evidence_patch:
            merged_evidence = dict(structured.get("evidence", {}))
            structured["evidence"] = self._merge_dicts(merged_evidence, evidence_patch)

        tags = explanation_result.get("tags", [])
        if isinstance(tags, list) and tags:
            existing_tags = [
                str(tag) for tag in structured.get("tags", []) if str(tag).strip()
            ]
            structured["tags"] = self._dedupe_strings(
                existing_tags + [str(tag) for tag in tags]
            )

        evidence = structured.get("evidence", {})
        if isinstance(evidence, dict):
            llm_profile = evidence.get("llm_profile")
            llm_behavior_profile = evidence.get("llm_behavior_profile")
            if isinstance(llm_behavior_profile, dict) and not isinstance(llm_profile, dict):
                evidence["llm_profile"] = llm_behavior_profile

            timeline_sections = evidence.get("timeline_sections")
            compact_sections = evidence.get("timeline_sections_compact")
            raw_sections = evidence.get("timeline_sections_raw")
            if not isinstance(compact_sections, list) and isinstance(timeline_sections, list):
                evidence["timeline_sections_compact"] = timeline_sections
            if not isinstance(raw_sections, list) and isinstance(timeline_sections, list):
                evidence["timeline_sections_raw"] = timeline_sections
            if not isinstance(timeline_sections, list) and isinstance(compact_sections, list):
                evidence["timeline_sections"] = compact_sections
            if not evidence.get("timeline_narrative") and evidence.get("llm_timeline"):
                evidence["timeline_narrative"] = evidence["llm_timeline"]

            structured["evidence"] = evidence

    def _build_summary(self, structured: dict[str, object]) -> str:
        status = str(structured.get("status", "ok") or "ok")
        if status != "ok":
            return "行为画像当前已回退为规则结果。"

        evidence = structured.get("evidence", {})
        if isinstance(evidence, dict):
            narrative = evidence.get("behavior_profile_narrative", {})
            if isinstance(narrative, dict):
                summary = str(narrative.get("behavior_summary", "") or "").strip()
                if summary:
                    return summary

            llm_profile = evidence.get("llm_profile") or evidence.get(
                "llm_behavior_profile",
                {},
            )
            if isinstance(llm_profile, dict):
                behavior_summary = str(llm_profile.get("behavior_summary", "") or "").strip()
                if behavior_summary:
                    return behavior_summary

        metrics = structured.get("metrics", {})
        if not isinstance(metrics, dict):
            return "行为画像当前已回退为规则结果。"
        engagement_level = str(structured.get("engagement_level", "unknown") or "unknown")
        repayment = str(metrics.get("repayment_willingness_level", "unknown") or "unknown")
        product_sensitivity = str(
            metrics.get("product_sensitivity_level", "unknown") or "unknown"
        )
        churn_risk = str(metrics.get("churn_risk_level", "unknown") or "unknown")
        return (
            "当前行为画像采用规则结果回退输出，"
            f"活跃度为{engagement_level}，还款意愿为{repayment}，"
            f"产品敏感度为{product_sensitivity}，流失风险为{churn_risk}。"
        )

    def _merge_dicts(self, base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(dict(merged[key]), value)  # type: ignore[index]
            else:
                merged[key] = value
        return merged

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = str(value or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped
