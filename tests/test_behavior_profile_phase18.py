from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.core.config import settings
from app.core.model_client import ModelClient
from app.country_packs.behavior_profile import load_behavior_country_pack
from app.repositories.base import BaseUserRepository
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.behavior_profile import (
    BehaviorDataProvider,
    BehaviorDecisionEngine,
    BehaviorExplainer,
    BehaviorFeatureBuilder,
    BehaviorPageAssembler,
)
from app.runtime_skills.behavior_profile.contracts import (
    build_behavior_run_context,
    build_empty_prepared_record,
)
from app.runtime_skills.behavior_profile_agent import BehaviorProfileSkill
from app.scripts.behavior_prepared_builder import (
    BEHAVIOR_PREPARED_SCHEMA_VERSION,
    prepare_behavior_record_from_csv_file,
)
from app.scripts.data_prep.behavior_preparer import (
    prepare_behavior_prepared_json_directory,
)
from app.services.orchestrator import AnalysisOrchestrator


SAMPLE_UID = "user_001"
EVENT_UID = "behavior_event_uid_001"
REAL_EVENT_UID = "824812551379353600"
MISSING_UID = "behavior_uid_not_found_for_phase18_test"


def _build_event_rows(uid: str) -> list[dict[str, str]]:
    return [
        {
            "user_uuid": uid,
            "event_time": "2026-04-10T09:00:00",
            "event_name": "app_open",
            "page_name": "home",
            "status": "ok",
            "note": "open app",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-10T09:08:00",
            "event_name": "view_rate_card",
            "page_name": "rate_page",
            "status": "ok",
            "note": "check promo coupon",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-10T09:18:00",
            "event_name": "start_apply",
            "page_name": "application_form",
            "status": "ok",
            "note": "fill employment info",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-10T09:28:00",
            "event_name": "kyc_submit",
            "page_name": "kyc_page",
            "status": "fail",
            "note": "liveness timeout",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-11T20:05:00",
            "event_name": "whatsapp_click",
            "page_name": "support_center",
            "status": "ok",
            "note": "contact agent",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-12T19:30:00",
            "event_name": "repay_now",
            "page_name": "repayment_page",
            "status": "ok",
            "note": "payment reminder viewed",
        },
        {
            "user_uuid": uid,
            "event_time": "2026-04-12T19:36:00",
            "event_name": "view_discount_coupon",
            "page_name": "coupon_center",
            "status": "ok",
            "note": "discount available",
        },
    ]


class FakePreparedRepository(BaseUserRepository):
    def __init__(self, prepared_payload: dict[str, object]) -> None:
        self.prepared_payload = prepared_payload

    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return dict(self.prepared_payload)

    def get_credit_data(self, uid: str) -> dict:
        return {}


class RawCsvRepository(BaseUserRepository):
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_type": "local_file",
            "source_kind": "raw_behavior_csv",
            "source_file": f"raw://behavior/{uid}.csv",
            "rows": list(self.rows),
        }

    def get_credit_data(self, uid: str) -> dict:
        return {}


class LegacySummaryRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_type": "database_api",
            "source_kind": "legacy_behavior_summary_json",
            "source_file": f"legacy://behavior/{uid}.json",
            "avg_session_minutes": 34,
            "login_days_30d": 16,
            "purchase_preference": "discount_value",
        }

    def get_credit_data(self, uid: str) -> dict:
        return {}


class InvalidBehaviorRepository(BaseUserRepository):
    def get_app_data(self, uid: str) -> dict:
        return {}

    def get_behavior_data(self, uid: str) -> dict:
        return {
            "uid": uid,
            "source_file": f"broken://{uid}",
            "data_status": "invalid",
            "load_error": "broken_behavior_csv",
        }

    def get_credit_data(self, uid: str) -> dict:
        return {}


class MissingBehaviorRepository(BaseUserRepository):
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
        return {
            "uid": uid,
            "schema_version": BEHAVIOR_PREPARED_SCHEMA_VERSION,
            "source_meta": {"source_type": "local_file"},
        }

    def get_credit_data(self, uid: str) -> dict:
        return {}


