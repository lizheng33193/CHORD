"""Local repository that reads user data from local sample files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.repositories.base import BaseUserRepository
from app.scripts.behavior_prepared_builder import BEHAVIOR_PREPARED_SCHEMA_VERSION
from app.scripts.credit_prepared_builder import CREDIT_PREPARED_SCHEMA_VERSION


logger = get_logger(__name__)


class LocalUserRepository(BaseUserRepository):
    """Read local sample files and provide uid-based lookup methods.

    This repository is intentionally simple:
    - App data comes from a CSV file.
    - Behavior data comes from a CSV file.
    - Credit data comes from a JSON file.

    The files are loaded once during initialization so each API request can
    reuse the in-memory dictionaries instead of re-reading the files.
    """

    def __init__(self, *, allow_sample_fallback: bool = True) -> None:
        """Load all sample data into memory when the repository is created."""
        self.allow_sample_fallback = allow_sample_fallback
        self.data_dir = settings.resolve_path(settings.data_dir)
        self.app_source_dir = settings.resolve_path(settings.app_source_dir)
        self.app_by_uid_dir = settings.resolve_path(settings.app_by_uid_dir)
        self.behavior_source_dir = settings.resolve_path(settings.behavior_source_dir)
        self.behavior_by_uid_dir = settings.resolve_path(settings.behavior_by_uid_dir)
        self.credit_source_dir = settings.resolve_path(settings.credit_source_dir)
        self.credit_by_uid_dir = settings.resolve_path(settings.credit_by_uid_dir)
        self.legacy_app_by_uid_dirs = [
            self.data_dir / "data" / "data" / "appData" / "appData_by_user",
        ]
        self.behavior_sample_file = self.data_dir / "sample_behavior_data.csv"
        self.credit_sample_file = self.data_dir / "sample_credit_data.json"
        self._behavior_data_by_uid = self._load_csv_by_uid(
            self.behavior_sample_file
        )
        self._credit_data_by_uid = self._load_json_by_uid(
            self.credit_sample_file
        )

    def get_app_data(self, uid: str) -> dict[str, Any]:
        """Return app usage data for the specified uid or an empty structure."""
        file_path = self._resolve_app_uid_file(uid)
        if not file_path.exists():
            logger.warning("App CSV file not found for uid=%s at %s", uid, file_path)
            return {}

        apps: list[dict[str, Any]] = []
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = [str(name).strip() for name in (reader.fieldnames or []) if name]
                required_fields = {
                    "uid",
                    "app_name",
                    "app_package",
                    "first_install_time",
                    "last_update_time",
                    "gp_category",
                    "ai_category_level_2_CN",
                }
                if not required_fields.issubset(set(fieldnames)):
                    missing_fields = sorted(required_fields.difference(fieldnames))
                    logger.warning(
                        "App CSV schema invalid for uid=%s at %s missing=%s",
                        uid,
                        file_path,
                        ",".join(missing_fields),
                    )
                    return {
                        "uid": uid,
                        "source_type": "local_file",
                        "source_file": str(file_path),
                        "apps": [],
                        "data_status": "invalid",
                        "load_error": f"missing_fields:{','.join(missing_fields)}",
                    }
                for row in reader:
                    normalized_row = self._normalize_csv_row(row)
                    if str(normalized_row.get("uid", "")).strip() == str(uid).strip():
                        apps.append(normalized_row)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load app CSV %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "apps": [],
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not apps:
            return {}

        return {
            "uid": uid,
            "source_type": "local_file",
            "source_file": str(file_path),
            "apps": apps,
        }

    def get_behavior_data(self, uid: str) -> dict[str, Any]:
        """Return behavior data with prepared-json priority and raw-csv fallback."""
        normalized_uid = str(uid or "").strip()
        json_path = self.behavior_by_uid_dir / f"{normalized_uid}.json"
        csv_path = self.behavior_by_uid_dir / f"{normalized_uid}.csv"

        if json_path.exists():
            prepared = self._read_behavior_prepared_json(json_path, normalized_uid)
            if prepared:
                return prepared

        if csv_path.exists():
            raw_csv_payload = self._read_behavior_raw_csv_payload(csv_path, normalized_uid)
            if raw_csv_payload:
                return raw_csv_payload

        if not self.allow_sample_fallback:
            return {}

        sample_record = self._get_record_or_empty(self._behavior_data_by_uid, normalized_uid)
        if sample_record:
            return {
                **sample_record,
                "uid": normalized_uid,
                "source_type": "sample_file",
                "source_kind": "legacy_behavior_summary_sample",
                "source_file": str(self.behavior_sample_file),
            }
        return {}

    def get_credit_data(self, uid: str) -> dict[str, Any]:
        """Return credit data with prepared-json priority and raw-csv fallback."""
        normalized_uid = str(uid or "").strip()
        json_path = self.credit_by_uid_dir / f"{normalized_uid}.json"
        csv_path = self.credit_by_uid_dir / f"{normalized_uid}.csv"

        if json_path.exists():
            prepared = self._read_credit_prepared_json(json_path, normalized_uid)
            if prepared:
                return prepared

        if csv_path.exists():
            raw_csv_payload = self._read_credit_raw_csv_payload(csv_path, normalized_uid)
            if raw_csv_payload:
                return raw_csv_payload

        if json_path.exists():
            legacy_summary = self._read_credit_legacy_summary_json(json_path, normalized_uid)
            if legacy_summary:
                return legacy_summary

        if not self.allow_sample_fallback:
            return {}

        sample_record = self._get_record_or_empty(self._credit_data_by_uid, normalized_uid)
        if sample_record:
            return {
                **sample_record,
                "uid": normalized_uid,
                "source_type": "sample_file",
                "source_kind": "legacy_summary_sample",
                "source_file": str(self.credit_sample_file),
            }
        return {}

    def _read_credit_prepared_json(self, file_path: Path, uid: str) -> dict[str, Any]:
        """Return prepared Credit JSON only when it matches the new schema."""
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load credit prepared json %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not isinstance(payload, dict):
            return {}

        # 2026-05-05 修复: 严格校验 schema_version 等于 builder 常量，
        # 避免 data_acquisition_agent V2 落地的“只有 uid” json（schema_version="da_agent_v2"）
        # 被误认为 prepared，从而覆盖 csv 有效数据。
        if payload.get("schema_version") == CREDIT_PREPARED_SCHEMA_VERSION and isinstance(payload.get("source_meta"), dict):
            return {
                **payload,
                "uid": uid,
                "source_type": "local_file",
                "source_kind": "prepared_json",
                "source_file": str(file_path),
            }
        return {}

    def _read_behavior_prepared_json(self, file_path: Path, uid: str) -> dict[str, Any]:
        """Return prepared Behavior JSON only when it matches the new schema."""
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load behavior prepared json %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not isinstance(payload, dict):
            return {}

        # 2026-05-05 修复: 严格校验 schema_version 等于 builder 常量，
        # 避免 data_acquisition_agent V2 落地的“只有 uid” json（schema_version="da_agent_v2"）
        # 被误认为 prepared，从而覆盖 csv 有效数据。
        if payload.get("schema_version") == BEHAVIOR_PREPARED_SCHEMA_VERSION and isinstance(payload.get("source_meta"), dict):
            return {
                **payload,
                "uid": uid,
                "source_type": "local_file",
                "source_kind": "prepared_json",
                "source_file": str(file_path),
            }
        return {}

    def _read_behavior_raw_csv_payload(self, file_path: Path, uid: str) -> dict[str, Any]:
        """Return raw uid-scoped Behavior CSV rows without business interpretation."""
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = {
                    str(name).strip() for name in (reader.fieldnames or []) if name
                }
                if not fieldnames:
                    return {
                        "uid": uid,
                        "source_type": "local_file",
                        "source_kind": "raw_behavior_csv",
                        "source_file": str(file_path),
                        "data_status": "invalid",
                        "load_error": "missing_csv_header",
                    }
                rows = [self._normalize_csv_row(row) for row in reader]
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load raw behavior csv %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_kind": "raw_behavior_csv",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not rows:
            return {}

        return {
            "uid": uid,
            "source_type": "local_file",
            "source_kind": "raw_behavior_csv",
            "source_file": str(file_path),
            "rows": rows,
        }

    def _read_credit_raw_csv_payload(self, file_path: Path, uid: str) -> dict[str, Any]:
        """Return raw uid-scoped Credit CSV rows without business interpretation."""
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = {str(name).strip() for name in (reader.fieldnames or []) if name}
                if not fieldnames:
                    return {
                        "uid": uid,
                        "source_type": "local_file",
                        "source_kind": "raw_credit_csv",
                        "source_file": str(file_path),
                        "data_status": "invalid",
                        "load_error": "missing_csv_header",
                    }
                rows = [self._normalize_csv_row(row) for row in reader]
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load raw credit csv %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_kind": "raw_credit_csv",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not rows:
            return {}

        return {
            "uid": uid,
            "source_type": "local_file",
            "source_kind": "raw_credit_csv",
            "source_file": str(file_path),
            "rows": rows,
        }

    def _read_credit_legacy_summary_json(self, file_path: Path, uid: str) -> dict[str, Any]:
        """Return legacy three-field summary JSON when prepared JSON is absent."""
        result = self._read_uid_json_record(
            file_path=file_path,
            uid=uid,
            required_fields={"uid", "credit_score_band", "repayment_status", "risk_level"},
        )
        if not result:
            return {}
        result["source_kind"] = "legacy_summary_json"
        return result

    def _load_csv_by_uid(self, file_path: Path) -> dict[str, dict[str, Any]]:
        """Load a CSV file and index records by uid."""
        records: dict[str, dict[str, Any]] = {}
        if not file_path.exists():
            logger.warning("CSV file not found: %s", file_path)
            return records

        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    normalized_row = self._normalize_csv_row(row)
                    uid = str(normalized_row.get("uid", "")).strip()
                    if uid:
                        records[uid] = normalized_row
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load CSV %s: %s", file_path, exc)

        return records

    def _load_json_by_uid(self, file_path: Path) -> dict[str, dict[str, Any]]:
        """Load a JSON list file and index records by uid."""
        if not file_path.exists():
            logger.warning("JSON file not found: %s", file_path)
            return {}

        records: dict[str, dict[str, Any]] = {}
        try:
            with file_path.open("r", encoding="utf-8") as json_file:
                raw_records = json.load(json_file)
            for record in raw_records:
                uid = str(record.get("uid", "")).strip()
                if uid:
                    records[uid] = record
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load JSON %s: %s", file_path, exc)

        return records

    def _normalize_csv_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Convert CSV string values into more useful Python data types."""
        normalized_row: dict[str, Any] = {}

        for key, value in row.items():
            if value is None:
                normalized_row[key] = None
                continue

            stripped_value = value.strip()

            if key == "installed_apps":
                normalized_row[key] = [
                    app_name.strip() for app_name in stripped_value.split("|") if app_name.strip()
                ]
            elif stripped_value.isdigit():
                normalized_row[key] = int(stripped_value)
            else:
                normalized_row[key] = stripped_value

        return normalized_row

    def _read_uid_csv_record(
        self,
        *,
        file_path: Path,
        uid: str,
        required_fields: set[str],
    ) -> dict[str, Any]:
        """Read one uid-scoped CSV record with minimal schema validation."""
        if not file_path.exists():
            return {}

        rows: list[dict[str, Any]] = []
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = {str(name).strip() for name in (reader.fieldnames or []) if name}
                if not required_fields.issubset(fieldnames):
                    missing_fields = sorted(required_fields.difference(fieldnames))
                    logger.warning(
                        "UID CSV schema invalid for uid=%s at %s missing=%s",
                        uid,
                        file_path,
                        ",".join(missing_fields),
                    )
                    return {
                        "uid": uid,
                        "source_type": "local_file",
                        "source_file": str(file_path),
                        "data_status": "invalid",
                        "load_error": f"missing_fields:{','.join(missing_fields)}",
                    }
                for row in reader:
                    normalized_row = self._normalize_csv_row(row)
                    if str(normalized_row.get("uid", "")).strip() == str(uid).strip():
                        rows.append(normalized_row)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load uid CSV %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not rows:
            return {}
        if len(rows) > 1:
            logger.warning(
                "UID CSV contains multiple rows for uid=%s at %s rows=%s",
                uid,
                file_path,
                len(rows),
            )
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": "multiple_rows_not_supported",
            }

        return {
            **rows[0],
            "source_type": "local_file",
            "source_file": str(file_path),
        }

    def _read_uid_json_record(
        self,
        *,
        file_path: Path,
        uid: str,
        required_fields: set[str],
    ) -> dict[str, Any]:
        """Read one uid-scoped JSON object with minimal schema validation."""
        if not file_path.exists():
            return {}

        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load uid JSON %s: %s", file_path, exc)
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": str(exc),
            }

        if not isinstance(payload, dict):
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": "json_payload_not_object",
            }

        normalized_payload = {
            str(key).strip(): value for key, value in payload.items()
        }
        fieldnames = set(normalized_payload.keys())
        if not required_fields.issubset(fieldnames):
            missing_fields = sorted(required_fields.difference(fieldnames))
            logger.warning(
                "UID JSON schema invalid for uid=%s at %s missing=%s",
                uid,
                file_path,
                ",".join(missing_fields),
            )
            return {
                "uid": uid,
                "source_type": "local_file",
                "source_file": str(file_path),
                "data_status": "invalid",
                "load_error": f"missing_fields:{','.join(missing_fields)}",
            }

        if str(normalized_payload.get("uid", "")).strip() != str(uid).strip():
            return {}

        return {
            **normalized_payload,
            "source_type": "local_file",
            "source_file": str(file_path),
        }

    def _resolve_app_uid_file(self, uid: str) -> Path:
        """Resolve an App uid CSV with new-path priority and legacy fallback."""
        normalized_uid = str(uid or "").strip()
        new_path = self.app_by_uid_dir / f"{normalized_uid}.csv"
        if new_path.exists():
            return new_path

        for legacy_dir in self.legacy_app_by_uid_dirs:
            legacy_path = legacy_dir / f"{normalized_uid}.csv"
            if legacy_path.exists():
                return legacy_path

        return new_path

    def _resolve_credit_uid_file(self, uid: str) -> tuple[Path | None, str]:
        """Resolve a Credit uid file from the new by_uid directory."""
        normalized_uid = str(uid or "").strip()
        json_path = self.credit_by_uid_dir / f"{normalized_uid}.json"
        if json_path.exists():
            return json_path, "json"
        csv_path = self.credit_by_uid_dir / f"{normalized_uid}.csv"
        if csv_path.exists():
            return csv_path, "csv"
        return None, ""

    def _get_record_or_empty(
        self,
        records_by_uid: dict[str, dict[str, Any]],
        uid: str,
    ) -> dict[str, Any]:
        """Return a record for the uid, or an empty dictionary if it is missing."""
        return records_by_uid.get(uid, {})
