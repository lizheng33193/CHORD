"""Explainer layer for the Product Advice pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.runtime_skills.product_advice.contracts import (
    ProductAdviceDecisionResult,
    ProductAdviceExplanationResult,
    ProductAdviceFeatureBundle,
    ProductAdviceRunContext,
)


logger = get_logger(__name__)


class ProductAdviceExplainer:
    """Augment deterministic decisions with LLM-generated talking points."""

    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = Path(prompt_path)

    def explain(
        self,
        uid: str,
        feature_bundle: ProductAdviceFeatureBundle,
        decision_result: ProductAdviceDecisionResult,
        prompt_payload: dict[str, Any],
        context: ProductAdviceRunContext,
    ) -> ProductAdviceExplanationResult:
        if self.model_client.mode == "mock":
            return self._skipped("model_mode_mock")

        prompt = self._build_prompt(uid, prompt_payload)
        fallback = {"recommendation_summary": "", "talking_points": [], "risk_warnings": []}
        result = self.model_client.generate_structured(
            skill_name="product_advice",
            prompt=prompt,
            fallback_result=fallback,
            response_schema={
                "type": "object",
                "properties": {
                    "recommendation_summary": {"type": "string"},
                    "talking_points": {"type": "array", "items": {"type": "string"}},
                    "risk_warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
            route_key="product_advice.explainer",
        )
        payload = result.get("structured_result", {}) if isinstance(result.get("structured_result"), dict) else {}
        accepted = result.get("status") == "ok" and bool(str(payload.get("recommendation_summary", "")).strip())
        status = "ok" if accepted else "model_unavailable"
        return {
            "status": status,
            "payload": payload if accepted else {},
            "fallback_reason": "" if accepted else str(result.get("status", "model_unavailable")),
            "used_llm": accepted,
            "model_name": str(result.get("model_name", self.model_client.model_name) or ""),
        }

    def _skipped(self, reason: str) -> ProductAdviceExplanationResult:
        return {
            "status": reason,
            "payload": {},
            "fallback_reason": reason,
            "used_llm": False,
            "model_name": self.model_client.model_name,
        }

    def _build_prompt(self, uid: str, prompt_payload: dict[str, Any]) -> str:
        template = self.prompt_path.read_text(encoding="utf-8") if self.prompt_path.exists() \
            else "uid={{uid}} payload={{payload}}"
        return template.replace("{{uid}}", uid).replace(
            "{{payload}}", json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":")),
        )
