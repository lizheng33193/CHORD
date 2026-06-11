"""Orchestrator Agent FastAPI routes (SSE chat + session GET + ACK).

Plan #04 hotfix: 在保留 `/chat` 一把梭路由（Plan #03 golden test 在用）的基础上，
补 3 个 thin adapter 路由对接前端 chat tab：
- POST /sessions          创建 session（可携带 initial_message 入槽）
- POST /sessions/{id}/messages  追加用户输入到槽
- GET  /sessions/{id}/stream    从槽取 prompt 跑 run_agent_loop

槽是 module-level dict（process-local，单实例 OK；多 worker 需要外部缓存，
Plan #04 V1 不要求多实例）。
"""

from __future__ import annotations

import json
import threading
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import build_request_context, require_permission
from app.auth.permissions import normalize_country_scope_value
from app.core.config import settings
from app.core.audit import record_runtime_audit_event
from app.core.user_context import UserContext
from app.services.orchestrator_agent.ack_bus import abort_ack, resolve_ack
from app.services.orchestrator_agent.resolve_bus import abort_resolution, resolve_pending_resolution
from app.services.orchestrator_agent.agent_loop import run_agent_loop
from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import (
    DEFAULT_COUNTRY,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    MemoryStoreConflict,
    MemoryStoreNotFound,
    SQLiteMemoryStore,
    memory_retrieval_top_k,
)
from app.services.orchestrator_agent.schemas import OrchestratorChatRequest
from app.services.orchestrator_agent.session_store import (
    create_session, get_session, list_sessions, save_session,
)


router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])

_PUBLIC_SESSION_EXCLUDE = {
    "execution_traces": {
        "__all__": {
            "internal_metadata",
        }
    }
}


# Pending-prompt 槽：session_id → 下一轮要喂给 agent_loop 的 prompt
# POST /sessions 与 POST /sessions/{id}/messages 写入；GET /sessions/{id}/stream 读取并清空。
_PENDING_PROMPTS_LOCK = threading.Lock()
_PENDING_PROMPTS: dict[str, dict[str, Any]] = {}


def _set_pending_prompt(session_id: str, prompt: str, client_turn_id: str | None = None) -> None:
    with _PENDING_PROMPTS_LOCK:
        _PENDING_PROMPTS[session_id] = {
            "prompt": prompt,
            "client_turn_id": client_turn_id,
        }


def _pop_pending_prompt(session_id: str) -> Optional[dict[str, Any]]:
    with _PENDING_PROMPTS_LOCK:
        return _PENDING_PROMPTS.pop(session_id, None)


