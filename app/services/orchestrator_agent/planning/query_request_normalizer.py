"""Internal-only query request normalization helpers for query_data paths."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from app.services.orchestrator_agent.schemas import RequestUnderstanding


_HINT_MARKER = "[Normalized query hints]"
_HINT_BLOCK_RE = re.compile(r"\n\n\[Normalized query hints\]\n.*\Z", re.DOTALL)

_TIME_WINDOW_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("last_7_days", "最近7天", re.compile(r"(过去|最近)\s*7\s*天")),
    ("last_30_days", "过去30天", re.compile(r"(过去\s*30\s*天|近一个月|最近一个月)")),
    ("last_90_days", "最近三个月", re.compile(r"(最近\s*三个月|过去\s*90\s*天)")),
    ("current_month", "本月", re.compile(r"本月")),
    ("previous_month", "上个月", re.compile(r"上个月")),
]

_PROFILE_NEGATIVE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"不要画像",
        r"不需要画像",
        r"别画像",
        r"只给我\s*uid",
        r"只要\s*uid",
        r"不要分析",
        r"不继续画像",
        r"no profile",
    )
]
_PROFILE_POSITIVE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"画像",
        r"分析画像",
        r"生成画像",
        r"自动画像",
        r"跑画像",
        r"\bprofile\b",
    )
]
_QUERY_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"筛选",
        r"找出",
        r"找一批",
        r"拉一批",
        r"用户列表",
        r"查询",
        r"cohort",
        r"uid",
    )
]

_FILTER_RULES: list[tuple[str, list[re.Pattern[str]]]] = [
    ("active users", [re.compile(r"活跃"), re.compile(r"登录")]),
    ("loan applicants", [re.compile(r"贷款"), re.compile(r"借款"), re.compile(r"申请贷款"), re.compile(r"借贷")]),
    ("overdue users", [re.compile(r"逾期"), re.compile(r"overdue")]),
    ("app installed users", [re.compile(r"安装.*app"), re.compile(r"app.*安装"), re.compile(r"installed app")]),
]

_LATIN_COUNTRY_ALIASES = {
    "mx": "mx",
    "mexico": "mx",
    "méxico": "mx",
    "th": "th",
    "thailand": "th",
}

_CJK_COUNTRY_ALIASES = {
    "墨西哥": "mx",
    "泰国": "th",
}

_TRUE_STRINGS = {"true", "1", "yes", "y", "是", "true.", "ok"}
_FALSE_STRINGS = {"false", "0", "no", "n", "否", "不要", "false.", "cancel"}


@dataclass(frozen=True, slots=True)
class NormalizedQueryRequest:
    original_text: str
    effective_request_text: str
    country: str | None
    time_window_key: str | None
    time_window_label: str | None
    query_mode: Literal["query_only", "query_profile", "unknown"]
    auto_profile: bool | None
    filters_summary: list[str]
    warnings: list[str]


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


def _strip_existing_hints_block(text: str) -> str:
    return _HINT_BLOCK_RE.sub("", text.rstrip())


def _normalize_country_alias(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = _normalize_text(raw)
    if normalized in _LATIN_COUNTRY_ALIASES:
        return _LATIN_COUNTRY_ALIASES[normalized]
    if raw in _CJK_COUNTRY_ALIASES:
        return _CJK_COUNTRY_ALIASES[raw]
    return None


def _contains_latin_alias(text: str, alias: str) -> bool:
    return bool(
        re.search(
            rf"(?<![a-z0-9_]){re.escape(alias)}(?![a-z0-9_])",
            text,
        )
    )


def _detect_country(
    *,
    request_text: str,
    country_hint: str | None,
    request_understanding: RequestUnderstanding | None,
) -> str | None:
    explicit = _normalize_country_alias(country_hint)
    if explicit is not None:
        return explicit
    candidate_country = _normalize_country_alias((request_understanding.candidate_defaults or {}).get("country") if request_understanding else None)
    if candidate_country is not None:
        return candidate_country

    normalized = _normalize_text(request_text)
    for alias, canonical in _CJK_COUNTRY_ALIASES.items():
        if alias in request_text:
            return canonical
    for alias, canonical in _LATIN_COUNTRY_ALIASES.items():
        if _contains_latin_alias(normalized, _normalize_text(alias)):
            return canonical
    return None


def _detect_time_window(
    request_text: str,
    clarification_answers: Mapping[str, Any] | None,
) -> tuple[str | None, str | None]:
    sources = []
    explicit_time_window = clarification_answers.get("time_window") if clarification_answers else None
    if explicit_time_window:
        sources.append(str(explicit_time_window))
    sources.append(request_text)
    for source in sources:
        for key, label, pattern in _TIME_WINDOW_RULES:
            if pattern.search(source):
                return key, label
    return None, None


def _parse_explicit_auto_profile(clarification_answers: Mapping[str, Any] | None) -> tuple[bool | None, str | None]:
    if not clarification_answers or "auto_profile" not in clarification_answers:
        return None, None
    value = clarification_answers.get("auto_profile")
    if isinstance(value, bool):
        return value, None
    if isinstance(value, str):
        normalized = _normalize_text(value).strip()
        if normalized in _TRUE_STRINGS:
            return True, None
        if normalized in _FALSE_STRINGS:
            return False, None
        return None, f"ignored non-boolean auto_profile value: {value!r}"
    return None, f"ignored unsupported auto_profile value type: {type(value).__name__}"


def _infer_query_mode(request_text: str) -> Literal["query_only", "query_profile", "unknown"]:
    normalized = _normalize_text(request_text)
    has_negative_profile = any(pattern.search(normalized) for pattern in _PROFILE_NEGATIVE_PATTERNS)
    has_profile = (not has_negative_profile) and any(pattern.search(normalized) for pattern in _PROFILE_POSITIVE_PATTERNS)
    has_query = any(pattern.search(normalized) for pattern in _QUERY_PATTERNS)
    if has_profile and has_query:
        return "query_profile"
    if has_query:
        return "query_only"
    if has_profile:
        return "unknown"
    return "unknown"


def _detect_filters_summary(request_text: str) -> list[str]:
    normalized = _normalize_text(request_text)
    if any(token in normalized for token in ("select ", "drop ", "truncate ", "insert ", "update ", "delete ")):
        pass
    items: list[str] = []
    for label, patterns in _FILTER_RULES:
        if any(pattern.search(normalized) for pattern in patterns):
            items.append(label)
    return items


def _build_effective_request_text(
    *,
    original_text: str,
    country: str | None,
    time_window_key: str | None,
    query_mode: Literal["query_only", "query_profile", "unknown"],
    auto_profile: bool | None,
    filters_summary: list[str],
) -> str:
    base_text = _strip_existing_hints_block(original_text)
    hint_lines = [_HINT_MARKER]
    if country:
        hint_lines.append(f"country: {country}")
    if time_window_key:
        hint_lines.append(f"time_window: {time_window_key}")
    if query_mode != "unknown":
        hint_lines.append(f"query_mode: {query_mode}")
    if auto_profile is not None:
        hint_lines.append(f"auto_profile: {'true' if auto_profile else 'false'}")
    if filters_summary:
        hint_lines.append("filters_summary:")
        hint_lines.extend(f"- {item}" for item in filters_summary)
    if len(hint_lines) == 1:
        return base_text
    return f"{base_text}\n\n" + "\n".join(hint_lines)


def normalize_query_request(
    *,
    request_text: str,
    country_hint: str | None,
    request_understanding: RequestUnderstanding | None = None,
    clarification_answers: Mapping[str, Any] | None = None,
    default_query_mode: Literal["query_only", "query_profile", "unknown"] = "unknown",
    default_auto_profile: bool | None = None,
) -> NormalizedQueryRequest:
    warnings: list[str] = []
    base_text = _strip_existing_hints_block(request_text or "")
    explicit_auto_profile, auto_profile_warning = _parse_explicit_auto_profile(clarification_answers)
    if auto_profile_warning is not None:
        warnings.append(auto_profile_warning)
    country = _detect_country(
        request_text=base_text,
        country_hint=country_hint,
        request_understanding=request_understanding,
    )
    time_window_key, time_window_label = _detect_time_window(
        base_text,
        clarification_answers,
    )
    inferred_query_mode = _infer_query_mode(base_text)
    if explicit_auto_profile is True:
        query_mode: Literal["query_only", "query_profile", "unknown"] = "query_profile"
    elif explicit_auto_profile is False:
        query_mode = "query_only"
    elif default_auto_profile is True and default_query_mode == "query_profile":
        query_mode = "query_profile"
    elif default_auto_profile is False and default_query_mode == "query_only":
        query_mode = "query_only"
    elif inferred_query_mode != "unknown":
        query_mode = inferred_query_mode
    else:
        query_mode = default_query_mode

    if explicit_auto_profile is not None:
        auto_profile = explicit_auto_profile
    elif default_auto_profile is not None:
        auto_profile = default_auto_profile
    elif query_mode == "query_profile":
        auto_profile = True
    elif query_mode == "query_only":
        auto_profile = False
    else:
        auto_profile = None

    filters_summary = _detect_filters_summary(base_text)
    effective_request_text = _build_effective_request_text(
        original_text=base_text,
        country=country,
        time_window_key=time_window_key,
        query_mode=query_mode,
        auto_profile=auto_profile,
        filters_summary=filters_summary,
    )
    return NormalizedQueryRequest(
        original_text=base_text,
        effective_request_text=effective_request_text,
        country=country,
        time_window_key=time_window_key,
        time_window_label=time_window_label,
        query_mode=query_mode,
        auto_profile=auto_profile,
        filters_summary=filters_summary,
        warnings=warnings,
    )
