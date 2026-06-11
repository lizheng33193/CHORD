"""Decision engine layer for the trace_analyzer pipeline.

Assembles prompt payload + deterministic template fallback story / interventions.
See docs/specs/trace-analyzer-design.md §6.
"""
from __future__ import annotations

from typing import Any

from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceFeatureBundle,
    TraceRunContext,
)


class TraceDecisionEngine:
    """Build prompt payload + template fallback."""

    def decide(
        self,
        feature_bundle: TraceFeatureBundle,
        context: TraceRunContext,
    ) -> TraceDecisionResult:
        if feature_bundle["feature_status"] != "ok":
            return {
                "uid": feature_bundle["uid"],
                "decision_status": "skipped",
                "prompt_payload": {},
                "fallback_story": self._fallback_story_skipped(feature_bundle["feature_status"]),
                "fallback_interventions": [],
                "errors": list(feature_bundle.get("errors", [])),
            }

        prompt_payload: dict[str, Any] = {
            "event_window": feature_bundle["event_window"],
            "path_graph": feature_bundle["path_graph"],
            "friction_hotspots": feature_bundle["friction_hotspots"],
            "time_pattern": feature_bundle["time_pattern"],
            "key_events_tail": feature_bundle["key_events_tail"],
            "churn_candidates": feature_bundle["churn_root_cause_candidates"],
        }
        return {
            "uid": feature_bundle["uid"],
            "decision_status": "ok",
            "prompt_payload": prompt_payload,
            "fallback_story": self._build_fallback_story(feature_bundle),
            "fallback_interventions": self._build_fallback_interventions(feature_bundle),
            "errors": list(feature_bundle.get("errors", [])),
        }

    @staticmethod
    def _fallback_story_skipped(status: str) -> str:
        if status == "insufficient_events":
            return "事件量不足，无法生成行为深度解析。"
        return "事件数据缺失或异常，无法生成行为深度解析。"

    @staticmethod
    def _build_fallback_story(bundle: TraceFeatureBundle) -> str:
        n_hot = len(bundle["friction_hotspots"])
        n_pages = len(bundle["path_graph"]["top_pages"])
        label = bundle["time_pattern"].get("active_window_label", "")
        return (
            f"基于规则识别到 {n_hot} 个摩擦热点，{n_pages} 个高频页面，"
            f"时段特征为 {label}。详见结构化结果。"
        )

    @staticmethod
    def _build_fallback_interventions(bundle: TraceFeatureBundle) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in bundle["friction_hotspots"][:3]:
            out.append({
                "hotspot": h["step"],
                "advice": f"在 {h['step']} 阶段观察到 retry={h['retry_count']} / "
                          f"error={h['error_count']}，建议针对性优化引导。",
                "channel_hint": "",
            })
        return out
