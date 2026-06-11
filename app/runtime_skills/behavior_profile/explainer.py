"""Dual LLM explanation layer for the Behavior profile pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.model_client import ModelClient
from app.runtime_skills.behavior_profile.contracts import (
    BehaviorDecisionResult,
    BehaviorExplanationResult,
    BehaviorFeatureBundle,
    BehaviorRunContext,
)


class BehaviorExplainer:
    """Generate profile and timeline LLM patches on top of deterministic Behavior decisions."""

    def __init__(
        self,
        model_client: ModelClient,
        profile_prompt_path: Path,
        timeline_prompt_path: Path,
    ) -> None:
        self.model_client = model_client
        self.profile_prompt_path = Path(profile_prompt_path)
        self.timeline_prompt_path = Path(timeline_prompt_path)

    def explain(
        self,
        uid: str,
        _feature_bundle: BehaviorFeatureBundle,
        _decision_result: BehaviorDecisionResult,
        prompt_payload: dict[str, Any],
        context: BehaviorRunContext,
    ) -> BehaviorExplanationResult:
        country_code = context["country_code"]
        if not context.get("enable_llm_explanation", True):
            return self._build_skipped_result(
                uid,
                country_code,
                "llm_explanation_disabled",
            )

        if self.model_client.mode == "mock":
            return self._build_skipped_result(uid, country_code, "model_mode_mock")

        profile_input = prompt_payload.get("behavior_profile_prompt_input", {})
        timeline_input = prompt_payload.get("behavior_timeline_prompt_input", {})

        profile_result = self._run_profile_chain(uid, profile_input)
        timeline_result = self._run_timeline_chain(uid, timeline_input)

        profile_payload = self._payload_as_dict(profile_result)
        timeline_payload = self._payload_as_dict(timeline_result)
        profile_used_llm = self._profile_payload_has_value(profile_payload) and profile_result.get(
            "status"
        ) == "ok"
        timeline_used_llm = self._timeline_payload_has_value(timeline_payload) and timeline_result.get(
            "status"
        ) == "ok"

        evidence_patch = self._build_evidence_patch(
            profile_payload,
            timeline_payload,
            profile_used_llm=profile_used_llm,
            timeline_used_llm=timeline_used_llm,
            profile_fallback_reason=self._build_model_fallback_reason(profile_result),
            timeline_fallback_reason=self._build_model_fallback_reason(timeline_result),
        )
        tags = self._collect_tags(profile_payload)
        summary = self._pick_summary(profile_payload, timeline_payload)
        report_markdown = str(profile_payload.get("report_markdown", "") or "")

        # Extract churn root cause from LLM output (default to no_clear_signal)
        raw_causes = profile_payload.get("churn_root_cause")
        if not raw_causes or not isinstance(raw_causes, list):
            evidence = profile_payload.get("evidence", {})
            if isinstance(evidence, dict):
                for key in ("llm_behavior_profile", "llm_profile", "behavior_profile_narrative"):
                    nested = evidence.get(key, {})
                    if isinstance(nested, dict) and isinstance(nested.get("churn_root_cause"), list):
                        raw_causes = nested["churn_root_cause"]
                        break
        churn_root_cause = (
            [str(c) for c in raw_causes if str(c).strip()]
            if isinstance(raw_causes, list) and raw_causes
            else ["no_clear_signal"]
        )

        explanation_status = self._resolve_explanation_status(
            profile_result_status=str(profile_result.get("status", "")),
            timeline_result_status=str(timeline_result.get("status", "")),
            profile_used_llm=profile_used_llm,
            timeline_used_llm=timeline_used_llm,
        )

        return {
            "uid": uid,
            "country_code": country_code,
            "explanation_status": explanation_status,
            "used_llm": bool(profile_used_llm or timeline_used_llm),
            "summary": summary,
            "tags": tags,
            "churn_root_cause": churn_root_cause,
            "evidence_patch": evidence_patch,
            "report_markdown": report_markdown,
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": bool(profile_used_llm or timeline_used_llm),
                "used_llm_profile": profile_used_llm,
                "used_llm_timeline": timeline_used_llm,
                "model_name": self.model_client.model_name,
                "fallback_reason": evidence_patch.get("fallback_reason", ""),
                "profile_status": str(profile_result.get("status", "")),
                "timeline_status": str(timeline_result.get("status", "")),
            },
            "errors": [],
        }

    def _run_profile_chain(self, uid: str, profile_input: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(
            self.profile_prompt_path,
            uid,
            profile_input,
        )
        return self.model_client.generate_structured(
            skill_name="behavior_profile_summary",
            prompt=prompt,
            fallback_result=self._build_profile_fallback_payload(),
            response_schema=self._build_profile_response_schema(),
            route_key="behavior_profile.explainer",
        )

    def _run_timeline_chain(self, uid: str, timeline_input: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(
            self.timeline_prompt_path,
            uid,
            timeline_input,
        )
        return self.model_client.generate_structured(
            skill_name="behavior_timeline_summary",
            prompt=prompt,
            fallback_result=self._build_timeline_fallback_payload(),
            response_schema=self._build_timeline_response_schema(),
            route_key="behavior_profile.timeline",
        )

    def _build_prompt(
        self,
        prompt_path: Path,
        uid: str,
        prompt_input: dict[str, Any],
    ) -> str:
        from app.country_packs.mx.behavior_profile import (
            MX_PAY_CYCLE_DESCRIPTION,
            MX_PAY_CYCLE_NAME,
            MX_PRIMARY_CHANNEL,
        )

        template = self._load_prompt_template(prompt_path)
        return (
            template.replace("{{uid}}", uid)
            .replace(
                "{{behavior_data}}",
                json.dumps(prompt_input, ensure_ascii=False, separators=(",", ":")),
            )
            .replace("{{pay_cycle_name}}", MX_PAY_CYCLE_NAME)
            .replace("{{primary_channel}}", MX_PRIMARY_CHANNEL)
            .replace("{{pay_cycle_description}}", MX_PAY_CYCLE_DESCRIPTION)
        )

    def _load_prompt_template(self, prompt_path: Path) -> str:
        if not prompt_path.exists():
            return "Behavior prompt missing. uid={{uid}} behavior_data={{behavior_data}}"
        return prompt_path.read_text(encoding="utf-8")

    def _build_profile_response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "report_markdown": {"type": "string"},
                "churn_root_cause": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "credit_limit_unmet",
                            "interest_perception_high",
                            "competitor_poaching",
                            "ux_friction",
                            "repayment_burden",
                            "no_clear_signal",
                        ],
                    },
                    "description": "1-2 probable churn root causes",
                },
                "evidence": {
                    "type": "object",
                    "properties": {
                        "behavior_profile_narrative": {"type": "object"},
                        "llm_behavior_profile": {"type": "object"},
                        "llm_profile": {"type": "object"},
                    },
                },
            },
            "required": ["summary", "tags", "report_markdown", "churn_root_cause", "evidence"],
        }

    def _build_timeline_response_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "evidence": {
                    "type": "object",
                    "properties": {
                        "timeline_narrative": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "sections": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "content": {"type": "string"},
                                        },
                                        "required": ["title", "content"],
                                    },
                                },
                                "insights": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["summary"],
                        },
                        "llm_timeline": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "key_events": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["summary"],
                        },
                        "timeline_insights": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["timeline_narrative"],
                },
            },
            "required": ["summary", "evidence"],
        }

    def _build_profile_fallback_payload(self) -> dict[str, Any]:
        return {
            "summary": "",
            "tags": [],
            "report_markdown": "",
            "evidence": {},
        }

    def _build_timeline_fallback_payload(self) -> dict[str, Any]:
        return {
            "summary": "",
            "evidence": {},
        }

    def _build_skipped_result(
        self,
        uid: str,
        country_code: str,
        fallback_reason: str,
    ) -> BehaviorExplanationResult:
        return {
            "uid": uid,
            "country_code": country_code,
            "explanation_status": "skipped",
            "used_llm": False,
            "summary": "",
            "tags": [],
            "churn_root_cause": ["no_clear_signal"],
            "evidence_patch": {
                "used_llm_profile": False,
                "used_llm_timeline": False,
                "fallback_reason": fallback_reason,
            },
            "report_markdown": "",
            "model_trace": {
                "mode": self.model_client.mode,
                "used_llm": False,
                "used_llm_profile": False,
                "used_llm_timeline": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": fallback_reason,
            },
            "errors": [],
        }

    def _build_model_fallback_reason(self, model_result: dict[str, Any]) -> str:
        if model_result.get("status") == "ok":
            return ""
        structured_result = model_result.get("structured_result", {})
        if isinstance(structured_result, dict) and structured_result.get("model_error"):
            return str(structured_result.get("model_error"))
        return str(model_result.get("status", "model_unavailable"))

    def _payload_as_dict(self, model_result: dict[str, Any]) -> dict[str, Any]:
        payload = model_result.get("structured_result", {})
        return payload if isinstance(payload, dict) else {}

    def _profile_payload_has_value(self, payload: dict[str, Any]) -> bool:
        evidence = payload.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        narrative = evidence.get("behavior_profile_narrative", {})
        llm_profile = evidence.get("llm_profile", {})
        llm_behavior_profile = evidence.get("llm_behavior_profile", {})
        return bool(
            str(payload.get("summary", "") or "").strip()
            or str(payload.get("report_markdown", "") or "").strip()
            or payload.get("tags")
            or str(narrative.get("behavior_summary", "") or "").strip()
            or str(llm_profile.get("behavior_summary", "") or "").strip()
            or str(llm_behavior_profile.get("behavior_summary", "") or "").strip()
        )

    def _timeline_payload_has_value(self, payload: dict[str, Any]) -> bool:
        evidence = payload.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}
        narrative = evidence.get("timeline_narrative", {})
        llm_timeline = evidence.get("llm_timeline", {})
        return bool(
            str(payload.get("summary", "") or "").strip()
            or str(narrative.get("summary", "") or "").strip()
            or narrative.get("sections")
            or narrative.get("insights")
            or llm_timeline
        )

    def _build_evidence_patch(
        self,
        profile_payload: dict[str, Any],
        timeline_payload: dict[str, Any],
        *,
        profile_used_llm: bool,
        timeline_used_llm: bool,
        profile_fallback_reason: str,
        timeline_fallback_reason: str,
    ) -> dict[str, Any]:
        profile_evidence = profile_payload.get("evidence", {})
        if not isinstance(profile_evidence, dict):
            profile_evidence = {}
        timeline_evidence = timeline_payload.get("evidence", {})
        if not isinstance(timeline_evidence, dict):
            timeline_evidence = {}

        fallback_reason = ""
        if not profile_used_llm and profile_fallback_reason:
            fallback_reason = f"profile:{profile_fallback_reason}"
        if not timeline_used_llm and timeline_fallback_reason:
            fallback_reason = (
                f"{fallback_reason};timeline:{timeline_fallback_reason}"
                if fallback_reason
                else f"timeline:{timeline_fallback_reason}"
            )

        merged = self._merge_dicts(profile_evidence, timeline_evidence)
        merged["used_llm_profile"] = profile_used_llm
        merged["used_llm_timeline"] = timeline_used_llm
        merged["fallback_reason"] = fallback_reason

        # 强制把 LLM 顶层文本注入前端读取的展示槽位，避免规则模板遮蔽 LLM 输出。
        # 前端读 evidence.behavior_profile_narrative.behavior_summary / business_advice，
        # 以及 evidence.llm_profile.behavior_summary / business_advice。
        # 若 LLM 严格按嵌套路径返回过这些字段，_merge_dicts 已合并；这里仅在缺失时补齐。
        if profile_used_llm:
            llm_top_summary = str(profile_payload.get("summary", "") or "").strip()
            llm_report_md = str(profile_payload.get("report_markdown", "") or "").strip()
            llm_business_advice = self._extract_business_advice(profile_payload)

            # 强制 LLM 优先（只要 LLM 输出非空就覆盖）。
            # 旧版 `if not narrative.get(...)` 的写法会被 evidence_seed 里的规则模板
            # 提前填充导致 LLM 输出永远进不来 → 前端漏出 5 句 banned 空话。
            narrative = merged.get("behavior_profile_narrative")
            if not isinstance(narrative, dict):
                narrative = {}
            if llm_top_summary or llm_report_md:
                narrative["behavior_summary"] = llm_top_summary or llm_report_md
            if llm_business_advice:
                narrative["business_advice"] = llm_business_advice
            merged["behavior_profile_narrative"] = narrative

            llm_profile = merged.get("llm_profile")
            if not isinstance(llm_profile, dict):
                llm_profile = {}
            if llm_top_summary or llm_report_md:
                llm_profile["behavior_summary"] = llm_top_summary or llm_report_md
            if llm_business_advice:
                llm_profile["business_advice"] = llm_business_advice
            merged["llm_profile"] = llm_profile

        return merged

    @staticmethod
    def _extract_business_advice(profile_payload: dict[str, Any]) -> str:
        """从 LLM payload 中提取 business_advice 文本（多路径兼容）。"""
        evidence = profile_payload.get("evidence", {})
        if isinstance(evidence, dict):
            for key in ("behavior_profile_narrative", "llm_profile", "llm_behavior_profile"):
                node = evidence.get(key)
                if isinstance(node, dict):
                    advice = str(node.get("business_advice", "") or "").strip()
                    if advice:
                        return advice
                    suggestions = node.get("strategy_suggestions")
                    if isinstance(suggestions, list) and suggestions:
                        return "\n".join(
                            f"{i + 1}. {str(s).strip()}"
                            for i, s in enumerate(suggestions)
                            if str(s).strip()
                        )
        return ""

    def _pick_summary(
        self,
        profile_payload: dict[str, Any],
        timeline_payload: dict[str, Any],
    ) -> str:
        profile_summary = str(profile_payload.get("summary", "") or "").strip()
        if profile_summary:
            return profile_summary
        timeline_summary = str(timeline_payload.get("summary", "") or "").strip()
        if timeline_summary:
            return timeline_summary
        return ""

    def _collect_tags(self, profile_payload: dict[str, Any]) -> list[str]:
        tags = profile_payload.get("tags", [])
        if not isinstance(tags, list):
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            cleaned = str(tag or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped

    def _resolve_explanation_status(
        self,
        *,
        profile_result_status: str,
        timeline_result_status: str,
        profile_used_llm: bool,
        timeline_used_llm: bool,
    ) -> str:
        if profile_used_llm and timeline_used_llm:
            return "ok"
        if profile_used_llm or timeline_used_llm:
            return "partial"
        if profile_result_status == "ok" or timeline_result_status == "ok":
            return "partial"
        return "model_unavailable"

    def _merge_dicts(
        self,
        base: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(dict(merged[key]), value)
            else:
                merged[key] = value
        return merged
