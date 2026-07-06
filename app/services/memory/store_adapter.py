"""Isolated M4-2 store adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.services.memory.records import MemoryRecordDraft
from app.services.orchestrator_agent.memory_store import (
    DEFAULT_COUNTRY,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    MemoryRecord,
    SQLiteMemoryStore,
)


class MemoryStoreAdapter(Protocol):
    def exists_by_dedupe_key(self, dedupe_key: str) -> bool:
        ...

    def add_record(self, draft: MemoryRecordDraft) -> str:
        ...


class InMemoryMemoryStoreAdapter:
    def __init__(self) -> None:
        self._records_by_dedupe: dict[str, tuple[str, MemoryRecordDraft]] = {}

    def exists_by_dedupe_key(self, dedupe_key: str) -> bool:
        return dedupe_key in self._records_by_dedupe

    def add_record(self, draft: MemoryRecordDraft) -> str:
        existing = self._records_by_dedupe.get(draft.dedupe_key)
        if existing is not None:
            return existing[0]
        memory_id = uuid4().hex
        self._records_by_dedupe[draft.dedupe_key] = (memory_id, draft)
        return memory_id


class SQLiteV1MemoryStoreAdapter:
    def __init__(self, *, db_path: Path | str | None = None) -> None:
        self._store = SQLiteMemoryStore(Path(db_path) if db_path is not None else None)

    def exists_by_dedupe_key(self, dedupe_key: str) -> bool:
        rows = self._store.list_records(limit=1000)
        return any(str(row.get("dedupe_key") or "") == dedupe_key for row in rows)

    def add_record(self, draft: MemoryRecordDraft) -> str:
        metadata = dict(draft.metadata_json)
        scope_warnings = list(metadata.get("scope_warnings") or [])

        user_id = draft.user_id or DEFAULT_USER_ID
        project_id = draft.project_id or DEFAULT_PROJECT_ID
        country = (draft.country or DEFAULT_COUNTRY).lower()
        if not draft.user_id:
            scope_warnings.append("missing_user_id_defaulted")
        if not draft.project_id:
            scope_warnings.append("missing_project_id_defaulted")
        if not draft.country:
            scope_warnings.append("missing_country_defaulted")
        metadata["scope_warnings"] = scope_warnings

        record = MemoryRecord(
            memory_id=uuid4().hex,
            scope="user",
            user_id=user_id,
            project_id=project_id,
            session_id=draft.session_id,
            country=country,
            category=_legacy_category(draft.memory_source_type),
            memory_type=_legacy_memory_type(draft.memory_source_type),
            content=draft.content,
            importance=float(draft.importance),
            confidence=float(draft.confidence),
            status=draft.status,
            tags=_build_tags(draft),
            source="m4_write_gate",
            dedupe_key=draft.dedupe_key,
            metadata=metadata,
        )
        return self._store.add(record).memory_id


def _legacy_category(memory_source_type: str) -> str:
    mapping = {
        "profile_result": "insight",
        "risk_qa_answer": "insight",
        "data_agent_sql_case": "reference",
        "data_agent_sql_error": "task",
        "user_preference": "preference",
        "audit_event": "reference",
        "eval_case": "reference",
    }
    value = mapping.get(memory_source_type, "reference")
    if value not in {"preference", "feedback", "project", "reference", "task", "insight"}:
        return "reference"
    return value


def _legacy_memory_type(memory_source_type: str) -> str:
    mapping = {
        "data_agent_sql_case": "procedural",
        "data_agent_sql_error": "episodic",
        "audit_event": "episodic",
        "eval_case": "episodic",
    }
    value = mapping.get(memory_source_type, "semantic")
    if value not in {"episodic", "semantic", "procedural"}:
        return "semantic"
    return value


def _build_tags(draft: MemoryRecordDraft) -> list[str]:
    tags = [draft.memory_source_type, draft.authority_level]
    if draft.evidence_status:
        tags.append(draft.evidence_status)
    return tags
