"""Deterministic request normalization for orchestrator fast paths."""

from __future__ import annotations

import re
from typing import Any

from app.services.orchestrator_agent.request_understanding import build_request_understanding
from app.services.orchestrator_agent.schemas import NormalizedRequest


_UID_RE = re.compile(r"(?<!\d)\d{18}(?!\d)")
_SHORT_UID_RE = re.compile(r"\b[A-Za-z]{2}\d{4,}\b")
_NAMED_UID_RE = re.compile(r"\buid\s*[:：]?\s*([A-Za-z0-9_-]{4,64})\b", re.IGNORECASE)
_UID_FILE_RE = re.compile(r"(?P<path>\.?/?data/id_files/[^\s,，。；;]+)", re.IGNORECASE)
_TRACE_HINTS = ("trace", "轨迹", "路径", "深度行为解析", "churn root cause", "timeline")
_PROFILE_ACTION_HINTS = ("分析", "看下", "看看", "画像", "生成", "跑一下", "跑个", "帮我看")
_PROFILE_CONTEXT_HINTS = (
    "当前用户", "这个用户", "该用户", "当前画像", "刚才分析", "左侧结果", "画像",
    "流失风险", "征信", "信用", "app画像", "行为画像", "产品策略", "运营策略",
)
_SUMMARY_HINTS = (
    "综合画像", "用户画像", "行为画像", "行为摘要", "行为特点", "征信画像", "app画像",
    "产品策略", "运营策略", "挽留方式", "总结", "简单描述", "概括", "特点",
)
_WHY_HINTS = ("为什么", "原因", "为何", "why")
_SCRIPT_HINTS = ("客服话术", "话术", "改写", "改成客服", "触达文案", "文案")
_COMPARE_HINTS = ("对比", "比较", "哪个更", "谁更", "区别")
_RERUN_HINTS = ("重新分析", "重新跑", "刷新", "最新", "重新生成", "重跑")
_COHORT_ACTION_HINTS = ("找出", "找", "筛选", "查询", "拉取", "拉", "获取", "圈出")
_COHORT_SUBJECT_HINTS = ("用户列表", "uid列表", "uid list", "用户集合", "cohort", "批量", "一批", "分群", "高流失用户", "流失用户")
_TIME_WINDOW_HINTS = ("最近", "过去", "近", "天", "周", "月", "上周", "本周", "上个月", "本月")
_COUNTRY_HINTS = ("墨西哥", "mx", "mexico", "泰国", "th", "thailand", "哥伦比亚", "co", "colombia", "秘鲁", "pe", "peru", "智利", "cl", "chile", "巴西", "br", "brazil")
_GENERAL_CHAT_BLOCKERS = ("讨论的方案", "这个方案", "这个计划", "刚才讨论")
_UID_FILE_HINT = "data/id_files/"
_MODULE_PROMPT_HINTS: dict[str, tuple[str, ...]] = {
    "app": ("app画像", "应用画像", "app 使用", "安装应用", "app安装"),
    "behavior": ("行为画像", "行为摘要", "行为特点", "活跃度", "流失风险"),
    "credit": ("征信画像", "信用画像", "征信", "信用分", "负债"),
    "comprehensive": ("综合画像", "用户画像", "总体画像", "整体画像"),
    "product": ("产品策略", "挽留方式", "续贷策略", "产品建议"),
    "ops": ("运营策略", "催收策略", "触达策略", "运营建议"),
}


