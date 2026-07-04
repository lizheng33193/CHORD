from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import csv
from pathlib import Path
from unittest.mock import Mock

from app.core.config import settings
from app.core.model_client import ModelClient
from app.country_packs.credit_profile import load_credit_country_pack
from app.repositories.base import BaseUserRepository
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.credit_profile import (
    CreditDataProvider,
    CreditDecisionEngine,
    CreditExplainer,
    CreditFeatureBuilder,
    CreditPageAssembler,
)
from app.runtime_skills.credit_profile.contracts import (
    build_credit_run_context,
    build_empty_prepared_record,
)
from app.runtime_skills.credit_profile_agent import CreditProfileSkill
from app.scripts.credit_prepared_builder import (
    CREDIT_PREPARED_SCHEMA_VERSION,
    prepare_credit_record_from_csv_file,
)
from app.scripts.data_prep.credit_preparer import prepare_credit_prepared_json_directory
from app.services.orchestrator import AnalysisOrchestrator


SAMPLE_UID = "user_001"
REAL_UID = "824812551379353600"
MISSING_UID = "credit_uid_not_found_for_phase17_test"


class FakePreparedRepository(BaseUserRepository):
    def __init__(self, prepared_payload: dict[str, object]) -> None:
        self.prepared_payload = prepared_payload

    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return dict(self.prepared_payload)


class LegacySummaryRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_type": "database_api",
            "source_kind": "legacy_summary_json",
            "source_file": f"legacy://credit/{uid}.json",
            "credit_score_band": "B",
            "repayment_status": "normal",
            "risk_level": "medium",
        }


class InvalidCreditRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_file": f"broken://{uid}",
            "data_status": "invalid",
            "load_error": "broken_credit_json",
        }


class MissingCreditRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {}


class SchemaMismatchRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {}

    def get_credit_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "schema_version": CREDIT_PREPARED_SCHEMA_VERSION,
            "source_meta": {"source_type": "local_file"},
        }


