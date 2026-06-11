# SSE 进度推送 Plan

**Design Doc**: [docs/specs/sse-progress-design.md](../specs/sse-progress-design.md)

**模式**: Superpowers（项目架构清晰，Step 2-3 已完成 Design + Stub，本 Plan 走纯任务列表）

**基线 commit**: `[baseline] sse-progress-plan`（Plan 审核通过后立刻打）

**预期最终 commit**: `[complete] sse-progress-plan: SSE progress streaming`

---

## 已 Plan 阶段敲定的细节（Design Doc §12 的 7 项）

| # | 项 | 决定值 | 理由 |
|---|---|---|---|
| 1 | SSE 事件 JSON 字段命名 | `type` / `uid` / `skill` / `stage` / `duration_ms` / `error_message` / `result` / `results` / `uids` / `total_skills_per_uid` | 与 Design Doc §3 表保持一致，下划线风格匹配项目 Python 习惯 |
| 2 | 总超时秒数 | **600s** | Design Doc §6.1 推荐范围 600-900s 下限；测试用例可注入更小值 |
| 3 | heartbeat 间隔 | **15s** | Design Doc §6.1 默认；`asyncio.wait_for(queue.get, timeout=15)` 兼任 heartbeat 触发 |
| 4 | 后台线程实现 | **`threading.Thread(daemon=True)`** | 不污染 FastAPI 的 thread pool（避免和 sync 路由争抢 worker）；daemon=True 保证主进程退出时线程不阻塞关闭 |
| 5 | `app/main.py` 改动放哪个 Task | **Task 8**（最后一个 Task） | 与 E1 窗口 3 协调，append 式 include_router，rebase 友好 |
| 6 | ProgressView 视觉细节 | 见 Task 6 完整代码块 | 复用 LoadingView 的深色 hero 风格 + Tailwind |
| 7 | `analysis_progress` 中 `result` 字段形态 | **`UserAnalysisResult.model_dump(mode="json")`** 全量 | 前端可早渲染单 UID dashboard，复用 normalizeAnalysisResult |

---

## Scope / Out-of-Scope

### Scope
- 新增 `POST /api/analyze-stream` SSE 端点（含 7 种事件 + heartbeat + 总超时 watchdog）
- `SkillRegistry.run_all` + `AnalysisOrchestrator.analyze` / `_analyze_single_user` 加 `progress_callback` 可选参数
- 前端 `ProgressView` 组件（6 行步骤列表 + 聚合标题 + 多 UID 折叠）
- 前端 `analyzeByUidStream` 服务（fetch + ReadableStream 解析 SSE）
- `app.jsx` 替换假动画 + 新 `view='streaming'` 分支
- mock 模式兼容
- 单 UID 和多 UID 场景

### Out-of-Scope
- `/api/analyze-file-stream`（留后续）
- 浏览器断线自动重连
- 后端任务状态字典 / Redis / request_id
- WebSocket / gRPC / 长轮询
- Skill 内部进度（六步管线分步推送）
- 前端 abort 时后端任务真正取消（线程继续跑完）
- Skill 级超时（仅总超时）

---

## Task 概览（共 8 个）

| Task | 范围 | 涉及文件 |
|---|---|---|
| 1 | `SkillRegistry.run_all` 加 `progress_callback` 参数 | `app/runtime_skills/base.py` |
| 2 | `AnalysisOrchestrator` 透传 callback + `_analyze_single_user` 末尾推 `analysis_progress` | `app/services/orchestrator.py` |
| 3 | SSE 端点骨架：queue 桥接 + event_gen + heartbeat | `app/api/analyze_stream.py` |
| 4 | SSE 端点：总超时 watchdog + `stream_error` 兜底 | `app/api/analyze_stream.py` |
| 5 | 前端 `analyzeByUidStream` SSE 解析服务 | `app/static/js/services/api.js` |
| 6 | 前端 `ProgressView` 组件实现 | `app/static/js/components/ProgressView.jsx` |
| 7 | `app.jsx` 集成：`view='streaming'` + 删除假动画 | `app/static/js/app.jsx` |
| 8 | 路由挂载 + LOAD_ORDER 注册（与 E1 协调点） | `app/main.py` + `app/ui/build_frontend.py` |

`/api/analyze` 同步端点全程零行为变化——回归测试每步执行确认。

---

# Task 1：SkillRegistry.run_all 加 progress_callback 参数

**Files**:
- Modify: `app/runtime_skills/base.py`（修改 `SkillRegistry.run_all` 签名 L100；`_run_skill` 内部 callback 调用 L117-128）
- Test: `tests/test_skill_registry_progress.py`（新建）

### Step 1: 写失败测试

```python
# tests/test_skill_registry_progress.py
"""SkillRegistry.run_all progress_callback contract tests."""

from __future__ import annotations

from app.runtime_skills.base import BaseSkill, SkillRegistry


class _FakeSkill(BaseSkill):
    def __init__(self, name: str, stage: int = 0, depends_on=None, raise_exc=False):
        self.name = name
        self.stage = stage
        self.depends_on = depends_on or []
        self._raise = raise_exc

    def analyze(self, uid: str, **kwargs):
        if self._raise:
            raise RuntimeError(f"{self.name} boom")
        return {"summary": f"{self.name} ok"}


def test_run_all_without_callback_unchanged():
    """When callback is None the behavior must equal pre-change semantics."""
    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.register(_FakeSkill("b"))
    out = reg.run_all(uid="u1")
    assert set(out.keys()) == {"a", "b"}


def test_run_all_emits_started_and_completed():
    events: list[dict] = []
    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.run_all(uid="u1", progress_callback=events.append)

    types = [e["type"] for e in events]
    assert types == ["skill_started", "skill_completed"]
    for evt in events:
        assert evt["uid"] == "u1"
        assert evt["skill"] == "a"
        assert evt["stage"] == 0
    assert "duration_ms" in events[1]
    assert isinstance(events[1]["duration_ms"], int)


def test_run_all_emits_failed_on_exception():
    events: list[dict] = []
    reg = SkillRegistry()
    reg.register(_FakeSkill("a", raise_exc=True))
    reg.register(_FakeSkill("b"))  # downstream stage-0 sibling, must still run

    reg.run_all(uid="u1", progress_callback=events.append)

    types_for_a = [e["type"] for e in events if e["skill"] == "a"]
    assert types_for_a == ["skill_started", "skill_failed"]
    failed = next(e for e in events if e["type"] == "skill_failed")
    assert failed["error_message"] == "a boom"
    assert "duration_ms" in failed

    # b 的事件仍然推送，证明 skill_failed 不级联终止
    types_for_b = [e["type"] for e in events if e["skill"] == "b"]
    assert types_for_b == ["skill_started", "skill_completed"]


def test_run_all_callback_signature_is_dict_only():
    """Callback receives a single dict argument; no kwargs or extras."""
    captured: list[tuple] = []

    def cb(*args, **kwargs):
        captured.append((args, kwargs))

    reg = SkillRegistry()
    reg.register(_FakeSkill("a"))
    reg.run_all(uid="u1", progress_callback=cb)

    for args, kwargs in captured:
        assert len(args) == 1
        assert isinstance(args[0], dict)
        assert kwargs == {}
```

