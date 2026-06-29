from __future__ import annotations

from types import SimpleNamespace

import pytest


def _settings(**overrides):
    defaults = {
        "hybrid_retrieval_enabled_raw": "0",
        "hybrid_retrieval_mode_raw": "deterministic_only",
        "hybrid_retrieval_source_namespace_raw": "m2b_legacy_v3",
        "hybrid_retrieval_vector_index_path_raw": "",
        "hybrid_retrieval_allow_countries_raw": "",
        "hybrid_retrieval_allow_project_ids_raw": "",
        "hybrid_retrieval_vector_rank_limit_raw": "8",
        "hybrid_retrieval_family_score_thresholds_json_raw": (
            '{"catalog_table": 0.18, "catalog_field": 0.16, "glossary_term": 0.17, "sql_example": 0.15}'
        ),
        "hybrid_retrieval_family_caps_json_raw": (
            '{"catalog_table": 1, "catalog_field": 2, "glossary_term": 1, "sql_example": 1}'
        ),
        "hybrid_retrieval_total_vector_supplement_cap_raw": "3",
        "hybrid_retrieval_deterministic_pass_guard_raw": "1",
        "hybrid_retrieval_shadow_sample_rate_raw": "0.0",
        "project_root": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_load_hybrid_config_defaults_to_disabled_deterministic_only() -> None:
    from app.data_agent.hybrid_runtime import HybridRetrievalMode, load_hybrid_config

    config = load_hybrid_config(_settings())

    assert config.enabled is False
    assert config.retrieval_mode is HybridRetrievalMode.DETERMINISTIC_ONLY
    assert config.allow_countries == []
    assert config.allow_project_ids == []
    assert config.errors == []


def test_load_hybrid_config_marks_invalid_json_as_config_error() -> None:
    from app.data_agent.hybrid_runtime import load_hybrid_config

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_family_score_thresholds_json_raw="{bad json",
        )
    )

    assert config.enabled is True
    assert "family_score_thresholds_json" in " ".join(config.errors)


def test_load_hybrid_config_marks_invalid_threshold_value_as_config_error() -> None:
    from app.data_agent.hybrid_runtime import load_hybrid_config

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_family_score_thresholds_json_raw='{"catalog_field":"oops"}',
        )
    )

    assert any("catalog_field" in error for error in config.errors)
    assert config.family_score_thresholds["catalog_field"] == 0.16


def test_load_hybrid_config_marks_invalid_cap_value_as_config_error() -> None:
    from app.data_agent.hybrid_runtime import load_hybrid_config

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_family_caps_json_raw='{"catalog_field":"oops"}',
        )
    )

    assert any("catalog_field" in error for error in config.errors)
    assert config.family_caps["catalog_field"] == 2


def test_effective_mode_allows_hybrid_candidate_when_allowlist_scope_and_config_pass() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_candidate",
            hybrid_retrieval_allow_countries_raw="mx",
            hybrid_retrieval_allow_project_ids_raw="agent-user-profile-fork",
            hybrid_retrieval_shadow_sample_rate_raw="0.0",
        )
    )
    decision = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="cohort_query",
        request_key="stable-request",
    )

    assert decision.configured_mode is HybridRetrievalMode.HYBRID_CANDIDATE
    assert decision.effective_mode is HybridRetrievalMode.HYBRID_CANDIDATE
    assert decision.sample_hit is True
    assert decision.should_attempt_shadow is True
    assert decision.fallback_reason is None


def test_effective_mode_keeps_hybrid_enabled_forced_to_deterministic() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridFallbackReason,
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_enabled",
            hybrid_retrieval_allow_countries_raw="mx",
            hybrid_retrieval_allow_project_ids_raw="agent-user-profile-fork",
        )
    )
    decision = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="cohort_query",
        request_key="stable-request",
    )

    assert decision.configured_mode is HybridRetrievalMode.HYBRID_ENABLED
    assert decision.effective_mode is HybridRetrievalMode.DETERMINISTIC_ONLY
    assert decision.fallback_reason is HybridFallbackReason.MODE_FORCED_DETERMINISTIC


def test_effective_mode_rejects_empty_allowlists_by_default() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridFallbackReason,
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_shadow_sample_rate_raw="1.0",
        )
    )
    decision = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="cohort_query",
        request_key="stable-request",
    )

    assert decision.effective_mode is HybridRetrievalMode.DETERMINISTIC_ONLY
    assert decision.fallback_reason is HybridFallbackReason.COUNTRY_NOT_ALLOWLISTED


