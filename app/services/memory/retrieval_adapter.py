"""Readable store adapters for isolated M4 retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.memory.contracts import MemorySourceType
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
        rows = self._store.list_records(
            user_id=user_id,
            project_id=project_id,
            country=country,
            limit=max(10, limit * 8),
        )
        allowed_values = {item.value for item in allowed_source_types}
        records: list[MemoryStoredRecord] = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            if not include_legacy_memory and not _has_m4_marker(metadata):
                continue
            source_type = str(metadata.get("memory_source_type") or "").strip()
            if source_type not in allowed_values:
                continue
            records.append(
                MemoryStoredRecord(
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
            )
        return records[: max(1, limit)]


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


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
