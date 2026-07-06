"""OpsAdviceSkill — six-step pipeline orchestrator (thin entry)."""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.ops_advice import (
    OpsAdviceDecisionEngine,
    OpsAdviceExplainer,
    OpsAdviceFeatureBuilder,
    OpsAdvicePageAssembler,
    OpsAdviceUpstreamProvider,
    build_ops_advice_run_context,
)


class OpsAdviceSkill(BaseSkill):
    name = "ops_advice"
    stage = 2
    depends_on: list[str] = ["comprehensive_profile"]

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        prompt_path = settings.resolve_path(f"{settings.prompt_dir}/ops_advice_prompt.md")
        self.upstream_provider = OpsAdviceUpstreamProvider()
        self.feature_builder = OpsAdviceFeatureBuilder()
        self.decision_engine = OpsAdviceDecisionEngine()
        self.explainer = OpsAdviceExplainer(model_client, prompt_path)
        self.assembler = OpsAdvicePageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        country_code = kwargs.get("country_code") or settings.default_country_code
        context = build_ops_advice_run_context(uid, country_code=country_code)
        upstream = self.upstream_provider.fetch(
            uid, context,
            comprehensive_result=kwargs.get("comprehensive_profile_result", {}) or {},
        )
        if upstream["data_status"] != "ok":
            return self.assembler.build_missing_output(uid, context, upstream)

        feature_bundle = self.feature_builder.build(upstream, context)
        decision_result = self.decision_engine.decide(feature_bundle, context)
        prompt_payload = self.decision_engine.build_prompt_payload(feature_bundle, decision_result)
        fallback_structured = self.assembler.build_fallback_structured(
            uid,
            upstream,
            feature_bundle,
            decision_result,
        )
        explanation_result = self.explainer.explain(
            uid, feature_bundle, decision_result, prompt_payload, context,
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
