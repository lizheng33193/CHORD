"""Phase-1 unit tests for the six-step comprehensive pipeline."""
from __future__ import annotations

import pytest

from app.runtime_skills.comprehensive import (
    ComprehensiveDecisionResult,
    ComprehensiveExplanationResult,
    ComprehensiveFeatureBundle,
    ComprehensivePageResult,
    ComprehensiveRunContext,
    ComprehensiveUpstreamBundle,
    build_comprehensive_run_context,
)


class TestComprehensiveContracts:
    def test_build_run_context_returns_required_keys(self) -> None:
        ctx = build_comprehensive_run_context("uid-1", application_time=None)
        assert ctx["uid"] == "uid-1"
        assert ctx["country_code"]
        assert ctx["application_time"]
        assert ctx["trace_id"] == ""
        assert isinstance(ctx["enable_llm_explanation"], bool)
        assert ctx["language"]
        assert ctx["channel"]

    def test_typeddicts_are_importable(self) -> None:
        for cls in (
            ComprehensiveRunContext,
            ComprehensiveUpstreamBundle,
            ComprehensiveFeatureBundle,
            ComprehensiveDecisionResult,
            ComprehensiveExplanationResult,
            ComprehensivePageResult,
        ):
            assert cls is not None


from app.runtime_skills.comprehensive import ComprehensiveUpstreamProvider


def _ok_skill_result(name: str) -> dict:
    return {
        "status": "ok",
        "structured_result": {"summary": f"{name} ok"},
    }


def _missing_skill_result() -> dict:
    return {"status": "data_missing", "structured_result": {}}


class TestComprehensiveUpstreamProvider:
    def setup_method(self) -> None:
        self.provider = ComprehensiveUpstreamProvider()
        self.context = build_comprehensive_run_context("uid-2")

    def test_all_three_ok(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_ok_skill_result("app"),
            behavior_result=_ok_skill_result("behavior"),
            credit_result=_ok_skill_result("credit"),
        )
        assert bundle["ok_count"] == 3
        assert bundle["missing_modules"] == []
        assert bundle["data_status"] == "ok"

    def test_partial_missing(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_ok_skill_result("app"),
            behavior_result=_missing_skill_result(),
            credit_result=_ok_skill_result("credit"),
        )
        assert bundle["ok_count"] == 2
        assert "behavior_profile" in bundle["missing_modules"]
        assert bundle["data_status"] == "ok"

    def test_all_missing_triggers_data_missing(self) -> None:
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=_missing_skill_result(),
            behavior_result=_missing_skill_result(),
            credit_result=_missing_skill_result(),
        )
        assert bundle["ok_count"] == 0
        assert bundle["data_status"] == "data_missing"
        assert set(bundle["missing_modules"]) == {
            "app_profile", "behavior_profile", "credit_profile",
        }

    def test_non_dict_structured_is_tolerated(self) -> None:
        bad = {"status": "ok", "structured_result": "not-a-dict"}
        bundle = self.provider.fetch(
            "uid-2", self.context,
            app_result=bad,
            behavior_result=_ok_skill_result("behavior"),
            credit_result=_ok_skill_result("credit"),
        )
        assert "app_profile" in bundle["missing_modules"]
        assert bundle["ok_count"] == 2


from app.runtime_skills.comprehensive import ComprehensiveFeatureBuilder


def _bundle_all_ok(uid: str = "uid-3"):
    provider = ComprehensiveUpstreamProvider()
    ctx = build_comprehensive_run_context(uid)
    return provider.fetch(
        uid, ctx,
        app_result={"status": "ok", "structured_result": {
            "summary": "App summary",
            "activity_level": "high",
            "metrics": {"active_days_30d": 24, "consumption_ability_level": "high",
                        "financial_maturity_level": "banked", "multi_loan_risk_level": "low"},
            "tags": [],
        }},
        behavior_result={"status": "ok", "structured_result": {
            "summary": "Behavior summary",
            "engagement_level": "deep",
            "metrics": {"engagement_score": 80, "repayment_willingness_level": "high",
                        "churn_risk_level": "low", "product_sensitivity_level": "medium"},
            "tags": [],
        }},
        credit_result={"status": "ok", "structured_result": {
            "summary": "Credit summary",
            "status": "ok",
            "metrics": {"risk_level": "low", "credit_stability_level": "high",
                        "debt_pressure_level": "low"},
            "tags": [],
        }},
    )