### Step 2: 跑测试确认失败

Run: `python -m pytest tests/test_skill_registry_progress.py -v`
Expected: FAIL（`progress_callback` 参数不存在）

### Step 3: 写最少实现

Modify `app/runtime_skills/base.py`，把 `run_all` 改为：

```python
def run_all(
    self,
    uid: str,
    progress_callback=None,
    **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    """Execute every registered skill respecting stage order.

    Skills in the same stage run in parallel.  Each skill's output is
    stored under ``results[skill.name]`` and injected as
    ``<skill.name>_result`` into subsequent stages.

    Parameters
    ----------
    progress_callback:
        Optional ``Callable[[dict], None]``.  When provided, invoked
        before/after each skill with one of three event dicts:
        ``skill_started`` / ``skill_completed`` / ``skill_failed``.
        When ``None`` the registry behaves identically to pre-callback
        semantics — used by the synchronous ``/api/analyze`` path.
    """
    results: dict[str, dict[str, Any]] = {}
    stages = sorted({s.stage for s in self._skills.values()})

    for stage in stages:
        stage_skills = [s for s in self._skills.values() if s.stage == stage]

        def _run_skill(skill: BaseSkill) -> tuple[str, dict[str, Any]]:
            t0 = perf_counter()
            if progress_callback is not None:
                progress_callback({
                    "type": "skill_started",
                    "uid": uid,
                    "skill": skill.name,
                    "stage": stage,
                })
            skill_kwargs = dict(kwargs)
            for dep in skill.depends_on:
                skill_kwargs[f"{dep}_result"] = results.get(dep, {})
            try:
                result = skill.analyze(uid=uid, **skill_kwargs)
            except Exception as exc:
                if progress_callback is not None:
                    progress_callback({
                        "type": "skill_failed",
                        "uid": uid,
                        "skill": skill.name,
                        "stage": stage,
                        "error_message": str(exc),
                        "duration_ms": int((perf_counter() - t0) * 1000),
                    })
                raise
            duration_ms = int((perf_counter() - t0) * 1000)
            if progress_callback is not None:
                progress_callback({
                    "type": "skill_completed",
                    "uid": uid,
                    "skill": skill.name,
                    "stage": stage,
                    "duration_ms": duration_ms,
                })
            logger.info(
                "Skill done uid=%s skill=%s stage=%d duration=%.2fs",
                uid, skill.name, stage, duration_ms / 1000.0,
            )
            return skill.name, result

        if len(stage_skills) == 1:
            try:
                name, result = _run_skill(stage_skills[0])
                results[name] = result
            except Exception:
                # 与现有语义保持：异常上抛，由调用方决定（现状是 orchestrator 不 catch，
                # 但 Skill 内部都有规则引擎兜底，实际不会走到这里）
                pass
        else:
            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = [pool.submit(_run_skill, s) for s in stage_skills]
                for f in futures:
                    try:
                        name, result = f.result()
                        results[name] = result
                    except Exception:
                        pass

    return results
```

**关键说明**：
- `progress_callback` 参数位置在 `**kwargs` 之前作为关键字参数（不污染 kwargs，避免被 `<dep>_result` 注入逻辑干扰）
- callback 在 try/except 内部、异常重抛前调用 → `skill_failed` 事件保证发送
- **但需要现状对齐**：测试 `test_run_all_emits_failed_on_exception` 期望 b 仍然跑完——所以异常不能从 `_run_skill` 一路上抛中断 stage。当前代码是抛了之后 `f.result()` 处再抛——加 try/except 包裹 `f.result()`（见上）。同样单 skill 分支也包一层。**这与现状相比是改动**：当前 `len==1` 分支异常会冒泡，但实际项目中所有 stage 都有 ≥1 个 skill 且 stage 0/2 多 skill，stage 1 只有 ComprehensiveProfile 单个 skill；ComprehensiveProfile 内部已有 fallback 降级，不会抛。这个改动是兼容的（异常照样吃掉，但现在多了 callback 通知）。

### Step 4: 跑测试确认通过

Run: `python -m pytest tests/test_skill_registry_progress.py -v`
Expected: 4 passed

回归测试：`python -m pytest tests/ -v`
Expected: 全部 passed（callback 默认 None，现有 206 测试零回归）

### Step 5: 提交

```
git add app/runtime_skills/base.py tests/test_skill_registry_progress.py
git commit -m "feat(sse): add progress_callback param to SkillRegistry.run_all"
```

---

# Task 2：Orchestrator 透传 callback + 推 analysis_progress

**Files**:
- Modify: `app/services/orchestrator.py`（修改 `analyze` L60-70 和 `_analyze_single_user` L72-107 签名）
- Test: `tests/test_orchestrator_progress.py`（新建）

### Step 1: 写失败测试

