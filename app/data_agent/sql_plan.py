"""Deterministic structured SQL planning helpers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


STRUCTURED_SQL_PLAN_SCHEMA_VERSION = "structured_sql_plan_v1"
BEHAVIOR_TABLE_NAME = "dwb_b1_data_burying_point"
COHORT_TABLE_NAME = "dwd_w_apply"
BEHAVIOR_REQUIRED_FIELDS = ("uid", "timestamp_", "eventname")
BEHAVIOR_FORBIDDEN_PATTERNS = [
    "unresolved_uid_placeholder",
    "broad_behavior_scan",
    "historical_date_copy",
    "historical_source_filter",
    "literal_example_copy",
    "unsupported_field_family",
]


class SqlIntentPlan(BaseModel):
    schema_version: str = STRUCTURED_SQL_PLAN_SCHEMA_VERSION
    task_type: Literal["cohort_query", "bucket_writeback"]
    output_bucket: str | None = None
    country: str | None = None
    target_cohort_conditions: list[str] = Field(default_factory=list)
    source_tables: list[str] = Field(default_factory=list)
    join_keys: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    time_constraints: list[str] = Field(default_factory=list)
    source_filters_allowed: bool = False
    fixed_dates_allowed: bool = False
    uid_boundary_required: bool = False


class SqlPlanValidationResult(BaseModel):
    valid: bool
    code: str | None = None
    reason: str | None = None
    missing: list[str] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)


def build_structured_sql_plan(
    *,
    natural_language_request: str,
    run_type: str,
    output_bucket: str | None,
    country: str | None,
    retrieval_snapshot: dict,
) -> SqlIntentPlan:
    request_text = str(natural_language_request or "")
    target_conditions = _extract_target_cohort_conditions(request_text)
    grounded_fields_by_table = {
        str(table_name or ""): list(field_names or [])
        for table_name, field_names in dict(retrieval_snapshot or {}).get("grounded_fields_by_table", {}).items()
        if str(table_name or "")
    }
    grounded_tables = list(grounded_fields_by_table.keys())

    if run_type == "bucket_writeback":
        source_tables: list[str] = []
        if COHORT_TABLE_NAME in grounded_tables:
            source_tables.append(COHORT_TABLE_NAME)
        if output_bucket == "behavior" and BEHAVIOR_TABLE_NAME in grounded_tables:
            source_tables.append(BEHAVIOR_TABLE_NAME)
        required_fields: list[str] = ["uid"]
        if output_bucket == "behavior":
            grounded_behavior_fields = set(grounded_fields_by_table.get(BEHAVIOR_TABLE_NAME, []))
            required_fields = [field_name for field_name in BEHAVIOR_REQUIRED_FIELDS if field_name in grounded_behavior_fields]
        time_constraints = [marker for marker in target_conditions if marker == "recent_7d"]
        return SqlIntentPlan(
            task_type="bucket_writeback",
            output_bucket=output_bucket,
            country=country,
            target_cohort_conditions=target_conditions,
            source_tables=source_tables,
            join_keys=["uid"],
            required_fields=required_fields,
            forbidden_patterns=list(BEHAVIOR_FORBIDDEN_PATTERNS),
            time_constraints=time_constraints,
            source_filters_allowed=False,
            fixed_dates_allowed=False,
            uid_boundary_required=bool(output_bucket == "behavior"),
        )

    source_tables = []
    if COHORT_TABLE_NAME in grounded_tables:
        source_tables.append(COHORT_TABLE_NAME)
    elif grounded_tables:
        source_tables.append(grounded_tables[0])
    time_constraints = [marker for marker in target_conditions if marker == "recent_7d"]
    return SqlIntentPlan(
        task_type="cohort_query",
        output_bucket=output_bucket,
        country=country,
        target_cohort_conditions=target_conditions,
        source_tables=source_tables,
        join_keys=["uid"] if source_tables else [],
        required_fields=["uid"] if source_tables else [],
        forbidden_patterns=[
            "historical_date_copy",
            "historical_source_filter",
            "unsupported_field_family",
        ],
        time_constraints=time_constraints,
        source_filters_allowed=False,
        fixed_dates_allowed=False,
        uid_boundary_required=False,
    )


def validate_structured_sql_plan(
    *,
    plan: SqlIntentPlan,
    retrieval_snapshot: dict,
) -> SqlPlanValidationResult:
    grounded_fields_by_table = {
        str(table_name or ""): set(field_names or [])
        for table_name, field_names in dict(retrieval_snapshot or {}).get("grounded_fields_by_table", {}).items()
        if str(table_name or "")
    }
    grounded_tables = set(grounded_fields_by_table)

    if plan.task_type != "bucket_writeback":
        return SqlPlanValidationResult(valid=True)

    if not plan.output_bucket:
        return SqlPlanValidationResult(
            valid=False,
            code="DATA_AGENT_SQL_PLAN_INVALID",
            reason="Bucket writeback plan requires output_bucket.",
            missing=["output_bucket"],
        )

    if plan.output_bucket != "behavior":
        return SqlPlanValidationResult(valid=True)

    if not plan.target_cohort_conditions or plan.target_cohort_conditions == ["explicit_uid_list"] and plan.uid_boundary_required is False:
        return SqlPlanValidationResult(
            valid=False,
            code="DATA_AGENT_WRITEBACK_REQUIRES_COHORT",
            reason="Writeback requests require an explicit uid list or cohort conditions before SQL generation.",
            missing=["target_cohort_conditions"],
        )

    missing: list[str] = []
    if BEHAVIOR_TABLE_NAME not in grounded_tables:
        missing.append("behavior_table")
    if COHORT_TABLE_NAME not in plan.source_tables:
        missing.append("cohort_table")
    if BEHAVIOR_TABLE_NAME not in plan.source_tables:
        missing.append("behavior_source_table")

    behavior_grounded_fields = grounded_fields_by_table.get(BEHAVIOR_TABLE_NAME, set())
    for field_name in BEHAVIOR_REQUIRED_FIELDS:
        if field_name not in behavior_grounded_fields:
            missing.append(field_name)

    if missing:
        reason = "Behavior writeback plan requires uid, timestamp_, and eventname to be grounded by retrieved context."
        if "behavior_table" in missing:
            reason = "Behavior writeback plan requires grounded behavior table."
        return SqlPlanValidationResult(
            valid=False,
            code="DATA_AGENT_SQL_PLAN_INVALID",
            reason=reason,
            missing=missing,
        )

    return SqlPlanValidationResult(valid=True)


def _extract_target_cohort_conditions(natural_language_request: str) -> list[str]:
    request = str(natural_language_request or "").strip().lower()
    results: list[str] = []

    def _append(label: str) -> None:
        if label not in results:
            results.append(label)

    if any(token in request for token in ("首贷", "first loan", "first-loan", "first_loan")):
        _append("first_loan")
    if any(token in request for token in ("从未逾期", "never overdue", "never-overdue", "never_overdue")):
        _append("never_overdue")
    if any(token in request for token in ("高风险", "high risk", "high-risk", "high_risk")):
        _append("high_risk")
    if any(token in request for token in ("最近 7 天", "最近7天", "7 天", "7天", "7 days", "recent 7 days")):
        _append("recent_7d")
    if any(token in request for token in ("注册用户", "registered users", "registered user")):
        _append("registered_users")
    if "never_overdue" not in results and any(token in request for token in ("逾期用户", "overdue users", "overdue user")):
        _append("overdue_users")
    if any(token in request for token in ("uid", "uuid", "user_id", "userid", "用户列表")):
        _append("explicit_uid_list")
    return results
