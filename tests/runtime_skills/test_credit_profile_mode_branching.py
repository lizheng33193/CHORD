"""v6.1 路径 Q + profile_mode 分支单测。"""

import pytest

from app.country_packs.credit_profile import load_credit_country_pack
from app.runtime_skills.credit_profile.contracts import build_credit_run_context


def test_build_credit_run_context_th_emits_risk_features_profile_mode():
    """v6.1 路径 Q — TH context 必须含 profile_mode='risk_features'。"""
    context = build_credit_run_context("u_th_1", country_code="th")
    assert context["country_code"] == "th"
    assert context["profile_mode"] == "risk_features"


def test_build_credit_run_context_mx_emits_buro_profile_mode():
    """v6.1 路径 Q — mx context 必须含 profile_mode='buro'。"""
    context = build_credit_run_context("u_mx_1", country_code="mx")
    assert context["country_code"] == "mx"
    assert context["profile_mode"] == "buro"


def test_credit_explainer_accepts_dual_prompt_paths(tmp_path):
    """v6.1 路径 Q — CreditExplainer.__init__ 必须接受 prompt_paths 字典。"""
    from app.core.model_client import ModelClient
    from app.runtime_skills.credit_profile.explainer import CreditExplainer

    buro = tmp_path / "buro.md"
    risk = tmp_path / "th.md"
    buro.write_text("buro template")
    risk.write_text("risk_features template")

    explainer = CreditExplainer(
        ModelClient(),
        prompt_paths={"buro": buro, "risk_features": risk},
    )
    assert "buro" in explainer.prompt_paths
    assert "risk_features" in explainer.prompt_paths


def test_th_pack_does_not_leak_into_buro_path():
    """TH pack 的 score_band_thresholds 永远空，feature_builder 必须按 profile_mode 跳过 mx 路径。"""
    pack = load_credit_country_pack("th")
    assert pack.profile_mode == "risk_features"
    assert pack.score_band_thresholds == ()


def test_mx_pack_does_not_use_risk_feature_labels():
    """mx pack 在 buro 路径下不依赖 risk_feature_labels（向后兼容）。"""
    pack = load_credit_country_pack("mx")
    assert pack.profile_mode == "buro"
    assert pack.risk_feature_labels == {}
    assert pack.sentinel_values == {}