def test_effective_mode_shadow_sample_rate_is_stable_and_requires_allowlist_hit() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_allow_countries_raw="mx",
            hybrid_retrieval_allow_project_ids_raw="agent-user-profile-fork",
            hybrid_retrieval_shadow_sample_rate_raw="1.0",
        )
    )
    first = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="cohort_query",
        request_key="stable-request",
    )
    second = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="cohort_query",
        request_key="stable-request",
    )

    assert first.effective_mode is HybridRetrievalMode.HYBRID_SHADOW
    assert second.effective_mode is HybridRetrievalMode.HYBRID_SHADOW
    assert first.sample_hit is True
    assert second.sample_hit is True


def test_effective_mode_never_infers_run_type_and_rejects_unsupported_scope() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridFallbackReason,
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    config = load_hybrid_config(
        _settings(
            hybrid_retrieval_enabled_raw="1",
            hybrid_retrieval_mode_raw="hybrid_shadow",
            hybrid_retrieval_allow_countries_raw="mx",
            hybrid_retrieval_allow_project_ids_raw="agent-user-profile-fork",
            hybrid_retrieval_shadow_sample_rate_raw="1.0",
        )
    )
    decision = evaluate_effective_mode(
        config=config,
        country="mx",
        project_id="agent-user-profile-fork",
        run_type="bucket_writeback",
        request_key="stable-request",
    )

    assert decision.effective_mode is HybridRetrievalMode.DETERMINISTIC_ONLY
    assert decision.fallback_reason is HybridFallbackReason.UNSUPPORTED_RUN_TYPE


def test_canonical_key_for_field_is_stable_and_prefers_field_name() -> None:
    from app.data_agent.hybrid_runtime import _canonical_key_for_record

    record = {
        "asset_family": "catalog_field",
        "source_key": "field.mx.dwd_w_apply.withdraw_uuid",
        "title": "dwd_w_apply.withdraw_uuid",
        "metadata": {
            "field_name": "withdraw_uuid",
            "aliases": ["loan_order_id", "withdraw_id"],
        },
    }

    keys = {_canonical_key_for_record(record)[1] for _ in range(10)}
    assert keys == {"withdraw_uuid"}


def test_canonical_key_for_glossary_prefers_term_or_title_over_synonyms() -> None:
    from app.data_agent.hybrid_runtime import _canonical_key_for_record

    record = {
        "asset_family": "glossary_term",
        "source_key": "glossary.mx.mob1",
        "title": "mob1",
        "metadata": {
            "term": "mob1",
            "synonyms": ["settled 7d no reborrow", "首贷结清流失"],
        },
    }

    family, key, _title = _canonical_key_for_record(record)
    assert family == "glossary_term"
    assert key == "mob1"


def test_select_vector_supplements_is_stable_for_duplicate_field_candidates() -> None:
    from app.data_agent.hybrid_runtime import HybridRetrievalConfigV1, HybridRetrievalMode, _select_vector_supplements

    config = HybridRetrievalConfigV1(
        enabled=True,
        retrieval_mode=HybridRetrievalMode.HYBRID_SHADOW,
        source_namespace="m2b_legacy_v3",
        vector_index_path=None,
        allow_countries=["mx"],
        allow_project_ids=["1"],
        vector_rank_limit=8,
        family_score_thresholds={
            "catalog_table": 0.18,
            "catalog_field": 0.16,
            "glossary_term": 0.17,
            "sql_example": 0.15,
        },
        family_caps={
            "catalog_table": 1,
            "catalog_field": 2,
            "glossary_term": 1,
            "sql_example": 1,
        },
        total_vector_supplement_cap=3,
        deterministic_pass_guard=True,
        shadow_sample_rate=1.0,
        errors=[],
    )
    deterministic_candidates: list[dict] = []
    vector_candidates = [
        {
            "record_id": "r1",
            "source_key": "field.mx.dwd_w_apply.withdraw_uuid",
            "asset_family": "catalog_field",
            "canonical_key": "withdrawuuid",
            "title": "dwd_w_apply.withdraw_uuid",
            "score": 0.9,
            "rank": 1,
        },
        {
            "record_id": "r2",
            "source_key": "field.mx.alias.withdraw_id",
            "asset_family": "catalog_field",
            "canonical_key": "withdrawuuid",
            "title": "withdraw_id",
            "score": 0.8,
            "rank": 2,
        },
    ]

    accepted, rejected = _select_vector_supplements(
        config=config,
        deterministic_candidates=deterministic_candidates,
        vector_candidates=vector_candidates,
    )

    assert [item["record_id"] for item in accepted] == ["r1"]
    assert rejected[0]["rejected_reason"] == "duplicate_with_accepted_supplement"
