"""Deterministic data knowledge retriever for M2A."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.data_knowledge.models import (
    DataCatalogField,
    DataCatalogTable,
    DataGlossaryTerm,
    DataSqlErrorCase,
    DataSqlExample,
)
from app.data_knowledge.repository import DataKnowledgeRepository


@dataclass(slots=True)
class RetrievedKnowledgeContext:
    catalog_tables: list[DataCatalogTable]
    catalog_fields: list[DataCatalogField]
    glossary_terms: list[DataGlossaryTerm]
    sql_examples: list[DataSqlExample]
    error_cases: list[DataSqlErrorCase]
    section_counts: dict[str, int]
    source_ids: dict[str, list[int]]
    trimmed: bool


class DataKnowledgeRetriever:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DataKnowledgeRepository(db)

    def retrieve(
        self,
        *,
        natural_language_request: str,
        project_id: int | None,
        country: str,
        run_type: str,
        output_bucket: str | None,
    ) -> RetrievedKnowledgeContext:
        query = str(natural_language_request or "").strip().lower()
        target_country = str(country or "").strip().lower() or None

        tables = self._rank(
            self.repo.list_by_scope(DataCatalogTable, project_id=project_id, country=target_country),
            query=query,
            project_id=project_id,
            country=target_country,
            top_k=3,
            text_fn=lambda row: " ".join(
                filter(
                    None,
                    [
                        row.table_name,
                        row.domain or "",
                        row.description or "",
                        row.purpose or "",
                        " ".join(row.join_keys_json or []),
                        " ".join(row.common_filters_json or []),
                    ],
                )
            ),
            status_filter={"active"},
        )
        fields = self._rank(
            self.repo.list_by_scope(DataCatalogField, project_id=project_id, country=target_country),
            query=query,
            project_id=project_id,
            country=target_country,
            top_k=5,
            text_fn=lambda row: " ".join(
                filter(
                    None,
                    [
                        row.table_name,
                        row.field_name,
                        row.field_type or "",
                        row.description or "",
                        row.business_meaning or "",
                        row.join_hint or "",
                    ],
                )
            ),
            status_filter={"active"},
        )
        glossary = self._rank(
            self.repo.list_by_scope(DataGlossaryTerm, project_id=project_id, country=target_country),
            query=query,
            project_id=project_id,
            country=target_country,
            top_k=5,
            text_fn=lambda row: " ".join(
                filter(
                    None,
                    [
                        row.term,
                        row.definition or "",
                        " ".join(row.synonyms_json or []),
                        " ".join(row.mapped_tables_json or []),
                        " ".join(row.mapped_fields_json or []),
                        " ".join(row.suggested_filters_json or []),
                    ],
                )
            ),
            status_filter={"active"},
        )
        examples = self._rank(
            self.repo.list_by_scope(DataSqlExample, project_id=project_id, country=target_country),
            query=query,
            project_id=project_id,
            country=target_country,
            top_k=3,
            text_fn=lambda row: " ".join(
                filter(
                    None,
                    [
                        row.natural_language_request,
                        row.pattern_summary or "",
                        " ".join(row.tables_used_json or []),
                        " ".join(row.fields_used_json or []),
                        row.output_bucket or "",
                        row.run_type,
                    ],
                )
            ),
            status_filter={"active"},
        )
        error_cases = self._rank(
            self.repo.list_by_scope(DataSqlErrorCase, project_id=project_id, country=target_country),
            query=query,
            project_id=project_id,
            country=target_country,
            top_k=3,
            text_fn=lambda row: " ".join(
                filter(
                    None,
                    [
                        row.natural_language_request or "",
                        row.error_type,
                        row.error_message or "",
                        " ".join(row.detected_tables_json or []),
                        " ".join(row.detected_fields_json or []),
                        row.output_bucket or "",
                        row.run_type or "",
                    ],
                )
            ),
            status_filter={"open"},
        )

        if output_bucket:
            examples = [row for row in examples if row.output_bucket in {None, output_bucket}]
            error_cases = [row for row in error_cases if row.output_bucket in {None, output_bucket}]

        if run_type:
            examples = [row for row in examples if row.run_type == run_type]
            error_cases = [row for row in error_cases if row.run_type in {None, run_type}]

        tables = self._expand_tables_from_glossary(
            tables=tables,
            glossary=glossary,
            project_id=project_id,
            country=target_country,
        )
        fields = self._expand_fields_from_glossary(
            fields=fields,
            glossary=glossary,
            project_id=project_id,
            country=target_country,
        )

        return RetrievedKnowledgeContext(
            catalog_tables=tables,
            catalog_fields=fields,
            glossary_terms=glossary,
            sql_examples=examples,
            error_cases=error_cases,
            section_counts={
                "catalog_tables": len(tables),
                "catalog_fields": len(fields),
                "glossary_terms": len(glossary),
                "sql_examples": len(examples),
                "error_cases": len(error_cases),
            },
            source_ids={
                "table_ids": [row.id for row in tables],
                "field_ids": [row.id for row in fields],
                "glossary_ids": [row.id for row in glossary],
                "example_ids": [row.id for row in examples],
                "error_case_ids": [row.id for row in error_cases],
            },
            trimmed=False,
        )

    def _expand_tables_from_glossary(self, *, tables, glossary, project_id: int | None, country: str | None):
        seen = {row.id for row in tables}
        for term in glossary:
            for table_name in term.mapped_tables_json or []:
                matches = self.repo.list_by_scope(DataCatalogTable, project_id=project_id, country=country)
                for row in matches:
                    if row.status != "active" or row.table_name != table_name or row.id in seen:
                        continue
                    tables.append(row)
                    seen.add(row.id)
        return tables

    def _expand_fields_from_glossary(self, *, fields, glossary, project_id: int | None, country: str | None):
        seen = {row.id for row in fields}
        for term in glossary:
            mapped_fields = set(term.mapped_fields_json or [])
            if not mapped_fields:
                continue
            matches = self.repo.list_by_scope(DataCatalogField, project_id=project_id, country=country)
            for row in matches:
                if row.status != "active" or row.field_name not in mapped_fields or row.id in seen:
                    continue
                fields.append(row)
                seen.add(row.id)
        return fields

    def _rank(
        self,
        rows,
        *,
        query: str,
        project_id: int | None,
        country: str | None,
        top_k: int,
        text_fn,
        status_filter: set[str],
    ):
        ranked: list[tuple[int, int, int, object]] = []
        for row in rows:
            if getattr(row, "status", None) not in status_filter:
                continue
            if country is not None and row.country not in {country, None}:
                continue
            score = self._score(text_fn(row), query)
            if score <= 0:
                continue
            ranked.append((self._scope_rank(row, project_id=project_id, country=country), -score, row.id, row))
        ranked.sort()
        return [row for *_meta, row in ranked[:top_k]]

    @staticmethod
    def _scope_rank(row, *, project_id: int | None, country: str | None) -> int:
        row_project = row.project_id
        row_country = row.country
        if row_project == project_id and row_country == country:
            return 0
        if row_project is None and row_country == country:
            return 1
        if row_project == project_id and row_country is None:
            return 2
        return 3

    @staticmethod
    def _score(text: str, query: str) -> int:
        haystack = re.sub(r"\s+", " ", str(text or "").lower())
        query_terms = [term for term in re.split(r"[\s,，]+", query) if term]
        score = 0
        for term in query_terms:
            if len(term) <= 1:
                continue
            if term in haystack:
                score += max(2, len(term))
        for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", haystack):
            if len(token) <= 1:
                continue
            if token in query:
                score += max(2, len(token))
        return score
