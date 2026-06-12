"""Repository helpers for Data Agent SQL HITL."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.data_agent.models import (
    DataAgentExecutionEvent,
    DataAgentReviewEvent,
    DataAgentRun,
    DataAgentSqlVersion,
    DataAgentWritebackEvent,
)


class DataAgentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_run(self, **kwargs) -> DataAgentRun:
        run = DataAgentRun(**kwargs)
        self.db.add(run)
        self.db.flush()
        return run

    def add_sql_version(self, **kwargs) -> DataAgentSqlVersion:
        version = DataAgentSqlVersion(**kwargs)
        self.db.add(version)
        self.db.flush()
        return version

    def add_review_event(self, **kwargs) -> DataAgentReviewEvent:
        event = DataAgentReviewEvent(**kwargs)
        self.db.add(event)
        self.db.flush()
        return event

    def add_execution_event(self, **kwargs) -> DataAgentExecutionEvent:
        event = DataAgentExecutionEvent(**kwargs)
        self.db.add(event)
        self.db.flush()
        return event

    def add_writeback_event(self, **kwargs) -> DataAgentWritebackEvent:
        event = DataAgentWritebackEvent(**kwargs)
        self.db.add(event)
        self.db.flush()
        return event

    def get_run(self, run_id: str) -> DataAgentRun | None:
        return self.db.scalar(select(DataAgentRun).where(DataAgentRun.run_id == run_id))

    def get_scoped_run(self, run_id: str, *, project_id: int | None, country: str | None) -> DataAgentRun | None:
        stmt = select(DataAgentRun).where(DataAgentRun.run_id == run_id)
        if project_id is not None:
            stmt = stmt.where(DataAgentRun.project_id == project_id)
        if country is not None:
            stmt = stmt.where(DataAgentRun.country == country)
        return self.db.scalar(stmt)

    def list_runs(self, *, project_id: int | None, country: str | None, limit: int = 20) -> list[DataAgentRun]:
        stmt = select(DataAgentRun).order_by(desc(DataAgentRun.updated_at)).limit(limit)
        if project_id is not None:
            stmt = stmt.where(DataAgentRun.project_id == project_id)
        if country is not None:
            stmt = stmt.where(DataAgentRun.country == country)
        return list(self.db.scalars(stmt).all())

    def get_sql_version(self, version_id: int | None) -> DataAgentSqlVersion | None:
        if version_id is None:
            return None
        return self.db.scalar(select(DataAgentSqlVersion).where(DataAgentSqlVersion.id == version_id))

    def list_review_events(self, run_id: str) -> list[DataAgentReviewEvent]:
        stmt = select(DataAgentReviewEvent).where(DataAgentReviewEvent.run_id == run_id).order_by(DataAgentReviewEvent.created_at)
        return list(self.db.scalars(stmt).all())

    def latest_execution_event(self, run_id: str) -> DataAgentExecutionEvent | None:
        stmt = (
            select(DataAgentExecutionEvent)
            .where(DataAgentExecutionEvent.run_id == run_id)
            .order_by(desc(DataAgentExecutionEvent.created_at), desc(DataAgentExecutionEvent.id))
        )
        return self.db.scalar(stmt)

    def latest_writeback_event(self, run_id: str) -> DataAgentWritebackEvent | None:
        stmt = (
            select(DataAgentWritebackEvent)
            .where(DataAgentWritebackEvent.run_id == run_id)
            .order_by(desc(DataAgentWritebackEvent.created_at), desc(DataAgentWritebackEvent.id))
        )
        return self.db.scalar(stmt)

    def next_version_no(self, run_id: str) -> int:
        stmt = select(DataAgentSqlVersion).where(DataAgentSqlVersion.run_id == run_id).order_by(desc(DataAgentSqlVersion.version_no))
        latest = self.db.scalar(stmt)
        return 1 if latest is None else int(latest.version_no) + 1

