"""Assembler layer for the Ops Advice pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.model_client import ModelClient
from app.country_packs.mx.segments import MX_SEGMENT_NAMES
from app.runtime_skills.ops_advice.contracts import (
    OpsAdviceDecisionResult,
    OpsAdviceExplanationResult,
    OpsAdviceFeatureBundle,
    OpsAdvicePageResult,
    OpsAdviceRunContext,
    OpsAdviceUpstreamBundle,
)
from app.schemas.ops_advice import OpsAdviceStructuredResult
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


class OpsAdvicePageAssembler:
    """Merge rules + LLM output into the final AgentOutput-shaped page payload."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: OpsAdviceRunContext,
        upstream: OpsAdviceUpstreamBundle,
    ) -> OpsAdvicePageResult:
        reason = upstream.get("data_status", "missing")
        structured = OpsAdviceStructuredResult(
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
            "summary": "上游 comprehensive_profile 数据不足，建议人工复核后再生成运营策略。",
            "structured_result": model_dump_compat(structured),
            "charts": [],
            "report_markdown": f"## {uid} · 运营策略建议\n\n> 数据不足（{reason}），建议人工复核。",
        }

    def build_fallback_structured(
        self,
        uid: str,
        upstream: OpsAdviceUpstreamBundle,
        feature_bundle: OpsAdviceFeatureBundle,
        decision_result: OpsAdviceDecisionResult,
    ) -> dict[str, Any]:
        seg = decision_result["segment"]
        structured = OpsAdviceStructuredResult(
            uid=uid, status="ok",
            segment=seg, segment_name=MX_SEGMENT_NAMES.get(seg, ""),
            collection_strategy=decision_result.get("collection_strategy", {}),
            churn_warning=decision_result.get("churn_warning", {}),
            outreach_channel=decision_result.get("outreach_channel", {}),
            retention_offer=decision_result.get("retention_offer", {}),
            churn_root_cause=list(feature_bundle.get("churn_root_cause", [])),
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
        explanation_result: OpsAdviceExplanationResult,
    ) -> OpsAdvicePageResult:
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
        validated = model_dump_compat(model_validate_compat(OpsAdviceStructuredResult, structured))
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
        if isinstance(explanation, dict) and explanation.get("retention_pitch"):
            return str(explanation["retention_pitch"])
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        intensity = structured.get("collection_strategy", {}).get("intensity", "")
        level = structured.get("churn_warning", {}).get("level", "")
        ch = structured.get("outreach_channel", {}).get("primary", "")
        return f"{seg} {seg_name}：{intensity} 催收 + {level}流失预警，{ch} 触达。"

    @staticmethod
    def _build_report(uid: str, structured: dict[str, Any], explanation: dict[str, Any]) -> str:
        seg = structured.get("segment", "")
        seg_name = structured.get("segment_name", "")
        cs = structured.get("collection_strategy", {})
        cw = structured.get("churn_warning", {})
        oc = structured.get("outreach_channel", {})
        ro = structured.get("retention_offer", {})
        lines = [
            f"## {uid} · {seg} {seg_name} · 运营策略建议",
            "",
            f"- **催收策略**：{cs.get('intensity', '')}（trigger={cs.get('trigger', '')}）",
            f"- **流失预警**：{cw.get('level', '')}（信号：{', '.join(cw.get('signals', []) or [])}）",
            f"- **触达渠道**：{oc.get('primary', '')}（{oc.get('best_time', '')}）",
            f"- **挽回方案**：{ro.get('type', '') or '无'}"
            + (f"（有效期 {ro.get('valid_days')} 天）" if ro.get("valid_days") else ""),
        ]
        if isinstance(explanation, dict) and explanation.get("outreach_script"):
            lines.append("")
            lines.append("### 触达话术")
            for s in explanation.get("outreach_script", []):
                lines.append(f"- {s}")
        return "\n".join(lines)

    @staticmethod
    def _contract_fallback_reason(upstream: OpsAdviceUpstreamBundle) -> str:
        missing = list(upstream.get("missing_comprehensive_advice_fields", []))
        if not missing:
            return ""
        return f"missing_comprehensive_advice_fields:{','.join(missing)}"

    @staticmethod
    def _merge_fallback_reasons(existing: str, new: str) -> str:
        reasons = [reason for reason in (existing.strip(), new.strip()) if reason]
        return "; ".join(dict.fromkeys(reasons))
