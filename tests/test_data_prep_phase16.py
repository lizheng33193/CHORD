from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.core.model_client import ModelClient
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.behavior_profile_agent import BehaviorProfileSkill
from app.runtime_skills.credit_profile_agent import CreditProfileSkill
from app.scripts.behavior_data_loader import load_behavior_data
from app.scripts.credit_data_loader import load_credit_data
from app.scripts.data_prep.prepare_local_data import prepare_local_data


class DataPrepPhase16Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_settings = {
            "data_dir": settings.data_dir,
            "app_source_dir": settings.app_source_dir,
            "app_by_uid_dir": settings.app_by_uid_dir,
            "behavior_source_dir": settings.behavior_source_dir,
            "behavior_by_uid_dir": settings.behavior_by_uid_dir,
            "credit_source_dir": settings.credit_source_dir,
            "credit_by_uid_dir": settings.credit_by_uid_dir,
        }

    def tearDown(self) -> None:
        for key, value in self._original_settings.items():
            setattr(settings, key, value)

    def test_behavior_repository_prefers_new_by_uid_then_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            behavior_by_uid_dir = temp_root / "prepared" / "behavior" / "by_uid"
            self._seed_sample_files(data_root)

            uid = "user_001"
            behavior_by_uid_dir.mkdir(parents=True, exist_ok=True)
            (behavior_by_uid_dir / f"{uid}.json").write_text(
                json.dumps(
                    {
                        "uid": uid,
                        "country_code": "mx",
                        "schema_version": "behavior-prepared-v1",
                        "profile_header": {"uid": uid},
                        "session_summary": {"avg_session_minutes": 88},
                        "engagement_signals": {"engagement_score": 100, "engagement_level": "deep"},
                        "repayment_signals": {"repayment_willingness_level": "high"},
                        "product_intent_signals": {"product_sensitivity_level": "medium"},
                        "churn_signals": {"churn_risk_level": "low"},
                        "contact_signals": {"best_channel": "WhatsApp"},
                        "timeline_sections": [],
                        "timeline_insights": [],
                        "source_meta": {"source_type": "local_file"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings.data_dir = str(data_root)
            settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
            repository = LocalUserRepository()

            preferred = repository.get_behavior_data(uid)
            self.assertEqual(preferred["source_kind"], "prepared_json")
            self.assertEqual(preferred["session_summary"]["avg_session_minutes"], 88)
            self.assertEqual(preferred["source_file"], str(behavior_by_uid_dir / f"{uid}.json"))

            (behavior_by_uid_dir / f"{uid}.json").unlink()
            fallback = repository.get_behavior_data(uid)
            self.assertEqual(fallback["avg_session_minutes"], 52)
            self.assertEqual(fallback["purchase_preference"], "premium_quality")
            self.assertEqual(fallback["source_kind"], "legacy_behavior_summary_sample")

    def test_behavior_repository_invalid_new_file_and_loader_drops_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            behavior_by_uid_dir = temp_root / "prepared" / "behavior" / "by_uid"
            self._seed_sample_files(data_root)

            uid = "user_001"
            behavior_by_uid_dir.mkdir(parents=True, exist_ok=True)
            (behavior_by_uid_dir / f"{uid}.json").write_text("{", encoding="utf-8")

            settings.data_dir = str(data_root)
            settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
            repository = LocalUserRepository()

            payload = repository.get_behavior_data(uid)
            self.assertEqual(payload["data_status"], "invalid")
            self.assertTrue(payload["load_error"])
            loaded = load_behavior_data(repository, uid)
            self.assertEqual(loaded, {})

    def test_credit_repository_prefers_new_json_then_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            credit_by_uid_dir = temp_root / "prepared" / "credit" / "by_uid"
            self._seed_sample_files(data_root)

            uid = "user_001"
            credit_by_uid_dir.mkdir(parents=True, exist_ok=True)
            (credit_by_uid_dir / f"{uid}.json").write_text(
                json.dumps(
                    {
                        "uid": uid,
                        "credit_score_band": "B",
                        "repayment_status": "normal",
                        "risk_level": "medium",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            settings.data_dir = str(data_root)
            settings.credit_by_uid_dir = str(credit_by_uid_dir)
            repository = LocalUserRepository()

            preferred = repository.get_credit_data(uid)
            self.assertEqual(preferred["credit_score_band"], "B")
            self.assertEqual(preferred["source_file"], str(credit_by_uid_dir / f"{uid}.json"))

            (credit_by_uid_dir / f"{uid}.json").unlink()
            fallback = repository.get_credit_data(uid)
            self.assertEqual(fallback["credit_score_band"], "A")
            self.assertEqual(fallback["risk_level"], "low")
            self.assertEqual(fallback["source_kind"], "legacy_summary_sample")
            self.assertIn("source_file", fallback)

    def test_credit_repository_accepts_single_row_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            credit_by_uid_dir = temp_root / "prepared" / "credit" / "by_uid"
            self._seed_sample_files(data_root)

            uid = "user_009"
            self._write_csv(
                credit_by_uid_dir / f"{uid}.csv",
                ["uid", "credit_score_band", "repayment_status", "risk_level"],
                [
                    {
                        "uid": uid,
                        "credit_score_band": "C",
                        "repayment_status": "watchlist",
                        "risk_level": "high",
                    }
                ],
            )

            settings.data_dir = str(data_root)
            settings.credit_by_uid_dir = str(credit_by_uid_dir)
            repository = LocalUserRepository()

            payload = repository.get_credit_data(uid)
            self.assertEqual(payload["source_kind"], "raw_credit_csv")
            self.assertEqual(len(payload["rows"]), 1)
            self.assertEqual(payload["source_file"], str(credit_by_uid_dir / f"{uid}.csv"))

            loaded = load_credit_data(repository, uid)
            self.assertEqual(loaded["source_kind"], "raw_credit_csv")

    def test_credit_repository_invalid_json_and_loader_drops_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            credit_by_uid_dir = temp_root / "prepared" / "credit" / "by_uid"
            self._seed_sample_files(data_root)

            uid = "user_001"
            credit_by_uid_dir.mkdir(parents=True, exist_ok=True)
            (credit_by_uid_dir / f"{uid}.json").write_text(
                json.dumps({"uid": uid, "credit_score_band": "A"}, ensure_ascii=False),
                encoding="utf-8",
            )

            settings.data_dir = str(data_root)
            settings.credit_by_uid_dir = str(credit_by_uid_dir)
            repository = LocalUserRepository()

            payload = repository.get_credit_data(uid)
            self.assertEqual(payload["data_status"], "invalid")
            self.assertIn("missing_fields", payload["load_error"])
            loaded = load_credit_data(repository, uid)
            self.assertEqual(loaded, {})

    def test_prepare_local_data_behavior_and_credit_skip_without_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            behavior_source_dir = temp_root / "behavior" / "source"
            behavior_by_uid_dir = temp_root / "behavior" / "by_uid"
            credit_source_dir = temp_root / "credit" / "source"
            credit_by_uid_dir = temp_root / "credit" / "by_uid"

            behavior_source_dir.mkdir(parents=True, exist_ok=True)
            credit_source_dir.mkdir(parents=True, exist_ok=True)

            settings.behavior_source_dir = str(behavior_source_dir)
            settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
            settings.credit_source_dir = str(credit_source_dir)
            settings.credit_by_uid_dir = str(credit_by_uid_dir)

            behavior_result = prepare_local_data("behavior")
            credit_result = prepare_local_data("credit")
            all_result = prepare_local_data("all")

            self.assertEqual(behavior_result["behavior"]["status"], "skipped")
            self.assertEqual(credit_result["credit"]["status"], "skipped")
            self.assertEqual(all_result["behavior"]["status"], "skipped")
            self.assertEqual(all_result["credit"]["status"], "skipped")

    def test_behavior_and_credit_skill_sample_regression(self) -> None:
        repository = LocalUserRepository()

        behavior_model = ModelClient()
        behavior_model.mode = "mock"
        behavior_result = BehaviorProfileSkill(behavior_model).analyze("user_001", repository=repository)
        self.assertEqual(behavior_result["structured_result"]["status"], "ok")
        self.assertTrue(behavior_result["report_markdown"])

        credit_model = ModelClient()
        credit_model.mode = "mock"
        credit_result = CreditProfileSkill(credit_model).analyze("user_001", repository=repository)
        self.assertEqual(credit_result["structured_result"]["status"], "ok")
        self.assertTrue(credit_result["report_markdown"])

    def _seed_sample_files(self, data_root: Path) -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        self._write_csv(
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

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
