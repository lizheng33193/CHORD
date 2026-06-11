"""memory_write / memory_read compatibility tools backed by SQLite."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.memory_policy import (
    build_memory_record,
    classify_user_memory_content,
)
from app.services.orchestrator_agent.memory_store import (
    DEFAULT_COUNTRY,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    SQLiteMemoryStore,
)
from app.services.orchestrator_agent.schemas import (
    MemoryReadInput,
    MemoryReadOutput,
    MemoryWriteInput,
    MemoryWriteOutput,
)


VALID_CATEGORIES = ("user", "preference", "feedback", "project", "reference", "task", "insight")


def _project_root() -> Path:
    return settings.project_root


def _default_store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore()


def _parse_four_class_key(key: str) -> tuple[str, str, str, str] | None:
    parts = key.split("/", 3)
    if len(parts) != 4:
        return None
    country, session_id, category, memory_id = parts
    if category not in VALID_CATEGORIES:
        return None
    if not country or not session_id or not memory_id:
        return None
    return country, session_id, category, memory_id


def read_all_categories(country: str, session_id: str) -> list[dict]:
    store = _default_store()
    items = store.list_records(
        user_id=DEFAULT_USER_ID,
        project_id=DEFAULT_PROJECT_ID,
        country=country or DEFAULT_COUNTRY,
        limit=1000,
    )
    return [item for item in items if item.get("session_id") == session_id]


def memory_write(input_data: MemoryWriteInput) -> MemoryWriteOutput:
    return memory_write_scoped(input_data)


def memory_write_scoped(
    input_data: MemoryWriteInput,
    *,
    user_id: str = DEFAULT_USER_ID,
    project_id: str = DEFAULT_PROJECT_ID,
    default_country: str = DEFAULT_COUNTRY,
) -> MemoryWriteOutput:
    parsed = _parse_four_class_key(input_data.key)
    if parsed is None:
        country = default_country
        session_id = None
        classified = classify_user_memory_content(input_data.value)
        if classified:
            category, content = classified
        else:
            category = "reference"
            content = input_data.value
        memory_id = input_data.key
    else:
        country, session_id, category, memory_id = parsed
        content = input_data.value

    decision = build_memory_record(
        content=content,
        category=category,
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        country=country,
        scope="user",
        memory_type="semantic",
        source="memory_tool",
        metadata={"legacy_key": input_data.key, "legacy_memory_id": memory_id},
    )
    store = _default_store()
    if decision.accepted and decision.record:
        store.add(decision.record)
        return MemoryWriteOutput(ok=True, path=str(store.db_path))
    return MemoryWriteOutput(ok=False, path=str(store.db_path))


def memory_read(input_data: MemoryReadInput) -> MemoryReadOutput:
    return memory_read_scoped(input_data)


def memory_read_scoped(
    input_data: MemoryReadInput,
    *,
    user_id: str = DEFAULT_USER_ID,
    project_id: str = DEFAULT_PROJECT_ID,
    default_country: str = DEFAULT_COUNTRY,
) -> MemoryReadOutput:
    parsed = _parse_four_class_key(input_data.key_pattern)
    store = _default_store()
    if parsed is None:
        pattern = input_data.key_pattern.replace("*", "")
        all_items = store.list_records(
            user_id=user_id,
            project_id=project_id,
            country=default_country,
            limit=1000,
        )
        filtered = [
            item
            for item in all_items
            if pattern in str(item.get("metadata", {}).get("legacy_key", ""))
            or pattern in str(item.get("content", ""))
        ]
        if filtered:
            return MemoryReadOutput(items=filtered)
        return MemoryReadOutput(
            items=store.search(
                input_data.key_pattern,
                user_id=user_id,
                project_id=project_id,
                country=default_country,
                top_k=50,
            )
        )

    country, session_id, category, _ = parsed
    items = store.list_records(
        user_id=user_id,
        project_id=project_id,
        country=country,
        limit=1000,
    )
    normalized = "preference" if category == "user" else category
    return MemoryReadOutput(
        items=[
            item
            for item in items
            if item.get("session_id") == session_id and item.get("category") == normalized
        ]
    )
