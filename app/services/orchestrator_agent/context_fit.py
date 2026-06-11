"""ensure_context_fits + load_session_memories (Plan 10 Phase 4 / v3.2 + Errata).

集成入口：agent_loop.py 首轮调 load_session_memories；每轮 tool 落盘后调 ensure_context_fits。
"""
from __future__ import annotations

import logging
import os

from .memory_flush import memory_flush
from .memory_manager import (
    compress_iteratively,
    compress_level_1,
    compress_level_2,
    compress_level_4,
)
from .summarizer import iterative_summarize, summarize_messages
from .tools.memory import read_all_categories

logger = logging.getLogger(__name__)


COMPRESSION_THRESHOLD = 0.80
MODEL_MAX_TOKENS_PER_TURN = 800_000
MAX_MEMORY_ITEMS = 50

_warned_session_ids: set[str] = set()


def estimate_tokens(messages: list) -> int:
    total = 0
    for m in messages:
        if hasattr(m, "content"):
            content = m.content
        else:
            content = m.get("content", "")
        if isinstance(content, str):
            total += len(content) // 3
    return total


def load_session_memories(session_id: str, country: str = "mx") -> str:
    items = read_all_categories(country, session_id)
    if not items:
        return ""

    truncated = False
    if len(items) > MAX_MEMORY_ITEMS:
        if session_id not in _warned_session_ids:
            logger.warning(
                "load_session_memories session=%s country=%s 记忆 %d 超 %d，仅加载最近 %d 条",
                session_id,
                country,
                len(items),
                MAX_MEMORY_ITEMS,
                MAX_MEMORY_ITEMS,
            )
            _warned_session_ids.add(session_id)
        items = items[-MAX_MEMORY_ITEMS:]
        truncated = True

    by_cat: dict[str, list[str]] = {
        "preference": [],
        "feedback": [],
        "project": [],
        "reference": [],
        "task": [],
        "insight": [],
    }
    for it in items:
        cat = it.get("category")
        if cat in by_cat:
            by_cat[cat].append(str(it.get("content", "")))

    parts = ["## 历史记忆"]
    for cat, contents in by_cat.items():
        if contents:
            parts.append(f"### {cat}")
            for c in contents:
                parts.append(f"- {c}")
    if truncated:
        parts.append(f"\n> 提示：本 session 容量已超 {MAX_MEMORY_ITEMS}，只加载最近条目")
    return "\n".join(parts)


def ensure_context_fits(session, country: str, max_tokens: int) -> bool:
    if os.getenv("MEMORY_COMPRESSION_ENABLED", "1") == "0":
        return False

    if estimate_tokens(session.messages) / max_tokens < COMPRESSION_THRESHOLD:
        return False

    memory_flush(
        session.messages,
        session.session_id,
        country or "mx",
        user_id=getattr(session, "user_id", None),
        project_id=getattr(session, "project_id", None),
    )

    msgs = session.messages
    msgs = compress_level_1(msgs)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_level_2(msgs, session.tool_calls)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_iteratively(msgs, summarize_messages, iterative_summarize)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_level_4(msgs, summarize_messages)

    session.messages = msgs
    return True
