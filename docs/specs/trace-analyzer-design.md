# Trace Analyzer 设计文档（E1：单用户埋点深度解析）

- **状态**：Design 已确认（Q1-Q6 锁定）
- **作者**：v-yimingliu
- **日期**：2026-05-01
- **关联 Plan**：docs/plans/trace-analyzer-plan.md（Step 4 产出）
- **关联 PR / Branch**：main（窗口 3）

---

## 1. 问题背景与产品场景

### 1.1 现有行为画像链路的局限

当前 `BehaviorProfileSkill` 六步管线把 `data/behavior/{uid}.csv` 原始事件聚合成统计指标后，原始序列就丢了：

- `feature_builder.py` 输出 `login_days_30d / avg_session_minutes / pricing_event_count` 等汇总数值
- `explainer.py` 喂给 LLM 的是这些汇总数值，**不是原始事件序列**
- 因此 LLM 无法分析：
  - 操作路径（用户先去哪个页面 → 再去哪个 → 在哪卡住）
  - 摩擦点（哪个步骤重试了 4 次）
  - 时序模式（每次登录都在凌晨 2-4 点）

### 1.2 产品侧三个核心场景（来自 docs/技术路线/）

1. **流失归因**：抽取流失用户最后 N 步操作日志，LLM 自动总结故事线
   - 示例："分析 800 个流失日志，发现 85% 的用户点击'提交'后，因为收不到验证码而反复点击退出"
2. **智能提示**：检测到反复操作/长时间静止，生成针对性干预话术
   - 示例："检测到您在上传身份证环节停留较久，是因为光线问题吗？试试打开闪光灯"
3. **客群聚类**：基于行为序列发现隐性客群（"深夜焦虑型用户"等）—— **E2 范围，不在本设计内**

### 1.3 本次目标（E1）

针对**单 uid**的原始事件序列做深度解析，输出操作路径图、摩擦热点、流失归因故事线、干预建议。支撑产品侧场景 1 和场景 2，为场景 3（E2）打基础。

---

## 2. 方案选型（Q1-Q6 决策记录）

### Q1：API 入口设计 → 方案 A
- **选定**：新增 `GET /api/trace/{uid}` 独立端点，与 `/api/analyze` 完全解耦
- 理由：trace 按需触发（前端点"深度解析"按钮才请求）；输出结构和 `UserAnalysisResult` 差异大，独立端点改动面最小
- 前端约束：响应可能耗时较长（CSV 读取 + 规则预处理 + LLM 调用），需要 loading 状态

### Q2：输入数据来源 → 方案 A
- **选定**：trace 直接读 `data/behavior/by_uid/{uid}.csv` 原始 CSV
- 理由：文件已就位、列结构稳定；不为还没有的数仓后端扩展 Repository 抽象（YAGNI）
- 4 点约束：
  1. 输入路径前缀通过 settings 读取（与现有 behavior_profile 一致）
  2. 文件不存在 → HTTP 404 / `data_missing`
  3. 事件数 < 阈值 → `insufficient_events`，不调 LLM（阈值数字 Plan 阶段确认）
  4. 列契约固化在 `trace_analyzer/data_access.py`

### Q3：和现有 behavior_profile 的关系 → 方案 C
- **选定**：放在 `app/runtime_skills/trace_analyzer/`，不注册 SkillRegistry
- 治理边界（Design Doc 原文 5 点）：
  1. `app/runtime_skills/trace_analyzer/` 是**独立服务模块**，不是 SkillRegistry Skill
  2. 入口命名故意不用 `*_agent.py` 后缀（避免误读为 BaseSkill 子类），用 `analyzer.py`
  3. 不在 `_build_registry()` 注册
  4. 路由通过 `app/api/trace.py` 单独挂载，由 `app/main.py` `include_router`
  5. 复用六步管线的**结构**（contracts / data_access / feature_builder / decision_engine / explainer / assembler），但**不复用 BaseSkill 接口**