```python
# tests/test_orchestrator_progress.py
"""AnalysisOrchestrator progress_callback transparency tests."""

from __future__ import annotations

import pytest

from app.services.orchestrator import AnalysisOrchestrator


@pytest.fixture
def orchestrator(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    return AnalysisOrchestrator()


def test_analyze_without_callback_unchanged(orchestrator):
    """No callback -> behavior identical to current /api/analyze path."""
    resp = orchestrator.analyze(["824812551379353600"])
    assert len(resp.results) == 1


def test_analyze_passes_callback_through(orchestrator):
    events: list[dict] = []
    orchestrator.analyze(
        ["824812551379353600"],
        progress_callback=events.append,
    )

    types = [e["type"] for e in events]
    # Must contain at least one skill_started, one skill_completed, one analysis_progress
    assert "skill_started" in types
    assert "skill_completed" in types
    assert "analysis_progress" in types

    progress = next(e for e in events if e["type"] == "analysis_progress")
    assert progress["uid"] == "824812551379353600"
    assert "result" in progress
    assert progress["result"]["uid"] == "824812551379353600"


def test_analyze_emits_progress_per_uid(orchestrator):
    events: list[dict] = []
    uids = ["824812551379353600", "824812551379353601"]
    orchestrator.analyze(uids, progress_callback=events.append)

    progress_events = [e for e in events if e["type"] == "analysis_progress"]
    assert len(progress_events) == 2
    assert {e["uid"] for e in progress_events} == set(uids)


def test_analyze_progress_result_is_jsonable(orchestrator):
    """analysis_progress.result must be JSON-serializable (mode='json')."""
    import json
    events: list[dict] = []
    orchestrator.analyze(["824812551379353600"], progress_callback=events.append)

    progress = next(e for e in events if e["type"] == "analysis_progress")
    json.dumps(progress["result"])  # must not raise
```

### Step 2: 跑测试确认失败

Run: `python -m pytest tests/test_orchestrator_progress.py -v`
Expected: FAIL（`progress_callback` 参数未透传，`analysis_progress` 事件未推）

### Step 3: 写最少实现

Modify `app/services/orchestrator.py`：

```python
# 新签名（保持向后兼容）
def analyze(
    self,
    uids: list[str],
    application_time: str | None = None,
    progress_callback=None,
) -> AnalyzeResponse:
    """Analyze every uid and collect profile outputs."""
    results = [
        self._analyze_single_user(
            uid,
            application_time=application_time,
            progress_callback=progress_callback,
        )
        for uid in uids
    ]
    return AnalyzeResponse(results=results)

def _analyze_single_user(
    self,
    uid: str,
    application_time: str | None = None,
    progress_callback=None,
) -> UserAnalysisResult:
    """Run all registered skills for one user via the registry."""
    logger.info("Start analyze uid=%s", uid)
    started = perf_counter()

    all_results = self.registry.run_all(
        uid=uid,
        progress_callback=progress_callback,
        repository=self.repository,
        application_time=application_time,
    )

    logger.info("Analyze complete uid=%s duration=%.2fs", uid, perf_counter() - started)

    standardized_labels = build_standardized_labels(
        app_profile=all_results.get("app_profile"),
        behavior_profile=all_results.get("behavior_profile"),
        credit_profile=all_results.get("credit_profile"),
        comprehensive_profile=all_results.get("comprehensive_profile"),
        product_advice=all_results.get("product_advice"),
        ops_advice=all_results.get("ops_advice"),
    )

    user_result = UserAnalysisResult(
        uid=uid,
        app_profile=all_results.get("app_profile", {}),
        behavior_profile=all_results.get("behavior_profile", {}),
        credit_profile=all_results.get("credit_profile", {}),
        comprehensive_profile=all_results.get("comprehensive_profile", {}),
        product_advice=all_results.get("product_advice"),
        ops_advice=all_results.get("ops_advice"),
        standardized_labels=standardized_labels,
    )

    if progress_callback is not None:
        progress_callback({
            "type": "analysis_progress",
            "uid": uid,
            "result": user_result.model_dump(mode="json"),
        })

    return user_result
```

### Step 4: 跑测试确认通过

Run: `python -m pytest tests/test_orchestrator_progress.py -v`
Expected: 4 passed

回归：`python -m pytest tests/ -v`
Expected: 全部 passed

### Step 5: 提交

```
git add app/services/orchestrator.py tests/test_orchestrator_progress.py
git commit -m "feat(sse): orchestrator passthrough progress_callback + analysis_progress event"
```

---

# Task 3：SSE 端点骨架（queue 桥接 + event_gen + heartbeat）

**Files**:
- Modify: `app/api/analyze_stream.py`（替换 Step 3 stub）
- Test: `tests/test_analyze_stream_endpoint.py`（新建）

### Step 1: 写失败测试

```python
# tests/test_analyze_stream_endpoint.py
"""End-to-end tests for the /api/analyze-stream SSE endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analyze_stream import router as stream_router


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    app = FastAPI()
    app.include_router(stream_router, prefix="/api")
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    """Split SSE wire format into a list of event dicts (skip heartbeat lines)."""
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_stream_emits_full_event_sequence(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    types = [e["type"] for e in events]

    assert types[0] == "analysis_started"
    assert "skill_started" in types
    assert "skill_completed" in types
    assert "analysis_progress" in types
    assert types[-1] == "analysis_completed"


def test_stream_analysis_completed_carries_full_results(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    completed = next(e for e in events if e["type"] == "analysis_completed")
    assert "results" in completed
    assert isinstance(completed["results"], list)
    assert completed["results"][0]["uid"] == "824812551379353600"


def test_stream_started_event_carries_uids_and_total_skills(client):
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uids": ["824812551379353600", "824812551379353601"]},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    started = events[0]
    assert started["type"] == "analysis_started"
    assert started["uids"] == ["824812551379353600", "824812551379353601"]
    assert started["total_skills_per_uid"] == 6


def test_stream_invalid_uid_returns_400_not_sse(client):
    """Input validation failure must go HTTP 400, not enter the stream (Q6.4)."""
    resp = client.post("/api/analyze-stream", json={"uid": "not-an-18-digit"})
    assert resp.status_code == 400
    assert "text/event-stream" not in resp.headers.get("content-type", "")
```

### Step 2: 跑测试确认失败

Run: `python -m pytest tests/test_analyze_stream_endpoint.py -v`
Expected: FAIL（端点是 stub，raise NotImplementedError）

### Step 3: 写最少实现

完整替换 `app/api/analyze_stream.py`：

