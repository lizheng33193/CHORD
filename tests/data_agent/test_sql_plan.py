from __future__ import annotations

from app.data_agent.sql_plan import (
    SqlIntentPlan,
    build_structured_sql_plan,
    validate_structured_sql_plan,
)


def _snapshot(
    *,
    grounded_fields_by_table: dict[str, list[str]] | None = None,
) -> dict:
    return {
        "country": "mx",
        "grounded_fields_by_table": grounded_fields_by_table
        or {
            "dwd_w_apply": ["uid", "risk_level", "apply_time"],
            "dwb_b1_data_burying_point": ["uid", "timestamp_", "eventname"],
        },
    }


def test_build_structured_sql_plan_for_combo_behavior_writeback() -> None:
    plan = build_structured_sql_plan(
        natural_language_request="给首贷且从未逾期用户补齐行为数据",
        run_type="bucket_writeback",
        output_bucket="behavior",
        country="mx",
        retrieval_snapshot=_snapshot(),
    )

    assert isinstance(plan, SqlIntentPlan)
    assert plan.schema_version == "structured_sql_plan_v1"
    assert plan.task_type == "bucket_writeback"
    assert plan.output_bucket == "behavior"
    assert "first_loan" in plan.target_cohort_conditions
    assert "never_overdue" in plan.target_cohort_conditions
    assert "overdue_users" not in plan.target_cohort_conditions
    assert "dwd_w_apply" in plan.source_tables
    assert "dwb_b1_data_burying_point" in plan.source_tables
    assert plan.required_fields == ["uid", "timestamp_", "eventname"]
    assert plan.source_filters_allowed is False
    assert plan.fixed_dates_allowed is False


def test_validate_structured_sql_plan_requires_cohort_for_under_specified_writeback() -> None:
    plan = build_structured_sql_plan(
        natural_language_request="帮我查询并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
        country="mx",
        retrieval_snapshot=_snapshot(),
    )

    result = validate_structured_sql_plan(plan=plan, retrieval_snapshot=_snapshot())

    assert result.valid is False
    assert result.code == "DATA_AGENT_WRITEBACK_REQUIRES_COHORT"


def test_validate_structured_sql_plan_requires_behavior_table() -> None:
    snapshot = _snapshot(
        grounded_fields_by_table={
            "dwd_w_apply": ["uid", "risk_level", "apply_time"],
        }
    )
    plan = build_structured_sql_plan(
        natural_language_request="给首贷且从未逾期用户补齐行为数据",
        run_type="bucket_writeback",
        output_bucket="behavior",
        country="mx",
        retrieval_snapshot=snapshot,
    )

    result = validate_structured_sql_plan(plan=plan, retrieval_snapshot=snapshot)

    assert result.valid is False
    assert result.code == "DATA_AGENT_SQL_PLAN_INVALID"
    assert "behavior_table" in result.missing


def test_validate_structured_sql_plan_requires_grounded_behavior_fields() -> None:
    snapshot = _snapshot(
        grounded_fields_by_table={
            "dwd_w_apply": ["uid", "risk_level", "apply_time"],
            "dwb_b1_data_burying_point": ["uid", "timestamp_"],
        }
    )
    plan = build_structured_sql_plan(
        natural_language_request="给首贷且从未逾期用户补齐行为数据",
        run_type="bucket_writeback",
        output_bucket="behavior",
        country="mx",
        retrieval_snapshot=snapshot,
    )

    result = validate_structured_sql_plan(plan=plan, retrieval_snapshot=snapshot)

    assert result.valid is False
    assert result.code == "DATA_AGENT_SQL_PLAN_INVALID"
    assert "eventname" in result.missing


def test_build_structured_sql_plan_keeps_cohort_query_lightweight() -> None:
    plan = build_structured_sql_plan(
        natural_language_request="找最近 7 天高风险用户",
        run_type="cohort_query",
        output_bucket=None,
        country="mx",
        retrieval_snapshot=_snapshot(
            grounded_fields_by_table={
                "dwd_w_apply": ["uid", "apply_time"],
            }
        ),
    )

    result = validate_structured_sql_plan(
        plan=plan,
        retrieval_snapshot=_snapshot(
            grounded_fields_by_table={
                "dwd_w_apply": ["uid", "apply_time"],
            }
        ),
    )

    assert plan.task_type == "cohort_query"
    assert "recent_7d" in plan.target_cohort_conditions
    assert "high_risk" in plan.target_cohort_conditions
    assert result.valid is True
