from __future__ import annotations

import asyncio
import csv
import importlib
import json
import sys
from datetime import datetime, timezone

import pytest


# Data Agent capability test convention:
# - fake query_data / repair success paths must patch capability as enabled
# - unavailable behavior tests must set DATA_ACQUISITION_ENABLED=false or patch disabled capability
# - fake Data Agent tests must not depend on local DA dependencies being installed
# - direct query_data execute tests must also fake manifest loading
def _patch_enabled_data_acquisition(monkeypatch):
    from app.core.data_acquisition_capability import DataAcquisitionCapability

    cap = DataAcquisitionCapability(mode="auto", enabled=True, reason=None)
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.agent_loop"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.repair_profile_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.tools.query_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    return cap


def _patch_disabled_data_acquisition(monkeypatch):
    from app.core.data_acquisition_capability import DataAcquisitionCapability

    cap = DataAcquisitionCapability(
        mode="disabled",
        enabled=False,
        reason="disabled_by_config",
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.agent_loop"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.repair_profile_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.tools.query_data"),
        "get_data_acquisition_capability",
        lambda: cap,
    )
    return cap


def _patch_fake_query_data_manifest(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.tools.query_data"),
        "_load_manifest",
        lambda country: SimpleNamespace(
            analyst_private_prefix="analyst_private",
        ),
    )


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _collect_payload_keys(value):
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_collect_payload_keys(child))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_payload_keys(item))
    return keys


def _assert_no_internal_trace_keys_in_events(events):
    forbidden = {
        "internal_metadata",
        "flow_name",
        "flow_mode",
        "decision_mode",
        "fallback_reason",
        "terminal_reason",
    }
    seen_keys: set[str] = set()
    for event in events:
        seen_keys.update(_collect_payload_keys(event))
    leaked = forbidden & seen_keys
    assert not leaked, f"internal trace keys leaked into public events: {sorted(leaked)}"


def test_check_data_availability_reads_real_bucket_files(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(app_dir / f"{uid}.csv", [{
        "uid": uid,
        "app_name": "WhatsApp",
        "app_package": "com.whatsapp",
        "first_install_time": "2026-05-01T00:00:00Z",
        "last_update_time": "2026-05-15T00:00:00Z",
        "gp_category": "Social",
        "ai_category_level_2_CN": "社交",
    }])
    _write_csv(behavior_dir / f"{uid}.csv", [{
        "uid": uid,
        "event_name": "login",
        "event_time": "2026-05-15T00:00:00Z",
    }])

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")

    assert availability.checked_uids == [uid]
    assert availability.per_uid[0].app.status == "available"
    assert availability.per_uid[0].behavior.status == "available"
    assert availability.per_uid[0].credit.status == "missing"
    assert availability.per_uid[0].missing_buckets == ["credit"]


def test_check_data_availability_ignores_sample_fallback(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"
    app_dir.mkdir(parents=True, exist_ok=True)
    behavior_dir.mkdir(parents=True, exist_ok=True)
    credit_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")

    assert availability.per_uid[0].app.status == "missing"
    assert availability.per_uid[0].behavior.status == "missing"
    assert availability.per_uid[0].credit.status == "missing"


def test_check_data_availability_marks_invalid_csv(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(app_dir / f"{uid}.csv", [{
        "uid": uid,
        "app_name": "WhatsApp",
    }])
    behavior_dir.mkdir(parents=True, exist_ok=True)
    credit_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")

    assert availability.per_uid[0].app.status == "invalid"
    assert availability.per_uid[0].app.detail.startswith("missing_fields:")


def test_check_data_availability_uses_csv_when_prepared_json_schema_mismatches(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    behavior_dir.mkdir(parents=True, exist_ok=True)
    (behavior_dir / f"{uid}.json").write_text(
        '{"schema_version":"wrong","uid":"824812551379353600"}',
        encoding="utf-8",
    )
    _write_csv(behavior_dir / f"{uid}.csv", [{
        "uid": uid,
        "event_name": "login",
        "event_time": "2026-05-15T00:00:00Z",
    }])
    app_dir.mkdir(parents=True, exist_ok=True)
    credit_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")

    assert availability.per_uid[0].behavior.status == "available"
    assert availability.per_uid[0].behavior.source_type == "csv"


def test_check_data_availability_rejects_weak_behavior_and_credit_csv(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(behavior_dir / f"{uid}.csv", [{"uid": uid}])
    _write_csv(credit_dir / f"{uid}.csv", [{"uid": uid}])
    app_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.behavior.status == "invalid"
    assert row.behavior.usable_for_profile is False
    assert row.credit.status == "invalid"
    assert row.credit.usable_for_profile is False


def test_check_data_availability_accepts_raw_mx_behavior_csv_aliases(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(behavior_dir / f"{uid}.csv", [{
        "uid": uid,
        "servertimestamp": "1773121104896",
        "timestamp_": "1773121104652",
        "scenetype": "WebViewActivity",
        "processtype": "Native",
        "eventname": "page_onPause",
        "url": "https://www.mexicash.com/m/#/return-refresh-path",
    }])
    app_dir.mkdir(parents=True, exist_ok=True)
    credit_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.behavior.status == "available"
    assert row.behavior.usable_for_profile is True


def test_check_data_availability_accepts_camelcase_behavior_and_credit_fields(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(behavior_dir / f"{uid}.csv", [{
        "uid": uid,
        "eventTime": "2026-05-15T00:00:00Z",
        "eventName": "login",
    }])
    _write_csv(credit_dir / f"{uid}.csv", [{
        "uid": uid,
        "creditScore": "720",
        "riskLevel": "low",
    }])
    app_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.behavior.usable_for_profile is True
    assert row.credit.usable_for_profile is True


def test_check_data_availability_accepts_real_credit_raw_csv_aliases(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824928257039138816"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(credit_dir / f"{uid}.csv", [{
        "user_uuid": uid,
        "timestamp_": "1772369656095",
        "code": "0",
        "folioconsulta": "1951672304",
        "nombrescore": "FICO",
        "valor": "720",
        "razones": "R1|R2",
        "consultas_detail_json": '[{"fechaConsulta":"2024-01-01"}]',
        "creditos_detail_json": '[{"tipoCredito":"TC","saldoActual":"1000"}]',
    }])
    app_dir.mkdir(parents=True, exist_ok=True)
    behavior_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.credit.status == "available"
    assert row.credit.usable_for_profile is True


def test_check_data_availability_marks_credit_csv_mixed_when_strong_raw_and_summary_coexist(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824928257039138816"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(credit_dir / f"{uid}.csv", [{
        "uid": uid,
        "valor": "720",
        "nombrescore": "FICO",
        "creditos_detail_json": "[]",
        "risk_level": "low",
    }])
    app_dir.mkdir(parents=True, exist_ok=True)
    behavior_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.credit.status == "available"
    assert row.credit.source_shape == "mixed"


def test_check_data_availability_rejects_credit_csv_with_only_weak_meta_fields(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824928257039138816"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    _write_csv(credit_dir / f"{uid}.csv", [{
        "user_uuid": uid,
        "timestamp_": "1772369656095",
        "code": "0",
        "apply_risk_id": "AR-1",
    }])
    app_dir.mkdir(parents=True, exist_ok=True)
    behavior_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.credit.status == "invalid"
    assert row.credit.usable_for_profile is False
    assert row.credit.source_shape is None


def test_check_data_availability_rejects_empty_prepared_payloads(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.scripts.behavior_prepared_builder import BEHAVIOR_PREPARED_SCHEMA_VERSION
    from app.scripts.credit_prepared_builder import CREDIT_PREPARED_SCHEMA_VERSION
    from app.services.orchestrator_agent.data_availability import check_data_availability

    uid = "824812551379353600"
    app_dir = tmp_path / "app" / "by_uid"
    behavior_dir = tmp_path / "behavior" / "by_uid"
    credit_dir = tmp_path / "credit" / "by_uid"

    behavior_dir.mkdir(parents=True, exist_ok=True)
    credit_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)
    (behavior_dir / f"{uid}.json").write_text(json.dumps({
        "uid": uid,
        "schema_version": BEHAVIOR_PREPARED_SCHEMA_VERSION,
        "source_meta": {"event_count": 0, "timeline_section_count": 0},
        "session_summary": {"total_events": 0},
        "timeline_sections": [],
    }), encoding="utf-8")
    (credit_dir / f"{uid}.json").write_text(json.dumps({
        "uid": uid,
        "schema_version": CREDIT_PREPARED_SCHEMA_VERSION,
        "source_meta": {"row_count": 0},
        "credit_summary": {"total_accounts": 0},
        "delinquency_summary": {"total_delinquent_accounts": 0},
        "repayment_timeline": [0] * 12,
        "repayment_amount_timeline": [0] * 12,
    }), encoding="utf-8")

    monkeypatch.setattr(settings, "app_by_uid_dir", str(app_dir), raising=False)
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    availability = check_data_availability([uid], country="mx")
    row = availability.per_uid[0]

    assert row.behavior.usable_for_profile is False
    assert row.credit.usable_for_profile is False


def test_normalize_request_covers_known_intents():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    read_only = normalize_request("帮我总结一下这个用户的综合画像", session)
    single_uid = normalize_request("帮我分析一下 824812551379353600 这个用户", session)
    batch = normalize_request("帮我对比 824812551379353600 和 824812551379353601", session)
    trace = normalize_request("帮我看下 UID: TH000123 的轨迹", session)
    cohort = normalize_request("帮我找最近 7 天高流失用户并分析", session)

    assert read_only.intent == "answer_from_workspace"
    assert single_uid.intent == "profile_uid"
    assert single_uid.uids == ["824812551379353600"]
    assert batch.intent == "profile_batch"
    assert batch.uids == ["824812551379353600", "824812551379353601"]
    assert trace.intent == "run_trace"
    assert trace.uids == ["TH000123"]
    assert cohort.intent == "query_data_then_profile"
    assert cohort.query_request == "帮我找最近 7 天高流失用户并分析"


def test_normalize_request_accepts_uid_touching_chinese_text():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("请帮我分析824812551379353600这个用户", session)

    assert request.intent == "profile_uid"
    assert request.uids == ["824812551379353600"]


def test_normalize_request_extracts_trace_days():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("帮我分析 UID 824812551379353600 最近 30 天轨迹", session)

    assert request.intent == "run_trace"
    assert request.trace_days == 30


def test_normalize_request_routes_uid_file_batch_to_profile_execution():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。", session)

    assert request.intent == "profile_batch"
    assert request.uid_file_path == "./data/id_files/mx/sample.txt"
    assert request.read_only is False


def test_normalize_request_detects_cohort_request_from_pull_batch_phrase():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("帮我拉一批墨西哥上周流失且下单过的用户，然后逐个跑 App 画像。", session)

    assert request.intent == "query_data_then_profile"


def test_normalize_request_routes_explicit_data_agent_sql_request_to_create_run():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("用 Data Agent 生成 SQL，查询最近 7 天高风险用户", session)

    assert request.intent == "create_data_agent_run"
    assert request.query_request == "用 Data Agent 生成 SQL，查询最近 7 天高风险用户"


def test_normalize_request_routes_explicit_writeback_with_bucket_to_create_run():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("用 Data Agent 补齐这些用户的 behavior 数据并写回", session)

    assert request.intent == "create_data_agent_run"
    assert request.query_request == "用 Data Agent 补齐这些用户的 behavior 数据并写回"


def test_normalize_request_routes_ambiguous_data_request_to_clarify_data_request():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("帮我查一下数据", session)

    assert request.intent == "clarify_data_request"
    assert request.request_understanding is not None


def test_normalize_request_prefers_explicit_data_agent_request_over_profile_keywords():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("用 Data Agent 生成 SQL，查询这个用户的画像数据", session)

    assert request.intent == "create_data_agent_run"


def test_normalize_request_routes_ambiguous_cohort_to_need_clarification():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("找一批高流失用户", session)

    assert request.intent == "need_clarification"
    assert request.request_understanding is not None
    assert set(request.request_understanding.missing_slots) == {"country", "time_window"}
    assert "时间范围" in (request.request_understanding.clarification_prompt or "")


def test_normalize_request_keeps_general_chat_for_plain_summary_prompt():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("总结一下我们刚才讨论的方案", session)

    assert request.intent == "general_chat"


def test_risk_knowledge_normalize_request_routes_explicit_risk_concept_question():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    request = normalize_request("什么是多头借贷风险？", session)

    assert request.intent == "risk_knowledge_answer"
    assert request.request_understanding is not None


def test_risk_knowledge_normalize_request_does_not_steal_data_or_workspace_queries():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {
        "country": "mx",
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像：近30天登录偏低，流失风险高。",
                "structured_result": {"risk_level": "high"},
            }
        ],
    }

    data_request = normalize_request("统计逾期用户数量", session)
    workspace_request = normalize_request("帮我解释为什么这个用户流失风险高", session)

    assert data_request.intent != "risk_knowledge_answer"
    assert workspace_request.intent == "answer_from_workspace"


def test_normalize_request_enriches_request_understanding_for_followup_and_rerun():
    from app.services.orchestrator_agent.request_router import normalize_request
    from app.services.orchestrator_agent.session_store import create_session

    session = create_session(country="mx")

    followup = normalize_request("帮我解释为什么这个用户流失风险高，并改成客服话术", session)
    rerun = normalize_request("重新分析 UID 824812551379353600 的最新综合画像", session)

    assert followup.intent == "answer_from_workspace"
    assert followup.request_understanding.route_label == "已有画像追问"
    assert followup.request_understanding.rewritten_goal == "基于当前已有画像结果，解释高流失风险并改写为客服话术"
    assert followup.request_understanding.requires_tools is False
    assert followup.request_understanding.answer_mode == "workspace_evidence_answer"
    assert "why" in followup.request_understanding.focus
    assert "customer_script" in followup.request_understanding.focus

    assert rerun.intent == "profile_uid"
    assert rerun.request_understanding.answer_mode == "tool_execution"
    assert "rerun" in rerun.request_understanding.focus


def test_repair_profile_data_module_is_importable_without_executor_dependencies():
    import importlib

    mod = importlib.import_module("app.services.orchestrator_agent.repair_profile_data")

    assert hasattr(mod, "repair_profile_data")


def test_tools_registry_import_does_not_pull_data_agent_executor():
    sys.modules.pop("app.services.orchestrator_agent.tools", None)
    sys.modules.pop("app.services.orchestrator_agent.tools.query_data", None)
    sys.modules.pop("data_acquisition_agent.executor", None)

    mod = importlib.import_module("app.services.orchestrator_agent.tools")

    assert hasattr(mod, "get_tool_registry")
    assert "data_acquisition_agent.executor" not in sys.modules


def test_query_data_module_import_does_not_pull_data_agent_executor():
    sys.modules.pop("app.services.orchestrator_agent.tools.query_data", None)
    sys.modules.pop("data_acquisition_agent.executor", None)

    mod = importlib.import_module("app.services.orchestrator_agent.tools.query_data")

    assert hasattr(mod, "query_data")
    assert "data_acquisition_agent.executor" not in sys.modules


def test_repair_profile_data_writes_csv_and_returns_metadata(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.repair_profile_data import (
        RepairProfileDataInput,
        repair_profile_data,
    )

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    credit_dir = tmp_path / "credit" / "by_uid"
    credit_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "credit_by_uid_dir", str(credit_dir), raising=False)

    class _FakeChildAgent:
        def __init__(self, country: str, bucket: str) -> None:
            self.country = country
            self.bucket = bucket

        def run_query(self, request_text: str):
            return type("X", (), {
                "sql_text": "SELECT uid, score FROM bureau WHERE uid IN (...)",
                "rows_estimated": 1,
            })()

        def execute(self, sql_text: str):
            return {
                "uids": [uid],
                "rows_actual": 1,
                "filenames": [f"{uid}.csv"],
                "written_file_count": 1,
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.repair_profile_data._RepairChildAgent",
        _FakeChildAgent,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.repair_profile_data._await_user_ack",
        lambda session_id, tool_call_id, sql_text, rows_estimated: True,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.repair_profile_data._write_repair_csv",
        lambda bucket, rows, target_uids: [f"{uid}.csv"],
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.data_availability.check_data_availability",
        lambda uids, country=None: type("X", (), {
            "per_uid": [
                type("Row", (), {
                    "uid": uid,
                    "credit": type("Bucket", (), {"usable_for_profile": True})(),
                })()
            ],
        })(),
        raising=False,
    )

    output = repair_profile_data(
        RepairProfileDataInput(
            uids=[uid],
            country="mx",
            bucket="credit",
            reason="missing credit bucket",
        ),
        session_id="sess-1",
        tool_call_id="repair-1",
    )

    assert output.bucket == "credit"
    assert output.written_uids == [uid]
    assert output.filenames == [f"{uid}.csv"]
    assert output.rows_actual == 1


