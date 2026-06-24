"""Prompt context assembly for retrieved data knowledge."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.data_knowledge.retriever import RetrievedKnowledgeContext


@dataclass(slots=True)
class AssembledPromptContext:
    rendered_text: str
    context_hash: str
    section_counts: dict[str, int]
    source_ids: dict[str, list[int]]
    trimmed: bool


class PromptContextAssembler:
    def assemble(
        self,
        *,
        natural_language_request: str,
        country: str,
        run_type: str,
        output_bucket: str | None,
        context: RetrievedKnowledgeContext,
    ) -> AssembledPromptContext:
        sections: list[str] = []
        if context.catalog_tables:
            lines = ["# === retrieved_catalog_tables ==="]
            for row in context.catalog_tables:
                lines.append(
                    f"- table={row.table_name}; purpose={row.purpose or ''}; grain={row.grain or ''}; "
                    f"time_field={row.time_field or ''}; join_keys={','.join(row.join_keys_json or [])}"
                )
            sections.append("\n".join(lines))
        if context.catalog_fields:
            lines = ["# === retrieved_catalog_fields ==="]
            for row in context.catalog_fields:
                lines.append(
                    f"- {row.table_name}.{row.field_name}; type={row.field_type or ''}; "
                    f"meaning={row.business_meaning or row.description or ''}"
                )
            sections.append("\n".join(lines))
        if context.glossary_terms:
            lines = ["# === retrieved_glossary_terms ==="]
            for row in context.glossary_terms:
                lines.append(
                    f"- term={row.term}; definition={row.definition or ''}; "
                    f"tables={','.join(row.mapped_tables_json or [])}; fields={','.join(row.mapped_fields_json or [])}; "
                    f"filters={'; '.join(row.suggested_filters_json or [])}"
                )
            sections.append("\n".join(lines))
        if context.sql_examples:
            lines = ["# === retrieved_sql_examples ==="]
            for row in context.sql_examples:
                lines.append(
                    f"- request={row.natural_language_request}; summary={row.pattern_summary or ''}; "
                    f"tables={','.join(row.tables_used_json or [])}; fields={','.join(row.fields_used_json or [])}; "
                    f"run_type={row.run_type}; output_bucket={row.output_bucket or ''}"
                )
            lines.extend(
                [
                    "- current request is the source of truth.",
                    "- Use these examples as pattern guidance, not literal SQL.",
                    "- Examples are pattern guidance only.",
                    "- Adapt tables, fields, filters, and dates to the current request.",
                    "- Do not copy example WHERE clauses unless they semantically match the current request.",
                    "- Do not copy literal dates, partition ranges, source filters, uid placeholders, or table aliases from examples unless explicitly required by the current request and grounded by retrieved catalog/glossary.",
                    "- Do not copy uid placeholders.",
                    "- Prefer field names explicitly present in the retrieved catalog for the selected table and country.",
                    "- Do not substitute to a historical alias family unless that alias is present in retrieved catalog or glossary for the current country/table.",
                ]
            )
            sections.append("\n".join(lines))
        if context.error_cases:
            lines = ["# === retrieved_error_cases ==="]
            for row in context.error_cases:
                lines.append(
                    f"- error_type={row.error_type}; message={row.error_message or ''}; "
                    f"tables={','.join(row.detected_tables_json or [])}; fields={','.join(row.detected_fields_json or [])}; "
                    f"fix_summary={row.fix_summary or ''}"
                )
            sections.append("\n".join(lines))

        if run_type == "bucket_writeback":
            lines = [
                "# === writeback_constraints ===",
                f"- output_bucket={output_bucket or ''}",
                "- query_only SQL only",
                "- result must include uid",
                "- Define the target cohort first.",
                "- Define the target cohort or use an explicit uid list first.",
                "- Join the behavior source table by uid.",
                "- Return uid together with the requested behavior fields.",
                "- Do not emit unresolved uid placeholders.",
                "- Do not scan the behavior table without a cohort/uid constraint.",
                "- Do not broad-scan the behavior table.",
            ]
            if self._is_under_specified_writeback_request(natural_language_request):
                lines.append("- If the request has no cohort condition and no explicit uid list, return sql=null rather than inventing placeholders.")
            sections.append("\n".join(lines))

        rendered_text = "\n\n".join(section for section in sections if section).strip()
        context_hash = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest() if rendered_text else ""
        return AssembledPromptContext(
            rendered_text=rendered_text,
            context_hash=context_hash,
            section_counts=context.section_counts,
            source_ids=context.source_ids,
            trimmed=context.trimmed,
        )

    @staticmethod
    def build_snapshot(
        *,
        country: str,
        project_id: int | None,
        context: RetrievedKnowledgeContext,
        assembled: AssembledPromptContext,
    ) -> dict[str, object]:
        return {
            "context_hash": assembled.context_hash,
            "table_ids": context.source_ids["table_ids"],
            "field_ids": context.source_ids["field_ids"],
            "glossary_ids": context.source_ids["glossary_ids"],
            "example_ids": context.source_ids["example_ids"],
            "error_case_ids": context.source_ids["error_case_ids"],
            "section_counts": context.section_counts,
            "trimmed": context.trimmed,
            "country": country,
            "project_id": project_id,
        }

    @staticmethod
    def _is_under_specified_writeback_request(natural_language_request: str) -> bool:
        request = str(natural_language_request or "").strip().lower()
        if not request:
            return True
        explicit_uid = any(token in request for token in ("uid", "uuid", "user_id", "userid", "用户id", "用户 id"))
        has_cohort_condition = any(
            token in request
            for token in (
                "查询",
                "找出",
                "筛选",
                "最近",
                "首贷",
                "逾期",
                "高风险",
                "cohort",
                "where",
                "过滤",
                "满足",
                "从未",
                "7 天",
                "7天",
            )
        )
        return not explicit_uid and not has_cohort_condition
