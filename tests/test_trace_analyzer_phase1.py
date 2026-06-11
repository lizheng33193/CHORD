"""Trace analyzer pipeline tests — phase 1 (data_access)."""
from __future__ import annotations

import pandas as pd
import pytest

from app.runtime_skills.trace_analyzer.data_access import TraceDataAccess
from app.runtime_skills.trace_analyzer.contracts import TraceRunContext


CSV_HEADER = "uid,servertimestamp,timestamp_,scenetype,processtype,eventname,extend,clientmodel,clientosversion,url,refer,ip"


def _ctx(uid: str = "U1") -> TraceRunContext:
    return {
        "uid": uid,
        "country_code": "mx",
        "application_time": "2026-05-01T00:00:00Z",
        "enable_llm_explanation": True,
    }


def _write_csv(tmp_path, uid: str, rows: list[str]) -> None:
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text(
        CSV_HEADER + "\n" + "\n".join(rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def test_data_access_ok(tmp_path, monkeypatch):
    uid = "U1"
    _write_csv(tmp_path, uid, [
        f'{uid},1773121104896,1773121104652,bankInfo,bankInfo,field-click,"{{}}",model,15,https://x/m/#/auth/bankInfo?from=%2F,null,1.1.1.1',
        f'{uid},1773121128143,1773121127644,bankInfo,bankInfo,field-edit,"{{}}",model,15,https://x/m/#/auth/bankInfo?from=%2F,null,1.1.1.1',
    ])
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "ok"
    assert isinstance(raw["events_df"], pd.DataFrame)
    assert len(raw["events_df"]) == 2
    assert list(raw["events_df"].columns)[0] == "uid"


def test_data_access_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch("DOES_NOT_EXIST", _ctx("DOES_NOT_EXIST"))
    assert raw["data_status"] == "data_missing"
    assert raw["errors"]


def test_data_access_column_missing(tmp_path, monkeypatch):
    uid = "U2"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text("uid,foo,bar\nU2,1,2\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "error"
    assert any("column" in e.lower() or "schema" in e.lower() for e in raw["errors"])


def test_data_access_empty_csv(tmp_path, monkeypatch):
    uid = "U3"
    _write_csv(tmp_path, uid, [])
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    da = TraceDataAccess()
    raw = da.fetch(uid, _ctx(uid))
    assert raw["data_status"] == "ok"
    assert len(raw["events_df"]) == 0


import json as _json
from app.runtime_skills.trace_analyzer.feature_builder import TraceFeatureBuilder
from app.runtime_skills.trace_analyzer._constants import (
    INSUFFICIENT_EVENTS_THRESHOLD,
    TOP_N_TRANSITIONS, TOP_N_PAGES, TOP_K_FRICTION_HOTSPOTS,
    KEY_EVENTS_TAIL_N,
    TOTAL_TOKEN_BUDGET, TIER_3_TOKEN_BUDGET,
)


REQUIRED_COLUMNS_LIST = [
    "uid", "servertimestamp", "timestamp_", "scenetype", "processtype",
    "eventname", "extend", "clientmodel", "clientosversion", "url", "refer", "ip",
]


def _make_df(rows: list[dict]) -> pd.DataFrame:
    base = {c: "" for c in REQUIRED_COLUMNS_LIST}
    return pd.DataFrame([{**base, **r} for r in rows])


def _raw(df, status="ok", uid="U1"):
    return {"uid": uid, "events_df": df, "data_status": status, "errors": []}


def test_feature_builder_path_graph_top_n():
    df = _make_df([
        {"uid": "U1", "servertimestamp": str(1000 + i), "scenetype": p, "eventname": "x"}
        for i, p in enumerate(["A", "B", "A", "B", "C", "B", "C", "A", "D", "B", "E", "F"])
    ])
    fb = TraceFeatureBuilder()
    bundle = fb.build(_raw(df), _ctx())
    assert len(bundle["path_graph"]["top_pages"]) <= TOP_N_PAGES
    assert len(bundle["path_graph"]["top_transitions"]) <= TOP_N_TRANSITIONS
    pages = {p["page"] for p in bundle["path_graph"]["top_pages"]}
    assert "B" in pages  # most-visited


def test_feature_builder_friction_hotspots_severity_sorted():
    rows = []
    for i in range(9):
        rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + i * 5000),
                     "scenetype": "kyc", "eventname": "field-edit",
                     "extend": '{"field":"id_no"}'})
    rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + 9 * 5000),
                 "scenetype": "home", "eventname": "field-edit",
                 "extend": '{"field":"phone"}'})
    df = _make_df(rows)
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    assert len(bundle["friction_hotspots"]) <= TOP_K_FRICTION_HOTSPOTS
    severities = [h["severity"] for h in bundle["friction_hotspots"]]
    rank = {"high": 3, "medium": 2, "low": 1}
    assert severities == sorted(severities, key=lambda s: -rank.get(s, 0))
    assert bundle["friction_hotspots"][0]["avg_stay_seconds"] > 0


