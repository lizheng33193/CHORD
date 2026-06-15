"""SQLAlchemy models for data knowledge assets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.database import Base


class DataCatalogTable(Base):
    __tablename__ = "data_catalog_tables"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country",
            "source_namespace",
            "source_key",
            name="uk_data_catalog_table_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    grain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    time_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    partition_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    join_keys_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    common_filters_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class DataCatalogField(Base):
    __tablename__ = "data_catalog_fields"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country",
            "source_namespace",
            "source_key",
            name="uk_data_catalog_field_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_meaning: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_sensitive: Mapped[str] = mapped_column(String(8), nullable=False, default="false")
    join_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class DataGlossaryTerm(Base):
    __tablename__ = "data_glossary_terms"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country",
            "source_namespace",
            "source_key",
            name="uk_data_glossary_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    synonyms_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapped_tables_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    mapped_fields_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    suggested_filters_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class DataSqlExample(Base):
    __tablename__ = "data_sql_examples"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country",
            "source_namespace",
            "source_key",
            name="uk_data_sql_example_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    natural_language_request: Mapped[str] = mapped_column(Text, nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    output_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sql_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables_used_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fields_used_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pattern_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class DataSqlErrorCase(Base):
    __tablename__ = "data_sql_error_cases"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "country",
            "source_namespace",
            "source_key",
            name="uk_data_sql_error_case_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    natural_language_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_sql_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failed_sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_sql_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fixed_sql_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_tables_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    detected_fields_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
