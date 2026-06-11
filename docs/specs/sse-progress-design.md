# SSE 进度推送 Design Doc

- **状态**：Step 2 设计待确认
- **日期**：2026-05-01
- **作者**：Claude（与用户共同设计，Q1-Q6 全部锁定）
- **关联 Plan**：`docs/plans/sse-progress-plan.md`（Step 4 产出）

---

## 1. 问题背景

当前 `/api/analyze` 是同步阻塞端点，单 UID 的 6 个 Skill 按 stage 0→1→2 调度，端到端耗时 ~160s（实测见 TASK.md L106：`orchestrator.analyze(['824812551379353600'])` 总耗时 ~163s）。前端发起 POST 后没有任何进度反馈：

- 前端现状（`app/static/js/app.jsx` L46-61）用 `setInterval` 每 800ms 切换 5 条**假文案**（`LOADING_TEXTS`），和真实进度无关
- 用户 ~160s 内看不到"系统在干嘛、卡了还是在跑、哪个 Skill 慢"
- 多 UID 批量场景更糟（UID 串行，3 UID = ~480s 白等）

**目标**：在不破坏现有同步语义的前提下，新增 SSE 端点让前端实时收到每个 Skill 的开始/完成/失败事件，单 UID 全部完成时可拿到完整结果直接渲染 dashboard。

---

## 2. 方案选型与决策（Q1-Q6 锁定结果）

### 2.1 端点设计（Q1 → 方案 A）

**新增 `POST /api/analyze-stream`，独立 SSE 端点**，与现有 `/api/analyze` 完全隔离。

- `/api/analyze` 一字节不动，所有现有调用方（包括 `/api/analyze-file`）行为不变
- `/api/analyze-stream` 返回 `text/event-stream`，请求体复用 `AnalyzeRequest` schema（`uid` / `uids` / `application_time`）
- `/api/analyze-file-stream` 留到后续（文件批量是低频运营场景，先验证 callback 机制跑通）

**为什么不选 header 分流（B）**：FastAPI `response_model` 与 `StreamingResponse` 共存会让路由签名变丑，OpenAPI schema 混乱；调试容易踩坑。
**为什么不选两步式 request_id（C）**：违反"无状态独立端点"原则，需要任务字典 + Redis，爆破半径过大，且和"不引入新依赖"硬约束冲突。

### 2.2 事件格式与粒度（Q2 + Q5 → 三态推送 + 每 Skill 独立推 + analysis_progress）

- **三态推送**：每个 Skill 推 `started` → `completed`（或 `failed`），不推 `progress(%)`（Skill 内部六步管线没有进度概念，假百分比是负价值）
- **每 Skill 独立事件**：用 `uid` 字段区分多 UID，前端按 UID 分组渲染
- **新增 `analysis_progress` 事件**：单 UID 全部 Skill 完成时推一次，携带该 UID 的 `UserAnalysisResult`，支持多 UID 早渲染
- **`analysis_completed` 携完整 results**：前端拿到直接进 dashboard，无需二次调用 `/api/analyze`
- **`skill_failed` 不终止流**（与现有 orchestrator 语义一致：失败 Skill 走 fallback、其他 Skill 继续跑、最终 result 照常推）

### 2.3 Orchestrator 改造（Q3 → progress_callback + queue.Queue）

- `SkillRegistry.run_all()` 加可选参数 `progress_callback: Callable[[dict], None] | None = None`
- `AnalysisOrchestrator.analyze()` / `_analyze_single_user()` 透传 callback
- `/api/analyze-stream` 端点内部用标准库 `queue.Queue` 桥接：
  - 后台线程跑 `orchestrator.analyze(uids, progress_callback=lambda evt: queue.put(evt))`
  - SSE generator 在主协程里 `queue.get()`（通过 `loop.run_in_executor` 不阻塞协程），yield SSE 行
  - 后台线程结束推 `analysis_completed` + `None` 哨兵通知 generator 收尾
