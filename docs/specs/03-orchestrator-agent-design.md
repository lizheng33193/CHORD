# Design Doc #03 — Orchestrator Agent

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-05-02 |
| 作者 | v-yimingliu |
| 关联 | 依赖 Plan #01（ModelClient 抽象层）。本 Doc 不引用其他 Design Doc 章节号；依赖关系参见 PLANNING.md |

> Historical note (2026-06-03): 本文中的 pre-Phase 6 general-chat LLM/tool loop 与 `MAX_ROUNDS` 主循环描述仅保留为历史设计上下文。当前 live 行为以 `GeneralChatFlow`、`docs/specs/orchestrator-agent-decomposition.md` 与 `PLANNING.md` 为准。

## 0. 一句话目标（Goal）

在现有用户画像系统之上新增一个 Orchestrator Agent，让用户用自然语言一句话触发完整分析链路。同时把吃推理深度的 LLM 调用（Profile explainer、Trace、Orchestrator 自身）迁移到 Claude Opus 4.7，data_acquisition 保持 Gemini 不动（已有 163 测试通过，遵循 Karpathy Surgical Changes 原则）。

## 1. 背景与目标

### 1.1 当前痛点

分析师做一次完整分析的现状：
1. 用 SQL 工具自己写查询，捞出目标 UID 列表
2. 把 UID 写成本地 txt
3. 调 `/api/analyze-file` 等画像跑完
4. 切到前端 Dashboard 一个个 UID 看
5. 想看 Trace 还要单独切 Trace Tab

整套流程对分析师不友好，且每一步都需要人工把上一步结果手工传给下一步。

### 1.2 目标

让分析师用自然语言一句话表达意图：
- "分析泰国上周流失下单用户" → Agent 自主取数 → 跑画像 → 输出总结
- "看下 UID U001 的行为轨迹" → Agent 直接调 trace → 输出总结
- "查一下墨西哥本月新进高风险用户" → Agent 取数 + 跑画像 + 风险维度聚焦

Agent 在中间排工具链 + 流式回写中间过程；用户能看到每一步在做什么、能在 SQL 执行前 ACK。

### 1.3 不重新发明轮子

- 不引入 LangChain / LangGraph（PLANNING.md 已评估暂不迁移）
- 不引入 Anthropic SDK 直依赖（统一走 Maestro 端点）
- 不重写 6 Skill；Agent 调它们的现有入口

## 2. 范围与边界

### 2.1 In Scope

- Agent Loop（System Prompt + Round 控制 + Memory 读写）
- 6 工具 entry（5 个职责分组）
- JSON 文件会话持久化 + atexit + `--resume` CLI
- Eval 框架（Golden Cases + 4 维 Rubric + LLM Judge）
- Resilience 4 道防线
- Security（UID 校验 + SQL 脱敏复用 + ACK 流程 + Token 硬阻断）
- SSE 事件协议
- API 入口（`/api/orchestrator/chat` / `/sessions/{id}` / `/sessions/{id}/ack`）
- Knowledge 层（`skills/` 目录 + `load_skill` 工具）

### 2.2 Out of Scope

- 前端"自然语言对话" Tab（独立 Doc + 独立 Plan）
- ModelClient 多 Provider 重构（独立 Doc + 独立 Plan，本 Doc 假设其已落地）
- Profile explainer + Trace 切 Claude（独立 Doc + 独立 Plan）
- data_acquisition_agent 内部逻辑改造（Surgical 锁死）
- 多人协作 / 实时 push

## 3. 架构层（Harness 11 层）

### 3.1 UX/DX

- API：`POST /api/orchestrator/chat`（SSE 流式）
- 前端 Tab 由独立 Doc 落地

### 3.2 Agent

