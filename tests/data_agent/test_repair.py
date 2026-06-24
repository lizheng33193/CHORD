from __future__ import annotations

from app.data_agent.repair import (
    build_plan_guided_repair_instruction,
    select_repairable_plan_warnings,
)


def _snapshot(*, required_fields: list[str] | None = None) -> dict:
    return {
        "sql_intent_plan_summary": {
            "task_type": "bucket_writeback",
            "output_bucket": "behavior",
            "target_cohort_conditions": ["first_loan", "never_overdue"],
            "source_tables": ["dwd_w_apply", "dwb_b1_data_burying_point"],
            "join_keys": ["uid"],
            "required_fields": required_fields or ["uid", "timestamp_", "eventname"],
            "forbidden_patterns": [
                "unresolved_uid_placeholder",
                "broad_behavior_scan",
                "historical_date_copy",
                "historical_source_filter",
            ],
        }
    }


def test_select_repairable_plan_warnings_ignores_canonical_only_drift() -> None:
    warnings = [
        {"category": "NON_CANONICAL_FIELD", "evidence": "dwd_w_apply.user_uuid->uid"},
        {"category": "PLAN_CANONICAL_FIELD_DRIFT", "evidence": "dwd_w_apply.user_uuid->uid"},
    ]

    assert select_repairable_plan_warnings(warnings) == []


def test_build_repair_instruction_calls_for_removing_fixed_dates() -> None:
    instruction = build_plan_guided_repair_instruction(
        sql_text="SELECT uid FROM dwd_w_apply WHERE dt >= '20260201'",
        plan_warnings=[{"category": "PLAN_DATE_DRIFT", "evidence": "20260201"}],
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="找最近 7 天高风险用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert "20260201" in instruction
    assert "fixed historical date" in instruction.lower()
    assert "current request" in instruction.lower()


def test_build_repair_instruction_calls_for_removing_source_filters() -> None:
    instruction = build_plan_guided_repair_instruction(
        sql_text="SELECT uid FROM dwd_w_apply WHERE apply_source = 'MEX017'",
        plan_warnings=[{"category": "PLAN_SOURCE_FILTER_DRIFT", "evidence": "MEX017"}],
        retrieval_snapshot=_snapshot(required_fields=["uid"]),
        natural_language_request="找高风险用户",
        run_type="cohort_query",
        output_bucket=None,
    )

    assert "MEX017" in instruction
    assert "source" in instruction.lower()


def test_build_repair_instruction_requires_behavior_fields() -> None:
    instruction = build_plan_guided_repair_instruction(
        sql_text="SELECT b.uid FROM dwb_b1_data_burying_point b",
        plan_warnings=[{"category": "PLAN_REQUIRED_FIELD_MISSING", "evidence": "timestamp_,eventname"}],
        retrieval_snapshot=_snapshot(),
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    assert "timestamp_" in instruction
    assert "eventname" in instruction
    assert "required fields" in instruction.lower()


def test_build_repair_instruction_calls_for_target_cohort_before_behavior_join() -> None:
    instruction = build_plan_guided_repair_instruction(
        sql_text="SELECT uid, timestamp_, eventname FROM dwb_b1_data_burying_point LIMIT 100",
        plan_warnings=[{"category": "PLAN_BROAD_SCAN_RISK", "evidence": "dwb_b1_data_burying_point"}],
        retrieval_snapshot=_snapshot(),
        natural_language_request="找出墨西哥首贷且从未逾期的用户，并写回 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    assert "target cohort" in instruction.lower()
    assert "join behavior" in instruction.lower() or "join by uid" in instruction.lower()


def test_build_repair_instruction_preserves_combo_intent_and_reviewer_feedback_priority() -> None:
    instruction = build_plan_guided_repair_instruction(
        sql_text="SELECT user_uuid AS uid FROM dwd_w_apply",
        plan_warnings=[
            {"category": "PLAN_DATE_DRIFT", "evidence": "20260201"},
            {"category": "PLAN_CANONICAL_FIELD_DRIFT", "evidence": "dwd_w_apply.user_uuid->uid"},
        ],
        retrieval_snapshot=_snapshot(),
        natural_language_request="给首贷且从未逾期用户补齐 behavior",
        run_type="bucket_writeback",
        output_bucket="behavior",
        reviewer_feedback="保留首贷 cohort，不要把 cohort 丢掉。",
    )

    assert "reviewer feedback" in instruction.lower()
    assert "保留首贷 cohort" in instruction
    assert "preserve target cohort" in instruction.lower()
    assert "user_uuid" in instruction