def test_repair_profile_data_reject_marks_session_cancelled(monkeypatch):
    from app.services.orchestrator_agent.ack_bus import open_ack, wait_ack
    from app.services.orchestrator_agent.repair_profile_data import (
        RepairProfileDataInput,
        repair_profile_data,
    )
    from app.services.orchestrator_agent.session import is_query_cancelled, reset_query_cancelled

    _patch_enabled_data_acquisition(monkeypatch)

    session_id = "repair-reject-sess"
    reset_query_cancelled(session_id)

    class _FakeChildAgent:
        def __init__(self, country: str, bucket: str) -> None:
            self.country = country
            self.bucket = bucket

        def run_query(self, request_text: str):
            return type("X", (), {
                "sql_text": "SELECT uid FROM t",
                "rows_estimated": 1,
            })()

        def execute(self, sql_text: str):
            raise AssertionError("execute should not run after reject")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.repair_profile_data._RepairChildAgent",
        _FakeChildAgent,
    )

    def _fake_open_ack(sid: str):
        return open_ack(sid)

    def _fake_wait_ack(sid: str, timeout_sec: float = 600.0):
        return False

    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.open_ack",
        _fake_open_ack,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        _fake_wait_ack,
    )

    with pytest.raises(PermissionError):
        repair_profile_data(
            RepairProfileDataInput(
                uids=["824812551379353600"],
                country="mx",
                bucket="credit",
                reason="missing credit bucket",
            ),
            session_id=session_id,
            tool_call_id="repair-reject",
        )

    assert is_query_cancelled(session_id) is True


def test_repair_profile_data_opens_ack_before_before_ack_callback(monkeypatch):
    from app.services.orchestrator_agent.repair_profile_data import (
        RepairProfileDataInput,
        repair_profile_data,
    )

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    call_order = []

    class _FakeChildAgent:
        def __init__(self, country: str, bucket: str) -> None:
            self.country = country
            self.bucket = bucket

        def run_query(self, request_text: str):
            return type("X", (), {
                "sql_text": "SELECT uid FROM bureau",
                "rows_estimated": 1,
            })()

        def execute(self, sql_text: str):
            return {
                "uids": [uid],
                "rows_actual": 1,
                "filenames": [f"{uid}.csv"],
                "written_file_count": 1,
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.repair_profile_data._RepairChildAgent",
        _FakeChildAgent,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.open_ack",
        lambda sid: call_order.append("open_ack"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.data_availability.check_data_availability",
        lambda uids, country=None: type("X", (), {
            "per_uid": [
                type("Row", (), {
                    "uid": uid,
                    "credit": type("Bucket", (), {"usable_for_profile": True})(),
                })()
            ],
        })(),
        raising=False,
    )

    output = repair_profile_data(
        RepairProfileDataInput(
            uids=[uid],
            country="mx",
            bucket="credit",
            reason="missing credit bucket",
        ),
        session_id="repair-order-sess",
        tool_call_id="repair-order-call",
        before_ack=lambda sql, rows: call_order.append("before_ack"),
    )

    assert output.written_uids == [uid]
    assert call_order[:3] == ["open_ack", "before_ack", "wait_ack"]


def test_repair_profile_data_respects_pre_cancelled_session():
    from app.services.orchestrator_agent.repair_profile_data import (
        RepairProfileDataInput,
        repair_profile_data,
    )
    from app.services.orchestrator_agent.session import mark_query_cancelled, reset_query_cancelled

    session_id = "repair-pre-cancel"
    reset_query_cancelled(session_id)
    mark_query_cancelled(session_id)

    with pytest.raises(PermissionError, match="user cancelled"):
        repair_profile_data(
            RepairProfileDataInput(
                uids=["824812551379353600"],
                country="mx",
                bucket="credit",
                reason="missing credit bucket",
            ),
            session_id=session_id,
            tool_call_id="repair-cancelled",
        )


def test_query_data_execute_returns_uids_without_bucket_writes(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    _patch_enabled_data_acquisition(monkeypatch)
    _patch_fake_query_data_manifest(monkeypatch)

    behavior_dir = tmp_path / "behavior" / "by_uid"
    monkeypatch.setattr(settings, "behavior_by_uid_dir", str(behavior_dir), raising=False)

    class _FakeOrchestrator:
        def generate(self, req):
            return type("Resp", (), {"sql": "SELECT uid FROM t", "reasoning_summary": "ok"})()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.enforce_pre_execution_gates",
        lambda **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.open_starrocks_connection",
        lambda request_id: _FakeConn(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.precheck_row_count",
        lambda **kwargs: 2,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.execute_query",
        lambda **kwargs: __import__("pandas").DataFrame([{"uid": "u2"}, {"uid": "u1"}, {"uid": "u1"}]),
        raising=False,
    )

    child = _ChildAgent("mx")
    out = child.execute("SELECT uid FROM t")

    assert out["uids"] == ["u1", "u2"]
    assert out["rows_actual"] == 3
    assert not behavior_dir.exists() or not any(behavior_dir.iterdir())


def test_query_data_execute_accepts_user_uuid_alias(monkeypatch):
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    _patch_enabled_data_acquisition(monkeypatch)
    _patch_fake_query_data_manifest(monkeypatch)

    class _FakeOrchestrator:
        def generate(self, req):
            return type("Resp", (), {"sql": "SELECT user_uuid FROM t", "reasoning_summary": "ok"})()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.enforce_pre_execution_gates",
        lambda **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.open_starrocks_connection",
        lambda request_id: _FakeConn(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.precheck_row_count",
        lambda **kwargs: 2,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.execute_query",
        lambda **kwargs: __import__("pandas").DataFrame([{"user_uuid": "u2"}, {"user_uuid": "u1"}]),
        raising=False,
    )

    child = _ChildAgent("mx")
    out = child.execute("SELECT user_uuid FROM t")

    assert out["uids"] == ["u1", "u2"]


def test_query_data_execute_accepts_customer_id_alias_and_normalizes_numeric_uids(monkeypatch):
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    _patch_enabled_data_acquisition(monkeypatch)
    _patch_fake_query_data_manifest(monkeypatch)

    class _FakeOrchestrator:
        def generate(self, req):
            return type("Resp", (), {"sql": "SELECT customer_id FROM t", "reasoning_summary": "ok"})()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.enforce_pre_execution_gates",
        lambda **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.open_starrocks_connection",
        lambda request_id: _FakeConn(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.precheck_row_count",
        lambda **kwargs: 3,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.execute_query",
        lambda **kwargs: __import__("pandas").DataFrame([{"customer_id": 456}, {"customer_id": 123}, {"customer_id": 123}]),
        raising=False,
    )

    child = _ChildAgent("mx")
    out = child.execute("SELECT customer_id FROM t")

    assert out["uids"] == ["123", "456"]
    assert out["rows_actual"] == 3


def test_query_data_execute_filters_blank_and_none_uids(monkeypatch):
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    _patch_enabled_data_acquisition(monkeypatch)
    _patch_fake_query_data_manifest(monkeypatch)

    class _FakeOrchestrator:
        def generate(self, req):
            return type("Resp", (), {"sql": "SELECT uid FROM t", "reasoning_summary": "ok"})()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.enforce_pre_execution_gates",
        lambda **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.open_starrocks_connection",
        lambda request_id: _FakeConn(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.precheck_row_count",
        lambda **kwargs: 4,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.execute_query",
        lambda **kwargs: __import__("pandas").DataFrame(
            [{"uid": "u2"}, {"uid": ""}, {"uid": None}, {"uid": "u1"}]
        ),
        raising=False,
    )

    child = _ChildAgent("mx")
    out = child.execute("SELECT uid FROM t")

    assert out["uids"] == ["u1", "u2"]
    assert out["rows_actual"] == 4


def test_query_data_execute_missing_uid_column_raises_value_error(monkeypatch):
    from app.services.orchestrator_agent.tools.query_data import _ChildAgent

    _patch_enabled_data_acquisition(monkeypatch)
    _patch_fake_query_data_manifest(monkeypatch)

    class _FakeOrchestrator:
        def generate(self, req):
            return type("Resp", (), {"sql": "SELECT account_id FROM t", "reasoning_summary": "ok"})()

    class _FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.enforce_pre_execution_gates",
        lambda **kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.open_starrocks_connection",
        lambda request_id: _FakeConn(),
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.precheck_row_count",
        lambda **kwargs: 2,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data.execute_query",
        lambda **kwargs: __import__("pandas").DataFrame([{"account_id": "u1"}, {"account_id": "u2"}]),
        raising=False,
    )

    child = _ChildAgent("mx")

    with pytest.raises(ValueError, match="query_data result missing uid column"):
        child.execute("SELECT account_id FROM t")


def test_repair_profile_data_exposes_prepare_and_execute_stages():
    mod = importlib.import_module("app.services.orchestrator_agent.repair_profile_data")

    assert hasattr(mod, "prepare_repair_query")
    assert hasattr(mod, "execute_repair_query")


def test_build_repair_request_uses_raw_credit_contract():
    from app.services.orchestrator_agent.repair_profile_data import build_repair_request
    from app.services.orchestrator_agent.schemas import RepairProfileDataInput

    prompt = build_repair_request(RepairProfileDataInput(
        uids=["u1"],
        country="mx",
        bucket="credit",
        reason="credit missing",
    ))

    assert "nombrescore" in prompt
    assert "consultas_detail_json" in prompt
    assert "creditos_detail_json" in prompt
    assert "credit_score_band" not in prompt
    assert "repayment_status" not in prompt
    assert "risk_level" not in prompt


def test_query_data_single_shot_prefers_execute_rows_estimated(monkeypatch):
    from app.services.orchestrator_agent.schemas import QueryDataInput
    from app.services.orchestrator_agent.tools.query_data import query_data

    class _FakeChild:
        def __init__(self, country):
            self.country = country

        def run_query(self, request_text):
            return type("QR", (), {"sql_text": "SELECT user_uuid FROM t", "rows_estimated": -1})()

        def execute(self, sql_text):
            return {"uids": ["u1"], "rows_actual": 1, "rows_estimated": 37}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data._ChildAgent",
        _FakeChild,
    )

    out = query_data(QueryDataInput(request="拉一批用户", country="mx"))
    assert out.rows_estimated == 37


def test_run_agent_loop_known_profile_request_emits_execution_events(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        ExecutionPlan,
        NormalizedRequest,
        ReviewResult,
        ToolCallRecord,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run for known request"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    )

    def _fake_run_profile(inp, progress_callback=None):
        for idx, mod in enumerate(inp.modules, start=1):
            if progress_callback:
                progress_callback({
                    "progress_type": "profile_module_completed",
                    "uid": uid,
                    "module": mod,
                    "result": {
                        "status": "ok",
                        "data": {"summary": f"{mod} done", "structured_result": {}, "charts": [], "report_markdown": ""},
                        "error": None,
                    },
                    "status": "ok",
                    "completed": idx,
                    "total": len(inp.modules),
                })
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": mod,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{mod} done", "structured_result": {}, "charts": [], "report_markdown": ""},
                            "error": None,
                        },
                    }
                    for mod in inp.modules
                ],
                "cache_hits": 0,
                "cache_misses": len(inp.modules),
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析一下{uid}这个用户")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]

    assert "execution_plan" in types
    assert "plan_step_status" in types
    assert "tool_started" in types
    assert "tool_progress" in types
    assert "review_result" in types
    assert "final" in types
    assert types.index("execution_plan") < types.index("tool_started") < types.index("review_result") < types.index("final")


def test_run_agent_loop_marks_review_step_done(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 6},
        })(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    asyncio.run(_drive())
    trace = session.execution_traces[-1]
    review_step = next(step for step in trace.steps if step.step_id == "review_final")
    assert review_step.status == "done"


def test_run_agent_loop_parses_uid_file_before_batch_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uids = ["MX0001", "MX0002"]

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda incoming_uids, country=None: DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path=f"/tmp/{uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path=f"/tmp/{uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path=f"/tmp/{uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
                for uid in incoming_uids
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules),
            },
        })(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    tool_starts = [evt["tool_name"] for evt in events if evt["type"] == "tool_started"]
    tool_completed = [evt["tool_name"] for evt in events if evt["type"] == "tool_completed"]

    assert tool_starts[:2] == ["parse_uid_file", "run_profile"]
    assert tool_starts.count("parse_uid_file") == 1
    assert tool_completed.count("parse_uid_file") == 1


def test_run_agent_loop_uid_file_repair_emits_updated_execution_plan_after_parse(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uids = ["MX0001", "MX0002", "MX0003"]
    repaired_uid = "MX0002"
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_data_acquisition_capability",
        lambda: type("Cap", (), {"mode": "required", "enabled": True, "reason": None})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )

    def _availability(incoming_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            rows = [
                (uids[0], True, True, True),
                (uids[1], True, True, False),
                (uids[2], True, True, True),
            ]
        else:
            rows = [(uid, True, True, True) for uid in incoming_uids]
        return DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=app, usable_for_profile=app, source_type="csv", path=f"/tmp/{uid}_app.csv" if app else None),
                    behavior=BucketAvailability(status="available", available=behavior, usable_for_profile=behavior, source_type="csv", path=f"/tmp/{uid}_behavior.csv" if behavior else None),
                    credit=BucketAvailability(status="available" if credit else "missing", available=credit, usable_for_profile=credit, source_type="csv" if credit else "missing", path=f"/tmp/{uid}_credit.csv" if credit else None),
                    available_buckets=[name for name, flag in (("app", app), ("behavior", behavior), ("credit", credit)) if flag],
                    missing_buckets=[name for name, flag in (("app", app), ("behavior", behavior), ("credit", credit)) if not flag],
                )
                for uid, app, behavior, credit in rows
            ],
        )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        _availability,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": 1,
                "raw_prepared": {"prepared": input_data.bucket},
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [repaired_uid],
                    "written_uids": [repaired_uid],
                    "filenames": [f"{repaired_uid}_{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules),
            },
        })(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    parse_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done"
    )
    repair_running_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "running"
    )
    repair_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "done"
    )
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    review_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "review_result")
    final_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "final")
    second_plan_index = next(idx for idx, evt in enumerate(events) if evt is plan_events[1])
    second_plan_step_ids = [step["step_id"] for step in plan_events[1]["steps"]]
    run_profile_started = next(
        evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )

    assert len(plan_events) == 2
    assert [step["step_id"] for step in plan_events[0]["steps"]] == ["parse_uid_file"]
    assert "parse_uid_file" not in second_plan_step_ids
    assert {"check_data", "repair_credit", "run_profile", "review_final"}.issubset(set(second_plan_step_ids))
    assert second_plan_index > parse_done_index
    assert parse_done_index < repair_running_index
    assert repair_done_index < run_profile_started_index
    assert review_index < final_index
    assert run_profile_started["input"]["strict_data_mode"] is True
    assert run_profile_started["input"]["uids"] == uids
    assert availability_calls["count"] >= 2


def test_run_agent_loop_uid_file_repair_non_approved_never_starts_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uids = ["MX0001", "MX0002", "MX0003"]

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_data_acquisition_capability",
        lambda: type("Cap", (), {"mode": "required", "enabled": True, "reason": None})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda incoming_uids, country=None: DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_behavior.csv"),
                    credit=BucketAvailability(status="available" if uid != "MX0002" else "missing", available=uid != "MX0002", source_type="csv" if uid != "MX0002" else "missing", path=f"/tmp/{uid}_credit.csv" if uid != "MX0002" else None),
                    available_buckets=["app", "behavior"] + (["credit"] if uid != "MX0002" else []),
                    missing_buckets=[] if uid != "MX0002" else ["credit"],
                )
                for uid in incoming_uids
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for uid_file non-approved repair")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for uid_file non-approved repair")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: False)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    parse_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done"
    )
    repair_running_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "running"
    )
    run_record = session.turns[-1].runs[-1]

    assert parse_done_index < repair_running_index
    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"