- `OrchestratorAgent` 类（`app/runtime_skills/orchestrator_agent/agent.py`）
- 持有 `messages` 列表 + `session_id` + `token_usage`
- Loop 算法：
  1. 把 user prompt + System Prompt + skills 目录 + 当前 messages 送 Claude
  2. Claude 返回：要么直接 final，要么 tool_use 列表
  3. 如果 tool_use：依次执行（除非工具内部要求 ACK 暂停）→ 把 tool_result 拼回 messages → 回到 1
  4. 如果 final：写入 messages → 推 SSE final 事件 → Loop 结束
  5. 若 round 数 ≥ MAX_ROUNDS=15，强制结束并报错
  6. **连续工具失败上限**：连续 K=3 次工具调用返回 status=error则强制结束 session，推 SSE error 事件 `type=consecutive_tool_failures`，session.status 置 error。防止“工具失败 → LLM 修正参数 → 又失败”迭代中 token 暴涨但永不触发 MAX_ROUNDS。计数器在任一工具返回 status=ok 后重置为 0。实现位置见 Plan #03 Task 2.2 Resilience 模块 `consecutive_failures: int` 计数器。

### 3.3 Model

- Claude Opus 4.7（经 Maestro，10x tier 默认）
- Provider 抽象层来自 Plan #01；本 Doc 直接用 `LLMProvider` 接口
- fallback：Claude → Gemini → 关键词路由（详见 § 7）

### 3.4 Tools

6 个 entry，详见 § 4。

### 3.5 Memory

JSON 文件持久化 + atexit hook + `--resume`，详见 § 9。

### 3.6 Knowledge

`skills/` 目录 + `load_skill` 工具按需加载，详见 § 5。

### 3.7 Orchestration

Parent-Child 隔离：`query_data` 工具内部调 `data_acquisition_agent`（Child Agent），messages 不累积，详见 § 6。

### 3.8 Resilience

4 道防线：tenacity retry / Provider fallback / MAX_ROUNDS=15 / 关键词路由兜底，详见 § 7。

### 3.9 Security

UID 校验 + SQL 脱敏复用 + ACK 流程（硬编码不暴露 LLM）+ Token 硬阻断，详见 § 12。

### 3.10 Observability

SSE 事件协议 + 每次工具调用打 logger.info，详见 § 11。

### 3.11 Eval

Golden Cases + 4 维 Rubric + LLM Judge（独立模型实例），详见 § 8。

## 4. 工具集（5 个职责分组 / 6 个 entry）

### 4.1 `parse_uid_file(file_path: str) → list[str]`

**职责**：解析本地 UID 文本/CSV 文件，去重去空白，返回 UID 列表。

**Pydantic input/output schema**：

```python
class ParseUidFileInput(BaseModel):
    file_path: str = Field(..., description="UID 文件本地路径，必须在 data/id_files/ 下")

class ParseUidFileOutput(BaseModel):
    uids: list[str]
    source_path: str
    duplicates_removed: int
```

**实现要点**：限定 `file_path` 必须在 `data/id_files/` 目录下（防路径穿越）。

### 4.2 `run_profile(uids: list[str], app_time: str, modules: list[str] | None = None)`

**职责**：对一批 UID 跑画像分析。

**Pydantic input/output schema**：

```python
class RunProfileInput(BaseModel):
    uids: list[str]
    app_time: str               # ISO8601 格式
    modules: list[str] | None = None  # None = 跑 6 个 Skill 全集

class RunProfileOutput(BaseModel):
    results: list[dict]         # 每个 UID 一条 UserAnalysisResult
    cache_hits: int
    cache_misses: int
```

**实现要点**：
- 单/批合并；`uids=[uid]` 等同于跑单个
- `modules=None` 跑 6 Skill 全集；`modules=["app","behavior"]` 限定子集
- **内部缓存**（确定性代码判断 N 天内是否已有结果，**对 LLM 不可见**）
  - LLM 看不到 `cache_*` 字段的命中率，避免它对缓存做奇怪的推理
  - 缓存命中由代码判断，N 天阈值在 `config.yaml: orchestrator.profile_cache_days` 配
- 内部直接调 `app/services/orchestrator.py::AnalysisOrchestrator.analyze()`

### 4.3 `run_trace(uid: str)`

**职责**：返回单 UID 行为轨迹分析。

**Pydantic input/output schema**：

```python
class RunTraceInput(BaseModel):
    uid: str

class RunTraceOutput(BaseModel):
    timeline: list[dict]
    churn_root_cause: str | None
    summary_markdown: str
```

**实现要点**：内部直接调 `app/runtime_skills/trace_analyzer/analyzer.py::TraceAnalyzer.analyze()`。

