from __future__ import annotations

import unittest
from pathlib import Path

from app.core.model_client import ModelClient
from app.runtime_skills.product_advice.contracts import build_product_advice_run_context
from app.runtime_skills.product_advice.data_access import ProductAdviceUpstreamProvider
from app.runtime_skills.product_advice.decision_engine import ProductAdviceDecisionEngine
from app.runtime_skills.product_advice.explainer import ProductAdviceExplainer
from app.runtime_skills.product_advice.feature_builder import ProductAdviceFeatureBuilder


def _comp_result(segment="S2", overall_risk="中低", overall_value="中高", churn="低", status="ok"):
    return {
        "structured_result": {
            "uid": "U1",
            "status": status,
            "metrics": {
                "recommended_segment": segment,
                "segment_name": "稳健经营客",
                "overall_risk": overall_risk,
                "overall_value": overall_value,
                "behavior_tags": {"churn_risk": churn, "best_contact_channel": "WhatsApp",
                                  "best_contact_time": "晚间19-21点", "product_activity": "★★★★☆"},
                "financial_tags": {"multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高"},
                "confidence": "高",
                "data_completeness": {"skill1_available": True, "skill2_available": True, "skill3_available": True},
            },
        },
    }


class ProductAdviceDataAccessTests(unittest.TestCase):
    def test_fetch_happy(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result=_comp_result())
        self.assertEqual(bundle["data_status"], "ok")
        self.assertEqual(bundle["segment"], "S2")
        self.assertEqual(bundle["behavior_tags"]["churn_risk"], "低")

    def test_fetch_missing_when_empty(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch("U1", ctx, comprehensive_result={})
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_status_not_ok(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(status="data_missing")
        )
        self.assertEqual(bundle["data_status"], "missing")

    def test_fetch_missing_when_segment_invalid(self):
        ctx = build_product_advice_run_context("U1")
        bundle = ProductAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(segment="X9")
        )
        self.assertEqual(bundle["data_status"], "invalid_segment")


class ProductAdviceFeatureBuilderTests(unittest.TestCase):
    def test_build_normalizes(self):
        ctx = build_product_advice_run_context("U1")
        upstream = ProductAdviceUpstreamProvider().fetch(
            "U1", ctx, comprehensive_result=_comp_result(segment="s2 ")
        )
        fb = ProductAdviceFeatureBuilder().build(upstream, ctx)
        self.assertEqual(fb["segment"], "S2")
        self.assertEqual(fb["multi_head_risk"], "中")
        self.assertEqual(fb["contact_channel"], "WhatsApp")


class ProductAdviceDecisionEngineTests(unittest.TestCase):
    def test_decide_s2(self):
        fb = {"segment": "S2", "overall_risk": "中低", "overall_value": "中高",
              "multi_head_risk": "中", "debt_pressure": "中", "borrowing_urgency": "高",
              "product_activity": "高", "contact_channel": "WhatsApp", "contact_time": "晚间19-21点"}
        ctx = build_product_advice_run_context("U1")
        decision = ProductAdviceDecisionEngine().decide(fb, ctx)
        self.assertEqual(decision["segment"], "S2")
        self.assertEqual(decision["renewal_strategy"]["action"], "续贷优惠")
        self.assertEqual(decision["recommended_channel"]["best_time"], "晚间19-21点")

    def test_decide_s5_no_renewal(self):
        fb = {"segment": "S5", "overall_risk": "高", "overall_value": "中",
              "multi_head_risk": "高", "debt_pressure": "高", "borrowing_urgency": "高",
              "product_activity": "中", "contact_channel": "SMS", "contact_time": "工作日"}
        decision = ProductAdviceDecisionEngine().decide(fb, build_product_advice_run_context("U1"))
        self.assertIn("不主动", decision["renewal_strategy"]["action"])
        self.assertIsNone(decision["credit_line_action"]["delta_pct_range"])

    def test_build_prompt_payload(self):
        fb = {"segment": "S1", "overall_risk": "低", "overall_value": "高",
              "multi_head_risk": "低", "debt_pressure": "低", "borrowing_urgency": "低",
              "product_activity": "高", "contact_channel": "WhatsApp", "contact_time": ""}
        eng = ProductAdviceDecisionEngine()
        decision = eng.decide(fb, build_product_advice_run_context("U1"))
        payload = eng.build_prompt_payload(fb, decision)
        self.assertEqual(payload["segment"], "S1")
        self.assertIn("renewal_strategy", payload)


class ProductAdviceExplainerTests(unittest.TestCase):
    def test_mock_mode_skips_llm(self):
        client = ModelClient()
        client.mode = "mock"
        client.model_name = "test-model"
        prompt_path = Path("app/prompts/product_advice_prompt.md")
        explainer = ProductAdviceExplainer(client, prompt_path)
        ctx = build_product_advice_run_context("U1")
        result = explainer.explain("U1", {"segment": "S2"}, {"segment": "S2"}, {"segment": "S2"}, ctx)
        self.assertEqual(result["status"], "model_mode_mock")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["payload"], {})


class ProductAdviceSkillTests(unittest.TestCase):
    def setUp(self):
        from app.runtime_skills.product_advice_agent import ProductAdviceSkill
        client = ModelClient()
        client.mode = "mock"
        self.skill = ProductAdviceSkill(client)

    def test_e2e_s2(self):
        out = self.skill.analyze("U1", comprehensive_profile_result=_comp_result(segment="S2"))
        self.assertIn("structured_result", out)
        sr = out["structured_result"]
        self.assertEqual(sr["status"], "ok")
        self.assertEqual(sr["segment"], "S2")
        self.assertEqual(sr["renewal_strategy"]["action"], "续贷优惠")
        self.assertIn("S2", sr["tags"])
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