def test_run_agent_loop_uid_file_repair_tool_failure_stops_before_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uids = ["MX0001", "MX0002", "MX0003"]

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_data_acquisition_capability",
        lambda: type("Cap", (), {"mode": "required", "enabled": True, "reason": None})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda incoming_uids, country=None: DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_behavior.csv"),
                    credit=BucketAvailability(status="available" if uid != "MX0002" else "missing", available=uid != "MX0002", source_type="csv" if uid != "MX0002" else "missing", path=f"/tmp/{uid}_credit.csv" if uid != "MX0002" else None),
                    available_buckets=["app", "behavior"] + (["credit"] if uid != "MX0002" else []),
                    missing_buckets=[] if uid != "MX0002" else ["credit"],
                )
                for uid in incoming_uids
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(PermissionError("User rejected SQL execution")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for uid_file repair failure")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    parse_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done"
    )
    repair_running_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "running"
    )
    tool_completed_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    review_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "review_result")
    final_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "final")
    tool_completed = events[tool_completed_index]

    assert parse_done_index < repair_running_index < tool_completed_index
    assert tool_completed["status"] == "error"
    assert "run_cancelled" not in event_types
    assert "data_acquisition_unavailable" not in [evt.get("step_id") for evt in events if evt["type"] == "plan_step_status"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_index < final_index


def test_run_agent_loop_uid_file_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uids = ["MX0001", "MX0002"]
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=["credit"],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_data_acquisition_capability",
        lambda: type("Cap", (), {"mode": "required", "enabled": True, "reason": None})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )

    def _availability(incoming_uids, country=None):
        availability_calls["count"] += 1
        return DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
                for uid in incoming_uids
            ],
        )

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": "credit"}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": uids,
                    "written_uids": uids,
                    "filenames": [f"{uid}.csv" for uid in uids],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": len(uids),
                    "rows_actual": len(uids),
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for uid_file still-unavailable repair")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    parse_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done"
    )
    repair_running_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "running"
    )
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )
    review_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "review_result")
    final_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "final")

    assert availability_calls["count"] >= 2
    assert parse_done_index < repair_running_index
    assert "run_cancelled" not in event_types
    assert run_profile_step["status"] == "blocked"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_index < final_index


def test_run_agent_loop_uid_file_repair_partial_unavailable_runs_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    full_uid = "MX0001"
    partial_uid = "MX0002"
    uids = [full_uid, partial_uid]
    availability_calls = {"count": 0}
    seen_profile_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[],
            uid_file_path="./data/id_files/mx/sample.txt",
            modules=[],
            request_summary="分析 UID 文件 ./data/id_files/mx/sample.txt 的批量画像请求",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_data_acquisition_capability",
        lambda: type("Cap", (), {"mode": "required", "enabled": True, "reason": None})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uids": uids,
                "source_path": inp.file_path,
                "duplicates_removed": 0,
            },
        })(),
    )

    def _availability(incoming_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            rows = [
                (full_uid, True, True, True),
                (partial_uid, True, True, False),
            ]
        else:
            rows = [
                (full_uid, True, True, True),
                (partial_uid, True, False, False),
            ]
        return DataAvailability(
            country="mx",
            checked_uids=list(incoming_uids),
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=app, source_type="csv", path=f"/tmp/{uid}_app.csv" if app else None),
                    behavior=BucketAvailability(status="available" if behavior else "missing", available=behavior, source_type="csv" if behavior else "missing", path=f"/tmp/{uid}_behavior.csv" if behavior else None),
                    credit=BucketAvailability(status="available" if credit else "missing", available=credit, source_type="csv" if credit else "missing", path=f"/tmp/{uid}_credit.csv" if credit else None),
                    available_buckets=[name for name, flag in (("app", app), ("behavior", behavior), ("credit", credit)) if flag],
                    missing_buckets=[name for name, flag in (("app", app), ("behavior", behavior), ("credit", credit)) if not flag],
                )
                for uid, app, behavior, credit in rows
            ],
        )

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [partial_uid],
                    "written_uids": [partial_uid],
                    "filenames": [f"{partial_uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: seen_profile_inputs.append(inp.model_dump(mode="json")) or type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules),
            },
        })(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。")]

    events = asyncio.run(_drive())
    parse_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "parse_uid_file" and evt["status"] == "done"
    )
    repair_done_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "plan_step_status" and evt["step_id"] == "repair_credit" and evt["status"] == "done"
    )
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    review_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "review_result")
    final_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "final")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert availability_calls["count"] >= 2
    assert parse_done_index < repair_done_index < run_profile_started_index
    assert seen_profile_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]
    assert review_evt["status"] == "warning"
    assert review_index < final_index


def test_run_agent_loop_repairs_missing_credit_then_runs_full_modules(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        RepairProfileDataOutput,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    ])
    seen_modules = []
    repair_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )

    def _fake_repair(input_data, *, session_id: str, tool_call_id: str, before_ack=None):
        repair_calls.append((input_data.bucket, list(input_data.uids)))
        if before_ack:
            before_ack("SELECT uid FROM bureau", 1)
        return RepairProfileDataOutput(
            bucket="credit",
            requested_uids=[uid],
            written_uids=[uid],
            filenames=[f"{uid}.csv"],
            sql_text="SELECT uid FROM bureau",
            rows_estimated=1,
            rows_actual=1,
        )

    def _fake_run_profile(inp, progress_callback=None):
        seen_modules.extend(inp.modules or [])
        return type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])},
        })()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        _fake_repair,
        raising=False,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    assert repair_calls == [("credit", [uid])]
    assert seen_modules == ["app", "behavior", "credit", "comprehensive", "product", "ops"]
    assert [evt["type"] for evt in events].count("execution_plan") >= 1
    assert "awaiting_user_ack" in [evt["type"] for evt in events]


def test_run_agent_loop_repair_tool_failure_stops_before_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
    ])
    seen_modules = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("User rejected SQL execution")),
        raising=False,
    )

    def _fake_run_profile(inp, progress_callback=None):
        seen_modules.extend(inp.modules or [])
        return type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])},
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    assert seen_modules == []
    assert "review_result" in types
    assert "tool_completed" in types
    tool_completed = next(
        evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    assert tool_completed["status"] == "error"
    assert "data_acquisition_unavailable" not in [evt.get("step_id") for evt in events if evt["type"] == "plan_step_status"]
    assert "run_profile" not in [evt.get("tool_name") for evt in events if evt.get("type") == "tool_started"]
    assert "补数执行失败" in events[-1]["final_message"]


def test_run_agent_loop_two_bucket_repair_runs_profile_only_after_both_repairs(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    ])
    seen_modules = []
    call_order = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )

    def _fake_run_profile(inp, progress_callback=None):
        seen_modules.extend(inp.modules or [])
        return type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])},
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )

    session = create_session(country="mx")

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    events = asyncio.run(_drive())
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    run_profile_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"]
    awaiting_indices = [idx for idx, evt in enumerate(events) if evt["type"] == "awaiting_user_ack"]
    repair_completed_indices = [
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ]
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )
    run_record = session.turns[-1].runs[-1]

    assert len(repair_tool_completed) == 2
    assert len(run_profile_started) == 1
    assert awaiting_indices[0] < repair_completed_indices[0] < awaiting_indices[1] < repair_completed_indices[1] < run_profile_started_index
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]
    assert seen_modules == ["app", "behavior", "credit", "comprehensive", "product", "ops"]
    assert run_record.pending_ack is None


def test_run_agent_loop_mixed_batch_two_bucket_repair_runs_profile_only_after_both_repairs(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[full_uid, credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[full_uid, credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
            ],
        ),
    ])
    seen_calls = []
    call_order = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )

    def _fake_prepare_repair_query(input_data):
        seen_calls.append(("prepare", input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("legacy/query path should not run for mixed batch repair success")

    def _fake_run_profile(inp, progress_callback=None):
        seen_calls.append(("profile", list(inp.uids), list(inp.modules or [])))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules or []),
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )

    session = create_session(country="mx")

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=session, prompt="批量分析这三个 UID 的完整画像"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    events = asyncio.run(_drive())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    repair_completed_indices = [
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    ]
    second_ack_index = [idx for idx, evt in enumerate(events) if evt["type"] == "awaiting_user_ack"][1]
    run_profile_started_index = next(
        idx for idx, evt in enumerate(events)
        if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile"
    )

    assert any(
        evt["type"] == "execution_plan"
        and {"repair_credit", "repair_behavior", "run_profile"}.issubset({step["step_id"] for step in evt["steps"]})
        for evt in plan_events
    )
    assert all("data_acquisition_unavailable" not in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert seen_calls[:2] == [
        ("prepare", "credit", [credit_uid]),
        ("prepare", "behavior", [behavior_uid]),
    ]
    assert second_ack_index > repair_completed_indices[0]
    assert run_profile_started_index > repair_completed_indices[1]
    assert review_evt["status"] == "pass"
    assert not any(issue["type"] in {"data_acquisition_unavailable", "partial_repair"} for issue in review_evt["issues"])
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]


def test_run_agent_loop_profile_uid_multi_uid_mixed_bucket_repair_runs_profile_only_after_both_repairs(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[full_uid, credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[full_uid, credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
            ],
        ),
    ])
    seen_calls = []
    call_order = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )

    def _fake_prepare_repair_query(input_data):
        seen_calls.append(("prepare", input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )()

    def _fake_execute_repair_query(prepared):
        bucket = prepared["prepared"]
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("legacy/query path should not run for mixed multi-uid repair success")

    def _fake_run_profile(inp, progress_callback=None):
        seen_calls.append(("profile", list(inp.uids), list(inp.modules or [])))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules or []),
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _fake_execute_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: call_order.append("open_ack"))
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )

    session = create_session(country="mx")

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=session, prompt="批量分析这三个 UID 的完整画像"):
            events.append(evt)
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
        return events

    events = asyncio.run(_drive())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert any(
        evt["type"] == "execution_plan"
        and {"repair_credit", "repair_behavior", "run_profile"}.issubset({step["step_id"] for step in evt["steps"]})
        for evt in plan_events
    )
    assert seen_calls[:2] == [
        ("prepare", "credit", [credit_uid]),
        ("prepare", "behavior", [behavior_uid]),
    ]
    assert any(item[0] == "profile" for item in seen_calls)
    assert review_evt["status"] == "pass"
    assert call_order[:6] == ["open_ack", "awaiting_user_ack", "wait_ack", "open_ack", "awaiting_user_ack", "wait_ack"]


def test_run_agent_loop_mixed_batch_two_bucket_repair_first_failure_never_starts_second_repair_or_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        raise PermissionError(f"{bucket} repair failed")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when first mixed repair fails")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    repair_tool_started = [evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data"]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert execute_calls == ["credit"]
    assert len(repair_tool_started) == 1
    assert len(repair_tool_completed) == 1
    assert repair_tool_completed[0]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


def test_run_agent_loop_mixed_batch_two_bucket_repair_second_failure_never_starts_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        if bucket == "behavior":
            raise PermissionError("behavior repair failed")
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when second mixed repair fails")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert execute_calls == ["credit", "behavior"]
    assert len(repair_tool_completed) == 2
    assert repair_tool_completed[0]["status"] == "ok"
    assert repair_tool_completed[1]["status"] == "error"
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


def test_run_agent_loop_mixed_batch_two_bucket_first_rejected_never_starts_second_repair_or_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for rejected first mixed repair")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for rejected first mixed repair")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: False)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert event_types.count("awaiting_user_ack") == 1
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_mixed_batch_two_bucket_second_non_approved_never_starts_run_profile(monkeypatch, ack_value, wait_path):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        target_uid = credit_uid if bucket == "credit" else behavior_uid
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [target_uid],
                    "written_uids": [target_uid],
                    "filenames": [f"{target_uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for second mixed non-approved repair")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)

    ack_counter = {"count": 0}
    if wait_path == "ack_bus":
        def _wait_ack(sid, timeout_sec=600.0):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return True
            return ack_value

        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", _wait_ack)
    else:
        from app.services.orchestrator_agent.loop_context import HumanInputResult

        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return HumanInputResult(status="approved")
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert execute_calls == ["credit"]
    assert event_types.count("awaiting_user_ack") == 2
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


def test_run_agent_loop_mixed_batch_two_bucket_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[credit_uid, behavior_uid],
            modules=["behavior", "credit"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        return DataAvailability(
            country=country or "mx",
            checked_uids=[credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                ),
            ],
        )

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "written_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "filenames": [f"{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when mixed repair recheck stays blocked")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert availability_calls["count"] >= 2
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"


def test_run_agent_loop_mixed_batch_two_bucket_repair_partial_unavailable_runs_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    credit_uid = "824812551379353601"
    behavior_uid = "824812551379353602"
    availability_calls = {"count": 0}
    seen_repair_inputs = []
    seen_profile_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, credit_uid, behavior_uid],
            modules=["app", "behavior", "credit", "comprehensive"],
            request_summary="批量分析这三个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return DataAvailability(
                country=country or "mx",
                checked_uids=[full_uid, credit_uid, behavior_uid],
                per_uid=[
                    UidAvailability(
                        uid=full_uid,
                        app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                        behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                        credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                        available_buckets=["app", "behavior", "credit"],
                        missing_buckets=[],
                    ),
                    UidAvailability(
                        uid=credit_uid,
                        app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                        behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                        credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                        available_buckets=["app", "behavior"],
                        missing_buckets=["credit"],
                    ),
                    UidAvailability(
                        uid=behavior_uid,
                        app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                        behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                        credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                        available_buckets=["app", "credit"],
                        missing_buckets=["behavior"],
                    ),
                ],
            )
        return DataAvailability(
            country=country or "mx",
            checked_uids=[full_uid, credit_uid, behavior_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=credit_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{credit_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=behavior_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{behavior_uid}_credit.csv"),
                    available_buckets=["app", "credit"],
                    missing_buckets=["behavior"],
                ),
            ],
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": len(input_data.uids), "raw_prepared": {"prepared": input_data.bucket}},
        )()

    def _fake_run_profile(inp, progress_callback=None):
        seen_profile_inputs.append(inp.model_dump(mode="json"))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.uids) * len(inp.modules or [])},
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("query_data/legacy should not run for mixed batch repair partial path")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "written_uids": [credit_uid if prepared["prepared"] == "credit" else behavior_uid],
                    "filenames": [f"{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这三个 UID 的完整画像")]

    events = asyncio.run(_drive())
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [("credit", [credit_uid]), ("behavior", [behavior_uid])]
    assert seen_profile_inputs
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "warning"
    assert {issue["type"] for issue in review_evt["issues"]} >= {"data_acquisition_unavailable", "partial_repair"}
    assert ("部分" in final_evt["final_message"]) or ("降级" in final_evt["final_message"])


@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_repair_non_approved_never_starts_run_profile(monkeypatch, ack_value, wait_path):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    session = create_session(country="mx")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": True}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for non-approved repair path")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for non-approved repair path")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    else:
        from app.services.orchestrator_agent.loop_context import HumanInputResult

        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_profile_batch_single_bucket_repair_non_approved_never_starts_run_profile(monkeypatch, ack_value, wait_path):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    session = create_session(country="mx")
    seen_repair_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country=country or "mx",
            checked_uids=[full_uid, repair_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=repair_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{repair_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{repair_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
            ],
        ),
    )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for batch non-approved repair path")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(AssertionError("execute should not run for non-approved repair path")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    if wait_path == "ack_bus":
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    else:
        from app.services.orchestrator_agent.loop_context import HumanInputResult

        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]
    run_profile_steps = [
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    ]

    assert seen_repair_inputs == [("credit", [repair_uid])]
    assert "awaiting_user_ack" in event_types
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_steps == []
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


def test_run_agent_loop_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        return DataAvailability(
            country=country or "mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        )

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": True}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when repair recheck still unavailable")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(_drive())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert availability_calls["count"] >= 2
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert [evt["type"] for evt in events].count("final") == 1
    assert assistant_after - assistant_before == 1


