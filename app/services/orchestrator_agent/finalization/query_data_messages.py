"""Pure message helpers for query_data terminal and observation UX."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _cohort_size_from_output(output: dict[str, Any], *, limit: int) -> int | None:
    reason = str(output.get("reason") or "").strip().lower()
    if reason == "cohort_too_large":
        cohort_size = output.get("cohort_size")
        if isinstance(cohort_size, int) and cohort_size > 0:
            return cohort_size
        rows_estimated = output.get("rows_estimated")
        if isinstance(rows_estimated, int) and rows_estimated > limit:
            return rows_estimated
        uids = output.get("uids")
        if isinstance(uids, list) and len(uids) > limit:
            return len(uids)
    cohort_size = output.get("cohort_size")
    if isinstance(cohort_size, int) and cohort_size > 0:
        return cohort_size
    rows_estimated = output.get("rows_estimated")
    if isinstance(rows_estimated, int) and rows_estimated > 0:
        return rows_estimated
    uids = output.get("uids")
    if isinstance(uids, list) and uids:
        return len(uids)
    return None


def build_query_data_preview_text(
    *,
    query_mode: str | None,
    country: str | None,
    time_window_label: str | None,
    filters_summary: Sequence[str] | None,
    raw_sql: str | None,
    rows_estimated: int | None = None,
) -> str:
    raw_sql_text = str(raw_sql or "").strip()
    summary = (
        "本次将先筛选符合条件的用户；确认后，这批 UID 将继续用于画像分析。"
        if query_mode == "query_profile"
        else "本次将筛选符合条件的用户，并返回可用于后续分析的 UID 列表。"
    )

    lines = [
        "查询摘要：",
        summary,
        "",
    ]

    filter_lines: list[str] = []
    if country:
        filter_lines.append(f"- 国家/市场：{country}")
    if time_window_label:
        filter_lines.append(f"- 时间范围：{time_window_label}")
    normalized_filters = [str(item).strip() for item in (filters_summary or []) if str(item).strip()]
    if normalized_filters:
        filter_lines.append(f"- 条件：{'；'.join(normalized_filters)}")
    if isinstance(rows_estimated, int) and rows_estimated > 0:
        filter_lines.append(f"- 预计影响范围：约 {rows_estimated} 行")
    if filter_lines:
        lines.extend(["筛选条件：", *filter_lines, ""])

    lines.extend(
        [
            "确认提示：",
            "该查询仅会在你确认后执行。请确认筛选范围是否符合预期。",
            "",
            "原始 SQL：",
            raw_sql_text or "未提供 SQL 预览",
        ]
    )
    return "\n".join(lines).strip()


def build_query_empty_message(*, query_mode: str) -> str:
    if query_mode == "query_profile":
        return (
            "已完成查询，但当前条件下没有命中用户，因此没有可继续画像的 UID，本次不会启动画像分析。\n\n"
            "你可以尝试放宽筛选条件，例如扩大时间范围、减少限制条件，或改用更宽泛的用户行为条件后重新查询。"
        )
    return (
        "已完成查询，但当前条件下没有命中用户，UID 数量：0。\n\n"
        "你可以尝试放宽筛选条件，例如扩大时间范围、减少限制条件，或改用更宽泛的用户行为条件后重新查询。"
    )


def build_query_too_large_message(
    *,
    query_mode: str,
    cohort_size: int | None = None,
    limit: int = 200,
) -> str:
    size_text = (
        f"查询命中的用户数量为 {cohort_size}，超过当前可安全处理的上限 {limit}。"
        if cohort_size is not None
        else f"查询命中的用户数量过多，已超过当前可安全处理的上限 {limit}。"
    )
    if query_mode == "query_profile":
        return (
            f"{size_text} 因此本次没有继续执行画像分析。\n\n"
            "你可以尝试缩小范围，例如缩短时间窗口、增加更明确的行为条件、限定用户状态，或先按更小客群分批查询。"
        )
    return (
        f"{size_text} 因此本次已安全终止，没有继续执行后续分析。\n\n"
        "你可以尝试缩小范围，例如缩短时间窗口、增加更明确的行为条件、限定用户状态，或先按更小客群分批查询。"
    )


def build_query_data_observation_message(output: dict[str, Any], *, limit: int = 200) -> str | None:
    reason = str(output.get("reason") or "").strip().lower()
    uids = output.get("uids")
    if reason == "cohort_empty" or (isinstance(uids, list) and len(uids) == 0 and reason != "cohort_too_large"):
        return (
            "查询已完成，但当前条件没有命中用户，UID 数量为 0。"
            " 请向用户说明当前筛选条件没有命中用户，并建议放宽筛选条件，例如扩大时间范围、减少限制条件或改用更宽泛的行为条件。"
        )

    cohort_size = _cohort_size_from_output(output, limit=limit)
    if reason == "cohort_too_large" or (cohort_size is not None and cohort_size > limit):
        size_note = (
            f"命中的用户数量为 {cohort_size}，超过当前可安全处理的上限 {limit}。"
            if cohort_size is not None
            else f"命中的用户数量过多，超过当前可安全处理的上限 {limit}。"
        )
        return (
            f"查询已完成，但{size_note} 本轮不会继续画像或后续分析。"
            " 请向用户建议缩小范围，例如缩短时间窗口、增加更明确的行为条件、限定用户状态，或分批查询更小客群。"
        )
    return None
