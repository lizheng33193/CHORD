"""Data access layer for the App profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.logger import get_logger
from app.repositories.base import BaseUserRepository
from app.scripts.app_data_loader import load_app_data
from app.runtime_skills.app_profile.contracts import AppRawData, AppRunContext


logger = get_logger(__name__)


class AppDataProvider:
    """Adapt repository output into a stable App raw-data contract."""

    def __init__(self, repository: BaseUserRepository) -> None:
        self.repository = repository

    def fetch(self, uid: str, context: AppRunContext) -> AppRawData:
        raw_payload = load_app_data(self.repository, uid)
        fetched_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        if not isinstance(raw_payload, dict) or not raw_payload:
            logger.warning("App raw data missing uid=%s", uid)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type="",
                origin_ref="",
                records=[],
                data_status="missing",
                fetched_at=fetched_at,
                errors=[],
            )

        source_ref = str(raw_payload.get("source_file", "") or raw_payload.get("source_ref", "") or "")
        data_status = str(raw_payload.get("data_status", "") or "").strip().lower()
        load_error = str(raw_payload.get("load_error", "") or "").strip()
        records = raw_payload.get("apps", [])
        source_type = str(raw_payload.get("source_type", "") or "").strip()

        if load_error:
            errors.append(load_error)
        if data_status == "invalid":
            logger.warning("App raw data invalid uid=%s reason=%s", uid, load_error or "repository_invalid")
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                records=[],
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors or ["repository_invalid"],
            )

        if not isinstance(records, list):
            errors.append("apps_not_list")
            logger.warning("App raw data invalid uid=%s reason=apps_not_list", uid)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                records=[],
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors,
            )

        if records and not all(isinstance(record, dict) for record in records):
            errors.append("apps_contains_non_object_row")
            logger.warning("App raw data invalid uid=%s reason=apps_contains_non_object_row", uid)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                records=[],
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors,
            )

        normalized_records = [dict(record) for record in records]
        if not normalized_records:
            logger.warning("App raw data missing uid=%s source=%s", uid, source_ref)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                records=[],
                data_status="missing",
                fetched_at=fetched_at,
                errors=errors,
            )

        return self._build_raw_data(
            uid=uid,
            context=context,
            source_type=source_type,
            origin_ref=source_ref,
            records=normalized_records,
            data_status="ok",
            fetched_at=fetched_at,
            errors=errors,
        )

    def _build_raw_data(
        self,
        *,
        uid: str,
        context: AppRunContext,
        source_type: str,
        origin_ref: str,
        records: list[dict[str, Any]],
        data_status: str,
        fetched_at: str,
        errors: list[str],
    ) -> AppRawData:
        resolved_source_type = (
            source_type
            or (
                "local_file"
                if origin_ref and str(context["source_preference"] or "").lower() == "local"
                else str(context["source_preference"] or "unknown")
            )
        )
        return {
            "uid": uid,
            "country_code": context["country_code"],
            "source_meta": {
                "source_type": resolved_source_type,
                "origin_ref": origin_ref,
                "fetched_at": fetched_at,
                "trace_id": context.get("trace_id", ""),
            },
            "records": records,
            "data_status": data_status,
            "errors": errors,
        }