def test_run_agent_loop_profile_batch_single_bucket_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    first_uid = "824812551379353600"
    second_uid = "824812551379353601"
    availability_calls = {"count": 0}
    seen_repair_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[first_uid, second_uid],
            modules=["credit"],
            request_summary="批量分析这两个 UID 的 credit 画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        return DataAvailability(
            country=country or "mx",
            checked_uids=[first_uid, second_uid],
            per_uid=[
                UidAvailability(
                    uid=first_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{first_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{first_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=second_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{second_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{second_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
            ],
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for batch still-unavailable repair path")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [first_uid, second_uid],
                    "written_uids": [first_uid, second_uid],
                    "filenames": [f"{first_uid}.csv", f"{second_uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 2,
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的 credit 画像")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(_drive())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [("credit", [first_uid, second_uid])]
    assert "run_cancelled" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


def test_run_agent_loop_profile_batch_single_bucket_repair_partial_unavailable_runs_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"
    availability_calls = {"count": 0}
    seen_repair_inputs = []
    seen_profile_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, partial_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1:
            return DataAvailability(
                country=country or "mx",
                checked_uids=[full_uid, partial_uid],
                per_uid=[
                    UidAvailability(
                        uid=full_uid,
                        app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                        behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                        credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                        available_buckets=["app", "behavior", "credit"],
                        missing_buckets=[],
                    ),
                    UidAvailability(
                        uid=partial_uid,
                        app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{partial_uid}_app.csv"),
                        behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{partial_uid}_behavior.csv"),
                        credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                        available_buckets=["app", "behavior"],
                        missing_buckets=["credit"],
                    ),
                ],
            )
        return DataAvailability(
            country=country or "mx",
            checked_uids=[full_uid, partial_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=partial_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{partial_uid}_app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                ),
            ],
        )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )()

    def _fake_run_profile(inp, progress_callback=None):
        seen_profile_inputs.append(inp.model_dump(mode="json"))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.uids) * len(inp.modules or [])},
        })()

    def _fail(*args, **kwargs):
        raise AssertionError("query_data/legacy should not run for batch repair partial path")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": "credit",
                    "requested_uids": [partial_uid],
                    "written_uids": [partial_uid],
                    "filenames": [f"{partial_uid}.csv"],
                    "sql_text": "SELECT * FROM credit_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(_drive())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert availability_calls["count"] >= 2
    assert seen_repair_inputs == [("credit", [partial_uid])]
    assert seen_profile_inputs == [
        {
            "uids": [full_uid],
            "app_time": None,
            "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"],
            "strict_data_mode": True,
        },
        {
            "uids": [partial_uid],
            "app_time": None,
            "modules": ["app"],
            "strict_data_mode": True,
        },
    ]
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "warning"
    issue_types = {issue.get("type") for issue in review_evt["issues"]}
    assert "data_acquisition_unavailable" in issue_types
    assert "partial_repair" in issue_types
    assert event_types.count("final") == 1
    assert ("部分" in final_evt["final_message"]) or ("降级" in final_evt["final_message"])
    assert assistant_after - assistant_before == 1


def test_run_agent_loop_profile_batch_single_bucket_repair_tool_failure_stops_before_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    full_uid = "824812551379353600"
    repair_uid = "824812551379353601"
    seen_repair_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, repair_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析这两个 UID 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country=country or "mx",
            checked_uids=[full_uid, repair_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{full_uid}_credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=repair_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{repair_uid}_app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path=f"/tmp/{repair_uid}_behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
            ],
        ),
    )

    def _fake_prepare_repair_query(input_data):
        seen_repair_inputs.append((input_data.bucket, list(input_data.uids)))
        return type(
            "PreparedRepair",
            (),
            {"sql_text": "SELECT * FROM credit_source", "rows_estimated": 1, "raw_prepared": {"prepared": "credit"}},
        )()

    def _fail(*args, **kwargs):
        raise AssertionError("run_profile/query_data/legacy should not run for batch repair failure")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _fake_prepare_repair_query)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: (_ for _ in ()).throw(PermissionError("User rejected SQL execution")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _fail)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="批量分析这两个 UID 的完整画像")]

    assistant_before = len([m for m in session.messages if m.role == "assistant"])
    events = asyncio.run(_drive())
    assistant_after = len([m for m in session.messages if m.role == "assistant"])
    event_types = [evt["type"] for evt in events]
    tool_completed = next(
        evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"
    )
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert seen_repair_inputs == [("credit", [repair_uid])]
    assert tool_completed["status"] == "error"
    assert "run_cancelled" not in event_types
    assert "data_acquisition_unavailable" not in [evt.get("step_id") for evt in events if evt["type"] == "plan_step_status"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)
    assert event_types.count("final") == 1
    assert assistant_after - assistant_before == 1


def test_run_agent_loop_two_bucket_repair_second_failure_never_starts_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability = DataAvailability(
        country="mx",
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                available_buckets=["app"],
                missing_buckets=["behavior", "credit"],
            )
        ],
    )
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: availability,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        if bucket == "behavior":
            raise PermissionError("behavior repair failed")
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when second repair fails")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]

    assert execute_calls == ["credit", "behavior"]
    assert len(repair_tool_completed) == 2
    assert repair_tool_completed[0]["status"] == "ok"
    assert repair_tool_completed[1]["status"] == "error"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None


def test_run_agent_loop_two_bucket_repair_first_failure_never_starts_second_repair_or_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability = DataAvailability(
        country="mx",
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                available_buckets=["app"],
                missing_buckets=["behavior", "credit"],
            )
        ],
    )
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: availability,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        raise PermissionError(f"{bucket} repair failed")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when first repair fails")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_record = session.turns[-1].runs[-1]

    assert execute_calls == ["credit"]
    assert len(repair_tool_completed) == 1
    assert repair_tool_completed[0]["status"] == "error"
    assert [evt["type"] for evt in events].count("awaiting_user_ack") == 1
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert review_evt["status"] == "fail"
    assert run_record.pending_ack is None


@pytest.mark.parametrize(
    ("ack_value", "wait_path"),
    [
        (False, "ack_bus"),
        (None, "ack_bus"),
        ("cancelled", "human_input"),
    ],
)
def test_run_agent_loop_two_bucket_repair_second_non_approved_never_starts_run_profile(monkeypatch, ack_value, wait_path):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    session = create_session(country="mx")
    execute_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )

    def _execute(prepared):
        bucket = prepared["prepared"]
        execute_calls.append(bucket)
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": bucket,
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{bucket}.csv"],
                    "sql_text": f"SELECT * FROM {bucket}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run for second non-approved repair")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)

    ack_counter = {"count": 0}
    if wait_path == "ack_bus":
        def _wait_ack(sid, timeout_sec=600.0):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return True
            return ack_value
        monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", _wait_ack)
    else:
        from app.services.orchestrator_agent.loop_context import HumanInputResult

        async def _fake_wait_for_ack(self, *, session_id, timeout_seconds=600.0, poll_interval=0.25, should_cancel=None):
            ack_counter["count"] += 1
            if ack_counter["count"] == 1:
                return HumanInputResult(status="approved")
            return HumanInputResult(status="cancelled")

        monkeypatch.setattr(
            "app.services.orchestrator_agent.runtime.human_input.HumanInputController.wait_for_ack",
            _fake_wait_for_ack,
        )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]
    run_record = session.turns[-1].runs[-1]
    repair_tool_calls = [call for call in session.tool_calls if call.run_id == run_record.run_id and call.tool_name == "repair_profile_data"]

    assert execute_calls == ["credit"]
    assert event_types.count("awaiting_user_ack") == 2
    assert "run_cancelled" in event_types
    assert "review_result" not in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_record.pending_ack is None
    assert run_record.status == "cancelled"
    assert session.active_run_id is None
    assert repair_tool_calls
    assert all(call.status != "running" for call in repair_tool_calls)


def test_run_agent_loop_two_bucket_repair_still_unavailable_blocks_without_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        return DataAvailability(
            country=country or "mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        )

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.check_data_availability", _availability)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        lambda input_data: type(
            "PreparedRepair",
            (),
            {"sql_text": f"SELECT * FROM {input_data.bucket}_source", "rows_estimated": 1, "raw_prepared": {"prepared": input_data.bucket}},
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        lambda prepared: type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["prepared"],
                    "requested_uids": [uid],
                    "written_uids": [uid],
                    "filenames": [f"{uid}_{prepared['prepared']}.csv"],
                    "sql_text": f"SELECT * FROM {prepared['prepared']}_source",
                    "rows_estimated": 1,
                    "rows_actual": 1,
                },
            },
        )(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when two-bucket repair recheck still unavailable")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    repair_tool_completed = [evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "repair_profile_data"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    run_profile_step = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt["step_id"] == "run_profile"
    )

    assert availability_calls["count"] >= 2
    assert len(repair_tool_completed) == 2
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert run_profile_step["status"] == "blocked"
    assert review_evt["status"] == "fail"
    assert [evt["type"] for evt in events].count("final") == 1

def test_run_agent_loop_blocks_large_cohort_before_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run for large cohort block"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="查询最近 7 天高流失用户并生成画像",
            query_request="最近7天高流失用户",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {"uids": [f"u{i:03d}" for i in range(201)], "rows_actual": 201, "rows_estimated": 201, "sql_text": "SELECT uid FROM t"},
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我找最近7天高流失用户并分析")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    assert "execution_plan" in types
    assert "review_result" in types
    assert "final" in types
    assert "tool_started" in types
    assert "tool_completed" in types
    assert "缩小范围" in events[-1]["final_message"]


def test_run_agent_loop_known_cohort_opens_ack_before_emitting_preview(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    call_order = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app"],
            request_summary="查询 cohort 并画像",
            query_request="拉一批用户",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {"child": object(), "sql_text": "SELECT uid FROM t", "rows_estimated": 1},
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        lambda *args, **kwargs: {"uids": ["u1"], "rows_actual": 1, "rows_estimated": 1, "sql_text": "SELECT uid FROM t"},
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.open_ack",
        lambda sid: call_order.append("open_ack"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["DataAvailability"]).DataAvailability(country="mx", checked_uids=["u1"], per_uid=[]),
    )

    session = create_session(country="mx")

    async def _drive():
        seen = []
        async for evt in run_agent_loop(session=session, prompt="帮我拉一批用户并分析"):
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
            seen.append(evt)
        return seen

    events = asyncio.run(_drive())
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    assert "awaiting_user_ack" in [evt["type"] for evt in events]
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]
    assert "查询摘要" in awaiting_evt["sql_text"]
    assert "筛选条件" in awaiting_evt["sql_text"]
    assert "确认提示" in awaiting_evt["sql_text"]
    assert "原始 SQL" in awaiting_evt["sql_text"]
    assert "SELECT uid FROM t" in awaiting_evt["sql_text"]
    assert awaiting_evt["sql_text"] != "SELECT uid FROM t"


def test_run_agent_loop_blocks_non_mx_cohort_without_tool_dispatch(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="th",
            uids=[],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="查询泰国 cohort 并生成画像",
            query_request="最近7天高流失用户",
            read_only=False,
        ),
    )

    session = create_session(country="th")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我找最近7天高流失用户并分析")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    assert types[:3] == ["session_started", "turn_started", "run_started"]
    assert types[-4:] == ["plan_step_status", "plan_step_status", "review_result", "final"]
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    assert [step["step_id"] for step in plan_evt["steps"]] == ["query_data", "review_final"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "unsupported_country" for issue in review_evt["issues"])
    assert "仅支持 mx" in events[-1]["final_message"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert types.count("final") == 1


def test_run_agent_loop_blocks_when_no_basic_bucket_exists(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    behavior=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=[],
                    missing_buckets=["app", "behavior", "credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("User rejected SQL execution")),
        raising=False,
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid}")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    assert "tool_started" in types
    assert "run_profile" not in [evt.get("tool_name") for evt in events if evt.get("type") == "tool_started"]
    assert "无法生成可信画像" in events[-1]["final_message"]


def test_run_agent_loop_app_only_request_ignores_unrelated_missing_bucket_when_data_acquisition_disabled(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_disabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    seen_modules = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app"],
            request_summary=f"分析 UID {uid} 的 app 画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: (
            seen_modules.extend(inp.modules or []),
            type("X", (), {
                "model_dump": lambda self, mode="json": {
                    "results": [{
                        "uid": uid,
                        "module": "app",
                        "result": {
                            "status": "ok",
                            "data": {"summary": "app ok", "structured_result": {"x": 1}, "charts": [], "report_markdown": ""},
                            "error": None,
                        },
                    }],
                    "cache_hits": 0,
                    "cache_misses": 1,
                },
            })()
        )[1],
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我看 {uid} 的 app 画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert all("data_acquisition_unavailable" not in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert all("repair_credit" not in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert seen_modules == ["app"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "pass"


def test_run_agent_loop_full_profile_partial_when_credit_missing_and_data_acquisition_disabled(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_disabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    seen_modules = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary=f"分析 UID {uid} 的完整画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: (
            seen_modules.extend(inp.modules or []),
            type("X", (), {
                "model_dump": lambda self, mode="json": {
                    "results": [
                        {
                            "uid": uid,
                            "module": module,
                            "result": {
                                "status": "ok",
                                "data": {"summary": f"{module} ok", "structured_result": {"module": module}, "charts": [], "report_markdown": ""},
                                "error": None,
                            },
                        }
                        for module in (inp.modules or [])
                    ],
                    "cache_hits": 0,
                    "cache_misses": len(inp.modules or []),
                },
            })()
        )[1],
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid} 的完整画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert any("data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert not any("repair_credit" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert seen_modules == ["app", "behavior"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "warning"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])


def test_run_agent_loop_credit_only_request_blocks_when_credit_missing_and_data_acquisition_disabled(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_disabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["credit"],
            request_summary=f"分析 UID {uid} 的征信画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when requested module is unavailable")),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid} 的征信画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert any("data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert not any("repair_credit" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])


def test_run_agent_loop_direct_profile_still_plans_repair_when_data_acquisition_enabled(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"
    availability_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app", "behavior", "credit"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )

    def _availability(uids, country=None):
        availability_calls["count"] += 1
        credit_status = (
            BucketAvailability(status="missing", available=False, usable_for_profile=False, source_type="missing", path=None)
            if availability_calls["count"] == 1
            else BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/credit.csv")
        )
        available_buckets = ["app", "behavior"] if availability_calls["count"] == 1 else ["app", "behavior", "credit"]
        missing_buckets = ["credit"] if availability_calls["count"] == 1 else []
        return DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=credit_status,
                    available_buckets=available_buckets,
                    missing_buckets=missing_buckets,
                )
            ],
        )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        _availability,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        lambda *args, **kwargs: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "bucket": "credit",
                "requested_uids": [uid],
                "written_uids": [uid],
                "filenames": [f"{uid}.csv"],
                "sql_text": "SELECT * FROM bureau",
                "rows_estimated": 1,
                "rows_actual": 1,
            },
        })(),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [
                    {
                        "uid": uid,
                        "module": module,
                        "result": {
                            "status": "ok",
                            "data": {"summary": f"{module} ok", "structured_result": {"module": module}, "charts": [], "report_markdown": ""},
                            "error": None,
                        },
                    }
                    for module in (inp.modules or [])
                ],
                "cache_hits": 0,
                "cache_misses": len(inp.modules or []),
            },
        })(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析 {uid} 的画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert any("repair_credit" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)
    assert not any("data_acquisition_unavailable" in [step["step_id"] for step in evt["steps"]] for evt in plan_events)


def test_run_agent_loop_cohort_emits_updated_execution_plan_for_profile_phase(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="最近 7 天高流失用户画像",
            query_request="最近7天高流失用户",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {"uids": [uid], "rows_actual": 1, "rows_estimated": 1, "sql_text": "SELECT uid FROM t"},
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])},
        })(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我找最近7天高流失用户并分析")]

    events = asyncio.run(_drive())
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert len(plan_events) >= 2


def test_run_agent_loop_need_clarification_emits_resolution_event(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest, RequestUnderstanding
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=[],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx"},
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.open_resolution",
        lambda session_id, resolution_id=None, run_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.wait_resolution",
        lambda session_id, timeout_sec=600.0: {
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            "resolution_type": "clarification",
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {"uids": ["u1"], "rows_actual": 1, "rows_estimated": 1, "sql_text": "SELECT uid FROM t"},
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["DataAvailability"]).DataAvailability(country="mx", checked_uids=["u1"], per_uid=[]),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    assert "execution_plan" in [evt["type"] for evt in events]
    resolution_evt = next(evt for evt in events if evt["type"] == "awaiting_resolution")
    assert resolution_evt["resolution_type"] == "clarification"
    assert resolution_evt["required_slots"] == ["country", "time_window"]
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)


def _patch_query_only_clarification_resume_visible(
    monkeypatch,
    *,
    preview_result: dict[str, object] | None = None,
    preview_exception: Exception | None = None,
    complete_result: dict[str, object] | None = None,
    complete_exception: Exception | None = None,
    ack_value=True,
    seen_query_requests: list[tuple[str, str]] | None = None,
):
    from app.services.orchestrator_agent.session_store import create_session
    from app.services.orchestrator_agent.schemas import NormalizedRequest, RequestUnderstanding

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app", "behavior"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.open_resolution",
        lambda session_id, resolution_id=None, run_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.wait_resolution",
        lambda session_id, timeout_sec=600.0: {
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            "resolution_type": "clarification",
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )

    def _preview(*args, **kwargs):
        if seen_query_requests is not None:
            seen_query_requests.append((args[1], args[2]))
        if preview_exception is not None:
            raise preview_exception
        if preview_result is not None:
            return preview_result
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    def _complete(*args, **kwargs):
        if complete_exception is not None:
            raise complete_exception
        if complete_result is not None:
            return complete_result
        return {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        _preview,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        _complete,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: ack_value,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("availability should not run when auto_profile=false")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when auto_profile=false")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_tool_registry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("get_tool_registry should not run for query-only clarification flow")),
    )

    async def _legacy_resume(*args, **kwargs):
        raise AssertionError("legacy clarification resume should not run for auto_profile=false query-only path")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._run_clarification_resume_legacy",
        _legacy_resume,
    )
    return create_session(country="mx")


