"""ComprehensiveProfileSkill — six-step pipeline orchestrator (thin entry)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.comprehensive import (
    ComprehensiveDecisionEngine,
    ComprehensiveExplainer,
    ComprehensiveFeatureBuilder,
    ComprehensivePageAssembler,
    ComprehensiveUpstreamProvider,
    build_comprehensive_run_context,
)


class ComprehensiveProfileSkill(BaseSkill):
    name = "comprehensive_profile"
    stage = 1
    depends_on: list[str] = ["app_profile", "behavior_profile", "credit_profile"]

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        prompt_path = settings.resolve_path(
            f"{settings.prompt_dir}/comprehensive_prompt.md"
        )
        self.upstream_provider = ComprehensiveUpstreamProvider()
        self.feature_builder = ComprehensiveFeatureBuilder()
        self.decision_engine = ComprehensiveDecisionEngine()
        self.explainer = ComprehensiveExplainer(model_client, prompt_path)
        self.assembler = ComprehensivePageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        country_code = kwargs.get("country_code") or settings.default_country_code
        context = build_comprehensive_run_context(
            uid, application_time=kwargs.get("application_time"),
            country_code=country_code,
        )
        upstream = self.upstream_provider.fetch(
            uid, context,
            app_result=kwargs.get("app_profile_result", {}),
            behavior_result=kwargs.get("behavior_profile_result", {}),
            credit_result=kwargs.get("credit_profile_result", {}),
        )
        if upstream["data_status"] != "ok":
            return self.assembler.build_missing_output(uid, context, upstream)

        feature_bundle = self.feature_builder.build(upstream, context)
        decision_result = self.decision_engine.decide(feature_bundle, upstream, context)
        prompt_payload = self.decision_engine.build_prompt_payload(
            feature_bundle, decision_result, upstream,
        )
        fallback_structured = self.assembler.build_fallback_structured(
            uid, feature_bundle, decision_result,
        )
        explanation_result = self.explainer.explain(
            uid, feature_bundle, decision_result, upstream,
            prompt_payload, context,
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
