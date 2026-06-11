"""Assembly layer — merge rule output + LLM explanation into TraceAnalyzeResponse dict."""
from __future__ import annotations

from typing import Any

from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceExplanationResult,
    TraceFeatureBundle,
)


class TraceAssembler:
    """Assemble the final TraceAnalyzeResponse Pydantic-shaped dict."""

    def assemble(
        self,
        uid: str,
        feature_bundle: TraceFeatureBundle,
        decision_result: TraceDecisionResult,
        explanation_result: TraceExplanationResult,
    ) -> dict[str, Any]:
        status = self._resolve_status(feature_bundle, decision_result, explanation_result)

        path_graph_in = feature_bundle["path_graph"]
        # Pydantic Transition uses alias `from`, so populate by alias to match schema
        top_transitions = [
            {"from": t["from"], "to": t["to"], "count": t["count"]}
            for t in path_graph_in.get("top_transitions", [])
        ]
        path_graph = {
            "top_transitions": top_transitions,
            "top_pages": list(path_graph_in.get("top_pages", [])),
        }

        return {
            "uid": uid,
            "status": status,
            "event_window": feature_bundle["event_window"],
            "path_graph": path_graph,
            "friction_hotspots": list(feature_bundle["friction_hotspots"]),
            "time_pattern": feature_bundle["time_pattern"],
            "churn_root_cause": list(explanation_result["churn_root_cause"]),
            "churn_story": explanation_result["churn_story"],
            "intervention_suggestions": list(explanation_result["intervention_suggestions"]),
            "key_events_tail": list(feature_bundle["key_events_tail"]),
            "model_trace": dict(explanation_result["model_trace"]),
            "errors": list(set(
                list(feature_bundle.get("errors", []))
                + list(decision_result.get("errors", []))
                + list(explanation_result.get("errors", []))
            )),
        }

    @staticmethod
    def _resolve_status(
        bundle: TraceFeatureBundle,
        decision: TraceDecisionResult,
        explanation: TraceExplanationResult,
    ) -> str:
        if bundle["feature_status"] == "empty":
            return "data_missing"
        if bundle["feature_status"] == "insufficient_events":
            return "insufficient_events"
        if bundle["feature_status"] != "ok":
            return "error"
        if explanation["explanation_status"] == "ok":
            return "ok"
        return "model_unavailable"
