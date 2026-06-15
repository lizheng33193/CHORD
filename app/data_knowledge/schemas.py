"""Pydantic contracts for data knowledge assets."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


KnowledgeAssetStatus = Literal["draft", "active", "deprecated"]
ErrorCaseStatus = Literal["open", "resolved", "deprecated"]
SourceType = Literal["seed", "manual", "approved_sql", "error_case"]


class SeedImportRequest(BaseModel):
    bundle: Literal["mx", "ph", "common"]


class SeedImportResponse(BaseModel):
    bundle: str
    upserted: int
    deprecated: int


class CatalogTableCreateRequest(BaseModel):
    country: str | None = None
    status: KnowledgeAssetStatus = "active"
    source_type: SourceType = "manual"
    source_namespace: str
    source_key: str
    table_name: str
    domain: str | None = None
    description: str | None = None
    purpose: str | None = None
    grain: str | None = None
    time_field: str | None = None
    partition_field: str | None = None
    join_keys: list[str] = Field(default_factory=list)
    common_filters: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class CatalogTableUpdateRequest(BaseModel):
    status: KnowledgeAssetStatus | None = None
    description: str | None = None
    purpose: str | None = None
    grain: str | None = None
    time_field: str | None = None
    partition_field: str | None = None
    join_keys: list[str] | None = None
    common_filters: list[str] | None = None
    metadata: dict[str, Any] | None = None


class CatalogFieldCreateRequest(BaseModel):
    country: str | None = None
    status: KnowledgeAssetStatus = "active"
    source_type: SourceType = "manual"
    source_namespace: str
    source_key: str
    table_name: str
    field_name: str
    field_type: str | None = None
    description: str | None = None
    business_meaning: str | None = None
    is_sensitive: bool = False
    join_hint: str | None = None
    metadata: dict[str, Any] | None = None


class CatalogFieldUpdateRequest(BaseModel):
    status: KnowledgeAssetStatus | None = None
    field_type: str | None = None
    description: str | None = None
    business_meaning: str | None = None
    is_sensitive: bool | None = None
    join_hint: str | None = None
    metadata: dict[str, Any] | None = None


class GlossaryCreateRequest(BaseModel):
    country: str | None = None
    status: KnowledgeAssetStatus = "active"
    source_type: SourceType = "manual"
    source_namespace: str
    source_key: str
    term: str
    synonyms: list[str] = Field(default_factory=list)
    definition: str | None = None
    mapped_tables: list[str] = Field(default_factory=list)
    mapped_fields: list[str] = Field(default_factory=list)
    suggested_filters: list[str] = Field(default_factory=list)


class GlossaryUpdateRequest(BaseModel):
    status: KnowledgeAssetStatus | None = None
    synonyms: list[str] | None = None
    definition: str | None = None
    mapped_tables: list[str] | None = None
    mapped_fields: list[str] | None = None
    suggested_filters: list[str] | None = None


class SqlExampleCreateRequest(BaseModel):
    country: str | None = None
    status: KnowledgeAssetStatus = "draft"
    source_type: SourceType = "manual"
    source_namespace: str
    source_key: str
    natural_language_request: str
    run_type: str
    output_bucket: str | None = None
    sql_hash: str
    sql_text: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    fields_used: list[str] = Field(default_factory=list)
    pattern_summary: str | None = None
    reviewer_username: str | None = None
    execution_status: str | None = None


class SqlExampleUpdateRequest(BaseModel):
    status: KnowledgeAssetStatus | None = None
    sql_text: str | None = None
    tables_used: list[str] | None = None
    fields_used: list[str] | None = None
    pattern_summary: str | None = None
    execution_status: str | None = None


class SqlErrorCaseCreateRequest(BaseModel):
    country: str | None = None
    status: ErrorCaseStatus = "open"
    source_type: SourceType = "manual"
    source_namespace: str
    source_key: str
    natural_language_request: str | None = None
    run_type: str | None = None
    output_bucket: str | None = None
    error_type: str
    error_message: str | None = None
    failed_sql_hash: str | None = None
    failed_sql_text: str | None = None
    fixed_sql_hash: str | None = None
    fixed_sql_text: str | None = None
    fix_summary: str | None = None
    detected_tables: list[str] = Field(default_factory=list)
    detected_fields: list[str] = Field(default_factory=list)


class SqlErrorCaseUpdateRequest(BaseModel):
    status: ErrorCaseStatus | None = None
    error_message: str | None = None
    failed_sql_text: str | None = None
    fixed_sql_hash: str | None = None
    fixed_sql_text: str | None = None
    fix_summary: str | None = None
    detected_tables: list[str] | None = None
    detected_fields: list[str] | None = None


class CatalogTableItem(BaseModel):
    id: int
    country: str | None = None
    status: KnowledgeAssetStatus
    source_type: SourceType
    source_namespace: str
    source_key: str
    table_name: str
    domain: str | None = None
    description: str | None = None
    purpose: str | None = None
    grain: str | None = None
    time_field: str | None = None
    partition_field: str | None = None
    join_keys: list[str] = Field(default_factory=list)
    common_filters: list[str] = Field(default_factory=list)


class CatalogFieldItem(BaseModel):
    id: int
    country: str | None = None
    status: KnowledgeAssetStatus
    source_type: SourceType
    source_namespace: str
    source_key: str
    table_name: str
    field_name: str
    field_type: str | None = None
    description: str | None = None
    business_meaning: str | None = None
    is_sensitive: bool = False
    join_hint: str | None = None


class GlossaryItem(BaseModel):
    id: int
    country: str | None = None
    status: KnowledgeAssetStatus
    source_type: SourceType
    source_namespace: str
    source_key: str
    term: str
    synonyms: list[str] = Field(default_factory=list)
    definition: str | None = None
    mapped_tables: list[str] = Field(default_factory=list)
    mapped_fields: list[str] = Field(default_factory=list)
    suggested_filters: list[str] = Field(default_factory=list)


class SqlExampleItem(BaseModel):
    id: int
    country: str | None = None
    status: KnowledgeAssetStatus
    source_type: SourceType
    source_namespace: str
    source_key: str
    natural_language_request: str
    run_type: str
    output_bucket: str | None = None
    sql_hash: str
    sql_text: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    fields_used: list[str] = Field(default_factory=list)
    pattern_summary: str | None = None
    reviewer_username: str | None = None
    execution_status: str | None = None


class SqlErrorCaseItem(BaseModel):
    id: int
    country: str | None = None
    status: ErrorCaseStatus
    source_type: SourceType
    source_namespace: str
    source_key: str
    natural_language_request: str | None = None
    run_type: str | None = None
    output_bucket: str | None = None
    error_type: str
    error_message: str | None = None
    failed_sql_hash: str | None = None
    failed_sql_text: str | None = None
    fixed_sql_hash: str | None = None
    fixed_sql_text: str | None = None
    fix_summary: str | None = None
    detected_tables: list[str] = Field(default_factory=list)
    detected_fields: list[str] = Field(default_factory=list)


class CatalogTableListResponse(BaseModel):
    items: list[CatalogTableItem]


class CatalogFieldListResponse(BaseModel):
    items: list[CatalogFieldItem]


class GlossaryListResponse(BaseModel):
    items: list[GlossaryItem]


class SqlExampleListResponse(BaseModel):
    items: list[SqlExampleItem]


class SqlErrorCaseListResponse(BaseModel):
    items: list[SqlErrorCaseItem]
