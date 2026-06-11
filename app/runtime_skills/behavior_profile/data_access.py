"""Data access layer for the Behavior profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.logger import get_logger
from app.repositories.base import BaseUserRepository
from app.runtime_skills.behavior_profile.contracts import (
    BehaviorRawData,
    BehaviorRunContext,
    build_empty_prepared_record,
)
from app.scripts.behavior_prepared_builder import prepare_behavior_record_from_payload


logger = get_logger(__name__)


class BehaviorDataProvider:
    """Adapt repository output into a stable prepared Behavior contract."""

    def __init__(self, repository: BaseUserRepository) -> None:
        self.repository = repository

    def fetch(self, uid: str, context: BehaviorRunContext) -> BehaviorRawData:
        raw_payload = self.repository.get_behavior_data(uid) or {}
        fetched_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        if not isinstance(raw_payload, dict) or not raw_payload:
            logger.warning("Behavior raw data missing uid=%s", uid)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type="",
                origin_ref="",
                source_variant="missing",
                prepared_record=build_empty_prepared_record(
                    uid,
                    country_code=context["country_code"],
                ),
                data_status="missing",
                fetched_at=fetched_at,
                errors=[],
            )

        source_ref = str(
            raw_payload.get("source_file", "") or raw_payload.get("source_ref", "") or ""
        )
        source_type = str(raw_payload.get("source_type", "") or "").strip()
        source_variant = str(raw_payload.get("source_kind", "") or "").strip().lower()
        data_status = str(raw_payload.get("data_status", "") or "").strip().lower()
        load_error = str(raw_payload.get("load_error", "") or "").strip()
        if load_error:
            errors.append(load_error)

        if data_status == "invalid":
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                source_variant=source_variant or "repository_invalid",
                prepared_record=build_empty_prepared_record(
                    uid,
                    country_code=context["country_code"],
                ),
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors or ["repository_invalid"],
            )

        prepared_record, prep_errors = prepare_behavior_record_from_payload(
            uid,
            raw_payload,
            country_code=context["country_code"],
        )
        if prep_errors:
            errors.extend(prep_errors)
        if not prepared_record:
            logger.warning(
                "Behavior prepared record invalid uid=%s source_variant=%s errors=%s",
                uid,
                source_variant or "unknown",
                ",".join(errors) or "prepared_record_empty",
            )
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                source_variant=source_variant or "prepared_invalid",
                prepared_record=build_empty_prepared_record(
                    uid,
                    country_code=context["country_code"],
                ),
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors or ["prepared_record_empty"],
            )

        prepared_source_meta = prepared_record.get("source_meta", {})
        return self._build_raw_data(
            uid=uid,
            context=context,
            source_type=source_type
            or str(prepared_source_meta.get("source_type", "") or ""),
            origin_ref=source_ref
            or str(prepared_source_meta.get("origin_ref", "") or ""),
            source_variant=source_variant
            or str(prepared_source_meta.get("source_variant", "") or ""),
            prepared_record=prepared_record,
            data_status="ok",
            fetched_at=fetched_at,
            errors=errors,
        )

    def _build_raw_data(
        self,
        *,
        uid: str,
        context: BehaviorRunContext,
        source_type: str,
        origin_ref: str,
        source_variant: str,
        prepared_record: dict[str, object],
        data_status: str,
        fetched_at: str,
        errors: list[str],
    ) -> BehaviorRawData:
        resolved_source_type = (
            source_type
            or (
                "local_file"
                if origin_ref and str(context["source_preference"] or "").lower() == "local"
                else str(context["source_preference"] or "unknown")
            )
        )
        record_source_meta = (
            prepared_record.get("source_meta", {})
            if isinstance(prepared_record.get("source_meta", {}), dict)
            else {}
        )
        return {
            "uid": uid,
            "country_code": context["country_code"],
            "source_meta": {
                "source_type": resolved_source_type,
                "origin_ref": origin_ref,
                "source_variant": source_variant
                or str(record_source_meta.get("source_variant", "") or ""),
                "schema_version": str(prepared_record.get("schema_version", "") or ""),
                "fetched_at": fetched_at,
                "trace_id": context.get("trace_id", ""),
            },
            "prepared_record": prepared_record,  # type: ignore[typeddict-item]
            "data_status": data_status,
            "errors": errors,
        }
