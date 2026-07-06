"""Data access layer for the Product Advice pipeline."""

from __future__ import annotations

from typing import Any

from app.country_packs.mx.segments import MX_SEGMENTS
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceRunContext,
    ProductAdviceUpstreamBundle,
)


class ProductAdviceUpstreamProvider:
    """Extract Product-Advice-relevant fields from the comprehensive_profile result."""

    REQUIRED_FIELDS = (
        "segment",
        "segment_name",
        "overall_risk",
        "overall_value",
        "confidence",
        "data_completeness",
        "behavior_tags",
        "financial_tags",
    )

    def fetch(
        self,
        uid: str,
        context: ProductAdviceRunContext,
        *,
        comprehensive_result: dict[str, Any],
    ) -> ProductAdviceUpstreamBundle:
        sr = comprehensive_result.get("structured_result", {}) if isinstance(comprehensive_result, dict) else {}
        if not isinstance(sr, dict) or not sr:
            return self._missing(uid, "missing")
        if str(sr.get("status", "")) != "ok":
            return self._missing(uid, "missing")

        metrics = sr.get("metrics", {}) if isinstance(sr.get("metrics"), dict) else {}
        missing_fields = self._collect_missing_fields(sr, metrics)
        segment_raw = str(
            sr.get("segment")
            or sr.get("recommended_segment")
            or metrics.get("recommended_segment")
            or metrics.get("segment")
            or ""
        ).strip().upper()
        segment_name = str(sr.get("segment_name") or metrics.get("segment_name") or "")

        if segment_raw not in MX_SEGMENTS:
            return self._missing(uid, "invalid_segment", segment=segment_raw)

        behavior_tags = sr.get("behavior_tags", {}) if isinstance(sr.get("behavior_tags"), dict) else {}
        if not behavior_tags:
            behavior_tags = metrics.get("behavior_tags", {}) if isinstance(metrics.get("behavior_tags"), dict) else {}
        financial_tags = sr.get("financial_tags", {}) if isinstance(sr.get("financial_tags"), dict) else {}
        if not financial_tags:
            financial_tags = metrics.get("financial_tags", {}) if isinstance(metrics.get("financial_tags"), dict) else {}

        return {
            "data_status": "ok",
            "segment": segment_raw,
            "segment_name": segment_name,
            "overall_risk": str(sr.get("overall_risk") or metrics.get("overall_risk") or ""),
            "overall_value": str(sr.get("overall_value") or metrics.get("overall_value") or ""),
            "behavior_tags": dict(behavior_tags),
            "financial_tags": dict(financial_tags),
            "confidence": str(sr.get("confidence") or metrics.get("confidence") or ""),
            "data_completeness": dict(sr.get("data_completeness", {}))
            if isinstance(sr.get("data_completeness"), dict)
            else dict(metrics.get("data_completeness", {}))
            if isinstance(metrics.get("data_completeness"), dict)
            else {},
            "missing_comprehensive_advice_fields": missing_fields,
            "used_default_advice_inputs": bool(missing_fields),
            "raw": dict(sr),
        }

    @staticmethod
    def _missing(uid: str, status: str, *, segment: str = "") -> ProductAdviceUpstreamBundle:
        return {
            "data_status": status,
            "segment": segment,
            "segment_name": "",
            "overall_risk": "",
            "overall_value": "",
            "behavior_tags": {},
            "financial_tags": {},
            "confidence": "",
            "data_completeness": {},
            "missing_comprehensive_advice_fields": [],
            "used_default_advice_inputs": False,
            "raw": {},
        }

    def _collect_missing_fields(self, structured: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for field in self.REQUIRED_FIELDS:
            if field == "segment":
                present = any(
                    key in structured for key in ("segment", "recommended_segment")
                ) or any(key in metrics for key in ("segment", "recommended_segment"))
            else:
                present = field in structured or field in metrics
            if not present:
                missing.append(field)
        return missing
