"""LLM explanation layer for the trace_analyzer pipeline.

Calls ModelClient.generate_structured() to produce churn story / intervention
suggestions / churn_root_cause final picks. See trace-analyzer-design.md §8.

Whitelist constraint: churn_root_cause output is filtered against the 6
candidate values shared with ops_advice (CHURN_ROOT_CAUSE_ENUM in _constants).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.trace_analyzer._constants import CHURN_ROOT_CAUSE_ENUM
from app.runtime_skills.trace_analyzer.contracts import (
    TraceDecisionResult,
    TraceExplanationResult,
    TraceRunContext,
)


PROMPT_PATH = Path(__file__).resolve().parents[3] / "app" / "prompts" / "trace_analyzer_prompt.md"


class TraceExplainer:
    """Generate LLM narrative + intervention suggestions on top of rule output."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def explain(
        self,
        decision_result: TraceDecisionResult,
        context: TraceRunContext,
    ) -> TraceExplanationResult:
        uid = decision_result["uid"]
        fallback_story = decision_result.get("fallback_story", "")
        fallback_interv = decision_result.get("fallback_interventions", [])

        if (
            decision_result["decision_status"] != "ok"
            or self.model_client.mode == "mock"
            or not context.get("enable_llm_explanation", True)
        ):
            return self._build_skipped(uid, fallback_story, fallback_interv,
                                        reason=self._skip_reason(decision_result, context))

        prompt = self._build_prompt(uid, decision_result["prompt_payload"])
        result = self.model_client.generate_structured(
            skill_name="trace_analyzer",
            prompt=prompt,
            fallback_result={"churn_story": "", "intervention_suggestions": [],
                              "churn_root_cause": []},
            response_schema=self._response_schema(),
            route_key="trace_analyzer.explainer",
        )
        if result.get("status") != "ok":
            return self._build_unavailable(uid, fallback_story, fallback_interv,
                                            reason=str(result.get("status", "")))

        sr = result.get("structured_result", {}) or {}
        churn_story = str(sr.get("churn_story", "") or "").strip() or fallback_story
        interventions = self._normalize_interventions(sr.get("intervention_suggestions"))
        if not interventions:
            interventions = fallback_interv
        churn_root_cause = [
            v for v in (sr.get("churn_root_cause") or []) if v in CHURN_ROOT_CAUSE_ENUM
        ] or ["no_clear_signal"]

        return {
            "uid": uid,
            "explanation_status": "ok",
            "used_llm": True,
            "churn_story": churn_story,
            "intervention_suggestions": interventions,
            "churn_root_cause": churn_root_cause[:2],
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": True,
                "model_name": self.model_client.model_name,
                "fallback_reason": "",
            },
            "errors": [],
        }

    # ---- helpers ----

    def _build_prompt(self, uid: str, payload: dict[str, Any]) -> str:
        if not PROMPT_PATH.exists():
            return f"trace prompt missing. uid={uid} trace_data={json.dumps(payload)}"
        tpl = PROMPT_PATH.read_text(encoding="utf-8")
        return tpl.replace("{{uid}}", uid).replace(
            "{{trace_data}}",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def _response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "churn_story": {"type": "string"},
                "intervention_suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hotspot": {"type": "string"},
                            "advice": {"type": "string"},
                            "channel_hint": {"type": "string"},
                        },
                    },
                },
                "churn_root_cause": {"type": "array", "items": {"type": "string"}},
            },
        }

    @staticmethod
    def _normalize_interventions(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            out.append({
                "hotspot": str(item.get("hotspot", "") or ""),
                "advice": str(item.get("advice", "") or ""),
                "channel_hint": str(item.get("channel_hint", "") or ""),
            })
        return out

    def _skip_reason(self, decision: TraceDecisionResult, ctx: TraceRunContext) -> str:
        if decision["decision_status"] != "ok":
            return f"decision_{decision['decision_status']}"
        if self.model_client.mode == "mock":
            return "model_mode_mock"
        if not ctx.get("enable_llm_explanation", True):
            return "llm_disabled"
        return "unknown"

    def _build_skipped(self, uid, fallback_story, fallback_interv, *, reason) -> TraceExplanationResult:
        return {
            "uid": uid, "explanation_status": "skipped", "used_llm": False,
            "churn_story": fallback_story, "intervention_suggestions": fallback_interv,
            "churn_root_cause": ["no_clear_signal"],
            "model_trace": {
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": reason,
            },
            "errors": [],
        }

    def _build_unavailable(self, uid, fallback_story, fallback_interv, *, reason) -> TraceExplanationResult:
        return {
            "uid": uid, "explanation_status": "model_unavailable", "used_llm": False,
            "churn_story": fallback_story, "intervention_suggestions": fallback_interv,
            "churn_root_cause": ["no_clear_signal"],
            "model_trace": {
                "mode": self.model_client.mode, "used_llm": False,
                "model_name": getattr(self.model_client, "model_name", ""),
                "fallback_reason": reason,
            },
            "errors": [],
        }