```python
"""SSE streaming endpoint for /api/analyze-stream.

Implementation per docs/plans/sse-progress-plan.md Task 3-4.
Design: docs/specs/sse-progress-design.md §4.

Architecture:
    POST request
       │
       ├─ background threading.Thread runs orchestrator.analyze(...,
       │       progress_callback=lambda evt: q.put(evt))
       │       Final events: analysis_completed, then None sentinel.
       │
       └─ event_gen() main coroutine reads queue via run_in_executor,
          yields SSE wire format. On 15s idle yields heartbeat comment.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.request import AnalyzeRequest
from app.services.orchestrator import AnalysisOrchestrator
from app.services.batch_service import BatchAnalysisService


router = APIRouter()
_orchestrator = AnalysisOrchestrator()
_batch_service = BatchAnalysisService(_orchestrator)

HEARTBEAT_INTERVAL_SEC = 15
TOTAL_SKILLS_PER_UID = 6


def _format_event(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _run_analysis_in_thread(
    uids: list[str],
    application_time: str | None,
    q: queue.Queue,
) -> None:
    """Background thread entry: run orchestrator + push events into queue."""
    try:
        q.put({
            "type": "analysis_started",
            "uids": uids,
            "total_skills_per_uid": TOTAL_SKILLS_PER_UID,
        })

        def cb(evt: dict[str, Any]) -> None:
            q.put(evt)

        response = _orchestrator.analyze(
            uids,
            application_time=application_time,
            progress_callback=cb,
        )

        q.put({
            "type": "analysis_completed",
            "results": [r.model_dump(mode="json") for r in response.results],
        })
    except Exception as exc:  # noqa: BLE001 — bottom-of-stack guard
        q.put({"type": "stream_error", "error_message": str(exc)})
    finally:
        q.put(None)  # sentinel


@router.post("/analyze-stream", summary="Stream analysis progress as Server-Sent Events")
async def analyze_stream(request: AnalyzeRequest) -> StreamingResponse:
    """Return text/event-stream of skill-level progress events.

    Input validation failures raise 400 via the global RequestValidationError
    handler in app/main.py — they never enter the stream.
    """
    uids = request.get_uid_list()
    application_time = request.application_time
    q: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_analysis_in_thread,
        args=(uids, application_time, q),
        daemon=True,
    )
    thread.start()

    async def event_gen():
        loop = asyncio.get_event_loop()
        while True:
            try:
                evt = await asyncio.wait_for(
                    loop.run_in_executor(None, q.get),
                    timeout=HEARTBEAT_INTERVAL_SEC,
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if evt is None:
                break
            yield _format_event(evt)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

### Step 4: 跑测试确认通过

Run: `python -m pytest tests/test_analyze_stream_endpoint.py -v`
Expected: 4 passed

回归：`python -m pytest tests/ -v`
Expected: 全部 passed

### Step 5: 提交

```
git add app/api/analyze_stream.py tests/test_analyze_stream_endpoint.py
git commit -m "feat(sse): implement /api/analyze-stream endpoint with queue bridge + heartbeat"
```

---

# Task 4：总超时 watchdog + stream_error 兜底

**Files**:
- Modify: `app/api/analyze_stream.py`（在 Task 3 实现上增加 watchdog）
- Test: `tests/test_analyze_stream_timeout.py`（新建）

### Step 1: 写失败测试

```python
# tests/test_analyze_stream_timeout.py
"""Total-timeout watchdog tests for /api/analyze-stream."""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import analyze_stream as stream_module