### Q4：LLM 的角色 → 方案 B（规则预处理 + LLM 双轨）
- **选定**：规则层从原始事件提取 5 类结构化事实，LLM 层基于结构化事实生成 3 类叙述
- **规则层 5 类事实**：
  1. 路径图（top-N 跳转 + top-N 页面）
  2. 摩擦热点列表（步骤名 + 重试次数 + 平均停留 + 错误次数 + severity）
  3. 时间分布（24 小时直方图 + 活跃时段标签）
  4. 关键节点序列（最后 N 步 / 流失前 N 步）
  5. churn_root_cause 先验候选（基于规则匹配 6 种模式给 0-2 个候选 + 置信度）
- **LLM 层 3 类叙述**：
  1. 流失归因故事线（中文 narrative，必须引用规则层提供的具体页面/字段/次数，禁止泛化模板）
  2. 干预建议（针对每个 top-3 摩擦热点出 1 条具体话术）
  3. churn_root_cause 最终判定（在规则先验基础上选 1-2 个最相关值，与 ops_advice 的 6 种候选值兼容）
- **降级路径**：
  - LLM 失败/mock → `model_unavailable`，保留规则产物，叙述性字段填模板兜底
  - 事件 < 阈值 → `insufficient_events`，规则产物为空，LLM 不调用

### Q5：输出结构设计
- **双层契约**：
  - 内部六步管线 → TypedDict（`app/runtime_skills/trace_analyzer/contracts.py`）
  - API 响应顶层 → Pydantic model（`app/schemas/trace_analyzer.py`）
- **HTTP 状态码**：
  - 404 仅用于 `data_missing`
  - 其他 4 种状态全部 200 + status 字段
- **status 5 种枚举**：`ok / data_missing / insufficient_events / model_unavailable / error`
- **12 字段全必选**（见 §4 Schema）
- `key_events_tail` 脱敏规则：丢 `ip` 列 / `url` 只保留 path（不含 query）/ `extend` 只保留 `field` 字段

### Q6：token 预算控制 → 方案 B（三层分层压缩）
- **三层独立预算**：
  - 第 1 层（聚合摘要，永远全量）：~1-2K token
  - 第 2 层（摩擦点详情 top-K）：≤2K token
  - 第 3 层（关键节点序列最后 N 步）：≤5K token
- **总上限**：≤8K token（具体数字 Plan 阶段精化）
- **超限护栏顺序**（信息密度从高到低保护）：
  1. 第 3 层 N 减半
  2. 第 2 层 K 减半
  3. 第 1 层永不动
- **token 估算**：trace 模块内自实现最小版 CJK 加权（不依赖 data_acquisition_agent）
- **mock 模式跳过 token 检查**

---

## 3. 输入数据契约

### 3.1 CSV 列定义（来自 `data/behavior/by_uid/{uid}.csv`）

| 列 | 类型 | 说明 |
|---|---|---|
| `uid` | str | 主键 |
| `servertimestamp` | int(ms) | 服务端时间戳 |
| `timestamp_` | int(ms) | 客户端时间戳 |
| `scenetype` | str | 页面/场景类型（用作"页面"维度） |
| `processtype` | str | 流程类型 |
| `eventname` | str | 事件类型（`field-click / field-edit / page_onPause / page_onResume / ...`） |
| `extend` | JSON str | 扩展字段（含 `field` = 触发的输入框名等） |
| `clientmodel` | str | 设备型号 |
| `clientosversion` | str | OS 版本 |
| `url` | str | 页面 URL |
| `refer` | str | 来源 URL |
| `ip` | str | IP（**输出脱敏丢弃**） |

### 3.2 事件量级
- 单 uid 实测约 600 行
- 阈值（`insufficient_events`、top-N、最后 N 步等具体数字）→ Plan 阶段确认

---

## 4. 输出数据契约（API Response Schema）

### 4.1 顶层 Pydantic model：`TraceAnalyzeResponse`

文件：`app/schemas/trace_analyzer.py`