class BehaviorProfilePhase18Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_prompt_path = settings.resolve_path(
            f"{settings.prompt_dir}/behavior_profile_prompt.md"
        )
        cls.timeline_prompt_path = settings.resolve_path(
            f"{settings.prompt_dir}/behavior_timeline_prompt.md"
        )
        cls.repository = LocalUserRepository()
        cls.sample_context = build_behavior_run_context(SAMPLE_UID)
        cls.event_context = build_behavior_run_context(EVENT_UID)
        cls.event_rows = _build_event_rows(EVENT_UID)
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.real_csv_path = Path(cls.temp_dir.name) / f"{EVENT_UID}.csv"
        with cls.real_csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=list(cls.event_rows[0].keys()),
            )
            writer.writeheader()
            writer.writerows(cls.event_rows)
        cls.prepared_from_csv, cls.prepared_errors = prepare_behavior_record_from_csv_file(
            cls.real_csv_path,
            EVENT_UID,
            country_code=cls.event_context["country_code"],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def _build_pipeline_objects(
        self,
        repository: BaseUserRepository,
        uid: str = EVENT_UID,
    ) -> tuple[dict, dict, dict, dict]:
        context = build_behavior_run_context(uid)
        provider = BehaviorDataProvider(repository)
        raw_data = provider.fetch(uid, context)
        feature_bundle = BehaviorFeatureBuilder().build(raw_data, context)
        decision_result = BehaviorDecisionEngine().decide(feature_bundle, context)
        prompt_payload = BehaviorDecisionEngine().build_prompt_payload(
            feature_bundle,
            decision_result,
        )
        return raw_data, feature_bundle, decision_result, prompt_payload

    def test_run_context_contract(self) -> None:
        context = build_behavior_run_context(SAMPLE_UID)
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
        self.assertEqual(context["country_code"], "mx")
        self.assertEqual(context["channel"], "api")

    def test_prepared_csv_builder_contract(self) -> None:
        self.assertEqual(self.prepared_errors, [])
        self.assertEqual(
            self.prepared_from_csv["schema_version"],
            BEHAVIOR_PREPARED_SCHEMA_VERSION,
        )
        self.assertGreater(len(self.prepared_from_csv["timeline_sections"]), 0)
        self.assertGreater(len(self.prepared_from_csv["timeline_sections_raw"]), 0)
        self.assertGreater(len(self.prepared_from_csv["timeline_sections_compact"]), 0)
        self.assertEqual(
            self.prepared_from_csv["contact_signals"]["best_channel"],
            "WhatsApp",
        )

    def test_data_provider_prepared_json_contract(self) -> None:
        prepared_payload = {
            **self.prepared_from_csv,
            "source_meta": {
                **self.prepared_from_csv["source_meta"],
                "source_variant": "prepared_json",
            },
        }
        provider = BehaviorDataProvider(FakePreparedRepository(prepared_payload))
        raw_data = provider.fetch(EVENT_UID, self.event_context)

        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(raw_data["source_meta"]["source_variant"], "prepared_json")
        self.assertEqual(
            raw_data["prepared_record"]["schema_version"],
            BEHAVIOR_PREPARED_SCHEMA_VERSION,
        )
        self.assertTrue(raw_data["prepared_record"]["timeline_sections"])
        self.assertTrue(raw_data["prepared_record"]["timeline_sections_compact"])
        self.assertTrue(raw_data["prepared_record"]["timeline_sections_raw"])

    def test_data_provider_raw_csv_contract(self) -> None:
        provider = BehaviorDataProvider(RawCsvRepository(self.event_rows))
        raw_data = provider.fetch(EVENT_UID, self.event_context)

        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(raw_data["source_meta"]["source_variant"], "raw_behavior_csv")
        self.assertGreater(
            len(raw_data["prepared_record"]["timeline_sections"]),
            0,
        )
        self.assertGreater(
            len(raw_data["prepared_record"]["timeline_sections_compact"]),
            0,
        )
        self.assertGreater(
            raw_data["prepared_record"]["session_summary"]["total_events"],
            0,
        )

    def test_data_provider_legacy_summary_contract(self) -> None:
        provider = BehaviorDataProvider(LegacySummaryRepository())
        raw_data = provider.fetch(SAMPLE_UID, self.sample_context)

        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(
            raw_data["source_meta"]["source_variant"],
            "legacy_behavior_summary_json",
        )
        self.assertEqual(raw_data["prepared_record"]["timeline_sections"], [])
        self.assertEqual(raw_data["prepared_record"]["timeline_sections_raw"], [])
        self.assertEqual(raw_data["prepared_record"]["timeline_sections_compact"], [])
        self.assertIn("legacy_behavior_summary_only", raw_data["errors"])

    def test_data_provider_missing_contract(self) -> None:
        raw_data = BehaviorDataProvider(MissingBehaviorRepository()).fetch(
            MISSING_UID,
            build_behavior_run_context(MISSING_UID),
        )
        self.assertEqual(raw_data["data_status"], "missing")
        self.assertEqual(
            raw_data["prepared_record"]["schema_version"],
            BEHAVIOR_PREPARED_SCHEMA_VERSION,
        )
        self.assertEqual(
            raw_data["prepared_record"]["source_meta"]["source_variant"],
            "missing",
        )

    def test_data_provider_invalid_contract(self) -> None:
        raw_data = BehaviorDataProvider(InvalidBehaviorRepository()).fetch(
            "broken-behavior-uid",
            build_behavior_run_context("broken-behavior-uid"),
        )
        self.assertEqual(raw_data["data_status"], "invalid")
        self.assertIn("broken_behavior_csv", raw_data["errors"][0])

    def test_data_provider_schema_mismatch_contract(self) -> None:
        raw_data = BehaviorDataProvider(SchemaMismatchRepository()).fetch(
            "schema-mismatch-uid",
            build_behavior_run_context("schema-mismatch-uid"),
        )
        self.assertEqual(raw_data["data_status"], "invalid")
        self.assertIn("prepared_schema_mismatch", raw_data["errors"])

    def test_feature_bundle_contract(self) -> None:
        raw_data, feature_bundle, _, _ = self._build_pipeline_objects(
            RawCsvRepository(self.event_rows)
        )
        self.assertEqual(raw_data["data_status"], "ok")
        self.assertEqual(
            set(feature_bundle.keys()),
            {
                "uid",
                "country_code",
                "prepared_record",
                "summary_features",
                "timeline_features",
                "derived_signals",
                "feature_status",
                "errors",
            },
        )
        self.assertEqual(feature_bundle["feature_status"], "ok")
        self.assertIn("timeline_section_count", feature_bundle["timeline_features"])
        self.assertIn("timeline_sections_raw", feature_bundle["timeline_features"])
        self.assertIn("timeline_sections_compact", feature_bundle["timeline_features"])
        self.assertIn("contact_preference", feature_bundle["derived_signals"])

    def test_decision_result_contract(self) -> None:
        _, feature_bundle, decision_result, _ = self._build_pipeline_objects(
            RawCsvRepository(self.event_rows)
        )
        self.assertEqual(
            set(decision_result.keys()),
            {
                "uid",
                "country_code",
                "decision_status",
                "summary_seed",
                "evidence_seed",
                "engagement_profile",
                "repayment_willingness",
                "product_sensitivity",
                "churn_risk",
                "contact_preference",
                "behavior_signal_score",
                "metrics",
                "tags_rule",
                "llm_fallback_profile",
                "errors",
            },
        )
        self.assertEqual(decision_result["decision_status"], "ok")
        self.assertIn("timeline_section_count", decision_result["metrics"])
        self.assertIn("timeline_event_count_compact", decision_result["metrics"])
        self.assertIn("behavior_summary", decision_result["llm_fallback_profile"])

    def test_prompt_payload_built_from_prepared_contract(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects(
            RawCsvRepository(self.event_rows)
        )
        self.assertIn("prepared_behavior_record", prompt_payload)
        self.assertIn("behavior_profile_prompt_input", prompt_payload)
        self.assertIn("behavior_timeline_prompt_input", prompt_payload)
        self.assertIn("fallback_llm_profile", prompt_payload)
        self.assertEqual(prompt_payload["uid"], feature_bundle["uid"])
        self.assertEqual(
            prompt_payload["default_inference"]["engagement_level"],
            decision_result["engagement_profile"]["level"],
        )

    def test_page_assembler_rich_contract(self) -> None:
        raw_data, feature_bundle, decision_result, _ = self._build_pipeline_objects(
            RawCsvRepository(self.event_rows)
        )
        assembler = BehaviorPageAssembler(ModelClient())
        fallback_structured = assembler.build_fallback_structured(
            EVENT_UID,
            raw_data,
            feature_bundle,
            decision_result,
        )
        explanation_result = {
            "uid": EVENT_UID,
            "country_code": self.event_context["country_code"],
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
        page_result = assembler.assemble(EVENT_UID, fallback_structured, explanation_result)
        structured = page_result["structured_result"]

        self.assertEqual(structured["status"], "ok")
        self.assertIn("timeline_section_count", structured["metrics"])
        self.assertIn("timeline_sections", structured["evidence"])
        self.assertIn("timeline_sections_raw", structured["evidence"])
        self.assertIn("timeline_sections_compact", structured["evidence"])
        self.assertIn("timeline_narrative", structured["evidence"])
        self.assertIn("behavior_profile_narrative", structured["evidence"])
        self.assertIn("llm_behavior_profile", structured["evidence"])
        self.assertIn("llm_profile", structured["evidence"])
        self.assertEqual(structured["model_trace"]["fallback_reason"], "model_mode_mock")
        self.assertFalse(structured["model_trace"]["used_llm"])
        self.assertIn("llm_timeline", structured["evidence"])
        self.assertGreaterEqual(len(page_result["charts"]), 3)

    def test_real_behavior_csv_schema_regression(self) -> None:
        raw_data = BehaviorDataProvider(LocalUserRepository()).fetch(
            REAL_EVENT_UID,
            build_behavior_run_context(REAL_EVENT_UID),
        )
        self.assertEqual(raw_data["data_status"], "ok")
        prepared = raw_data["prepared_record"]
        self.assertGreater(len(prepared["timeline_sections"]), 0)
        self.assertGreater(len(prepared["timeline_sections_raw"]), 0)
        self.assertGreater(len(prepared["timeline_sections_compact"]), 0)
        self.assertGreater(prepared["session_summary"]["total_events"], 0)
        self.assertEqual(
            prepared["profile_header"]["global_info"]["UID"],
            REAL_EVENT_UID,
        )

    def test_real_behavior_compaction_regression(self) -> None:
        raw_data = BehaviorDataProvider(LocalUserRepository()).fetch(
            REAL_EVENT_UID,
            build_behavior_run_context(REAL_EVENT_UID),
        )
        prepared = raw_data["prepared_record"]
        raw_sections = prepared["timeline_sections_raw"]
        compact_sections = prepared["timeline_sections_compact"]

        self.assertTrue(raw_sections)
        self.assertTrue(compact_sections)

        raw_event_count = sum(len(section.get("events", [])) for section in raw_sections)
        compact_event_count = sum(len(section.get("events", [])) for section in compact_sections)

        self.assertGreater(raw_event_count, compact_event_count)
        self.assertTrue(
            any(
                int(section.get("raw_event_count", 0) or 0)
                > len(section.get("events", []))
                for section in compact_sections
            )
        )

    def test_real_behavior_skill_rich_page_contract(self) -> None:
        model_client = ModelClient()
        model_client.mode = "mock"
        skill = BehaviorProfileSkill(model_client)
        result = skill.analyze(REAL_EVENT_UID, repository=LocalUserRepository())
        structured = result["structured_result"]
        evidence = structured["evidence"]

        self.assertEqual(structured["status"], "ok")
        self.assertTrue(evidence["timeline_sections"])
        self.assertTrue(evidence["timeline_insights"])
        self.assertTrue(evidence["timeline_sections_raw"])
        self.assertTrue(evidence["timeline_sections_compact"])
        self.assertIn("timeline_narrative", evidence)
        self.assertIn("behavior_profile_narrative", evidence)
        self.assertIn("llm_timeline", evidence)
        self.assertIn("global_info", evidence)
        self.assertIn("llm_profile", evidence)
        self.assertEqual(evidence["global_info"]["UID"], REAL_EVENT_UID)
        self.assertGreater(structured["metrics"]["page_node_count"], 0)
        self.assertGreater(structured["metrics"]["interaction_count"], 0)
        self.assertGreater(structured["metrics"]["timeline_event_count"], structured["metrics"]["timeline_event_count_compact"])

    def test_explainer_mock_status(self) -> None:
        _, feature_bundle, decision_result, prompt_payload = self._build_pipeline_objects(
            RawCsvRepository(self.event_rows)
        )
        model_client = ModelClient()
        model_client.mode = "mock"
        explainer = BehaviorExplainer(
            model_client,
            self.profile_prompt_path,
            self.timeline_prompt_path,
        )

        result = explainer.explain(
            EVENT_UID,
            feature_bundle,
            decision_result,
            prompt_payload,
            self.event_context,
        )
        self.assertEqual(result["explanation_status"], "skipped")
        self.assertFalse(result["used_llm"])
        self.assertEqual(result["model_trace"]["fallback_reason"], "model_mode_mock")
        self.assertFalse(result["model_trace"]["used_llm_profile"])
        self.assertFalse(result["model_trace"]["used_llm_timeline"])

    def test_behavior_skill_model_unavailable_path_still_renders(self) -> None:
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
        skill = BehaviorProfileSkill(model_client)
        result = skill.analyze(SAMPLE_UID, repository=self.repository)
        structured = result["structured_result"]

        self.assertEqual(structured["status"], "ok")
        self.assertIn("llm_behavior_profile", structured["evidence"])
        self.assertIn("timeline_sections", structured["evidence"])
        self.assertIn("timeline_sections_raw", structured["evidence"])
        self.assertIn("timeline_sections_compact", structured["evidence"])
        self.assertIn("llm_timeline", structured["evidence"])
        self.assertIn("engagement_score", structured["metrics"])
        self.assertGreaterEqual(len(result["charts"]), 2)

    def test_behavior_skill_sample_regression(self) -> None:
        model_client = ModelClient()
        model_client.mode = "mock"
        skill = BehaviorProfileSkill(model_client)
        result = skill.analyze(SAMPLE_UID, repository=self.repository)
        structured = result["structured_result"]

        self.assertEqual(structured["status"], "ok")
        self.assertEqual(structured["engagement_level"], "deep")
        self.assertEqual(structured["metrics"]["repayment_willingness_level"], "high")
        self.assertIn("llm_behavior_profile", structured["evidence"])
        self.assertIn("behavior_profile_narrative", structured["evidence"])
        self.assertTrue(result["report_markdown"])

    def test_prepare_behavior_prepared_json_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            target_csv = temp_path / f"{EVENT_UID}.csv"
            shutil.copyfile(self.real_csv_path, target_csv)

            result = prepare_behavior_prepared_json_directory(
                by_uid_dir=temp_path,
                country_code="mx",
            )
            target_json = temp_path / f"{EVENT_UID}.json"

            self.assertEqual(result["prepared_count"], 1)
            self.assertTrue(target_json.exists())
            payload = json.loads(target_json.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["schema_version"],
                BEHAVIOR_PREPARED_SCHEMA_VERSION,
            )
            self.assertIn("timeline_sections", payload)
            self.assertIn("timeline_sections_raw", payload)
            self.assertIn("timeline_sections_compact", payload)

    def test_country_pack_fallback(self) -> None:
        pack = load_behavior_country_pack("br")
        self.assertEqual(pack.country_code, "mx")
        self.assertEqual(pack.default_contact_channel, "WhatsApp")

    def test_orchestrator_integration_regression(self) -> None:
        orchestrator = AnalysisOrchestrator()
        orchestrator.model_client.mode = "mock"
        result = orchestrator.analyze([SAMPLE_UID])
        behavior_profile = result.results[0].behavior_profile

        self.assertEqual(behavior_profile.structured_result["status"], "ok")
        self.assertIn("timeline_sections", behavior_profile.structured_result["evidence"])
        self.assertIn("timeline_sections_compact", behavior_profile.structured_result["evidence"])
        self.assertIn("engagement_score", behavior_profile.structured_result["metrics"])

    def test_build_empty_prepared_record_contract(self) -> None:
        record = build_empty_prepared_record("blank-uid", country_code="mx")
        self.assertEqual(record["schema_version"], BEHAVIOR_PREPARED_SCHEMA_VERSION)
        self.assertEqual(record["source_meta"]["source_variant"], "missing")
        self.assertEqual(record["contact_signals"]["best_channel"], "WhatsApp")
        self.assertEqual(record["timeline_sections_raw"], [])
        self.assertEqual(record["timeline_sections_compact"], [])


if __name__ == "__main__":
    unittest.main()
