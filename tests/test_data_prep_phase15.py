from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from app.core.config import settings
from app.repositories.local_repository import LocalUserRepository
from app.scripts.data_prep.applist_joiner import prepare_joined_applist_by_uid
from app.scripts.data_prep.prepare_local_data import prepare_local_data
from app.scripts.data_prep.uid_csv_splitter import prepare_uid_csv_directory


class DataPrepPhase15Tests(unittest.TestCase):
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

    def test_applist_joiner_builds_uid_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "by_uid"
            source_dir.mkdir(parents=True, exist_ok=True)

            self._write_csv(
                source_dir / "mex_usage.csv",
                ["uid", "app_name", "app_package", "first_install_time", "last_update_time"],
                [
                    {
                        "uid": "u1",
                        "app_name": "Kueski",
                        "app_package": "com.kueski.app",
                        "first_install_time": "1713000000000",
                        "last_update_time": "1713500000000",
                    },
                    {
                        "uid": "u2",
                        "app_name": "Mercado Pago",
                        "app_package": "com.mercadopago.wallet",
                        "first_install_time": "1713000000001",
                        "last_update_time": "1713500000001",
                    },
                ],
            )
            self._write_csv(
                source_dir / "mex_label.csv",
                ["app_package", "app_name", "gp_category", "ai_category_level_2_CN"],
                [
                    {
                        "app_package": "com.kueski.app",
                        "app_name": "Kueski",
                        "gp_category": "Finance",
                        "ai_category_level_2_CN": "Loan",
                    },
                    {
                        "app_package": "com.mercadopago.wallet",
                        "app_name": "Mercado Pago",
                        "gp_category": "Finance",
                        "ai_category_level_2_CN": "Wallet",
                    },
                ],
            )

            stats = prepare_joined_applist_by_uid(source_dir=source_dir, output_dir=output_dir)

            self.assertIsNotNone(stats)
            uid_file = output_dir / "u1.csv"
            self.assertTrue(uid_file.exists())
            with uid_file.open("r", encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 1)
            self.assertEqual(
                list(rows[0].keys()),
                [
                    "uid",
                    "app_name",
                    "app_package",
                    "first_install_time",
                    "last_update_time",
                    "gp_category",
                    "ai_category_level_2_CN",
                ],
            )
            self.assertEqual(rows[0]["gp_category"], "Finance")
            self.assertEqual(rows[0]["ai_category_level_2_CN"], "Loan")

    def test_uid_csv_splitter_rebuilds_when_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "source"
            output_dir = Path(temp_dir) / "by_uid"
            source_dir.mkdir(parents=True, exist_ok=True)
            source_file = source_dir / "behavior.csv"

            self._write_csv(
                source_file,
                ["uid", "event_name"],
                [
                    {"uid": "u1", "event_name": "open"},
                    {"uid": "u2", "event_name": "submit"},
                ],
            )

            first_stats = prepare_uid_csv_directory(source_dir=source_dir, output_dir=output_dir)
            self.assertEqual(len(first_stats), 1)
            self.assertTrue((output_dir / ".split_state.json").exists())
            self.assertTrue((output_dir / "u1.csv").exists())

            self._write_csv(
                source_file,
                ["uid", "event_name"],
                [
                    {"uid": "u1", "event_name": "open"},
                    {"uid": "u3", "event_name": "approve"},
                ],
            )

            second_stats = prepare_uid_csv_directory(source_dir=source_dir, output_dir=output_dir)
            self.assertEqual(len(second_stats), 1)
            self.assertTrue((output_dir / "u3.csv").exists())
            with (output_dir / "u1.csv").open("r", encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 1)

    def test_local_repository_prefers_new_app_by_uid_then_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            new_by_uid_dir = temp_root / "prepared" / "app" / "by_uid"
            legacy_by_uid_dir = data_root / "data" / "data" / "appData" / "appData_by_user"
            self._seed_local_repository_base(data_root)

            uid = "priority_uid"
            self._write_valid_app_uid_csv(
                new_by_uid_dir / f"{uid}.csv",
                uid=uid,
                app_name="New Source App",
            )
            self._write_valid_app_uid_csv(
                legacy_by_uid_dir / f"{uid}.csv",
                uid=uid,
                app_name="Legacy Source App",
            )

            settings.data_dir = str(data_root)
            settings.app_by_uid_dir = str(new_by_uid_dir)

            repository = LocalUserRepository()
            result = repository.get_app_data(uid)
            self.assertEqual(result["apps"][0]["app_name"], "New Source App")
            self.assertEqual(result["source_file"], str(new_by_uid_dir / f"{uid}.csv"))

            (new_by_uid_dir / f"{uid}.csv").unlink()
            fallback_result = repository.get_app_data(uid)
            self.assertEqual(fallback_result["apps"][0]["app_name"], "Legacy Source App")
            self.assertEqual(fallback_result["source_file"], str(legacy_by_uid_dir / f"{uid}.csv"))

    def test_local_repository_invalid_new_file_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            data_root = temp_root / "data"
            new_by_uid_dir = temp_root / "prepared" / "app" / "by_uid"
            legacy_by_uid_dir = data_root / "data" / "data" / "appData" / "appData_by_user"
            self._seed_local_repository_base(data_root)

            uid = "invalid_priority_uid"
            new_by_uid_dir.mkdir(parents=True, exist_ok=True)
            self._write_csv(
                new_by_uid_dir / f"{uid}.csv",
                ["uid", "app_name"],
                [{"uid": uid, "app_name": "Broken App"}],
            )
            self._write_valid_app_uid_csv(
                legacy_by_uid_dir / f"{uid}.csv",
                uid=uid,
                app_name="Legacy Valid App",
            )

            settings.data_dir = str(data_root)
            settings.app_by_uid_dir = str(new_by_uid_dir)

            repository = LocalUserRepository()
            result = repository.get_app_data(uid)
            self.assertEqual(result["data_status"], "invalid")
            self.assertIn("missing_fields", result["load_error"])
            self.assertEqual(result["source_file"], str(new_by_uid_dir / f"{uid}.csv"))

    def test_prepare_local_data_app_and_all_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            app_source_dir = temp_root / "app" / "source"
            app_by_uid_dir = temp_root / "app" / "by_uid"
            behavior_source_dir = temp_root / "behavior" / "source"
            behavior_by_uid_dir = temp_root / "behavior" / "by_uid"
            credit_source_dir = temp_root / "credit" / "source"
            credit_by_uid_dir = temp_root / "credit" / "by_uid"

            app_source_dir.mkdir(parents=True, exist_ok=True)
            behavior_source_dir.mkdir(parents=True, exist_ok=True)
            credit_source_dir.mkdir(parents=True, exist_ok=True)

            self._write_csv(
                app_source_dir / "mex_usage.csv",
                ["uid", "app_name", "app_package", "first_install_time", "last_update_time"],
                [
                    {
                        "uid": "u100",
                        "app_name": "Kueski",
                        "app_package": "com.kueski.app",
                        "first_install_time": "1713000000000",
                        "last_update_time": "1713500000000",
                    }
                ],
            )
            self._write_csv(
                app_source_dir / "mex_label.csv",
                ["app_package", "app_name", "gp_category", "ai_category_level_2_CN"],
                [
                    {
                        "app_package": "com.kueski.app",
                        "app_name": "Kueski",
                        "gp_category": "Finance",
                        "ai_category_level_2_CN": "Loan",
                    }
                ],
            )

            settings.app_source_dir = str(app_source_dir)
            settings.app_by_uid_dir = str(app_by_uid_dir)
            settings.behavior_source_dir = str(behavior_source_dir)
            settings.behavior_by_uid_dir = str(behavior_by_uid_dir)
            settings.credit_source_dir = str(credit_source_dir)
            settings.credit_by_uid_dir = str(credit_by_uid_dir)

            app_result = prepare_local_data("app")
            self.assertEqual(app_result["app"]["status"], "prepared")
            self.assertTrue((app_by_uid_dir / "u100.csv").exists())

            all_result = prepare_local_data("all")
            self.assertIn(all_result["behavior"]["status"], {"skipped", "prepared"})
            self.assertIn(all_result["credit"]["status"], {"skipped", "prepared"})
            self.assertEqual(all_result["behavior"]["status"], "skipped")
            self.assertEqual(all_result["credit"]["status"], "skipped")

    def _seed_local_repository_base(self, data_root: Path) -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        self._write_csv(
            data_root / "sample_behavior_data.csv",
            ["uid", "avg_session_minutes", "login_days_30d", "purchase_preference"],
            [{"uid": "stub_uid", "avg_session_minutes": "10", "login_days_30d": "2", "purchase_preference": "x"}],
        )
        (data_root / "sample_credit_data.json").write_text("[]", encoding="utf-8")

    def _write_valid_app_uid_csv(self, path: Path, *, uid: str, app_name: str) -> None:
        self._write_csv(
            path,
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
                    "uid": uid,
                    "app_name": app_name,
                    "app_package": "com.example.app",
                    "first_install_time": "1713000000000",
                    "last_update_time": "1713500000000",
                    "gp_category": "Finance",
                    "ai_category_level_2_CN": "Loan",
                }
            ],
        )

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
