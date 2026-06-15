"""SQLAlchemy models for Data Agent SQL HITL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.database import Base


class DataAgentRun(Base):
    __tablename__ = "data_agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    country: Mapped[str] = mapped_column(String(16), nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    natural_language_request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sql_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_sql_version_id: Mapped[int | None] = mapped_column(ForeignKey("data_agent_sql_versions.id"), nullable=True)
    approved_sql_version_id: Mapped[int | None] = mapped_column(ForeignKey("data_agent_sql_versions.id"), nullable=True)
    approved_sql_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    output_bucket: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uid_column: Mapped[str | None] = mapped_column(String(128), nullable=True)
    overwrite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class DataAgentSqlVersion(Base):
    __tablename__ = "data_agent_sql_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("data_agent_runs.run_id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    sql_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    sql_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    safety_status: Mapped[str] = mapped_column(String(32), nullable=False)
    safety_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    retrieval_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())


class DataAgentReviewEvent(Base):
    __tablename__ = "data_agent_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("data_agent_runs.run_id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_username: Mapped[str] = mapped_column(String(128), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_sql_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_sql_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())


class DataAgentExecutionEvent(Base):
    __tablename__ = "data_agent_execution_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("data_agent_runs.run_id"), nullable=False)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_sql_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    executor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executor_username: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rows_estimated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_preview_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())


class DataAgentWritebackEvent(Base):
    __tablename__ = "data_agent_writeback_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("data_agent_runs.run_id"), nullable=False)
    approved_sql_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    executor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executor_username: Mapped[str] = mapped_column(String(128), nullable=False)
    output_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    output_format: Mapped[str] = mapped_column(String(32), nullable=False)
    target_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    written_uid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, server_default=func.current_timestamp())
