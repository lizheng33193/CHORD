"""Deterministic bounded-repair helpers for plan-guided regeneration."""

from __future__ import annotations

from collections.abc import Iterable


REPAIRABLE_PLAN_WARNING_CATEGORIES = {
    "PLAN_DATE_DRIFT",
    "PLAN_SOURCE_FILTER_DRIFT",
    "PLAN_REQUIRED_FIELD_MISSING",
    "PLAN_BROAD_SCAN_RISK",
    "PLAN_FORBIDDEN_PATTERN",
}


def select_repairable_plan_warnings(warnings: Iterable[dict] | None) -> list[dict]:
    selected: list[dict] = []
    for item in warnings or []:
        category = str((item or {}).get("category") or "").strip().upper()
        if category in REPAIRABLE_PLAN_WARNING_CATEGORIES:
            selected.append(dict(item))
    return selected


def build_plan_guided_repair_instruction(
    *,
    sql_text: str,
    plan_warnings: list[dict],
    retrieval_snapshot: dict,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
    reviewer_feedback: str | None = None,
) -> str:
    snapshot = dict(retrieval_snapshot or {})
    intent_plan = dict(snapshot.get("sql_intent_plan_summary") or {})
    required_fields = [str(field).strip() for field in (intent_plan.get("required_fields") or []) if str(field).strip()]
    target_cohort_conditions = [
        str(marker).strip() for marker in (intent_plan.get("target_cohort_conditions") or []) if str(marker).strip()
    ]
    source_tables = [str(table).strip() for table in (intent_plan.get("source_tables") or []) if str(table).strip()]
    join_keys = [str(key).strip() for key in (intent_plan.get("join_keys") or []) if str(key).strip()]
    warning_lines: list[str] = []
    for item in plan_warnings:
        category = str(item.get("category") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        warning_lines.append(f"- {category}: {evidence}")

    lines = [
        "Repair the SQL to follow the current request and SQL intent plan.",
        f"- run_type={run_type}",
        f"- output_bucket={output_bucket or ''}",
        f"- current_request={natural_language_request}",
    ]
    if reviewer_feedback:
        lines.extend(
            [
                "Reviewer feedback has higher priority than repair instruction and historical examples.",
                f"- reviewer_feedback={reviewer_feedback}",
            ]
        )
    if target_cohort_conditions:
        lines.append(f"- target_cohort_conditions={','.join(target_cohort_conditions)}")
    if source_tables:
        lines.append(f"- source_tables={','.join(source_tables)}")
    if join_keys:
        lines.append(f"- join_keys={','.join(join_keys)}")
    if required_fields:
        lines.append(f"- required_fields={','.join(required_fields)}")
    lines.extend(
        [
            "",
            "Problems detected:",
            *warning_lines,
            "",
            "Rules:",
            "- Preserve the current request intent.",
            "- Preserve target cohort and behavior join intent.",
            "- Build the target cohort first, then join behavior data by uid.",
            "- Do not introduce unresolved placeholders.",
            "- Do not broad-scan the behavior table.",
            "- Remove fixed historical date filters unless explicitly requested.",
            "- Remove source or channel filters unless explicitly requested.",
            "- Keep dynamic relative date expressions when the request is relative.",
            "- Treat canonical drift only as a low-priority hint; do not rewrite the task around it.",
            "- Do not output explanations, only return repaired SQL in the normal generator response.",
            "",
            "Original SQL for repair reference:",
            sql_text.strip(),
        ]
    )
    if output_bucket == "behavior" and required_fields:
        lines.append(f"- For behavior writeback, the repaired SQL must return the required fields: {', '.join(required_fields)}.")
    return "\n".join(line for line in lines if line is not None).strip()
