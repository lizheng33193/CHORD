"""th country pack 单元测试 — v6.1 双模式断言（risk_features vs buro）。"""

import logging

import pytest

from app.country_packs.app_profile import load_app_country_pack
from app.country_packs.behavior_profile import load_behavior_country_pack
from app.country_packs.credit_profile import load_credit_country_pack


def test_load_app_country_pack_th_returns_th_pack():
    pack = load_app_country_pack("th")
    assert pack.country_code == "th"
    assert pack.display_name == "Thailand"


def test_load_app_country_pack_mx_unchanged():
    pack = load_app_country_pack("mx")
    assert pack.country_code == "mx"
    assert pack.display_name == "Mexico"


def test_load_behavior_country_pack_th_uses_line_channel():
    pack = load_behavior_country_pack("th")
    assert pack.country_code == "th"
    assert pack.default_contact_channel == "LINE"
    assert pack.display_name == "泰国"
    assert "LINE" in pack.contact_channel_keywords
    assert "ลงทะเบียน" in pack.stage_keywords["acquisition"]


def test_load_credit_country_pack_th_is_risk_features_not_buro():
    """v6.1 核心断言 — TH credit 走 risk_features 模式，不是 buro。"""
    pack = load_credit_country_pack("th")
    assert pack.country_code == "th"
    assert pack.profile_mode == "risk_features"
    assert pack.source_display_name == "风控特征聚合表（泰国）"
    assert pack.currency_code == "THB"
    assert pack.score_band_thresholds == ()
    assert pack.account_type_labels == {}
    assert pack.risk_feature_labels
    assert pack.sentinel_values
    assert pack.risk_feature_labels["liveness_score"] == "人脸活体识别分数（防伪反欺诈）"
    assert pack.risk_feature_labels["max_yuqi_days"] == "历史最大逾期天数"
    assert "rule_hit_多头规则拦截" in pack.risk_feature_labels
    assert pack.sentinel_values["liveness_score"] == ("无活体分",)
    assert pack.sentinel_values["max_yuqi_days"] == ("无逾期",)


def test_load_credit_country_pack_th_no_ncb_residue():
    """v6.1 hard-gate 提前在单测中守门 — TH pack 不能含任何 NCB 语义。"""
    pack = load_credit_country_pack("th")
    assert "NCB" not in pack.source_display_name
    assert "National Credit Bureau" not in pack.source_display_name
    assert pack.score_band_thresholds == ()
    assert pack.account_type_labels == {}


def test_load_credit_country_pack_mx_buro_mode_unchanged():
    """v6.1 向后兼容 — mx credit pack 行为零变更。"""
    pack = load_credit_country_pack("mx")
    assert pack.country_code == "mx"
    assert pack.profile_mode == "buro"
    assert pack.source_display_name == "Buró de Crédito（墨西哥）"
    assert pack.currency_code == "MXN"
    assert pack.score_band_thresholds[0] == ("A", 700)
    assert pack.account_type_labels["CC"] == "信用卡"
    assert pack.risk_feature_labels == {}
    assert pack.sentinel_values == {}


def test_load_country_pack_unknown_falls_back_to_mx(caplog):
    with caplog.at_level(logging.WARNING):
        pack = load_credit_country_pack("xx")
    assert pack.country_code == "mx"
    assert pack.profile_mode == "buro"