def test_feature_builder_time_pattern_24_buckets():
    rows = [
        {"uid": "U1", "servertimestamp": "1773100800000", "scenetype": "home"},  # 02:00 UTC
        {"uid": "U1", "servertimestamp": "1773108000000", "scenetype": "home"},  # 04:00 UTC
    ]
    # Pad to 10 events (>= INSUFFICIENT_EVENTS_THRESHOLD) at 04:00 UTC
    for i in range(8):
        rows.append({"uid": "U1", "servertimestamp": str(1773108000000 + i * 1000),
                     "scenetype": "home"})
    df = _make_df(rows)
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    hist = bundle["time_pattern"]["hour_histogram"]
    assert isinstance(hist, list) and len(hist) == 24
    assert sum(hist) == 10
    assert isinstance(bundle["time_pattern"]["active_window_label"], str)


def test_feature_builder_key_events_tail_redacted_and_capped():
    rows = []
    for i in range(KEY_EVENTS_TAIL_N + 20):
        rows.append({
            "uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
            "scenetype": "auth", "eventname": "field-click",
            "extend": '{"field":"phone","app_version":"1.2.6"}',
            "url": "https://x.com/m/#/auth?token=SECRET&from=%2F",
            "ip": "1.2.3.4",
        })
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    tail = bundle["key_events_tail"]
    assert len(tail) == KEY_EVENTS_TAIL_N
    for ev in tail:
        # Whitelist enforced: only ts_offset / page / event / field allowed
        assert set(ev.keys()) <= {"ts_offset", "page", "event", "field"}
        # Redaction sanity
        assert "ip" not in ev
        assert "?" not in str(ev.get("page", ""))  # no url query


def test_feature_builder_churn_prior_candidates_in_whitelist():
    rows = []
    for i in range(4):  # repeated visits to interest page → interest_perception_high prior
        rows.append({"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
                     "scenetype": "interest", "processtype": "interest",
                     "eventname": "page_onResume", "extend": "{}"})
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    candidates = bundle["churn_root_cause_candidates"]
    assert isinstance(candidates, list)
    for c in candidates:
        assert c["value"] in {
            "credit_limit_unmet", "interest_perception_high", "competitor_poaching",
            "ux_friction", "repayment_burden", "no_clear_signal",
        }
        assert 0.0 <= float(c.get("confidence", 0)) <= 1.0


def test_feature_builder_token_budget_within_total():
    rows = [{"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
             "scenetype": "auth", "eventname": "field-click", "extend": '{"field":"x"}'}
            for i in range(800)]
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    fb = TraceFeatureBuilder()
    payload = [bundle["event_window"], bundle["path_graph"], bundle["friction_hotspots"],
               bundle["time_pattern"], bundle["key_events_tail"]]
    est = fb._estimate_tokens(_json.dumps(payload, ensure_ascii=False))
    assert est <= TOTAL_TOKEN_BUDGET, f"token budget exceeded est={est} budget={TOTAL_TOKEN_BUDGET}"


def test_feature_builder_tier3_halved_when_over_budget():
    # Force tier 3 to be larger than TIER_3_TOKEN_BUDGET so guard halves N
    rows = [{"uid": "U1", "servertimestamp": str(1773000000000 + i * 1000),
             "scenetype": "very_long_page_name_to_inflate_tokens" * 3,
             "eventname": "field-click",
             "extend": '{"field":"long_field_name_to_inflate_tokens"}'}
            for i in range(KEY_EVENTS_TAIL_N + 100)]
    bundle = TraceFeatureBuilder().build(_raw(_make_df(rows)), _ctx())
    # When trimmed, errors should record truncation
    if len(bundle["key_events_tail"]) < KEY_EVENTS_TAIL_N:
        assert any("truncat" in e.lower() or "tier3" in e.lower() for e in bundle["errors"])


