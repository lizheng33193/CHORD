from __future__ import annotations

import unittest
from pathlib import Path

from app.core.model_client import ModelClient
from app.runtime_skills.ops_advice.contracts import build_ops_advice_run_context
from app.runtime_skills.ops_advice.data_access import OpsAdviceUpstreamProvider
from app.runtime_skills.ops_advice.decision_engine import OpsAdviceDecisionEngine
from app.runtime_skills.ops_advice.explainer import OpsAdviceExplainer
from app.runtime_skills.ops_advice.feature_builder import OpsAdviceFeatureBuilder


def _comp_result(segment="S2", overall_risk="中低", overall_value="中高", churn="低", status="ok"):
    return {
        "structured_result": {
            "uid": "U1",
            "status": status,
            "segment": segment,
            "segment_name": "稳健经营客",
            "overall_risk": overall_risk,
            "overall_value": overall_value,
            "behavior_tags": {"churn_risk": churn, "best_contact_channel": "WhatsApp",
                              "best_contact_time": "晚间19-21点", "product_activity": "★★★★☆"},
            "financial_tags": {"multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高"},
            "confidence": "高",
            "data_completeness": {
                "app": "available",
                "behavior": "available",
                "credit": "available",
                "overall": "complete",
            },
            "metrics": {
                "recommended_segment": segment,
                "segment_name": "稳健经营客",
                "overall_risk": overall_risk,
                "overall_value": overall_value,
                "behavior_tags": {"churn_risk": churn, "best_contact_channel": "WhatsApp",
                                  "best_contact_time": "晚间19-21点", "product_activity": "★★★★☆"},
                "financial_tags": {"multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高"},
                "confidence": "高",
                "data_completeness": {
                    "app": "available",
                    "behavior": "available",
                    "credit": "available",
                    "overall": "complete",
                },
            },
        },
    }


class OpsAdviceDataAccessTests(unittest.TestCase):
    def test_fetch_happy(self):
        ctx = build_ops_advice_run_context("U1")
        bundle = OpsAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result())
        self.assertEqual(bundle["data_status"], "ok")
        self.assertEqual(bundle["segment"], "S2")
        self.assertEqual(bundle["behavior_tags"]["churn_risk"], "低")
        self.assertEqual(bundle["missing_comprehensive_advice_fields"], [])
        self.assertFalse(bundle["used_default_advice_inputs"])

    def test_fetch_keeps_metrics_compatibility_when_top_level_missing(self):
        ctx = build_ops_advice_run_context("U1")
        comp = _comp_result()
        sr = comp["structured_result"]
        for field in (
            "segment",
            "segment_name",
            "overall_risk",
            "overall_value",
            "behavior_tags",
            "financial_tags",
            "confidence",
            "data_completeness",
        ):
            sr.pop(field, None)
        bundle = OpsAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=comp)
        self.assertEqual(bundle["data_status"], "ok")
        self.assertEqual(bundle["missing_comprehensive_advice_fields"], [])
        self.assertFalse(bundle["used_default_advice_inputs"])

    def test_fetch_missing_when_empty(self):
        ctx = build_ops_advice_run_context("U1")
        bundle = OpsAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result={})
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_status_not_ok(self):
        ctx = build_ops_advice_run_context("U1")
        bundle = OpsAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(status="data_missing")
        )
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_segment_invalid(self):
        ctx = build_ops_advice_run_context("U1")
        bundle = OpsAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(segment="X9")
        )
        self.assertEqual(bundle["data_status"], "invalid_segment")


class OpsAdviceFeatureBuilderTests(unittest.TestCase):
    def test_build_normalizes(self):
        ctx = build_ops_advice_run_context("U1")
        upstream = OpsAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(segment="s2 ")
        )
        fb = OpsAdviceFeatureBuilder().build(upstream, ctx)
        self.assertEqual(fb["segment"], "S2")
        self.assertEqual(fb["churn_risk"], "低")
        self.assertEqual(fb["contact_channel"], "WhatsApp")


