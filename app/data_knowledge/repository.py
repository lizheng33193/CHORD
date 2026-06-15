"""Repository helpers for data knowledge assets."""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.data_knowledge.models import (
    DataCatalogField,
    DataCatalogTable,
    DataGlossaryTerm,
    DataSqlErrorCase,
    DataSqlExample,
)


ModelT = TypeVar(
    "ModelT",
    DataCatalogTable,
    DataCatalogField,
    DataGlossaryTerm,
    DataSqlExample,
    DataSqlErrorCase,
)


class DataKnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find_by_source_identity(
        self,
        model: type[ModelT],
        *,
        project_id: int | None,
        country: str | None,
        source_namespace: str,
        source_key: str,
    ) -> ModelT | None:
        stmt = select(model).where(
            model.project_id == project_id,
            model.country == country,
            model.source_namespace == source_namespace,
            model.source_key == source_key,
        )
        return self.db.scalar(stmt)

    def list_by_scope(
        self,
        model: type[ModelT],
        *,
        project_id: int | None,
        country: str | None,
    ) -> list[ModelT]:
        stmt = select(model).where(
            or_(model.project_id == project_id, model.project_id.is_(None)),
            or_(model.country == country, model.country.is_(None)),
        ).order_by(model.id.asc())
        return list(self.db.scalars(stmt).all())

    def list_seed_namespace_rows(
        self,
        model: type[ModelT],
        *,
        project_id: int | None,
        country: str | None,
        source_namespace: str,
    ) -> list[ModelT]:
        stmt = select(model).where(
            model.project_id == project_id,
            model.country == country,
            model.source_type == "seed",
            model.source_namespace == source_namespace,
        )
        return list(self.db.scalars(stmt).all())

    def get(self, model: type[ModelT], row_id: int) -> ModelT | None:
        return self.db.get(model, row_id)

    def add(self, row: ModelT) -> ModelT:
        self.db.add(row)
        self.db.flush()
        return row