### 4.4 `query_data(request: str, country: Literal[...])`

**职责**：自然语言取数请求 → 内部调 data_acquisition_agent（Child）→ 生成 SQL → 暂停等用户 ACK → execute → 返回 UID 列表。

**Pydantic input/output schema**：

```python
class QueryDataInput(BaseModel):
    request: str
    country: Literal["th", "mx", "co", "pe", "cl", "br"]
    # 注意：签名不含 require_confirmation 参数

class QueryDataOutput(BaseModel):
    uids: list[str]
    sql_text: str               # 已脱敏
    rows_estimated: int
    rows_actual: int
    ack_at: str                 # 用户 ACK 时间戳
```

**A-1 ACK 安全规约**：
- ACK 流程在工具**内部硬编码**，**LLM 不可见、不可关闭**
- 工具签名**不含** `require_confirmation` 参数
- Anti-pattern 注释（必须写在工具源码顶部）：

```python
# ANTI-PATTERN: Do not expose require_confirmation as a tool argument.
# If the LLM can pass require_confirmation=False, prompt injection can
# bypass the security ACK gate. ACK is hardcoded inside this tool.
```

**内部流程**：
1. 实例化 `DataAcquisitionAgent` 子实例（Child Agent）
2. Child 跑自己的 Loop：生成 SQL → 脱敏
2.5. **预估影响行数**（P1-4）：Child 在 SQL 脱敏后调用 EXPLAIN / `SELECT COUNT(*)` 估算影响行数并填入 `rows_estimated`。如果数据源不支持 EXPLAIN（如某些数据仓库），`rows_estimated` 返回 `-1` 表示未知；Data Acquisition Agent 不需为此中止。前端弹窗看到 `-1` 时显示“未知（数据源不支持估算）” + 黄色警告 icon。
3. 返回到 Parent 之前，向 Parent SSE 队列推一个 `awaiting_user_ack` 事件
4. 等用户 ACK（POST `/api/orchestrator/sessions/{id}/ack`）
5. ACK 通过 → Child 继续：execute → 收集 UID 列表
6. ACK 拒绝 → 抛 `UserCancelledACK` → Parent 看到一个 abort tool_result，**并且 session.query_cancelled 置 True**（见下方 P1-2）

**P1-2 防止 LLM “换参数重试”死循环**：
ACK 拒绝后 LLM 完全可能“换个 country / 换个描述再试一次”进入死循环。因此强制一个 session 级 flag：

- session 状态机报一个 `query_cancelled: bool` 字段，初值 False。
- 任何一次 `query_data` 的 ACK 被拒绝则置 True。
- 同一 session 内后续调用 `query_data` 直接返回 tool_result `error: 'user cancelled in this session, please start new chat for new query'`，不走 Child Loop。
- 直到用户开新 session（新 session_id）才重置。

实现位置见 Plan #03 Task 1.4 query_data 实装 + Task 2.1 session schema 中 `query_cancelled` 字段。

### 4.5 `memory_write(key: str, value: str) → bool`（独立 entry）

**V1 实装定义（修正 P0-2）**：V1 是 *minimal implementation*，不是空 stub。
- `memory_write` **真实写入** `outputs/orchestrator_memory/{session_id}.json` 并返回 `success=true`。
- `memory_read` **真实读盘**，未命中返回 `found=false`。
- LLM 在 System Prompt 中被明确告知：memory 仅用于本 session 内跨 round 复用，不跨 session 持久；V2 才升级到持久化记忆服务。
- 实施人员不得把这两个工具写成 `raise NotImplementedError`。

**职责**：跨轮次记忆写入。V1 minimal。

**Pydantic schema**：

```python
class MemoryWriteInput(BaseModel):
    key: str = Field(..., max_length=64)
    value: str = Field(..., max_length=2048)

class MemoryWriteOutput(BaseModel):
    success: bool
```

**V1 实现**：写本地 JSON 文件 `outputs/orchestrator_memory/{session_id}.json`（真实写盘，不是空 stub）。V2 接持久化记忆服务。

### 4.6 `memory_read(key: str) → str | None`（独立 entry）