```python
class TraceAnalyzeResponse(BaseModel):
    uid: str
    status: Literal["ok", "data_missing", "insufficient_events", "model_unavailable", "error"]
    event_window: EventWindow             # {start, end, total_events, analyzed_events}
    path_graph: PathGraph                 # {top_transitions, top_pages}
    friction_hotspots: list[FrictionHotspot]
    time_pattern: TimePattern             # {hour_histogram[24], active_window_label}
    churn_root_cause: list[str]           # 1-2 个值，6 种候选之一
    churn_story: str                      # LLM 故事线（mock/失败时填模板）
    intervention_suggestions: list[InterventionSuggestion]
    key_events_tail: list[KeyEvent]       # 脱敏后的最后 N 步关键事件
    model_trace: ModelTrace
    errors: list[str]
```

子模型字段（具体字段名 Plan 阶段精化）：
- `EventWindow`: `start`(ISO str), `end`(ISO str), `total_events`(int), `analyzed_events`(int)
- `PathGraph`: `top_transitions: list[{from, to, count}]`, `top_pages: list[{page, visit_count, avg_stay_seconds}]`
- `FrictionHotspot`: `step`, `retry_count`, `error_count`, `avg_stay_seconds`, `severity` (`high|medium|low`)
- `TimePattern`: `hour_histogram: list[int][24]`, `active_window_label: str`
- `InterventionSuggestion`: `hotspot`, `advice`, `channel_hint`
- `KeyEvent`: `ts_offset`(秒，相对会话起点), `page`, `event`, `field?`（脱敏后字段，无 ip / 无 url query / 无完整 extend）
- `ModelTrace`: `mode`, `used_llm`, `model_name`, `fallback_reason`

### 4.2 内部 TypedDict 契约（`app/runtime_skills/trace_analyzer/contracts.py`）

```python
class TraceRunContext(TypedDict):
    uid: str
    country_code: str
    application_time: str
    enable_llm_explanation: bool

class TraceRawData(TypedDict):
    uid: str
    events_df: Any  # pandas DataFrame，不在 TypedDict 表达
    data_status: str  # ok | data_missing | error
    errors: list[str]

class TraceFeatureBundle(TypedDict):
    uid: str
    event_window: dict
    path_graph: dict
    friction_hotspots: list[dict]
    time_pattern: dict
    key_events_tail: list[dict]
    churn_root_cause_candidates: list[dict]  # 规则层先验
    feature_status: str
    errors: list[str]

class TraceDecisionResult(TypedDict):
    uid: str
    decision_status: str
    prompt_payload: dict   # 已应用 token 护栏后的 LLM 输入
    fallback_story: str    # 模板兜底叙述
    fallback_interventions: list[dict]
    errors: list[str]

class TraceExplanationResult(TypedDict):
    uid: str
    explanation_status: str  # ok | model_unavailable | skipped
    used_llm: bool
    churn_story: str
    intervention_suggestions: list[dict]
    churn_root_cause: list[str]
    model_trace: dict
    errors: list[str]
```

---

## 5. 模块结构（六步管线）

```
app/runtime_skills/trace_analyzer/
├── __init__.py
├── analyzer.py              # 入口（不带 _agent 后缀，避免被误读为 BaseSkill）
├── contracts.py             # TypedDict 契约
├── data_access.py           # 读 CSV → DataFrame
├── feature_builder.py       # 5 类规则事实提取 + token 估算 + 护栏降级
├── decision_engine.py       # 组装 prompt_payload + 模板兜底
├── explainer.py             # 调 LLM（ModelClient）+ JSON 解析 + churn_root_cause 收敛
└── assembler.py             # 拼装 Pydantic 响应

app/api/trace.py             # GET /api/trace/{uid} 路由
app/schemas/trace_analyzer.py # Pydantic 响应 model
app/prompts/trace_analyzer_prompt.md  # LLM prompt 模板
app/main.py                  # 单独 Task 加 include_router（注意 D2 协调）

tests/test_trace_analyzer_phase1.py  # 测试入口（参考 test_app_profile_phase1.py）
```

每个文件 ≤500 行（CLAUDE.md 硬约束）。

---

## 6. 数据流向

