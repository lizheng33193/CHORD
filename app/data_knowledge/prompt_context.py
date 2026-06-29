"""Prompt context assembly for retrieved data knowledge."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.data_knowledge.canonical_fields import (
    build_canonical_alternative_to_preferred_by_table,
    build_canonical_guidance_rows,
    normalize_field_name,
    normalize_table_name,
)
from app.data_knowledge.retriever import RetrievedKnowledgeContext


@dataclass(slots=True)
class AssembledPromptContext:
    rendered_text: str
    context_hash: str
    section_counts: dict[str, int]
    source_ids: dict[str, list[int]]
    trimmed: bool


def append_prompt_section(assembled: AssembledPromptContext, section_text: str) -> AssembledPromptContext:
    extra = str(section_text or "").strip()
    if not extra:
        return assembled
    rendered_text = assembled.rendered_text.strip()
    if rendered_text:
        rendered_text = f"{rendered_text}\n\n{extra}"
    else:
        rendered_text = extra
    context_hash = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest() if rendered_text else ""
    return AssembledPromptContext(
        rendered_text=rendered_text,
        context_hash=context_hash,
        section_counts=dict(assembled.section_counts),
        source_ids={key: list(values) for key, values in assembled.source_ids.items()},
        trimmed=assembled.trimmed,
    )


class PromptContextAssembler:
    def assemble(
        self,
        *,
        natural_language_request: str,
        country: str,
        run_type: str,
        output_bucket: str | None,
        context: RetrievedKnowledgeContext,
        structured_plan: dict[str, object] | None = None,
    ) -> AssembledPromptContext:
        sections: list[str] = []
        grounded_fields = self._build_grounded_fields_by_table(context)
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
            grounding_lines = ["# === retrieved_field_grounding ==="]
            for table_name, field_names in grounded_fields.items():
                grounding_lines.append(f"- table={table_name}; allowed_fields={','.join(field_names)}")
            grounding_lines.extend(
                [
                    "- Selected table fields must come from retrieved catalog/glossary for that table and country.",
                    "- Do not switch to a historical alias family unless explicitly grounded by retrieved catalog/glossary.",
                    "- Do not invent new base-table fields from historical examples.",
                ]
            )
            sections.append("\n".join(grounding_lines))
            canonical_rows = build_canonical_guidance_rows(grounded_fields)
            if canonical_rows:
                canonical_lines = ["# === canonical_field_guidance ==="]
                for row in canonical_rows:
                    canonical_lines.append(
                        f"- table={row['table']}; semantic={row['semantic']}; preferred={row['preferred']}; alternatives={row['alternatives']}"
                    )
                canonical_lines.extend(
                    [
                        "- Use preferred fields by default.",
                        "- Alternatives are allowed only when the current request or retrieved context explicitly requires them.",
                        "- Do not switch from preferred fields to alternative families because of historical examples.",
                    ]
                )
                sections.append("\n".join(canonical_lines))
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
                    "- If the current request does not mention a source or channel filter, do not add one from examples.",
                    "- If the current request uses a relative time window, keep it relative instead of replacing it with fixed example partitions.",
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
                lines.append("- If the request has no cohort condition and no explicit uid list, return sql=null and sql_kind=query_only rather than inventing placeholders.")
            sections.append("\n".join(lines))
            intent_plan_summary = self._build_sql_intent_plan_summary(
                natural_language_request=natural_language_request,
                run_type=run_type,
                output_bucket=output_bucket,
                context=context,
                grounded_fields_by_table=grounded_fields,
            )
            if structured_plan:
                sections.append(self._render_structured_sql_plan_contract(structured_plan))
            if intent_plan_summary:
                sections.append(self._render_sql_intent_plan(intent_plan_summary))

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
    def build_base_snapshot(
        *,
        country: str,
        project_id: int | None,
        natural_language_request: str,
        run_type: str,
        output_bucket: str | None,
        context: RetrievedKnowledgeContext,
    ) -> dict[str, object]:
        grounded_fields = PromptContextAssembler._build_grounded_fields_by_table(context)
        return {
            "table_ids": context.source_ids["table_ids"],
            "field_ids": context.source_ids["field_ids"],
            "glossary_ids": context.source_ids["glossary_ids"],
            "example_ids": context.source_ids["example_ids"],
            "error_case_ids": context.source_ids["error_case_ids"],
            "section_counts": context.section_counts,
            "trimmed": context.trimmed,
            "country": country,
            "project_id": project_id,
            "grounded_fields_by_table": grounded_fields,
            "canonical_alternative_to_preferred_by_table": build_canonical_alternative_to_preferred_by_table(grounded_fields),
            "sql_intent_plan_summary": PromptContextAssembler._build_sql_intent_plan_summary(
                natural_language_request=natural_language_request,
                run_type=run_type,
                output_bucket=output_bucket,
                context=context,
                grounded_fields_by_table=grounded_fields,
            ),
        }

    @staticmethod
    def build_snapshot(
        *,
        country: str,
        project_id: int | None,
        natural_language_request: str,
        run_type: str,
        output_bucket: str | None,
        context: RetrievedKnowledgeContext,
        assembled: AssembledPromptContext,
        structured_plan: dict[str, object] | None = None,
        structured_plan_validation: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = PromptContextAssembler.build_base_snapshot(
            country=country,
            project_id=project_id,
            natural_language_request=natural_language_request,
            run_type=run_type,
            output_bucket=output_bucket,
            context=context,
        )
        snapshot["context_hash"] = assembled.context_hash
        if structured_plan is not None:
            snapshot["structured_sql_plan"] = structured_plan
        if structured_plan_validation is not None:
            snapshot["structured_sql_plan_validation"] = structured_plan_validation
        return snapshot

    @staticmethod
    def _is_under_specified_writeback_request(natural_language_request: str) -> bool:
        request = str(natural_language_request or "").strip().lower()
        if not request:
            return True
        explicit_uid = any(token in request for token in ("uid", "uuid", "user_id", "userid", "用户id", "用户 id", "用户列表"))
        has_cohort_condition = any(
            token in request
            for token in (
                "最近",
                "首贷",
                "逾期",
                "高风险",
                "cohort",
                "从未",
                "7 天",
                "7天",
                "注册用户",
                "逾期用户",
                "first-loan",
                "never-overdue",
            )
        )
        return not explicit_uid and not has_cohort_condition

    @staticmethod
    def _build_grounded_fields_by_table(context: RetrievedKnowledgeContext) -> dict[str, list[str]]:
        grounded_fields: dict[str, list[str]] = {}
        for row in context.catalog_fields:
            table_name = normalize_table_name(row.table_name)
            field_name = normalize_field_name(row.field_name)
            if not table_name or not field_name:
                continue
            bucket = grounded_fields.setdefault(table_name, [])
            if field_name not in bucket:
                bucket.append(field_name)
        for row in context.glossary_terms:
            mapped_tables = [normalize_table_name(table) for table in (row.mapped_tables_json or []) if normalize_table_name(table)]
            mapped_fields = [normalize_field_name(field) for field in (row.mapped_fields_json or []) if normalize_field_name(field)]
            for table_name in mapped_tables:
                bucket = grounded_fields.setdefault(table_name, [])
                for field_name in mapped_fields:
                    if field_name not in bucket:
                        bucket.append(field_name)
        return grounded_fields

    @classmethod
    def _build_sql_intent_plan_summary(
        cls,
        *,
        natural_language_request: str,
        run_type: str,
        output_bucket: str | None,
        context: RetrievedKnowledgeContext,
        grounded_fields_by_table: dict[str, list[str]],
    ) -> dict[str, object] | None:
        if run_type != "bucket_writeback" or cls._is_under_specified_writeback_request(natural_language_request):
            return None
        source_tables: list[str] = []
        for row in context.catalog_tables:
            table_name = normalize_table_name(row.table_name)
            if table_name and table_name not in source_tables:
                source_tables.append(table_name)
        grounded_field_set = {field_name for field_names in grounded_fields_by_table.values() for field_name in field_names}
        required_fields = ["uid"]
        if output_bucket == "behavior":
            required_fields = [
                field_name
                for field_name in ("uid", "timestamp_", "eventname")
                if field_name in grounded_field_set
            ]
        return {
            "task_type": "bucket_writeback",
            "output_bucket": output_bucket or "",
            "target_cohort_conditions": cls._extract_target_cohort_conditions(natural_language_request),
            "source_tables": source_tables,
            "join_keys": ["uid"],
            "required_fields": required_fields,
            "forbidden_patterns": [
                "unresolved_uid_placeholder",
                "broad_behavior_scan",
                "historical_date_copy",
                "historical_source_filter",
                "literal_example_copy",
                "unsupported_field_family",
            ],
        }

    @staticmethod
    def _extract_target_cohort_conditions(natural_language_request: str) -> list[str]:
        request = str(natural_language_request or "").strip().lower()
        markers: list[tuple[tuple[str, ...], str]] = [
            (("首贷", "first loan", "first-loan", "first_loan"), "first_loan"),
            (("从未逾期", "never overdue", "never-overdue", "never_overdue"), "never_overdue"),
            (("高风险", "high risk", "high-risk", "high_risk"), "high_risk"),
            (("最近 7 天", "最近7天", "7 天", "7天", "7 days", "recent 7 days"), "recent_7d"),
            (("注册用户", "registered users", "registered user"), "registered_users"),
            (("逾期用户", "overdue users", "overdue user"), "overdue_users"),
            (("uid", "uuid", "user_id", "userid", "用户列表"), "explicit_uid_list"),
        ]
        results: list[str] = []
        for tokens, label in markers:
            if any(token in request for token in tokens) and label not in results:
                results.append(label)
        return results

    @staticmethod
    def _render_sql_intent_plan(intent_plan_summary: dict[str, object]) -> str:
        return "\n".join(
            [
                "# === sql_intent_plan ===",
                f"- task_type={intent_plan_summary.get('task_type', '')}",
                f"- output_bucket={intent_plan_summary.get('output_bucket', '')}",
                f"- target_cohort_conditions={','.join(intent_plan_summary.get('target_cohort_conditions', []) or [])}",
                f"- source_tables={','.join(intent_plan_summary.get('source_tables', []) or [])}",
                f"- join_keys={','.join(intent_plan_summary.get('join_keys', []) or [])}",
                f"- required_fields={','.join(intent_plan_summary.get('required_fields', []) or [])}",
                f"- forbidden_patterns={','.join(intent_plan_summary.get('forbidden_patterns', []) or [])}",
            ]
        )

    @staticmethod
    def _render_structured_sql_plan_contract(structured_plan: dict[str, object]) -> str:
        return "\n".join(
            [
                "# === structured_sql_plan_contract ===",
                f"- schema_version={structured_plan.get('schema_version', '')}",
                f"- task_type={structured_plan.get('task_type', '')}",
                f"- output_bucket={structured_plan.get('output_bucket', '')}",
                f"- target_cohort_conditions={','.join(structured_plan.get('target_cohort_conditions', []) or [])}",
                f"- source_tables={','.join(structured_plan.get('source_tables', []) or [])}",
                f"- join_keys={','.join(structured_plan.get('join_keys', []) or [])}",
                f"- required_fields={','.join(structured_plan.get('required_fields', []) or [])}",
                f"- forbidden_patterns={','.join(structured_plan.get('forbidden_patterns', []) or [])}",
                f"- source_filters_allowed={str(bool(structured_plan.get('source_filters_allowed', False))).lower()}",
                f"- fixed_dates_allowed={str(bool(structured_plan.get('fixed_dates_allowed', False))).lower()}",
                "Generated SQL must satisfy this structured plan.",
                "Do not add fixed historical dates unless fixed_dates_allowed=true.",
                "Do not add source/channel filters unless source_filters_allowed=true.",
                "Do not drop target cohort conditions.",
                "Do not simplify combo writeback into plain behavior scan.",
            ]
        )