**职责**：跨轮次记忆读取。V1 minimal实现（本地 JSON 读盘，未命中返回 `found=false`）。

**Pydantic schema**：

```python
class MemoryReadInput(BaseModel):
    key: str = Field(..., max_length=64)

class MemoryReadOutput(BaseModel):
    value: str | None
    found: bool
```

### 4.7 注册表（`TOOL_HANDLERS` 6 项）

```python
TOOL_HANDLERS = {
    "parse_uid_file": ParseUidFileHandler(),
    "run_profile": RunProfileHandler(),
    "run_trace": RunTraceHandler(),
    "query_data": QueryDataHandler(),
    "memory_write": MemoryWriteHandler(),
    "memory_read": MemoryReadHandler(),
}
```

每个 Handler 暴露统一接口：`describe()` 返回 LLM 可读 JSON Schema；`run(input)` 执行。

## 5. Knowledge 层（两层注入）

### 5.1 `skills/` 目录（V1 baseline 6 国）

```
skills/
├── thai-churn-analysis.md          # 泰国流失/复贷下单分析框架
├── mexico-cohort-analysis.md       # 墨西哥 S1-S6 客群分析框架
├── colombia-credit-risk.md         # 哥伦比亚征信解读规则
├── peru-app-mix-analysis.md        # 秘鲁 APP 安装画像规则
├── chile-payment-behavior.md       # 智利支付时间线模式
└── brazil-overdue-recovery.md      # 巴西逾期回收分析手册
```

每个文件写一份完整的国家分析 playbook（不少于 500 字）：
- 业务背景（市场特征、产品形态）
- 关键指标定义（流失定义、风险阈值等）
- 分析步骤建议
- 常见陷阱

### 5.2 System Prompt 只放"目录"

System Prompt 里每个 skill 一行 ~100 tokens 描述（skill 名 + 一句话作用），不放全文。详见附录 A。

### 5.3 `load_skill(skill_name: str) → str`

工具入口，读 `skills/{skill_name}.md` 全文返回。

```python
class LoadSkillInput(BaseModel):
    skill_name: Literal[
        "thai-churn-analysis",
        "mexico-cohort-analysis",
        "colombia-credit-risk",
        "peru-app-mix-analysis",
        "chile-payment-behavior",
        "brazil-overdue-recovery",
    ]
```

注意：`load_skill` 是辅助工具，不计入 § 4 的 6 个核心 entry（可以理解为第 7 个 entry，但属于 Knowledge 层而非业务工具）。

### 5.4 加载策略

- 同一 session 内同 skill 不重复加载（`session.loaded_skills` Set）
- 命中后注入下一轮 system context（追加到 messages 的 system 部分）
- 一个 session 最多加载 3 个 skill（防止 token 爆掉）

## 6. Orchestration 层 — Parent-Child 隔离

### 6.1 Parent

`OrchestratorAgent`（Parent）持有 `self.messages` 列表，包含本会话所有 user/assistant/tool 消息。

### 6.2 Child Agent 实例化

调 `query_data` 工具时，工具内部 `child = DataAcquisitionAgent(country=country)` per-call 创建。

### 6.3 Child 独立 Loop

Child 用 `child.messages`（独立列表），自己跑生成 SQL → ACK → execute 这套 Loop。Child 内部可能也调 LLM（Gemini，data_acquisition Provider 路由），那是 Child 的事。

### 6.4 Child 返回 Pydantic 结构化结论

Child 跑完 Loop 后，把结论包成 `QueryDataOutput`（SQL 文本 / UID 列表 / 行数 / ACK 时间戳）返回给工具。工具把这个 Pydantic 对象的 `.model_dump()` 作为 `tool_result` 拼回 Parent 的 messages。

### 6.5 Child messages 不累积到 Parent

**A-3 关键约束**：Child 的 messages 不进入 Parent 的 messages，也不进入 Parent 的 session JSON。Parent 只看到 Child 的最终结论（SQL 文本、UID 列表、行数），看不到 Child 的内部推理过程。

理由：
- Child 的中间推理（试错的 SQL、被 reject 的 DDL 尝试）对 Parent 没用，反而让 Parent 的 token 浪费
- 隔离让 Child 可以独立换 Provider / 换实现而不影响 Parent
- 测试时可以 mock Parent 调用而不需要 mock 整个 Child 内部

