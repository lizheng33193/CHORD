"""Data access layer for the Ops Advice pipeline."""

from __future__ import annotations

from typing import Any

from app.country_packs.mx.segments import MX_SEGMENTS
from app.runtime_skills.ops_advice.contracts import (
    OpsAdviceRunContext,
    OpsAdviceUpstreamBundle,
)


class OpsAdviceUpstreamProvider:
    """Extract Ops-Advice-relevant fields from the comprehensive_profile result."""

    def fetch(
        self,
        uid: str,
        context: OpsAdviceRunContext,
        *,
        comprehensive_result: dict[str, Any],
    ) -> OpsAdviceUpstreamBundle:
        sr = comprehensive_result.get("structured_result", {}) if isinstance(comprehensive_result, dict) else {}
        if not isinstance(sr, dict) or not sr:
            return self._missing(uid, "missing")
        if str(sr.get("status", "")) != "ok":
            return self._missing(uid, "missing")

        metrics = sr.get("metrics", {}) if isinstance(sr.get("metrics"), dict) else {}
        segment_raw = str(metrics.get("recommended_segment") or metrics.get("segment") or sr.get("recommended_segment") or sr.get("segment") or "").strip().upper()
        segment_name = str(metrics.get("segment_name") or sr.get("segment_name") or "")

        if segment_raw not in MX_SEGMENTS:
            return self._missing(uid, "invalid_segment", segment=segment_raw)

        behavior_tags = metrics.get("behavior_tags", {}) if isinstance(metrics.get("behavior_tags"), dict) else {}
        financial_tags = metrics.get("financial_tags", {}) if isinstance(metrics.get("financial_tags"), dict) else {}

        return {
            "data_status": "ok",
            "segment": segment_raw,
            "segment_name": segment_name,
            "overall_risk": str(metrics.get("overall_risk", "")),
            "overall_value": str(metrics.get("overall_value", "")),
            "behavior_tags": dict(behavior_tags),
            "financial_tags": dict(financial_tags),
            "confidence": str(metrics.get("confidence", "")),
            "data_completeness": dict(metrics.get("data_completeness", {})) if isinstance(metrics.get("data_completeness"), dict) else {},
            "raw": dict(sr),
        }

    @staticmethod
    def _missing(uid: str, status: str, *, segment: str = "") -> OpsAdviceUpstreamBundle:
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
            "raw": {},
        }
