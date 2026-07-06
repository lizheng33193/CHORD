from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.model_client import ModelClient
from app.runtime_skills.base import BaseSkill
from app.runtime_skills.comprehensive_agent import ComprehensiveProfileSkill
from app.runtime_skills.ops_advice_agent import OpsAdviceSkill
from app.runtime_skills.product_advice_agent import ProductAdviceSkill
from app.services.profile_dag.executor import ProfileDagExecutor
from app.services.profile_dag.node_registry import PROFILE_NODE_SPECS


STABLE_ADVICE_FIELDS = [
    "segment",
    "segment_name",
    "overall_risk",
    "overall_value",
    "confidence",
    "data_completeness",
    "behavior_tags",
    "financial_tags",
]


class _FakeSkill(BaseSkill):
    def __init__(self, *, name: str, stage: int, result: dict[str, Any]) -> None:
        self.name = name
        self.stage = stage
        self.depends_on: list[str] = []
        self._result = result

    def analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]:
        structured = dict(self._result.get("structured_result") or {})
        structured.setdefault("uid", uid)
        return {
            **self._result,
            "structured_result": structured,
        }


def _make_executor(monkeypatch) -> ProfileDagExecutor:
    monkeypatch.setattr(settings, "model_mode", "mock")
    model_client = ModelClient()
    model_client.mode = "mock"

    skill_map = {
        "app_profile": _FakeSkill(
            name="app_profile",
            stage=0,
            result={
                "summary": "App summary",
                "structured_result": {
                    "status": "ok",
                    "summary": "App summary",
                    "activity_level": "high",
                    "metrics": {
                        "active_days_30d": 24,
                        "consumption_ability_level": "high",
                        "financial_maturity_level": "banked",
                        "multi_loan_risk_level": "low",
                    },
                    "tags": ["app-banked", "app-active"],
                },
                "charts": [],
                "report_markdown": "",
            },
        ),
        "behavior_profile": _FakeSkill(
            name="behavior_profile",
            stage=0,
            result={
                "summary": "Behavior summary",
                "structured_result": {
                    "status": "ok",
                    "summary": "Behavior summary",
                    "engagement_level": "deep",
                    "metrics": {
                        "engagement_score": 80,
                        "repayment_willingness_level": "high",
                        "churn_risk_level": "low",
                        "product_sensitivity_level": "medium",
                    },
                    "tags": ["behavior-deep", "behavior-stable"],
                },
                "charts": [],
                "report_markdown": "",
            },
        ),
        "credit_profile": _FakeSkill(
            name="credit_profile",
            stage=0,
            result={
                "summary": "Credit summary",
                "structured_result": {
                    "status": "ok",
                    "summary": "Credit summary",
                    "metrics": {
                        "risk_level": "low",
                        "credit_stability_level": "high",
                        "debt_pressure_level": "low",
                    },
                    "tags": ["credit-low-risk", "credit-stable"],
                },
                "charts": [],
                "report_markdown": "",
            },
        ),
        "comprehensive_profile": ComprehensiveProfileSkill(model_client),
        "product_advice": ProductAdviceSkill(model_client),
        "ops_advice": OpsAdviceSkill(model_client),
    }
    return ProfileDagExecutor(node_specs=PROFILE_NODE_SPECS, skill_map=skill_map)


def test_real_dag_emits_stable_comprehensive_to_advice_contract(monkeypatch):
    executor = _make_executor(monkeypatch)

    _, snapshots = executor.run(
        uids=["U1"],
        requested_modules=["product", "ops"],
        application_time="2026-04-15T12:00:00",
        country_code="mx",
        strict_data_mode=True,
        source="test",
    )
    outputs = snapshots[0].module_outputs

    comprehensive_sr = outputs["comprehensive"]["structured_result"]
    metrics = comprehensive_sr["metrics"]

    for field in STABLE_ADVICE_FIELDS:
        assert field in comprehensive_sr
        assert field in metrics
        assert comprehensive_sr[field] == metrics[field]

    product_sr = outputs["product"]["structured_result"]
    ops_sr = outputs["ops"]["structured_result"]

    assert product_sr["missing_comprehensive_advice_fields"] == []
    assert product_sr["used_default_advice_inputs"] is False
    assert ops_sr["missing_comprehensive_advice_fields"] == []
    assert ops_sr["used_default_advice_inputs"] is False