- **`/api/analyze` 完全不传 callback**，`SkillRegistry.run_all` 在 callback 为 None 时跳过推送 → 同步路径零行为变化

**关注点分离**：
- `SkillRegistry` 只知道"调 callback"，不知道有 SSE
- SSE 端点只知道"从 queue 读、yield 行"，不知道 Skill 怎么跑
- 同步 `/api/analyze` 既不知道 callback 也不知道 queue

### 2.4 前端进度展示（Q4 → 步骤列表 6 行 + 聚合标题 + fetch/ReadableStream）

- **新增 `app/static/js/components/ProgressView.jsx`**：6 行步骤列表，每行一个 Skill，状态图标 ⚪→⏳→✅/⚠️
- **聚合标题**：顶部显示"分析进度：3 / 6 完成 ⏱ 已用 47s"，已用时间前端 `Date.now()` 差值算（不需后端推）
- **替换假动画**：删除 `app.jsx` 的 `playLoadingSequence` + `LOADING_TEXTS`，新增 `view='streaming'` 状态
- **新增 `analyzeByUidStream(uid, applicationTime, onEvent)`**：在 `app/static/js/services/api.js`，用 `fetch + ReadableStream` 解析 SSE（不用 `EventSource`，因为端点是 POST）
- **完成耗时**：`skill_completed` 事件带 `duration_ms`，行尾显示"28.4s"

### 2.5 多 UID 处理（Q5 → 当前 UID 展开 + 其他折叠）

- 同一时刻最多一个 UID 在跑（orchestrator 串行 for-loop），展开 6 行步骤列表
- 其他 UID 折叠成摘要行：`⚪ UID xxx 等待中` / `✅ UID xxx 已完成 28.4s`（可点击展开 dashboard）

### 2.6 错误与超时处理（Q6 全部锁定）

| 维度 | 决策 |
|---|---|
| 总超时 | 后端硬上限（具体秒数 Plan 阶段定，建议 600-900s），到点推 `stream_error` + 关闭流 |
| Heartbeat | 每 ~15s 推 `: keepalive\n\n`（SSE 注释行，前端忽略），防反向代理断连 |
| 浏览器断线 | 不自动重连；fetch error → 前端切回 home view + 提示"分析中断，请重新发起分析" |
| Skill 失败 | 不级联、不终止流；下游 Skill 照常拿 fallback 跑；`analysis_progress`/`analysis_completed` 照常推；UI 该 Skill 行显示 ⚠️ |
| `stream_error` 触发 | orchestrator 整体异常 / 后台线程死掉无回调 / 总超时 watchdog；输入校验失败仍走 HTTP 400（不进流） |
| 取消请求 | 前端 abort fetch，后端线程继续跑完（资源浪费可接受，~160s 任务用户取消概率低，零侵入 orchestrator） |

---

## 3. SSE 事件 JSON Schema

### 3.1 事件类型表（7 种）

| `type` | 触发时机 | 关键字段 |
|---|---|---|
| `analysis_started` | 流开始（端点接收请求后第一个事件） | `uids`, `total_skills_per_uid` |
| `skill_started` | 单个 Skill 即将执行 | `uid`, `skill`, `stage` |
| `skill_completed` | Skill 正常返回 | `uid`, `skill`, `stage`, `duration_ms` |
| `skill_failed` | Skill 抛异常（兜底事件，正常情况下 Skill 内部规则引擎已降级，不会走到这里） | `uid`, `skill`, `stage`, `error_message`, `duration_ms` |
| `analysis_progress` | 单 UID 全部 Skill 完成 | `uid`, `result: UserAnalysisResult` |
| `analysis_completed` | 全部 UID 完成（流的最后一个事件） | `results: [UserAnalysisResult, ...]` |
| `stream_error` | 流自身异常（非 Skill 业务异常） | `error_message` |

### 3.2 SSE 线路格式

每个事件按 SSE 标准格式输出：

```
data: {"type":"skill_started","uid":"824812551379353600","skill":"app_profile","stage":0}

```

每条事件之间用空行分隔；心跳用注释行：

