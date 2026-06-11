"""Phase 1 RED contract tests — must fail before implementation lands.

Covers:
- Pydantic schemas validation
- 6-tool registry shape
- load_skill / assemble_system_prompt path resolution
- session.py ACK gateway + per-session query_cancelled flag
"""

from __future__ import annotations

import pytest

from app.services.orchestrator_agent.schemas import (
    OrchestratorChatRequest, ParseUidFileInput, RunProfileInput,
    RunTraceInput, RunTraceOutput, QueryDataInput,
    MemoryWriteInput, MemoryReadInput,
    OrchestratorSession,
)
from app.services.orchestrator_agent.tools import get_tool_registry
from app.services.orchestrator_agent.skills_loader import load_skill
from app.services.orchestrator_agent.system_prompt import (
    get_system_prompt_v1, assemble_system_prompt,
)
from app.services.orchestrator_agent.session import (
    is_query_cancelled, mark_query_cancelled, reset_query_cancelled,
)


# ---- Schemas ----

def test_chat_request_validates_min_length():
    with pytest.raises(ValueError):
        OrchestratorChatRequest(prompt="")


def test_chat_request_max_length():
    with pytest.raises(ValueError):
        OrchestratorChatRequest(prompt="a" * 4001)


def test_run_profile_input_validates_uids_min():
    with pytest.raises(ValueError):
        RunProfileInput(uids=[], app_time="2026-04-30", modules=["app"])


def test_run_profile_input_validates_uids_max():
    with pytest.raises(ValueError):
        RunProfileInput(uids=["a"] * 201, app_time="2026-04-30", modules=["app"])


def test_run_profile_input_app_time_optional():
    req = RunProfileInput(uids=["u1"], modules=["app"])
    assert req.app_time is None


def test_run_trace_input_days_range():
    with pytest.raises(ValueError):
        RunTraceInput(uid="MX0001", days=0)
    with pytest.raises(ValueError):
        RunTraceInput(uid="MX0001", days=91)


def test_run_trace_output_preserves_dashboard_payload():
    out = RunTraceOutput(
        uid="MX0001",
        status="ok",
        event_window={"start": "s", "end": "e", "total_events": 3, "analyzed_events": 3},
        path_graph={"top_pages": [], "top_transitions": []},
    )
    dumped = out.model_dump(mode="json")
    assert dumped["event_window"]["total_events"] == 3
    assert dumped["path_graph"]["top_pages"] == []


def test_query_data_input_country_literal():
    # mexico 短码 mx 合法
    req = QueryDataInput(request="拉一批用户", country="mx")
    assert req.country == "mx"
    # 非 6 国之一（如 "us"）应当 Pydantic 拒绝
    with pytest.raises(ValueError):
        QueryDataInput(request="x", country="us")


def test_memory_write_key_pattern():
    with pytest.raises(ValueError):
        MemoryWriteInput(key="bad key with space", value="v")


def test_session_default_status_active():
    from datetime import datetime, timezone
    s = OrchestratorSession(
        session_id="abc", created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert s.status == "active"
    assert s.query_cancelled is False
    assert s.consecutive_failures == 0


# ---- Tools registry ----

def test_tool_registry_has_six_entries():
    reg = get_tool_registry()
    assert set(reg.keys()) == {
        "parse_uid_file", "run_profile", "run_trace",
        "query_data", "memory_write", "memory_read",
    }
    assert len(reg) == 6


# ---- Skills loader ----

def test_load_skill_unsupported_country():
    with pytest.raises(ValueError):
        load_skill("us")
    with pytest.raises(ValueError):
        load_skill("")


def test_load_skill_th_returns_content():
    content = load_skill("th")
    assert "泰国" in content or "th" in content.lower()
    assert "数据源" in content
    assert "UID 规范" in content


def test_load_skill_mx_returns_content():
    content = load_skill("mx")
    assert "墨西哥" in content or "mx" in content.lower()
    assert "MXN" in content


def test_load_skill_all_six_countries_exist():
    for c in ["th", "mx", "co", "pe", "cl", "br"]:
        content = load_skill(c)
        assert len(content) > 200, f"{c}.md too short, expected ≥ 200 chars"


# ---- System Prompt ----

def test_get_system_prompt_v1_loads():
    prompt = get_system_prompt_v1()
    assert "Orchestrator Agent" in prompt
    assert "parse_uid_file" in prompt
    assert "query_data" in prompt


def test_system_prompt_disambiguates_profile_and_trace():
    prompt = get_system_prompt_v1()
    assert '分析这个用户' in prompt
    assert 'modules=["app","behavior","credit","comprehensive","product","ops"]' in prompt
    assert "run_trace is not a substitute for run_profile" in prompt
    assert "Do not repeat an identical tool call" in prompt


def test_assemble_system_prompt_includes_country_section():
    prompt = assemble_system_prompt("th")
    assert "国别规则" in prompt
    assert "th" in prompt.lower()


def test_assemble_system_prompt_default_no_country_section():
    """R7 P0-3：country=None 时 base prompt 不包含“国别规则”段，
    防 Knowledge 层被错误注入。"""
    prompt = assemble_system_prompt(None)
    assert "国别规则" not in prompt


# ---- Session ACK gateway + query_cancelled ----

def test_query_cancelled_default_false():
    reset_query_cancelled("test-session-1")
    assert is_query_cancelled("test-session-1") is False


def test_mark_and_reset_query_cancelled():
    sid = "test-session-2"
    reset_query_cancelled(sid)
    mark_query_cancelled(sid)
    assert is_query_cancelled(sid) is True
    reset_query_cancelled(sid)
    assert is_query_cancelled(sid) is False


def test_query_cancelled_per_session_isolated():
    reset_query_cancelled("sess-A")
    reset_query_cancelled("sess-B")
    mark_query_cancelled("sess-A")
    assert is_query_cancelled("sess-A") is True
    assert is_query_cancelled("sess-B") is False
