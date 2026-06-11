"""Plan #04 hotfix: chat-tab adapter routes (sessions / messages / stream)."""

from __future__ import annotations

import builtins
import importlib
import sys

import pytest


def test_create_session_with_initial_message_returns_id_and_iso_created_at(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions",
        json={"initial_message": "test prompt"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data and len(data["session_id"]) > 0
    assert "created_at" in data and "T" in data["created_at"]


def test_send_message_404_for_unknown_session(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/non-existent/messages",
        json={"content": "hi"},
    )
    assert r.status_code == 404


def test_send_message_writes_pending_prompt(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import orchestrator_routes as routes

    client = TestClient(app)
    sid = client.post(
        "/api/orchestrator/sessions", json={}
    ).json()["session_id"]

    ok = client.post(
        f"/api/orchestrator/sessions/{sid}/messages",
        json={"content": "second turn"},
    )
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    with routes._PENDING_PROMPTS_LOCK:
        assert routes._PENDING_PROMPTS.get(sid) == {
            "prompt": "second turn",
            "client_turn_id": None,
        }


def test_create_session_persists_workspace_snapshot(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    snapshot = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "comprehensive",
                "summary": "综合画像总结",
                "structured_result": {"segment": "S4"},
            }
        ],
    }

    sid = client.post(
        "/api/orchestrator/sessions",
        json={"workspace_snapshot": snapshot},
    ).json()["session_id"]

    session_payload = client.get(f"/api/orchestrator/sessions/{sid}").json()
    assert session_payload["active_entities"]["workspace_snapshot"] == snapshot


def test_send_message_updates_workspace_snapshot(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    sid = client.post("/api/orchestrator/sessions", json={}).json()["session_id"]
    snapshot = {
        "country": "mx",
        "applicationTime": None,
        "results": [
            {
                "uid": "824812551379353600",
                "module": "behavior",
                "summary": "行为画像总结",
                "structured_result": {"activity": "low"},
            }
        ],
    }

    resp = client.post(
        f"/api/orchestrator/sessions/{sid}/messages",
        json={"content": "帮我概括这个用户的行为画像", "workspace_snapshot": snapshot},
    )

    assert resp.status_code == 200
    session_payload = client.get(f"/api/orchestrator/sessions/{sid}").json()
    assert session_payload["active_entities"]["workspace_snapshot"] == snapshot


def test_stream_endpoint_runs_loop_and_terminates_with_done(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    sid = client.post(
        "/api/orchestrator/sessions",
        json={"initial_message": "hello"},
    ).json()["session_id"]

    with client.stream("GET", f"/api/orchestrator/sessions/{sid}/stream") as r:
        assert r.status_code == 200
        body = b"".join(chunk for chunk in r.iter_bytes()).decode("utf-8")
    assert '"type": "session_started"' in body
    assert '"type": "turn_started"' in body
    assert '"type": "run_started"' in body
    assert '"type": "final"' in body
    assert '"type": "done"' in body
    assert '"event_id":' in body
    assert '"event_seq":' in body
    assert '"turn_id":' in body
    assert '"run_id":' in body


def test_send_message_rejects_when_session_has_active_run(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.session_store import get_session, save_session

    client = TestClient(app)
    sid = client.post("/api/orchestrator/sessions", json={}).json()["session_id"]
    sess = get_session(sid)
    sess.active_run_id = "run-active"
    sess.active_run_status = "running"
    save_session(sess)

    resp = client.post(
        f"/api/orchestrator/sessions/{sid}/messages",
        json={"content": "second turn"},
    )
    assert resp.status_code == 409


def test_send_message_rejects_when_pending_prompt_already_exists(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import orchestrator_routes as routes

    client = TestClient(app)
    sid = client.post("/api/orchestrator/sessions", json={}).json()["session_id"]
    with routes._PENDING_PROMPTS_LOCK:
        routes._PENDING_PROMPTS[sid] = {"prompt": "already queued", "client_turn_id": "ct-1"}

    resp = client.post(
        f"/api/orchestrator/sessions/{sid}/messages",
        json={"content": "second turn"},
    )
    assert resp.status_code == 409


def test_legacy_chat_rejects_when_session_has_active_run(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.session_store import get_session, save_session

    client = TestClient(app)
    sid = client.post("/api/orchestrator/sessions", json={}).json()["session_id"]
    sess = get_session(sid)
    sess.active_turn_id = "turn-legacy"
    sess.active_run_id = "run-legacy"
    sess.active_run_status = "running"
    save_session(sess)

    resp = client.post("/api/orchestrator/chat", json={"session_id": sid, "prompt": "legacy path"})
    assert resp.status_code == 409


def test_cancel_run_endpoint_accepts_known_active_run(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.session_store import get_session, save_session

    client = TestClient(app)
    sid = client.post("/api/orchestrator/sessions", json={}).json()["session_id"]
    sess = get_session(sid)
    sess.active_turn_id = "turn-1"
    sess.active_run_id = "run-1"
    sess.active_run_status = "running"
    save_session(sess)

    resp = client.post(f"/api/orchestrator/sessions/{sid}/runs/run-1/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["run_id"] == "run-1"


def test_stream_without_pending_prompt_yields_done_only(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    sid = client.post(
        "/api/orchestrator/sessions", json={}
    ).json()["session_id"]

    with client.stream("GET", f"/api/orchestrator/sessions/{sid}/stream") as r:
        body = b"".join(chunk for chunk in r.iter_bytes()).decode("utf-8")
    assert '"type": "done"' in body
    assert '"type": "session_started"' not in body


def test_ack_endpoint_accepts_decision_body(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/no-such-session/ack",
        json={"tool_call_id": "x", "decision": "approve"},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": False}


def test_ack_endpoint_uses_tool_call_id_when_ack_id_missing(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.ack_bus import open_ack

    client = TestClient(app)
    open_ack("s-ack", ack_id="tc-1", run_id="run-1")
    r = client.post(
        "/api/orchestrator/sessions/s-ack/ack",
        json={"tool_call_id": "tc-1", "decision": "approve"},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": True}


def test_ack_endpoint_rejects_wrong_tool_call_id(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.ack_bus import open_ack

    client = TestClient(app)
    open_ack("s-ack-mismatch", ack_id="tc-1", run_id="run-1")
    r = client.post(
        "/api/orchestrator/sessions/s-ack-mismatch/ack",
        json={"tool_call_id": "tc-wrong", "decision": "approve"},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": False}


def test_ack_endpoint_legacy_confirm_cannot_bypass_bound_ack_id(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.orchestrator_agent.ack_bus import open_ack

    client = TestClient(app)
    open_ack("s-ack-legacy", ack_id="tc-1", run_id="run-1")
    r = client.post(
        "/api/orchestrator/sessions/s-ack-legacy/ack",
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": False}


def test_ack_endpoint_rejects_empty_body(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/x/ack",
        json={},
    )
    assert r.status_code == 422


def test_resolve_endpoint_accepts_clarification_answers(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(
        "app.api.orchestrator_routes.resolve_pending_resolution",
        lambda session_id, payload: session_id == "s-1" and payload["resolution_type"] == "clarification",
    )

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/s-1/resolve",
        json={
            "execution_id": "ex-1",
            "step_id": "clarify_scope",
            "resolution_id": "res-1",
            "resolution_type": "clarification",
            "answers": {"country": "mx", "time_window": "最近 7 天", "auto_profile": True},
        },
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": True}


def test_resolve_endpoint_rejects_empty_resolution(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/s-1/resolve",
        json={
            "execution_id": "ex-1",
            "step_id": "clarify_scope",
            "resolution_type": "clarification",
        },
    )
    assert r.status_code == 422


def test_resolve_endpoint_requires_resolution_id(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/s-1/resolve",
        json={
            "execution_id": "ex-1",
            "step_id": "clarify_scope",
            "resolution_type": "clarification",
            "answers": {"country": "mx"},
        },
    )
    assert r.status_code == 422


def test_app_main_imports_without_data_acquisition_executor_and_skips_router(monkeypatch):
    original_import = builtins.__import__

    def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"data_acquisition_agent.connection", "data_acquisition_agent.executor"}:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _patched_import)
    for mod in [
        "app.main",
        "data_acquisition_agent.api",
        "data_acquisition_agent.connection",
        "data_acquisition_agent.executor",
    ]:
        sys.modules.pop(mod, None)

    main_mod = importlib.import_module("app.main")
    routes = [route.path for route in main_mod.app.routes]

    assert "/api/orchestrator/sessions" in routes
    assert all(not path.startswith("/api/data-acquisition") for path in routes)


def test_app_main_disabled_data_acquisition_never_mounts_router(monkeypatch):
    original_import = builtins.__import__

    monkeypatch.setenv("DATA_ACQUISITION_ENABLED", "false")

    def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _patched_import)
    for mod in [
        "app.main",
        "data_acquisition_agent.api",
        "data_acquisition_agent.connection",
        "data_acquisition_agent.executor",
    ]:
        sys.modules.pop(mod, None)

    main_mod = importlib.import_module("app.main")
    routes = [route.path for route in main_mod.app.routes]

    assert all(not path.startswith("/api/data-acquisition") for path in routes)


def test_app_main_required_data_acquisition_raises_when_dependency_missing(monkeypatch):
    original_import = builtins.__import__

    monkeypatch.setenv("DATA_ACQUISITION_ENABLED", "true")

    def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"data_acquisition_agent.connection", "data_acquisition_agent.executor"}:
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _patched_import)
    for mod in [
        "app.main",
        "data_acquisition_agent.api",
        "data_acquisition_agent.connection",
        "data_acquisition_agent.executor",
    ]:
        sys.modules.pop(mod, None)

    with pytest.raises(RuntimeError):
        importlib.import_module("app.main")


def test_get_session_after_chat_includes_assistant_message(monkeypatch):
    """Plan #04 hotfix 二段：agent_loop final 分支应把 assistant 也写入 session.messages，
    否则 TC-4 刷新恢复时只能看到 user 气泡。"""
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    sid = client.post(
        "/api/orchestrator/sessions",
        json={"initial_message": "hello"},
    ).json()["session_id"]

    with client.stream("GET", f"/api/orchestrator/sessions/{sid}/stream") as r:
        b"".join(chunk for chunk in r.iter_bytes())

    sess = client.get(f"/api/orchestrator/sessions/{sid}").json()
    roles = [m["role"] for m in sess["messages"]]
    assert "user" in roles
    assert "assistant" in roles


def test_get_session_after_known_request_includes_execution_traces(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app

    uid = "824812551379353600"

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.normalize_request",
        lambda prompt, session, detected_country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["NormalizedRequest"]).NormalizedRequest(
            intent="profile_uid",
            country="mx",
            uids=[uid],
            modules=["app"],
            request_summary=f"分析 UID {uid} 的画像",
            query_request=None,
            read_only=False,
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.check_data_availability",
        lambda uids, country=None: __import__("app.services.orchestrator_agent.schemas", fromlist=["DataAvailability", "UidAvailability", "BucketAvailability"]).DataAvailability(
            country="mx",
            checked_uids=[uid],
            per_uid=[
                __import__("app.services.orchestrator_agent.schemas", fromlist=["UidAvailability", "BucketAvailability"]).UidAvailability(
                    uid=uid,
                    app=__import__("app.services.orchestrator_agent.schemas", fromlist=["BucketAvailability"]).BucketAvailability(status="available", available=True, source_type="csv", path="/tmp/app.csv"),
                    behavior=__import__("app.services.orchestrator_agent.schemas", fromlist=["BucketAvailability"]).BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    credit=__import__("app.services.orchestrator_agent.schemas", fromlist=["BucketAvailability"]).BucketAvailability(status="missing", available=False, source_type="missing", path=None),
                    available_buckets=["app"],
                    missing_buckets=["behavior", "credit"],
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile",
        lambda inp, progress_callback=None: type("X", (), {
            "model_dump": lambda self, mode="json": {
                "results": [{
                    "uid": uid,
                    "module": "app",
                    "result": {
                        "status": "ok",
                        "data": {"summary": "app done", "structured_result": {}, "charts": [], "report_markdown": ""},
                        "error": None,
                    },
                }],
                "cache_hits": 0,
                "cache_misses": 1,
            },
        })(),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: type("NoLLM", (), {"generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run"))})(),
    )

    client = TestClient(app)
    sid = client.post(
        "/api/orchestrator/sessions",
        json={"initial_message": f"帮我分析一下{uid}"},
    ).json()["session_id"]

    with client.stream("GET", f"/api/orchestrator/sessions/{sid}/stream") as r:
        assert r.status_code == 200
        b"".join(chunk for chunk in r.iter_bytes())

    sess = client.get(f"/api/orchestrator/sessions/{sid}").json()
    assert isinstance(sess.get("execution_traces"), list)
    assert sess["execution_traces"]