### 6.6 实现要点

```python
# tools/query_data.py
def run(input: QueryDataInput) -> QueryDataOutput:
    child = DataAcquisitionAgent(country=input.country)
    try:
        result = child.run_query(input.request)  # Child Loop 在此
    finally:
        del child  # per-call 即丢
    return QueryDataOutput(**result)
```

## 7. Resilience（4 道防线）

### 7.1 Layer 1 — tenacity retry

单次 LLM 调用瞬时失败（网络抖动 / 5xx / json parse 失败）重试 3 次。Provider 内部已实现，本层复用。

### 7.2 Layer 2 — Provider fallback

`ClaudeMaestroProvider` 抛 `ProviderUnavailable` → 自动切到 `GeminiProvider`。SSE 推 `provider_fallback` 事件，前端展示降级标记。

### 7.3 Layer 3 — `MAX_ROUNDS=15`

Agent Loop 单 session 最多 15 轮。超出强制结束并推 `error` 事件，避免 LLM 死循环工具调用。

### 7.4 Layer 4 — 关键词路由兜底

Claude + Gemini 都挂时，进入退化模式：

| 输入特征 | 路由动作 | confidence |
|---|---|---|
| 输入含 UID 格式（regex 匹配） | 直接调 `run_profile` | 0.1 |
| 输入含 "trace" / "轨迹" / "行为" | 直接调 `run_trace` | 0.1 |
| 其他 | 返回明确错误"AI 服务不可用，请稍后重试" | N/A |

关键词模式响应字段 `confidence=0.1`，前端展示"AI 服务降级中"。

**兜底是降级不是欺骗**：confidence 必须显式标低，前端必须显示降级 banner。

## 8. Eval 层

### 8.1 Golden Cases（10-20 条）

存储位置：`tests/golden/orchestrator_cases.json`

字段：

```json
{
  "input": "string",
  "expected_tools": ["tool_name", ...],
  "expected_country": "th|mx|co|pe|cl|br|null",
  "expected_uid": "string|null",
  "notes": "string"
}
```

V1 baseline 例子：

```json
[
  {
    "input": "分析泰国上周流失下单用户",
    "expected_tools": ["query_data", "run_profile"],
    "expected_country": "th",
    "expected_uid": null,
    "notes": "典型 cohort 取数 + 画像"
  },
  {
    "input": "看下 UID U001 的行为轨迹",
    "expected_tools": ["run_trace"],
    "expected_country": null,
    "expected_uid": "U001",
    "notes": "单 UID trace"
  }
]
```

### 8.2 Rubric 4 维度（每维 1-5 分）

1. **工具选择准确性**：选对工具 = 5；选错主工具 = 1
2. **工具顺序合理性**：query_data 先于 run_profile = 5；颠倒 = 1
3. **参数提取准确性**：country / app_time / uid 提取正确 = 5；缺失 = 2
4. **无幻觉**：不调不存在的工具 / 不编造 UID = 5；调不存在工具 = 1

每条 case 总分 4-20 分。Golden Test 通过线：单条 ≥ 16 分（每维 ≥ 4 分）。

### 8.3 触发时机

每次改 Orchestrator System Prompt（包括微调措辞）必须跑一遍 Golden Test，分数不退化才能 commit。

### 8.4 V1 Cases 来源

- 手写 10-20 条覆盖 6 国 × 不同分析意图
- 灵感来源：data_acquisition_agent 已有 163 个测试 case 中典型查询
- V2：上线后真实 case 持续追加

### 8.5 Judge 选型（A-2）

- **Judge 模型**：Claude Opus 4.7（10x tier）
- **不复用被评估实例**：Judge 必须是独立的 Provider 实例（避免同一调用既当裁判又当被告）
- **Judge prompt 模板**：固化在 `tests/golden/judge_prompt.md`，模板内容包括：
  - 4 维 Rubric 详细评分标准
  - 输入：被测 Agent 的 input + Agent 实际工具调用序列 + Agent 实际参数
  - 输出：JSON `{"tool_selection": int, "tool_order": int, "param_extract": int, "no_hallucination": int, "comment": str}`
