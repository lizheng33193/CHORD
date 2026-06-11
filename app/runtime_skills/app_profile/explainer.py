"""Explanation layer for the App profile pipeline."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.core.model_client import ModelClient
from app.runtime_skills.app_profile.contracts import (
    AppDecisionResult,
    AppExplanationResult,
    AppFeatureBundle,
    AppRunContext,
)


logger = get_logger(__name__)


class AppExplainer:
    """Generate LLM explanation fields on top of deterministic App decisions."""

    def __init__(self, model_client: ModelClient, prompt_path: Path) -> None:
        self.model_client = model_client
        self.prompt_path = Path(prompt_path)

    def explain(
        self,
        uid: str,
        feature_bundle: AppFeatureBundle,
        decision_result: AppDecisionResult,
        prompt_payload: dict[str, Any],
        context: AppRunContext,
    ) -> AppExplanationResult:
        country_code = context["country_code"]
        if not context.get("enable_llm_explanation", True):
            return self._build_skipped_result(uid, country_code, "llm_explanation_disabled")

        if self.model_client.mode == "mock":
            return self._build_skipped_result(uid, country_code, "model_mode_mock")

        trimmed_payload = self._build_llm_prompt_input(prompt_payload)
        prompt = self._build_prompt(uid, trimmed_payload)
        logger.info(
            "App explainer prompt ready uid=%s prompt_chars=%s app_count=%s",
            uid,
            len(prompt),
            len(trimmed_payload.get("apps", [])) if isinstance(trimmed_payload.get("apps"), list) else 0,
        )

        model_result = self.model_client.generate_structured(
            skill_name="app_profile",
            prompt=prompt,
            fallback_result=self._build_fallback_payload(),
            response_schema=self._build_llm_response_schema(),
            route_key="app_profile.explainer",
        )
        payload = model_result.get("structured_result", {})
        if not isinstance(payload, dict):
            payload = {}

        fallback_reason = self._build_model_fallback_reason(model_result)
        explanation_status = "ok" if model_result.get("status") == "ok" else "model_unavailable"
        accepted_llm = explanation_status == "ok" and self._has_meaningful_payload(payload)
        if explanation_status == "ok" and not accepted_llm:
            explanation_status = "model_unavailable"
            fallback_reason = fallback_reason or "empty_explanation_payload"
        elif accepted_llm and not self._is_complete_payload(payload):
            explanation_status = "partial"

        logger.info(
            "App explainer complete uid=%s status=%s used_llm=%s",
            uid,
            explanation_status,
            accepted_llm,
        )
        return {
            "uid": uid,
            "country_code": country_code,
            "explanation_status": explanation_status,
            "used_llm": accepted_llm,
            "summary": str(payload.get("summary", "") or ""),
            "tags": [
                str(tag) for tag in payload.get("tags", []) if str(tag).strip()
            ]
            if isinstance(payload.get("tags"), list)
            else [],
            "app_insight": payload.get("app_insight", {}) if isinstance(payload.get("app_insight"), dict) else {},
            "reasoning_texts": {
                "risk_assessment_reasoning": self._nested_text(payload, "risk_assessment", "reasoning"),
                "financial_maturity_reasoning": self._nested_text(payload, "financial_maturity", "reasoning"),
                "consumption_profile_reasoning": self._nested_text(payload, "consumption_profile", "reasoning"),
                "recommendation_reasoning": decision_result.get("recommendation", {}).get("reason_seed", ""),
            },
            "report_markdown": str(payload.get("report_markdown", "") or ""),
            "model_trace": self._build_model_trace(
                model_result,
                fallback_reason,
                accepted_llm=accepted_llm,
            ),
            "errors": [],
        }

    def _build_prompt(self, uid: str, prompt_input: dict[str, Any]) -> str:
        template = self._load_prompt_template()
        return template.replace("{{uid}}", uid).replace(
            "{{app_data}}",
            json.dumps(prompt_input, ensure_ascii=False, separators=(",", ":")),
        )

    def _load_prompt_template(self) -> str:
        if not self.prompt_path.exists():
            return "App profile prompt missing. uid={{uid}} app_data={{app_data}}"
        return self.prompt_path.read_text(encoding="utf-8")

    def _build_llm_prompt_input(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(prompt_payload, dict):
            return {}

        trimmed = deepcopy(prompt_payload)
        max_apps = max(0, settings.app_profile_prompt_max_apps)
        max_detail = max(0, settings.app_profile_prompt_max_detail_apps)

        apps = trimmed.get("apps", [])
        if isinstance(apps, list):
            compacted: list[dict[str, Any]] = []
            for app in apps[:max_apps]:
                if not isinstance(app, dict):
                    continue
                compacted.append(
                    {
                        "app_name": app.get("app_name", ""),
                        "app_package": app.get("app_package", ""),
                        "localized_category": app.get("localized_category", ""),
                        "install_time_display": app.get("install_time_display", ""),
                        "last_update_time_display": app.get("last_update_time_display", ""),
                        "gp_category": app.get("gp_category", ""),
                        "ai_category_level_2_CN": app.get("ai_category_level_2_CN", ""),
                        "install_bucket": app.get("install_bucket", ""),
                        "days_since_install": app.get("days_since_install"),
                    }
                )
            trimmed["apps"] = compacted

        trimmed.pop("install_bucket_details", None)
        trimmed.pop("category_app_details", None)

        key_app_lists = trimmed.get("key_app_lists", {})
        if isinstance(key_app_lists, dict) and max_detail:
            for key, value in list(key_app_lists.items()):
                if isinstance(value, list):
                    key_app_lists[key] = value[: max(10, max_detail)]

        visual_defaults = trimmed.get("visual_defaults", {})
        if isinstance(visual_defaults, dict):
            visual_defaults.pop("progress_metric_explanations", None)

        return trimmed

    def _build_llm_response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "app_insight": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "risk_assessment": {
                    "type": "object",
                    "properties": {"reasoning": {"type": "string"}},
                },
                "financial_maturity": {
                    "type": "object",
                    "properties": {"reasoning": {"type": "string"}},
                },
                "consumption_profile": {
                    "type": "object",
                    "properties": {"reasoning": {"type": "string"}},
                },
                "report_markdown": {"type": "string"},
            },
        }

    def _build_fallback_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "summary": "",
            "tags": [],
            "app_insight": {},
            "risk_assessment": {"reasoning": ""},
            "financial_maturity": {"reasoning": ""},
            "consumption_profile": {"reasoning": ""},
            "report_markdown": "",
        }

    def _build_skipped_result(
        self,
        uid: str,
        country_code: str,
        fallback_reason: str,
    ) -> AppExplanationResult:
        return {
            "uid": uid,
            "country_code": country_code,
            "explanation_status": "skipped",
            "used_llm": False,
            "summary": "",
            "tags": [],
            "app_insight": {},
            "reasoning_texts": {
                "risk_assessment_reasoning": "",
                "financial_maturity_reasoning": "",
                "consumption_profile_reasoning": "",
                "recommendation_reasoning": "",
            },
            "report_markdown": "",
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": fallback_reason,
            },
            "errors": [],
        }

    def _build_model_trace(
        self,
        model_result: dict[str, Any],
        fallback_reason: str,
        *,
        accepted_llm: bool,
    ) -> dict[str, Any]:
        return {
            "mode": self.model_client.mode,
            "used_llm": bool(accepted_llm),
            "model_name": str(model_result.get("model_name", self.model_client.model_name) or ""),
            "fallback_reason": "" if accepted_llm else fallback_reason,
        }

    def _build_model_fallback_reason(self, model_result: dict[str, Any]) -> str:
        if model_result.get("status") == "ok":
            return ""
        structured_result = model_result.get("structured_result", {})
        if isinstance(structured_result, dict) and structured_result.get("model_error"):
            return str(structured_result.get("model_error"))
        return str(model_result.get("status", "model_unavailable"))

    def _has_meaningful_payload(self, payload: dict[str, Any]) -> bool:
        if str(payload.get("summary", "") or "").strip():
            return True
        if str(payload.get("report_markdown", "") or "").strip():
            return True
        if self._nested_text(payload, "risk_assessment", "reasoning"):
            return True
        if self._nested_text(payload, "financial_maturity", "reasoning"):
            return True
        if self._nested_text(payload, "consumption_profile", "reasoning"):
            return True
        app_insight = payload.get("app_insight", {})
        if isinstance(app_insight, dict) and (
            str(app_insight.get("summary", "") or "").strip()
            or app_insight.get("reasons")
            or app_insight.get("labels")
        ):
            return True
        return False

    def _is_complete_payload(self, payload: dict[str, Any]) -> bool:
        required_texts = [
            str(payload.get("summary", "") or "").strip(),
            str(payload.get("report_markdown", "") or "").strip(),
            self._nested_text(payload, "risk_assessment", "reasoning"),
            self._nested_text(payload, "financial_maturity", "reasoning"),
            self._nested_text(payload, "consumption_profile", "reasoning"),
        ]
        return all(required_texts)

    def _nested_text(self, payload: dict[str, Any], key: str, nested_key: str) -> str:
        nested = payload.get(key, {})
        if not isinstance(nested, dict):
            return ""
        return str(nested.get(nested_key, "") or "")
