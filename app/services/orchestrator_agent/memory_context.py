"""Identity and context assembly helpers for Orchestrator memory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.memory.observability import (
    SEMANTIC_MEMORY_TRACE_HANDOFF_KEY,
    SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY,
)
from app.services.memory.hybrid_retrieval import build_hybrid_memory_retrieval_service
from app.services.memory.retrieval import MemoryRetrievalRequest
from app.services.memory.retrieval_policy import MemoryRetrievalTaskType
from app.services.orchestrator_agent.memory_policy import (
    build_memory_record,
    classify_user_memory_content,
)
from app.services.orchestrator_agent.memory_store import (
    DEFAULT_COUNTRY,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    SQLiteMemoryStore,
    long_term_memory_enabled,
    memory_backend,
    memory_enabled,
    memory_retrieval_top_k,
    memory_write_enabled,
)


def apply_identity(
    session: Any,
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    country: str | None = None,
) -> None:
    if user_id:
        session.user_id = user_id
    elif not getattr(session, "user_id", None):
        session.user_id = DEFAULT_USER_ID

    if project_id:
        session.project_id = project_id
    elif not getattr(session, "project_id", None):
        session.project_id = DEFAULT_PROJECT_ID

    if country:
        session.country = country.lower()
    elif not getattr(session, "country", None):
        session.country = DEFAULT_COUNTRY


def build_retrieved_memory_context(
    *,
    session: Any,
    query: str,
    country: str | None = None,
    store: SQLiteMemoryStore | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    if not _sqlite_memory_on():
        _clear_semantic_memory_trace_handoff(session)
        return "", []
    if not settings.memory_vector_context_injection_enabled:
        _clear_semantic_memory_trace_handoff(session)
        return _legacy_retrieved_memory_context(
            session=session,
            query=query,
            country=country,
            store=store,
        )

    task_type = _resolve_memory_task_type(query)
    if task_type not in {
        MemoryRetrievalTaskType.GENERAL_CHAT,
        MemoryRetrievalTaskType.PROFILE_FOLLOWUP,
        MemoryRetrievalTaskType.RISK_QA_FOLLOWUP,
    }:
        _clear_semantic_memory_trace_handoff(session)
        return _legacy_retrieved_memory_context(
            session=session,
            query=query,
            country=country,
            store=store,
        )

    active_country = (country or getattr(session, "country", None) or DEFAULT_COUNTRY).lower()
    store = store or SQLiteMemoryStore()
    request = MemoryRetrievalRequest(
        query=query,
        task_type=task_type,
        user_id=getattr(session, "user_id", DEFAULT_USER_ID) or DEFAULT_USER_ID,
        project_id=getattr(session, "project_id", DEFAULT_PROJECT_ID) or DEFAULT_PROJECT_ID,
        country=active_country,
        session_id=getattr(session, "session_id", None),
        max_items=settings.memory_context_max_total_items,
        include_legacy_memory=True,
        allow_vector=True,
        allow_fts=True,
        retrieval_mode=settings.memory_vector_retrieval_mode,
        max_vector_items=settings.memory_vector_max_context_items,
        run_id=getattr(session, "active_run_id", None),
        request_id=_request_context_value(session, "request_id"),
        trace_id=_request_context_value(session, "trace_id"),
    )
    bundle = build_hybrid_memory_retrieval_service(store=store).build_context_bundle(request=request)
    _store_semantic_memory_trace_handoff(session, bundle.metadata)
    if not bundle.items:
        return "", []
    return bundle.rendered_text, [
        {
            "memory_id": item.memory_id,
            "content": item.content,
            "requested_use": item.requested_use,
            "retrieval_method": item.retrieval_method,
            "source_type": item.source_type,
            "authority_level": item.authority_level,
            "evidence_status": item.evidence_status,
        }
        for item in bundle.items
    ]


def append_rolling_summary(system_prompt: str, session: Any) -> str:
    summary = getattr(session, "rolling_summary", None)
    if not summary:
        return system_prompt
    return f"{system_prompt}\n\n## Rolling Session Summary\n{summary}"


def maybe_write_task_memory(
    *,
    session: Any,
    user_text: str,
    assistant_text: str | None = None,
    country: str | None = None,
    store: SQLiteMemoryStore | None = None,
) -> list[dict[str, Any]]:
    if not (_sqlite_memory_on() and memory_write_enabled()):
        return []
    store = store or SQLiteMemoryStore()
    active_country = (country or getattr(session, "country", None) or DEFAULT_COUNTRY).lower()
    written: list[dict[str, Any]] = []

    classified = classify_user_memory_content(user_text)
    if not classified:
        session.last_memory_sync_at = datetime.now(timezone.utc)
        return written

    category, content = classified
    decision = build_memory_record(
        content=content,
        category=category,
        user_id=getattr(session, "user_id", DEFAULT_USER_ID) or DEFAULT_USER_ID,
        project_id=getattr(session, "project_id", DEFAULT_PROJECT_ID) or DEFAULT_PROJECT_ID,
        session_id=getattr(session, "session_id", None),
        country=active_country,
        scope="user",
        memory_type="episodic" if category == "task" else "semantic",
        source="orchestrator_user_prompt",
        metadata={"auto_category": category},
    )
    if decision.accepted and decision.record:
        record = store.add(decision.record)
        written.append({"memory_id": record.memory_id, "category": record.category})

    session.last_memory_sync_at = datetime.now(timezone.utc)
    return written


def _sqlite_memory_on() -> bool:
    return memory_enabled() and long_term_memory_enabled() and memory_backend() == "sqlite"


def _legacy_retrieved_memory_context(
    *,
    session: Any,
    query: str,
    country: str | None = None,
    store: SQLiteMemoryStore | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    active_country = (country or getattr(session, "country", None) or DEFAULT_COUNTRY).lower()
    store = store or SQLiteMemoryStore()
    results = store.search(
        query=query,
        user_id=getattr(session, "user_id", DEFAULT_USER_ID) or DEFAULT_USER_ID,
        project_id=getattr(session, "project_id", DEFAULT_PROJECT_ID) or DEFAULT_PROJECT_ID,
        country=active_country,
        top_k=memory_retrieval_top_k(),
    )
    if not results:
        return "", []
    lines = [
        "## Retrieved Memories",
        "Use these persisted memories as user/project facts when they are relevant. "
        "If the user asks about their preferences, answer from preference memories "
        "before generic system output-style rules.",
    ]
    for item in results:
        score = item.get("score", 0)
        category = item.get("category", "memory")
        lines.append(f"- [{category} score={score}] {item.get('content', '')}")
    return "\n".join(lines), results


def _resolve_memory_task_type(query: str) -> MemoryRetrievalTaskType:
    lowered = str(query or "").strip().lower()
    if any(token in lowered for token in ("sql repair", "repair hint", "修复 sql", "修复sql")):
        return MemoryRetrievalTaskType.SQL_REPAIR
    if any(token in lowered for token in ("sql", "query data", "approved sql", "生成 sql")):
        return MemoryRetrievalTaskType.DATA_AGENT_SQL
    if any(token in lowered for token in ("risk", "拒绝原因", "风控", "why was the user rejected")):
        return MemoryRetrievalTaskType.RISK_QA_FOLLOWUP
    if any(token in lowered for token in ("profile", "画像", "segment", "risk level", "value level")):
        return MemoryRetrievalTaskType.PROFILE_FOLLOWUP
    return MemoryRetrievalTaskType.GENERAL_CHAT


def _request_context_value(session: Any, key: str) -> str | None:
    active_entities = getattr(session, "active_entities", None)
    if not isinstance(active_entities, dict):
        return None
    request_context = active_entities.get("request_context")
    if not isinstance(request_context, dict):
        return None
    value = str(request_context.get(key) or "").strip()
    return value or None


def _store_semantic_memory_trace_handoff(session: Any, metadata: dict[str, Any]) -> None:
    active_entities = getattr(session, "active_entities", None)
    if not isinstance(active_entities, dict):
        return
    summary = metadata.get(SEMANTIC_MEMORY_TRACE_SUMMARY_METADATA_KEY)
    if not isinstance(summary, dict):
        active_entities.pop(SEMANTIC_MEMORY_TRACE_HANDOFF_KEY, None)
        return
    active_entities[SEMANTIC_MEMORY_TRACE_HANDOFF_KEY] = dict(summary)


def _clear_semantic_memory_trace_handoff(session: Any) -> None:
    active_entities = getattr(session, "active_entities", None)
    if isinstance(active_entities, dict):
        active_entities.pop(SEMANTIC_MEMORY_TRACE_HANDOFF_KEY, None)
