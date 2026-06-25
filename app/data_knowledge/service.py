"""Service layer for data knowledge assets, seed import, and M2A retrieval support."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.permissions import normalize_country_scope_value, require_permission, require_permissions
from app.core.user_context import UserContext
from app.data_knowledge.models import (
    DataCatalogField,
    DataCatalogTable,
    DataGlossaryTerm,
    DataSqlErrorCase,
    DataSqlExample,
)
from app.data_knowledge.repository import DataKnowledgeRepository
from app.data_knowledge.schemas import (
    CatalogFieldCreateRequest,
    CatalogFieldItem,
    CatalogFieldListResponse,
    CatalogFieldUpdateRequest,
    CatalogTableCreateRequest,
    CatalogTableItem,
    CatalogTableListResponse,
    CatalogTableUpdateRequest,
    GlossaryCreateRequest,
    GlossaryItem,
    GlossaryListResponse,
    GlossaryUpdateRequest,
    SeedImportResponse,
    SqlErrorCaseCreateRequest,
    SqlErrorCaseItem,
    SqlErrorCaseListResponse,
    SqlErrorCaseUpdateRequest,
    SqlExampleCreateRequest,
    SqlExampleItem,
    SqlExampleListResponse,
    SqlExampleUpdateRequest,
)


DATA_KNOWLEDGE_SEED_DIR = Path(__file__).resolve().parents[2] / "data_knowledge_seed"
_SUPPORTED_BUNDLES = {"mx", "ph", "common"}
_CATALOG_SOURCE_NAMESPACE = {
    "mx": "seed/mx/catalog",
    "ph": "seed/ph/catalog",
}
_GLOSSARY_SOURCE_NAMESPACE = {
    "mx": "seed/mx/glossary",
    "ph": "seed/ph/glossary",
    "common": "seed/common/glossary",
}
_SQL_EXAMPLE_SOURCE_NAMESPACE = {
    "mx": "seed/mx/sql_examples",
    "ph": "seed/ph/sql_examples",
}
_SQL_ERROR_CASE_SOURCE_NAMESPACE = {
    "ph": "seed/ph/error_cases",
}


def _normalize_json_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(_normalize_json_payload(value).encode("utf-8")).hexdigest()


def _bundle_country(bundle: str) -> str | None:
    normalized = str(bundle).strip().lower()
    if normalized == "common":
        return None
    return normalize_country_scope_value(normalized) or normalized


def _normalize_country_for_seed_patch(value: Any) -> str | None:
    normalized = str(value).strip().lower() if value is not None else ""
    if normalized in {"", "common", "null", "none"}:
        return None
    return normalize_country_scope_value(normalized) or normalized


class DataKnowledgeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DataKnowledgeRepository(db)

    def list_catalog_tables(self, *, ctx: UserContext) -> CatalogTableListResponse:
        require_permission(ctx, "data:knowledge:read")
        rows = self.repo.list_by_scope(
            DataCatalogTable,
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        return CatalogTableListResponse(items=[self._serialize_catalog_table(row) for row in rows])

    def list_catalog_fields(self, *, ctx: UserContext) -> CatalogFieldListResponse:
        require_permission(ctx, "data:knowledge:read")
        rows = self.repo.list_by_scope(
            DataCatalogField,
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        return CatalogFieldListResponse(items=[self._serialize_catalog_field(row) for row in rows])

    def list_glossary(self, *, ctx: UserContext) -> GlossaryListResponse:
        require_permission(ctx, "data:knowledge:read")
        rows = self.repo.list_by_scope(
            DataGlossaryTerm,
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        return GlossaryListResponse(items=[self._serialize_glossary(row) for row in rows])

    def list_examples(self, *, ctx: UserContext) -> SqlExampleListResponse:
        require_permission(ctx, "data:knowledge:read")
        can_view_sql = "data:query:view_sql" in ctx.permissions or ctx.is_superuser
        rows = self.repo.list_by_scope(
            DataSqlExample,
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        return SqlExampleListResponse(items=[self._serialize_sql_example(row, can_view_sql=can_view_sql) for row in rows])

    def list_error_cases(self, *, ctx: UserContext) -> SqlErrorCaseListResponse:
        require_permission(ctx, "data:knowledge:read")
        can_view_sql = "data:query:view_sql" in ctx.permissions or ctx.is_superuser
        rows = self.repo.list_by_scope(
            DataSqlErrorCase,
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(ctx.country) if ctx.country else None,
        )
        return SqlErrorCaseListResponse(items=[self._serialize_error_case(row, can_view_sql=can_view_sql) for row in rows])

    def import_seed_bundle(self, *, bundle: str, project_id: int | None, actor_username: str) -> dict[str, int | str]:
        if bundle not in _SUPPORTED_BUNDLES:
            raise HTTPException(status_code=400, detail=f"unsupported seed bundle: {bundle}")
        country = _bundle_country(bundle)
        upserted = 0
        deprecated = 0
        if bundle != "common":
            upserted += self._import_catalog_seed(bundle=bundle, country=country, project_id=project_id, actor_username=actor_username)
            upserted += self._import_sql_examples_seed(bundle=bundle, country=country, project_id=project_id, actor_username=actor_username)
            upserted += self._import_sql_error_cases_seed(bundle=bundle, country=country, project_id=project_id, actor_username=actor_username)
            deprecated += self._deprecate_removed_namespace_rows(
                DataCatalogTable,
                project_id=project_id,
                country=country,
                source_namespace=_CATALOG_SOURCE_NAMESPACE[bundle],
                seen_keys=self._seen_keys_for_namespace(bundle, "catalog"),
            )
            deprecated += self._deprecate_removed_namespace_rows(
                DataCatalogField,
                project_id=project_id,
                country=country,
                source_namespace=_CATALOG_SOURCE_NAMESPACE[bundle],
                seen_keys=self._seen_field_keys_for_namespace(bundle),
            )
            deprecated += self._deprecate_removed_namespace_rows(
                DataSqlExample,
                project_id=project_id,
                country=country,
                source_namespace=_SQL_EXAMPLE_SOURCE_NAMESPACE[bundle],
                seen_keys=self._seen_keys_for_namespace(bundle, "sql_examples"),
            )
            if bundle in _SQL_ERROR_CASE_SOURCE_NAMESPACE:
                deprecated += self._deprecate_removed_namespace_rows(
                    DataSqlErrorCase,
                    project_id=project_id,
                    country=country,
                    source_namespace=_SQL_ERROR_CASE_SOURCE_NAMESPACE[bundle],
                    seen_keys=self._seen_keys_for_namespace(bundle, "error_cases"),
                )
        upserted += self._import_glossary_seed(bundle=bundle, country=country, project_id=project_id, actor_username=actor_username)
        deprecated += self._deprecate_removed_namespace_rows(
            DataGlossaryTerm,
            project_id=project_id,
            country=country,
            source_namespace=_GLOSSARY_SOURCE_NAMESPACE[bundle],
            seen_keys=self._seen_keys_for_namespace(bundle, "glossary"),
        )
        self.db.commit()
        return {"bundle": bundle, "upserted": upserted, "deprecated": deprecated}

    def import_seed_bundle_for_ctx(self, *, ctx: UserContext, bundle: str) -> SeedImportResponse:
        require_permission(ctx, "data:knowledge:manage")
        result = self.import_seed_bundle(
            bundle=bundle,
            project_id=self._project_id(ctx),
            actor_username=ctx.username,
        )
        return SeedImportResponse(**result)

    def import_seed_patch(self, *, path: Path, project_id: int | None, actor_username: str) -> dict[str, int | str]:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="seed patch must be a mapping")
        source_namespace = str(payload.get("source_namespace") or "").strip()
        if not source_namespace:
            raise HTTPException(status_code=400, detail="seed patch source_namespace is required")

        upserted = 0
        deprecated = 0
        seen_by_family: dict[tuple[type, str | None], set[str]] = {}

        def remember(model, country: str | None, source_key: str) -> None:
            seen_by_family.setdefault((model, country), set()).add(source_key)

        for entry in payload.get("catalog_tables") or []:
            country = _normalize_country_for_seed_patch(entry.get("country"))
            source_key = str(entry["source_key"])
            remember(DataCatalogTable, country, source_key)
            table_payload = {
                "table_name": entry["table_name"],
                "domain": entry.get("domain"),
                "description": entry.get("description"),
                "purpose": entry.get("purpose"),
                "grain": entry.get("grain"),
                "time_field": entry.get("time_field"),
                "partition_field": entry.get("partition_field"),
                "join_keys": entry.get("join_keys") or [],
                "common_filters": entry.get("common_filters") or [],
                "metadata": entry.get("metadata") or {},
            }
            upserted += self._upsert_catalog_table_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=source_key,
                actor_username=actor_username,
                payload=table_payload,
            )

        for entry in payload.get("catalog_fields") or []:
            country = _normalize_country_for_seed_patch(entry.get("country"))
            source_key = str(entry["source_key"])
            remember(DataCatalogField, country, source_key)
            field_payload = {
                "table_name": entry["table_name"],
                "field_name": entry["field_name"],
                "field_type": entry.get("field_type"),
                "description": entry.get("description"),
                "business_meaning": entry.get("business_meaning"),
                "is_sensitive": entry.get("is_sensitive", False),
                "join_hint": entry.get("join_hint"),
                "metadata": entry.get("metadata") or {},
            }
            upserted += self._upsert_catalog_field_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=source_key,
                actor_username=actor_username,
                payload=field_payload,
            )

        for entry in payload.get("glossary_terms") or []:
            country = _normalize_country_for_seed_patch(entry.get("country"))
            source_key = str(entry["source_key"])
            remember(DataGlossaryTerm, country, source_key)
            glossary_payload = {
                "term": entry["term"],
                "synonyms": entry.get("synonyms") or [],
                "definition": entry.get("definition"),
                "mapped_tables": entry.get("mapped_tables") or [],
                "mapped_fields": entry.get("mapped_fields") or [],
                "suggested_filters": entry.get("suggested_filters") or [],
            }
            upserted += self._upsert_glossary_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=source_key,
                actor_username=actor_username,
                payload=glossary_payload,
            )

        for entry in payload.get("sql_examples") or []:
            country = _normalize_country_for_seed_patch(entry.get("country"))
            source_key = str(entry["source_key"])
            remember(DataSqlExample, country, source_key)
            example_payload = {
                "natural_language_request": entry["natural_language_request"],
                "run_type": entry.get("run_type") or "cohort_query",
                "output_bucket": entry.get("output_bucket"),
                "sql_hash": entry["sql_hash"],
                "sql_text": entry.get("sql_text"),
                "tables_used": entry.get("tables_used") or [],
                "fields_used": entry.get("fields_used") or [],
                "pattern_summary": entry.get("pattern_summary"),
                "reviewer_username": entry.get("reviewer_username"),
                "execution_status": entry.get("execution_status"),
            }
            upserted += self._upsert_sql_example_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=source_key,
                actor_username=actor_username,
                payload=example_payload,
            )

        for entry in payload.get("sql_error_cases") or []:
            country = _normalize_country_for_seed_patch(entry.get("country"))
            source_key = str(entry["source_key"])
            remember(DataSqlErrorCase, country, source_key)
            error_payload = {
                "natural_language_request": entry.get("natural_language_request"),
                "run_type": entry.get("run_type"),
                "output_bucket": entry.get("output_bucket"),
                "error_type": entry["error_type"],
                "error_message": entry.get("error_message"),
                "failed_sql_hash": entry.get("failed_sql_hash"),
                "failed_sql_text": entry.get("failed_sql_text"),
                "fixed_sql_hash": entry.get("fixed_sql_hash"),
                "fixed_sql_text": entry.get("fixed_sql_text"),
                "fix_summary": entry.get("fix_summary"),
                "detected_tables": entry.get("detected_tables") or [],
                "detected_fields": entry.get("detected_fields") or [],
                "status": entry.get("status") or "open",
            }
            upserted += self._upsert_sql_error_case_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=source_key,
                actor_username=actor_username,
                payload=error_payload,
            )

        for (model, country), seen_keys in seen_by_family.items():
            deprecated += self._deprecate_removed_namespace_rows(
                model,
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                seen_keys=seen_keys,
            )
        self.db.commit()
        return {"source_namespace": source_namespace, "upserted": upserted, "deprecated": deprecated}

    def create_catalog_table(self, *, ctx: UserContext, body: CatalogTableCreateRequest) -> CatalogTableItem:
        require_permission(ctx, "data:knowledge:write")
        payload = body.model_dump(mode="json")
        row = DataCatalogTable(
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(body.country) if body.country else None,
            status=body.status,
            source_type=body.source_type,
            source_namespace=body.source_namespace,
            source_key=body.source_key,
            source_hash=_hash_payload(payload),
            created_by=ctx.username,
            updated_by=ctx.username,
            table_name=body.table_name,
            domain=body.domain,
            description=body.description,
            purpose=body.purpose,
            grain=body.grain,
            time_field=body.time_field,
            partition_field=body.partition_field,
            join_keys_json=body.join_keys,
            common_filters_json=body.common_filters,
            metadata_json=body.metadata,
        )
        self.repo.add(row)
        self.db.commit()
        return self._serialize_catalog_table(row)

    def update_catalog_table(self, *, ctx: UserContext, row_id: int, body: CatalogTableUpdateRequest) -> CatalogTableItem:
        require_permission(ctx, "data:knowledge:write")
        row = self._get_owned_row(DataCatalogTable, row_id, project_id=self._project_id(ctx))
        self._apply_updates(row, body.model_dump(exclude_unset=True), updated_by=ctx.username)
        self.db.commit()
        return self._serialize_catalog_table(row)

    def create_catalog_field(self, *, ctx: UserContext, body: CatalogFieldCreateRequest) -> CatalogFieldItem:
        require_permission(ctx, "data:knowledge:write")
        payload = body.model_dump(mode="json")
        row = DataCatalogField(
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(body.country) if body.country else None,
            status=body.status,
            source_type=body.source_type,
            source_namespace=body.source_namespace,
            source_key=body.source_key,
            source_hash=_hash_payload(payload),
            created_by=ctx.username,
            updated_by=ctx.username,
            table_name=body.table_name,
            field_name=body.field_name,
            field_type=body.field_type,
            description=body.description,
            business_meaning=body.business_meaning,
            is_sensitive="true" if body.is_sensitive else "false",
            join_hint=body.join_hint,
            metadata_json=body.metadata,
        )
        self.repo.add(row)
        self.db.commit()
        return self._serialize_catalog_field(row)

    def update_catalog_field(self, *, ctx: UserContext, row_id: int, body: CatalogFieldUpdateRequest) -> CatalogFieldItem:
        require_permission(ctx, "data:knowledge:write")
        row = self._get_owned_row(DataCatalogField, row_id, project_id=self._project_id(ctx))
        payload = body.model_dump(exclude_unset=True)
        if "is_sensitive" in payload:
            payload["is_sensitive"] = "true" if payload["is_sensitive"] else "false"
        self._apply_updates(row, payload, updated_by=ctx.username)
        self.db.commit()
        return self._serialize_catalog_field(row)

    def create_glossary(self, *, ctx: UserContext, body: GlossaryCreateRequest) -> GlossaryItem:
        require_permission(ctx, "data:knowledge:write")
        payload = body.model_dump(mode="json")
        row = DataGlossaryTerm(
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(body.country) if body.country else None,
            status=body.status,
            source_type=body.source_type,
            source_namespace=body.source_namespace,
            source_key=body.source_key,
            source_hash=_hash_payload(payload),
            created_by=ctx.username,
            updated_by=ctx.username,
            term=body.term,
            synonyms_json=body.synonyms,
            definition=body.definition,
            mapped_tables_json=body.mapped_tables,
            mapped_fields_json=body.mapped_fields,
            suggested_filters_json=body.suggested_filters,
        )
        self.repo.add(row)
        self.db.commit()
        return self._serialize_glossary(row)

    def update_glossary(self, *, ctx: UserContext, row_id: int, body: GlossaryUpdateRequest) -> GlossaryItem:
        require_permission(ctx, "data:knowledge:write")
        row = self._get_owned_row(DataGlossaryTerm, row_id, project_id=self._project_id(ctx))
        self._apply_updates(row, body.model_dump(exclude_unset=True), updated_by=ctx.username)
        self.db.commit()
        return self._serialize_glossary(row)

    def create_sql_example(self, *, ctx: UserContext, body: SqlExampleCreateRequest) -> SqlExampleItem:
        require_permissions(ctx, ("data:knowledge:write", "data:query:view_sql"))
        payload = body.model_dump(mode="json")
        row = DataSqlExample(
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(body.country) if body.country else None,
            status=body.status,
            source_type=body.source_type,
            source_namespace=body.source_namespace,
            source_key=body.source_key,
            source_hash=_hash_payload(payload),
            created_by=ctx.username,
            updated_by=ctx.username,
            natural_language_request=body.natural_language_request,
            run_type=body.run_type,
            output_bucket=body.output_bucket,
            sql_hash=body.sql_hash,
            sql_text=body.sql_text,
            tables_used_json=body.tables_used,
            fields_used_json=body.fields_used,
            pattern_summary=body.pattern_summary,
            reviewer_username=body.reviewer_username,
            execution_status=body.execution_status,
        )
        self.repo.add(row)
        self.db.commit()
        return self._serialize_sql_example(row, can_view_sql=True)

    def update_sql_example(self, *, ctx: UserContext, row_id: int, body: SqlExampleUpdateRequest) -> SqlExampleItem:
        require_permissions(ctx, ("data:knowledge:write", "data:query:view_sql"))
        row = self._get_owned_row(DataSqlExample, row_id, project_id=self._project_id(ctx))
        self._apply_updates(row, body.model_dump(exclude_unset=True), updated_by=ctx.username)
        self.db.commit()
        return self._serialize_sql_example(row, can_view_sql=True)

    def create_sql_error_case(self, *, ctx: UserContext, body: SqlErrorCaseCreateRequest) -> SqlErrorCaseItem:
        require_permissions(ctx, ("data:knowledge:write", "data:query:view_sql"))
        payload = body.model_dump(mode="json")
        row = DataSqlErrorCase(
            project_id=self._project_id(ctx),
            country=normalize_country_scope_value(body.country) if body.country else None,
            status=body.status,
            source_type=body.source_type,
            source_namespace=body.source_namespace,
            source_key=body.source_key,
            source_hash=_hash_payload(payload),
            created_by=ctx.username,
            updated_by=ctx.username,
            natural_language_request=body.natural_language_request,
            run_type=body.run_type,
            output_bucket=body.output_bucket,
            error_type=body.error_type,
            error_message=body.error_message,
            failed_sql_hash=body.failed_sql_hash,
            failed_sql_text=body.failed_sql_text,
            fixed_sql_hash=body.fixed_sql_hash,
            fixed_sql_text=body.fixed_sql_text,
            fix_summary=body.fix_summary,
            detected_tables_json=body.detected_tables,
            detected_fields_json=body.detected_fields,
        )
        self.repo.add(row)
        self.db.commit()
        return self._serialize_error_case(row, can_view_sql=True)

    def update_sql_error_case(self, *, ctx: UserContext, row_id: int, body: SqlErrorCaseUpdateRequest) -> SqlErrorCaseItem:
        require_permissions(ctx, ("data:knowledge:write", "data:query:view_sql"))
        row = self._get_owned_row(DataSqlErrorCase, row_id, project_id=self._project_id(ctx))
        self._apply_updates(row, body.model_dump(exclude_unset=True), updated_by=ctx.username)
        self.db.commit()
        return self._serialize_error_case(row, can_view_sql=True)

    def _import_catalog_seed(self, *, bundle: str, country: str | None, project_id: int | None, actor_username: str) -> int:
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / "catalog.yaml"
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
        count = 0
        for entry in entries or []:
            table_key = str(entry.get("source_key") or f"table:{entry['table_name']}")
            table_payload = {
                "table_name": entry["table_name"],
                "domain": entry.get("domain"),
                "description": entry.get("description"),
                "purpose": entry.get("purpose"),
                "grain": entry.get("grain"),
                "time_field": entry.get("time_field"),
                "partition_field": entry.get("partition_field"),
                "join_keys": entry.get("join_keys") or [],
                "common_filters": entry.get("common_filters") or [],
                "metadata": entry.get("metadata") or {},
            }
            count += self._upsert_catalog_table_seed(
                project_id=project_id,
                country=country,
                source_namespace=_CATALOG_SOURCE_NAMESPACE[bundle],
                source_key=table_key,
                actor_username=actor_username,
                payload=table_payload,
            )
            for field in entry.get("fields") or []:
                field_key = str(field.get("source_key") or f"field:{entry['table_name']}.{field['field_name']}")
                field_payload = {
                    "table_name": entry["table_name"],
                    "field_name": field["field_name"],
                    "field_type": field.get("field_type"),
                    "description": field.get("description"),
                    "business_meaning": field.get("business_meaning"),
                    "is_sensitive": field.get("is_sensitive", False),
                    "join_hint": field.get("join_hint"),
                    "metadata": field.get("metadata") or {},
                }
                count += self._upsert_catalog_field_seed(
                    project_id=project_id,
                    country=country,
                    source_namespace=_CATALOG_SOURCE_NAMESPACE[bundle],
                    source_key=field_key,
                    actor_username=actor_username,
                    payload=field_payload,
                )
        return count

    def _import_glossary_seed(self, *, bundle: str, country: str | None, project_id: int | None, actor_username: str) -> int:
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / "glossary.yaml"
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
        count = 0
        for entry in entries or []:
            payload = {
                "term": entry["term"],
                "synonyms": entry.get("synonyms") or [],
                "definition": entry.get("definition"),
                "mapped_tables": entry.get("mapped_tables") or [],
                "mapped_fields": entry.get("mapped_fields") or [],
                "suggested_filters": entry.get("suggested_filters") or [],
            }
            count += self._upsert_glossary_seed(
                project_id=project_id,
                country=country,
                source_namespace=_GLOSSARY_SOURCE_NAMESPACE[bundle],
                source_key=str(entry["source_key"]),
                actor_username=actor_username,
                payload=payload,
            )
        return count

    def _import_sql_examples_seed(self, *, bundle: str, country: str | None, project_id: int | None, actor_username: str) -> int:
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / "sql_examples.yaml"
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
        count = 0
        for entry in entries or []:
            payload = {
                "natural_language_request": entry["natural_language_request"],
                "run_type": entry.get("run_type") or "cohort_query",
                "output_bucket": entry.get("output_bucket"),
                "sql_hash": entry["sql_hash"],
                "sql_text": entry.get("sql_text"),
                "tables_used": entry.get("tables_used") or [],
                "fields_used": entry.get("fields_used") or [],
                "pattern_summary": entry.get("pattern_summary"),
                "reviewer_username": entry.get("reviewer_username"),
                "execution_status": entry.get("execution_status"),
            }
            count += self._upsert_sql_example_seed(
                project_id=project_id,
                country=country,
                source_namespace=_SQL_EXAMPLE_SOURCE_NAMESPACE[bundle],
                source_key=str(entry["source_key"]),
                actor_username=actor_username,
                payload=payload,
            )
        return count

    def _import_sql_error_cases_seed(self, *, bundle: str, country: str | None, project_id: int | None, actor_username: str) -> int:
        source_namespace = _SQL_ERROR_CASE_SOURCE_NAMESPACE.get(bundle)
        if source_namespace is None:
            return 0
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / "error_cases.yaml"
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
        count = 0
        for entry in entries or []:
            payload = {
                "natural_language_request": entry.get("natural_language_request"),
                "run_type": entry.get("run_type"),
                "output_bucket": entry.get("output_bucket"),
                "error_type": entry["error_type"],
                "error_message": entry.get("error_message"),
                "failed_sql_hash": entry.get("failed_sql_hash"),
                "failed_sql_text": entry.get("failed_sql_text"),
                "fixed_sql_hash": entry.get("fixed_sql_hash"),
                "fixed_sql_text": entry.get("fixed_sql_text"),
                "fix_summary": entry.get("fix_summary"),
                "detected_tables": entry.get("detected_tables") or [],
                "detected_fields": entry.get("detected_fields") or [],
                "status": entry.get("status") or "open",
            }
            count += self._upsert_sql_error_case_seed(
                project_id=project_id,
                country=country,
                source_namespace=source_namespace,
                source_key=str(entry["source_key"]),
                actor_username=actor_username,
                payload=payload,
            )
        return count

    def _upsert_catalog_table_seed(self, *, project_id: int | None, country: str | None, source_namespace: str, source_key: str, actor_username: str, payload: dict[str, Any]) -> int:
        row = self.repo.find_by_source_identity(
            DataCatalogTable,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
            source_key=source_key,
        )
        source_hash = _hash_payload(payload)
        if row is None:
            self.repo.add(
                DataCatalogTable(
                    project_id=project_id,
                    country=country,
                    status="active",
                    source_type="seed",
                    source_namespace=source_namespace,
                    source_key=source_key,
                    source_hash=source_hash,
                    created_by=actor_username,
                    updated_by=actor_username,
                    table_name=payload["table_name"],
                    domain=payload.get("domain"),
                    description=payload.get("description"),
                    purpose=payload.get("purpose"),
                    grain=payload.get("grain"),
                    time_field=payload.get("time_field"),
                    partition_field=payload.get("partition_field"),
                    join_keys_json=payload.get("join_keys") or [],
                    common_filters_json=payload.get("common_filters") or [],
                    metadata_json=payload.get("metadata"),
                )
            )
            return 1
        if row.source_hash == source_hash and row.status == "active":
            return 0
        row.status = "active"
        row.source_hash = source_hash
        row.updated_by = actor_username
        row.table_name = payload["table_name"]
        row.domain = payload.get("domain")
        row.description = payload.get("description")
        row.purpose = payload.get("purpose")
        row.grain = payload.get("grain")
        row.time_field = payload.get("time_field")
        row.partition_field = payload.get("partition_field")
        row.join_keys_json = payload.get("join_keys") or []
        row.common_filters_json = payload.get("common_filters") or []
        row.metadata_json = payload.get("metadata")
        self.db.flush()
        return 1

    def _upsert_catalog_field_seed(self, *, project_id: int | None, country: str | None, source_namespace: str, source_key: str, actor_username: str, payload: dict[str, Any]) -> int:
        row = self.repo.find_by_source_identity(
            DataCatalogField,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
            source_key=source_key,
        )
        source_hash = _hash_payload(payload)
        if row is None:
            self.repo.add(
                DataCatalogField(
                    project_id=project_id,
                    country=country,
                    status="active",
                    source_type="seed",
                    source_namespace=source_namespace,
                    source_key=source_key,
                    source_hash=source_hash,
                    created_by=actor_username,
                    updated_by=actor_username,
                    table_name=payload["table_name"],
                    field_name=payload["field_name"],
                    field_type=payload.get("field_type"),
                    description=payload.get("description"),
                    business_meaning=payload.get("business_meaning"),
                    is_sensitive="true" if payload.get("is_sensitive") else "false",
                    join_hint=payload.get("join_hint"),
                    metadata_json=payload.get("metadata"),
                )
            )
            return 1
        if row.source_hash == source_hash and row.status == "active":
            return 0
        row.status = "active"
        row.source_hash = source_hash
        row.updated_by = actor_username
        row.table_name = payload["table_name"]
        row.field_name = payload["field_name"]
        row.field_type = payload.get("field_type")
        row.description = payload.get("description")
        row.business_meaning = payload.get("business_meaning")
        row.is_sensitive = "true" if payload.get("is_sensitive") else "false"
        row.join_hint = payload.get("join_hint")
        row.metadata_json = payload.get("metadata")
        self.db.flush()
        return 1

    def _upsert_glossary_seed(self, *, project_id: int | None, country: str | None, source_namespace: str, source_key: str, actor_username: str, payload: dict[str, Any]) -> int:
        row = self.repo.find_by_source_identity(
            DataGlossaryTerm,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
            source_key=source_key,
        )
        source_hash = _hash_payload(payload)
        if row is None:
            self.repo.add(
                DataGlossaryTerm(
                    project_id=project_id,
                    country=country,
                    status="active",
                    source_type="seed",
                    source_namespace=source_namespace,
                    source_key=source_key,
                    source_hash=source_hash,
                    created_by=actor_username,
                    updated_by=actor_username,
                    term=payload["term"],
                    synonyms_json=payload.get("synonyms") or [],
                    definition=payload.get("definition"),
                    mapped_tables_json=payload.get("mapped_tables") or [],
                    mapped_fields_json=payload.get("mapped_fields") or [],
                    suggested_filters_json=payload.get("suggested_filters") or [],
                )
            )
            return 1
        if row.source_hash == source_hash and row.status == "active":
            return 0
        row.status = "active"
        row.source_hash = source_hash
        row.updated_by = actor_username
        row.term = payload["term"]
        row.synonyms_json = payload.get("synonyms") or []
        row.definition = payload.get("definition")
        row.mapped_tables_json = payload.get("mapped_tables") or []
        row.mapped_fields_json = payload.get("mapped_fields") or []
        row.suggested_filters_json = payload.get("suggested_filters") or []
        self.db.flush()
        return 1

    def _upsert_sql_example_seed(self, *, project_id: int | None, country: str | None, source_namespace: str, source_key: str, actor_username: str, payload: dict[str, Any]) -> int:
        row = self.repo.find_by_source_identity(
            DataSqlExample,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
            source_key=source_key,
        )
        source_hash = _hash_payload(payload)
        if row is None:
            self.repo.add(
                DataSqlExample(
                    project_id=project_id,
                    country=country,
                    status="active",
                    source_type="seed",
                    source_namespace=source_namespace,
                    source_key=source_key,
                    source_hash=source_hash,
                    created_by=actor_username,
                    updated_by=actor_username,
                    natural_language_request=payload["natural_language_request"],
                    run_type=payload["run_type"],
                    output_bucket=payload.get("output_bucket"),
                    sql_hash=payload["sql_hash"],
                    sql_text=payload.get("sql_text"),
                    tables_used_json=payload.get("tables_used") or [],
                    fields_used_json=payload.get("fields_used") or [],
                    pattern_summary=payload.get("pattern_summary"),
                    reviewer_username=payload.get("reviewer_username"),
                    execution_status=payload.get("execution_status"),
                )
            )
            return 1
        if row.source_hash == source_hash and row.status == "active":
            return 0
        row.status = "active"
        row.source_hash = source_hash
        row.updated_by = actor_username
        row.natural_language_request = payload["natural_language_request"]
        row.run_type = payload["run_type"]
        row.output_bucket = payload.get("output_bucket")
        row.sql_hash = payload["sql_hash"]
        row.sql_text = payload.get("sql_text")
        row.tables_used_json = payload.get("tables_used") or []
        row.fields_used_json = payload.get("fields_used") or []
        row.pattern_summary = payload.get("pattern_summary")
        row.reviewer_username = payload.get("reviewer_username")
        row.execution_status = payload.get("execution_status")
        self.db.flush()
        return 1

    def _upsert_sql_error_case_seed(self, *, project_id: int | None, country: str | None, source_namespace: str, source_key: str, actor_username: str, payload: dict[str, Any]) -> int:
        row = self.repo.find_by_source_identity(
            DataSqlErrorCase,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
            source_key=source_key,
        )
        source_hash = _hash_payload(payload)
        if row is None:
            self.repo.add(
                DataSqlErrorCase(
                    project_id=project_id,
                    country=country,
                    status=payload.get("status") or "open",
                    source_type="seed",
                    source_namespace=source_namespace,
                    source_key=source_key,
                    source_hash=source_hash,
                    created_by=actor_username,
                    updated_by=actor_username,
                    natural_language_request=payload.get("natural_language_request"),
                    run_type=payload.get("run_type"),
                    output_bucket=payload.get("output_bucket"),
                    error_type=payload["error_type"],
                    error_message=payload.get("error_message"),
                    failed_sql_hash=payload.get("failed_sql_hash"),
                    failed_sql_text=payload.get("failed_sql_text"),
                    fixed_sql_hash=payload.get("fixed_sql_hash"),
                    fixed_sql_text=payload.get("fixed_sql_text"),
                    fix_summary=payload.get("fix_summary"),
                    detected_tables_json=payload.get("detected_tables") or [],
                    detected_fields_json=payload.get("detected_fields") or [],
                )
            )
            return 1
        if row.source_hash == source_hash and row.status == (payload.get("status") or "open"):
            return 0
        row.status = payload.get("status") or "open"
        row.source_hash = source_hash
        row.updated_by = actor_username
        row.natural_language_request = payload.get("natural_language_request")
        row.run_type = payload.get("run_type")
        row.output_bucket = payload.get("output_bucket")
        row.error_type = payload["error_type"]
        row.error_message = payload.get("error_message")
        row.failed_sql_hash = payload.get("failed_sql_hash")
        row.failed_sql_text = payload.get("failed_sql_text")
        row.fixed_sql_hash = payload.get("fixed_sql_hash")
        row.fixed_sql_text = payload.get("fixed_sql_text")
        row.fix_summary = payload.get("fix_summary")
        row.detected_tables_json = payload.get("detected_tables") or []
        row.detected_fields_json = payload.get("detected_fields") or []
        self.db.flush()
        return 1

    def _deprecate_removed_namespace_rows(self, model, *, project_id: int | None, country: str | None, source_namespace: str, seen_keys: set[str]) -> int:
        rows = self.repo.list_seed_namespace_rows(
            model,
            project_id=project_id,
            country=country,
            source_namespace=source_namespace,
        )
        count = 0
        for row in rows:
            if row.source_key in seen_keys or row.status == "deprecated":
                continue
            row.status = "deprecated"
            count += 1
        self.db.flush()
        return count

    def _seen_keys_for_namespace(self, bundle: str, asset_type: str) -> set[str]:
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / f"{asset_type}.yaml"
        if not path.exists():
            return set()
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        keys: set[str] = set()
        for entry in entries:
            if asset_type == "catalog":
                keys.add(str(entry.get("source_key") or f"table:{entry['table_name']}"))
            else:
                keys.add(str(entry["source_key"]))
        return keys

    def _seen_field_keys_for_namespace(self, bundle: str) -> set[str]:
        path = DATA_KNOWLEDGE_SEED_DIR / bundle / "catalog.yaml"
        if not path.exists():
            return set()
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        keys: set[str] = set()
        for entry in entries:
            table_name = entry["table_name"]
            for field in entry.get("fields") or []:
                keys.add(str(field.get("source_key") or f"field:{table_name}.{field['field_name']}"))
        return keys

    def _get_owned_row(self, model, row_id: int, *, project_id: int | None):
        row = self.repo.get(model, row_id)
        if row is None:
            raise HTTPException(status_code=404, detail="data knowledge row not found")
        if row.project_id not in {project_id, None}:
            raise HTTPException(status_code=404, detail="data knowledge row not found")
        return row

    @staticmethod
    def _apply_updates(row, payload: dict[str, Any], *, updated_by: str) -> None:
        rename = {
            "join_keys": "join_keys_json",
            "common_filters": "common_filters_json",
            "synonyms": "synonyms_json",
            "mapped_tables": "mapped_tables_json",
            "mapped_fields": "mapped_fields_json",
            "suggested_filters": "suggested_filters_json",
            "tables_used": "tables_used_json",
            "fields_used": "fields_used_json",
            "detected_tables": "detected_tables_json",
            "detected_fields": "detected_fields_json",
            "metadata": "metadata_json",
        }
        for key, value in payload.items():
            setattr(row, rename.get(key, key), value)
        row.updated_by = updated_by
        if hasattr(row, "source_hash"):
            row.source_hash = _hash_payload(payload or {"id": getattr(row, "id", None)})

    @staticmethod
    def _project_id(ctx: UserContext) -> int | None:
        return int(ctx.project_id) if ctx.project_id and str(ctx.project_id).isdigit() else None

    @staticmethod
    def _serialize_catalog_table(row: DataCatalogTable) -> CatalogTableItem:
        return CatalogTableItem(
            id=row.id,
            country=row.country,
            status=row.status,
            source_type=row.source_type,
            source_namespace=row.source_namespace,
            source_key=row.source_key,
            table_name=row.table_name,
            domain=row.domain,
            description=row.description,
            purpose=row.purpose,
            grain=row.grain,
            time_field=row.time_field,
            partition_field=row.partition_field,
            join_keys=row.join_keys_json or [],
            common_filters=row.common_filters_json or [],
        )

    @staticmethod
    def _serialize_catalog_field(row: DataCatalogField) -> CatalogFieldItem:
        return CatalogFieldItem(
            id=row.id,
            country=row.country,
            status=row.status,
            source_type=row.source_type,
            source_namespace=row.source_namespace,
            source_key=row.source_key,
            table_name=row.table_name,
            field_name=row.field_name,
            field_type=row.field_type,
            description=row.description,
            business_meaning=row.business_meaning,
            is_sensitive=row.is_sensitive == "true",
            join_hint=row.join_hint,
        )

    @staticmethod
    def _serialize_glossary(row: DataGlossaryTerm) -> GlossaryItem:
        return GlossaryItem(
            id=row.id,
            country=row.country,
            status=row.status,
            source_type=row.source_type,
            source_namespace=row.source_namespace,
            source_key=row.source_key,
            term=row.term,
            synonyms=row.synonyms_json or [],
            definition=row.definition,
            mapped_tables=row.mapped_tables_json or [],
            mapped_fields=row.mapped_fields_json or [],
            suggested_filters=row.suggested_filters_json or [],
        )

    @staticmethod
    def _serialize_sql_example(row: DataSqlExample, *, can_view_sql: bool) -> SqlExampleItem:
        return SqlExampleItem(
            id=row.id,
            country=row.country,
            status=row.status,
            source_type=row.source_type,
            source_namespace=row.source_namespace,
            source_key=row.source_key,
            natural_language_request=row.natural_language_request,
            run_type=row.run_type,
            output_bucket=row.output_bucket,
            sql_hash=row.sql_hash,
            sql_text=row.sql_text if can_view_sql else None,
            tables_used=row.tables_used_json or [],
            fields_used=row.fields_used_json or [],
            pattern_summary=row.pattern_summary,
            reviewer_username=row.reviewer_username,
            execution_status=row.execution_status,
        )

    @staticmethod
    def _serialize_error_case(row: DataSqlErrorCase, *, can_view_sql: bool) -> SqlErrorCaseItem:
        return SqlErrorCaseItem(
            id=row.id,
            country=row.country,
            status=row.status,
            source_type=row.source_type,
            source_namespace=row.source_namespace,
            source_key=row.source_key,
            natural_language_request=row.natural_language_request,
            run_type=row.run_type,
            output_bucket=row.output_bucket,
            error_type=row.error_type,
            error_message=row.error_message,
            failed_sql_hash=row.failed_sql_hash,
            failed_sql_text=row.failed_sql_text if can_view_sql else None,
            fixed_sql_hash=row.fixed_sql_hash,
            fixed_sql_text=row.fixed_sql_text if can_view_sql else None,
            fix_summary=row.fix_summary,
            detected_tables=row.detected_tables_json or [],
            detected_fields=row.detected_fields_json or [],
        )
