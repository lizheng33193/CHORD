"""run_trace — 薄封装 TraceAnalyzer.analyze()。"""

from __future__ import annotations

from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
from app.schemas.trace_analyzer import TraceAnalyzeResponse
from app.services.orchestrator_agent.schemas import RunTraceInput, RunTraceOutput


def run_trace(input_data: RunTraceInput) -> RunTraceOutput:
    """Run trace analysis for a single UID.

    V1：days 字段保留但不传给 build_context（下游 N 天阈值走 trace_analyzer 内部配置）。
    返回完整 TraceAnalyzeResponse 形状，供 Dashboard trace 面板直接渲染。
    """
    analyzer = TraceAnalyzer()
    ctx = build_context(input_data.uid)
    out = analyzer.analyze(uid=input_data.uid, context=ctx)
    payload = TraceAnalyzeResponse.model_validate(out).model_dump(
        mode="json",
        by_alias=True,
    )
    event_window = payload.get("event_window") or {}
    payload.setdefault("events", payload.get("key_events_tail", []))
    payload.setdefault("summary", {
        "status": payload.get("status", "unknown"),
        "total_events": event_window.get("total_events", 0),
        "analyzed_events": event_window.get("analyzed_events", 0),
        "churn_root_cause": payload.get("churn_root_cause", []),
        "churn_story": payload.get("churn_story", ""),
    })
    return RunTraceOutput(**payload)