```
: keepalive

```

### 3.3 字段精确命名

具体字段名（如 `error_message` vs `error` vs `message`、`duration_ms` vs `elapsed_ms`）**Plan 阶段在写 contracts 文件时敲死**——硬约束 #13。

---

## 4. Orchestrator 改动方式（详细）

### 4.1 改动点清单

| 文件 | 改动 |
|---|---|
| `app/runtime_skills/base.py` | `SkillRegistry.run_all()` 新增 `progress_callback` 参数；`_run_skill` 内部三处 callback 调用（Skill 开始/完成/失败） |
| `app/services/orchestrator.py` | `analyze()` 和 `_analyze_single_user()` 透传 callback；`_analyze_single_user` 完成时调一次 `analysis_progress` callback |
| `app/api/analyze_stream.py`（新文件） | `/api/analyze-stream` 路由 + SSE generator + queue 桥接 + watchdog 超时 |
| `app/main.py` | `include_router(analyze_stream.router)`（**注意：和 E1 窗口 3 协调**，见 §7） |

### 4.2 callback 调用时序伪码

```python
# SkillRegistry.run_all (改后)
def run_all(self, uid, progress_callback=None, **kwargs):
    for stage in stages:
        for skill in stage_skills:
            if progress_callback:
                progress_callback({"type": "skill_started", "uid": uid, "skill": skill.name, "stage": stage})
            t0 = perf_counter()
            try:
                result = skill.analyze(uid=uid, **skill_kwargs)
                if progress_callback:
                    progress_callback({
                        "type": "skill_completed", "uid": uid, "skill": skill.name,
                        "stage": stage, "duration_ms": int((perf_counter() - t0) * 1000)
                    })
            except Exception as exc:
                if progress_callback:
                    progress_callback({
                        "type": "skill_failed", "uid": uid, "skill": skill.name,
                        "stage": stage, "error_message": str(exc),
                        "duration_ms": int((perf_counter() - t0) * 1000)
                    })
                raise  # 现有语义保留：异常上抛由调用方决定
            results[skill.name] = result
```

### 4.3 SSE 端点伪码