def _patch_query_profile_clarification_resume_visible(
    monkeypatch,
    *,
    complete_result: dict[str, object] | None = None,
    availability=None,
    post_repair_availability=None,
    modules: list[str] | None = None,
    ack_value=True,
    query_ack_value=None,
    repair_ack_value=None,
    repair_execute_exception: Exception | None = None,
    allow_profile_run: bool = True,
    allow_repair_run: bool = False,
):
    from app.services.orchestrator_agent.session_store import create_session
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        RequestUnderstanding,
        UidAvailability,
    )

    def _available_bucket(path: str):
        return BucketAvailability(
            status="available",
            available=True,
            usable_for_profile=True,
            checked_sources=["csv:available"],
            source_type="csv",
            path=path,
        )

    def _missing_bucket(path: str):
        return BucketAvailability(
            status="missing",
            available=False,
            usable_for_profile=False,
            checked_sources=["csv:missing"],
            source_type="csv",
            path=path,
        )

    def _availability_for_rows(rows: list[tuple[str, bool, bool, bool]], *, country: str = "mx"):
        checked_uids: list[str] = []
        per_uid: list[UidAvailability] = []
        for uid, app, behavior, credit in rows:
            checked_uids.append(uid)
            available_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if ok]
            missing_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if not ok]
            per_uid.append(
                UidAvailability(
                    uid=uid,
                    app=_available_bucket(f"{uid}-app.csv") if app else _missing_bucket(f"{uid}-app.csv"),
                    behavior=_available_bucket(f"{uid}-behavior.csv") if behavior else _missing_bucket(f"{uid}-behavior.csv"),
                    credit=_available_bucket(f"{uid}-credit.csv") if credit else _missing_bucket(f"{uid}-credit.csv"),
                    available_buckets=available_buckets,
                    missing_buckets=missing_buckets,
                )
            )
        return DataAvailability(country=country, checked_uids=checked_uids, per_uid=per_uid)

    _patch_enabled_data_acquisition(monkeypatch)
    active_modules = list(modules or ["app", "behavior"])
    availability_calls = {"count": 0}
    ack_values = [
        query_ack_value if query_ack_value is not None else ack_value,
        repair_ack_value if repair_ack_value is not None else ack_value,
    ]

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=list(active_modules),
            trace_days=7,
            request_summary="找一批高流失用户并自动画像",
            query_request="找一批高流失用户并自动画像",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort", "profile"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.open_resolution",
        lambda session_id, resolution_id=None, run_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.wait_resolution",
        lambda session_id, timeout_sec=600.0: {
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": True},
            "resolution_type": "clarification",
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并自动画像",
        }),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        lambda *args, **kwargs: complete_result or {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        },
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)

    def _wait_ack(sid, timeout_sec=600.0):
        if ack_values:
            return ack_values.pop(0)
        return ack_value

    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        _wait_ack,
    )
    def _check_data_availability(resolved_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1 and availability is not None:
            return availability
        if availability_calls["count"] > 1 and post_repair_availability is not None:
            return post_repair_availability
        return _availability_for_rows(
            [(uid, True, True, False) for uid in resolved_uids],
            country=country or "mx",
        )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        _check_data_availability,
    )
    def _prepare_repair_query(input_data):
        if not allow_repair_run:
            raise AssertionError("repair_profile_data should not run for this visible test")
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {
                    "bucket": input_data.bucket,
                    "uids": list(input_data.uids),
                },
            },
        )()

    def _execute_repair_query(prepared):
        if not allow_repair_run:
            raise AssertionError("execute_repair_query should not run for this visible test")
        if repair_execute_exception is not None:
            raise repair_execute_exception
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["bucket"],
                    "requested_uids": list(prepared["uids"]),
                    "written_uids": list(prepared["uids"]),
                    "filenames": [f"{uid}_{prepared['bucket']}.csv" for uid in prepared["uids"]],
                    "sql_text": f"SELECT * FROM {prepared['bucket']}_source",
                    "rows_estimated": len(prepared["uids"]),
                    "rows_actual": len(prepared["uids"]),
                },
            },
        )()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.prepare_repair_query",
        _prepare_repair_query,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_repair_query",
        _execute_repair_query,
    )
    if not allow_profile_run:
        def _run_profile(*args, **kwargs):
            raise AssertionError("run_profile should not run for this visible test")
    else:
        def _run_profile(inp, progress_callback=None):
            return type(
                "RunProfileOut",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "results": [
                            {
                                "uid": uid,
                                "module": module,
                                "result": {
                                    "status": "ok",
                                    "data": {
                                        "summary": f"{uid}-{module}-ok",
                                        "structured_result": {"uid": uid, "module": module},
                                    },
                                },
                            }
                            for uid in (inp.uids or [])
                            for module in (inp.modules or [])
                        ],
                        "cache_hits": 0,
                        "cache_misses": len((inp.uids or [])) * len((inp.modules or [])),
                    },
                },
            )()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        _run_profile,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_tool_registry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("get_tool_registry should not run for query-profile clarification flow")),
    )

    async def _legacy_resume(*args, **kwargs):
        raise AssertionError("legacy clarification resume should not run for auto_profile=true query-profile path")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._run_clarification_resume_legacy",
        _legacy_resume,
    )
    return create_session(country="mx")


def _patch_first_turn_query_profile_visible(
    monkeypatch,
    *,
    preview_result: dict[str, object] | None = None,
    preview_exception: Exception | None = None,
    complete_result: dict[str, object] | None = None,
    complete_exception: Exception | None = None,
    availability=None,
    post_repair_availability=None,
    modules: list[str] | None = None,
    ack_value=True,
    query_ack_value=None,
    repair_ack_value=None,
    repair_execute_exception: Exception | None = None,
    allow_profile_run: bool = True,
    allow_repair_run: bool = False,
    seen_query_requests: list[tuple[str, str]] | None = None,
):
    from app.services.orchestrator_agent.session_store import create_session
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )

    def _available_bucket(path: str):
        return BucketAvailability(
            status="available",
            available=True,
            usable_for_profile=True,
            checked_sources=["csv:available"],
            source_type="csv",
            path=path,
        )

    def _missing_bucket(path: str):
        return BucketAvailability(
            status="missing",
            available=False,
            usable_for_profile=False,
            checked_sources=["csv:missing"],
            source_type="missing",
            path=path,
        )

    def _availability_for_rows(rows: list[tuple[str, bool, bool, bool]], *, country: str = "mx"):
        checked_uids: list[str] = []
        per_uid: list[UidAvailability] = []
        for uid, app, behavior, credit in rows:
            checked_uids.append(uid)
            available_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if ok]
            missing_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if not ok]
            per_uid.append(
                UidAvailability(
                    uid=uid,
                    app=_available_bucket(f"{uid}-app.csv") if app else _missing_bucket(f"{uid}-app.csv"),
                    behavior=_available_bucket(f"{uid}-behavior.csv") if behavior else _missing_bucket(f"{uid}-behavior.csv"),
                    credit=_available_bucket(f"{uid}-credit.csv") if credit else _missing_bucket(f"{uid}-credit.csv"),
                    available_buckets=available_buckets,
                    missing_buckets=missing_buckets,
                )
            )
        return DataAvailability(country=country, checked_uids=checked_uids, per_uid=per_uid)

    _patch_enabled_data_acquisition(monkeypatch)
    active_modules = list(modules or ["app", "behavior"])
    availability_calls = {"count": 0}
    ack_values = [
        query_ack_value if query_ack_value is not None else ack_value,
        repair_ack_value if repair_ack_value is not None else ack_value,
    ]

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=list(active_modules),
            trace_days=7,
            request_summary="查询 cohort 并画像",
            query_request="找墨西哥最近 7 天高流失用户并自动画像",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )

    def _preview(*args, **kwargs):
        if seen_query_requests is not None:
            seen_query_requests.append((args[1], args[2]))
        if preview_exception is not None:
            raise preview_exception
        if preview_result is not None:
            return preview_result
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        _preview,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        lambda *args, **kwargs: (
            (_ for _ in ()).throw(complete_exception)
            if complete_exception is not None
            else complete_result or {
                "uids": ["u1", "u2"],
                "rows_actual": 2,
                "rows_estimated": 5,
                "sql_text": "SELECT uid FROM t",
            }
        ),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)

    def _wait_ack(sid, timeout_sec=600.0):
        if ack_values:
            return ack_values.pop(0)
        return ack_value

    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", _wait_ack)

    def _check_data_availability(resolved_uids, country=None):
        availability_calls["count"] += 1
        if availability_calls["count"] == 1 and availability is not None:
            return availability
        if availability_calls["count"] > 1 and post_repair_availability is not None:
            return post_repair_availability
        return _availability_for_rows(
            [(uid, True, True, True) for uid in resolved_uids],
            country=country or "mx",
        )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        _check_data_availability,
    )

    def _prepare_repair_query(input_data):
        if not allow_repair_run:
            raise AssertionError("repair_profile_data should not run for this visible test")
        return type(
            "PreparedRepair",
            (),
            {
                "sql_text": f"SELECT * FROM {input_data.bucket}_source",
                "rows_estimated": len(input_data.uids),
                "raw_prepared": {
                    "bucket": input_data.bucket,
                    "uids": list(input_data.uids),
                },
            },
        )()

    def _execute_repair_query(prepared):
        if not allow_repair_run:
            raise AssertionError("execute_repair_query should not run for this visible test")
        if repair_execute_exception is not None:
            raise repair_execute_exception
        return type(
            "RepairOut",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "bucket": prepared["bucket"],
                    "requested_uids": list(prepared["uids"]),
                    "written_uids": list(prepared["uids"]),
                    "filenames": [f"{uid}_{prepared['bucket']}.csv" for uid in prepared["uids"]],
                    "sql_text": f"SELECT * FROM {prepared['bucket']}_source",
                    "rows_estimated": len(prepared["uids"]),
                    "rows_actual": len(prepared["uids"]),
                },
            },
        )()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.prepare_repair_query", _prepare_repair_query)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_repair_query", _execute_repair_query)

    if not allow_profile_run:
        def _run_profile(*args, **kwargs):
            raise AssertionError("run_profile should not run for this visible test")
    else:
        def _run_profile(inp, progress_callback=None):
            return type(
                "RunProfileOut",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "results": [
                            {
                                "uid": uid,
                                "module": module,
                                "result": {
                                    "status": "ok",
                                    "data": {
                                        "summary": f"{uid}-{module}-ok",
                                        "structured_result": {"uid": uid, "module": module},
                                    },
                                },
                            }
                            for uid in (inp.uids or [])
                            for module in (inp.modules or [])
                        ],
                        "cache_hits": 0,
                        "cache_misses": len((inp.uids or [])) * len((inp.modules or [])),
                    },
                },
            )()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _run_profile)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_tool_registry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("get_tool_registry should not run for first-turn query_data_then_profile")),
    )

    async def _legacy(*args, **kwargs):
        raise AssertionError("first-turn query_data_then_profile should not use legacy _run_known_request")
        yield {}

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._run_known_request", _legacy)
    return create_session(country="mx")


def _visible_availability_for_rows(rows: list[tuple[str, bool, bool, bool]], *, country: str = "mx"):
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="missing", path=path)

    checked_uids: list[str] = []
    per_uid: list[UidAvailability] = []
    for uid, app, behavior, credit in rows:
        checked_uids.append(uid)
        available_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if ok]
        missing_buckets = [bucket for bucket, ok in [("app", app), ("behavior", behavior), ("credit", credit)] if not ok]
        per_uid.append(
            UidAvailability(
                uid=uid,
                app=_available_bucket(f"{uid}-app.csv") if app else _missing_bucket(f"{uid}-app.csv"),
                behavior=_available_bucket(f"{uid}-behavior.csv") if behavior else _missing_bucket(f"{uid}-behavior.csv"),
                credit=_available_bucket(f"{uid}-credit.csv") if credit else _missing_bucket(f"{uid}-credit.csv"),
                available_buckets=available_buckets,
                missing_buckets=missing_buckets,
            )
        )
    return DataAvailability(country=country, checked_uids=checked_uids, per_uid=per_uid)


def _assert_no_clarify_scope_in_visible_plan(events):
    assert not any(
        step["step_id"] == "clarify_scope"
        for evt in events
        if evt["type"] == "execution_plan"
        for step in evt["steps"]
    )


