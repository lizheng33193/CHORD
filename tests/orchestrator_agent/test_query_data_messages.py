from app.services.orchestrator_agent.finalization.query_data_messages import (
    build_query_data_observation_message,
    build_query_empty_message,
    build_query_data_preview_text,
    build_query_too_large_message,
)


def test_build_query_empty_message_for_query_only_mentions_zero_and_relaxing_filters():
    message = build_query_empty_message(query_mode="query_only")

    assert "没有命中用户" in message
    assert "UID 数量：0" in message
    assert "放宽筛选条件" in message
    assert "执行失败" not in message


def test_build_query_empty_message_for_query_profile_mentions_no_profile_start():
    message = build_query_empty_message(query_mode="query_profile")

    assert "没有可继续画像的 UID" in message
    assert "不会启动画像分析" in message
    assert "放宽筛选条件" in message
    assert "执行失败" not in message


def test_build_query_too_large_message_mentions_limit_and_narrowing_filters():
    message = build_query_too_large_message(query_mode="query_profile", cohort_size=356, limit=200)

    assert "356" in message
    assert "200" in message
    assert "缩小范围" in message
    assert "执行失败" not in message


def test_build_query_data_observation_message_for_empty_guides_relaxing_filters():
    message = build_query_data_observation_message(
        {
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 0,
            "sql_text": "SELECT uid FROM t",
            "internal_metadata": {"x": 1},
        }
    )

    assert message is not None
    assert "没有命中用户" in message
    assert "放宽筛选条件" in message
    assert "SELECT" not in message
    assert "internal_metadata" not in message


def test_build_query_data_observation_message_for_too_large_uses_rows_estimated_when_uids_missing():
    message = build_query_data_observation_message(
        {
            "uids": [],
            "rows_estimated": 356,
            "reason": "cohort_too_large",
            "sql_text": "SELECT uid FROM t",
        },
        limit=200,
    )

    assert message is not None
    assert "356" in message
    assert "200" in message
    assert "缩小范围" in message
    assert "不会继续画像或后续分析" in message
    assert "SELECT" not in message


def test_build_query_data_preview_text_for_query_only_contains_sections_and_raw_sql():
    message = build_query_data_preview_text(
        query_mode="query_only",
        country="mx",
        time_window_label="最近7天",
        filters_summary=["active users", "loan applicants"],
        raw_sql="SELECT uid FROM t",
        rows_estimated=128,
    )

    assert "查询摘要" in message
    assert "筛选条件" in message
    assert "确认提示" in message
    assert "原始 SQL" in message
    assert "国家/市场：mx" in message
    assert "时间范围：最近7天" in message
    assert "条件：active users；loan applicants" in message
    assert "预计影响范围：约 128 行" in message
    assert "SELECT uid FROM t" in message
    assert "```" not in message


def test_build_query_data_preview_text_for_query_profile_mentions_profile_continuation():
    message = build_query_data_preview_text(
        query_mode="query_profile",
        country="mx",
        time_window_label=None,
        filters_summary=None,
        raw_sql="SELECT uid FROM t",
        rows_estimated=5,
    )

    assert "确认后，这批 UID 将继续用于画像分析" in message
    assert "SELECT uid FROM t" in message


def test_build_query_data_preview_text_omits_estimate_when_non_positive_and_none_sql_is_safe():
    message = build_query_data_preview_text(
        query_mode="query_only",
        country=None,
        time_window_label=None,
        filters_summary=None,
        raw_sql=None,
        rows_estimated=0,
    )

    assert "预计影响范围" not in message
    assert "None" not in message
    assert "未提供 SQL 预览" in message
