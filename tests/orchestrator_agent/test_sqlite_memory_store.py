from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import MemoryStoreConflict, SQLiteMemoryStore


def _add(
    store: SQLiteMemoryStore,
    content: str,
    *,
    user_id: str = "u1",
    project_id: str = "p1",
    country: str = "mx",
    category: str = "preference",
):
    decision = build_memory_record(
        content=content,
        category=category,
        user_id=user_id,
        project_id=project_id,
        country=country,
        session_id="s1",
    )
    assert decision.accepted
    return store.add(decision.record)


@pytest.mark.timeout(2)
def test_sqlite_store_searches_and_scores(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    _add(store, "用户偏好中文输出，并喜欢简洁摘要")
    _add(store, "项目事实：当前项目是墨西哥用户画像系统", category="project")

    results = store.search("中文输出", user_id="u1", project_id="p1", country="mx", top_k=3)

    assert results
    assert results[0]["content"] == "用户偏好中文输出，并喜欢简洁摘要"
    assert "score_parts" in results[0]


@pytest.mark.timeout(2)
def test_sqlite_store_retrieves_chinese_paraphrase_query(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    _add(store, "请记住：我偏好中文输出，并且回答要简洁")

    results = store.search("我之前让你记住的输出偏好是什么？", user_id="u1", project_id="p1", country="mx", top_k=3)

    assert results
    assert "中文输出" in results[0]["content"]


@pytest.mark.timeout(2)
def test_sqlite_store_isolates_user_and_country(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    _add(store, "用户偏好 mx only memory", user_id="u1", country="mx")
    _add(store, "用户偏好 th only memory", user_id="u1", country="th")
    _add(store, "用户偏好 other user memory", user_id="u2", country="mx")

    assert len(store.search("memory", user_id="u1", project_id="p1", country="mx")) == 1
    assert len(store.search("memory", user_id="u1", project_id="p1", country="th")) == 1
    assert len(store.search("memory", user_id="u2", project_id="p1", country="mx")) == 1
    mx_results = store.search("th only", user_id="u1", project_id="p1", country="mx")
    assert all(item["country"] == "mx" for item in mx_results)
    assert all(item["content"] != "用户偏好 th only memory" for item in mx_results)


@pytest.mark.timeout(2)
def test_sqlite_store_dedupes_and_filters_expired(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    first = _add(store, "用户偏好 same preference memory")
    second = _add(store, "用户偏好 same preference memory")
    assert first.memory_id == second.memory_id

    expired = build_memory_record(
        content="项目事实：expired memory item",
        category="project",
        user_id="u1",
        project_id="p1",
        country="mx",
    )
    assert expired.accepted and expired.record
    expired.record.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    store.add(expired.record)

    results = store.search("memory", user_id="u1", project_id="p1", country="mx", top_k=10)
    contents = {item["content"] for item in results}
    assert "用户偏好 same preference memory" in contents
    assert "项目事实：expired memory item" not in contents


@pytest.mark.timeout(2)
def test_sqlite_store_management_update_status_and_list(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    record = _add(store, "用户偏好中文输出", user_id="manager", project_id="proj", country="mx")

    loaded = store.get(record.memory_id, user_id="manager", project_id="proj", country="mx")
    assert loaded and loaded["content"] == "用户偏好中文输出"

    record.content = "用户偏好英文输出"
    record.dedupe_key = ""
    updated = store.update(record)
    assert updated.memory_id == record.memory_id
    assert "英文输出" in store.search("英文输出", user_id="manager", project_id="proj", country="mx")[0]["content"]
    assert store.search("中文", user_id="manager", project_id="proj", country="mx") == []

    archived = store.set_status(record.memory_id, status="archived", user_id="manager", project_id="proj", country="mx")
    assert archived["status"] == "archived"
    assert store.search("英文输出", user_id="manager", project_id="proj", country="mx") == []
    assert store.list_records(user_id="manager", project_id="proj", country="mx", status="archived")[0]["memory_id"] == record.memory_id

    restored = store.set_status(record.memory_id, status="active", user_id="manager", project_id="proj", country="mx")
    assert restored["status"] == "active"
    assert store.search("英文输出", user_id="manager", project_id="proj", country="mx")


@pytest.mark.timeout(2)
def test_sqlite_store_update_rejects_dedupe_conflict(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.sqlite3")
    first = _add(store, "用户偏好中文输出", user_id="manager", project_id="proj", country="mx")
    second = _add(store, "用户偏好英文输出", user_id="manager", project_id="proj", country="mx")

    second.content = first.content
    second.dedupe_key = first.dedupe_key
    with pytest.raises(MemoryStoreConflict):
        store.update(second)
