"""Explainer layer for the Ops Advice pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.runtime_skills.ops_advice.contracts import (
    OpsAdviceDecisionResult,
    OpsAdviceExplanationResult,
    OpsAdviceFeatureBundle,
    OpsAdviceRunContext,
)


logger = get_logger(__name__)


class OpsAdviceExplainer:
    """Augment deterministic decisions with LLM-generated outreach scripts."""

    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = Path(prompt_path)

    def explain(
        self,
        uid: str,
        feature_bundle: OpsAdviceFeatureBundle,
        decision_result: OpsAdviceDecisionResult,
        prompt_payload: dict[str, Any],
        context: OpsAdviceRunContext,
    ) -> OpsAdviceExplanationResult:
        if self.model_client.mode == "mock":
            return self._skipped("model_mode_mock")

        prompt = self._build_prompt(uid, prompt_payload)
        fallback = {"outreach_script": [], "retention_pitch": "", "risk_warnings": []}
        result = self.model_client.generate_structured(
            skill_name="ops_advice",
            prompt=prompt,
            fallback_result=fallback,
            response_schema={
                "type": "object",
                "properties": {
                    "outreach_script": {"type": "array", "items": {"type": "string"}},
                    "retention_pitch": {"type": "string"},
                    "risk_warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
            route_key="ops_advice.explainer",
        )
        payload = result.get("structured_result", {}) if isinstance(result.get("structured_result"), dict) else {}
        has_content = (
            bool(payload.get("outreach_script"))
            or bool(str(payload.get("retention_pitch", "")).strip())
        )
        accepted = result.get("status") == "ok" and has_content
        status = "ok" if accepted else "model_unavailable"
        return {
            "status": status,
            "payload": payload if accepted else {},
            "fallback_reason": "" if accepted else str(result.get("status", "model_unavailable")),
            "used_llm": accepted,
            "model_name": str(result.get("model_name", self.model_client.model_name) or ""),
        }

    def _skipped(self, reason: str) -> OpsAdviceExplanationResult:
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