- **初期人工对齐**：
  - 5-10 条人工打分 vs LLM Judge 打分对比
  - 偏差 > 1 分 → 调 Rubric 措辞，重跑
  - 迭代到偏差 < 1 分才信任 LLM Judge 自动跑

**补充说明（P2-3）——Judge 离线运行**：
- LLM Judge 跑在 CI / 线下 Eval 环境，**独立于运行时 fallback 链**。Claude 全挂不影响 Eval 跑分。
- Judge 模型选型在 `tests/golden/judge_provider.yaml` 独立配置（与运行时 `config.yaml: llm.routes` 解耦），默认 `claude_maestro: 10x`，可在 Claude 全挂时手动切为 `gemini` 并重新跑一轮人工对齐。
- 运行时出现 Provider fallback 的样本仍可被 Judge 后期起跑评分（只要会话 JSON 完整落盘）。

## 9. 会话持久化

### 9.1 存储

`outputs/orchestrator_sessions/{session_id}.json`

### 9.2 字段

```json
{
  "session_id": "uuid4",
  "created_at": "ISO8601",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "tool", "tool_name": "...", "input": {...}, "output": {...}}
  ],
  "tool_calls": [
    {"tool_name": "run_profile", "started_at": "...", "completed_at": "...", "status": "ok"}
  ],
  "token_usage": {
    "total": 12345,
    "by_round": [1234, 5678, ...]
  }
}
```

### 9.3 atexit hook

进程退出时把所有 in-memory session 刷盘。优雅关闭和异常退出都覆盖（注册 `atexit.register(flush_all_sessions)`）。

### 9.4 `--resume {session_id}`

CLI 参数（脚本入口 `python -m app.runtime_skills.orchestrator_agent.cli --resume xxx`）恢复历史会话，继续 Loop。

API 入口同样支持：`POST /api/orchestrator/chat` body 中带 `session_id` 即恢复。

### 9.5 Child Agent messages 不持久化（A-3）

**关键约束**：Child Agent（如 data_acquisition_agent）的 messages **不**持久化到 Parent session JSON。Parent session 只记录 Child 返回的结构化结论（SQL 文本、UID 列表、行数），不记录 Child 的中间推理过程。

理由：
- Child 内部推理对 resume 没用（恢复时直接看结论即可）
- 减少 session JSON 体积
- 隔离 Provider 切换：Child 换 Gemini → Claude 时不影响 Parent session 历史可读性

**实现约束（修正 P0-3）**：
- Child Agent 实例 **per-call 创建**：`tools/query_data.py` 内 `child = DataAcquisitionAgent(country=...)`，工具函数返回前 `del child` 丢弃引用让 GC 回收。
- **不得修改 `child.messages` 内部状态**（违反“工具不应修改其依赖对象内部状态”原则；也会让 Child 实例失去自己 resume 的能力）。
- **不得保留 child 引用**。Child 如有自己的 atexit 写盘机制（落到 `outputs/data_acquisition_runs/{run_id}/conversation.json`），与 Parent session 隔离不冲突。
- 参考实现见 § 6.6。

## 10. Token 预算

### 10.1 per-session 上限

`500K tokens`，写入 PLANNING.md 已知约束。

### 10.2 软提醒（80%）

session 累计 token > 400K 时，下一次 LLM 调用前先推 SSE `budget_warning` 事件（前端显示 banner），不阻塞调用。

### 10.3 硬阻断（100%）

session 累计 token ≥ 500K 时，拒绝新 LLM 调用，推 SSE `error` 事件并强制结束 session。下次 chat 必须开新 session。

### 10.4 计数实现

每次 `LLMProvider.generate_*` 调用结束后，`provider.last_token_usage` 累加到 `session.token_usage.total`。

## 11. SSE 事件协议

7 种事件类型：