def normalize_request(prompt: str, session=None, detected_country: str | None = None) -> NormalizedRequest:
    stripped_prompt = str(prompt or "").strip()
    lowered = stripped_prompt.lower()
    focus = _detect_focus(stripped_prompt)
    uid_file_path = _extract_uid_file_path(stripped_prompt)
    if _UID_FILE_HINT in lowered and uid_file_path:
        return _build_request(
            intent="profile_batch",
            country=detected_country or getattr(session, "country", None),
            uids=[],
            uid_file_path=uid_file_path,
            modules=[],
            trace_days=7,
            application_time_hint=_workspace_application_time(session),
            request_summary=_build_request_summary(stripped_prompt, [], uid_file_path),
            query_request=None,
            read_only=False,
            prompt=stripped_prompt,
            focus=focus,
        )

    uids = _extract_uids(stripped_prompt)
    modules = _detect_requested_modules(stripped_prompt)
    country = detected_country or getattr(session, "country", None)
    trace_days = _extract_trace_days(stripped_prompt)
    request_summary = _build_request_summary(stripped_prompt, uids, uid_file_path)
    rerun_requested = _has_any(stripped_prompt, _RERUN_HINTS)
    workspace_context = _has_workspace_context(session)
    if not uids and rerun_requested:
        inferred_uids = _workspace_uids(session)
        if len(inferred_uids) == 1:
            uids = inferred_uids
            request_summary = _build_request_summary(stripped_prompt, uids)

    if uids and _has_any(stripped_prompt, _TRACE_HINTS):
        return _build_request(
            intent="run_trace",
            country=country,
            uids=[uids[0]],
            uid_file_path=None,
            modules=modules or ["behavior"],
            trace_days=trace_days,
            application_time_hint=_workspace_application_time(session),
            request_summary=request_summary,
            query_request=None,
            read_only=False,
            prompt=stripped_prompt,
            focus=focus or ["trace"],
        )

    if _looks_like_read_only(stripped_prompt, workspace_context=workspace_context) and not rerun_requested:
        if workspace_context or _references_current_profile(stripped_prompt):
            return _build_request(
                intent="answer_from_workspace",
                country=country,
                uids=uids,
                uid_file_path=None,
                modules=modules or ["comprehensive"],
                trace_days=trace_days,
                application_time_hint=_workspace_application_time(session),
                request_summary=request_summary,
                query_request=None,
                read_only=True,
                prompt=stripped_prompt,
                focus=focus,
            )

    if uids:
        base_focus = focus or (["rerun"] if rerun_requested else [])
        if rerun_requested and "rerun" not in base_focus:
            base_focus = base_focus + ["rerun"]
        return _build_request(
            intent="profile_uid" if len(uids) == 1 else "profile_batch",
            country=country,
            uids=uids,
            uid_file_path=None,
            modules=modules,
            trace_days=trace_days,
            application_time_hint=_workspace_application_time(session),
            request_summary=request_summary,
            query_request=None,
            read_only=False,
            prompt=stripped_prompt,
            focus=base_focus,
        )

    if _looks_like_cohort_request(stripped_prompt):
        return _build_request(
            intent="query_data_then_profile",
            country=country,
            uids=[],
            uid_file_path=None,
            modules=modules,
            trace_days=trace_days,
            application_time_hint=_workspace_application_time(session),
            request_summary=request_summary,
            query_request=stripped_prompt,
            read_only=False,
            prompt=stripped_prompt,
            focus=focus or ["cohort"],
        )

    if _looks_like_ambiguous_cohort_request(stripped_prompt):
        missing_slots: list[str] = []
        if not _has_explicit_country(stripped_prompt):
            missing_slots.append("country")
        if not _has_time_window(stripped_prompt):
            missing_slots.append("time_window")
        candidate_defaults: dict[str, Any] = {}
        if country:
            candidate_defaults["country"] = country
        candidate_defaults["time_window"] = "最近 7 天"
        candidate_defaults["auto_profile"] = True
        clarification_prompt = "请补充国家和时间范围，例如：墨西哥、最近 7 天。"
        return _build_request(
            intent="need_clarification",
            country=country,
            uids=[],
            uid_file_path=None,
            modules=modules,
            trace_days=trace_days,
            application_time_hint=_workspace_application_time(session),
            request_summary=request_summary,
            query_request=stripped_prompt,
            read_only=False,
            prompt=stripped_prompt,
            focus=focus or ["cohort"],
            missing_slots=missing_slots,
            clarification_prompt=clarification_prompt,
            candidate_defaults=candidate_defaults,
        )

    return _build_request(
        intent="general_chat",
        country=country,
        uids=[],
        uid_file_path=None,
        modules=[],
        trace_days=trace_days,
        application_time_hint=_workspace_application_time(session),
        request_summary=request_summary,
        query_request=None,
        read_only=False,
        prompt=stripped_prompt,
        focus=focus,
    )


