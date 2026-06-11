"""Explanation layer for the Credit profile pipeline."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.credit_profile.contracts import (
    CreditDecisionResult,
    CreditExplanationResult,
    CreditFeatureBundle,
    CreditRunContext,
)


class CreditExplainer:
    """Generate LLM explanation fields on top of deterministic Credit decisions."""

    def __init__(
        self,
        model_client: ModelClient,
        prompt_paths: dict[str, Path] | Path | None = None,
        *,
        prompt_path: Path | None = None,
    ) -> None:
        self.model_client = model_client
        if prompt_paths is None and prompt_path is not None:
            prompt_paths = prompt_path
        if prompt_paths is None:
            raise TypeError(
                "CreditExplainer requires prompt_paths (dict[str, Path]) "
                "or prompt_path (Path) keyword argument."
            )
        if isinstance(prompt_paths, dict):
            self.prompt_paths: dict[str, Path] = {k: Path(v) for k, v in prompt_paths.items()}
        else:
            self.prompt_paths = {"buro": Path(prompt_paths), "risk_features": Path(prompt_paths)}
        assert "buro" in self.prompt_paths, "Credit explainer 必须配置 buro prompt 模板"
        assert "risk_features" in self.prompt_paths, "Credit explainer 必须配置 risk_features prompt 模板"
        self.prompt_path = self.prompt_paths["buro"]

    def explain(
        self,
        uid: str,
        _feature_bundle: CreditFeatureBundle,
        _decision_result: CreditDecisionResult,
        prompt_payload: dict[str, Any],
        context: CreditRunContext,
    ) -> CreditExplanationResult:
        country_code = context["country_code"]
        profile_mode = context.get("profile_mode", "buro")
        active_prompt_path = self.prompt_paths.get(profile_mode, self.prompt_paths["buro"])
        if not context.get("enable_llm_explanation", True):
            return self._build_skipped_result(uid, country_code, "llm_explanation_disabled")

        if self.model_client.mode == "mock":
            return self._build_skipped_result(uid, country_code, "model_mode_mock")

        prompt = self._build_prompt(uid, self._build_llm_prompt_input(prompt_payload), active_prompt_path)
        model_result = self.model_client.generate_structured(
            skill_name="credit_profile",
            prompt=prompt,
            fallback_result=self._build_fallback_payload(),
            response_schema=self._build_llm_response_schema(),
            route_key="credit_profile.explainer",
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
            "evidence_patch": self._build_evidence_patch(payload, accepted_llm=accepted_llm),
            "report_markdown": str(payload.get("report_markdown", "") or ""),
            "model_trace": self._build_model_trace(
                model_result,
                fallback_reason,
                accepted_llm=accepted_llm,
            ),
            "errors": [],
        }

    def _build_evidence_patch(
        self, payload: dict[str, Any], *, accepted_llm: bool,
    ) -> dict[str, Any]:
        """合并 LLM evidence 并强制把顶层 summary/report_markdown 注入前端展示槽位。

        前端 `CreditPanel` 读 `evidence.llm_credit_profile.credit_summary`。
        若 LLM 严格按嵌套路径返回了该字段，merge 会保留；否则用顶层 summary 兜底，
        避免规则引擎模板（_build_credit_summary_text）遮蔽 LLM 解释文本。
        """
        evidence = payload.get("evidence", {}) if isinstance(payload.get("evidence"), dict) else {}
        patch: dict[str, Any] = dict(evidence)

        if accepted_llm:
            top_summary = str(payload.get("summary", "") or "").strip()
            top_report = str(payload.get("report_markdown", "") or "").strip()

            llm_credit = patch.get("llm_credit_profile")
            if not isinstance(llm_credit, dict):
                llm_credit = {}
            if not str(llm_credit.get("credit_summary", "") or "").strip():
                llm_credit["credit_summary"] = top_summary or top_report
            patch["llm_credit_profile"] = llm_credit

        return patch

    def _build_llm_prompt_input(self, prompt_payload: dict[str, Any]) -> dict[str, Any]:
        """Trim oversized fields from credit prompt payload to reduce LLM token cost.

        Keeps structured summaries (summary, delinquency, inquiries, risk_flags)
        but caps account_details to 10 entries and removes raw bulk data.
        """
        if not isinstance(prompt_payload, dict):
            return {}

        trimmed = deepcopy(prompt_payload)

        # Cap account_details to 10 most recent entries
        account_details = trimmed.get("account_details")
        if isinstance(account_details, list) and len(account_details) > 10:
            # Sort by account_age_months ascending (newest first) if available
            try:
                account_details_sorted = sorted(
                    account_details,
                    key=lambda a: a.get("account_age_months", 9999) if isinstance(a, dict) else 9999,
                )
                trimmed["account_details"] = account_details_sorted[:10]
            except (TypeError, ValueError):
                trimmed["account_details"] = account_details[:10]

        # Remove raw bulk data fields that waste tokens
        for raw_field in ("raw_credit_json", "raw_report", "raw_credit_data", "raw_json"):
            trimmed.pop(raw_field, None)

        return trimmed

    def _build_prompt(self, uid: str, prompt_input: dict[str, Any], prompt_path: Path | None = None) -> str:
        template = self._load_prompt_template(prompt_path)
        return template.replace("{{uid}}", uid).replace(
            "{{credit_data}}",
            json.dumps(prompt_input, ensure_ascii=False, separators=(",", ":")),
        )

    def _load_prompt_template(self, prompt_path: Path | None = None) -> str:
        path = prompt_path or self.prompt_path
        if not path.exists():
            return "Credit profile prompt missing. uid={{uid}} credit_data={{credit_data}}"
        return path.read_text(encoding="utf-8")

    def _build_llm_response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "object"},
                "report_markdown": {"type": "string"},
            },
        }

    def _build_fallback_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "summary": "",
            "tags": [],
            "evidence": {},
            "report_markdown": "",
        }

    def _build_skipped_result(
        self,
        uid: str,
        country_code: str,
        fallback_reason: str,
    ) -> CreditExplanationResult:
        return {
            "uid": uid,
            "country_code": country_code,
            "explanation_status": "skipped",
            "used_llm": False,
            "summary": "",
            "tags": [],
            "evidence_patch": {},
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
        evidence = payload.get("evidence", {})
        llm_credit_profile = evidence.get("llm_credit_profile", {}) if isinstance(evidence, dict) else {}
        return bool(
            str(payload.get("summary", "") or "").strip()
            or str(payload.get("report_markdown", "") or "").strip()
            or payload.get("tags")
            or payload.get("evidence")
            or str(llm_credit_profile.get("credit_summary", "") or "").strip()
        )

    def _is_complete_payload(self, payload: dict[str, Any]) -> bool:
        evidence = payload.get("evidence", {})
        llm_credit_profile = evidence.get("llm_credit_profile", {}) if isinstance(evidence, dict) else {}
        return bool(
            (
                str(payload.get("summary", "") or "").strip()
                or str(llm_credit_profile.get("credit_summary", "") or "").strip()
            )
            and str(payload.get("report_markdown", "") or "").strip()
        )