class TestComprehensiveFeatureBuilder:
    def setup_method(self) -> None:
        self.builder = ComprehensiveFeatureBuilder()
        self.context = build_comprehensive_run_context("uid-3")

    def test_all_ok_produces_full_bundle(self) -> None:
        bundle = self.builder.build(_bundle_all_ok(), self.context)
        assert bundle["feature_status"] == "ok"
        assert 1 <= bundle["app_score"] <= 5
        assert 1 <= bundle["behavior_score"] <= 5
        assert 1 <= bundle["credit_score"] <= 5
        assert set(bundle["upstream_summaries"]) == {
            "app_profile", "behavior_profile", "credit_profile",
        }

    def test_missing_upstream_yields_zero_score_and_empty_metrics(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        upstream = provider.fetch(
            "uid-3", self.context,
            app_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
        )
        bundle = self.builder.build(upstream, self.context)
        assert bundle["behavior_metrics"] == {}
        assert bundle["behavior_score"] == 0

    def test_score_is_clamped_to_1_5_range(self) -> None:
        bundle = self.builder.build(_bundle_all_ok(), self.context)
        for s in (bundle["app_score"], bundle["behavior_score"], bundle["credit_score"]):
            assert 0 <= s <= 5


from app.runtime_skills.comprehensive import ComprehensiveDecisionEngine


class TestComprehensiveDecisionEngine:
    def setup_method(self) -> None:
        self.builder = ComprehensiveFeatureBuilder()
        self.engine = ComprehensiveDecisionEngine()
        self.context = build_comprehensive_run_context("uid-4")
        self.upstream = _bundle_all_ok("uid-4")
        self.feature = self.builder.build(self.upstream, self.context)

    def test_decision_status_ok_with_full_upstream(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        assert result["decision_status"] == "ok"
        assert result["segment"].startswith("S")
        assert result["overall_risk_level"] in {"low", "medium", "high", "unknown"}
        assert result["value_signal_level"] in {"low", "medium", "high"}
        assert result["confidence_level"] in {"low", "medium", "high"}

    def test_metrics_flattened_to_schema_shape(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        m = result["metrics"]
        assert "segment" in m
        assert "risk_level" in m
        assert "value_signal_level" in m
        assert "confidence_level" in m
        assert "dimension_scores" in m
        assert "conflict_count" in m

    def test_prompt_payload_keys(self) -> None:
        result = self.engine.decide(self.feature, self.upstream, self.context)
        payload = self.engine.build_prompt_payload(self.feature, result, self.upstream)
        assert "segment" in payload
        assert "missing_modules" in payload
        assert "upstream_summaries" in payload

    def test_partial_upstream_lowers_confidence(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        upstream = provider.fetch(
            "uid-4", self.context,
            app_result={"status": "ok", "structured_result": {"summary": "ok", "metrics": {}}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "data_missing", "structured_result": {}},
        )
        feature = self.builder.build(upstream, self.context)
        result = self.engine.decide(feature, upstream, self.context)
        assert result["confidence_level"] in {"low", "medium"}


from pathlib import Path
from unittest.mock import MagicMock

from app.runtime_skills.comprehensive import ComprehensiveExplainer


def _mk_mock_client(mode: str = "vertex", payload: dict | None = None, status: str = "ok"):
    client = MagicMock()
    client.mode = mode
    client.model_name = "gemini-3.1-pro-preview"
    client.generate_structured.return_value = {
        "status": status,
        "structured_result": payload if payload is not None else {},
        "model_name": "gemini-3.1-pro-preview",
        "prompt_preview": "test prompt...",
    }
    return client


class TestComprehensiveExplainer:
    def setup_method(self) -> None:
        self.context = build_comprehensive_run_context("uid-5")
        self.upstream = _bundle_all_ok("uid-5")
        self.feature = ComprehensiveFeatureBuilder().build(self.upstream, self.context)
        self.engine = ComprehensiveDecisionEngine()
        self.decision = self.engine.decide(self.feature, self.upstream, self.context)
        self.payload = self.engine.build_prompt_payload(self.feature, self.decision, self.upstream)
        self.prompt_path = Path("app/prompts/comprehensive_prompt.md")

    def test_mock_mode_skips_llm(self) -> None:
        client = _mk_mock_client(mode="mock")
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["used_llm"] is False
        assert result["explanation_status"] == "skipped"
        client.generate_structured.assert_not_called()

    def test_llm_ok_payload_adopted(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "LLM summary",
            "persona": "LLM persona",
            "tags_addon": ["t1", "t2", "t3", "t4"],
            "conflict_explanations": ["c1 polished"],
            "reasoning_texts": {"app": "r1", "behavior": "r2", "credit": "r3"},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["used_llm"] is True
        assert result["explanation_status"] == "ok"
        assert result["summary"] == "LLM summary"
        assert len(result["tags_addon"]) <= 3

    def test_empty_payload_marks_model_unavailable(self) -> None:
        client = _mk_mock_client(payload={})
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream, self.payload, self.context,
        )
        assert result["explanation_status"] == "model_unavailable"
        assert "empty_explanation_payload" in result["model_trace"]["fallback_reason"]

    def test_conflict_alignment_by_index(self) -> None:
        decision = dict(self.decision)
        decision["conflict_explanations"] = ["seedA", "seedB", "seedC"]
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": ["only-one"],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        result = explainer.explain(
            "uid-5", self.feature, decision, self.upstream, self.payload, self.context,
        )
        assert len(result["conflict_explanations"]) == 3
        assert result["conflict_explanations"][0] == "only-one"
        assert result["conflict_explanations"][1] == "seedB"
        assert result["conflict_explanations"][2] == "seedC"

    def test_missing_modules_renders_in_prompt(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": [],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        payload_with_missing = dict(self.payload)
        payload_with_missing["missing_modules"] = ["behavior_profile"]
        explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream,
            payload_with_missing, self.context,
        )
        sent_prompt = client.generate_structured.call_args.kwargs.get("prompt") \
            or client.generate_structured.call_args.args[0]
        assert "missing_modules" in sent_prompt
        assert "behavior_profile" in sent_prompt

    def test_missing_modules_empty_omits_line(self) -> None:
        client = _mk_mock_client(payload={
            "summary": "s", "persona": "p", "tags_addon": [],
            "conflict_explanations": [],
            "reasoning_texts": {},
        })
        explainer = ComprehensiveExplainer(client, self.prompt_path)
        payload_no_missing = dict(self.payload)
        payload_no_missing["missing_modules"] = []
        explainer.explain(
            "uid-5", self.feature, self.decision, self.upstream,
            payload_no_missing, self.context,
        )
        sent_prompt = client.generate_structured.call_args.kwargs.get("prompt") \
            or client.generate_structured.call_args.args[0]
        assert "- missing_modules:" not in sent_prompt


from app.runtime_skills.comprehensive import ComprehensivePageAssembler


class TestComprehensivePageAssembler:
    def setup_method(self) -> None:
        self.context = build_comprehensive_run_context("uid-6")
        self.upstream = _bundle_all_ok("uid-6")
        self.feature = ComprehensiveFeatureBuilder().build(self.upstream, self.context)
        self.engine = ComprehensiveDecisionEngine()
        self.decision = self.engine.decide(self.feature, self.upstream, self.context)
        self.client = _mk_mock_client(mode="mock")
        self.assembler = ComprehensivePageAssembler(self.client)

    def test_build_missing_output_returns_data_missing(self) -> None:
        provider = ComprehensiveUpstreamProvider()
        bad_upstream = provider.fetch(
            "uid-6", self.context,
            app_result={"status": "data_missing", "structured_result": {}},
            behavior_result={"status": "data_missing", "structured_result": {}},
            credit_result={"status": "data_missing", "structured_result": {}},
        )
        page = self.assembler.build_missing_output("uid-6", self.context, bad_upstream)
        assert page["structured_result"]["status"] == "data_missing"

    def test_build_fallback_structured_has_required_fields(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        assert fb["uid"] == "uid-6"
        assert "metrics" in fb
        assert "summary" in fb
        assert "tags" in fb

    def test_assemble_merges_llm_text(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        explanation = ComprehensiveExplanationResult(
            uid="uid-6",
            country_code=self.context["country_code"],
            explanation_status="ok",
            used_llm=True,
            summary="merged summary",
            persona="merged persona",
            tags_addon=["x_addon"],
            conflict_explanations=[],
            reasoning_texts={"app": "r"},
            model_trace={"mode": "vertex", "fallback_reason": ""},
            errors=[],
        )
        page = self.assembler.assemble("uid-6", fb, explanation)
        assert page["structured_result"]["summary"] == "merged summary"
        assert "x_addon" in page["structured_result"]["tags"]

    def test_tags_final_dedupe(self) -> None:
        fb = self.assembler.build_fallback_structured(
            "uid-6", self.feature, self.decision,
        )
        explanation = ComprehensiveExplanationResult(
            uid="uid-6", country_code=self.context["country_code"],
            explanation_status="ok", used_llm=True,
            summary="s", persona="p",
            tags_addon=fb["tags"][:1],  # 与 rule 重复
            conflict_explanations=[], reasoning_texts={},
            model_trace={"mode": "vertex", "fallback_reason": ""}, errors=[],
        )
        page = self.assembler.assemble("uid-6", fb, explanation)
        tags = page["structured_result"]["tags"]
        assert len(tags) == len(set(tags))


from app.runtime_skills.comprehensive_agent import ComprehensiveProfileSkill


class TestComprehensiveAgentE2E:
    def setup_method(self) -> None:
        self.client = _mk_mock_client(mode="mock")
        self.skill = ComprehensiveProfileSkill(self.client)

    def test_data_missing_path(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "data_missing", "structured_result": {}},
            behavior_profile_result={"status": "data_missing", "structured_result": {}},
            credit_profile_result={"status": "data_missing", "structured_result": {}},
        )
        assert result["structured_result"]["status"] == "data_missing"

    def test_partial_upstream_mock_mode_ok(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"active_days_30d": 30}}},
            behavior_profile_result={"status": "data_missing", "structured_result": {}},
            credit_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"risk_level": "low"}}},
        )
        assert result["structured_result"]["status"] == "ok"

    def test_full_upstream_mock_mode_ok(self) -> None:
        result = self.skill.analyze(
            "uid-7",
            app_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"active_days_30d": 25}}},
            behavior_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"engagement_score": 60}}},
            credit_profile_result={"status": "ok", "structured_result": {
                "summary": "ok", "metrics": {"risk_level": "low"}}},
        )
        assert result["structured_result"]["status"] == "ok"
        assert set(result.keys()) >= {"summary", "structured_result", "charts", "report_markdown"}