def test_run_agent_loop_query_data_then_profile_first_turn_success_visible(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    seen_query_requests: list[tuple[str, str]] = []
    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        availability=_visible_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        seen_query_requests=seen_query_requests,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    run_profile_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    _assert_no_clarify_scope_in_visible_plan(events)
    assert [step["step_id"] for step in plan_events[-1]["steps"]] == ["query_data", "check_data", "run_profile", "review_final"]
    assert events.index(query_completed) < events.index(check_data_done) < events.index(run_profile_started) < events.index(run_profile_completed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "pass"
    assert [evt["type"] for evt in events].count("final") == 1
    assert next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data")["input"] == {
        "request": "找墨西哥最近 7 天高流失用户并自动画像",
        "country": "mx",
    }
    assert seen_query_requests == [(
        "找墨西哥最近 7 天高流失用户并自动画像\n\n[Normalized query hints]\ncountry: mx\ntime_window: last_7_days\nquery_mode: query_profile\nauto_profile: true",
        "mx",
    )]
    assert "normalized_query" not in awaiting_evt
    assert "query_mode" not in awaiting_evt
    assert "time_window_key" not in awaiting_evt
    assert "filters_summary" not in awaiting_evt


def test_run_agent_loop_query_data_then_profile_first_turn_repair_success_visible(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_visible_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_visible_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, True)],
        ),
        allow_repair_run=True,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done")
    repair_running = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "running")
    repair_done = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "done")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    _assert_no_clarify_scope_in_visible_plan(events)
    assert [step["step_id"] for step in plan_events[-1]["steps"]] == ["query_data", "check_data", "repair_credit", "run_profile", "review_final"]
    assert events.index(query_completed) < events.index(check_data_done) < events.index(repair_running) < events.index(repair_done) < events.index(run_profile_started) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "pass"
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_query_data_then_profile_first_turn_blocked_visible(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        availability=_visible_availability_for_rows(
            [("u1", False, False, False), ("u2", False, False, False)],
        ),
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done")
    run_profile_blocked = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "run_profile" and evt.get("status") == "blocked")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    _assert_no_clarify_scope_in_visible_plan(events)
    assert events.index(query_completed) < events.index(check_data_done) < events.index(run_profile_blocked) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_query_data_then_profile_first_turn_post_repair_partial_visible(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        availability=_visible_availability_for_rows(
            [("u1", True, True, True), ("u2", True, True, False)],
        ),
        post_repair_availability=_visible_availability_for_rows(
            [("u1", True, True, True), ("u2", True, False, False)],
        ),
        allow_repair_run=True,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    repair_done = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "done")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    run_profile_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    _assert_no_clarify_scope_in_visible_plan(events)
    assert events.index(query_completed) < events.index(repair_done) < events.index(run_profile_started) < events.index(run_profile_completed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "warning"
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_query_data_then_profile_first_turn_query_failure_visible(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        preview_exception=RuntimeError("preview exploded"),
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    query_failed = next(evt for evt in events if evt["type"] == "plan_step_status" and evt.get("step_id") == "query_data" and evt.get("status") == "failed")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    _assert_no_clarify_scope_in_visible_plan(events)
    assert events.index(query_failed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_query_data_then_profile_missing_uid_output_never_starts_run_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        complete_exception=ValueError("query_data result missing uid column"),
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并自动画像", country="mx")]

    events = asyncio.run(_drive())

    tool_completed = next(
        evt
        for evt in events
        if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data"
    )
    query_failed = next(
        evt
        for evt in events
        if evt["type"] == "plan_step_status"
        and evt.get("step_id") == "query_data"
        and evt.get("status") == "failed"
    )
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert tool_completed["status"] == "error"
    assert events.index(tool_completed) < events.index(query_failed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_clarification_auto_profile_false_stops_after_query_data(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest, RequestUnderstanding
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app", "behavior"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.open_resolution",
        lambda session_id, resolution_id=None, run_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.wait_resolution",
        lambda session_id, timeout_sec=600.0: {
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            "resolution_type": "clarification",
        },
    )
    seen_query_requests: list[tuple[str, str]] = []

    def _preview(*args, **kwargs):
        seen_query_requests.append((args[1], args[2]))
        return {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _preview)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        lambda *args, **kwargs: {
            "uids": ["u1", "u2"],
            "rows_actual": 2,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        },
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("availability should not run when auto_profile=false")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when auto_profile=false")),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    awaiting_ack_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")

    assert len(plan_events) == 2
    assert plan_events[0]["execution_id"] == plan_events[1]["execution_id"]
    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "review_final"]
    assert review_evt["status"] == "pass"
    assert not review_evt["issues"]
    assert plan_events[1]["trace_id"] == query_started["trace_id"] == query_completed["trace_id"]
    assert awaiting_ack_evt["tool_call_id"] == query_started["tool_call_id"] == query_completed["tool_call_id"]
    assert query_started["input"] == {
        "request": "找墨西哥最近 7 天高流失用户并分析",
        "country": "mx",
    }
    assert seen_query_requests == [(
        "找墨西哥最近 7 天高流失用户并分析\n\n[Normalized query hints]\ncountry: mx\ntime_window: last_7_days\nquery_mode: query_only\nauto_profile: false",
        "mx",
    )]
    assert "normalized_query" not in awaiting_ack_evt
    assert "query_mode" not in awaiting_ack_evt
    assert "time_window_key" not in awaiting_ack_evt
    assert "filters_summary" not in awaiting_ack_evt
    assert "查询摘要" in awaiting_ack_evt["sql_text"]
    assert "筛选条件" in awaiting_ack_evt["sql_text"]
    assert "确认提示" in awaiting_ack_evt["sql_text"]
    assert "原始 SQL" in awaiting_ack_evt["sql_text"]
    assert "SELECT uid FROM t" in awaiting_ack_evt["sql_text"]
    assert awaiting_ack_evt["sql_text"] != "SELECT uid FROM t"
    assert "如需继续画像" in final_evt["final_message"]
    assert "UID 数量" in final_evt["final_message"]
    assert not any(any(step["step_id"] == "check_data" for step in evt["steps"]) for evt in plan_events)
    assert not any(any(step["step_id"] == "run_profile" for step in evt["steps"]) for evt in plan_events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1
    metadata = session.execution_traces[-1].internal_metadata
    assert metadata["flow_name"] == "QueryDataThenProfileFlow"
    assert metadata["flow_mode"] == "query_only"
    assert metadata["auto_profile"] is False
    assert metadata["country"] == "mx"
    assert metadata["clarification_resume"] is True
    assert metadata["cohort_size"] == 2
    assert metadata["ack_result"] == "approved"
    _assert_no_internal_trace_keys_in_events(events)


@pytest.mark.parametrize("ack_value", [False, None])
def test_run_agent_loop_clarification_auto_profile_false_non_approved_stops_after_query_ack(monkeypatch, ack_value):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest, RequestUnderstanding
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="need_clarification",
            country=None,
            uids=[],
            modules=["app", "behavior"],
            trace_days=7,
            request_summary="找一批高流失用户",
            query_request="找一批高流失用户",
            read_only=False,
            request_understanding=RequestUnderstanding(
                intent="need_clarification",
                route_label="需要补充条件",
                rewritten_goal="补充 cohort 查询条件后继续执行",
                focus=["cohort"],
                requires_tools=False,
                route_reason="当前请求明显是在找一批用户，但缺少国家或时间范围。",
                answer_mode="tool_execution",
                missing_slots=["country", "time_window"],
                clarification_prompt="请补充国家和时间范围，例如：墨西哥、最近 7 天。",
                candidate_defaults={"country": "mx", "auto_profile": True},
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.open_resolution",
        lambda session_id, resolution_id=None, run_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.resolve_bus.wait_resolution",
        lambda session_id, timeout_sec=600.0: {
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": False},
            "resolution_type": "clarification",
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request.model_copy(update={
            "intent": "query_data_then_profile",
            "country": "mx",
            "query_request": "找墨西哥最近 7 天高流失用户并分析",
        }),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {
            "child": object(),
            "sql_text": "SELECT uid FROM t",
            "rows_estimated": 5,
        },
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._complete_query_data_cohort",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("complete should not run for non-approved query-only path")),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: ack_value)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("availability should not run when auto_profile=false")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not run when auto_profile=false")),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert any(evt["type"] == "run_cancelled" for evt in events)
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)


def test_run_agent_loop_clarification_auto_profile_false_execute_failure_emits_fail_review_and_final(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_only_clarification_resume_visible(
        monkeypatch,
        complete_exception=RuntimeError("complete boom"),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")

    assert len(plan_events) == 2
    assert plan_events[0]["execution_id"] == plan_events[1]["execution_id"]
    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "review_final"]
    assert any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert query_completed["status"] == "error"
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "tool_error" for issue in review_evt["issues"])
    assert query_started["trace_id"] == query_completed["trace_id"] == plan_events[1]["trace_id"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert not any(any(step["step_id"] == "check_data" for step in evt["steps"]) for evt in plan_events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert "请调整取数条件" in final_evt["final_message"]


def test_run_agent_loop_clarification_auto_profile_false_empty_cohort_finishes_without_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_only_clarification_resume_visible(
        monkeypatch,
        complete_result={
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 5,
            "sql_text": "SELECT uid FROM t",
        },
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    assert review_evt["status"] == "pass"
    assert "没有命中用户" in final_evt["final_message"]
    assert "UID 数量：0" in final_evt["final_message"]
    assert "UID 列表：无" in final_evt["final_message"]
    assert "放宽筛选条件" in final_evt["final_message"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)


def test_run_agent_loop_clarification_auto_profile_false_large_cohort_blocks_after_query(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_only_clarification_resume_visible(
        monkeypatch,
        complete_result={
            "uids": [f"u{i:03d}" for i in range(201)],
            "rows_actual": 201,
            "rows_estimated": 201,
            "sql_text": "SELECT uid FROM t",
        },
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")

    assert query_completed["status"] == "ok"
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "cohort_too_large" for issue in review_evt["issues"])
    assert [evt["type"] for evt in events].count("final") == 1
    assert "200" in final_evt["final_message"]
    assert "缩小范围" in final_evt["final_message"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)


def test_run_agent_loop_clarification_auto_profile_false_preview_completed_without_ack_finishes(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_only_clarification_resume_visible(
        monkeypatch,
        preview_result={
            "uids": ["u1"],
            "rows_actual": 1,
            "rows_estimated": 1,
            "sql_text": "SELECT uid FROM t",
        },
        complete_exception=AssertionError("complete should not run for direct-completed preview"),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")

    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "review_final"]
    assert not any(evt["type"] == "awaiting_user_ack" for evt in events)
    assert query_completed["status"] == "ok"
    assert review_evt["status"] == "pass"
    assert "UID 数量：1" in final_evt["final_message"]
    assert [evt["type"] for evt in events].count("final") == 1
    assert not any(any(step["step_id"] == "check_data" for step in evt["steps"]) for evt in plan_events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)


def test_run_agent_loop_clarification_auto_profile_true_success_runs_query_then_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_profile_clarification_resume_visible(monkeypatch)

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    run_profile_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    check_data_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done"
    )

    assert len(plan_events) == 2
    assert plan_events[0]["execution_id"] == plan_events[1]["execution_id"]
    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "check_data", "run_profile", "review_final"]
    assert review_evt["status"] == "pass"
    assert not any(any(step["step_id"].startswith("repair_") for step in evt["steps"]) for evt in plan_events)
    assert not any(any(step["step_id"] == "data_acquisition_unavailable" for step in evt["steps"]) for evt in plan_events)
    assert events.index(query_completed) < events.index(check_data_done) < events.index(run_profile_started) < events.index(run_profile_completed) < events.index(review_evt) < events.index(final_evt)
    assert [evt["type"] for evt in events].count("final") == 1
    metadata = session.execution_traces[-1].internal_metadata
    assert metadata["flow_name"] == "QueryDataThenProfileFlow"
    assert metadata["flow_mode"] == "query_profile"
    assert metadata["auto_profile"] is True
    assert metadata["country"] == "mx"
    assert metadata["clarification_resume"] is True
    assert metadata["cohort_size"] == 2
    assert metadata["ack_result"] == "approved"
    _assert_no_internal_trace_keys_in_events(events)


def test_run_agent_loop_clarification_auto_profile_true_single_bucket_repair_runs_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid="u1",
                app=_available_bucket("u1-app.csv"),
                behavior=_available_bucket("u1-behavior.csv"),
                credit=_available_bucket("u1-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            ),
            UidAvailability(
                uid="u2",
                app=_available_bucket("u2-app.csv"),
                behavior=_available_bucket("u2-behavior.csv"),
                credit=_missing_bucket("u2-credit.csv"),
                available_buckets=["app", "behavior"],
                missing_buckets=["credit"],
            ),
        ],
    )
    post_repair_availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=_available_bucket(f"{uid}-app.csv"),
                behavior=_available_bucket(f"{uid}-behavior.csv"),
                credit=_available_bucket(f"{uid}-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            )
            for uid in ["u1", "u2"]
        ],
    )
    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        post_repair_availability=post_repair_availability,
        modules=["app", "behavior", "credit"],
        allow_repair_run=True,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done"
    )
    repair_running = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "running"
    )
    repair_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "done"
    )
    repair_ack = [
        evt for evt in events
        if evt["type"] == "awaiting_user_ack"
    ][1]
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    run_profile_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")

    assert review_evt["status"] == "pass"
    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "check_data", "repair_credit", "run_profile", "review_final"]
    assert next(step for step in plan_events[1]["steps"] if step["step_id"] == "query_data")["status"] == "done"
    assert next(step for step in plan_events[1]["steps"] if step["step_id"] == "check_data")["status"] == "done"
    assert not any(any(step["step_id"] == "data_acquisition_unavailable" for step in evt["steps"]) for evt in plan_events)
    assert events.index(query_completed) < events.index(check_data_done) < events.index(repair_running) < events.index(repair_ack) < events.index(repair_done) < events.index(run_profile_started) < events.index(run_profile_completed) < events.index(review_evt) < events.index(final_evt)
    assert [evt["type"] for evt in events].count("final") == 1
    assert final_evt["type"] == "final"


def test_run_agent_loop_clarification_auto_profile_true_repair_non_approved_emits_cancel_only(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid="u1",
                app=_available_bucket("u1-app.csv"),
                behavior=_available_bucket("u1-behavior.csv"),
                credit=_available_bucket("u1-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            ),
            UidAvailability(
                uid="u2",
                app=_available_bucket("u2-app.csv"),
                behavior=_available_bucket("u2-behavior.csv"),
                credit=_missing_bucket("u2-credit.csv"),
                available_buckets=["app", "behavior"],
                missing_buckets=["credit"],
            ),
        ],
    )
    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        modules=["app", "behavior", "credit"],
        allow_profile_run=False,
        allow_repair_run=True,
        query_ack_value=True,
        repair_ack_value=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    repair_ack = [evt for evt in events if evt["type"] == "awaiting_user_ack"][1]
    cancelled_evt = next(evt for evt in events if evt["type"] == "run_cancelled")

    assert events.index(query_completed) < events.index(repair_ack) < events.index(cancelled_evt)
    assert not any(evt["type"] == "review_result" for evt in events)
    assert not any(evt["type"] == "final" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)