@router.post("/chat")
async def chat_endpoint(
    req: OrchestratorChatRequest,
    request: Request,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> StreamingResponse:
    if req.session_id:
        sess = get_session(req.session_id)
        if sess is None:
            raise HTTPException(404, f"Session {req.session_id} not found")
        _require_session_access(sess, ctx)
        if sess.active_run_id and sess.active_run_status in {
            "queued", "running", "awaiting_user_ack", "awaiting_resolution", "cancel_requested", "cancelling",
        }:
            raise HTTPException(409, "An active run already exists for this session")
        with _PENDING_PROMPTS_LOCK:
            if req.session_id in _PENDING_PROMPTS:
                raise HTTPException(409, "A pending prompt already exists for this session")
    else:
        identity = _identity_from_request(request, ctx=ctx)
        sess = create_session(**identity)
    if req.session_id:
        identity = {
            "user_id": sess.user_id,
            "project_id": sess.project_id,
            "country": normalize_country_scope_value(sess.country) or DEFAULT_COUNTRY,
        }
    request_ctx = build_request_context(request, user=ctx, session_id=sess.session_id)

    async def event_stream() -> AsyncGenerator[bytes, None]:
        async for evt in run_agent_loop(
            session=sess,
            prompt=req.prompt,
            user_context=ctx,
            request_context=request_ctx,
            **identity,
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b'data: {"type": "done"}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ===== Plan #04 chat-tab 前端对接路由 =====


class _CreateSessionBody(BaseModel):
    initial_message: Optional[str] = None
    client_turn_id: Optional[str] = None
    workspace_snapshot: Optional[dict[str, Any]] = None


@router.post("/sessions")
async def create_session_endpoint(
    body: _CreateSessionBody,
    request: Request,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    identity = _identity_from_request(request, ctx=ctx)
    sess = create_session(**identity)
    sess.active_entities["request_context"] = build_request_context(request, user=ctx, session_id=sess.session_id).to_dict()
    sess.active_entities["user_context_snapshot"] = ctx.to_dict()
    if body.workspace_snapshot:
        sess.active_entities["workspace_snapshot"] = body.workspace_snapshot
        save_session(sess)
    if body.initial_message:
        _set_pending_prompt(sess.session_id, body.initial_message, body.client_turn_id)
    return {
        "session_id": sess.session_id,
        "created_at": sess.created_at.isoformat(),
        **identity,
    }


@router.get("/sessions")
async def list_sessions_endpoint(
    request: Request,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 20,
    ctx: UserContext = Depends(require_permission("profile:view")),
) -> dict:
    identity = _identity_from_request(
        request,
        ctx=ctx,
        user_id=user_id,
        project_id=project_id,
        country=country,
    )
    rows = list_sessions(
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
        limit=limit,
    )
    return {
        "success": True,
        **identity,
        "limit": max(1, min(100, int(limit or 20))),
        "sessions": rows,
    }


class _SendMessageBody(BaseModel):
    content: str
    client_turn_id: Optional[str] = None
    workspace_snapshot: Optional[dict[str, Any]] = None


@router.post("/sessions/{session_id}/messages")
async def send_message_endpoint(
    session_id: str,
    body: _SendMessageBody,
    request: Request,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    sess = get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _require_session_access(sess, ctx)
    if sess.active_run_id and sess.active_run_status in {
        "queued", "running", "awaiting_user_ack", "awaiting_resolution", "cancel_requested", "cancelling",
    }:
        raise HTTPException(409, "An active run already exists for this session")
    with _PENDING_PROMPTS_LOCK:
        if session_id in _PENDING_PROMPTS:
            raise HTTPException(409, "A pending prompt already exists for this session")
    _apply_request_identity(sess, request, ctx)
    if body.workspace_snapshot:
        sess.active_entities["workspace_snapshot"] = body.workspace_snapshot
        save_session(sess)
    _set_pending_prompt(session_id, body.content, body.client_turn_id)
    return {"ok": True}


@router.get("/sessions/{session_id}/stream")
async def stream_endpoint(
    session_id: str,
    request: Request,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> StreamingResponse:
    sess = get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _require_session_access(sess, ctx)
    identity = _apply_request_identity(sess, request, ctx)
    pending = _pop_pending_prompt(session_id)
    request_ctx = build_request_context(request, user=ctx, session_id=session_id)

    async def event_stream() -> AsyncGenerator[bytes, None]:
        if not pending:
            yield b'data: {"type": "done"}\n\n'
            return
        async for evt in run_agent_loop(
            session=sess,
            prompt=str(pending.get("prompt") or ""),
            client_turn_id=pending.get("client_turn_id"),
            user_context=ctx,
            request_context=request_ctx,
            **identity,
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b'data: {"type": "done"}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _AckBody(BaseModel):
    """兼容两种 body：
    - 旧（Plan #03 golden test）: {"confirm": true}
    - 新（Plan #04 前端 chat panel）: {"tool_call_id": "...", "decision": "approve"|"reject"}
    """

    confirm: Optional[bool] = None
    tool_call_id: Optional[str] = None
    ack_id: Optional[str] = None
    decision: Optional[str] = None


@router.post("/sessions/{session_id}/ack")
async def ack_endpoint(
    session_id: str,
    body: _AckBody,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    sess = get_session(session_id)
    if sess is None and settings.auth_enabled:
        raise HTTPException(404, f"Session {session_id} not found")
    if sess is not None:
        _require_session_access(sess, ctx)
    if body.confirm is not None:
        confirm = body.confirm
    elif body.decision is not None:
        confirm = body.decision == "approve"
    else:
        raise HTTPException(422, "ack body must contain either 'confirm' or 'decision'")
    ok = resolve_ack(session_id, confirm, ack_id=(body.ack_id or body.tool_call_id))
    return {"resolved": ok}


class _ResolveBody(BaseModel):
    execution_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    resolution_type: str = Field(..., min_length=1)
    resolution_id: Optional[str] = None
    answers: Optional[dict[str, Any]] = None
    selected_option: Optional[str] = None


@router.post("/sessions/{session_id}/resolve")
async def resolve_endpoint(
    session_id: str,
    body: _ResolveBody,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    sess = get_session(session_id)
    if sess is None and settings.auth_enabled:
        raise HTTPException(404, f"Session {session_id} not found")
    if sess is not None:
        _require_session_access(sess, ctx)
    if body.answers is None and not body.selected_option:
        raise HTTPException(422, "resolve body must contain either 'answers' or 'selected_option'")
    if not body.resolution_id:
        raise HTTPException(422, "resolve body must contain 'resolution_id'")
    ok = resolve_pending_resolution(
        session_id,
        {
            "execution_id": body.execution_id,
            "step_id": body.step_id,
            "resolution_type": body.resolution_type,
            "resolution_id": body.resolution_id,
            "answers": body.answers or {},
            "selected_option": body.selected_option,
        },
    )
    return {"resolved": ok}


@router.post("/sessions/{session_id}/runs/{run_id}/cancel")
async def cancel_run_endpoint(
    session_id: str,
    run_id: str,
    ctx: UserContext = Depends(require_permission("profile:run")),
) -> dict:
    sess = get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _require_session_access(sess, ctx)

    if sess.active_run_id == run_id and sess.active_run_status in {
        "queued", "running", "awaiting_user_ack", "awaiting_resolution", "cancel_requested", "cancelling",
    }:
        from app.services.orchestrator_agent.session import request_run_cancel

        sess.active_run_status = "cancel_requested"
        save_session(sess)
        request_run_cancel(session_id, run_id)
        abort_ack(session_id, run_id=run_id)
        abort_resolution(session_id, run_id=run_id)
        return {
            "status": "accepted",
            "session_id": session_id,
            "turn_id": sess.active_turn_id,
            "run_id": run_id,
            "run_status": "cancel_requested",
        }

    known_run_ids = {
        run.run_id
        for turn in getattr(sess, "turns", [])
        for run in getattr(turn, "runs", [])
    }
    if run_id in known_run_ids:
        return {
            "status": "already_finished",
            "session_id": session_id,
            "turn_id": sess.active_turn_id,
            "run_id": run_id,
        }
    return {
        "status": "not_found",
        "session_id": session_id,
        "turn_id": sess.active_turn_id,
        "run_id": run_id,
    }


@router.get("/sessions/{session_id}")
async def get_session_endpoint(
    session_id: str,
    ctx: UserContext = Depends(require_permission("profile:view")),
) -> dict:
    sess = get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id} not found")
    _require_session_access(sess, ctx)
    return sess.model_dump(mode="json", exclude=_PUBLIC_SESSION_EXCLUDE)


class _MemoryQueryBody(BaseModel):
    query: str = Field("", max_length=2000)
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    top_k: Optional[int] = Field(None, ge=1, le=50)


class _MemoryCreateBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    category: str = "reference"
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    country: Optional[str] = None
    session_id: Optional[str] = None
    scope: str = "user"
    memory_type: str = "semantic"
    tags: list[str] = Field(default_factory=list)
    importance: Optional[float] = Field(None, ge=0, le=1)
    confidence: float = Field(0.8, ge=0, le=1)
    expires_at: Optional[str] = None


class _MemoryUpdateBody(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=4000)
    category: Optional[str] = None
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    country: Optional[str] = None
    tags: Optional[list[str]] = None
    importance: Optional[float] = Field(None, ge=0, le=1)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    expires_at: Optional[str] = None


@router.get("/memory/status")
async def memory_status_endpoint(
    _ctx: UserContext = Depends(require_permission("memory:manage")),
) -> dict:
    return {"success": True, **SQLiteMemoryStore().status()}


@router.get("/memory/list")
async def memory_list_endpoint(
    request: Request,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    country: Optional[str] = None,
    status: Optional[str] = "active",
    category: Optional[str] = None,
    limit: int = 100,
    ctx: UserContext = Depends(require_permission("memory:read")),
) -> dict:
    identity = _identity_from_request(request, ctx=ctx, user_id=user_id, project_id=project_id, country=country)
    normalized_status = None if str(status or "").lower() == "all" else (status or "active")
    results = SQLiteMemoryStore().list_records(
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
        status=normalized_status,
        category=category,
        limit=max(1, min(1000, int(limit or 100))),
    )
    return {
        "success": True,
        **identity,
        "status": normalized_status or "all",
        "category": category,
        "results": results,
    }


@router.post("/memory/query")
async def memory_query_endpoint(
    body: _MemoryQueryBody,
    request: Request,
    ctx: UserContext = Depends(require_permission("memory:read")),
) -> dict:
    identity = _identity_from_request(
        request,
        ctx=ctx,
        user_id=body.user_id,
        project_id=body.project_id,
        country=body.country,
    )
    top_k = body.top_k or memory_retrieval_top_k()
    store = SQLiteMemoryStore()
    results = store.search(
        body.query,
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
        category=body.category,
        top_k=top_k,
    )
    return {
        "success": True,
        "query": body.query,
        **identity,
        "category": body.category,
        "top_k": top_k,
        "results": results,
    }


@router.post("/memory")
async def memory_create_endpoint(
    body: _MemoryCreateBody,
    request: Request,
    ctx: UserContext = Depends(require_permission("memory:write")),
) -> dict:
    identity = _identity_from_request(
        request,
        ctx=ctx,
        user_id=body.user_id,
        project_id=body.project_id,
        country=body.country,
    )
    decision = build_memory_record(
        content=body.content,
        category=body.category,
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        session_id=body.session_id,
        country=identity["country"],
        scope=body.scope,
        memory_type=body.memory_type,
        source="memory_admin",
        tags=body.tags,
        importance=body.importance,
        confidence=body.confidence,
        metadata={"admin_action": "create"},
    )
    if not decision.accepted or decision.record is None:
        raise HTTPException(status_code=422, detail={"reason": decision.reason})
    decision.record.expires_at = body.expires_at
    store = SQLiteMemoryStore()
    record = store.add(decision.record)
    memory = store.get(
        record.memory_id,
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
        session_id=body.session_id,
    )
    record_runtime_audit_event(
        user=ctx,
        request_context=build_request_context(request, user=ctx),
        event_type="memory.create",
        action="create",
        resource_type="memory",
        resource_id=record.memory_id,
        metadata={
            "scope": memory.get("scope") if memory else body.scope,
            "category": body.category,
            "country": identity["country"],
        },
    )
    return {
        "success": True,
        "memory": memory,
        "redaction_hits": decision.redaction_hits,
    }


@router.patch("/memory/{memory_id}")
async def memory_update_endpoint(
    memory_id: str,
    body: _MemoryUpdateBody,
    request: Request,
    ctx: UserContext = Depends(require_permission("memory:manage")),
) -> dict:
    identity = _identity_from_request(
        request,
        ctx=ctx,
        user_id=body.user_id,
        project_id=body.project_id,
        country=body.country,
    )
    store = SQLiteMemoryStore()
    existing = _get_memory_or_404(store, memory_id, identity)

    expires_at = existing.get("expires_at")
    if "expires_at" in body.model_fields_set:
        expires_at = body.expires_at
    metadata = dict(existing.get("metadata") or {})
    metadata["admin_action"] = "update"
    decision = build_memory_record(
        content=body.content if body.content is not None else existing["content"],
        category=body.category if body.category is not None else existing["category"],
        user_id=existing["user_id"],
        project_id=identity["project_id"],
        session_id=existing.get("session_id"),
        country=existing.get("country") or identity["country"],
        scope=existing.get("scope") or "user",
        memory_type=existing.get("memory_type") or "semantic",
        source="memory_admin",
        tags=body.tags if body.tags is not None else existing.get("tags", []),
        importance=body.importance if body.importance is not None else existing.get("importance"),
        confidence=body.confidence if body.confidence is not None else existing.get("confidence", 0.8),
        metadata=metadata,
    )
    if not decision.accepted or decision.record is None:
        raise HTTPException(status_code=422, detail={"reason": decision.reason})
    decision.record.memory_id = memory_id
    decision.record.status = existing.get("status") or "active"
    decision.record.created_at = existing.get("created_at") or decision.record.created_at
    decision.record.expires_at = expires_at
    try:
        record = store.update(decision.record)
    except MemoryStoreConflict as exc:
        raise HTTPException(status_code=409, detail={"reason": "duplicate_memory", "memory_id": str(exc)}) from exc
    except MemoryStoreNotFound as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    memory = store.get(
        record.memory_id,
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
        session_id=existing.get("session_id"),
    )
    record_runtime_audit_event(
        user=ctx,
        request_context=build_request_context(request, user=ctx),
        event_type="memory.update",
        action="update",
        resource_type="memory",
        resource_id=record.memory_id,
        metadata={
            "scope": memory.get("scope") if memory else existing.get("scope"),
            "category": memory.get("category") if memory else existing.get("category"),
            "country": identity["country"],
        },
    )
    return {"success": True, "memory": memory, "redaction_hits": decision.redaction_hits}


@router.post("/memory/{memory_id}/archive")
async def memory_archive_endpoint(
    memory_id: str,
    request: Request,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    country: Optional[str] = None,
    ctx: UserContext = Depends(require_permission("memory:manage")),
) -> dict:
    return _set_memory_status(
        memory_id,
        "archived",
        request,
        ctx,
        user_id=user_id,
        project_id=project_id,
        country=country,
    )


@router.post("/memory/{memory_id}/restore")
async def memory_restore_endpoint(
    memory_id: str,
    request: Request,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    country: Optional[str] = None,
    ctx: UserContext = Depends(require_permission("memory:manage")),
) -> dict:
    return _set_memory_status(
        memory_id,
        "active",
        request,
        ctx,
        user_id=user_id,
        project_id=project_id,
        country=country,
    )


@router.delete("/memory/{memory_id}")
async def memory_delete_endpoint(
    memory_id: str,
    request: Request,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    country: Optional[str] = None,
    ctx: UserContext = Depends(require_permission("memory:manage")),
) -> dict:
    return _set_memory_status(
        memory_id,
        "deleted",
        request,
        ctx,
        user_id=user_id,
        project_id=project_id,
        country=country,
    )


def _identity_from_request(
    request: Request,
    *,
    ctx: UserContext | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
) -> dict[str, str]:
    if settings.auth_enabled and ctx is not None:
        identity = {
            "user_id": ctx.user_id,
            "project_id": str(ctx.project_id or DEFAULT_PROJECT_ID),
            "country": normalize_country_scope_value(ctx.country or DEFAULT_COUNTRY) or DEFAULT_COUNTRY,
        }
        if ctx.is_superuser:
            return {
                "user_id": user_id or identity["user_id"],
                "project_id": project_id or identity["project_id"],
                "country": normalize_country_scope_value(country or identity["country"]) or identity["country"],
            }
        return identity
    return {
        "user_id": user_id or request.headers.get("X-User-ID") or DEFAULT_USER_ID,
        "project_id": project_id or request.headers.get("X-Project-ID") or DEFAULT_PROJECT_ID,
        "country": normalize_country_scope_value(country or request.headers.get("X-Country") or DEFAULT_COUNTRY) or DEFAULT_COUNTRY,
    }


def _apply_request_identity(sess, request: Request, ctx: UserContext | None = None) -> dict[str, str]:
    requested_identity = _identity_from_request(request, ctx=ctx)
    changed = False
    if not sess.user_id:
        sess.user_id = requested_identity["user_id"]
        changed = True
    if not sess.project_id:
        sess.project_id = requested_identity["project_id"]
        changed = True
    if not sess.country:
        sess.country = requested_identity["country"]
        changed = True
    identity = {
        "user_id": sess.user_id,
        "project_id": sess.project_id,
        "country": normalize_country_scope_value(sess.country) or requested_identity["country"],
    }
    if ctx is not None:
        sess.active_entities["user_context_snapshot"] = ctx.to_dict()
        sess.active_entities["request_context"] = build_request_context(request, user=ctx, session_id=sess.session_id).to_dict()
        changed = True
    if changed:
        save_session(sess)
    return identity


def _require_session_access(sess, ctx: UserContext) -> None:
    if ctx.is_superuser:
        return
    session_country = normalize_country_scope_value(sess.country) or DEFAULT_COUNTRY
    context_country = normalize_country_scope_value(ctx.country) or DEFAULT_COUNTRY
    if (
        str(sess.user_id) != str(ctx.user_id)
        or str(sess.project_id or DEFAULT_PROJECT_ID) != str(ctx.project_id or DEFAULT_PROJECT_ID)
        or session_country != context_country
    ):
        raise HTTPException(status_code=403, detail="session is not visible to the current user")


def _get_memory_or_404(
    store: SQLiteMemoryStore,
    memory_id: str,
    identity: dict[str, str],
) -> dict:
    memory = store.get(
        memory_id,
        user_id=identity["user_id"],
        project_id=identity["project_id"],
        country=identity["country"],
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return memory


def _set_memory_status(
    memory_id: str,
    status: str,
    request: Request,
    ctx: UserContext | None,
    *,
    user_id: str | None,
    project_id: str | None,
    country: str | None,
) -> dict:
    identity = _identity_from_request(
        request,
        ctx=ctx,
        user_id=user_id,
        project_id=project_id,
        country=country,
    )
    try:
        memory = SQLiteMemoryStore().set_status(memory_id, status=status, **identity)
    except MemoryStoreNotFound as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    if ctx is not None:
        action = {"archived": "archive", "active": "restore", "deleted": "delete"}.get(status, status)
        record_runtime_audit_event(
            user=ctx,
            request_context=build_request_context(request, user=ctx),
            event_type=f"memory.{action}",
            action=action,
            resource_type="memory",
            resource_id=memory_id,
            metadata={"scope": memory.get("scope"), "country": identity["country"]},
        )
    return {"success": True, "memory": memory}
