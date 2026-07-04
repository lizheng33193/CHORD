from __future__ import annotations


def test_sql_semantic_validator_blocks_country_scope_mismatch_from_structured_plan() -> None:
    from app.data_agent.semantic_validation import (
        SqlSemanticValidationRequest,
        validate_sql_semantics,
    )

    result = validate_sql_semantics(
        SqlSemanticValidationRequest(
            query="查询墨西哥高风险用户",
            sql="SELECT uid FROM dwd_w_apply WHERE risk_level = 'high'",
            structured_sql_plan={
                "task_type": "cohort_query",
                "country": "ph",
                "source_tables": ["dwd_w_apply"],
                "join_keys": ["uid"],
                "required_fields": ["uid"],
            },
            expected_country="mx",
        )
    )

    assert result.validation_status == "blocked"
    assert result.requires_human_review is True
    assert any(item.code == "COUNTRY_SCOPE_MISMATCH" and item.blocking for item in result.violations)


def test_sql_semantic_validator_blocks_risky_write_operation() -> None:
    from app.data_agent.semantic_validation import (
        SqlSemanticValidationRequest,
        validate_sql_semantics,
    )

    result = validate_sql_semantics(
        SqlSemanticValidationRequest(
            query="更新用户风险等级",
            sql="UPDATE dwd_w_apply SET risk_level = 'high' WHERE uid = 'u1'",
            structured_sql_plan={
                "task_type": "cohort_query",
                "country": "mx",
                "source_tables": ["dwd_w_apply"],
                "join_keys": ["uid"],
                "required_fields": ["uid"],
            },
            expected_country="mx",
        )
    )

    assert result.validation_status == "blocked"
    assert any(item.code == "RISKY_SQL_OPERATION" for item in result.violations)


def test_review_sql_candidate_surfaces_semantic_validation_and_blocks_execution_eligibility() -> None:
    from app.data_agent.service import _review_sql_candidate

    result = _review_sql_candidate(
        sql_text="SELECT eventname FROM dwb_b1_data_burying_point",
        sql_kind="query_only",
        target_country="mx",
        retrieval_snapshot={
            "structured_sql_plan": {
                "task_type": "bucket_writeback",
                "country": "mx",
                "source_tables": ["dwd_w_apply", "dwb_b1_data_burying_point"],
                "join_keys": ["uid"],
                "required_fields": ["uid", "timestamp_", "eventname"],
                "uid_boundary_required": True,
            }
        },
        natural_language_request="给首贷且从未逾期用户补齐行为数据",
        run_type="bucket_writeback",
        output_bucket="behavior",
    )

    assert result["status"] == "blocked"
    assert result["semantic_validation"]["validation_status"] == "blocked"
    assert any(item["code"] == "UID_BOUNDARY_MISSING" for item in result["semantic_validation"]["violations"])