def test_run_agent_loop_clarification_auto_profile_true_repair_failed_emits_fail_final(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid="u1",
                app=_available_bucket("u1-app.csv"),
                behavior=_available_bucket("u1-behavior.csv"),
                credit=_available_bucket("u1-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            ),
            UidAvailability(
                uid="u2",
                app=_available_bucket("u2-app.csv"),
                behavior=_available_bucket("u2-behavior.csv"),
                credit=_missing_bucket("u2-credit.csv"),
                available_buckets=["app", "behavior"],
                missing_buckets=["credit"],
            ),
        ],
    )
    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        modules=["app", "behavior", "credit"],
        allow_profile_run=False,
        allow_repair_run=True,
        repair_execute_exception=RuntimeError("repair exploded"),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    repair_failed = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "failed"
    )
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert events.index(query_completed) < events.index(repair_failed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "run_cancelled" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_clarification_auto_profile_true_post_repair_partial_runs_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid="u1",
                app=_available_bucket("u1-app.csv"),
                behavior=_available_bucket("u1-behavior.csv"),
                credit=_available_bucket("u1-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            ),
            UidAvailability(
                uid="u2",
                app=_available_bucket("u2-app.csv"),
                behavior=_available_bucket("u2-behavior.csv"),
                credit=_missing_bucket("u2-credit.csv"),
                available_buckets=["app", "behavior"],
                missing_buckets=["credit"],
            ),
        ],
    )
    post_repair_availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid="u1",
                app=_available_bucket("u1-app.csv"),
                behavior=_available_bucket("u1-behavior.csv"),
                credit=_available_bucket("u1-credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            ),
            UidAvailability(
                uid="u2",
                app=_available_bucket("u2-app.csv"),
                behavior=_missing_bucket("u2-behavior.csv"),
                credit=_missing_bucket("u2-credit.csv"),
                available_buckets=["app"],
                missing_buckets=["behavior", "credit"],
            ),
        ],
    )
    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        post_repair_availability=post_repair_availability,
        modules=["app", "behavior", "credit"],
        allow_repair_run=True,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    repair_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "repair_credit" and evt.get("status") == "done"
    )
    run_profile_started = next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    run_profile_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert events.index(query_completed) < events.index(repair_done) < events.index(run_profile_started) < events.index(run_profile_completed) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "warning"
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_clarification_auto_profile_true_blocked_unavailable_blocks_before_profile(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=_missing_bucket(f"{uid}-app.csv"),
                behavior=_missing_bucket(f"{uid}-behavior.csv"),
                credit=_missing_bucket(f"{uid}-credit.csv"),
                available_buckets=[],
                missing_buckets=["app", "behavior", "credit"],
            )
            for uid in ["u1", "u2"]
        ],
    )

    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done"
    )
    run_profile_blocked = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "run_profile" and evt.get("status") == "blocked"
    )
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")

    assert [step["step_id"] for step in plan_events[1]["steps"]] == ["clarify_scope", "query_data", "check_data", "run_profile", "review_final"]
    assert not any(any(step["step_id"].startswith("repair_") for step in evt["steps"]) for evt in plan_events)
    assert events.index(query_completed) < events.index(check_data_done) < events.index(run_profile_blocked) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_clarification_auto_profile_true_multi_bucket_missing_blocks_without_repair_steps(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import BucketAvailability, DataAvailability, UidAvailability

    def _available_bucket(path: str):
        return BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv:available"], source_type="csv", path=path)

    def _missing_bucket(path: str):
        return BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["csv:missing"], source_type="csv", path=path)

    availability = DataAvailability(
        country="mx",
        checked_uids=["u1", "u2"],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=_available_bucket(f"{uid}-app.csv"),
                behavior=_missing_bucket(f"{uid}-behavior.csv"),
                credit=_missing_bucket(f"{uid}-credit.csv"),
                available_buckets=["app"],
                missing_buckets=["behavior", "credit"],
            )
            for uid in ["u1", "u2"]
        ],
    )
    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        availability=availability,
        modules=["app", "behavior", "credit"],
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    query_completed = next(evt for evt in events if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    check_data_done = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "check_data" and evt.get("status") == "done"
    )
    run_profile_blocked = next(
        evt for evt in events
        if evt["type"] == "plan_step_status" and evt.get("step_id") == "run_profile" and evt.get("status") == "blocked"
    )

    assert not any(any(step["step_id"].startswith("repair_") for step in evt["steps"]) for evt in plan_events)
    assert events.index(query_completed) < events.index(check_data_done) < events.index(run_profile_blocked) < events.index(review_evt) < events.index(final_evt)
    assert review_evt["status"] == "fail"
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_clarification_auto_profile_true_empty_cohort_blocks_before_check_data(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    session = _patch_query_profile_clarification_resume_visible(
        monkeypatch,
        complete_result={
            "uids": [],
            "rows_actual": 0,
            "rows_estimated": 0,
            "sql_text": "SELECT uid FROM t",
        },
        allow_profile_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找一批高流失用户并自动画像")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    final_evt = next(evt for evt in events if evt["type"] == "final")
    assert review_evt["status"] == "fail"
    assert "没有可继续画像的 UID" in final_evt["final_message"]
    assert "不会启动画像分析" in final_evt["final_message"]
    assert not any(any(step["step_id"] == "check_data" for step in evt["steps"]) for evt in plan_events[1:])
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_query_data_then_profile_blocked_when_data_acquisition_disabled(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    monkeypatch.setenv("DATA_ACQUISITION_ENABLED", "false")
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app"],
            request_summary="查询 cohort 并画像",
            query_request="找墨西哥最近 7 天高流失用户并分析",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("query_data should not run when data acquisition is disabled")),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并分析")]

    events = asyncio.run(_drive())

    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    assert [step["step_id"] for step in plan_evt["steps"]] == ["query_data", "review_final"]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "fail"
    assert any(issue["type"] == "data_acquisition_unavailable" for issue in review_evt["issues"])
    final_evt = next(evt for evt in events if evt["type"] == "final")
    assert "未启用" in final_evt["final_message"] or "不可用" in final_evt["final_message"]
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_large_cohort_multi_bucket_blocks_without_repair_strategy(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    uids = [f"u{i:03d}" for i in range(21)]
    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        modules=["app", "behavior", "credit"],
        complete_result={
            "uids": uids,
            "rows_actual": len(uids),
            "rows_estimated": len(uids),
            "sql_text": "SELECT user_uuid FROM t",
        },
        availability=_visible_availability_for_rows(
            [(uid, True, False, False) for uid in uids],
        ),
        allow_profile_run=False,
        allow_repair_run=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并分析")]

    events = asyncio.run(_drive())

    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert not any(evt["type"] == "awaiting_resolution" for evt in events)
    assert not any(step["step_id"].startswith("repair_") for evt in plan_events for step in evt["steps"])
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    review_evt = next(evt for evt in events if evt["type"] == "review_result")
    assert review_evt["status"] == "fail"
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_medium_cohort_single_bucket_uses_repair_bridge(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop

    uids = [f"u{i:03d}" for i in range(10)]
    session = _patch_first_turn_query_profile_visible(
        monkeypatch,
        modules=["app", "behavior"],
        complete_result={
            "uids": uids,
            "rows_actual": len(uids),
            "rows_estimated": len(uids),
            "sql_text": "SELECT user_uuid FROM t",
        },
        availability=_visible_availability_for_rows(
            [(uid, True, False, True) for uid in uids],
        ),
        post_repair_availability=_visible_availability_for_rows(
            [(uid, True, True, True) for uid in uids],
        ),
        allow_repair_run=True,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="找墨西哥最近 7 天高流失用户并分析")]

    events = asyncio.run(_drive())

    assert not any(evt["type"] == "awaiting_resolution" for evt in events)
    plan_events = [evt for evt in events if evt["type"] == "execution_plan"]
    assert any(any(step["step_id"] == "repair_behavior" for step in evt["steps"]) for evt in plan_events)
    repair_ack = [evt for evt in events if evt["type"] == "awaiting_user_ack"][1]
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "repair_profile_data" for evt in events)
    assert any(evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile" for evt in events)
    assert repair_ack["type"] == "awaiting_user_ack"
    assert [evt["type"] for evt in events].count("final") == 1


def test_run_agent_loop_workspace_followup_uses_evidence_llm_without_tool_rerun(monkeypatch):
    from datetime import datetime, timezone

    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import ToolCallRecord
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"
    session = create_session(country="mx")
    session.tool_calls.append(ToolCallRecord(
        tool_name="run_profile",
        tool_call_id="tc-existing",
        input={"uids": [uid], "app_time": None, "modules": ["behavior"]},
        output={
            "results": [
                {
                    "uid": uid,
                    "module": "behavior",
                    "result": {
                        "status": "ok",
                        "data": {
                            "summary": "行为画像：近30天登录2天，流失风险高。",
                            "structured_result": {"risk_level": "high", "engagement": "low"},
                            "charts": [],
                            "report_markdown": "",
                        },
                        "error": None,
                    },
                }
            ],
            "cache_hits": 1,
            "cache_misses": 0,
        },
        status="done",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    ))

    model_calls: list[dict] = []

    class _EvidenceClient:
        last_token_usage = {"prompt": 120, "completion": 40, "total": 160}

        def generate_structured(self, **kwargs):
            model_calls.append(kwargs)
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "这是基于已有画像证据的聚焦回答：该用户近30天登录显著偏低，因此流失风险高；以下已改写为客服话术。",
                    "confidence": 0.91,
                },
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _EvidenceClient(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_profile should not rerun for workspace follow-up")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_trace",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_trace should not rerun for workspace follow-up")),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我解释为什么这个用户流失风险高，并改成客服话术")]

    events = asyncio.run(_drive())
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")

    assert model_calls, "workspace follow-up should call the evidence-constrained LLM path"
    assert plan_evt["request_understanding"]["answer_mode"] == "workspace_evidence_answer"
    assert plan_evt["request_understanding"]["requires_tools"] is False
    assert "这是基于已有画像证据的聚焦回答" in events[-1]["final_message"]
    assert "tool_started" not in [evt["type"] for evt in events]


def test_run_agent_loop_general_query_data_opens_ack_before_emitting_preview(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    call_order = []

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def __init__(self):
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "status": "ok",
                    "structured_result": {
                        "tool_call": {
                            "name": "query_data",
                            "arguments": {"request": "拉一批用户", "country": "mx"},
                        }
                    },
                }
            return {
                "status": "ok",
                "structured_result": {"final_message": "done", "confidence": 0.6},
            }

    class _FakeChild:
        def __init__(self, country):
            self.country = country

        def run_query(self, req):
            return type("QR", (), {"sql_text": "SELECT uid FROM t", "rows_estimated": 1})()

        def execute(self, sql):
            return {"uids": ["u1"], "rows_actual": 1}

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _GeneralClient(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["NormalizedRequest"]).NormalizedRequest(
            intent="general_chat",
            country="mx",
            uids=[],
            modules=[],
            request_summary="普通聊天",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.query_data._ChildAgent",
        _FakeChild,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.open_ack",
        lambda sid: call_order.append("open_ack"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.ack_bus.wait_ack",
        lambda sid, timeout_sec=600.0: (call_order.append("wait_ack") or True),
    )

    session = create_session(country="mx")

    async def _drive():
        seen = []
        async for evt in run_agent_loop(session=session, prompt="请查询一批用户"):
            if evt["type"] == "awaiting_user_ack":
                call_order.append("awaiting_user_ack")
            seen.append(evt)
        return seen

    events = asyncio.run(_drive())

    assert "awaiting_user_ack" in [evt["type"] for evt in events]
    assert call_order[:3] == ["open_ack", "awaiting_user_ack", "wait_ack"]


def test_run_agent_loop_general_query_data_ack_timeout_cancels_without_final(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def __init__(self):
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "status": "ok",
                    "structured_result": {
                        "tool_call": {
                            "name": "query_data",
                            "arguments": {"request": "拉一批用户", "country": "mx"},
                        }
                    },
                }
            return {
                "status": "ok",
                "structured_result": {"final_message": "should-not-happen", "confidence": 0.6},
            }

    class _FakeChild:
        def __init__(self, country):
            self.country = country

        def run_query(self, req):
            return type("QR", (), {"sql_text": "SELECT uid FROM t", "rows_estimated": 1})()

        def execute(self, sql):
            raise AssertionError("SQL must not execute after ACK timeout")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["NormalizedRequest"]).NormalizedRequest(
            intent="general_chat",
            country="mx",
            uids=[],
            modules=[],
            request_summary="普通聊天",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        importlib.import_module("app.services.orchestrator_agent.tools.query_data"),
        "_ChildAgent",
        _FakeChild,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: None)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请查询一批用户")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]

    assert "ack_expired" not in event_types  # lifecycle kept in run_events, not SSE
    assert "run_cancelled" in event_types
    assert "final" not in event_types
    assert session.active_run_id is None
    assert [evt.event_type for evt in session.run_events].count("run_cancelled") == 1


def test_run_agent_loop_known_request_cancel_after_query_execute_skips_output_and_final(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session import request_run_cancel
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="query_data_then_profile",
            country="mx",
            uids=[],
            modules=["app"],
            request_summary="查询 cohort 并画像",
            query_request="拉一批用户",
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.execute_query_data_cohort",
        lambda *args, **kwargs: {"child": object(), "sql_text": "SELECT uid FROM t", "rows_estimated": 1},
    )

    session = create_session(country="mx")

    async def _complete(session_arg, child, sql_text):
        request_run_cancel(session_arg.session_id, session_arg.active_run_id)
        return {"uids": ["u1"], "rows_actual": 1, "rows_estimated": 1, "sql_text": sql_text}

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._complete_query_data_cohort", _complete)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["DataAvailability"]).DataAvailability(country="mx", checked_uids=["u1"], per_uid=[]),
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我拉一批用户并分析")]

    events = asyncio.run(_drive())
    event_types = [evt["type"] for evt in events]

    assert "run_cancelled" in event_types
    assert "final" not in event_types
    assert not any(evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data" and evt.get("status") == "ok" for evt in events)
    assert [evt.event_type for evt in session.run_events].count("run_cancelled") == 1


def test_extract_reusable_profile_results_ignores_cancelled_run_artifacts():
    from app.services.orchestrator_agent.schemas import (
        ConversationTurn,
        OrchestratorMessage,
        OrchestratorSession,
        ToolCallRecord,
        TurnRunRecord,
    )
    from app.services.orchestrator_agent.visible_execution import extract_reusable_profile_results

    now = datetime.now(timezone.utc)
    session = OrchestratorSession(
        session_id="sess-cancelled-artifact",
        created_at=now,
        updated_at=now,
        turns=[
            ConversationTurn(
                turn_id="turn-1",
                session_id="sess-cancelled-artifact",
                user_message=OrchestratorMessage(role="user", content="analyze", turn_id="turn-1", run_id="run-1", timestamp=now),
                runs=[
                    TurnRunRecord(
                        run_id="run-1",
                        trace_id="trace-1",
                        status="cancelled",
                        completeness="partial",
                        started_at=now,
                        ended_at=now,
                    )
                ],
                created_at=now,
                updated_at=now,
            )
        ],
        tool_calls=[
            ToolCallRecord(
                turn_id="turn-1",
                run_id="run-1",
                trace_id="trace-1",
                tool_name="run_profile",
                tool_call_id="tc-1",
                input={"uids": ["824812551379353600"], "modules": ["behavior"]},
                output={
                    "results": [
                        {
                            "uid": "824812551379353600",
                            "module": "behavior",
                            "result": {
                                "status": "ok",
                                "data": {
                                    "summary": "不应该进入默认 evidence",
                                    "structured_result": {"risk_level": "high"},
                                },
                            },
                        }
                    ]
                },
                status="done",
                started_at=now,
                finished_at=now,
            )
        ],
    )

    reusable = extract_reusable_profile_results(session)
    assert reusable == {}


def test_run_agent_loop_read_only_followup_without_workspace_emits_blocked_trace(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    class _ShouldNotCallModelClient:
        last_token_usage = {"prompt": 0, "completion": 0, "total": 0}

        def generate_structured(self, **kwargs):
            raise AssertionError("LLM should not run when read-only follow-up has no reusable workspace")

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _ShouldNotCallModelClient(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我总结一下当前用户画像")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    review_evt = next(evt for evt in events if evt["type"] == "review_result")

    assert types[:3] == ["session_started", "turn_started", "run_started"]
    assert types[-4:] == ["plan_step_status", "plan_step_status", "review_result", "final"]
    assert review_evt["status"] == "fail"
    assert review_evt["issues"][0]["type"] == "no_workspace_context"
    assert "先分析 UID" in events[-1]["final_message"]


def test_run_agent_loop_general_chat_emits_lightweight_execution_plan(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "我是当前的画像分析助手。",
                    "confidence": 0.6,
                },
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _GeneralClient(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你是谁？")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")

    assert types[:4] == ["session_started", "turn_started", "run_started", "execution_plan"]
    assert types.count("final") == 1
    assert types[-3:] == ["plan_step_status", "run_completed", "final"]
    assert plan_evt["request_understanding"]["answer_mode"] == "general_chat"
    assert plan_evt["request_understanding"]["route_label"] == "通用 Agent 对话"
    assert plan_evt["steps"][0]["step_id"] == "general_answer"
    assert any(evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done" for evt in events)


def test_run_agent_loop_general_chat_no_tool_failure_has_no_final(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            }

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _GeneralClient(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.get_tool_registry",
        lambda: (_ for _ in ()).throw(AssertionError("get_tool_registry should not run for no-tool GeneralChatFlow")),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你是谁？")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]

    assert types[:4] == ["session_started", "turn_started", "run_started", "execution_plan"]
    assert "run_failed" in types
    assert "error" in types
    assert "final" not in types
    assert "tool_started" not in types
    assert any(evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "failed" for evt in events)


def test_run_agent_loop_general_chat_memory_write_visible_success(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.loop_context import MemoryFacade
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def __init__(self):
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "memory_write",
                        "arguments": {
                            "key": "user_output_preference",
                            "value": "请记住：我偏好中文输出。",
                        },
                    },
                },
            }

    client = _GeneralClient()
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: client)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="写入记忆",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=lambda input_obj: {"ok": True, "path": "/tmp/memory.sqlite3"}),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请记住：我偏好中文输出。")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    tool_started_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_started" and evt.get("tool_name") == "memory_write")
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_write")
    done_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done")
    run_completed_index = types.index("run_completed")
    final_index = types.index("final")

    assert tool_started_index < tool_completed_index < done_index < run_completed_index < final_index
    assert client.calls == 1
    assert events[-1]["final_message"] == "已记住。"


def test_run_agent_loop_general_chat_memory_read_visible_success(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.loop_context import MemoryFacade
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "memory_read",
                    "arguments": {"key_pattern": "output_preference"},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "我记得你偏好中文输出。", "confidence": 0.83},
        },
    ])

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def __init__(self):
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            return next(decisions)

    client = _GeneralClient()
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: client)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="读取记忆",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop._build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(read=lambda input_obj: {"items": [{"content": "用户偏好中文输出"}]}),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你还记得我之前的输出偏好吗？")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    tool_started_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_started" and evt.get("tool_name") == "memory_read")
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "memory_read")
    done_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done")
    run_completed_index = types.index("run_completed")
    final_index = types.index("final")

    assert tool_started_index < tool_completed_index < done_index < run_completed_index < final_index
    assert client.calls == 2
    assert events[-1]["final_message"] == "我记得你偏好中文输出。"


def test_run_agent_loop_general_chat_run_trace_tool_loop_visible_success(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "轨迹分析完成。", "confidence": 0.82},
        },
    ])

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_trace(input_data):
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uid": input_data.uid,
                "status": "ok",
                "events": [],
                "summary": {},
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: {"run_trace": _fake_run_trace})

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你好，先帮我查轨迹")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    tool_started_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_started" and evt.get("tool_name") == "run_trace")
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_trace")
    done_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done")
    run_completed_index = types.index("run_completed")
    final_index = types.index("final")

    assert [step["step_id"] for step in plan_evt["steps"]] == ["general_answer"]
    assert tool_started_index < tool_completed_index < done_index < run_completed_index < final_index
    assert types.count("final") == 1


def test_run_agent_loop_general_chat_run_trace_tool_loop_visible_failure(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {"name": "run_trace", "arguments": {"uid": "824812551379353600", "days": 7}},
                },
            }

    def _boom(input_data):
        raise RuntimeError("trace failed")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="查轨迹",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", lambda: {"run_trace": _boom})

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="你好，先帮我查轨迹")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_trace")
    failed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "failed")
    run_failed_index = types.index("run_failed")
    error_index = types.index("error")
    tool_completed = events[tool_completed_index]

    assert tool_completed["status"] == "error"
    assert tool_completed_index < failed_index < run_failed_index < error_index
    assert "final" not in types


def test_run_agent_loop_general_chat_query_data_tool_loop_visible_success(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "query_data",
                    "arguments": {"request": "筛选最近 7 天高风险用户", "country": "mx"},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "已完成筛选。", "confidence": 0.8},
        },
    ])

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    child = object()

    async def _preview(session_arg, request_text, country):
        return {"child": child, "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(session_arg, child_arg, sql_text):
        return {
            "uids": ["UID_A", "UID_B"],
            "rows_actual": 2,
            "sql_text": sql_text,
            "rows_estimated": 2,
        }

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _preview)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._complete_query_data_cohort", _complete)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我筛选最近 7 天高风险用户列表")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    tool_started_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data")
    awaiting_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "awaiting_user_ack")
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    done_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done")
    run_completed_index = types.index("run_completed")
    final_index = types.index("final")
    awaiting_evt = next(evt for evt in events if evt["type"] == "awaiting_user_ack")

    assert [step["step_id"] for step in plan_evt["steps"]] == ["general_answer"]
    assert tool_started_index < awaiting_index < tool_completed_index < done_index < run_completed_index < final_index
    assert types.count("final") == 1
    assert next(evt for evt in events if evt["type"] == "tool_started" and evt.get("tool_name") == "query_data")["input"] == {
        "request": "筛选最近 7 天高风险用户",
        "country": "mx",
    }
    assert "normalized_query" not in awaiting_evt
    assert "query_mode" not in awaiting_evt
    assert "time_window_key" not in awaiting_evt
    assert "filters_summary" not in awaiting_evt


