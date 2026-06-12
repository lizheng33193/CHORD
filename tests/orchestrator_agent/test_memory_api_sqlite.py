from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.orchestrator_agent.schemas import OrchestratorMessage
from app.services.orchestrator_agent.session_store import create_session, save_session


@pytest.mark.timeout(3)
def test_session_creation_uses_identity_headers():
    client = TestClient(app)
    resp = client.post(
        "/api/orchestrator/sessions",
        json={"initial_message": "hello"},
        headers={"X-User-ID": "analyst-1", "X-Project-ID": "proj-1", "X-Country": "th"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "analyst-1"
    assert body["project_id"] == "proj-1"
    assert body["country"] == "th"


@pytest.mark.timeout(3)
def test_memory_status_and_query_api():
    decision = build_memory_record(
        content="用户偏好中文输出",
        category="preference",
        user_id="analyst-1",
        project_id="proj-1",
        country="mx",
    )
    assert decision.accepted and decision.record
    SQLiteMemoryStore().add(decision.record)
    project_decision = build_memory_record(
        content="项目事实：当前项目使用 SQLite 长期记忆",
        category="project",
        user_id="analyst-1",
        project_id="proj-1",
        country="mx",
    )
    assert project_decision.accepted and project_decision.record
    SQLiteMemoryStore().add(project_decision.record)

    client = TestClient(app)
    status = client.get("/api/orchestrator/memory/status")
    assert status.status_code == 200
    assert status.json()["total"] >= 1

    query = client.post(
        "/api/orchestrator/memory/query",
        json={"query": "中文输出", "top_k": 3},
        headers={"X-User-ID": "analyst-1", "X-Project-ID": "proj-1", "X-Country": "mx"},
    )
    assert query.status_code == 200
    results = query.json()["results"]
    assert results
    assert results[0]["content"] == "用户偏好中文输出"
    assert "score_parts" in results[0]

    recent = client.post(
        "/api/orchestrator/memory/query",
        json={"query": "", "category": "project", "top_k": 5},
        headers={"X-User-ID": "analyst-1", "X-Project-ID": "proj-1", "X-Country": "mx"},
    )
    assert recent.status_code == 200
    body = recent.json()
    assert body["category"] == "project"
    assert body["results"]
    assert all(item["category"] == "project" for item in body["results"])
    assert any(item["content"] == "项目事实：当前项目使用 SQLite 长期记忆" for item in body["results"])


@pytest.mark.timeout(3)
def test_memory_management_api_create_edit_archive_restore_delete():
    client = TestClient(app)
    identity = {"user_id": "admin-user", "project_id": "admin-project", "country": "mx"}

    created = client.post(
        "/api/orchestrator/memory",
        json={
            **identity,
            "content": "请记住：我偏好中文输出",
            "category": "preference",
            "tags": ["manual"],
        },
    )
    assert created.status_code == 200
    memory = created.json()["memory"]
    memory_id = memory["memory_id"]
    assert memory["source"] == "memory_admin"

    listed = client.get("/api/orchestrator/memory/list", params={**identity, "status": "active"})
    assert listed.status_code == 200
    assert any(item["memory_id"] == memory_id for item in listed.json()["results"])

    updated = client.patch(
        f"/api/orchestrator/memory/{memory_id}",
        json={**identity, "content": "请记住：我偏好英文输出", "category": "preference"},
    )
    assert updated.status_code == 200
    assert "英文输出" in updated.json()["memory"]["content"]

    archive = client.post(f"/api/orchestrator/memory/{memory_id}/archive", params=identity)
    assert archive.status_code == 200
    assert archive.json()["memory"]["status"] == "archived"
    archived_query = client.post("/api/orchestrator/memory/query", json={**identity, "query": "英文输出"})
    assert archived_query.status_code == 200
    assert archived_query.json()["results"] == []

    restore = client.post(f"/api/orchestrator/memory/{memory_id}/restore", params=identity)
    assert restore.status_code == 200
    assert restore.json()["memory"]["status"] == "active"
    restored_query = client.post("/api/orchestrator/memory/query", json={**identity, "query": "英文输出"})
    assert restored_query.status_code == 200
    assert any(item["memory_id"] == memory_id for item in restored_query.json()["results"])

    delete = client.delete(f"/api/orchestrator/memory/{memory_id}", params=identity)
    assert delete.status_code == 200
    assert delete.json()["memory"]["status"] == "deleted"
    deleted_query = client.post("/api/orchestrator/memory/query", json={**identity, "query": "英文输出"})
    assert deleted_query.status_code == 200
    assert deleted_query.json()["results"] == []


@pytest.mark.timeout(3)
def test_memory_management_api_identity_isolation_and_duplicate_update_conflict():
    client = TestClient(app)
    identity = {"user_id": "admin-user-2", "project_id": "admin-project", "country": "mx"}
    first = client.post(
        "/api/orchestrator/memory",
        json={**identity, "content": "请记住：我偏好中文输出", "category": "preference"},
    ).json()["memory"]
    second = client.post(
        "/api/orchestrator/memory",
        json={**identity, "content": "请记住：我偏好英文输出", "category": "preference"},
    ).json()["memory"]

    isolated = client.patch(
        f"/api/orchestrator/memory/{first['memory_id']}",
        json={**identity, "user_id": "other-user", "content": "请记住：我偏好西语输出"},
    )
    assert isolated.status_code == 404

    conflict = client.patch(
        f"/api/orchestrator/memory/{second['memory_id']}",
        json={**identity, "content": "请记住：我偏好中文输出", "category": "preference"},
    )
    assert conflict.status_code == 409

    rejected = client.post(
        "/api/orchestrator/memory",
        json={**identity, "content": "你好", "category": "preference"},
    )
    assert rejected.status_code == 422


@pytest.mark.timeout(3)
def test_project_scope_memory_is_shared_within_same_project_and_country():
    store = SQLiteMemoryStore()
    decision = build_memory_record(
        content="项目事实：这个结论应该在项目内共享",
        category="project",
        user_id="alice",
        project_id="proj-shared",
        country="mx",
        scope="project",
        source="memory_admin",
    )
    assert decision.accepted and decision.record
    store.add(decision.record)

    visible = store.search(
        "项目内共享",
        user_id="bob",
        project_id="proj-shared",
        country="mx",
    )
    hidden_other_country = store.search(
        "项目内共享",
        user_id="bob",
        project_id="proj-shared",
        country="th",
    )

    assert visible
    assert visible[0]["scope"] == "project"
    assert hidden_other_country == []


@pytest.mark.timeout(3)
def test_global_scope_memory_is_shared_across_countries_within_same_project():
    store = SQLiteMemoryStore()
    decision = build_memory_record(
        content="项目全局事实：这个结论应该跨国家共享",
        category="project",
        user_id="alice",
        project_id="proj-global",
        country="mx",
        scope="global",
        source="memory_admin",
    )
    assert decision.accepted and decision.record
    store.add(decision.record)

    same_project_other_country = store.search(
        "跨国家共享",
        user_id="bob",
        project_id="proj-global",
        country="th",
    )
    other_project = store.search(
        "跨国家共享",
        user_id="bob",
        project_id="other-project",
        country="mx",
    )

    assert same_project_other_country
    assert same_project_other_country[0]["scope"] == "global"
    assert other_project == []


@pytest.mark.timeout(3)
@pytest.mark.parametrize("scope,country", [("project", "mx"), ("global", "mx")])
def test_shared_scope_dedupe_ignores_creator_identity(scope: str, country: str):
    store = SQLiteMemoryStore()
    first = build_memory_record(
        content="项目事实：共享记忆不应按创建者重复",
        category="project",
        user_id="alice",
        project_id="proj-dedupe",
        country=country,
        scope=scope,
        source="memory_admin",
    )
    second = build_memory_record(
        content="项目事实：共享记忆不应按创建者重复",
        category="project",
        user_id="bob",
        project_id="proj-dedupe",
        country=country,
        scope=scope,
        source="memory_admin",
    )
    assert first.accepted and first.record
    assert second.accepted and second.record

    record_1 = store.add(first.record)
    record_2 = store.add(second.record)

    assert record_1.memory_id == record_2.memory_id
    listed = store.list_records(project_id="proj-dedupe", status="active", limit=20)
    assert len([item for item in listed if item["memory_id"] == record_1.memory_id]) == 1


@pytest.mark.timeout(3)
def test_session_history_list_api_identity_sorting_preview_and_limit():
    first = create_session(user_id="history-user", project_id="history-project", country="mx")
    first.messages.append(OrchestratorMessage(
        role="user",
        content="第一条用户消息",
        timestamp=datetime.now(timezone.utc),
    ))
    save_session(first)

    second = create_session(user_id="history-user", project_id="history-project", country="mx")
    second.messages.append(OrchestratorMessage(
        role="user",
        content="第二条用户消息，应该排在最前",
        timestamp=datetime.now(timezone.utc),
    ))
    second.final_message = "第二条最终回复"
    save_session(second)

    other = create_session(user_id="other-user", project_id="history-project", country="mx")
    other.messages.append(OrchestratorMessage(
        role="user",
        content="不应该被看到",
        timestamp=datetime.now(timezone.utc),
    ))
    save_session(other)

    client = TestClient(app)
    resp = client.get(
        "/api/orchestrator/sessions",
        params={"limit": 1},
        headers={"X-User-ID": "history-user", "X-Project-ID": "history-project", "X-Country": "mx"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 1
    assert len(body["sessions"]) == 1
    item = body["sessions"][0]
    assert item["session_id"] == second.session_id
    assert item["message_count"] == 1
    assert "第二条用户消息" in item["last_user_message_preview"]
    assert item["final_message_preview"] == "第二条最终回复"
    assert item["user_id"] == "history-user"