```python
# app/api/analyze_stream.py
@router.post("/analyze-stream")
async def analyze_stream(request: AnalyzeRequest):
    q: queue.Queue = queue.Queue()

    def run_in_thread():
        try:
            def cb(evt): q.put(evt)
            q.put({"type": "analysis_started", "uids": request.get_uid_list(), "total_skills_per_uid": 6})
            response = orchestrator.analyze(request.get_uid_list(),
                                             application_time=request.application_time,
                                             progress_callback=cb)
            q.put({"type": "analysis_completed", "results": [r.model_dump() for r in response.results]})
        except Exception as exc:
            q.put({"type": "stream_error", "error_message": str(exc)})
        finally:
            q.put(None)  # 哨兵

    executor.submit(run_in_thread)  # 具体起线程方式 Plan 阶段定

    async def event_gen():
        loop = asyncio.get_event_loop()
        last_event = time.monotonic()
        while True:
            # 带超时的 queue.get，到点推 heartbeat
            try:
                evt = await asyncio.wait_for(
                    loop.run_in_executor(None, q.get), timeout=15
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if evt is None:
                break
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

总超时 watchdog 和 `analysis_progress` 在每 UID 完成时的注入点（`_analyze_single_user` 末尾）实现细节 Plan 阶段敲死。

---

## 5. 前端组件设计

### 5.1 新增/改动文件

| 文件 | 改动类型 | 职责 |
|---|---|---|
| `app/static/js/components/ProgressView.jsx` | 新增 | 6 行步骤列表 + 聚合标题；多 UID 折叠摘要行 |
| `app/static/js/services/api.js` | 修改 | 新增 `analyzeByUidStream(uid, applicationTime, onEvent, signal)` |
| `app/static/js/app.jsx` | 修改 | `view` 新增 `'streaming'`；删除 `playLoadingSequence`/`LOADING_TEXTS`；`handleAnalyze` 走 streaming 分支 |
| `app/ui/build_frontend.py` | 修改 | `LOAD_ORDER` 加入 `js/components/ProgressView.jsx` |

### 5.2 ProgressView 状态机

每行 Skill 的状态由 SSE 事件驱动：

| 收到事件 | 行状态切换 |
|---|---|
| 初始（无事件） | `pending` ⚪ |
| `skill_started` | `running` ⏳ + 闪烁动画 |
| `skill_completed` | `done` ✅ + 显示 `duration_ms` |
| `skill_failed` | `failed` ⚠️ + 显示"降级运行" |

Skill 显示名称映射（前端常量）：

| skill (后端) | UI 显示 |
|---|---|
| `app_profile` | App 画像 |
| `behavior_profile` | 行为画像 |
| `credit_profile` | 征信画像 |
| `comprehensive_profile` | 综合画像 |
| `product_advice` | 产品策略 |
| `ops_advice` | 运营策略 |

### 5.3 SSE 解析（fetch + ReadableStream）

伪码：

```js
async function analyzeByUidStream(uid, applicationTime, onEvent, signal) {
  const resp = await fetch('/api/analyze-stream', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
    body: JSON.stringify({uid, application_time: applicationTime}),
    signal,
  });
  if (!resp.ok) throw new Error(`SSE ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {stream: true});
    const events = buf.split('\n\n');
    buf = events.pop();  // 最后一段可能不完整
    for (const block of events) {
      if (block.startsWith(':')) continue;  // 心跳注释行
      const dataLine = block.split('\n').find(l => l.startsWith('data:'));
      if (!dataLine) continue;
      const evt = JSON.parse(dataLine.slice(5).trim());
      onEvent(evt);
    }
  }
}
```

### 5.4 多 UID 折叠行为

- 当前正在跑的 UID（最近一次 `skill_started` 的 uid）：展开 6 行步骤列表
- 其他 UID：折叠成单行摘要
  - 还没开始：`⚪ UID xxx 等待中`
  - 已完成（收到 `analysis_progress`）：`✅ UID xxx 已完成 28.4s`（可点击展开 dashboard）

---

## 6. Mock 模式兼容性

硬约束 #3 要求 mock 模式也推 SSE 事件。落地方式：

- mock 模式下每个 Skill `analyze()` 瞬间返回（~毫秒级），callback 照常触发
- SSE 事件流会以"高速放电"形式快速推完所有事件，前端能看到 6 个 ✅ 在 1 秒内连续点亮——这正是 mock 模式期望的视觉表现
- `ModelClient` 在 mock/gemini/vertex 三种模式下对 SSE 路径完全透明

---

## 7. 与 E1（窗口 3，埋点解析）协调 — `app/main.py`

硬约束 #14 提示：E1 窗口 3 也会改 `app/main.py`。

**协调策略**：
- 改动隔离在一行：`app.include_router(analyze_stream.router, prefix="/api")`
- 谁先改先 commit；后到的 rebase 时只解决这一行 conflict（两个都是新增 include_router 调用，append 即可，无逻辑冲突）
- 在 Plan 中**单独标注哪个 Task 改 `app/main.py`**（建议放在最后一个 Task，方便 rebase）

---

## 8. 数据流总览

```
POST /api/analyze-stream { uid: "...", application_time: "..." }
   │
   ├─ 创建 queue.Queue
   ├─ executor.submit(run_in_thread)
   │     │
   │     ├─ q.put({type: "analysis_started", ...})
   │     ├─ orchestrator.analyze(uids, progress_callback=cb)
   │     │     │
   │     │     └─ for uid in uids: _analyze_single_user(uid, callback)
   │     │           │
   │     │           ├─ SkillRegistry.run_all(uid, progress_callback=cb)
   │     │           │     │
   │     │           │     ├─ stage 0 (并行 ThreadPool):
   │     │           │     │     cb(skill_started) → analyze() → cb(skill_completed)
   │     │           │     │     [并发 3 路]
   │     │           │     ├─ stage 1: 同上
   │     │           │     └─ stage 2 (并行): 同上
   │     │           │
   │     │           └─ cb({type: "analysis_progress", uid, result})
   │     │
   │     ├─ q.put({type: "analysis_completed", results: [...]})
   │     └─ q.put(None)  # 哨兵
   │
   └─ event_gen() 主协程:
         while True:
             evt = await loop.run_in_executor(None, q.get)  # 带 15s 超时
             if evt is None: break
             yield f"data: {json.dumps(evt)}\n\n"
         # 超时分支: yield ": keepalive\n\n"
```

---

## 9. Scope / Out-of-Scope

### Scope（本次实现）
- 新增 `POST /api/analyze-stream` SSE 端点
- `SkillRegistry.run_all` + orchestrator 加 `progress_callback` 参数
- 前端 `ProgressView` 组件 + 替换假动画
- 7 种事件类型完整实现（含 heartbeat、stream_error、analysis_progress）
- 总超时 watchdog
- mock 模式兼容
- 单 UID 和多 UID 场景

### Out-of-Scope（本次不做）
- `/api/analyze-file-stream`（文件上传 + SSE，留后续）
- 浏览器断线自动重连 / 续传进度
- 后端任务状态字典 / Redis / request_id
- WebSocket / gRPC 流 / 长轮询等替代方案
- Skill 内部进度（六步管线分步推送）—— 现有架构无此能力
- 前端 abort 时后端任务取消（线程继续跑完）
- Skill 级超时（仅总超时）

---

## 10. 验证策略概览

Plan 阶段会逐 Task 写 TDD 测试，本节列总体验证维度：

- **单元测试**：
  - `SkillRegistry.run_all` 不传 callback 时行为完全等同改造前（现有 206 测试零回归）
  - `progress_callback` 接收到的事件序列符合 7 种类型 + 顺序约束
  - mock 模式下事件顺序正确
- **集成测试**：
  - `/api/analyze-stream` 端到端：发请求 → 解析 SSE 流 → 校验事件序列
  - heartbeat 触发（mock 一个 >15s 慢 Skill）
  - skill_failed 不终止流场景
  - 多 UID 场景 `analysis_progress` 数量 == UID 数
- **回归测试**：
  - `/api/analyze` 行为零变化（response 字节级 diff）
  - 全量 `python -m pytest tests/ -v` 必须通过

---

## 11. 与现有架构的兼容性总结

| 现有机制 | SSE 落地后状态 |
|---|---|
| `/api/analyze` 同步端点 | 一字节不动 |
| `/api/analyze-file` | 一字节不动 |
| `BatchAnalysisService` | 一字节不动 |
| `SkillRegistry.run_all` 签名 | 加可选参数 `progress_callback=None`，向后兼容 |
| `BaseSkill.analyze(uid, **kwargs)` 签名 | 一字节不动（硬约束 #1 严守） |
| 6 个 Skill 实现 | 一字节不动 |
| `ModelClient` 三种模式 | 一字节不动 |
| 现有 206 测试 | 必须全部通过 |

---

## 12. 待 Plan 阶段敲定的细节（标记 "Plan 阶段确认"）

1. SSE 事件 JSON 字段精确命名（`error_message` vs `error`、`duration_ms` vs `elapsed_ms` 等）
2. 总超时具体秒数（建议 600-900s）
3. heartbeat 间隔具体秒数（建议 15s）
4. 后台线程实现方式（`ThreadPoolExecutor.submit` vs `threading.Thread`）
5. `app/main.py` 改动放在哪个 Task（与 E1 窗口 3 协调，建议最后一个 Task）
6. ProgressView 视觉细节（图标 unicode、颜色、字号、动画 CSS）
7. `analysis_progress` 事件中 `result` 字段是 `UserAnalysisResult.model_dump()` 全量还是精简版

---

## 13. 更新记录

- [2026-05-01] 初始创建（Q1-Q6 全部锁定后产出）
