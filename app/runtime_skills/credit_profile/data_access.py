"""Data access layer for the Credit profile pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.logger import get_logger
from app.repositories.base import BaseUserRepository
from app.runtime_skills.credit_profile.contracts import (
    CreditRawData,
    CreditRunContext,
    build_empty_prepared_record,
)
from app.scripts.credit_prepared_builder import prepare_credit_record_from_payload


logger = get_logger(__name__)


class CreditDataProvider:
    """Adapt repository output into a stable prepared Credit contract."""

    def __init__(self, repository: BaseUserRepository) -> None:
        self.repository = repository

    def fetch(self, uid: str, context: CreditRunContext) -> CreditRawData:
        """v6.1 路径 Q：按 profile_mode 分支。"""
        if context.get("profile_mode") == "risk_features":
            return self._fetch_risk_features(uid, context)
        return self._fetch_buro(uid, context)

    def _fetch_buro(self, uid: str, context: CreditRunContext) -> CreditRawData:
        """原 mx Buró 解读逻辑 — 行为零变更。"""
        raw_payload = self.repository.get_credit_data(uid) or {}
        fetched_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        if not isinstance(raw_payload, dict) or not raw_payload:
            logger.warning("Credit raw data missing uid=%s", uid)
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type="",
                origin_ref="",
                source_variant="missing",
                prepared_record=build_empty_prepared_record(uid, country_code=context["country_code"]),
                data_status="missing",
                fetched_at=fetched_at,
                errors=[],
            )

        source_ref = str(raw_payload.get("source_file", "") or raw_payload.get("source_ref", "") or "")
        source_type = str(raw_payload.get("source_type", "") or "").strip()
        source_variant = str(raw_payload.get("source_kind", "") or "").strip().lower()
        data_status = str(raw_payload.get("data_status", "") or "").strip().lower()
        load_error = str(raw_payload.get("load_error", "") or "").strip()
        if load_error:
            errors.append(load_error)

        if data_status == "invalid":
            logger.warning(
                "Credit raw data invalid uid=%s reason=%s",
                uid,
                load_error or "repository_invalid",
            )
            return self._build_raw_data(
                uid=uid,
                context=context,
                source_type=source_type,
                origin_ref=source_ref,
                source_variant=source_variant or "repository_invalid",
                prepared_record=build_empty_prepared_record(uid, country_code=context["country_code"]),
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors or ["repository_invalid"],
            )

        prepared_record, prep_errors = prepare_credit_record_from_payload(
            uid,
            raw_payload,
            country_code=context["country_code"],
        )
        if prep_errors:
            errors.extend(prep_errors)
        if not prepared_record:
            logger.warning(
                "Credit prepared record invalid uid=%s source_variant=%s errors=%s",
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
                prepared_record=build_empty_prepared_record(uid, country_code=context["country_code"]),
                data_status="invalid",
                fetched_at=fetched_at,
                errors=errors or ["prepared_record_empty"],
            )

        prepared_source_meta = prepared_record.get("source_meta", {})
        return self._build_raw_data(
            uid=uid,
            context=context,
            source_type=source_type or str(prepared_source_meta.get("source_type", "") or ""),
            origin_ref=source_ref or str(prepared_source_meta.get("origin_ref", "") or ""),
            source_variant=source_variant or str(prepared_source_meta.get("source_variant", "") or ""),
            prepared_record=prepared_record,
            data_status="ok",
            fetched_at=fetched_at,
            errors=errors,
        )

    def _fetch_risk_features(self, uid: str, context: CreditRunContext) -> CreditRawData:
        """v6.1 路径 Q：TH 风控特征聚合表分支。

        V1 实现策略：
        - 仅从 repository.get_credit_data(uid) 拿原始 payload
        - 不强行解析 csv（属于后续 plan 范围）
        - prepared_record 用 build_empty_prepared_record(uid, country_code="th") 占位
        - risk_features_record 直接透传 raw_payload.get("risk_features", {}) 或 None
        - 保留哨兵字符串原状不转 None（feature_builder 层负责识别）
        """
        raw_payload = self.repository.get_credit_data(uid) or {}
        fetched_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        if not isinstance(raw_payload, dict) or not raw_payload:
            logger.warning("TH credit raw data missing uid=%s", uid)
            return {
                "uid": uid,
                "country_code": context["country_code"],
                "source_meta": {
                    "source_type": "",
                    "origin_ref": "",
                    "source_variant": "missing",
                    "fetched_at": fetched_at,
                },
                "prepared_record": build_empty_prepared_record(uid, country_code=context["country_code"]),
                "risk_features_record": None,
                "data_status": "missing",
                "errors": [],
            }

        risk_features_record = raw_payload.get("risk_features")
        if not isinstance(risk_features_record, dict):
            risk_features_record = None

        return {
            "uid": uid,
            "country_code": context["country_code"],
            "source_meta": {
                "source_type": str(raw_payload.get("source_type", "") or ""),
                "origin_ref": str(raw_payload.get("source_file", "") or raw_payload.get("source_ref", "") or ""),
                "source_variant": str(raw_payload.get("source_kind", "") or "").strip().lower() or "th_risk_features_v1",
                "fetched_at": fetched_at,
            },
            "prepared_record": build_empty_prepared_record(uid, country_code=context["country_code"]),
            "risk_features_record": risk_features_record,
            "data_status": "ok" if risk_features_record else "missing",
            "errors": errors,
        }

    def _build_raw_data(
        self,
        *,
        uid: str,
        context: CreditRunContext,
        source_type: str,
        origin_ref: str,
        source_variant: str,
        prepared_record: dict[str, object],
        data_status: str,
        fetched_at: str,
        errors: list[str],
        risk_features_record: dict[str, object] | None = None,
    ) -> CreditRawData:
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
                "source_variant": source_variant or str(record_source_meta.get("source_variant", "") or ""),
                "schema_version": str(prepared_record.get("schema_version", "") or ""),
                "fetched_at": fetched_at,
                "trace_id": context.get("trace_id", ""),
            },
            "prepared_record": prepared_record,  # type: ignore[typeddict-item]
            "risk_features_record": risk_features_record,
            "data_status": data_status,
            "errors": errors,
        }
