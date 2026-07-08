"""Readable store adapters for isolated M4 retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.memory.contracts import (
    MemoryAuthorityLevel,
    MemorySourceType,
)
from app.services.memory.policy import (
    get_allowed_memory_use,
    get_forbidden_memory_use,
)
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore


@dataclass(frozen=True)
class MemoryStoredRecord:
    memory_id: str
    content: str
    user_id: str
    project_id: str | None
    country: str | None
    status: str
    metadata_json: dict[str, Any]
    importance: float = 0.5
    confidence: float = 0.5
    created_at: str | None = None


class MemoryReadableStoreAdapter(Protocol):
    def search_records(
        self,
        *,
        query: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        allowed_source_types: tuple[MemorySourceType, ...],
        limit: int,
        include_legacy_memory: bool = False,
    ) -> list[MemoryStoredRecord]:
        ...

    def get_record(
        self,
        *,
        memory_id: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        session_id: str | None = None,
        include_legacy_memory: bool = False,
    ) -> MemoryStoredRecord | None:
        ...


class InMemoryMemoryRetrievalAdapter:
    def __init__(self, records: list[MemoryStoredRecord] | None = None) -> None:
        self._records = list(records or [])

    def search_records(
        self,
        *,
        query: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        allowed_source_types: tuple[MemorySourceType, ...],
        limit: int,
        include_legacy_memory: bool = False,
        ) -> list[MemoryStoredRecord]:
        allowed_values = {item.value for item in allowed_source_types}
        records: list[MemoryStoredRecord] = []
        for record in self._records:
            if record.user_id != user_id:
                continue
            if project_id is not None and record.project_id != project_id:
                continue
            if country is not None and (record.country or "").lower() != country.lower():
                continue
            source_type = str(record.metadata_json.get("memory_source_type") or "").strip()
            if source_type and source_type not in allowed_values:
                continue
            if not include_legacy_memory and not _has_m4_marker(record.metadata_json):
                continue
            records.append(record)
        return records[: max(1, limit)]

    def get_record(
        self,
        *,
        memory_id: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        session_id: str | None = None,
        include_legacy_memory: bool = False,
    ) -> MemoryStoredRecord | None:
        for record in self._records:
            if record.memory_id != memory_id:
                continue
            if record.user_id != user_id:
                continue
            if project_id is not None and record.project_id != project_id:
                continue
            if country is not None and (record.country or "").lower() != country.lower():
                continue
            if not include_legacy_memory and not _has_m4_marker(record.metadata_json):
                continue
            return record
        return None


class SQLiteV1MemoryRetrievalAdapter:
    def __init__(self, *, db_path: Path | str | None = None) -> None:
        self._store = SQLiteMemoryStore(Path(db_path) if db_path is not None else None)

    def search_records(
        self,
        *,
        query: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        allowed_source_types: tuple[MemorySourceType, ...],
        limit: int,
        include_legacy_memory: bool = False,
    ) -> list[MemoryStoredRecord]:
        rows = self._store.search(
            query=query,
            user_id=user_id,
            project_id=project_id or "",
            country=country or "",
            top_k=max(10, limit * 8),
        )
        allowed_values = {item.value for item in allowed_source_types}
        records: list[MemoryStoredRecord] = []
        for row in rows:
            record = stored_record_from_memory_row(row, include_legacy_memory=include_legacy_memory)
            if record is None:
                continue
            source_type = str(record.metadata_json.get("memory_source_type") or "").strip()
            if source_type not in allowed_values:
                continue
            records.append(record)
        return records[: max(1, limit)]

    def get_record(
        self,
        *,
        memory_id: str,
        user_id: str,
        project_id: str | None,
        country: str | None,
        session_id: str | None = None,
        include_legacy_memory: bool = False,
    ) -> MemoryStoredRecord | None:
        row = self._store.get(
            memory_id,
            user_id=user_id,
            project_id=project_id or "",
            country=country or "",
            session_id=session_id,
        )
        if row is None:
            return None
        return stored_record_from_memory_row(row, include_legacy_memory=include_legacy_memory)


def stored_record_from_memory_row(
    row: dict[str, Any],
    *,
    include_legacy_memory: bool = False,
) -> MemoryStoredRecord | None:
    metadata = dict(row.get("metadata") or row.get("metadata_json") or {})
    if not _has_m4_marker(metadata):
        if not include_legacy_memory:
            return None
        metadata = _legacy_metadata_for_row(row)
    return MemoryStoredRecord(
        memory_id=str(row.get("memory_id") or ""),
        content=str(row.get("content") or ""),
        user_id=str(row.get("user_id") or ""),
        project_id=_optional_text(row.get("project_id")),
        country=_optional_text(row.get("country")),
        status=str(row.get("status") or ""),
        metadata_json=metadata,
        importance=float(row.get("importance") or 0.5),
        confidence=float(row.get("confidence") or 0.5),
        created_at=_optional_text(row.get("created_at")),
    )


def _is_m4_governed_metadata(metadata: dict[str, Any]) -> bool:
    required = {
        "m4_contract_version",
        "memory_source_type",
        "authority_level",
        "allowed_memory_use",
        "forbidden_memory_use",
        "write_gate",
    }
    return required.issubset(metadata)


def _has_m4_marker(metadata: dict[str, Any]) -> bool:
    return "m4_contract_version" in metadata


def _legacy_metadata_for_row(row: dict[str, Any]) -> dict[str, Any]:
    source_type = _legacy_source_type_for_row(row)
    authority = _legacy_authority_for_row(row, source_type)
    return {
        "m4_contract_version": "m6b_legacy_compat",
        "memory_source_type": source_type.value,
        "authority_level": authority.value,
        "allowed_memory_use": [item.value for item in get_allowed_memory_use(source_type)],
        "forbidden_memory_use": [item.value for item in get_forbidden_memory_use(source_type)],
        "source_run_id": None,
        "source_artifact_id": None,
        "evidence_status": None,
        "candidate_metadata": {
            "legacy": True,
            "category": str(row.get("category") or ""),
            "memory_type": str(row.get("memory_type") or ""),
            "source": str(row.get("source") or ""),
        },
        "write_gate": {
            "status": "legacy_compat",
            "reject_reason": None,
            "redacted": False,
            "dedupe_key": str(row.get("memory_id") or ""),
            "decision_reason": "legacy_memory_runtime_compat",
        },
    }


def _legacy_source_type_for_row(row: dict[str, Any]) -> MemorySourceType:
    category = str(row.get("category") or "").strip().lower()
    if category == "preference":
        return MemorySourceType.USER_PREFERENCE
    return MemorySourceType.CONVERSATION


def _legacy_authority_for_row(row: dict[str, Any], source_type: MemorySourceType) -> MemoryAuthorityLevel:
    source = str(row.get("source") or "").strip().lower()
    if source_type is MemorySourceType.USER_PREFERENCE:
        return MemoryAuthorityLevel.USER_PROVIDED
    if "profile" in source or "system" in source:
        return MemoryAuthorityLevel.SYSTEM_GENERATED
    return MemoryAuthorityLevel.SYSTEM_GENERATED


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