class OpsAdviceDecisionEngineTests(unittest.TestCase):
    def test_decide_s2(self):
        fb = {"segment": "S2", "churn_risk": "低", "debt_pressure": "中",
              "multi_head_risk": "中", "contact_channel": "WhatsApp",
              "contact_time": "晚间19-21点", "overall_risk": "中低"}
        decision = OpsAdviceDecisionEngine().decide(fb, build_ops_advice_run_context("U1"))
        self.assertEqual(decision["segment"], "S2")
        self.assertEqual(decision["collection_strategy"]["intensity"], "soft")
        self.assertEqual(decision["churn_warning"]["level"], "无")

    def test_decide_s2_with_high_churn_escalates(self):
        fb = {"segment": "S2", "churn_risk": "高", "debt_pressure": "中",
              "multi_head_risk": "中", "contact_channel": "WhatsApp",
              "contact_time": "晚间", "overall_risk": "中低"}
        decision = OpsAdviceDecisionEngine().decide(fb, build_ops_advice_run_context("U1"))
        self.assertEqual(decision["churn_warning"]["level"], "轻")

    def test_decide_s5_strong_already_caps(self):
        fb = {"segment": "S5", "churn_risk": "高", "debt_pressure": "高",
              "multi_head_risk": "高", "contact_channel": "SMS",
              "contact_time": "工作日", "overall_risk": "高"}
        decision = OpsAdviceDecisionEngine().decide(fb, build_ops_advice_run_context("U1"))
        self.assertEqual(decision["churn_warning"]["level"], "强")

    def test_build_prompt_payload(self):
        fb = {"segment": "S4", "churn_risk": "高", "debt_pressure": "中",
              "multi_head_risk": "中", "contact_channel": "WhatsApp",
              "contact_time": "晚间", "overall_risk": "中"}
        eng = OpsAdviceDecisionEngine()
        decision = eng.decide(fb, build_ops_advice_run_context("U1"))
        payload = eng.build_prompt_payload(fb, decision)
        self.assertEqual(payload["segment"], "S4")
        self.assertIn("collection_strategy", payload)


class OpsAdviceExplainerTests(unittest.TestCase):
    def test_mock_mode_skips_llm(self):
        client = ModelClient()
        client.mode = "mock"
        client.model_name = "test-model"
        prompt_path = Path("app/prompts/ops_advice_prompt.md")
        explainer = OpsAdviceExplainer(client, prompt_path)
        ctx = build_ops_advice_run_context("U1")
        result = explainer.explain("U1", {"segment": "S4"}, {"segment": "S4"}, {"segment": "S4"}, ctx)
        self.assertEqual(result["status"], "model_mode_mock")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["payload"], {})


class OpsAdviceSkillTests(unittest.TestCase):
    def setUp(self):
        from app.runtime_skills.ops_advice_agent import OpsAdviceSkill
        client = ModelClient()
        client.mode = "mock"
        self.skill = OpsAdviceSkill(client)

    def test_e2e_s4(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment="S4", churn="高"))
        self.assertIn("structured_result", out)
        sr = out["structured_result"]
        self.assertEqual(sr["status"], "ok")
        self.assertEqual(sr["segment"], "S4")
        self.assertEqual(sr["collection_strategy"]["intensity"], "soft")
        self.assertEqual(sr["churn_warning"]["level"], "强")
        self.assertIn("S4", sr["tags"])
        self.assertEqual(sr["missing_comprehensive_advice_fields"], [])
        self.assertFalse(sr["used_default_advice_inputs"])
        self.assertEqual(out["charts"], [])
        self.assertTrue(out["report_markdown"].startswith("## "))
        from app.schemas.final_response import AgentOutput
        AgentOutput.model_validate(out)

    def test_e2e_each_segment(self):
        for seg in ("S1", "S2", "S3", "S4", "S5", "S6"):
            out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment=seg))
            self.assertEqual(out["structured_result"]["segment"], seg)
            self.assertEqual(out["structured_result"]["status"], "ok")

    def test_missing_upstream(self):
        out = self.skill.analyze("U1", comprehensive_profile_result={})
        self.assertEqual(out["structured_result"]["status"], "data_missing")
        self.assertIn("数据不足", out["summary"])

    def test_invalid_segment(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment="X9"))
        self.assertEqual(out["structured_result"]["status"], "data_missing")

    def test_model_trace_mock(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result())
        mt = out["structured_result"]["model_trace"]
        self.assertEqual(mt["mode"], "mock")
        self.assertFalse(mt["used_llm"])
        self.assertEqual(mt["fallback_reason"], "model_mode_mock")

    def test_model_trace_appends_contract_warning_without_overwriting_mock_reason(self):
        comp = _comp_result()
        comp["structured_result"].pop("confidence", None)
        comp["structured_result"]["metrics"].pop("confidence", None)
        out = self.skill.analyze("U1", comprehensive_profile_result=comp)
        sr = out["structured_result"]
        self.assertEqual(sr["missing_comprehensive_advice_fields"], ["confidence"])
        self.assertTrue(sr["used_default_advice_inputs"])
        self.assertIn("missing_comprehensive_advice_fields:confidence", sr["model_trace"]["fallback_reason"])
        self.assertIn("model_mode_mock", sr["model_trace"]["fallback_reason"])