```
GET /api/trace/{uid}
  ↓
app/api/trace.py
  ↓
TraceAnalyzer.analyze(uid)              ← analyzer.py 入口
  ↓
TraceDataAccess.fetch(uid)              ← 读 CSV
  ↓ events_df (pandas DataFrame) | data_missing
TraceFeatureBuilder.build(raw_data)     ← 提取 5 类事实 + token 估算 + 护栏降级
  ↓ feature_bundle (含 prompt_payload 三层 + churn 先验)
TraceDecisionEngine.decide(features)    ← 组装 prompt_payload + 模板兜底
  ↓ decision_result
TraceExplainer.explain(decision)        ← 调 ModelClient（mock 跳过）
  ↓ explanation_result（含 LLM 输出 / model_unavailable）
TraceAssembler.assemble(decision, explanation)
  ↓
TraceAnalyzeResponse (Pydantic)
  ↓
JSON → 前端
```

---

## 7. 与现有系统的集成

### 7.1 与 ops_advice 的关系
- trace 输出的 `churn_root_cause` 字段格式（`list[str]`，6 种候选值）与 `app/runtime_skills/ops_advice/decision_engine.py` 第 55-66 行读的 `feature_bundle["churn_root_cause"]` **字段名 + 值域 100% 兼容**
- **不修改 ops_advice**：trace 是独立按需端点，输出供前端展示
- ops_advice 仍从 behavior_profile 链路拿 churn_root_cause，保持现有解耦

### 7.2 与 behavior_profile 的关系
- **不修改 behavior_profile 现有 6 个 .py**（前置硬约束 #2）
- 不复用 `BaseUserRepository.get_behavior_data`（它返回的是聚合后的 prepared_record，不是原始事件）
- trace 直接读 `data/behavior/by_uid/{uid}.csv`

### 7.3 与 data_acquisition_agent 的关系
- 不依赖 data_acquisition_agent 任何代码（YAGNI）
- 未来 da-agent V2 落到 `data/behavior/by_uid/` 的事件文件天然兼容（同一路径前缀）

### 7.4 与窗口 2（D2 SSE）的协调
- D2 也会改 `app/main.py` 加 SSE 路由
- **协调方案**：
  - trace 的 `app/main.py` 改动（`include_router(trace_router)`）放在 Plan 中**单独的小 Task**
  - 该 Task 执行前先 `git pull --rebase`，避免与 D2 冲突
  - Plan 中显式标注此 Task

---

## 8. LLM 调用与 prompt 策略

### 8.1 prompt 模板（`app/prompts/trace_analyzer_prompt.md`）
风格参考 `app/prompts/behavior_profile_prompt.md`，要求：
- **反模板硬约束**（复用 behavior_profile_prompt.md 经验）：
  - 干预建议每条必须引用具体页面名/字段名/重试次数
  - 禁止"建议优化 / 建议突出 / 建议触发"等泛化开头
  - 故事线必须基于规则层提供的事实，不允许虚构未出现的页面/字段
- **churn_root_cause 候选值固化**：6 种候选值列表写进 prompt，要求 LLM 必须选其中 1-2 个，不允许新创值（与 behavior_profile_prompt.md §churn_root_cause 推断指引保持一致）

### 8.2 ModelClient 调用
- 通过 `ModelClient.generate_structured()`（项目已有的封装），传入 `response_schema`
- mock 模式：跳过 LLM 调用，直接返回模板兜底叙述
- 失败重试：依赖 ModelClient 内置重试（不在 trace 自己实现）

### 8.3 token 护栏实现
- `feature_builder.py` 内 `_apply_token_budget(prompt_payload, budget=8000)`：
  1. 估算当前三层总 token（CJK 加权：`len(ascii)*0.25 + len(cjk)*1.0`）
  2. 若超 budget：先砍第 3 层 N 减半 → 再砍第 2 层 K 减半 → 重新估算
  3. 记录 truncation 日志到 `feature_bundle["errors"]` 或 `model_trace.fallback_reason`

---

## 9. 状态机与降级路径

