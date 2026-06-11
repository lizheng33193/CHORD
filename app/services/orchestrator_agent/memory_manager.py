"""Multi-level message compression (Plan 10 Phase 2 / v3.2).

走项目原生 OrchestratorMessage + ToolCallRecord。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage,
    ToolCallRecord,
)


TAIL_PROTECT = 5
HEAD_PROTECT = 1
_TRUNCATED_PREFIX = "[已裁剪：原长度 "
_DEDUPED_MARKER = "[结果重复，已去重]"
_SUMMARY_PREFIX = "[历史对话摘要"


def compress_level_1(messages: list[OrchestratorMessage]) -> list[OrchestratorMessage]:
    cutoff = max(0, len(messages) - TAIL_PROTECT)
    for msg in messages[:cutoff]:
        if msg.role == "tool" and isinstance(msg.content, str) and len(msg.content) > 200:
            msg.content = f"{_TRUNCATED_PREFIX}{len(msg.content)} 字符]"
    return messages


def _hash_payload(payload: object) -> str:
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def compress_level_2(
    messages: list[OrchestratorMessage],
    tool_calls: list[ToolCallRecord],
) -> list[OrchestratorMessage]:
    if not tool_calls:
        return messages

    tail_ids = {
        m.tool_call_id
        for m in messages[-TAIL_PROTECT:]
        if m.role == "tool" and m.tool_call_id
    }

    seen_keys: dict[tuple[str, str, str], str] = {}
    duplicate_ids: set[str] = set()
    for rec in tool_calls:
        if rec.status != "done" or not rec.tool_call_id:
            continue
        if rec.tool_call_id in tail_ids:
            continue
        key = (
            rec.tool_name,
            _hash_payload(rec.input),
            _hash_payload(rec.output),
        )
        if key in seen_keys:
            duplicate_ids.add(rec.tool_call_id)
        else:
            seen_keys[key] = rec.tool_call_id

    for msg in messages:
        if msg.role == "tool" and msg.tool_call_id in duplicate_ids:
            msg.content = _DEDUPED_MARKER
    return messages


def align_tool_pairs(messages: list[OrchestratorMessage]) -> list[OrchestratorMessage]:
    cleaned: list[OrchestratorMessage] = []
    for msg in messages:
        if not cleaned and msg.role == "tool":
            continue
        cleaned.append(msg)
    return cleaned


def _to_dicts(messages: list[OrchestratorMessage]) -> list[dict]:
    return [m.model_dump() for m in messages]


def compress_level_3(
    messages: list[OrchestratorMessage],
    summarize_fn: Callable[[list[dict]], str],
) -> list[OrchestratorMessage]:
    if len(messages) <= HEAD_PROTECT + TAIL_PROTECT:
        return messages

    head = messages[:HEAD_PROTECT]
    tail = messages[-TAIL_PROTECT:]
    middle = messages[HEAD_PROTECT:-TAIL_PROTECT]
    middle = align_tool_pairs(middle)

    summary_text = summarize_fn(_to_dicts(middle))
    summary_msg = OrchestratorMessage(
        role="assistant",
        content=(
            f"{_SUMMARY_PREFIX} — 覆盖第 {HEAD_PROTECT + 1} 至第 {len(messages) - TAIL_PROTECT} 轮]\n\n"
            f"{summary_text}"
        ),
        timestamp=datetime.now(timezone.utc),
    )
    return head + [summary_msg] + tail


def compress_level_4(
    messages: list[OrchestratorMessage],
    full_summarize_fn: Callable[[list[dict]], str],
) -> list[OrchestratorMessage]:
    summary = full_summarize_fn(_to_dicts(messages))
    return [
        OrchestratorMessage(
            role="assistant",
            content=summary,
            timestamp=datetime.now(timezone.utc),
        )
    ]


def compress_iteratively(
    messages: list[OrchestratorMessage],
    summarize_fn: Callable[[list[dict]], str],
    iterative_summarize_fn: Callable[[str, list[dict]], str],
) -> list[OrchestratorMessage]:
    existing_idx: int | None = None
    for i, msg in enumerate(messages):
        if (
            msg.role == "assistant"
            and isinstance(msg.content, str)
            and msg.content.startswith(_SUMMARY_PREFIX)
        ):
            existing_idx = i
            break

    if existing_idx is None:
        return compress_level_3(messages, summarize_fn)

    head = messages[:existing_idx]
    existing_summary = messages[existing_idx].content
    new_messages = messages[existing_idx + 1 : -TAIL_PROTECT]
    tail = messages[-TAIL_PROTECT:]

    new_summary = iterative_summarize_fn(existing_summary, _to_dicts(new_messages))
    summary_msg = OrchestratorMessage(
        role="assistant",
        content=new_summary,
        timestamp=datetime.now(timezone.utc),
    )
    return head + [summary_msg] + tail
