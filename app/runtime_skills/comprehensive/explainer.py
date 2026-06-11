"""LLM explanation layer for the comprehensive pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.comprehensive.contracts import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
)


_TAGS_ADDON_LIMIT = 3
_MISSING_PLACEHOLDER = "{{MISSING_MODULES_LINE}}"


class ComprehensiveExplainer:
    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = Path(prompt_path)
        self._template_cache: str | None = None

    def explain(
        self,
        uid: str,
        feature_bundle: ComprehensiveFeatureBundle,
        decision_result: ComprehensiveDecisionResult,
        upstream: ComprehensiveUpstreamBundle,
        prompt_payload: dict[str, Any],
        context: ComprehensiveRunContext,
    ) -> ComprehensiveExplanationResult:
        seed_conflicts = list(decision_result["conflict_explanations"])

        if self.model_client.mode == "mock":
            return self._build_skipped_result(
                uid, context, seed_conflicts,
                fallback_reason="model_mode_mock",
            )

        prompt = self._build_prompt(prompt_payload)
        response = self.model_client.generate_structured(
            skill_name="comprehensive_profile",
            prompt=prompt,
            fallback_result=self._build_fallback_payload(decision_result),
            route_key="comprehensive.explainer",
        )

        if response.get("status") != "ok":
            return self._build_unavailable_result(
                uid, context, seed_conflicts,
                fallback_reason=str(response.get("status", "model_unavailable")),
                response=response,
            )

        payload = response.get("structured_result", {})
        if not isinstance(payload, dict):
            payload = {}
        if not self._has_meaningful_payload(payload):
            return self._build_unavailable_result(
                uid, context, seed_conflicts,
                fallback_reason="empty_explanation_payload",
                response=response,
            )

        try:
            patched_conflicts = self._patch_conflict_explanations(
                seed_conflicts, payload.get("conflict_explanations") or [],
            )
            tags_addon = self._filter_tags_addon(
                payload.get("tags_addon") or [],
                set(decision_result["tags_rule"]),
            )
            summary = str(payload.get("summary") or "")
            persona = str(payload.get("persona") or "")
            reasoning = payload.get("reasoning_texts") or {}
            if not isinstance(reasoning, dict):
                reasoning = {}
            reasoning = {str(k): str(v) for k, v in reasoning.items()}
        except Exception as exc:  # noqa: BLE001
            return self._build_unavailable_result(
                uid, context, seed_conflicts,
                fallback_reason=f"schema_validation_failed: {exc}",
                response=response,
            )

        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="ok",
            used_llm=True,
            summary=summary,
            persona=persona,
            tags_addon=tags_addon,
            conflict_explanations=patched_conflicts,
            reasoning_texts=reasoning,
            model_trace=self._build_model_trace(response, fallback_reason=""),
            errors=[],
        )

    # --- prompt construction ---

    def _load_prompt_template(self) -> str:
        if self._template_cache is None:
            self._template_cache = self.prompt_path.read_text(encoding="utf-8")
        return self._template_cache

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        template = self._load_prompt_template()
        missing = payload.get("missing_modules") or []
        if missing:
            line = (
                f"- missing_modules: {', '.join(missing)}; "
                f"treat their metrics as absent rather than as low values"
            )
            rendered = template.replace(_MISSING_PLACEHOLDER, line)
        else:
            # 空时连同前导换行一起去掉
            rendered = template.replace("\n" + _MISSING_PLACEHOLDER, "")
            rendered = rendered.replace(_MISSING_PLACEHOLDER, "")
        return (
            f"{rendered}\n\n## Payload\n```json\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
        )

    # --- alignment helpers ---

    @staticmethod
    def _patch_conflict_explanations(
        seed: list[str], llm_returned: list[Any],
    ) -> list[str]:
        out: list[str] = []
        for i, seed_text in enumerate(seed):
            if i < len(llm_returned) and isinstance(llm_returned[i], str) and llm_returned[i].strip():
                out.append(llm_returned[i])
            else:
                out.append(seed_text)
        return out

    @staticmethod
    def _filter_tags_addon(raw: list[Any], rule_set: set[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in raw:
            if not isinstance(t, str):
                continue
            t = t.strip()
            if not t or t in rule_set or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= _TAGS_ADDON_LIMIT:
                break
        return out

    @staticmethod
    def _has_meaningful_payload(payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        keys = ("summary", "persona", "tags_addon", "conflict_explanations", "reasoning_texts")
        return any(payload.get(k) for k in keys)

    # --- result builders ---

    def _build_skipped_result(
        self, uid: str, context: ComprehensiveRunContext,
        seed_conflicts: list[str], *, fallback_reason: str,
    ) -> ComprehensiveExplanationResult:
        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="skipped",
            used_llm=False,
            summary="",
            persona="",
            tags_addon=[],
            conflict_explanations=list(seed_conflicts),
            reasoning_texts={},
            model_trace=self._build_model_trace(None, fallback_reason=fallback_reason),
            errors=[],
        )

    def _build_unavailable_result(
        self, uid: str, context: ComprehensiveRunContext,
        seed_conflicts: list[str], *, fallback_reason: str, response: Any,
    ) -> ComprehensiveExplanationResult:
        return ComprehensiveExplanationResult(
            uid=uid,
            country_code=context["country_code"],
            explanation_status="model_unavailable",
            used_llm=True,
            summary="",
            persona="",
            tags_addon=[],
            conflict_explanations=list(seed_conflicts),
            reasoning_texts={},
            model_trace=self._build_model_trace(response, fallback_reason=fallback_reason),
            errors=[fallback_reason],
        )

    def _build_model_trace(
        self, response: Any, *, fallback_reason: str,
    ) -> dict[str, Any]:
        model_name = self.model_client.model_name
        if isinstance(response, dict):
            model_name = str(response.get("model_name", model_name) or model_name)
        return {
            "mode": self.model_client.mode,
            "used_llm": not fallback_reason,
            "model_name": model_name,
            "fallback_reason": fallback_reason,
        }

    @staticmethod
    def _build_fallback_payload(
        decision_result: ComprehensiveDecisionResult,
    ) -> dict[str, Any]:
        """Fallback result passed to ModelClient.generate_structured."""
        return {
            "status": "ok",
            "summary": "",
            "persona": "",
            "tags_addon": [],
            "conflict_explanations": list(decision_result["conflict_explanations"]),
            "reasoning_texts": {},
        }
