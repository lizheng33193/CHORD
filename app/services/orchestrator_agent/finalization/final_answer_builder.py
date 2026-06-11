"""Pure final-answer builders for known orchestrator flows."""

from __future__ import annotations

from app.services.orchestrator_agent.finalization.query_data_messages import build_query_empty_message
from app.services.orchestrator_agent.planning.availability_summary import availability_summary
from app.services.orchestrator_agent.schemas import DataAvailability, NormalizedRequest, ReviewResult


def build_known_final_message(
    normalized_request: NormalizedRequest,
    *,
    profile_output: dict | None = None,
    trace_output: dict | None = None,
    review: ReviewResult | None = None,
    availability: DataAvailability | None = None,
    extra_note: str | None = None,
) -> str:
    request_understanding = normalized_request.request_understanding
    lines = [
        "## 用户请求理解",
        (request_understanding.rewritten_goal if request_understanding else normalized_request.request_summary),
        "",
    ]
    if request_understanding:
        lines.extend(["## 路径说明", request_understanding.route_reason, ""])
    if availability is not None:
        lines.extend(["## 数据完整性检查", availability_summary(availability), ""])
    if profile_output is not None:
        lines.append("## 执行结果")
        results = profile_output.get("results") or []
        if results:
            for row in results:
                result = row.get("result") or {}
                data = result.get("data") or {}
                summary = data.get("summary") or "暂无摘要"
                lines.append(f"- {row.get('uid')} / {row.get('module')}: {summary}")
        else:
            lines.append("- 无画像结果")
        lines.append("")
    if trace_output is not None:
        lines.append("## 执行结果")
        summary = trace_output.get("summary") or {}
        story = summary.get("churn_story") or trace_output.get("churn_story") or "暂无 trace 摘要"
        lines.append(story)
        lines.append("")
    if review is not None:
        lines.append("## 规则审核")
        if review.status == "pass":
            lines.append("- 所需步骤已完成，结论可直接使用。")
        else:
            for issue in review.issues:
                if issue.get("bucket") and issue.get("uid"):
                    lines.append(f"- UID {issue['uid']} 缺少 {issue['bucket']} 数据。")
                else:
                    lines.append(f"- {issue.get('message') or issue.get('type') or '存在待关注项'}")
        if review.confidence_impact:
            lines.append(f"- 影响：{review.confidence_impact}")
        lines.append("")
    if extra_note:
        lines.extend(["## 下一步建议", extra_note])
    return "\n".join(lines).strip()


def build_query_only_final_message(
    normalized_request: NormalizedRequest,
    *,
    output: dict,
) -> str:
    uids = list(output.get("uids") or [])
    sql_text = str(output.get("sql_text") or "").strip() or "暂无 SQL"
    rows_actual = int(output.get("rows_actual") or 0)
    rows_estimated = int(output.get("rows_estimated") or -1)
    uid_preview = ", ".join(uids[:10]) if uids else "无"
    more_note = f"（其余 {len(uids) - 10} 个已省略）" if len(uids) > 10 else ""
    next_step_note = (
        build_query_empty_message(query_mode="query_only")
        if not uids
        else "如需继续画像，请再次提交这些 UID，或重新开启自动继续画像。"
    )
    lines = [
        "## 用户请求理解",
        (
            normalized_request.request_understanding.rewritten_goal
            if normalized_request.request_understanding
            else normalized_request.request_summary
        ),
        "",
        "## Query 结果",
        f"- UID 数量：{len(uids)}",
        f"- UID 列表：{uid_preview}{more_note}",
        f"- rows_estimated：{rows_estimated}",
        f"- rows_actual：{rows_actual}",
        *(["- 当前条件下没有命中用户"] if not uids else []),
        f"- SQL：{sql_text}",
        "",
        "## 下一步建议",
        next_step_note,
    ]
    return "\n".join(lines).strip()
