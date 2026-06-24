from __future__ import annotations

from app.data_agent.plan_review import review_sql_against_intent_plan


def _snapshot(
    *,
    required_fields: list[str] | None = None,
    forbidden_patterns: list[str] | None = None,
    canonical_map: dict[str, dict[str, str]] | None = None,
) -> dict:
    return {
        "sql_intent_plan_summary": {
            "task_type": "bucket_writeback",
            "output_bucket": "behavior",
            "target_cohort_conditions": ["first_loan", "never_overdue"],
            "source_tables": ["dwd_w_apply", "dwb_b1_data_burying_point"],
            "join_keys": ["uid"],
            "required_fields": required_fields or ["uid", "timestamp_", "eventname"],
            "forbidden_patterns": forbidden_patterns
            or [
                "unresolved_uid_placeholder",
                "broad_behavior_scan",
                "historical_date_copy",
                "historical_source_filter",
                "literal_example_copy",
                "unsupported_field_family",
            ],
        },
        "canonical_alternative_to_preferred_by_table": canonical_map
        or {"dwd_w_apply": {"user_uuid": "uid"}},
        "grounded_fields_by_table": {
            "dwd_w_apply": ["uid", "user_uuid", "risk_level", "apply_time"],
            "dwb_b1_data_burying_point": ["uid", "timestamp_", "eventname"],
        },
    }


def test_review_flags_fixed_historical_date_drift() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text="SELECT uid FROM dwd_w_apply WHERE dt >= '20260201'",
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="找最近 7 天高风险用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert any(item["category"] == "PLAN_DATE_DRIFT" for item in warnings)


def test_review_does_not_flag_dynamic_relative_date_expression() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text=(
            "SELECT uid FROM dwd_w_apply "
            "WHERE dt >= date_format(date_sub(current_date, 7), 'yyyyMMdd')"
        ),
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="找最近 7 天高风险用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert not any(item["category"] == "PLAN_DATE_DRIFT" for item in warnings)


def test_review_flags_source_filter_drift() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text="SELECT uid FROM dwd_w_apply WHERE apply_source = 'MEX017'",
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="找高风险用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert any(item["category"] == "PLAN_SOURCE_FILTER_DRIFT" for item in warnings)


def test_review_flags_canonical_field_drift() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text="SELECT user_uuid AS uid FROM dwd_w_apply",
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="查询首贷用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert any(item["category"] == "PLAN_CANONICAL_FIELD_DRIFT" for item in warnings)


def test_review_flags_behavior_required_fields_missing_from_select_output() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text=(
            "SELECT uid FROM dwb_b1_data_burying_point "
            "WHERE eventname = 'click'"
        ),
        retrieval_snapshot=_snapshot(),
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    assert any(item["category"] == "PLAN_REQUIRED_FIELD_MISSING" for item in warnings)
    evidence = next(item["evidence"] for item in warnings if item["category"] == "PLAN_REQUIRED_FIELD_MISSING")
    assert "timestamp_" in evidence
    assert "eventname" in evidence


def test_review_flags_behavior_broad_scan_even_with_limit() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text=(
            "SELECT uid, timestamp_, eventname "
            "FROM dwb_b1_data_burying_point LIMIT 100"
        ),
        retrieval_snapshot=_snapshot(),
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    assert any(item["category"] == "PLAN_BROAD_SCAN_RISK" for item in warnings)


def test_review_flags_forbidden_placeholder_pattern() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text="SELECT uid FROM dwd_w_apply WHERE uid IN (<target_users>)",
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="查询指定 uid 列表",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert any(item["category"] == "PLAN_FORBIDDEN_PATTERN" for item in warnings)


def test_review_accepts_clean_cohort_plus_behavior_join_sql() -> None:
    warnings = review_sql_against_intent_plan(
        sql_text=(
            "WITH target_users AS ("
            " SELECT uid FROM dwd_w_apply WHERE risk_level = 'high'"
            ") "
            "SELECT b.uid, b.timestamp_, b.eventname "
            "FROM dwb_b1_data_burying_point b "
            "JOIN target_users t ON b.uid = t.uid"
        ),
        retrieval_snapshot=_snapshot(),
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    categories = {item["category"] for item in warnings}
    assert "PLAN_DATE_DRIFT" not in categories
    assert "PLAN_SOURCE_FILTER_DRIFT" not in categories
    assert "PLAN_BROAD_SCAN_RISK" not in categories
    assert "PLAN_REQUIRED_FIELD_MISSING" not in categories
