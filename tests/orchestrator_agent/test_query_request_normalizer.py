from app.services.orchestrator_agent.planning.query_request_normalizer import normalize_query_request
from app.services.orchestrator_agent.schemas import QueryDataInput, RequestUnderstanding


def _understanding(**candidate_defaults) -> RequestUnderstanding:
    return RequestUnderstanding(
        intent="query_data_then_profile",
        route_label="查询 cohort",
        rewritten_goal="查询一批用户并按需要继续画像",
        focus=["cohort"],
        requires_tools=True,
        route_reason="需要先取数。",
        answer_mode="tool_execution",
        candidate_defaults=candidate_defaults,
    )


def test_normalize_query_request_recognizes_country_time_and_query_only_mode():
    normalized = normalize_query_request(
        request_text="筛选墨西哥过去30天活跃的用户",
        country_hint=None,
        request_understanding=_understanding(auto_profile=False),
        default_query_mode="unknown",
        default_auto_profile=False,
    )

    assert normalized.original_text == "筛选墨西哥过去30天活跃的用户"
    assert normalized.country == "mx"
    assert normalized.time_window_key == "last_30_days"
    assert normalized.time_window_label == "过去30天"
    assert normalized.query_mode == "query_only"
    assert normalized.auto_profile is False
    assert normalized.filters_summary == ["active users"]
    assert normalized.effective_request_text.startswith("筛选墨西哥过去30天活跃的用户")
    assert "[Normalized query hints]" in normalized.effective_request_text
    assert "country: mx" in normalized.effective_request_text
    assert "time_window: last_30_days" in normalized.effective_request_text
    assert "query_mode: query_only" in normalized.effective_request_text
    assert "auto_profile: false" in normalized.effective_request_text


def test_normalize_query_request_prefers_query_profile_when_query_and_profile_both_present():
    normalized = normalize_query_request(
        request_text="找出墨西哥近一个月申请贷款的用户，并分析画像",
        country_hint=None,
        default_query_mode="unknown",
        default_auto_profile=None,
    )

    assert normalized.country == "mx"
    assert normalized.time_window_key == "last_30_days"
    assert normalized.query_mode == "query_profile"
    assert normalized.auto_profile is True
    assert normalized.filters_summary == ["loan applicants"]


def test_normalize_query_request_explicit_auto_profile_false_wins_over_profile_words_and_defaults():
    normalized = normalize_query_request(
        request_text="找墨西哥最近7天高流失用户并分析",
        country_hint="mx",
        clarification_answers={"auto_profile": "否", "time_window": "最近 7 天"},
        default_query_mode="query_profile",
        default_auto_profile=True,
    )

    assert normalized.country == "mx"
    assert normalized.time_window_key == "last_7_days"
    assert normalized.query_mode == "query_only"
    assert normalized.auto_profile is False
    assert "auto_profile: false" in normalized.effective_request_text


def test_normalize_query_request_is_idempotent_and_keeps_original_text():
    first = normalize_query_request(
        request_text="筛选最近 7 天高风险用户",
        country_hint="mx",
        default_query_mode="query_only",
        default_auto_profile=False,
    )
    second = normalize_query_request(
        request_text=first.effective_request_text,
        country_hint="mx",
        default_query_mode="query_only",
        default_auto_profile=False,
    )

    assert first.effective_request_text.count("[Normalized query hints]") == 1
    assert second.effective_request_text.count("[Normalized query hints]") == 1
    assert second.effective_request_text.startswith("筛选最近 7 天高风险用户")


def test_normalize_query_request_filters_summary_does_not_echo_raw_sql_fragments():
    normalized = normalize_query_request(
        request_text="帮我找安装了 app 的用户，别把 SELECT * FROM users 或 DROP TABLE 带进去",
        country_hint="mx",
        default_query_mode="query_only",
        default_auto_profile=False,
    )

    assert normalized.filters_summary == ["app installed users"]
    combined = " ".join(normalized.filters_summary).lower()
    assert "select" not in combined
    assert "drop" not in combined


def test_normalize_query_request_does_not_match_th_inside_english_words():
    for text in [
        "find the users who logged in last 7 days",
        "show the cohort",
        "other users",
        "the app installed users",
    ]:
        normalized = normalize_query_request(
            request_text=text,
            country_hint=None,
            default_query_mode="query_only",
            default_auto_profile=False,
        )
        assert normalized.country is None


def test_normalize_query_request_recognizes_latin_country_aliases_as_words():
    assert normalize_query_request(
        request_text="Thailand users",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "th"
    assert normalize_query_request(
        request_text="th users",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "th"
    assert normalize_query_request(
        request_text="Mexico users",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "mx"
    assert normalize_query_request(
        request_text="México users",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "mx"
    assert normalize_query_request(
        request_text="墨西哥用户",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "mx"
    assert normalize_query_request(
        request_text="泰国用户",
        country_hint=None,
        default_query_mode="query_only",
        default_auto_profile=False,
    ).country == "th"


def test_normalize_query_request_prefers_explicit_country_hint_over_text_inference():
    normalized = normalize_query_request(
        request_text="Thailand users",
        country_hint="mx",
        default_query_mode="query_only",
        default_auto_profile=False,
    )

    assert normalized.country == "mx"


def test_query_public_contracts_remain_unchanged():
    assert set(QueryDataInput.model_fields) == {"request", "country"}
    assert "time_window_key" not in QueryDataInput.model_fields
    assert "query_mode" not in QueryDataInput.model_fields
    assert "normalized_query" not in QueryDataInput.model_fields
