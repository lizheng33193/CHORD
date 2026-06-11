"""Credit profile skill orchestrating the layered Credit pipeline."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.credit_profile import (
    CreditDataProvider,
    CreditDecisionEngine,
    CreditExplainer,
    CreditFeatureBuilder,
    CreditPageAssembler,
)
from app.runtime_skills.credit_profile.contracts import build_credit_run_context


logger = get_logger(__name__)


class CreditProfileSkill(BaseSkill):
    """Run the Credit profile pipeline for one uid."""

    name = "credit_profile"
    stage = 0
    depends_on: list[str] = []

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client
        buro_prompt_path = settings.resolve_path(f"{settings.prompt_dir}/credit_profile_prompt.md")
        th_prompt_path = settings.resolve_path(f"{settings.prompt_dir}/credit_profile_th_prompt.md")
        self.feature_builder = CreditFeatureBuilder()
        self.decision_engine = CreditDecisionEngine()
        self.explainer = CreditExplainer(
            model_client,
            prompt_paths={
                "buro": buro_prompt_path,
                "risk_features": th_prompt_path,
            },
        )
        self.assembler = CreditPageAssembler(model_client)

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        """Execute the Credit profile pipeline end to end."""
        repository = kwargs.get("repository")
        country_code = kwargs.get("country_code") or settings.default_country_code
        context = build_credit_run_context(
            uid,
            country_code=country_code,
            source_preference=settings.data_source,
            enable_llm_explanation=True,
        )

        data_provider = CreditDataProvider(repository)
        raw_data = data_provider.fetch(uid, context)
        if raw_data["data_status"] != "ok":
            return self.assembler.build_missing_output(
                uid,
                context,
                data_status=raw_data["data_status"],
                errors=raw_data.get("errors", []),
            )

        feature_bundle = self.feature_builder.build(raw_data, context)
        decision_result = self.decision_engine.decide(feature_bundle, context)
        prompt_payload = self.decision_engine.build_prompt_payload(
            feature_bundle, decision_result
        )
        fallback_structured = self.assembler.build_fallback_structured(
            uid,
            raw_data,
            feature_bundle,
            decision_result,
        )
        explanation_result = self.explainer.explain(
            uid,
            feature_bundle,
            decision_result,
            prompt_payload,
            context,
        )

        logger.info(
            "Credit profile assembled uid=%s feature_status=%s decision_status=%s explanation_status=%s",
            uid,
            feature_bundle.get("feature_status"),
            decision_result.get("decision_status"),
            explanation_result.get("explanation_status"),
        )
        return self.assembler.assemble(uid, fallback_structured, explanation_result)
