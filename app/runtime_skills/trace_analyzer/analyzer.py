"""Trace analyzer entry point — orchestrates the six-step pipeline.

Trace analyzer is an independent service module (not a SkillRegistry Skill).
See docs/specs/trace-analyzer-design.md §2.Q3 for governance boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.trace_analyzer.assembler import TraceAssembler
from app.runtime_skills.trace_analyzer.contracts import TraceRunContext
from app.runtime_skills.trace_analyzer.data_access import TraceDataAccess
from app.runtime_skills.trace_analyzer.decision_engine import TraceDecisionEngine
from app.runtime_skills.trace_analyzer.explainer import TraceExplainer
from app.runtime_skills.trace_analyzer.feature_builder import TraceFeatureBuilder


def build_context(uid: str, *, country_code: str | None = None,
                   enable_llm_explanation: bool = True) -> TraceRunContext:
    return {
        "uid": uid,
        "country_code": country_code or getattr(settings, "default_country_code", "mx"),
        "application_time": datetime.now(timezone.utc).isoformat(),
        "enable_llm_explanation": enable_llm_explanation,
    }


class TraceAnalyzer:
    """Orchestrate the trace_analyzer six-step pipeline.

    Note: Does NOT inherit BaseSkill. Not registered in SkillRegistry.
    Invoked directly by app/api/trace.py route handler.
    """

    def __init__(self, model_client: ModelClient | None = None) -> None:
        self.model_client = model_client or ModelClient()
        self.data_access = TraceDataAccess()
        self.feature_builder = TraceFeatureBuilder()
        self.decision_engine = TraceDecisionEngine()
        self.explainer = TraceExplainer(self.model_client)
        self.assembler = TraceAssembler()

    def analyze(self, uid: str, context: TraceRunContext | None = None) -> dict[str, Any]:
        ctx = context or build_context(uid)
        raw = self.data_access.fetch(uid, ctx)
        bundle = self.feature_builder.build(raw, ctx)
        decision = self.decision_engine.decide(bundle, ctx)
        explanation = self.explainer.explain(decision, ctx)
        return self.assembler.assemble(uid, bundle, decision, explanation)