| 事件 | 触发时机 | payload |
|---|---|---|
| `tool_started` | 工具调用前 | `{tool_name, input, started_at}` |
| `tool_completed` | 工具调用完成 | `{tool_name, output, completed_at, status}` |
| `assistant_thinking` | LLM 流式输出 partial content | `{content_delta}` |
| `budget_warning` | 80% token 阈值 | `{used, limit, percentage}` |
| `provider_fallback` | Claude → Gemini 降级 | `{from, to, reason}` |
| `error` | 任何不可恢复错误 | `{error_type, message}` |
| `final` | Loop 结束 | `{final_message, total_rounds, total_tokens, confidence}` |

不每条 LLM token 都推（前端处理不过来）；`assistant_thinking` 按 50-100 字符为单位 batch flush。

## 12. Security

### 12.1 UID 格式校验（双层 P1-3）

分为两层，职责不同：

**Layer A — 通用入口安全校验**（本 § 12.1，安全层）：
- 正则 `^[A-Za-z0-9_-]{1,64}$`
- 防注入 / 防成本、防路径穿越、防 prompt injection。
- 所有从 LLM / 起 user input 拿到的 UID 必须先过此校验，失败抛 `InvalidUIDFormat`。
- 适用全局，不区分国别。

**Layer B — 国别业务校验**（Plan #03 Task 2.3 `uid_whitelist.py`，业务层）：
- 6 国各自更严格的业务 pattern（例如 `th` 长度 8-32、`mx` 不允许大小写混淆等，按业务方决定）。
- 需要在 `query_data` / `parse_uid_file` 等工具返回 UID 后调用验证，验证不过记录为 `invalid_uids` 丢弃，不报错（允许部分出错但不阻断全量分析）。
- 不是安全层，是业务正确性层。

两层互不替代。Layer A 过不了 → 报错；Layer A 过了但 Layer B 过不了 → 丢弃单个 UID 但不中断会话。

### 12.2 SQL 凭据脱敏

`query_data` 工具内部复用 `data_acquisition_agent/redactor.py` 的 11 family 脱敏。SQL 文本进入 Parent messages / SSE 事件 / session JSON 之前必须脱敏。

### 12.3 ACK 流程

固定 UI 弹窗（前端 Doc 落地）：
- 显示 SQL 全文（已脱敏）
- 显示预估影响行数
- 确认 / 取消两个按钮
- **不让 LLM 生成确认提示文案**（避免 prompt injection 让确认看起来像废话用户随便点）

工具签名 `query_data` 不含 `require_confirmation` 参数（详见 § 4.4 A-1）。

### 12.4 Token 预算硬阻断

详见 § 10。

## 13. System Prompt 设计

### 13.1 V1 草拟

附录 A 是 V1 完整文本。

### 13.2 跑分迭代

Plan #03 Phase 1 Task 1.7 把附录 A 写入 `app/prompts/orchestrator_system_prompt_v1.md`，跑 Golden Test 看 4 维 Rubric 分数。

### 13.3 固化

如果 V1 跑分不达标（任意维度均分 < 4），迭代措辞。最终版本固化在附录 A 并同步到 `app/prompts/orchestrator_system_prompt_v1.md`。

### 13.4 修改 Prompt 必跑 Golden Test

每次改 System Prompt（哪怕一个字），必须重跑 Golden Test。分数不退化才允许 commit。

## 14. API 入口

### 14.1 `POST /api/orchestrator/chat`

SSE 流式响应。Request body：

```json
{
  "prompt": "string",
  "session_id": "string|null"
}
```

Response：SSE stream，事件协议见 § 11。

### 14.2 `GET /api/orchestrator/sessions/{session_id}`

返回 session JSON 全文（用于前端 resume）。

### 14.3 `POST /api/orchestrator/sessions/{session_id}/ack`

Request body：

```json
{
  "confirm": true|false
}
```

通知后端用户对 SQL ACK 弹窗的选择。后端 unblock Child Agent 的 ACK 等待。

## 15. 不在本期范围（Out of Scope）

- 不改前端任何文件（独立 Doc + 独立 Plan）
- 不改 ModelClient 抽象层（独立 Doc + 独立 Plan，本 Doc 假设其已落地）
- 不改 7 个 Skill 的 explainer（独立 Doc + 独立 Plan）
- 不改 data_acquisition_agent 内部逻辑（Surgical 锁死，163 测试基线不动）
- 不实现多人协作 / 实时 push
- 不接持久化记忆服务（V2 才接，本期 memory_write/read 是本地 JSON stub）