def _extract_uids(prompt: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for matched in _NAMED_UID_RE.findall(prompt or ""):
        if matched in seen:
            continue
        seen.add(matched)
        ordered.append(matched)
    for matched in _UID_RE.findall(prompt or ""):
        if matched in seen:
            continue
        seen.add(matched)
        ordered.append(matched)
    for matched in _SHORT_UID_RE.findall(prompt or ""):
        if matched in seen:
            continue
        seen.add(matched)
        ordered.append(matched)
    return ordered


def _extract_uid_file_path(prompt: str) -> str | None:
    matched = _UID_FILE_RE.search(prompt or "")
    if not matched:
        return None
    return matched.group("path")


def _looks_like_read_only(prompt: str, *, workspace_context: bool) -> bool:
    focus = _detect_focus(prompt)
    if not focus:
        return False
    if _has_any(prompt, _GENERAL_CHAT_BLOCKERS) and not workspace_context:
        return False
    if "summary" in focus and not workspace_context and not _references_current_profile(prompt):
        return False
    return True


def _looks_like_cohort_request(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return (
        any(keyword.lower() in lowered for keyword in _COHORT_ACTION_HINTS)
        and any(keyword.lower() in lowered for keyword in _COHORT_SUBJECT_HINTS)
        and _has_time_window(prompt)
    )


def _looks_like_ambiguous_cohort_request(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return (
        any(keyword.lower() in lowered for keyword in _COHORT_ACTION_HINTS)
        and any(keyword.lower() in lowered for keyword in _COHORT_SUBJECT_HINTS)
        and (not _has_explicit_country(prompt) or not _has_time_window(prompt))
    )


def _has_time_window(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return any(keyword.lower() in lowered for keyword in _TIME_WINDOW_HINTS)


def _has_explicit_country(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return any(keyword.lower() in lowered for keyword in _COUNTRY_HINTS)


def _references_current_profile(prompt: str) -> bool:
    lowered = str(prompt or "").lower()
    return any(keyword.lower() in lowered for keyword in _PROFILE_CONTEXT_HINTS)


def _detect_requested_modules(prompt: str) -> list[str]:
    lowered = prompt.lower()
    matched: list[str] = []
    for module_name, hints in _MODULE_PROMPT_HINTS.items():
        if any(keyword.lower() in lowered for keyword in hints):
            matched.append(module_name)
    return matched


def _build_request_summary(prompt: str, uids: list[str], uid_file_path: str | None = None) -> str:
    if uid_file_path:
        return f"分析 UID 文件 {uid_file_path} 的批量画像请求"
    if uids:
        if len(uids) == 1:
            return f"分析 UID {uids[0]} 的画像请求"
        return f"分析 {len(uids)} 个 UID 的批量画像请求"
    compact = " ".join(prompt.split())
    return compact[:120] or "自然语言分析请求"


def _build_request(
    *,
    intent: str,
    country: str | None,
    uids: list[str],
    uid_file_path: str | None,
    modules: list[str],
    trace_days: int,
    application_time_hint: str | None,
    request_summary: str,
    query_request: str | None,
    read_only: bool,
    prompt: str,
    focus: list[str],
    missing_slots: list[str] | None = None,
    clarification_prompt: str | None = None,
    candidate_defaults: dict[str, Any] | None = None,
) -> NormalizedRequest:
    return NormalizedRequest(
        intent=intent,
        country=country,
        uids=uids,
        uid_file_path=uid_file_path,
        modules=modules,
        trace_days=trace_days,
        application_time_hint=application_time_hint,
        request_summary=request_summary,
        query_request=query_request,
        read_only=read_only,
        request_understanding=build_request_understanding(
            prompt=prompt,
            intent=intent,
            uids=uids,
            focus=focus,
            trace_days=trace_days,
            missing_slots=missing_slots,
            clarification_prompt=clarification_prompt,
            candidate_defaults=candidate_defaults,
        ),
    )


def _detect_focus(prompt: str) -> list[str]:
    detected: list[str] = []
    if _has_any(prompt, _WHY_HINTS):
        detected.append("why")
    if _has_any(prompt, _SCRIPT_HINTS):
        detected.append("customer_script")
    if _has_any(prompt, _COMPARE_HINTS):
        detected.append("comparison")
    if _has_any(prompt, _SUMMARY_HINTS):
        detected.append("summary")
    return detected


def _extract_trace_days(prompt: str) -> int:
    compact = str(prompt or "")
    matched = re.search(r"(最近|过去|近)\s*(\d{1,2})\s*天", compact)
    if matched:
        value = int(matched.group(2))
        return max(1, min(value, 90))
    return 7


def _workspace_application_time(session: Any) -> str | None:
    snapshot = getattr(session, "active_entities", {}).get("workspace_snapshot") if session else None
    if isinstance(snapshot, dict):
        value = snapshot.get("applicationTime")
        if value:
            return str(value)
    return None


def _has_workspace_context(session: Any) -> bool:
    if session is None:
        return False
    snapshot = getattr(session, "active_entities", {}).get("workspace_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("results"):
        return True
    tool_calls = getattr(session, "tool_calls", []) or []
    return any(
        getattr(record, "tool_name", None) in {"run_profile", "run_trace"}
        and getattr(record, "status", None) == "done"
        for record in tool_calls
    )


def _workspace_uids(session: Any) -> list[str]:
    if session is None:
        return []
    seen: list[str] = []
    snapshot = getattr(session, "active_entities", {}).get("workspace_snapshot")
    if isinstance(snapshot, dict):
        rows = snapshot.get("results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = str(row.get("uid") or "").strip()
            if uid and uid not in seen:
                seen.append(uid)
    tool_calls = getattr(session, "tool_calls", []) or []
    for record in tool_calls:
        if getattr(record, "tool_name", None) != "run_profile" or getattr(record, "status", None) != "done":
            continue
        output = getattr(record, "output", None)
        rows = output.get("results") if isinstance(output, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            uid = str(row.get("uid") or "").strip()
            if uid and uid not in seen:
                seen.append(uid)
    return seen


def _has_any(prompt: str, keywords: tuple[str, ...]) -> bool:
    lowered = str(prompt or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)