def test_run_agent_loop_general_chat_query_data_tool_loop_visible_failure(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选最近 7 天高风险用户", "country": "mx"},
                    },
                },
            }

    async def _preview(session_arg, request_text, country):
        return {"child": object(), "sql_text": "select uid from users", "rows_estimated": 2}

    async def _complete(session_arg, child_arg, sql_text):
        raise RuntimeError("query failed")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _preview)
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop._complete_query_data_cohort", _complete)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda *args, **kwargs: True)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我筛选最近 7 天高风险用户列表")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "query_data")
    failed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "failed")
    run_failed_index = types.index("run_failed")
    error_index = types.index("error")
    tool_completed = events[tool_completed_index]

    assert tool_completed["status"] == "error"
    assert tool_completed_index < failed_index < run_failed_index < error_index
    assert "final" not in types


def test_run_agent_loop_general_chat_query_data_requires_view_sql_and_execute_permissions(monkeypatch):
    from app.core.user_context import ProjectAccessScope, UserContext
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "query_data",
                        "arguments": {"request": "筛选最近 7 天高风险用户", "country": "mx"},
                    },
                },
            }

    async def _preview(*_args, **_kwargs):
        raise AssertionError("query_data preview must be blocked before permission passes")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选用户列表",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.execute_query_data_cohort", _preview)

    session = create_session(country="mx", user_id="12", project_id="1")
    user_context = UserContext(
        user_id="12",
        username="analyst",
        email="analyst@example.com",
        display_name="Analyst",
        roles=("analyst",),
        permissions=("profile:run", "data:query:generate"),
        project_id="1",
        project_code="maps_lz",
        country="mx",
        project_scopes=(ProjectAccessScope(project_id="1", project_code="maps_lz", access_level="member", country="mx"),),
        is_superuser=False,
    )

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我筛选最近 7 天高风险用户列表", user_context=user_context)]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    messages = [evt.get("message", "") for evt in events if isinstance(evt, dict)]

    assert not any(evt["type"] == "tool_started" and evt.get("tool_name") == "query_data" for evt in events)
    assert "awaiting_user_ack" not in types
    assert "run_failed" in types
    assert any("data:query:view_sql" in message or "data:query:execute" in message for message in messages)


def test_run_agent_loop_general_chat_run_profile_tool_loop_visible_success(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    decisions = iter([
        {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "run_profile",
                    "arguments": {"uids": ["824812551379353600"], "modules": ["app"]},
                },
            },
        },
        {
            "status": "ok",
            "structured_result": {"final_message": "画像完成。", "confidence": 0.82},
        },
    ])

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    def _fake_run_profile(input_data, progress_callback=None):
        if progress_callback is not None:
            progress_callback({
                "progress_type": "profile_module_completed",
                "uid": input_data.uids[0],
                "module": "app",
                "status": "ok",
                "completed": 1,
                "total": 1,
            })
        return {"results": [], "cache_hits": 0, "cache_misses": 1}

    def _fail_registry():
        raise AssertionError("run_profile GeneralChatFlow path must not call get_tool_registry")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.get_tool_registry", _fail_registry)
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请执行这个用户的画像分析")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    plan_evt = next(evt for evt in events if evt["type"] == "execution_plan")
    tool_started_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_started" and evt.get("tool_name") == "run_profile")
    tool_progress_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_progress" and evt.get("tool_name") == "run_profile")
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    done_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "done")
    run_completed_index = types.index("run_completed")
    final_index = types.index("final")

    assert [step["step_id"] for step in plan_evt["steps"]] == ["general_answer"]
    assert tool_started_index < tool_progress_index < tool_completed_index < done_index < run_completed_index < final_index
    assert types.count("final") == 1


def test_run_agent_loop_general_chat_run_profile_tool_loop_visible_failure(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "tool_call": {
                        "name": "run_profile",
                        "arguments": {"uids": ["824812551379353600"], "modules": ["app"]},
                    },
                },
            }

    def _boom(input_data, progress_callback=None):
        raise RuntimeError("profile failed")

    monkeypatch.setattr("app.services.orchestrator_agent.agent_loop.ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="执行用户画像",
            request_understanding=None,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.refine_normalized_request",
        lambda client, prompt, session, normalized_request: normalized_request,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _boom)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请执行这个用户的画像分析")]

    events = asyncio.run(_drive())
    types = [evt["type"] for evt in events]
    tool_completed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "tool_completed" and evt.get("tool_name") == "run_profile")
    failed_index = next(idx for idx, evt in enumerate(events) if evt["type"] == "plan_step_status" and evt["step_id"] == "general_answer" and evt["status"] == "failed")
    run_failed_index = types.index("run_failed")
    error_index = types.index("error")
    tool_completed = events[tool_completed_index]

    assert tool_completed["status"] == "error"
    assert tool_completed_index < failed_index < run_failed_index < error_index
    assert "final" not in types


def test_run_agent_loop_general_run_profile_forces_strict_mode(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    seen_inputs = []

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def __init__(self):
            self.calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "status": "ok",
                    "structured_result": {
                        "tool_call": {
                            "name": "run_profile",
                            "arguments": {
                                "uids": ["824812551379353600"],
                                "app_time": None,
                                "modules": ["app"],
                            },
                        }
                    },
                }
            return {
                "status": "ok",
                "structured_result": {"final_message": "done", "confidence": 0.6},
            }

    def _fake_run_profile(inp, progress_callback=None):
        seen_inputs.append(inp.model_dump(mode="json"))
        return type("X", (), {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 1}})()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _GeneralClient(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["NormalizedRequest"]).NormalizedRequest(
            intent="general_chat",
            country="mx",
            uids=[],
            modules=[],
            request_summary="普通聊天",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="请执行画像")]

    asyncio.run(_drive())

    assert seen_inputs[0]["strict_data_mode"] is True


def test_run_agent_loop_trace_uses_requested_days(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    seen_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )

    def _fake_run_trace(input_data):
        seen_inputs.append(input_data.model_dump(mode="json"))
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "uid": input_data.uid,
                "status": "ok",
                "events": [],
                "summary": {},
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_trace", _fake_run_trace)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我分析 UID 824812551379353600 最近 30 天轨迹")]

    asyncio.run(_drive())
    assert seen_inputs == [{"uid": "824812551379353600", "days": 30}]


def test_run_agent_loop_profile_uses_workspace_application_time(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"
    seen_inputs = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app"],
            request_summary=f"分析 UID {uid} 的 app 画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
    )

    def _fake_run_profile(inp, progress_callback=None):
        seen_inputs.append(inp.model_dump(mode="json"))
        return type("X", (), {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 1}})()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")
    session.active_entities["workspace_snapshot"] = {"applicationTime": "2026-05-15T12:30"}

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析{uid}这个用户的app画像")]

    asyncio.run(_drive())
    assert seen_inputs[0]["app_time"] == "2026-05-15T12:30"


def test_run_agent_loop_tool_record_does_not_expose_uid_modules(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app"],
            request_summary=f"分析 UID {uid} 的 app 画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": 1}})(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我分析{uid}这个用户的app画像")]

    asyncio.run(_drive())

    run_profile_record = next(record for record in session.tool_calls if record.tool_name == "run_profile")
    assert "uid_modules" not in run_profile_record.input


def test_run_agent_loop_only_runs_requested_app_module(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"
    seen_modules = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app"],
            request_summary=f"分析 UID {uid} 的 app 画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    )

    def _fake_run_profile(inp, progress_callback=None):
        seen_modules.append(list(inp.modules or []))
        return type("X", (), {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])}})()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"只分析这个 UID {uid} 的 App画像")]

    asyncio.run(_drive())
    assert seen_modules == [["app"]]


def test_run_agent_loop_only_runs_requested_product_dependency_chain(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    uid = "824812551379353600"
    seen_modules = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["product"],
            request_summary=f"分析 UID {uid} 的产品策略",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                UidAvailability(
                    uid=uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior.csv"),
                    credit=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/credit.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                )
            ],
        ),
    )

    def _fake_run_profile(inp, progress_callback=None):
        seen_modules.append(list(inp.modules or []))
        return type("X", (), {"model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])}})()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt=f"帮我给 UID {uid} 生成产品策略")]

    asyncio.run(_drive())
    assert seen_modules == [["app", "behavior", "credit", "comprehensive", "product"]]


def test_requirements_include_tenacity():
    from pathlib import Path

    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert "tenacity" in requirements


def test_run_agent_loop_mixed_batch_runs_per_uid_module_plan(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    full_uid = "824812551379353600"
    partial_uid = "824812551379353601"
    seen_calls = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[full_uid, partial_uid],
            modules=[],
            request_summary="批量分析 2 个 UID",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: DataAvailability(
            country="mx",
            checked_uids=[full_uid, partial_uid],
            per_uid=[
                UidAvailability(
                    uid=full_uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app1.csv"),
                    behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior1.csv"),
                    credit=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/credit1.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=partial_uid,
                    app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app2.csv"),
                    behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                ),
            ],
        ),
    )
    _patch_disabled_data_acquisition(monkeypatch)

    def _fake_run_profile(inp, progress_callback=None):
        seen_calls.append({"uids": list(inp.uids), "modules": list(inp.modules or [])})
        return type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [],
                "cache_hits": 0,
                "cache_misses": len(inp.uids) * len(inp.modules or []),
            },
        })()

    monkeypatch.setattr("app.services.orchestrator_agent.tools.run_profile", _fake_run_profile)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("repair disabled")),
        raising=False,
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我批量分析两个 UID")]

    asyncio.run(_drive())
    assert seen_calls == [
        {"uids": [full_uid], "modules": ["app", "behavior", "credit", "comprehensive", "product", "ops"]},
        {"uids": [partial_uid], "modules": ["app"]},
    ]


def test_build_profile_review_flags_module_errors_and_degraded_outputs():
    from app.services.orchestrator_agent.review_rules import build_profile_review
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )

    uid = "824812551379353600"
    availability = DataAvailability(
        country="mx",
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                behavior=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/behavior.csv"),
                credit=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/credit.csv"),
                available_buckets=["app", "behavior", "credit"],
                missing_buckets=[],
            )
        ],
    )
    profile_output = {
        "results": [
            {
                "uid": uid,
                "module": "app",
                "result": {
                    "status": "ok",
                    "data": {
                        "summary": "",
                        "structured_result": {},
                        "model_trace": {"used_llm": False, "fallback_reason": "model_unavailable"},
                    },
                    "error": None,
                },
            },
            {
                "uid": uid,
                "module": "behavior",
                "result": {
                    "status": "error",
                    "data": None,
                    "error": "boom",
                },
            },
        ],
    }
    normalized_request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app", "behavior"],
        request_summary="分析 UID 画像",
        query_request=None,
        read_only=False,
    )

    review = build_profile_review(
        availability,
        {uid: ["app", "behavior"]},
        profile_output,
        normalized_request,
    )

    issue_types = {issue["type"] for issue in review.issues}
    assert review.status == "fail"
    assert "module_error" in issue_types
    assert "empty_summary" in issue_types
    assert "missing_structured_result" in issue_types
    assert "degraded_model_output" in issue_types


def test_build_profile_review_passes_when_single_requested_module_is_satisfied():
    from app.services.orchestrator_agent.review_rules import build_profile_review
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )

    uid = "824812551379353600"
    availability = DataAvailability(
        country="mx",
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                credit=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                available_buckets=["app"],
                missing_buckets=["behavior", "credit"],
            )
        ],
    )
    profile_output = {
        "results": [
            {
                "uid": uid,
                "module": "app",
                "result": {
                    "status": "ok",
                    "data": {
                        "summary": "app ok",
                        "structured_result": {"segment": "A"},
                    },
                    "error": None,
                },
            }
        ],
    }
    normalized_request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app"],
        request_summary="只分析 App 画像",
        query_request=None,
        read_only=False,
    )

    review = build_profile_review(
        availability,
        {uid: ["app"]},
        profile_output,
        normalized_request,
    )

    assert review.status == "pass"
    assert review.issues == []


def test_build_profile_review_ignores_weak_non_requested_bucket():
    from app.services.orchestrator_agent.review_rules import build_profile_review
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        UidAvailability,
    )

    uid = "824812551379353600"
    availability = DataAvailability(
        country="mx",
        checked_uids=[uid],
        per_uid=[
            UidAvailability(
                uid=uid,
                app=BucketAvailability(status="available", available=True, usable_for_profile=True, checked_sources=["csv"], source_type="csv", path="/tmp/app.csv"),
                behavior=BucketAvailability(status="missing", available=False, usable_for_profile=False, checked_sources=["missing"], source_type="missing", path=None),
                credit=BucketAvailability(
                    status="available",
                    available=True,
                    usable_for_profile=True,
                    checked_sources=["csv"],
                    source_type="csv",
                    source_shape="summary",
                    path="/tmp/credit.csv",
                    weak_reasons=["legacy_credit_summary_fallback"],
                    quality_score=0.8,
                ),
                available_buckets=["app", "credit"],
                missing_buckets=["behavior"],
            )
        ],
    )
    profile_output = {
        "results": [
            {
                "uid": uid,
                "module": "app",
                "result": {
                    "status": "ok",
                    "data": {
                        "summary": "app ok",
                        "structured_result": {"segment": "A"},
                    },
                    "error": None,
                },
            }
        ],
    }
    normalized_request = NormalizedRequest(
        intent="profile_uid",
        country="mx",
        uids=[uid],
        modules=["app"],
        request_summary="只分析 App 画像",
        query_request=None,
        read_only=False,
    )

    review = build_profile_review(
        availability,
        {uid: ["app"]},
        profile_output,
        normalized_request,
    )

    assert review.status == "pass"
    assert review.issues == []


def test_run_agent_loop_repairs_only_missing_uids_for_bucket(monkeypatch):
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.schemas import (
        BucketAvailability,
        DataAvailability,
        NormalizedRequest,
        RepairProfileDataOutput,
        UidAvailability,
    )
    from app.services.orchestrator_agent.session_store import create_session

    _patch_enabled_data_acquisition(monkeypatch)

    missing_uid = "824812551379353600"
    complete_uid = "824812551379353601"
    availability_seq = iter([
        DataAvailability(
            country="mx",
            checked_uids=[missing_uid, complete_uid],
            per_uid=[
                UidAvailability(
                    uid=missing_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app1.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior1.csv"),
                    credit=BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app", "behavior"],
                    missing_buckets=["credit"],
                ),
                UidAvailability(
                    uid=complete_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app2.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior2.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit2.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
            ],
        ),
        DataAvailability(
            country="mx",
            checked_uids=[missing_uid, complete_uid],
            per_uid=[
                UidAvailability(
                    uid=missing_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app1.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior1.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit1.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
                UidAvailability(
                    uid=complete_uid,
                    app=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app2.csv"),
                    behavior=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/behavior2.csv"),
                    credit=BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/credit2.csv"),
                    available_buckets=["app", "behavior", "credit"],
                    missing_buckets=[],
                ),
            ],
        ),
    ])
    repair_calls: list[list[str]] = []

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="profile_batch",
            country="mx",
            uids=[missing_uid, complete_uid],
            modules=["app", "behavior", "credit", "comprehensive", "product", "ops"],
            request_summary="批量分析 2 个 UID",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: next(availability_seq),
    )

    def _fake_repair(input_data, *, session_id: str, tool_call_id: str, before_ack=None):
        repair_calls.append(list(input_data.uids))
        if before_ack:
            before_ack("SELECT uid FROM bureau", 1)
        return RepairProfileDataOutput(
            bucket="credit",
            requested_uids=list(input_data.uids),
            written_uids=list(input_data.uids),
            filenames=[f"{uid}.csv" for uid in input_data.uids],
            sql_text="SELECT uid FROM bureau",
            rows_estimated=1,
            rows_actual=len(input_data.uids),
        )

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.repair_profile_data",
        _fake_repair,
        raising=False,
    )
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.open_ack", lambda sid: None)
    monkeypatch.setattr("app.services.orchestrator_agent.ack_bus.wait_ack", lambda sid, timeout_sec=600.0: True)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {"results": [], "cache_hits": 0, "cache_misses": len(inp.modules or [])},
        })(),
    )

    session = create_session(country="mx")

    async def _drive():
        return [evt async for evt in run_agent_loop(session=session, prompt="帮我批量分析这两个 UID")]

    asyncio.run(_drive())
    assert repair_calls == [[missing_uid]]