---

## 附录 A — System Prompt v1 完整文本

下面是 System Prompt v1 完整文本，将固化到 `app/prompts/orchestrator_system_prompt_v1.md`（Plan #03 Phase 1 Task 1.7）。

````text
You are the Orchestrator Agent for the Mexico/SEA user-profile analytics platform.
Your job is to help analysts run multi-step user-profile investigations using
natural language requests. You orchestrate a fixed set of tools; you do NOT
write code, do NOT invent SQL, and do NOT execute anything outside the
provided tools.

# Your Tools (6 entries, 5 responsibility groups)

1. parse_uid_file(file_path: str) -> list[str]
   Parse a local UID text/CSV file. Returns deduplicated UID list.

2. run_profile(uids: list[str], app_time: str, modules: list[str] | None = None)
   Run profile analysis for one or many UIDs. Default modules=["app"]; pass
   modules=["app","behavior","credit","comprehensive","product","ops"] to
   include the full skill set. Caching is handled internally.

3. run_trace(uid: str, days: int = 7)
   Return single-UID behavior trace analysis (timeline + churn root cause).

4. query_data(request: str, country: "mx")  # ⚠️ V1: ONLY "mx" works.
   "th" returns ManifestNotImplemented; "co/pe/cl/br" raise ValueError at
   the tool entrypoint. Do NOT call query_data for any country other than
   "mx" — the call will fail and waste a round.
   Submit a natural-language data extraction request. Internally generates
   SQL, asks the user to ACK the SQL, then executes and returns a UID list.
   ACK is enforced by the security layer; you cannot disable it.

5. memory_write(key: str, value: str) -> bool
   Persist a key-value pair across rounds (V1 local-JSON; not cross-session).

6. memory_read(key_pattern: str) -> list[{key, value}]
   Read previously persisted values matching the given key pattern.

# Knowledge Skills (load on demand)

You have access to 6 country-specific analysis playbooks under
docs/skills/orchestrator/{country}.md. The Agent runtime injects the
relevant skill content into the system prompt automatically when a country
code is detected in the user request — you do NOT call any load_skill tool.

A single session may load at most 3 country skills (the runtime enforces this).

# Decision Rules

- If user provides UIDs directly (or a UID file path), call parse_uid_file
  (if file) then run_profile.
- If user describes a cohort in natural language ("流失下单用户" / "高风险逾期"),
  call query_data first to materialize the UID list, then run_profile.
- For single-UID deep behavioral investigation, call run_trace instead of
  run_profile (or in addition to it).
- Always extract the country code explicitly. If ambiguous, ask the user.
- Always extract app_time explicitly (default to "today" only if user clearly
  means "now").

# Output Style

- Keep your reasoning concise; do not narrate every internal thought.
- After all tools complete, write a 5-section Markdown summary:
  1. 用户请求理解 (1-2 lines)
  2. 取数与画像执行情况 (which tools ran, key counts)
  3. 关键发现 (3-5 bullets, evidence-backed)
  4. 风险与不确定性 (data gaps, model fallbacks)
  5. 推荐下一步 (concrete analyst actions)
- Use plain Chinese; do not use emoji.

# Hard Boundaries

- Never invent UIDs that did not come from a tool call.
- Never generate SQL outside query_data. Never execute SQL directly.
- If the user asks for something outside the tool set (e.g. "send me an email"),
  refuse politely and suggest a tool-supported alternative.
- If a tool returns an error, surface it and ask the user how to proceed
  rather than retrying blindly more than 3 times.
- If the per-session token budget warning fires (80%), warn the user and
  suggest summarizing or ending the session.
- If the per-session token budget hard limit fires (100%), the system will
  end the session automatically; tell the user clearly.

# Output Protocol (the runtime parses this — follow exactly)

Respond with a single JSON object on each round:

```json
{
  "tool_call": {"name": "<tool_name>", "arguments": {<schema-conforming kwargs>}}
}
```

OR (when you have all needed information):

```json
{
  "final_message": "<5-section markdown>",
  "confidence": <float 0.0-1.0>
}
```

Never produce both keys in the same response.
````
