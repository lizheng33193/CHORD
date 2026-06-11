from app.country_packs.mx.product_advice_rules import MX_PRODUCT_ADVICE_RULES
from app.country_packs.mx.segments import MX_SEGMENTS


def test_all_six_segments_present():
    assert set(MX_PRODUCT_ADVICE_RULES.keys()) == set(MX_SEGMENTS)


def test_each_segment_has_required_keys():
    required = {"renewal_strategy", "credit_line_action", "rate_plan",
                "recommended_channel", "priority", "tags"}
    for seg, rule in MX_PRODUCT_ADVICE_RULES.items():
        assert required.issubset(rule.keys()), f"{seg} missing keys"


def test_s5_no_proactive_renewal():
    s5 = MX_PRODUCT_ADVICE_RULES["S5"]
    assert "不主动" in s5["renewal_strategy"]["action"]
    assert s5["credit_line_action"]["action"] == "控额"
    assert s5["credit_line_action"]["delta_pct_range"] is None


def test_s1_proactive_credit_increase():
    s1 = MX_PRODUCT_ADVICE_RULES["S1"]
    assert s1["credit_line_action"]["action"] == "主动提额"
    lo, hi = s1["credit_line_action"]["delta_pct_range"]
    assert lo == 30 and hi == 50