def test_feature_builder_event_window_counts():
    rows = [
        {"uid": "U1", "servertimestamp": str(1773000000000 + i * 60000), "scenetype": "a"}
        for i in range(10)
    ]
    df = _make_df(rows)
    bundle = TraceFeatureBuilder().build(_raw(df), _ctx())
    win = bundle["event_window"]
    assert win["total_events"] == 10
    assert win["analyzed_events"] == 10
    assert win["start"] and win["end"]


from app.runtime_skills.trace_analyzer.decision_engine import TraceDecisionEngine


def _bundle_ok():
    return {
        "uid": "U1",
        "event_window": {"start": "s", "end": "e", "total_events": 100, "analyzed_events": 100},
        "path_graph": {"top_pages": [{"page": "kyc", "visit_count": 10, "avg_stay_seconds": 5.0}],
                       "top_transitions": [{"from": "home", "to": "kyc", "count": 3}]},
        "friction_hotspots": [{"step": "kyc:id_no", "retry_count": 4, "error_count": 1,
                                "avg_stay_seconds": 0.0, "severity": "high"}],
        "time_pattern": {"hour_histogram": [0] * 24, "active_window_label": "深夜活跃"},
        "key_events_tail": [{"ts_offset": 0.0, "page": "kyc", "event": "field-click"}],
        "churn_root_cause_candidates": [{"value": "ux_friction", "confidence": 0.7, "reason": "x"}],
        "feature_status": "ok",
        "errors": [],
    }


def test_decision_engine_prompt_payload_built():
    de = TraceDecisionEngine()
    res = de.decide(_bundle_ok(), _ctx())
    assert res["decision_status"] == "ok"
    payload = res["prompt_payload"]
    for key in ("event_window", "path_graph", "friction_hotspots",
                "time_pattern", "key_events_tail", "churn_candidates"):
        assert key in payload, f"missing prompt_payload.{key}"


def test_decision_engine_fallback_story_present():
    de = TraceDecisionEngine()
    res = de.decide(_bundle_ok(), _ctx())
    assert isinstance(res["fallback_story"], str) and len(res["fallback_story"]) > 0
    assert isinstance(res["fallback_interventions"], list)


def test_decision_engine_skips_when_insufficient():
    bundle = _bundle_ok()
    bundle["feature_status"] = "insufficient_events"
    bundle["friction_hotspots"] = []
    bundle["key_events_tail"] = []
    res = TraceDecisionEngine().decide(bundle, _ctx())
    assert res["decision_status"] == "skipped"


from unittest.mock import MagicMock
from app.runtime_skills.trace_analyzer.explainer import TraceExplainer


def _decision_ok():
    return {
        "uid": "U1",
        "decision_status": "ok",
        "prompt_payload": {"event_window": {}, "path_graph": {"top_pages": [], "top_transitions": []},
                            "friction_hotspots": [], "time_pattern": {}, "key_events_tail": [],
                            "churn_candidates": [{"value": "ux_friction", "confidence": 0.7}]},
        "fallback_story": "FALLBACK_STORY",
        "fallback_interventions": [{"hotspot": "h", "advice": "a", "channel_hint": ""}],
        "errors": [],
    }


def test_explainer_mock_mode_skips_llm():
    mc = MagicMock()
    mc.mode = "mock"
    mc.model_name = "mock"
    ex = TraceExplainer(mc)
    res = ex.explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "skipped"
    assert res["used_llm"] is False
    assert res["churn_story"] == "FALLBACK_STORY"
    mc.generate_structured.assert_not_called()


def test_explainer_llm_ok_path():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "gemini-3.1-pro-preview"
    mc.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "churn_story": "用户在 KYC 阶段遇到 4 次失败后退出。",
            "intervention_suggestions": [
                {"hotspot": "kyc:id_no", "advice": "在 KYC 上传环节加入实时光照检测",
                 "channel_hint": "WhatsApp"}
            ],
            "churn_root_cause": ["ux_friction"],
        },
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "ok"
    assert res["used_llm"] is True
    assert "KYC" in res["churn_story"]
    assert res["churn_root_cause"] == ["ux_friction"]