class CreditProfilePhase17Tests(unittest.TestCase):
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
        credit_by_uid_dir.mkdir(parents=True, exist_ok=True)

        settings.data_dir = str(data_root)
        settings.app_source_dir = str(app_source_dir)
        settings.app_by_uid_dir = str(app_by_uid_dir)
        settings.behavior_source_dir = str(behavior_source_dir)
        settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
        settings.credit_source_dir = str(credit_source_dir)
        settings.credit_by_uid_dir = str(credit_by_uid_dir)

        cls._seed_sample_files(data_root)
        cls._write_credit_csv(credit_by_uid_dir / f"{REAL_UID}.csv")
        cls.prompt_path = settings.resolve_path(f"{settings.prompt_dir}/credit_profile_prompt.md")
        cls.repository = LocalUserRepository(allow_sample_fallback=False)
        cls.sample_context = build_credit_run_context(SAMPLE_UID)
        cls.real_context = build_credit_run_context(REAL_UID)
        cls.real_csv_path = settings.resolve_path(settings.credit_by_uid_dir) / f"{REAL_UID}.csv"
        cls.prepared_from_real_csv, cls.prepared_errors = prepare_credit_record_from_csv_file(
            cls.real_csv_path,
            REAL_UID,
            country_code=cls.real_context["country_code"],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        for key, value in cls._original_settings.items():
            setattr(settings, key, value)
        cls._temp_dir.cleanup()

    def _build_pipeline_objects(self, uid: str = REAL_UID) -> tuple[dict, dict, dict, dict]:
        context = build_credit_run_context(uid)
        provider = CreditDataProvider(self.repository)
        raw_data = provider.fetch(uid, context)
        feature_bundle = CreditFeatureBuilder().build(raw_data, context)
        decision_result = CreditDecisionEngine().decide(feature_bundle, context)
        prompt_payload = CreditDecisionEngine().build_prompt_payload(feature_bundle, decision_result)
        return raw_data, feature_bundle, decision_result, prompt_payload

    def test_run_context_contract(self) -> None:
        context = build_credit_run_context(SAMPLE_UID)
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
                "profile_mode",
            },
        )
        self.assertEqual(context["country_code"], "mx")
        self.assertEqual(context["channel"], "api")

    def test_prepared_csv_builder_contract(self) -> None:
        self.assertEqual(self.prepared_errors, [])
        self.assertEqual(self.prepared_from_real_csv["schema_version"], CREDIT_PREPARED_SCHEMA_VERSION)
        self.assertIn("account_details", self.prepared_from_real_csv)
        self.assertEqual(self.prepared_from_real_csv["score"]["credit_score_band"], "D")

    def test_data_provider_prepared_json_contract(self) -> None:
        prepared_payload = {
            **self.prepared_from_real_csv,
            "source_meta": {
                **self.prepared_from_real_csv["source_meta"],
                "source_variant": "prepared_json",
            },
        }
        provider = CreditDataProvider(FakePreparedRepository(prepared_payload))
        raw_data = provider.fetch(REAL_UID, self.real_context)

        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(raw_data["source_meta"]["source_variant"], "prepared_json")
        self.assertEqual(raw_data["prepared_record"]["schema_version"], CREDIT_PREPARED_SCHEMA_VERSION)
        self.assertTrue(raw_data["prepared_record"]["account_details"])

    def test_data_provider_raw_csv_priority_over_legacy_json(self) -> None:
        raw_data = CreditDataProvider(self.repository).fetch(REAL_UID, self.real_context)
        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(raw_data["source_meta"]["source_variant"], "raw_credit_csv")
        self.assertGreater(len(raw_data["prepared_record"]["account_details"]), 0)

    def test_data_provider_legacy_summary_contract(self) -> None:
        provider = CreditDataProvider(LegacySummaryRepository())
        raw_data = provider.fetch(SAMPLE_UID, self.sample_context)

        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(raw_data["source_meta"]["source_variant"], "legacy_summary_json")
        self.assertEqual(raw_data["prepared_record"]["score"]["credit_score_band"], "B")
        self.assertEqual(raw_data["prepared_record"]["summary"]["total_accounts"], 0)
        self.assertIn("legacy_credit_summary_only", raw_data["errors"])

    def test_data_provider_missing_contract(self) -> None:
        raw_data = CreditDataProvider(MissingCreditRepository()).fetch(MISSING_UID, build_credit_run_context(MISSING_UID))
        self.assertEqual(raw_data["data_status"], "missing")
        self.assertEqual(raw_data["prepared_record"]["schema_version"], CREDIT_PREPARED_SCHEMA_VERSION)
        self.assertEqual(raw_data["prepared_record"]["source_meta"]["source_variant"], "missing")

    def test_data_provider_invalid_contract(self) -> None:
        raw_data = CreditDataProvider(InvalidCreditRepository()).fetch("broken-credit-uid", build_credit_run_context("broken-credit-uid"))
        self.assertEqual(raw_data["data_status"], "invalid")
        self.assertIn("broken_credit_json", raw_data["errors"][0])

    def test_data_provider_schema_mismatch_contract(self) -> None:
        raw_data = CreditDataProvider(SchemaMismatchRepository()).fetch("schema-mismatch-uid", build_credit_run_context("schema-mismatch-uid"))
        self.assertEqual(raw_data["data_status"], "invalid")
        self.assertIn("prepared_schema_mismatch", raw_data["errors"])

    def test_feature_bundle_contract(self) -> None:
        raw_data, feature_bundle, _, _ = self._build_pipeline_objects()
        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(
            set(feature_bundle.keys()),
            {
                "uid",
                "country_code",
                "prepared_record",
                "summary_features",
                "account_features",
                "derived_signals",
                "feature_status",
                "errors",
            },
        )
        self.assertEqual(feature_bundle["feature_status"], "ok")
        self.assertIn("radar_scores", feature_bundle["derived_signals"])
        self.assertIn("score_value", feature_bundle["summary_features"])

    def test_decision_result_contract(self) -> None:
        _, feature_bundle, decision_result, _ = self._build_pipeline_objects()
        self.assertEqual(
            set(decision_result.keys()),
            {
                "uid",
                "country_code",
                "decision_status",
                "summary_seed",
                "evidence_seed",
                "financial_maturity",
                "debt_pressure",
                "credit_stability",
                "borrowing_urgency",
                "credit_signal_score",
                "metrics",
                "tags_rule",
                "llm_fallback_profile",
                "errors",
            },
        )
        self.assertEqual(decision_result["decision_status"], "ok")
        self.assertIn("score_value", decision_result["metrics"])
        self.assertIn("radar_scores", decision_result["metrics"])
        self.assertIn("credit_summary", decision_result["llm_fallback_profile"])

    def test_prompt_payload_built_from_prepared_contract(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        self.assertIn("prepared_credit_record", prompt_payload)
        self.assertIn("fallback_llm_profile", prompt_payload)
        self.assertEqual(prompt_payload["uid"], feature_bundle["uid"])
        self.assertEqual(
            prompt_payload["default_inference"]["risk_level"],
            decision_result["metrics"]["risk_level"],
        )

    def test_page_assembler_rich_contract(self) -> None:
        raw_data, feature_bundle, decision_result, _ = self._build_pipeline_objects()
        assembler = CreditPageAssembler(ModelClient())
        fallback_structured = assembler.build_fallback_structured(
            REAL_UID,
            raw_data,
            feature_bundle,
            decision_result,
        )
        explanation_result = {
            "uid": REAL_UID,
            "country_code": self.real_context["country_code"],
            "explanation_status": "skipped",
            "used_llm": False,
            "summary": "",
            "tags": [],
            "evidence_patch": {},
            "report_markdown": "",
            "model_trace": {
                "mode": "mock",
                "used_llm": False,
                "model_name": "mock-model",
                "fallback_reason": "model_mode_mock",
            },
            "errors": [],
        }
        page_result = assembler.assemble(REAL_UID, fallback_structured, explanation_result)
        structured = page_result["structured_result"]

        self.assertEqual(structured["status"], "ok")
        self.assertIn("score_value", structured["metrics"])
        self.assertIn("radar_scores", structured["metrics"])
        self.assertIn("llm_credit_profile", structured["evidence"])
        self.assertIn("account_details", structured["evidence"])
        self.assertGreaterEqual(len(page_result["charts"]), 4)
        self.assertEqual(structured["model_trace"]["fallback_reason"], "model_mode_mock")
        self.assertFalse(structured["model_trace"]["used_llm"])

    def test_explainer_mock_status(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects()
        model_client = ModelClient()
        model_client.mode = "mock"
        explainer = CreditExplainer(model_client, self.prompt_path)

        result = explainer.explain(
            REAL_UID,
            feature_bundle,
            decision_result,
            prompt_payload,
            self.real_context,
        )
        self.assertEqual(result["explanation_status"], "skipped")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["model_trace"]["fallback_reason"], "model_mode_mock")

    def test_credit_skill_model_unavailable_path_still_renders(self) -> None:
        model_client = ModelClient()
        model_client.mode = "vertex"
        model_client.generate_structured = Mock(
            return_value={
                "status": "model_unavailable",
                "model_name": "fake-model",
                "structured_result": {
                    "status": "model_unavailable",
                    "model_error": "dependency_missing",
                },
            }
        )
        skill = CreditProfileSkill(model_client)
        result = skill.analyze(REAL_UID, repository=self.repository)
        structured = result["structured_result"]

        self.assertEqual(structured["status"], "ok")
        self.assertIn("llm_credit_profile", structured["evidence"])
        self.assertIn("account_details", structured["evidence"])
        self.assertIn("score_value", structured["metrics"])
        self.assertGreaterEqual(len(result["charts"]), 4)

    def test_credit_skill_regression_real_uid(self) -> None:
        model_client = ModelClient()
        model_client.mode = "mock"
        skill = CreditProfileSkill(model_client)
        result = skill.analyze(REAL_UID, repository=self.repository)
        structured = result["structured_result"]
        metrics = structured["metrics"]
        evidence = structured["evidence"]

        self.assertEqual(structured["status"], "ok")
        self.assertEqual(metrics["credit_score_band"], "D")
        self.assertEqual(metrics["score_value"], 300)
        self.assertGreater(metrics["total_outstanding_debt_mxn"], 0)
        self.assertIn("repayment_amount_timeline", metrics)
        self.assertTrue(evidence["account_details"])
        self.assertTrue(evidence["llm_credit_profile"]["credit_summary"])

    def test_prepare_credit_prepared_json_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            target_csv = temp_path / f"{REAL_UID}.csv"
            shutil.copyfile(self.real_csv_path, target_csv)

            result = prepare_credit_prepared_json_directory(
                by_uid_dir=temp_path,
                country_code="mx",
            )
            target_json = temp_path / f"{REAL_UID}.json"

            self.assertEqual(result["prepared_count"], 1)
            self.assertTrue(target_json.exists())
            payload = json.loads(target_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], CREDIT_PREPARED_SCHEMA_VERSION)
            self.assertIn("account_details", payload)

    def test_country_pack_fallback(self) -> None:
        pack = load_credit_country_pack("br")
        self.assertEqual(pack.country_code, "mx")
        self.assertEqual(pack.source_display_name, "Buró de Crédito（墨西哥）")

    def test_orchestrator_integration_regression(self) -> None:
        orchestrator = AnalysisOrchestrator()
        orchestrator.model_client.mode = "mock"
        result = orchestrator.analyze([REAL_UID])
        credit_profile = result.results[0].credit_profile

        self.assertEqual(credit_profile.structured_result["status"], "ok")
        self.assertIn("score_value", credit_profile.structured_result["metrics"])
        self.assertIn("llm_credit_profile", credit_profile.structured_result["evidence"])

    def test_build_empty_prepared_record_contract(self) -> None:
        record = build_empty_prepared_record("blank-uid", country_code="mx")
        self.assertEqual(record["schema_version"], CREDIT_PREPARED_SCHEMA_VERSION)
        self.assertEqual(record["source_meta"]["source_variant"], "missing")
        self.assertEqual(len(record["repayment_timeline"]), 12)

    @staticmethod
    def _seed_sample_files(data_root: Path) -> None:
        data_root.mkdir(parents=True, exist_ok=True)
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
    def _write_credit_csv(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        credit_rows = [
            {
                "uid": REAL_UID,
                "valor": "300",
                "dt": "2026-06-30",
                "nombrescore": "FICO",
                "razones": "late payments,high utilization",
                "fechanacimiento": "1990-01-15",
                "ciudad": "Monterrey",
                "ocupacion": "Engineer",
                "consultas_detail_json": json.dumps(
                    [
                        {
                            "consultas_nombreotorgante": "BBVA",
                            "fechaconsulta": "2026-05-10",
                        }
                    ],
                    ensure_ascii=False,
                ),
                "creditos_detail_json": json.dumps(
                    [
                        {
                            "credito_nombreotorgante": "BBVA",
                            "credito_tipocredito": "TC",
                            "limitecredito": "10000",
                            "saldoactual": "7500",
                            "montopagar": "1200",
                            "dias_atraso": "15",
                            "fechaaperturacuenta": "2021-01-01",
                            "fechaactualizacion": "2026-06-30",
                        }
                    ],
                    ensure_ascii=False,
                ),
            }
        ]
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(credit_rows[0].keys()))
            writer.writeheader()
            writer.writerows(credit_rows)


if __name__ == "__main__":
    unittest.main()
