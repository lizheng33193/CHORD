"""Assembly layer for the Credit profile pipeline."""

from __future__ import annotations

from copy import deepcopy

from app.core.model_client import ModelClient
from app.runtime_skills.credit_profile.contracts import (
    CreditDecisionResult,
    CreditExplanationResult,
    CreditFeatureBundle,
    CreditPageResult,
    CreditRawData,
    CreditRunContext,
)
from app.schemas.credit_profile import CreditProfileStructuredResult
from app.scripts.chart_builder import build_credit_charts
from app.services.report_renderer import render_agent_report
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


class CreditPageAssembler:
    """Merge rule outputs and explanation outputs into the final Credit page payload."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: CreditRunContext,
        *,
        data_status: str = "missing",
        errors: list[str] | None = None,
    ) -> CreditPageResult:
        summary = (
            "当前征信输入数据无效，页面已回退为缺数据信息。"
            if data_status == "invalid"
            else "当前 uid 暂未找到可用的征信样本数据。"
        )
        tags = ["credit-data-missing"]
        if data_status == "invalid":
            tags.append("credit-data-invalid")
        structured = CreditProfileStructuredResult(
            uid=uid,
            status="data_missing",
            evidence={
                "market_context": "mexico_buro_credit_profile",
                "analysis_mode": "credit-data-missing",
                "errors": errors or [],
                "source_country": context.get("country_code", ""),
            },
            metrics={},
            tags=tags,
            model_trace={
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": "invalid_credit_data"
                if data_status == "invalid"
                else "missing_credit_data",
            },
        )
        structured_dict = model_dump_compat(structured)
        report_markdown = render_agent_report(
            "征信画像分析报告",
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
        _raw_data: CreditRawData,
        _feature_bundle: CreditFeatureBundle,
        decision_result: CreditDecisionResult,
    ) -> dict[str, object]:
        structured = CreditProfileStructuredResult(
            uid=uid,
            status="ok",
            evidence=decision_result.get("evidence_seed", {}),
            metrics=decision_result.get("metrics", {}),
            tags=[str(tag) for tag in decision_result.get("tags_rule", []) if str(tag).strip()],
            # New top-level level fields for label_builder convenience
            risk_level=str(
                decision_result.get("metrics", {}).get("risk_level", "unknown") or "unknown"
            ),
            financial_maturity_level=str(
                decision_result.get("financial_maturity", {}).get("level", "unknown")
                or "unknown"
            ),
            debt_pressure_level=str(
                decision_result.get("debt_pressure", {}).get("level", "unknown") or "unknown"
            ),
            credit_stability_level=str(
                decision_result.get("credit_stability", {}).get("level", "unknown")
                or "unknown"
            ),
            borrowing_urgency_level=str(
                decision_result.get("borrowing_urgency", {}).get("level", "unknown")
                or "unknown"
            ),
            # New nested sub-models (Pydantic auto-coerces dict → model)
            financial_maturity=decision_result.get("financial_maturity", {}),
            debt_pressure=decision_result.get("debt_pressure", {}),
            credit_stability=decision_result.get("credit_stability", {}),
            borrowing_urgency=decision_result.get("borrowing_urgency", {}),
        )
        return model_dump_compat(structured)

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, object],
        explanation_result: CreditExplanationResult,
    ) -> CreditPageResult:
        structured = deepcopy(fallback_structured)
        self._apply_explanation(structured, explanation_result)

        if structured.get("status") != "data_missing":
            # Deterministic Credit facts are sufficient for a complete page.
            # LLM failures should degrade explanation quality, not the whole module.
            structured["status"] = "ok"

        structured["model_trace"] = explanation_result.get("model_trace", {})

        validated = model_dump_compat(
            model_validate_compat(CreditProfileStructuredResult, structured)
        )
        summary = str(explanation_result.get("summary") or self._build_summary(validated))
        charts = build_credit_charts(validated) if validated.get("status") != "data_missing" else []
        report_markdown = str(
            explanation_result.get("report_markdown")
            or render_agent_report(
                "征信画像分析报告",
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
        explanation_result: CreditExplanationResult,
    ) -> None:
        evidence_patch = explanation_result.get("evidence_patch", {})
        if isinstance(evidence_patch, dict) and evidence_patch:
            merged_evidence = dict(structured.get("evidence", {}))
            structured["evidence"] = self._merge_dicts(merged_evidence, evidence_patch)

        tags = explanation_result.get("tags", [])
        if isinstance(tags, list) and tags:
            existing_tags = [str(tag) for tag in structured.get("tags", []) if str(tag).strip()]
            structured["tags"] = self._dedupe_strings(existing_tags + [str(tag) for tag in tags])

    def _build_summary(self, structured: dict[str, object]) -> str:
        status = str(structured.get("status", "ok") or "ok")
        if status != "ok":
            return "征信画像当前已回退为规则结果。"

        evidence = structured.get("evidence", {})
        if isinstance(evidence, dict):
            llm_profile = evidence.get("llm_credit_profile", {})
            if isinstance(llm_profile, dict):
                credit_summary = str(llm_profile.get("credit_summary", "") or "").strip()
                if credit_summary:
                    return credit_summary

        metrics = structured.get("metrics", {})
        if not isinstance(metrics, dict):
            return "征信画像当前已回退为规则结果。"
        risk_level = str(metrics.get("risk_level", "unknown") or "unknown")
        debt_pressure = str(metrics.get("debt_pressure_level", "unknown") or "unknown")
        credit_stability = str(metrics.get("credit_stability_level", "unknown") or "unknown")
        borrowing_urgency = str(metrics.get("borrowing_urgency_level", "unknown") or "unknown")

        return (
            "当前征信画像采用规则结果回退输出，"
            f"整体风险为{risk_level}，负债压力为{debt_pressure}，"
            f"信用稳定性为{credit_stability}，借贷饥渴度为{borrowing_urgency}。"
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
