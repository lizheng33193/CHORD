"""Conservative write policy for Orchestrator long-term memories."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from data_acquisition_agent.redactor import redact

from app.services.orchestrator_agent.memory_store import (
    DEFAULT_COUNTRY,
    DEFAULT_PROJECT_ID,
    DEFAULT_USER_ID,
    MemoryRecord,
    build_scope_dedupe_key,
    make_memory_id,
)


CATEGORY_ALIASES = {
    "user": "preference",
    "preference": "preference",
    "feedback": "feedback",
    "project": "project",
    "reference": "reference",
    "task": "task",
    "insight": "insight",
}

AUTO_SOURCES = {"orchestrator_user_prompt", "orchestrator_final", "memory_flush"}

CATEGORY_IMPORTANCE = {
    "preference": 0.85,
    "feedback": 0.8,
    "project": 0.75,
    "reference": 0.65,
    "task": 0.6,
    "insight": 0.7,
}

MIN_IMPORTANCE = 0.55
MAX_CONTENT_CHARS = 2000

_GREETING_OR_FILLER_RE = re.compile(
    r"^\s*(你好|您好|hi|hello|hey|谢谢|多谢|thanks|thank you|好的|好|ok|okay|收到|嗯|嗯嗯|啊|是的|对|没事)[。.!！,\s]*$",
    re.IGNORECASE,
)
_MODEL_IDENTITY_RE = re.compile(
    r"(你是什么模型|什么模型|你是谁|自我介绍|what model|which model|who are you|模型名称|模型版本)",
    re.IGNORECASE,
)
_ASSISTANT_SELF_INTRO_RE = re.compile(
    r"(我是一个用于|我是.*编排代理|我的职责是|我无法回忆|无法直接回忆|请提供具体的分析任务)",
    re.IGNORECASE,
)
_REFERENCE_RE = re.compile(
    r"(https?://|/[\w.\-/]+|\b[\w.\-]+\.(md|py|json|yaml|yml|csv|txt)\b|docs/|app/|tests/|api/|endpoint|接口|链接|入口|参考资料|reference)",
    re.IGNORECASE,
)
_PREFERENCE_RE = re.compile(
    r"(偏好|喜欢|希望|以后|默认|请记住|记住|请用|请使用|不要|不希望|prefer|preference|default|always|never|use .*output|中文输出|简洁)",
    re.IGNORECASE,
)
_FEEDBACK_RE = re.compile(
    r"(纠正|反馈|不对|错了|不是|应该|改成|修正|别|不要再|以后不要|correction|feedback|wrong|should)",
    re.IGNORECASE,
)
_PROJECT_RE = re.compile(
    r"(项目|当前|已经|已完成|决定|决策|目标|范围|schema|sqlite|orchestrator|memory|uid|画像|上线|实现|project|decision|implemented)",
    re.IGNORECASE,
)
_PROJECT_FACT_RE = re.compile(
    r"(项目事实|当前项目|默认国家|当前默认国家|已确认|已完成|决定|决策)",
    re.IGNORECASE,
)
_TASK_RE = re.compile(
    r"(分析|画像|查询|取数|运行|追踪|trace|run_profile|用户|任务|召回|实现|优化|修复|测试|检查|生成|profile|query|analy[sz]e|implement|test|fix|run)",
    re.IGNORECASE,
)
_INSIGHT_RE = re.compile(
    r"(关键发现|结论|风险|原因|显示|表明|画像|分析结果|insight|finding|risk|summary)",
    re.IGNORECASE,
)


@dataclass
class MemoryDecision:
    accepted: bool
    reason: str
    record: MemoryRecord | None = None
    redaction_hits: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def build_memory_record(
    *,
    content: str,
    category: str,
    user_id: str = DEFAULT_USER_ID,
    project_id: str = DEFAULT_PROJECT_ID,
    session_id: str | None = None,
    country: str = DEFAULT_COUNTRY,
    scope: str = "user",
    memory_type: str = "semantic",
    source: str = "memory_policy",
    tags: list[str] | None = None,
    importance: float | None = None,
    confidence: float = 0.8,
    metadata: dict[str, Any] | None = None,
) -> MemoryDecision:
    raw = str(content or "").strip()
    normalized_category = CATEGORY_ALIASES.get(str(category or "").strip().lower())
    if normalized_category is None:
        return MemoryDecision(False, "unsupported_category")
    if not raw:
        return MemoryDecision(False, "empty_content")
    if len(raw) < 4:
        return MemoryDecision(False, "too_short")
    if _looks_like_standalone_secret(raw):
        return MemoryDecision(False, "standalone_secret")
    if _is_low_value_chat(raw):
        return MemoryDecision(False, "low_value_chat")
    if not _category_accepts(raw, normalized_category, source):
        return MemoryDecision(False, "category_whitelist")

    redacted, hits = redact(raw)
    redacted = _compact(redacted)
    if len(redacted) > MAX_CONTENT_CHARS:
        redacted = redacted[:MAX_CONTENT_CHARS].rstrip()

    score = float(importance if importance is not None else CATEGORY_IMPORTANCE[normalized_category])
    if score < MIN_IMPORTANCE:
        return MemoryDecision(False, "low_importance", redaction_hits=hits)

    metadata = dict(metadata or {})
    if hits:
        metadata["redaction_hits"] = hits
    dedupe_key = build_scope_dedupe_key(
        scope=scope,
        user_id=user_id,
        project_id=project_id,
        country=(country or DEFAULT_COUNTRY).lower(),
        session_id=session_id,
        category=normalized_category,
        content=redacted,
    )
    record = MemoryRecord(
        memory_id=make_memory_id(),
        scope=scope,
        user_id=user_id or DEFAULT_USER_ID,
        project_id=project_id or DEFAULT_PROJECT_ID,
        session_id=session_id,
        country=(country or DEFAULT_COUNTRY).lower(),
        category=normalized_category,
        memory_type=memory_type,
        content=redacted,
        importance=score,
        confidence=max(0.0, min(1.0, float(confidence))),
        tags=tags or [],
        source=source,
        dedupe_key=dedupe_key,
        metadata=metadata,
    )
    return MemoryDecision(True, "accepted", record=record, redaction_hits=hits, metadata=metadata)


def classify_user_memory_content(content: str) -> tuple[str, str] | None:
    """Classify user text for conservative automatic long-term memory writes.

    Returns (category, normalized_content) when the text has durable value.
    """
    text = _compact(content)
    if not text or _is_low_value_chat(text):
        return None
    if _REFERENCE_RE.search(text):
        return "reference", extract_task_summary(text)
    if _FEEDBACK_RE.search(text):
        return "feedback", extract_task_summary(text)
    if _PROJECT_FACT_RE.search(text):
        return "project", extract_task_summary(text)
    if _PREFERENCE_RE.search(text):
        return "preference", extract_task_summary(text)
    if _PROJECT_RE.search(text) and not _TASK_RE.search(text):
        return "project", extract_task_summary(text)
    if _TASK_RE.search(text):
        return "task", extract_task_summary(text)
    if _PROJECT_RE.search(text):
        return "project", extract_task_summary(text)
    return None


def extract_task_summary(content: str, max_chars: int = 600) -> str:
    text = _compact(content)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_low_value_chat(text: str) -> bool:
    compacted = _compact(text)
    if not compacted:
        return True
    if _GREETING_OR_FILLER_RE.fullmatch(compacted):
        return True
    if _MODEL_IDENTITY_RE.search(compacted):
        return True
    if _ASSISTANT_SELF_INTRO_RE.search(compacted):
        return True
    return False


def _category_accepts(text: str, category: str, source: str) -> bool:
    if source == "orchestrator_final":
        return False
    if category == "preference":
        return bool(_PREFERENCE_RE.search(text))
    if category == "feedback":
        return bool(_FEEDBACK_RE.search(text) or _PREFERENCE_RE.search(text))
    if category == "project":
        return bool(_PROJECT_RE.search(text))
    if category == "reference":
        return bool(_REFERENCE_RE.search(text))
    if category == "task":
        return bool(_TASK_RE.search(text))
    if category == "insight":
        return source not in AUTO_SOURCES and bool(_INSIGHT_RE.search(text))
    return False


def _looks_like_standalone_secret(text: str) -> bool:
    stripped = text.strip()
    lower = stripped.lower()
    if re.fullmatch(
        r"(host|port|user|password|database|token|api_key|access_token|secret|key)\s*=\s*['\"]?[^'\"]+['\"]?",
        lower,
    ):
        return True
    if re.fullmatch(r"authorization\s*:\s*bearer\s+\S+", lower):
        return True
    return False
