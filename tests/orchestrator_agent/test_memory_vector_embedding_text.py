from __future__ import annotations

from app.services.orchestrator_agent.memory_vector.embedding_text import (
    build_memory_embedding_text,
)


def _memory_record(**overrides):
    base = {
        "memory_id": "mem-001",
        "content": "Approved SQL case for question='top delinquency users' with hash=abc123.",
        "category": "reference",
        "memory_type": "procedural",
        "source": "m4_write_gate",
        "status": "active",
        "tags": ["data_agent_sql_case", "human_approved"],
        "metadata": {
            "api_key": "super-secret-key",
            "password": "hunter2",
            "raw_sql": "SELECT * FROM risky_table",
            "raw_citations": [{"chunk_id": "c1", "content": "secret evidence"}],
            "safe_label": "approved_sql_case",
        },
    }
    base.update(overrides)
    return base


def test_build_memory_embedding_text_is_stable_and_excludes_sensitive_metadata():
    record = _memory_record()

    first = build_memory_embedding_text(record)
    second = build_memory_embedding_text(record)

    assert first.skipped is False
    assert first.reason is None
    assert first.text == second.text
    assert first.embedding_text_hash == second.embedding_text_hash
    assert "Category: reference" in first.text
    assert "Memory type: procedural" in first.text
    assert "Source: m4_write_gate" in first.text
    assert "Tags: data_agent_sql_case, human_approved" in first.text
    assert "Approved SQL case for question='top delinquency users'" in first.text
    assert "approved_sql_case" in first.text
    assert "super-secret-key" not in first.text
    assert "hunter2" not in first.text
    assert "SELECT * FROM risky_table" not in first.text
    assert "secret evidence" not in first.text


def test_build_memory_embedding_text_skips_empty_or_inactive_memory():
    empty = build_memory_embedding_text(_memory_record(content="   "))
    inactive = build_memory_embedding_text(_memory_record(status="archived"))

    assert empty.skipped is True
    assert empty.reason == "empty_content"
    assert empty.text == ""
    assert empty.embedding_text_hash is None

    assert inactive.skipped is True
    assert inactive.reason == "inactive_memory"
    assert inactive.text == ""
    assert inactive.embedding_text_hash is None


def test_build_memory_embedding_text_truncates_long_content():
    result = build_memory_embedding_text(
        _memory_record(content="x" * 4000, metadata={"safe_label": "bulk"}),
        max_chars=300,
    )

    assert result.skipped is False
    assert len(result.text) <= 300
    assert result.text.endswith("...")