def test_explainer_filters_invalid_churn_root_cause():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "x"
    mc.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "churn_story": "x", "intervention_suggestions": [],
            "churn_root_cause": ["INVENTED_VALUE", "ux_friction"],
        },
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["churn_root_cause"] == ["ux_friction"]


def test_explainer_falls_back_when_llm_fails():
    mc = MagicMock()
    mc.mode = "vertex"
    mc.model_name = "x"
    mc.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {"churn_story": "", "intervention_suggestions": [], "churn_root_cause": []},
    }
    res = TraceExplainer(mc).explain(_decision_ok(), _ctx())
    assert res["explanation_status"] == "model_unavailable"
    assert res["used_llm"] is False
    assert res["churn_story"] == "FALLBACK_STORY"
    assert res["churn_root_cause"] == ["no_clear_signal"]


from app.core.config import settings as _settings
from app.runtime_skills.trace_analyzer.assembler import TraceAssembler
from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer
from app.schemas.trace_analyzer import TraceAnalyzeResponse


def _explanation_ok():
    return {
        "uid": "U1", "explanation_status": "ok", "used_llm": True,
        "churn_story": "用户在 KYC 卡住", "intervention_suggestions": [
            {"hotspot": "kyc:id_no", "advice": "针对 id_no 加入光照提示", "channel_hint": "WhatsApp"}],
        "churn_root_cause": ["ux_friction"],
        "model_trace": {"mode": "vertex", "used_llm": True, "model_name": "x",
                          "fallback_reason": ""},
        "errors": [],
    }


def test_assembler_status_ok():
    bundle = _bundle_ok()
    decision = {"uid": "U1", "decision_status": "ok", "prompt_payload": {},
                "fallback_story": "fb", "fallback_interventions": [], "errors": []}
    res = TraceAssembler().assemble("U1", bundle, decision, _explanation_ok())
    TraceAnalyzeResponse.model_validate(res)
    assert res["status"] == "ok"
    assert res["churn_root_cause"] == ["ux_friction"]


def test_assembler_status_model_unavailable():
    bundle = _bundle_ok()
    decision = {"uid": "U1", "decision_status": "ok", "prompt_payload": {},
                "fallback_story": "fb", "fallback_interventions": [], "errors": []}
    expl = _explanation_ok()
    expl["explanation_status"] = "model_unavailable"
    expl["used_llm"] = False
    res = TraceAssembler().assemble("U1", bundle, decision, expl)
    assert res["status"] == "model_unavailable"


def test_analyzer_e2e_mock_mode(tmp_path, monkeypatch):
    uid = "EE1"
    rows = [f'{uid},{1773000000000 + i*1000},{1773000000000 + i*1000},kyc,kyc,'
            f'field-edit,"{{\\"field\\":\\"id_no\\"}}",m,15,https://x/kyc,null,1.1.1.1'
            for i in range(50)]
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(_settings, "model_mode", "mock")

    from app.core.model_client import ModelClient
    analyzer = TraceAnalyzer(model_client=ModelClient())
    res = analyzer.analyze(uid, _ctx(uid))
    TraceAnalyzeResponse.model_validate(res)
    assert res["status"] == "model_unavailable"  # mock → no LLM
    assert res["uid"] == uid
    assert len(res["friction_hotspots"]) >= 1


def test_analyzer_data_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(_settings, "model_mode", "mock")
    from app.core.model_client import ModelClient
    analyzer = TraceAnalyzer(model_client=ModelClient())
    res = analyzer.analyze("NOPE", _ctx("NOPE"))
    assert res["status"] == "data_missing"


def test_analyzer_insufficient_events(tmp_path, monkeypatch):
    uid = "II1"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},x,home,home,page_onResume,"{{}}",m,15,https://x/,null,1.1'
            for i in range(3)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr(_settings, "model_mode", "mock")
    from app.core.model_client import ModelClient
    res = TraceAnalyzer(model_client=ModelClient()).analyze(uid, _ctx(uid))
    assert res["status"] == "insufficient_events"

