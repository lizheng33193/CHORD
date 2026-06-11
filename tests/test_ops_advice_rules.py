from app.country_packs.mx.ops_advice_rules import MX_OPS_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENTS


def test_all_six_segments_present():
    assert set(MX_OPS_ADVICE_RULES.keys()) == set(MX_SEGMENTS)


def test_each_segment_has_required_keys():
    required = {"collection_strategy", "churn_warning", "outreach_channel",
                "retention_offer", "tags"}
    for seg, rule in MX_OPS_ADVICE_RULES.items():
        assert required.issubset(rule.keys()), f"{seg} missing keys"


def test_s4_strong_churn_warning():
    s4 = MX_OPS_ADVICE_RULES["S4"]
    assert s4["churn_warning"]["level"] == "强"
    assert s4["retention_offer"]["type"] is not None


def test_s5_no_offer():
    s5 = MX_OPS_ADVICE_RULES["S5"]
    assert s5["retention_offer"]["type"] is None
    assert s5["collection_strategy"]["intensity"] == "strong"
