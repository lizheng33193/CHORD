from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest


def _build_trace():
    from app.services.orchestrator_agent.schemas import ExecutionTraceRecord

    now = datetime.now(timezone.utc)
    return ExecutionTraceRecord(
        execution_id="trace-1",
        trace_id="trace-1",
        prompt="你是谁？",
        request_summary="通用问答",
        intent="general_chat",
        created_at=now,
        updated_at=now,
    )


def test_update_internal_trace_metadata_merges_values() -> None:
    from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata

    trace = _build_trace()

    update_internal_trace_metadata(trace, {"flow_name": "GeneralChatFlow", "tool_name": "query_data"})
    update_internal_trace_metadata(trace, {"terminal_reason": "tool_error"})

    assert trace.internal_metadata == {
        "flow_name": "GeneralChatFlow",
        "tool_name": "query_data",
        "terminal_reason": "tool_error",
    }


def test_update_internal_trace_metadata_ignores_none_and_invalid_values() -> None:
    from app.services.orchestrator_agent.runtime.trace_metadata import update_internal_trace_metadata

    trace = _build_trace()

    update_internal_trace_metadata(None, {"flow_name": "ignored"})
    update_internal_trace_metadata(trace, None)
    update_internal_trace_metadata(trace, ["not", "a", "mapping"])

    assert trace.internal_metadata == {}


@pytest.mark.timeout(3)
def test_general_chat_internal_metadata_persists_and_public_session_hides_it(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_MODE", "mock")

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.orchestrator_agent import agent_loop
    from app.services.orchestrator_agent.session_store import create_session, get_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return {
                "status": "ok",
                "structured_result": {
                    "final_message": "我是当前的画像分析助手。",
                    "confidence": 0.7,
                },
            }

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _GeneralClient())

    session = create_session(country="mx")

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "你是谁？", country="mx")]

    asyncio.run(collect())

    reloaded = get_session(session.session_id)
    assert reloaded is not None
    trace = reloaded.execution_traces[-1]
    assert trace.internal_metadata["flow_name"] == "GeneralChatFlow"
    assert trace.internal_metadata["flow_mode"] == "no_tool"

    client = TestClient(app)
    payload = client.get(f"/api/orchestrator/sessions/{session.session_id}").json()
    assert payload["execution_traces"]
    assert "internal_metadata" not in payload["execution_traces"][-1]


@pytest.mark.timeout(3)
def test_general_chat_memory_write_records_internal_tool_metadata(monkeypatch) -> None:
    from app.services.orchestrator_agent import agent_loop
    from app.services.orchestrator_agent.loop_context import MemoryFacade
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
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

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="写入记忆",
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(
        agent_loop,
        "_build_memory_facade",
        lambda *args, **kwargs: MemoryFacade(write=lambda input_obj: {"ok": True, "path": "/tmp/memory.sqlite3"}),
    )

    session = create_session(country="mx")

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "请记住：我偏好中文输出。", country="mx")]

    asyncio.run(collect())
    trace = session.execution_traces[-1]

    assert trace.internal_metadata["flow_name"] == "GeneralChatFlow"
    assert trace.internal_metadata["flow_mode"] == "memory_tool_loop"
    assert trace.internal_metadata["tool_name"] == "memory_write"
    assert trace.internal_metadata["memory_operation"] == "write"


@pytest.mark.timeout(3)
def test_general_chat_query_data_continuation_second_tool_records_terminal_reason(monkeypatch) -> None:
    from app.services.orchestrator_agent import agent_loop
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
            "structured_result": {
                "tool_call": {
                    "name": "run_trace",
                    "arguments": {"uid": "u1", "days": 7},
                },
            },
        },
    ])

    class _GeneralClient:
        last_token_usage = {"prompt": 80, "completion": 20, "total": 100}

        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _GeneralClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="筛选高风险用户",
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)
    monkeypatch.setattr(
        agent_loop,
        "execute_query_data_cohort",
        lambda *args, **kwargs: {
            "uids": ["u1"],
            "rows_actual": 1,
            "rows_estimated": 1,
            "sql_text": "SELECT uid FROM t",
        },
    )

    session = create_session(country="mx")

    async def collect():
        return [evt async for evt in agent_loop.run_agent_loop(session, "帮我筛选最近 7 天高风险用户", country="mx")]

    asyncio.run(collect())
    trace = session.execution_traces[-1]

    assert trace.internal_metadata["flow_name"] == "GeneralChatFlow"
    assert trace.internal_metadata["flow_mode"] == "query_data_tool_loop"
    assert trace.internal_metadata["tool_name"] == "query_data"
    assert trace.internal_metadata["terminal_reason"] == "continuation_second_tool_call"


@pytest.mark.timeout(3)
def test_general_chat_defensive_fallback_records_internal_metadata(monkeypatch) -> None:
    from app.services.orchestrator_agent import agent_loop
    from app.services.orchestrator_agent.schemas import NormalizedRequest
    from app.services.orchestrator_agent.session_store import create_session

    class _NoLlmClient:
        last_token_usage = {"prompt": 0, "completion": 0, "total": 0}

        def generate_structured(self, **kwargs):
            raise AssertionError("defensive fallback should not call the general-chat LLM")

    monkeypatch.setattr(agent_loop, "ModelClient", lambda: _NoLlmClient())
    monkeypatch.setattr(
        agent_loop,
        "normalize_request",
        lambda prompt, session, detected_country=None: NormalizedRequest(
            intent="general_chat",
            country="mx",
            request_summary="复杂 general chat 复合请求",
        ),
    )
    monkeypatch.setattr(agent_loop, "refine_normalized_request", lambda client, prompt, session, normalized_request: normalized_request)

    session = create_session(country="mx")

    async def collect():
        return [
            evt
            async for evt in agent_loop.run_agent_loop(
                session,
                "帮我先筛选高风险用户，再顺便分析这个用户画像",
                country="mx",
            )
        ]

    asyncio.run(collect())
    trace = session.execution_traces[-1]

    assert trace.internal_metadata == {
        "flow_name": "GeneralChatFlow",
        "flow_mode": "defensive_fallback",
        "fallback_reason": "unsupported_general_chat_complex_path",
        "terminal_reason": "unsupported_general_chat_complex_path",
    }
