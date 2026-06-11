"""run_profile — 薄封装 AnalysisOrchestrator.analyze_module()。

V1 决策：per-call 实例化 AnalysisOrchestrator（成本可接受），不引入模块级单例。
modules 默认 ["app"]；遍历 (uid × module) 调 analyze_module。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app.services.orchestrator import AnalysisOrchestrator
from app.services.orchestrator_agent.schemas import (
    RunProfileInput, RunProfileOutput,
)


def run_profile(
    input_data: RunProfileInput,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> RunProfileOutput:
    orch = AnalysisOrchestrator(strict_data_mode=input_data.strict_data_mode)
    modules = input_data.modules or ["app"]
    results: list[dict[str, Any]] = []
    total = len(input_data.uids) * len(modules)
    completed = 0
    for uid in input_data.uids:
        for mod in modules:
            started = time.perf_counter()
            if progress_callback is not None:
                progress_callback({
                    "progress_type": "profile_module_started",
                    "uid": uid,
                    "module": mod,
                    "status": "running",
                    "completed": completed,
                    "total": total,
                })
            try:
                r = orch.analyze_module(
                    uid=uid, module=mod, application_time=input_data.app_time,
                )
            except Exception as exc:
                if progress_callback is not None:
                    progress_callback({
                        "progress_type": "profile_module_error",
                        "uid": uid,
                        "module": mod,
                        "status": "error",
                        "completed": completed,
                        "total": total,
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "error": str(exc),
                    })
                raise
            completed += 1
            results.append({"uid": uid, "module": mod, "result": r})
            if progress_callback is not None:
                progress_callback({
                    "progress_type": "profile_module_completed",
                    "uid": uid,
                    "module": mod,
                    "result": r,
                    "status": "ok" if r.get("status") == "ok" else "error",
                    "completed": completed,
                    "total": total,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                })
    return RunProfileOutput(
        results=results,
        cache_hits=0,
        cache_misses=len(input_data.uids) * len(modules),
    )
