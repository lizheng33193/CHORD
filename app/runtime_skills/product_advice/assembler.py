"""Assembler layer for the Product Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.model_client import ModelClient
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceExplanationResult,
    ProductAdviceFeatureBundle,
    ProductAdvicePageResult,
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)
from app.schemas.product_advice import ProductAdviceStructuredResult
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


class ProductAdvicePageAssembler:
    """Merge rules + LLM output into the final AgentOutput-shaped page payload."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: ProductAdviceRunContext,
        upstream: ProductAdviceUpstreamBundle,
    ) -> ProductAdvicePageResult:
        reason = upstream.get("data_status", "missing")
        structured = ProductAdviceStructuredResult(
            uid=uid, status="data_missing", segment="", segment_name="",
            tags=["数据不足", "建议人工复核"],
            missing_comprehensive_advice_fields=list(
                upstream.get("missing_comprehensive_advice_fields", [])
            ),
            used_default_advice_inputs=bool(upstream.get("used_default_advice_inputs", False)),
            model_trace={
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": f"upstream_{reason}",
            },
        )
        return {
            "summary": "上游 comprehensive_profile 数据不足，建议人工复核后再生成产品策略。",
            "structured_result": model_dump_compat(structured),
            "charts": [],
            "report_markdown": f"## {uid} · 产品策略建议\n\n> 数据不足（{reason}），建议人工复核。",
        }

    def build_fallback_structured(
        self,
        uid: str,
        upstream: ProductAdviceUpstreamBundle,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = decision_result["segment"]
        structured = ProductAdviceStructuredResult(
            uid=uid, status="ok",
            segment=seg, segment_name=MX_SEGMENT_NAMES.get(seg, ""),
            renewal_strategy=decision_result.get("renewal_strategy", {}),
            credit_line_action=decision_result.get("credit_line_action", {}),
            rate_plan=decision_result.get("rate_plan", {}),
            recommended_channel=decision_result.get("recommended_channel", {}),
            priority=decision_result.get("priority", ""),
            tags=list(decision_result.get("tags", [])),
            missing_comprehensive_advice_fields=list(
                upstream.get("missing_comprehensive_advice_fields", [])
            ),
            used_default_advice_inputs=bool(upstream.get("used_default_advice_inputs", False)),
            model_trace={
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": self._contract_fallback_reason(upstream),
            },
        )
        return model_dump_compat(structured)

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: ProductAdviceExplanationResult,
    ) -> ProductAdvicePageResult:
        structured = deepcopy(fallback_structured)
        payload = explanation_result.get("payload", {})
        if explanation_result.get("used_llm") and isinstance(payload, dict):
            structured["explanation"] = payload

        existing_reason = str(
            ((structured.get("model_trace") or {}).get("fallback_reason"))
            if isinstance(structured.get("model_trace"), dict)
            else ""
        )
        explanation_reason = str(explanation_result.get("fallback_reason", ""))
        structured["model_trace"] = {
            "mode": self.model_client.mode,
            "used_llm": bool(explanation_result.get("used_llm")),
            "model_name": str(explanation_result.get("model_name", self.model_client.model_name) or ""),
            "fallback_reason": self._merge_fallback_reasons(existing_reason, explanation_reason),
        }
        validated = model_dump_compat(model_validate_compat(ProductAdviceStructuredResult, structured))
        summary = self._build_summary(validated, payload)
        report = self._build_report(uid, validated, payload)
        return {
            "summary": summary,
            "structured_result": validated,
            "charts": [],
            "report_markdown": report,
        }

    @staticmethod
    def _build_summary(structured: dict[str, Any], explanation: dict[str, Any]) -> str:
        if isinstance(explanation, dict) and explanation.get("recommendation_summary"):
            return str(explanation["recommendation_summary"])
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        ren = structured.get("renewal_strategy", {}).get("action", "")
        line = structured.get("credit_line_action", {}).get("action", "")
        ch = structured.get("recommended_channel", {}).get("primary", "")
        return f"{seg} {seg_name}建议{ren} + {line}，{ch} 触达。"

    @staticmethod
    def _build_report(uid: str, structured: dict[str, Any], explanation: dict[str, Any]) -> str:
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        rs = structured.get("renewal_strategy", {})
        cla = structured.get("credit_line_action", {})
        rp = structured.get("rate_plan", {})
        ch = structured.get("recommended_channel", {})
        lines = [
            f"## {uid} · {seg} {seg_name} · 产品策略建议",
            "",
            f"- **续贷策略**：{rs.get('action', '')}（{rs.get('reason', '')}）",
            f"- **额度动作**：{cla.get('action', '')}（{cla.get('reason', '')}）",
            f"- **利率方案**：{rp.get('plan', '')}" + (f"（锚定 {rp['anchor_competitor']}）" if rp.get("anchor_competitor") else ""),
            f"- **触达渠道**：{ch.get('primary', '')}（{ch.get('best_time', '')}）",
            f"- **优先级**：{structured.get('priority', '')}",
        ]
        if isinstance(explanation, dict) and explanation.get("talking_points"):
            lines.append("")
            lines.append("### 话术建议")
            for tp in explanation.get("talking_points", []):
                lines.append(f"- {tp}")
        return "\n".join(lines)

    @staticmethod
    def _contract_fallback_reason(upstream: ProductAdviceUpstreamBundle) -> str:
        missing = list(upstream.get("missing_comprehensive_advice_fields", []))
        if not missing:
            return ""
        return f"missing_comprehensive_advice_fields:{','.join(missing)}"

    @staticmethod
    def _merge_fallback_reasons(existing: str, new: str) -> str:
        reasons = [reason for reason in (existing.strip(), new.strip()) if reason]
        return "; ".join(dict.fromkeys(reasons))
