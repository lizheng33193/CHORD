from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.core.config import settings
from app.core.model_client import ModelClient
from app.repositories.base import BaseUserRepository
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.app_profile.assembler import AppPageAssembler
from app.runtime_skills.app_profile.contracts import build_app_run_context
from app.runtime_skills.app_profile.data_access import AppDataProvider
from app.runtime_skills.app_profile.decision_engine import AppDecisionEngine
from app.runtime_skills.app_profile.explainer import AppExplainer
from app.runtime_skills.app_profile.feature_builder import AppFeatureBuilder
from app.runtime_skills.app_profile_agent import AppProfileSkill
from app.services.orchestrator import AnalysisOrchestrator


SAMPLE_UID = "824812551379353600"
MISSING_UID = "uid_not_found_for_phase1_test"


class FakeDatabaseRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_type": "database_api",
            "source_file": f"warehouse://app_profile/{uid}",
            "apps": [
                {
                    "uid": uid,
                    "app_name": "Kueski",
                    "app_package": "com.kueski.app",
                    "first_install_time": 1772467899697,
                    "last_update_time": 1772467899697,
                    "gp_category": "Finance",
                    "ai_category_level_2_CN": "Loan",
                }
            ],
        }

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {}


class InvalidAppRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_file": f"broken://{uid}",
            "data_status": "invalid",
            "load_error": "broken_csv",
            "apps": [],
        }

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {}


