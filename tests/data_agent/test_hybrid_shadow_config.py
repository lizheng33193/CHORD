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


def test_effective_mode_forces_deterministic_when_candidate_or_enabled_is_configured() -> None:
    from app.data_agent.hybrid_runtime import (
        HybridFallbackReason,
        HybridRetrievalMode,
        evaluate_effective_mode,
        load_hybrid_config,
    )

    for configured in ("hybrid_candidate", "hybrid_enabled"):
        config = load_hybrid_config(
            _settings(
                hybrid_retrieval_enabled_raw="1",
                hybrid_retrieval_mode_raw=configured,
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
        assert decision.configured_mode is not HybridRetrievalMode.DETERMINISTIC_ONLY
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