| 触发条件 | status | HTTP | 行为 |
|---|---|---|---|
| CSV 不存在 | `data_missing` | **404** | 返回错误响应（依然带 status 字段，便于前端复用解析逻辑） |
| CSV 损坏 / 列缺失 | `error` | 200 | 规则产物为空，LLM 不调，errors 字段记录原因 |
| 事件数 < 阈值 | `insufficient_events` | 200 | 规则产物为空（或非常稀疏），LLM 不调 |
| LLM 失败/mock 模式 | `model_unavailable` | 200 | 规则产物完整，叙述字段填模板兜底 |
| 全链路成功 | `ok` | 200 | 规则产物 + LLM 叙述 |

---

## 10. Scope / Out-of-Scope

### Scope（E1 实现范围）
- `GET /api/trace/{uid}` 单端点
- 规则预处理 5 类事实
- LLM 叙述 3 类产物（故事线 / 干预建议 / churn_root_cause）
- 三层 token 预算 + 超限护栏
- mock 降级路径（`model_unavailable` 状态）
- key_events_tail 脱敏（丢 ip / url 只留 path / extend 只留 field）
- 单元测试覆盖：规则层 5 类事实、token 护栏、状态机 5 种状态、脱敏

### Out-of-Scope
- **trace 的 churn_root_cause 不回灌 ops_advice / behavior_profile**（仅供前端展示，未来"用精准版替换粗粒度版"是独立任务）
- 实时流式事件接入（当前是 CSV 拉取）
- 跨用户聚合归因（"分析 800 个流失日志"是 E2 范围）
- 客群聚类（"深夜焦虑型用户"是 E2 范围）
- 前端可视化实现（前端只消费 API，UI 实现不在本 Plan 内）
- 修改 behavior_profile 现有 6 个 .py（前置硬约束 #2）
- 修改 ops_advice 任何文件（保持解耦）

---

## 11. 待 Plan 阶段确认的具体数字

- `insufficient_events` 阈值（事件数 < N 时跳过 LLM）
- top-N 跳转数（路径图取 top 几个 transition）
- top-N 页面数
- top-K 摩擦热点（severity 排序后取前 K）
- 最后 N 步关键事件（key_events_tail 长度）
- 流失前 N 步关键事件（如果与"最后 N 步"不同）
- 总 token 上限的精确数字（数量级 8K，具体 8000? 7500? Plan 阶段定）
- 各层 token 预算细分（第 2 层 ≤2K 的具体值，第 3 层 ≤5K 的具体值）

---

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 长事件序列触发 token 超限 | 三层护栏自动降级，model_trace.fallback_reason 记录 truncation |
| LLM 输出 churn_root_cause 不在 6 种候选值内 | explainer 做白名单过滤，不在白名单的值丢弃，全为空时回退 `["no_clear_signal"]` |
| LLM 故事线虚构页面/字段 | prompt 反模板硬约束 + 在 evaluator/QA 阶段抽样人工校验（E1 不实现自动校验） |
| 与 D2 同改 app/main.py 冲突 | Plan 中该 Task 前 `git pull --rebase` |
| key_events_tail 脱敏遗漏导致 PII 泄露 | data_access 层硬编码白名单字段（仅 ts_offset/page/event/field），其他字段不进入序列 |
| CSV 格式未来变化 | 列契约固化在 `data_access.py`，schema 变更时只改一处 |

---

## 13. 验收标准

1. `GET /api/trace/{uid}` 在 mock 模式下返回 status=`model_unavailable`，规则产物完整
2. 在 vertex/gemini 模式下成功调 LLM，返回 status=`ok`，churn_root_cause 在 6 种候选值内
3. CSV 不存在时返回 HTTP 404 + status=`data_missing`
4. 事件数 < 阈值时返回 200 + status=`insufficient_events`
5. token 护栏单测：构造 1000+ 事件，确认第 3 层 N 自动减半且记录 truncation
6. 脱敏单测：确认 `key_events_tail` 不含 ip / url query / 完整 extend
7. 全量测试 `pytest tests/ -v` 通过（≥ 现有 206 passed）
8. 不修改 behavior_profile 6 个已有 .py（git diff 验证）
9. 不修改 ops_advice 任何文件（git diff 验证）