class AppProfilePhase1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls._original_settings = {
            "data_dir": settings.data_dir,
            "app_source_dir": settings.app_source_dir,
            "app_by_uid_dir": settings.app_by_uid_dir,
            "behavior_source_dir": settings.behavior_source_dir,
            "behavior_by_uid_dir": settings.behavior_by_uid_dir,
            "credit_source_dir": settings.credit_source_dir,
            "credit_by_uid_dir": settings.credit_by_uid_dir,
        }
        temp_root = Path(cls._temp_dir.name)
        data_root = temp_root / "data"
        app_source_dir = data_root / "app" / "source"
        app_by_uid_dir = data_root / "app" / "by_uid"
        behavior_source_dir = data_root / "behavior" / "source"
        behavior_by_uid_dir = data_root / "behavior" / "by_uid"
        credit_source_dir = data_root / "credit" / "source"
        credit_by_uid_dir = data_root / "credit" / "by_uid"

        app_source_dir.mkdir(parents=True, exist_ok=True)
        app_by_uid_dir.mkdir(parents=True, exist_ok=True)
        behavior_source_dir.mkdir(parents=True, exist_ok=True)
        credit_source_dir.mkdir(parents=True, exist_ok=True)

        settings.data_dir = str(data_root)
        settings.app_source_dir = str(app_source_dir)
        settings.app_by_uid_dir = str(app_by_uid_dir)
        settings.behavior_source_dir = str(behavior_source_dir)
        settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
        settings.credit_source_dir = str(credit_source_dir)
        settings.credit_by_uid_dir = str(credit_by_uid_dir)

        cls._write_csv(
            app_by_uid_dir / f"{SAMPLE_UID}.csv",
            [
                "uid",
                "app_name",
                "app_package",
                "first_install_time",
                "last_update_time",
                "gp_category",
                "ai_category_level_2_CN",
            ],
            [
                {
                    "uid": SAMPLE_UID,
                    "app_name": "Kueski",
                    "app_package": "com.kueski.app",
                    "first_install_time": "1772467899697",
                    "last_update_time": "1772467899697",
                    "gp_category": "Finance",
                    "ai_category_level_2_CN": "Loan",
                },
                {
                    "uid": SAMPLE_UID,
                    "app_name": "Mercado Pago",
                    "app_package": "com.mercadopago.wallet",
                    "first_install_time": "1771467899697",
                    "last_update_time": "1772467899697",
                    "gp_category": "Finance",
                    "ai_category_level_2_CN": "Wallet",
                },
            ],
        )
        cls._seed_sample_files(data_root)
        cls.prompt_path = settings.resolve_path(f"{settings.prompt_dir}/app_profile_prompt.md")
        cls.repository = LocalUserRepository(allow_sample_fallback=False)
        cls.context = build_app_run_context(SAMPLE_UID)

    @classmethod
    def tearDownClass(cls) -> None:
        for key, value in cls._original_settings.items():
            setattr(settings, key, value)
        cls._temp_dir.cleanup()

    def _build_pipeline_objects(self) -> tuple[dict, dict, dict, dict]:
        provider = AppDataProvider(self.repository)
        raw_data = provider.fetch(SAMPLE_UID, self.context)
        feature_bundle = AppFeatureBuilder().build(raw_data, self.context)
        decision_result = AppDecisionEngine().decide(feature_bundle, self.context)
        prompt_payload = AppDecisionEngine().build_prompt_payload(feature_bundle, decision_result)
        return raw_data, feature_bundle, decision_result, prompt_payload

    def test_run_context_contract(self) -> None:
        context = build_app_run_context(SAMPLE_UID)
        self.assertEqual(
            set(context.keys()),
            {
                "uid",
                "country_code",
                "application_time",
                "trace_id",
                "source_preference",
                "enable_llm_explanation",
                "language",
                "channel",
            },
        )
        self.assertEqual(context["channel"], "api")

    def test_data_provider_local_contract(self) -> None:
        provider = AppDataProvider(self.repository)
        raw_data = provider.fetch(SAMPLE_UID, self.context)

        self.assertEqual(
            set(raw_data.keys()),
            {"uid", "country_code", "source_meta", "records", "data_status", "errors"},
        )
        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(
            set(raw_data["source_meta"].keys()),
            {"source_type", "origin_ref", "fetched_at", "trace_id"},
        )
        self.assertIsInstance(raw_data["records"], list)
        self.assertTrue(raw_data["records"])

    def test_data_provider_invalid_contract(self) -> None:
        context = build_app_run_context("broken-uid")
        provider = AppDataProvider(InvalidAppRepository())
        raw_data = provider.fetch("broken-uid", context)

        self.assertEqual(raw_data["data_status"], "invalid")
        self.assertEqual(raw_data["records"], [])
        self.assertIn("broken_csv", raw_data["errors"][0])

    def test_data_provider_fake_database_shape(self) -> None:
        local_shape = AppDataProvider(self.repository).fetch(SAMPLE_UID, self.context)
        db_shape = AppDataProvider(FakeDatabaseRepository()).fetch(SAMPLE_UID, self.context)

        self.assertEqual(set(local_shape.keys()), set(db_shape.keys()))
        self.assertEqual(set(local_shape["source_meta"].keys()), set(db_shape["source_meta"].keys()))
        self.assertEqual(db_shape["source_meta"]["source_type"], "database_api")
        self.assertEqual(db_shape["data_status"], "ok")

    def test_feature_bundle_contract(self) -> None:
        raw_data, feature_bundle, _, _ = self._build_pipeline_objects()
        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(
            set(feature_bundle.keys()),
            {
                "uid",
                "country_code",
                "application_time",
                "normalized_apps",
                "aggregate_features",
                "signal_features",
                "evidence_features",
                "visual_features",
                "feature_status",
                "errors",
            },
        )
        self.assertNotIn("_prompt_payload", feature_bundle)
        self.assertIn("raw_counts", feature_bundle["evidence_features"])
        self.assertGreater(feature_bundle["evidence_features"]["raw_counts"]["row_count"], 0)

    def test_decision_result_contract(self) -> None:
        _, feature_bundle, decision_result, _ = self._build_pipeline_objects()
        self.assertEqual(
            set(decision_result.keys()),
            {
                "uid",
                "country_code",
                "decision_status",
                "summary_seed",
                "app_insight_seed",
                "activity_level",
                "risk_assessment",
                "financial_maturity",
                "consumption_profile",
                "metrics",
                "tags_rule",
                "recommendation",
                "visuals",
                "timeline",
                "errors",
            },
        )
        self.assertEqual(decision_result["decision_status"], "ok")
        self.assertIn(decision_result["risk_assessment"]["level"], {"high", "medium", "low"})

    def test_prompt_payload_built_from_feature_and_decision_only(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        self.assertIn("default_inference", prompt_payload)
        self.assertEqual(prompt_payload["uid"], feature_bundle["uid"])
        self.assertEqual(
            prompt_payload["default_inference"]["multi_loan_risk_level"],
            decision_result["risk_assessment"]["level"],
        )

    def test_explainer_mock_status(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        model_client = ModelClient()
        model_client.mode = "mock"
        explainer = AppExplainer(model_client, self.prompt_path)

        result = explainer.explain(
            SAMPLE_UID,
            feature_bundle,
            decision_result,
            prompt_payload,
            self.context,
        )
        self.assertEqual(result["explanation_status"], "skipped")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["model_trace"]["fallback_reason"], "model_mode_mock")

    def test_explainer_model_unavailable_contract(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        model_client = ModelClient()
        model_client.mode = "vertex"
        model_client.generate_structured = Mock(
            return_value={
                "status": "model_unavailable",
                "model_name": "fake-model",
                "structured_result": {"status": "model_unavailable", "model_error": "dependency_missing"},
            }
        )
        explainer = AppExplainer(model_client, Path("missing_prompt.md"))

        result = explainer.explain(
            SAMPLE_UID,
            feature_bundle,
            decision_result,
            prompt_payload,
            self.context,
        )
        self.assertEqual(result["explanation_status"], "model_unavailable")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["model_trace"]["fallback_reason"], "dependency_missing")

    def test_explainer_skipped_when_disabled(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        model_client = ModelClient()
        explainer = AppExplainer(model_client, self.prompt_path)
        context = dict(self.context)
        context["enable_llm_explanation"] = False

        result = explainer.explain(
            SAMPLE_UID,
            feature_bundle,
            decision_result,
            prompt_payload,
            context,
        )
        self.assertEqual(result["explanation_status"], "skipped")
        self.assertFalse(result["used_llm"])

    def test_page_assembler_contract(self) -> None:
        raw_data, feature_bundle, decision_result, _ = self._build_pipeline_objects()
        assembler = AppPageAssembler(ModelClient())
        fallback_structured = assembler.build_fallback_structured(
            SAMPLE_UID,
            raw_data,
            feature_bundle,
            decision_result,
        )
        explanation_result = {
            "uid": SAMPLE_UID,
            "country_code": self.context["country_code"],
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
                "mode": "mock",
                "used_llm": False,
                "model_name": "mock-model",
                "fallback_reason": "model_mode_mock",
            },
            "errors": [],
        }
        page = assembler.assemble(SAMPLE_UID, fallback_structured, explanation_result)

        self.assertEqual(set(page.keys()), {"summary", "structured_result", "charts", "report_markdown"})
        self.assertEqual(page["structured_result"]["status"], "ok")
        self.assertEqual(len(page["charts"]), 3)

    def test_app_skill_regression_sample_uid(self) -> None:
        model_client = ModelClient()
        model_client.mode = "mock"
        skill = AppProfileSkill(model_client)
        result = skill.analyze(SAMPLE_UID, repository=self.repository)

        self.assertEqual(set(result.keys()), {"summary", "structured_result", "charts", "report_markdown"})
        self.assertEqual(len(result["charts"]), 3)
        self.assertEqual(
            [chart["title"] for chart in result["charts"]],
            [
                "Installed Apps Category Share",
                "Install Time Distribution",
                "Risk / Maturity / Consumption Signals",
            ],
        )
        self.assertIn("metrics", result["structured_result"])
        self.assertFalse(result["structured_result"]["model_trace"]["used_llm"])

    def test_app_skill_missing_uid_path(self) -> None:
        model_client = ModelClient()
        model_client.mode = "mock"
        skill = AppProfileSkill(model_client)
        result = skill.analyze(MISSING_UID, repository=self.repository)

        self.assertEqual(result["structured_result"]["status"], "data_missing")
        self.assertEqual(result["charts"], [])
        self.assertTrue(result["report_markdown"])

    def test_app_skill_model_unavailable_path_still_renders(self) -> None:
        model_client = ModelClient()
        model_client.mode = "vertex"
        model_client.generate_structured = Mock(
            return_value={
                "status": "model_unavailable",
                "model_name": "fake-model",
                "structured_result": {"status": "model_unavailable", "model_error": "dependency_missing"},
            }
        )
        skill = AppProfileSkill(model_client)
        result = skill.analyze(SAMPLE_UID, repository=self.repository)

        self.assertEqual(result["structured_result"]["status"], "model_unavailable")
        self.assertEqual(len(result["charts"]), 3)
        self.assertTrue(result["report_markdown"])
        self.assertFalse(result["structured_result"]["model_trace"]["used_llm"])

    def test_orchestrator_integration_regression(self) -> None:
        original_mode = settings.model_mode
        original_name = settings.model_name
        original_gemini = settings.gemini_model
        try:
            settings.model_mode = "mock"
            settings.model_name = "mock-model"
            settings.gemini_model = "mock-model"
            orchestrator = AnalysisOrchestrator()
            response = orchestrator.analyze([SAMPLE_UID])
        finally:
            settings.model_mode = original_mode
            settings.model_name = original_name
            settings.gemini_model = original_gemini

        self.assertEqual(len(response.results), 1)
        result = response.results[0]
        self.assertEqual(result.uid, SAMPLE_UID)
        self.assertTrue(result.app_profile.structured_result)

    @staticmethod
    def _seed_sample_files(data_root: Path) -> None:
        AppProfilePhase1Tests._write_csv(
            data_root / "sample_behavior_data.csv",
            ["uid", "avg_session_minutes", "login_days_30d", "purchase_preference"],
            [
                {
                    "uid": "user_001",
                    "avg_session_minutes": "52",
                    "login_days_30d": "27",
                    "purchase_preference": "premium_quality",
                }
            ],
        )
        (data_root / "sample_credit_data.json").write_text(
            json.dumps(
                [
                    {
                        "uid": "user_001",
                        "credit_score_band": "A",
                        "repayment_status": "stable",
                        "risk_level": "low",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
