from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.services.orchestrator_agent.agent_loop import run_agent_loop
from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.schemas import OrchestratorSession


class _FakeModelClient:
    last_token_usage = {"total": 0}

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_structured(self, **kwargs):
        self.prompts.append(kwargs["prompt"])
        return {
            "status": "ok",
            "structured_result": {
                "final_message": "已完成",
                "confidence": 0.9,
            },
        }


class _FakeMemoryWriteModelClient:
    last_token_usage = {"total": 0}

    def generate_structured(self, **kwargs):
        return {
            "status": "ok",
            "structured_result": {
                "tool_call": {
                    "name": "memory_write",
                    "arguments": {
                        "key": "user_output_preference",
                        "value": "请记住：我偏好中文输出，并且回答要简洁。",
                    },
                }
            },
        }


def _session(session_id: str, user_id: str) -> OrchestratorSession:
    now = datetime.now(timezone.utc)
    return OrchestratorSession(
        session_id=session_id,
        created_at=now,
        updated_at=now,
        user_id=user_id,
        project_id="p1",
        country="mx",
    )


def _seed_memory(user_id: str, content: str) -> None:
    decision = build_memory_record(
        content=content,
        category="preference",
        user_id=user_id,
        project_id="p1",
        country="mx",
    )
    assert decision.accepted and decision.record
    SQLiteMemoryStore().add(decision.record)


def _run(session: OrchestratorSession, monkeypatch, user_id: str = "u1"):
    fake = _FakeModelClient()
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: fake,
    )

    async def collect():
        return [
            evt
            async for evt in run_agent_loop(
                session=session,
                prompt="mx 中文输出",
                user_id=user_id,
                project_id="p1",
                country="mx",
            )
        ]

    events = asyncio.run(collect())
    return fake, events


@pytest.mark.timeout(3)
def test_agent_loop_injects_same_user_cross_session_memory(monkeypatch):
    _seed_memory("u1", "用户偏好中文输出")
    session = _session("new_session", "u1")

    fake, events = _run(session, monkeypatch, user_id="u1")

    assert events[-1]["type"] == "final"
    assert "## Retrieved Memories" in fake.prompts[0]
    assert "用户偏好中文输出" in fake.prompts[0]


@pytest.mark.timeout(3)
def test_agent_loop_does_not_inject_other_user_memory(monkeypatch):
    _seed_memory("u1", "用户偏好中文输出")
    session = _session("new_session_other", "u2")

    fake, _events = _run(session, monkeypatch, user_id="u2")

    assert "用户偏好中文输出" not in fake.prompts[0]


@pytest.mark.timeout(3)
def test_agent_loop_memory_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LONG_TERM_MEMORY_ENABLED", "0")
    _seed_memory("u1", "用户偏好中文输出")
    session = _session("disabled_session", "u1")

    fake, _events = _run(session, monkeypatch, user_id="u1")

    assert "## Retrieved Memories" not in fake.prompts[0]


@pytest.mark.timeout(3)
def test_agent_loop_short_circuits_successful_memory_write(monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _FakeMemoryWriteModelClient(),
    )
    session = _session("memory_write_short_circuit", "u1")

    async def collect():
        return [
            evt
            async for evt in run_agent_loop(
                session=session,
                prompt="请记住：我偏好中文输出，并且回答要简洁。",
                user_id="u1",
                project_id="p1",
                country="mx",
            )
        ]

    events = asyncio.run(collect())

    assert any(evt["type"] == "tool_completed" and evt["tool_name"] == "memory_write" for evt in events)
    assert events[-1]["type"] == "final"
    assert events[-1]["final_message"] == "已记住。"
