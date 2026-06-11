from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.orchestrator_agent.memory_context import maybe_write_task_memory
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.schemas import OrchestratorSession


def _session() -> OrchestratorSession:
    now = datetime.now(timezone.utc)
    return OrchestratorSession(
        session_id="context_policy_session",
        created_at=now,
        updated_at=now,
        user_id="u-context",
        project_id="p-context",
        country="mx",
    )


@pytest.mark.timeout(2)
def test_context_does_not_write_noise_or_assistant_final(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    session = _session()

    written = maybe_write_task_memory(
        session=session,
        user_text="你好，你是什么模型？",
        assistant_text="您好！我是一个用于墨西哥/东南亚用户画像分析平台的编排代理。",
        store=store,
    )

    assert written == []
    assert store.list_records(user_id="u-context", project_id="p-context", country="mx") == []


@pytest.mark.timeout(2)
def test_context_writes_explicit_preference(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    session = _session()

    written = maybe_write_task_memory(
        session=session,
        user_text="请记住：我偏好中文输出，并且回答要简洁。",
        assistant_text="已记住。",
        store=store,
    )

    assert written == [{"memory_id": written[0]["memory_id"], "category": "preference"}]
    records = store.list_records(user_id="u-context", project_id="p-context", country="mx")
    assert len(records) == 1
    assert records[0]["category"] == "preference"
    assert "中文输出" in records[0]["content"]


@pytest.mark.timeout(2)
def test_context_writes_real_task_summary(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    session = _session()

    written = maybe_write_task_memory(
        session=session,
        user_text="请查询 UID 123 的用户画像，并分析最近 7 天行为 trace。",
        assistant_text="已完成画像分析。",
        store=store,
    )

    assert written and written[0]["category"] == "task"
    records = store.list_records(user_id="u-context", project_id="p-context", country="mx")
    assert len(records) == 1
    assert records[0]["category"] == "task"
    assert "UID 123" in records[0]["content"]