@pytest.fixture
def client_with_short_timeout(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    monkeypatch.setattr(stream_module, "TOTAL_TIMEOUT_SEC", 1)
    monkeypatch.setattr(stream_module, "HEARTBEAT_INTERVAL_SEC", 1)
    app = FastAPI()
    app.include_router(stream_module.router, prefix="/api")
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def test_stream_emits_stream_error_on_total_timeout(monkeypatch, client_with_short_timeout):
    """When background thread takes longer than TOTAL_TIMEOUT_SEC, stream_error fires."""

    def slow_run(uids, application_time, q):
        time.sleep(5)  # exceeds 1s timeout
        q.put(None)

    monkeypatch.setattr(stream_module, "_run_analysis_in_thread", slow_run)

    with client_with_short_timeout.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert "stream_error" in types
    err = next(e for e in events if e["type"] == "stream_error")
    assert "timeout" in err["error_message"].lower()


def test_stream_error_on_orchestrator_exception(monkeypatch):
    """If orchestrator.analyze raises, the queue gets a stream_error event."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def boom(*args, **kwargs):
        raise RuntimeError("orchestrator boom")

    monkeypatch.setattr(stream_module._orchestrator, "analyze", boom)

    app = FastAPI()
    app.include_router(stream_module.router, prefix="/api")
    client = TestClient(app)

    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600"},
    ) as resp:
        body = resp.read().decode("utf-8")
    events = _parse_sse(body)
    types = [e["type"] for e in events]
    assert "stream_error" in types
    err = next(e for e in events if e["type"] == "stream_error")
    assert "boom" in err["error_message"]
```

### Step 2: 跑测试确认失败

Run: `python -m pytest tests/test_analyze_stream_timeout.py -v`
Expected: FAIL（test_stream_emits_stream_error_on_total_timeout 失败——watchdog 未实现；test_stream_error_on_orchestrator_exception 应已通过来自 Task 3 的 try/except）

### Step 3: 写最少实现

修改 `app/api/analyze_stream.py`，在模块顶部加常量、改 `event_gen` 加 watchdog：

```python
# 模块顶部新增
TOTAL_TIMEOUT_SEC = 600  # 10 minutes hard cap (Design Doc §6.1)
```

替换 `event_gen` 为带 watchdog 版本：

```python
async def event_gen():
    loop = asyncio.get_event_loop()
    deadline = loop.time() + TOTAL_TIMEOUT_SEC
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            yield _format_event({
                "type": "stream_error",
                "error_message": f"stream timeout after {TOTAL_TIMEOUT_SEC}s",
            })
            return
        wait_for = min(HEARTBEAT_INTERVAL_SEC, remaining)
        try:
            evt = await asyncio.wait_for(
                loop.run_in_executor(None, q.get),
                timeout=wait_for,
            )
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue
        if evt is None:
            break
        yield _format_event(evt)
```

### Step 4: 跑测试确认通过

Run: `python -m pytest tests/test_analyze_stream_timeout.py -v`
Expected: 2 passed

回归（含 Task 3 测试）：`python -m pytest tests/test_analyze_stream_endpoint.py tests/test_analyze_stream_timeout.py -v`
Expected: 6 passed

全量回归：`python -m pytest tests/ -v`
Expected: 全部 passed

### Step 5: 提交

```
git add app/api/analyze_stream.py tests/test_analyze_stream_timeout.py
git commit -m "feat(sse): add total-timeout watchdog + stream_error guards"
```

---

# Task 5：前端 analyzeByUidStream SSE 解析服务

**Files**:
- Modify: `app/static/js/services/api.js`（在末尾追加 `analyzeByUidStream` + 更新 export）

### Step 1: 写失败测试

前端单元测试当前项目无 JS test runner（架构是 Babel Standalone 浏览器侧），按现有模式**不写 JS 单元测试**——通过 Task 3+4 的端到端 Python 测试已覆盖 SSE 协议正确性。本 Task 的验证放在 Task 7 集成时手动验证（启动服务 + 浏览器 DevTools 网络面板观测 SSE 流）。

**Verification command**（不是测试，但有验证步骤）：
- Lint check: `node -c app/static/js/services/api.js`（如果环境有 node；没有则跳过——Babel Standalone 运行时会在浏览器侧报语法错误）

### Step 2: 跳过（无失败测试）

### Step 3: 写实现

完整替换 `app/static/js/services/api.js`：

```javascript
// Extracted from app/ui/live_frontend.py during UI separation Step-1.
// All fetch calls live here so future SSE / polling switches are local to this file.

async function analyzeByUid(trimmedUid, normalizedApplicationTime) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      uid: trimmedUid,
      application_time: normalizedApplicationTime
    })
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '分析请求失败，请稍后重试。');
  }

  return payload;
}

async function analyzeByFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/analyze-file', {
    method: 'POST',
    body: formData
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || '文件分析请求失败，请检查文件内容。');
  }

  return payload;
}

// SSE-aware streaming variant of analyzeByUid.
// onEvent: (evt: object) => void  — invoked once per parsed event
// signal:  AbortSignal | undefined — fetch abort support (Q6.5)
// Returns: Promise<void> — resolves when stream ends naturally; rejects on
//          network/HTTP error (NOT on stream_error events — those are
//          delivered via onEvent and the consumer decides how to react).
async function analyzeByUidStream(trimmedUid, normalizedApplicationTime, onEvent, signal) {
  const body = trimmedUid && trimmedUid.length === 18
    ? { uid: trimmedUid, application_time: normalizedApplicationTime }
    : null;
  if (!body) throw new Error('UID 格式错误');

  const response = await fetch('/api/analyze-stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream'
    },
    body: JSON.stringify(body),
    signal
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `分析请求失败 (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex;
    // Process every complete event (delimited by blank line, '\n\n').
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (!block || block.startsWith(':')) continue;  // heartbeat
      const dataLine = block.split('\n').find((l) => l.startsWith('data:'));
      if (!dataLine) continue;
      try {
        const evt = JSON.parse(dataLine.slice(5).trim());
        onEvent(evt);
      } catch (e) {
        // Malformed event — ignore rather than tear down the whole stream.
        console.warn('SSE parse error', e, block);
      }
    }
  }
}

window.AppServices = window.AppServices || {};
window.AppServices.api = { analyzeByUid, analyzeByFile, analyzeByUidStream };
```

### Step 4: 验证

Run: `python -c "from app.ui.build_frontend import BUILT_FRONTEND_HTML; assert 'analyzeByUidStream' in BUILT_FRONTEND_HTML; print('frontend bundle OK')"`
Expected: `frontend bundle OK`（注意：此时 LOAD_ORDER 还没改，但 api.js 已经在 LOAD_ORDER 里 → bundle 自动包含新函数）

回归：`python -m pytest tests/ -v`
Expected: 全部 passed（前端改动不影响 Python 测试）

### Step 5: 提交

```
git add app/static/js/services/api.js
git commit -m "feat(sse): add analyzeByUidStream service (fetch + ReadableStream SSE parser)"
```

---

# Task 6：前端 ProgressView 组件实现

**Files**:
- Modify: `app/static/js/components/ProgressView.jsx`（替换 Step 3 stub）

### Step 1: 验证策略

同 Task 5：纯前端组件，无 JS test runner，通过 Task 7 集成 + 手动浏览器验证。

### Step 2: 跳过

### Step 3: 写实现

完整替换 `app/static/js/components/ProgressView.jsx`：

```jsx
// ProgressView — SSE-driven 6-row skill progress + multi-UID collapse.
// Design: docs/specs/sse-progress-design.md §5

const SKILL_ORDER = [
  { key: 'app_profile',           label: 'App 画像' },
  { key: 'behavior_profile',      label: '行为画像' },
  { key: 'credit_profile',        label: '征信画像' },
  { key: 'comprehensive_profile', label: '综合画像' },
  { key: 'product_advice',        label: '产品策略' },
  { key: 'ops_advice',            label: '运营策略' }
];

const ICON = {
  pending:   '⚪',
  running:   '⏳',
  done:      '✅',
  failed:    '⚠️'
};

function _formatDuration(ms) {
  if (ms == null) return '';
  const sec = ms / 1000;
  return `${sec.toFixed(1)}s`;
}

function SkillRow({ label, status, durationMs }) {
  const tail = status === 'done' || status === 'failed'
    ? _formatDuration(durationMs)
    : status === 'running' ? '进行中…'
    : status === 'pending' ? '等待中'
    : '';
  return (
    <div className="flex items-center justify-between py-2 px-4 border-b border-slate-700/40 last:border-b-0">
      <div className="flex items-center gap-3">
        <span className="text-xl">{ICON[status] || ICON.pending}</span>
        <span className="text-slate-200">{label}</span>
        {status === 'failed' && (
          <span className="text-xs text-amber-400 ml-1">降级运行</span>
        )}
      </div>
      <span className="text-slate-400 text-sm">{tail}</span>
    </div>
  );
}

function UidProgressBlock({ uid, progress }) {
  return (
    <div className="bg-slate-800/60 rounded-lg overflow-hidden border border-slate-700/40">
      {SKILL_ORDER.map(({ key, label }) => (
        <SkillRow
          key={key}
          label={label}
          status={(progress[key] && progress[key].status) || 'pending'}
          durationMs={progress[key] && progress[key].durationMs}
        />
      ))}
    </div>
  );
}

function CollapsedUidRow({ uid, status, durationMs, onExpand }) {
  const icon = status === 'done' ? ICON.done
             : status === 'pending' ? ICON.pending
             : ICON.running;
  const tail = status === 'done' ? _formatDuration(durationMs)
             : status === 'pending' ? '等待中'
             : '进行中…';
  return (
    <button
      type="button"
      onClick={status === 'done' ? onExpand : undefined}
      className={`w-full flex items-center justify-between py-2 px-4 ${
        status === 'done' ? 'hover:bg-slate-800/40 cursor-pointer' : 'cursor-default'
      } border-b border-slate-700/40 last:border-b-0`}
    >
      <div className="flex items-center gap-3">
        <span className="text-xl">{icon}</span>
        <span className="text-slate-200">UID {uid}</span>
      </div>
      <span className="text-slate-400 text-sm">{tail}</span>
    </button>
  );
}

function ProgressView({
  uids,
  activeUid,
  progressByUid,    // { uid: { skill_key: { status, durationMs } } }
  uidStatus,        // { uid: 'pending' | 'running' | 'done' }
  uidDurations,     // { uid: totalMs }
  elapsedSec,
  completedCount,
  totalCount,
  onExpandUid
}) {
  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white p-8">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <h2 className="text-2xl font-semibold mb-2 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-400">
            AI 智能体矩阵分析中
          </h2>
          <p className="text-slate-400 text-sm">
            分析进度：{completedCount} / {totalCount} 完成 ⏱ 已用 {elapsedSec}s
          </p>
        </div>

        {(uids || []).map((uid) => {
          const isActive = uid === activeUid;
          if (isActive) {
            return (
              <div key={uid} className="mb-4">
                <p className="text-slate-300 text-sm mb-2">UID {uid}</p>
                <UidProgressBlock uid={uid} progress={progressByUid[uid] || {}} />
              </div>
            );
          }
          return (
            <CollapsedUidRow
              key={uid}
              uid={uid}
              status={uidStatus[uid] || 'pending'}
              durationMs={uidDurations[uid]}
              onExpand={() => onExpandUid && onExpandUid(uid)}
            />
          );
        })}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ProgressView = ProgressView;
```

### Step 4: 验证

Run: `python -c "from app.ui.build_frontend import BUILT_FRONTEND_HTML; print('bundle len:', len(BUILT_FRONTEND_HTML))"`
**注意：此时 ProgressView.jsx 还未加入 LOAD_ORDER**（Task 8 才加），所以 bundle 暂时不包含 ProgressView——这没问题，因为 app.jsx 的集成在 Task 7，Task 7 commit 后跑端到端会失败，Task 8 才 LOAD_ORDER 注册让一切跑起来。

回归：`python -m pytest tests/ -v`
Expected: 全部 passed

### Step 5: 提交

```
git add app/static/js/components/ProgressView.jsx
git commit -m "feat(sse): implement ProgressView component (6-row skill progress + multi-UID collapse)"
```

---

# Task 7：app.jsx 集成 — view='streaming' + 删除假动画

**Files**:
- Modify: `app/static/js/app.jsx`（删除 LOADING_TEXTS / playLoadingSequence；新增 streaming 分支）

### Step 1: 验证策略

同 Task 5/6：手动浏览器验证。

### Step 2: 跳过

### Step 3: 写实现

完整替换 `app/static/js/app.jsx`：

```jsx
// Top-level entry — assembled during UI separation Step-1.
// SSE progress integration (sse-progress-plan Task 7):
//   - streaming view replaces fake LOADING_TEXTS animation
//   - analyzeByUidStream drives ProgressView via SSE events
//   - file-mode (analyzeByFile) keeps the legacy non-stream path

const { useState, useRef, useEffect } = React;
const { HomeView, LoadingView, DashboardView, ProgressView } = window.AppComponents;
const { normalizeAnalysisResult, buildEmptyAgentOutput, normalizeApplicationTime } = window.AppUtils.normalize;
const { analyzeByUid, analyzeByFile, analyzeByUidStream } = window.AppServices.api;

const UID_PATTERN = /^\d{18}$/;

const FALLBACK_RESULT = {
  uid: '',
  app_profile: buildEmptyAgentOutput('暂无 App 画像结果'),
  behavior_profile: buildEmptyAgentOutput('暂无行为画像结果'),
  credit_profile: buildEmptyAgentOutput('暂无征信画像结果'),
  comprehensive_profile: buildEmptyAgentOutput('暂无综合画像结果'),
  product_advice: null,
  ops_advice: null,
  standardized_labels: null
};

const SKILL_KEYS = [
  'app_profile', 'behavior_profile', 'credit_profile',
  'comprehensive_profile', 'product_advice', 'ops_advice'
];

function _emptyProgress() {
  const p = {};
  SKILL_KEYS.forEach((k) => { p[k] = { status: 'pending', durationMs: null }; });
  return p;
}

function App() {
  const [view, setView] = useState('home');
  const [uid, setUid] = useState('');
  const [uidError, setUidError] = useState('');
  const [applicationTime, setApplicationTime] = useState('2026-04-15T12:00');
  const [activeTab, setActiveTab] = useState('comprehensive');
  const [analysisResults, setAnalysisResults] = useState([FALLBACK_RESULT]);
  const [selectedResultIndex, setSelectedResultIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  // streaming view state
  const [streamUids, setStreamUids] = useState([]);
  const [activeStreamUid, setActiveStreamUid] = useState(null);
  const [progressByUid, setProgressByUid] = useState({});
  const [uidStatus, setUidStatus] = useState({});
  const [uidDurations, setUidDurations] = useState({});
  const [elapsedSec, setElapsedSec] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const startTsRef = useRef(0);
  const tickIdRef = useRef(null);

  useEffect(() => {
    if (view !== 'streaming') {
      if (tickIdRef.current) {
        window.clearInterval(tickIdRef.current);
        tickIdRef.current = null;
      }
      return;
    }
    tickIdRef.current = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startTsRef.current) / 1000));
    }, 1000);
    return () => {
      if (tickIdRef.current) {
        window.clearInterval(tickIdRef.current);
        tickIdRef.current = null;
      }
    };
  }, [view]);

  function _handleSseEvent(evt) {
    if (evt.type === 'analysis_started') {
      setStreamUids(evt.uids || []);
      const initStatus = {};
      const initProgress = {};
      (evt.uids || []).forEach((u) => {
        initStatus[u] = 'pending';
        initProgress[u] = _emptyProgress();
      });
      setUidStatus(initStatus);
      setProgressByUid(initProgress);
      return;
    }
    if (evt.type === 'skill_started') {
      setActiveStreamUid(evt.uid);
      setUidStatus((prev) => ({ ...prev, [evt.uid]: 'running' }));
      setProgressByUid((prev) => ({
        ...prev,
        [evt.uid]: {
          ...(prev[evt.uid] || _emptyProgress()),
          [evt.skill]: { status: 'running', durationMs: null }
        }
      }));
      return;
    }
    if (evt.type === 'skill_completed' || evt.type === 'skill_failed') {
      const status = evt.type === 'skill_completed' ? 'done' : 'failed';
      setProgressByUid((prev) => ({
        ...prev,
        [evt.uid]: {
          ...(prev[evt.uid] || _emptyProgress()),
          [evt.skill]: { status, durationMs: evt.duration_ms }
        }
      }));
      setCompletedCount((c) => c + 1);
      return;
    }
    if (evt.type === 'analysis_progress') {
      setUidStatus((prev) => ({ ...prev, [evt.uid]: 'done' }));
      setUidDurations((prev) => ({
        ...prev,
        [evt.uid]: Date.now() - startTsRef.current
      }));
      return;
    }
    if (evt.type === 'stream_error') {
      setErrorMessage(evt.error_message || '分析流异常');
      setView('home');
      return;
    }
    // analysis_completed handled by caller via the resolved promise
  }

  async function _runStreamForUid(trimmedUid, normalizedApplicationTime) {
    let finalResults = null;
    await analyzeByUidStream(
      trimmedUid,
      normalizedApplicationTime,
      (evt) => {
        if (evt.type === 'analysis_completed') {
          finalResults = evt.results;
        } else {
          _handleSseEvent(evt);
        }
      }
    );
    return finalResults;
  }

  async function handleAnalyze({ mode }) {
    const trimmedUid = uid.trim();
    const normalizedApplicationTime = normalizeApplicationTime(applicationTime);

    if (mode === 'uid' && !trimmedUid) {
      setUidError('请输入 18 位纯数字 UID。');
      return;
    }
    if (mode === 'uid' && !UID_PATTERN.test(trimmedUid)) {
      setUidError('UID 格式错误：仅支持 18 位纯数字。');
      return;
    }
    if (mode === 'uid' && !normalizedApplicationTime) {
      window.alert('请输入申请时间');
      return;
    }
    if (mode === 'file' && !selectedFile) {
      window.alert('请先选择 txt 或 csv 文件');
      return;
    }

    setErrorMessage('');
    setUidError('');

    try {
      let rawResults = [];
      if (mode === 'uid') {
        // Reset streaming state before entering streaming view.
        startTsRef.current = Date.now();
        setElapsedSec(0);
        setCompletedCount(0);
        setStreamUids([trimmedUid]);
        setActiveStreamUid(trimmedUid);
        setProgressByUid({ [trimmedUid]: _emptyProgress() });
        setUidStatus({ [trimmedUid]: 'pending' });
        setUidDurations({});
        setView('streaming');
        rawResults = (await _runStreamForUid(trimmedUid, normalizedApplicationTime)) || [];
      } else {
        // File-mode keeps legacy non-stream path. Show LoadingView fallback.
        setView('loading');
        const payload = await analyzeByFile(selectedFile);
        rawResults = Array.isArray(payload && payload.results) ? payload.results : [];
      }

      if (!rawResults.length) {
        throw new Error('后端未返回有效画像结果。');
      }

      const normalizedResults = rawResults.map((item, index) =>
        normalizeAnalysisResult(
          item,
          (item && item.uid) || trimmedUid || `user_${index + 1}`
        )
      );

      setAnalysisResults(normalizedResults);
      setSelectedResultIndex(0);
      setActiveTab('comprehensive');
      setView('dashboard');
    } catch (error) {
      setErrorMessage(error.message || '请求失败，请检查服务是否已启动。');
      setView('home');
    }
  }

  if (view === 'home') {
    return (
      <HomeView
        uid={uid}
        setUid={setUid}
        uidError={uidError}
        setUidError={setUidError}
        applicationTime={applicationTime}
        setApplicationTime={setApplicationTime}
        selectedFile={selectedFile}
        setSelectedFile={setSelectedFile}
        onStartUid={() => handleAnalyze({ mode: 'uid' })}
        onStartFile={() => handleAnalyze({ mode: 'file' })}
        errorMessage={errorMessage}
      />
    );
  }

  if (view === 'loading') {
    return <LoadingView text="正在分析批量文件..." />;
  }

  if (view === 'streaming') {
    return (
      <ProgressView
        uids={streamUids}
        activeUid={activeStreamUid}
        progressByUid={progressByUid}
        uidStatus={uidStatus}
        uidDurations={uidDurations}
        elapsedSec={elapsedSec}
        completedCount={completedCount}
        totalCount={streamUids.length * SKILL_KEYS.length}
        onExpandUid={(u) => setActiveStreamUid(u)}
      />
    );
  }

  return (
    <DashboardView
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      analysisResults={analysisResults}
      selectedResultIndex={selectedResultIndex}
      setSelectedResultIndex={setSelectedResultIndex}
      onBack={() => setView('home')}
    />
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
```

### Step 4: 验证

Run: `python -c "from app.ui.build_frontend import BUILT_FRONTEND_HTML; assert 'analyzeByUidStream' in BUILT_FRONTEND_HTML; print('bundle len:', len(BUILT_FRONTEND_HTML))"`
Expected: bundle 长度增加（注意 ProgressView 仍未在 LOAD_ORDER 里——Task 8 修复）

回归：`python -m pytest tests/ -v`
Expected: 全部 passed

### Step 5: 提交

```
git add app/static/js/app.jsx
git commit -m "feat(sse): integrate streaming view in app.jsx (replace fake LOADING_TEXTS animation)"
```

---

# Task 8：路由挂载 + LOAD_ORDER 注册（与 E1 协调点）

**Files**:
- Modify: `app/main.py`（在现有 `include_router(analyze_router, ...)` 后追加一行；**E1 协调点 — 见 Plan 顶部说明**）
- Modify: `app/ui/build_frontend.py`（`LOAD_ORDER` 中加入 `js/components/ProgressView.jsx`）
- Test: `tests/test_main_routing_sse.py`（新建，验证路由可达）

### Step 1: 写失败测试

```python
# tests/test_main_routing_sse.py
"""Verify /api/analyze-stream is mounted on the main FastAPI app."""

from fastapi.testclient import TestClient

from app.main import app


def test_analyze_stream_route_registered():
    client = TestClient(app)
    routes = [getattr(r, 'path', None) for r in app.routes]
    assert "/api/analyze-stream" in routes


def test_analyze_stream_smoke(monkeypatch):
    """End-to-end smoke: real app routes a real SSE request."""
    monkeypatch.setenv("MODEL_MODE", "mock")
    client = TestClient(app)
    with client.stream(
        "POST", "/api/analyze-stream",
        json={"uid": "824812551379353600", "application_time": "2026-04-15T12:00:00"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.read().decode("utf-8")
    assert "analysis_started" in body
    assert "analysis_completed" in body


def test_progress_view_in_frontend_bundle():
    from app.ui.build_frontend import BUILT_FRONTEND_HTML
    assert "ProgressView" in BUILT_FRONTEND_HTML
```

### Step 2: 跑测试确认失败

Run: `python -m pytest tests/test_main_routing_sse.py -v`
Expected: FAIL（路由未挂载、ProgressView 未在 bundle）

### Step 3: 写实现

**`app/main.py` 改动（E1 协调点）**：在 L60 `app.include_router(analyze_router, prefix="/api", tags=["analyze"])` 之后追加一行：

```python
from app.api.analyze_stream import router as analyze_stream_router
app.include_router(analyze_stream_router, prefix="/api", tags=["analyze"])
```

**Note for E1 rebase**：如果窗口 3 已经先 commit 修改了 `app/main.py`，在这一段后追加新 `include_router` 行即可，无逻辑冲突；新增 import 行附近也是 append 模式（参考现有 L62-63 `data_acquisition_router` 的写法）。

**`app/ui/build_frontend.py` 改动**：在 `LOAD_ORDER` 列表中 `"js/components/LoadingView.jsx",` 之后插入 `"js/components/ProgressView.jsx",`：

```python
LOAD_ORDER = [
    "js/utils/normalize.js",
    "js/utils/chartLookup.js",
    "js/utils/displayMappers.js",
    "js/utils/advice.js",
    "js/services/api.js",
    "js/components/common/InfoRow.jsx",
    "js/components/common/ProgressRow.jsx",
    "js/components/common/CreditProgressRow.jsx",
    "js/components/common/LegendDot.jsx",
    "js/components/common/MarkdownBlock.jsx",
    "js/components/common/MetricHelpTip.jsx",
    "js/components/common/InstallBucketModal.jsx",
    "js/components/common/CategoryAppsModal.jsx",
    "js/components/common/TimelineItem.jsx",
    "js/components/common/LabelsOverviewCard.jsx",
    "js/components/charts/DonutChart.jsx",
    "js/components/charts/CreditGauge.jsx",
    "js/components/charts/CreditRiskStructure.jsx",
    "js/components/panels/AppPanel.jsx",
    "js/components/panels/BehaviorPanel.jsx",
    "js/components/panels/CreditPanel.jsx",
    "js/components/panels/RichCreditPanel.jsx",
    "js/components/panels/ComprehensivePanel.jsx",
    "js/components/panels/ProductAdvicePanel.jsx",
    "js/components/panels/OpsAdvicePanel.jsx",
    "js/components/HomeView.jsx",
    "js/components/LoadingView.jsx",
    "js/components/ProgressView.jsx",
    "js/components/DashboardView.jsx",
    "js/app.jsx",
]
```

**注意**：`build_frontend.py` 顶部有 `BUILT_FRONTEND_HTML = _HTML_TEMPLATE.format(...)` 这种**模块级 eager 执行**——build_frontend 在导入时一次性读所有 jsx 文件、缓存 HTML。这意味着改 LOAD_ORDER 后**必须重启 Python 进程**才能让新 ProgressView 出现在 bundle 里（pytest 每次 fresh import，无问题）。

### Step 4: 跑测试确认通过

Run: `python -m pytest tests/test_main_routing_sse.py -v`
Expected: 3 passed

**最终全量回归**（Step 7 交付检查）：`python -m pytest tests/ -v`
Expected: 全部 passed（≥ 209 = 原 206 + 4 + 4 + 4 + 2 + 3 ≈ 223）

### Step 5: 提交（最终 [complete]）

```
git add app/main.py app/ui/build_frontend.py tests/test_main_routing_sse.py
git commit -m "feat(sse): mount /api/analyze-stream + register ProgressView in LOAD_ORDER

[complete] sse-progress-plan: SSE progress streaming"
```

---

# Step 7 交付清单（Plan 全部 Task 完成后执行）

1. 全量测试：`python -m pytest tests/ -v`，确认全部通过
2. 在 `TASK.md` 添加 D2 行（位置见下，TASK.md 在 Step 4 已经记录了 Plan 路径，最终交付时打勾）：
   ```
   - [x] D2 SSE 进度推送 → docs/plans/sse-progress-plan.md
   ```
3. 最终 commit message 已在 Task 8 含 `[complete] sse-progress-plan` 前缀，无需额外 commit
4. **不 push** — 等用户统一 push

---

# 五点检查法自查（提交 STOP 3 前的自检）

| # | 检查项 | 自查结果 |
|---|---|---|
| 1 | 每个 Task 有精确文件路径？ | ✅ 8 个 Task 全列了 Modify/Create 绝对路径 |
| 2 | 有占位符（TBD/TODO/implement later）？ | ✅ 无（所有"Plan 阶段确认"已敲死，见 §"已 Plan 阶段敲定的细节"表） |
| 3 | 代码步骤有完整代码块？ | ✅ Task 1-4 + 6-8 全部完整代码块；Task 5/6/7 前端无 JS test 是项目既有约定（无 JS test runner），代码本身完整 |
| 4 | 有验证命令 + 预期输出？ | ✅ 每个 Task 有 `python -m pytest ...` 或 `python -c ...` 命令 + Expected |
| 5 | 一个人不问问题能执行完？ | ✅ 包含异常路径（Task 1 stage 1 单 skill 异常处理）、E1 协调说明、bundle eager-load 警告等 |

---

# 待你五点检查法审核
