# Cohort Analysis 设计文档（E2：跨样本归因聚合）

- **状态**：Design 已确认（Q1-Q4 锁定）
- **作者**：v-yimingliu
- **日期**：2026-05-01
- **关联 Plan**：docs/plans/cohort-analysis-plan.md（Step 4 产出，本窗口不做）
- **关联前置**：docs/specs/trace-analyzer-design.md（E1 单用户 trace，E2 是它的批量聚合版）
- **关联 PR / Branch**：main

---

## 1. 问题背景与产品场景

### 1.1 E1 已就位、E2 要解决的缺口

E1 `TraceAnalyzer` 已能对**单个 UID** 输出操作路径图、摩擦热点、流失归因故事线、干预建议（详见 trace-analyzer-design.md）。但产品侧期望从"个体诊断"升级到"群体洞察"：

- **输入**：一批 UID（如 S4 潜在流失客群的全部 UID）
- **输出**：群体级聚合报告——"S4 客群中 39.7%（312 人）的流失源于额度不及预期，TOP1 摩擦点是 limitInfo:requestAmount 重试 4.2 次"
- **价值**：支撑产品经理做 feature 优先级决策（哪个环节卡住的人最多 → 优先优化）

### 1.2 与 docs/技术路线/ 的对齐

产品侧"客群聚类"场景明确提到"分析 800 个流失日志，自动总结故事线"。E2 实现该场景中的**已知归因聚合**部分（按 `churn_root_cause` 分组），不实现**隐性客群发现**（聚类）—— 后者留 E3。

### 1.3 本次目标（E2）

针对**N 个 UID** 的批量聚合：跑 E1 规则层提取每个 UID 的事实 → 按 `churn_root_cause` 分桶 → 桶级统计 + 代表 UID 选取 → 1 次合并 LLM 调用产出群体叙述。

---

## 2. 方案选型（Q1-Q4 决策记录）

### Q1：API 入口设计 → 方案 A

- **选定**：新增独立端点 `POST /api/cohort-analysis`，与 `/api/analyze-file` 完全解耦
- **请求体**：
  ```json
  {
    "uids": ["uid1", "uid2", ...],
    "group_by": "churn_root_cause" | "none",
    "cohort_label": "S4_potential_churn"
  }
  ```
- 理由：与 E1 端点解耦原则一致（E1 §7.1）；客群分析 ≠ 标准画像批量；uid 列表解析逻辑很轻不值得复用 BatchAnalysisService
- **不复用 BatchAnalysisService**：E2 不走 orchestrator 标准画像管线

### Q2：聚合分组维度 → 方案 A（churn_root_cause + none）

- **选定**：`group_by ∈ {churn_root_cause, none}`，默认 `churn_root_cause`
- **不支持 segment 维度**：调用方在 E2 外侧用 segment 筛 UID 列表（先调画像 → 拿 S4 UID → 喂给 E2）
- **6 种 churn_root_cause 候选值**与 E1 / ops_advice 完全一致：闭集，桶数稳定
- **`group_by: "none"`**：不分组，对全部 UID 出 1 份整体聚合
- **`cohort_label`**：仅作报告标题字段，不参与聚合逻辑

### Q3：输出结构 → 方案 C（完整版：分布 + TOP-K + LLM 群体叙述）

- **选定**：报告级 + 桶级双层结构 + LLM 群体叙述
- **2 个收缩**：
  1. LLM 调用合并成 **1 次**（输入桶级聚合 + 代表 UID trace 摘要，输出 cohort_story / group_stories / executive_summary 的 JSON），不是每桶 1 次
  2. mock / LLM 失败时叙述字段填模板兜底，规则产物完整输出，不阻塞报告
- **不做干预建议聚合**（方案 D）：留 E2.5

### Q4：LLM 参与度

- **4.1 prompt 输入结构 → 方案 B**：桶级聚合 + 每桶选 1 个代表 UID 的 trace 摘要（含 E1 已生成的 `churn_story`）。理由：纯桶级统计（A）会让 LLM 写出泛化模板。
- **4.2 token 预算 → 方案 B（12K 总上限）**：第 1 层（cohort 全局摘要 + 桶级统计）≤3K 永远全量；第 2 层（每桶 sample_traces）≤6K；第 3 层（schema 引导 + 反模板示例）≤3K。超限护栏：sample_traces 桶数减半 → 每桶 sample 内容压缩 → 第 1 层永不动。
- **4.3 反模板硬约束 4 条**：
  1. `cohort_story` 必须引用具体桶名 + ≥2 个具体页面/字段名 + 量化数字
  2. `group_story` 每条必须引用桶内具体页面/字段/重试次数；禁止"建议优化/突出/触发"等泛化开头
  3. `executive_summary` 每条必须以"占比/绝对数字"开头
  4. 不允许虚构：LLM 输出页面/字段必须在输入 sample_traces / top_friction_hotspots 中出现过；explainer 做白名单过滤
- **4.4 状态机 5 态 + 50% 失败阈值**：见 §9
- **4.5 与 E1 调用关系 → 方案 B + 代表 UID 单独跑完整版**：见 §6
- **关键差异声明**：分桶用 E1 规则层先验候选 TOP-1（`churn_root_cause_candidates[0]`），**不是** E1 LLM 最终判定的 `churn_root_cause`。E2 报告里的桶 key 与 E1 单 UID 视图可能不一致，前端展示需区分。

---

## 3. 输入数据契约

### 3.1 API 请求体（Pydantic model）

文件：`app/schemas/cohort_analysis.py`

```python
class CohortAnalysisRequest(BaseModel):
    uids: list[str]                  # 必填，去重后实际处理
    group_by: Literal["churn_root_cause", "none"] = "churn_root_cause"
    cohort_label: str = ""           # 可选，仅用于报告标题
```

### 3.2 单 UID 数据来源

通过调用 E1 `TraceAnalyzer` 拿每个 UID 的规则层事实（参见 §6 数据流向）。E2 不直接读 CSV，CSV 读取逻辑全部委托给 E1 `data_access.py`。

---

## 4. 输出数据契约（API Response Schema）

### 4.1 顶层 Pydantic model：`CohortAnalysisResponse`

文件：`app/schemas/cohort_analysis.py`

```python
class CohortAnalysisResponse(BaseModel):
    cohort_label: str
    status: Literal["ok", "partial", "model_unavailable", "insufficient_uids", "error"]
    group_by: Literal["churn_root_cause", "none"]
    total_uids: int                            # 去重后实际处理数量
    analyzed_uids: int                         # 成功跑通规则层的 UID 数
    failed_uids: list[FailedUid]               # [{uid, reason}]，reason ∈ E1 status 5 态
    executive_summary: list[str]               # 3-5 条 bullet
    cohort_story: str                          # LLM 整体叙述 ~300 字（mock/失败填模板）
    global_top_friction_hotspots: list[GlobalFrictionHotspot]   # 跨所有 UID 聚合 TOP-K
    groups: list[CohortGroup]                  # group_by=none 时长度 1
    model_trace: ModelTrace                    # mode/used_llm/model_name/fallback_reason
    errors: list[str]
```

### 4.2 子模型

```python
class FailedUid(BaseModel):
    uid: str
    reason: Literal["data_missing", "insufficient_events", "error"]   # E1 失败原因映射

class GlobalFrictionHotspot(BaseModel):
    step: str
    occurrence_count: int          # 总命中次数
    affected_uid_count: int        # 命中该 step 的 UID 数
    avg_severity: Literal["high", "medium", "low"]

class CohortGroup(BaseModel):
    key: str                       # churn_root_cause 值；group_by=none 时固定 "all"
    count: int
    percentage: float              # 0-100，2 位小数
    top_friction_hotspots: list[GroupFrictionHotspot]
    top_pages: list[GroupTopPage]
    dominant_active_window: str    # E1 active_window_label 桶内众数
    sample_uids: list[str]         # 3-5 个代表 UID（含本桶 LLM 代表）
    group_story: str               # LLM 桶级叙述 ~150 字（mock/失败填模板）

class GroupFrictionHotspot(BaseModel):
    step: str
    occurrence_count: int
    affected_uid_count: int
    avg_retry_count: float
    avg_stay_seconds: float
    avg_severity: Literal["high", "medium", "low"]

class GroupTopPage(BaseModel):
    page: str
    total_visits: int
    unique_uids: int

class ModelTrace(BaseModel):
    mode: str                      # mock / vertex / gemini
    used_llm: bool
    model_name: str
    fallback_reason: str            # 空串表示无降级
```

具体 TOP-K 数字（global_top_friction_hotspots 取前几、groups 内 top_friction_hotspots / top_pages 取前几、sample_uids 长度）→ Plan 阶段精化。

### 4.3 内部 TypedDict 契约

文件：`app/runtime_skills/cohort_analysis/contracts.py`

```python
class CohortRunContext(TypedDict):
    uids: list[str]
    group_by: str
    cohort_label: str

class CohortRawBundle(TypedDict):
    """第 1 遍批量调 E1 规则层结果。"""
    per_uid_features: dict[str, dict]   # uid -> E1 TraceFeatureBundle (规则层产物)
    failed_uids: list[dict]
    raw_status: str                     # ok | partial | insufficient_uids | error
    errors: list[str]

class CohortFeatureBundle(TypedDict):
    """聚合规则层产物。"""
    total_uids: int
    analyzed_uids: int
    failed_uids: list[dict]
    global_top_friction: list[dict]
    groups: list[dict]                  # 每桶 stat + sample_uid 候选
    feature_status: str
    errors: list[str]

class CohortDecisionResult(TypedDict):
    """组装 LLM payload + 模板兜底。"""
    prompt_payload: dict                # 已应用 12K 三层护栏
    representative_uids: list[str]      # 桶级代表 UID 列表（待第 2 遍跑 E1 完整版）
    fallback_executive_summary: list[str]
    fallback_cohort_story: str
    fallback_group_stories: dict[str, str]   # group_key -> story
    decision_status: str
    errors: list[str]

class CohortExplanationResult(TypedDict):
    explanation_status: str             # ok | model_unavailable | skipped
    used_llm: bool
    cohort_story: str
    group_stories: dict[str, str]
    executive_summary: list[str]
    model_trace: dict
    errors: list[str]
```

---

## 5. 模块结构（六步管线）

```
app/runtime_skills/cohort_analysis/
├── __init__.py
├── analyzer.py              # 入口（不带 _agent 后缀，避免被误读为 BaseSkill）
├── contracts.py             # TypedDict 契约
├── data_access.py           # 第 1 遍批量调 E1 TraceAnalyzer (enable_llm=False)
├── feature_builder.py       # 聚合统计 + 代表 UID 选取 + token 估算 + 护栏降级
├── decision_engine.py       # 组装 prompt_payload + 模板兜底 + 第 2 遍调 E1 完整版
├── explainer.py             # 1 次合并 LLM 调用 + JSON 解析 + 白名单过滤
└── assembler.py             # 拼装 Pydantic 响应

app/api/cohort_analysis.py   # POST /api/cohort-analysis 路由
app/schemas/cohort_analysis.py  # Pydantic 请求/响应 model
app/prompts/cohort_analysis_prompt.md   # LLM prompt 模板
app/main.py                  # 单独 Task 加 include_router

tests/test_cohort_analysis_phase1.py    # 测试入口
```

每个文件 ≤500 行（CLAUDE.md 硬约束）。

**治理边界**（与 E1 §2.Q3 一致）：
1. `cohort_analysis/` 是独立服务模块，不是 SkillRegistry Skill
2. 入口 `analyzer.py` 不用 `*_agent.py` 后缀
3. 不在 `_build_registry()` 注册
4. 路由通过 `app/api/cohort_analysis.py` 单独挂载

---

## 6. 数据流向

```
POST /api/cohort-analysis
  ↓
app/api/cohort_analysis.py
  ↓
CohortAnalyzer.analyze(request)              ← analyzer.py 入口
  ↓
[第 1 遍] CohortDataAccess.fetch_all(uids)
  循环每个 uid:
    ctx = build_context(uid, enable_llm_explanation=False)   # E1 已支持的工厂函数
    TraceAnalyzer.analyze(uid, ctx)
      → 仅跑 E1 规则层（data_access + feature_builder），不调 LLM
      → 返回 TraceFeatureBundle
  ↓ per_uid_features (dict[uid -> features]) + failed_uids
CohortFeatureBuilder.build(raw_bundle)
  ↓ 1) 按 churn_root_cause_candidates[0] 分桶（group_by=churn_root_cause）
  ↓ 2) 每桶统计 top_friction_hotspots / top_pages / dominant_active_window
  ↓ 3) 全局聚合 global_top_friction_hotspots
  ↓ 4) 每桶选代表 UID（severity=high 总数最多 → event 总数最多 tie-break）
  ↓ feature_bundle
CohortDecisionEngine.decide(features)
  ↓ 1) [第 2 遍] 仅对 representative_uids:
  ↓        ctx = build_context(uid, enable_llm_explanation=True)
  ↓        TraceAnalyzer.analyze(uid, ctx)
  ↓    拿到代表 UID 的 churn_story
  ↓ 2) 组装 prompt_payload（桶级聚合 + 代表 UID trace 摘要）
  ↓ 3) 应用 12K 三层 token 护栏
  ↓ 4) 准备模板兜底叙述
  ↓ decision_result
CohortExplainer.explain(decision)
  ↓ 1 次 ModelClient.generate_structured() 合并调用
  ↓ JSON 解析 + 白名单过滤（页面/字段/churn_root_cause 值域）
  ↓ explanation_result
CohortAssembler.assemble(features, decision, explanation)
  ↓
CohortAnalysisResponse (Pydantic)
  ↓
JSON → 前端
```

**关键说明**：
- **两遍循环不可避免**：分桶必须先发生才能知道代表 UID 是谁；E1 LLM 调用只在代表 UID 上跑（最多 6 次，对应 6 个桶；`group_by=none` 时仅 1 次）
- **第 1 遍并发**：N 个 UID 跑 E1 规则层是 IO + CPU 任务，可以并发（线程池）。Plan 阶段定并发度，Design 不约束实现细节
- **失败 UID 处理**：第 1 遍中任何 UID 出 `data_missing / insufficient_events / error` 都进 `failed_uids`，不参与聚合

---

## 7. 与现有系统的集成

### 7.1 与 E1 trace_analyzer 的关系

- **E2 调用 E1，但不修改 E1 任何文件**
- E2 通过 E1 的 `build_context(uid, enable_llm_explanation=...)` 工厂函数构造 `TraceRunContext`，再调 `TraceAnalyzer.analyze(uid, context=ctx)`（E1 现有公开签名，参见 [analyzer.py:46](app/runtime_skills/trace_analyzer/analyzer.py#L46)）
  - 第 1 遍：`enable_llm_explanation=False`，只拿规则层产物
  - 第 2 遍：`enable_llm_explanation=True`，仅代表 UID 跑完整 E1
- E2 读取 E1 输出字段：
  - `path_graph` / `friction_hotspots` / `time_pattern` / `key_events_tail`
  - `churn_root_cause_candidates`（规则层先验）→ 用于 E2 分桶
  - `churn_story`（仅代表 UID）→ 喂给 E2 LLM prompt
  - `event_window` / `errors`

### 7.2 与 ops_advice / behavior_profile 的关系

- **零修改**：E2 不读 ops_advice / behavior_profile 任何输出，不修改其任何文件
- E2 是端到端独立闭环，输入 = UID 列表，输出 = 群体报告
- 调用方在 E2 外侧根据 segment 筛 UID（如 PM 用现有 `/api/analyze-file` 拿到 S4 的 UID 列表，再喂 E2）

### 7.3 与 BatchAnalysisService 的关系

- **不复用**：BatchAnalysisService 当前只对接 orchestrator 跑标准画像六步管线
- E2 不走 orchestrator，独立路由 + 独立 service，避免污染标准画像批量入口

### 7.4 churn_root_cause 一致性差异声明

- **E1 单 UID 视图**的 `churn_root_cause` = LLM 最终判定（基于规则先验 + LLM 推理）
- **E2 桶 key** = E1 规则层先验 `churn_root_cause_candidates[0]`（不是 LLM 最终判定）
- **差异原因**：E2 第 1 遍不跑 LLM 以控制成本；规则先验在闭集（6 种候选）内已具备分桶价值
- **前端展示约束**：E2 报告页面需明确标注"分桶基于规则先验"；E1 单 UID 详情仍用 LLM 判定值
- **未来演进**：若发现规则先验与 LLM 判定差异显著影响产品决策，再考虑第 1 遍也跑 LLM 或用更精准的规则先验（独立任务）

---

## 8. LLM 调用与 prompt 策略

### 8.1 prompt 模板（`app/prompts/cohort_analysis_prompt.md`）

风格参考 `app/prompts/trace_analyzer_prompt.md`，4 条反模板硬约束（详见 Q4.3）：

1. `cohort_story` 必须引用具体桶名（churn_root_cause 值）+ ≥2 个具体页面/字段名 + 量化数字
2. `group_story` 每条必须引用桶内具体页面/字段/重试次数；禁止泛化模板开头
3. `executive_summary` 每条必须以"占比/绝对数字"开头
4. 不虚构：所有页面/字段必须出现在输入数据中

`churn_root_cause` 候选值固化在 prompt 中（与 E1 一致），LLM 不允许产出新值。

### 8.2 ModelClient 调用

- 1 次合并调用：`ModelClient.generate_structured(prompt, response_schema)`
- 输出 JSON schema 字段：`cohort_story / group_stories: dict[group_key -> str] / executive_summary: list[str]`
- mock 模式跳过，使用模板兜底（见 §9）
- 失败重试依赖 ModelClient 内置（不在 E2 自己实现）

### 8.3 token 护栏实现（12K 上限）

- `feature_builder.py` 内 `_apply_token_budget(prompt_payload, budget=12000)`：
  - **token 估算函数 E2 内部最小重写一份**（CJK 加权：`len(ascii)*0.25 + len(cjk)*1.0`，与 E1 [feature_builder.py:299](app/runtime_skills/trace_analyzer/feature_builder.py#L299) `_estimate_tokens` 算法一致但物理上独立）
  - **不**抽 E1 私有方法到共享 utils（避免修改 E1 文件，违反 §10 隔离约束）
  - 重写代价极小（约 5-10 行），换取 E1 零修改 + E2 自治
  - **未来若有第 3 个模块也需要 token 估算**（不在本 Plan 范围），届时再评估抽 utils
- 三层独立预算：第 1 层 ≤3K，第 2 层 ≤6K，第 3 层 ≤3K
- 超限护栏顺序：第 2 层桶数减半 → 第 2 层每桶 sample 内容压缩 → 第 1 层永不动
- truncation 记录到 `model_trace.fallback_reason`

### 8.4 explainer 白名单过滤

- LLM 输出的页面 / 字段名必须在输入 prompt 的 `sample_traces` 或 `top_friction_hotspots` 中出现过
- 不在白名单的内容直接丢弃，对应字段降级为模板兜底文案
- LLM 输出的 `churn_root_cause` 引用必须在 6 种候选值内（与 E1 一致）

---

## 9. 状态机与降级路径

| 触发条件 | status | HTTP | 行为 |
|---|---|---|---|
| `uids` 空列表 / 全部 UID 失败 / 失败比例 ≥ 50% | `insufficient_uids` | 200 | 报告级返回 0 桶或仅失败 UID 列表，LLM 不调 |
| 失败比例 < 50% | `partial` | 200 | 失败 UID 列入 `failed_uids`，成功部分正常聚合 + LLM 调用；status=`partial` 即使 LLM 成功也不升级为 ok |
| LLM 失败 / mock 模式 | `model_unavailable` | 200 | 规则聚合产物完整，cohort_story / group_stories / executive_summary 全填模板 |
| 全链路成功（无失败 UID 且 LLM ok） | `ok` | 200 | 完整产物 |
| 异常（聚合层崩溃 / 不可恢复错误） | `error` | 200 | errors 字段记录原因，尽力返回已计算部分 |

**HTTP 状态码原则**：除请求体校验失败由 FastAPI 自动返回 422 外，所有业务状态全部 200 + status 字段（与 E1 §9 一致；`data_missing` 在 E2 不存在，因为 E2 是 UID 列表级，不是单 UID 文件级）。

**失败比例分母定义**：
- `failure_rate = len(failed_uids) / total_uids`
- `total_uids` = 请求体 `uids` 字段去重（保序去重，按首次出现顺序）后的长度
- 空字符串 / 纯空白 uid 视为非法 → 在 `total_uids` 之前直接拒绝（计入 422，而非 `failed_uids`）
- 阈值判断 `failure_rate >= 0.5` 触发 `insufficient_uids`

**状态优先级（复合场景仲裁）**：

当多个状态触发条件同时成立时，按下列优先级**从高到低**取最终 status（高优先级覆盖低优先级）：

1. `error`（聚合层崩溃 / 不可恢复异常）
2. `insufficient_uids`（uids 空 / failure_rate ≥ 50% / 全部失败）
3. `partial`（0 < failure_rate < 50%，无论 LLM 成功与否）
4. `model_unavailable`（无失败 UID，但 LLM 失败 / mock 模式）
5. `ok`（无失败 UID 且 LLM 成功）

**复合场景示例**：
- mock 模式 + 无失败 UID → `model_unavailable`
- mock 模式 + failure_rate=20% → `partial`（partial 高于 model_unavailable；LLM 是否调用与 status 无关，叙述字段填模板兜底）
- mock 模式 + failure_rate=60% → `insufficient_uids`
- LLM 成功 + failure_rate=20% → `partial`（partial 不会因 LLM 成功降级为 ok）
- LLM 失败 + 无失败 UID → `model_unavailable`
- 聚合层崩溃 + 任何其他条件 → `error`

**模板兜底文案**：
- `cohort_story` 模板示例："本批 {N} 名用户中，{top_group_key} 占 {pct}%（{count} 人），TOP 摩擦点为 {step}（平均重试 {avg_retry} 次）。"
- `group_story` 模板示例："该群组共 {count} 人，主导摩擦点 {step}（平均重试 {avg_retry} 次，平均停留 {avg_stay} 秒）。"
- `executive_summary` 模板：从 `global_top_friction_hotspots` / 桶分布机械生成 3 条，例："{pct}%（{count} 人）流失归因于 {key}"

---

## 10. Scope / Out-of-Scope

### Scope（E2 实现范围）

- `POST /api/cohort-analysis` 单端点
- 请求体：`uids` / `group_by ∈ {churn_root_cause, none}` / `cohort_label`
- 第 1 遍批量调 E1 规则层（关 LLM）
- 第 2 遍仅代表 UID 跑 E1 完整版（开 LLM）
- 桶级聚合：top_friction_hotspots / top_pages / dominant_active_window / sample_uids
- 全局聚合：global_top_friction_hotspots
- 1 次合并 LLM 调用产出：cohort_story / group_stories / executive_summary
- 12K token 三层预算 + 超限护栏
- mock 降级路径（model_unavailable 状态 + 模板兜底）
- explainer 白名单过滤（页面 / 字段 / churn_root_cause 值域）
- 状态机 5 态 + 50% 失败阈值
- 单元测试覆盖：第 1 遍批量、分桶、代表 UID 选取、token 护栏、状态机 5 态、白名单过滤、模板兜底

### Out-of-Scope

- **不修改 E1 任何文件**（仅作为调用方；token 估算函数 E2 内部独立重写，不抽 E1 私有方法到共享 utils — 见 §8.3）
- **不修改 ops_advice / behavior_profile**
- **不复用 BatchAnalysisService**（独立路由 + 独立 service）
- **不做干预建议聚合**（D 方案，留 E2.5）
- **不做 segment 维度分组**（调用方外侧筛 UID）
- **不做隐性客群聚类**（"深夜焦虑型用户"留 E3）
- **不做跨时间窗口对比**（"上周 vs 本周流失归因变化"留 E3）
- **不做实时流式**（仍是批量 UID 列表）
- **不做数据导出**（CSV / Excel 下载留前端）
- **不回灌结果**到 ops_advice / behavior_profile / E1
- **E2 桶 key 与 E1 LLM 判定差异**不在 E2 内部消解，由前端展示层标注

---

## 11. 待 Plan 阶段确认的具体数字

- 第 1 遍批量调 E1 的并发度（线程池大小）
- `global_top_friction_hotspots` TOP-K 的 K
- `groups[].top_friction_hotspots` 桶内 TOP-K 的 K
- `groups[].top_pages` 桶内 TOP-K 的 K
- `groups[].sample_uids` 长度（3 / 5）
- 12K 总 token 上限的精确值（11500? 12000? 12500?）
- 三层各自精确预算（3K / 6K / 3K 数量级）
- `executive_summary` 条数（3 / 5）
- `cohort_story` / `group_story` 期望字数（300 / 150 是数量级）

---

## 12. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 第 1 遍 N 个 UID 顺序跑过慢 | 线程池并发（具体并发度 Plan 阶段定）；前端 loading 状态 |
| 大批量 UID（如 5000+）耗时超前端超时 | 当前 E2 不做 SSE 进度（与 D2 SSE 解耦）；超大批量返回前响应时间过长 → 调用方在 E2 外侧分批 |
| LLM 输出虚构页面/字段 | explainer 白名单过滤 + prompt 反模板硬约束 |
| LLM 输出 churn_root_cause 不在 6 候选 | explainer 白名单过滤，丢弃后回退模板 |
| 12K token 仍超限（极端：6 桶 sample 都很长） | 三层护栏自动降级，model_trace.fallback_reason 记录 |
| E2 桶 key（规则先验）与 E1 LLM 判定不一致引发用户困惑 | 前端展示标注"基于规则先验分桶"；Design Doc §7.4 明确声明 |
| 第 1 遍并发触发 ModelClient 限流（即使 enable_llm=False，data_access 内部不调 LLM 应该不触发，但保险） | E1 在 enable_llm=False 时严格不调 LLM（E1 §2.Q4 已约束）；Plan 阶段验证 |
| 与 D2 / E1 同改 app/main.py 冲突 | Plan 中 include_router Task 单独执行前 `git pull --rebase` |
| `failed_uids` 信息泄露（uid 是否敏感） | uid 本身在系统内已是主键，与 E1 path 参数同等敏感度，不额外脱敏 |

---

## 13. 验收标准

1. mock 模式 + **无失败 UID** 时返回 status=`model_unavailable`，规则聚合产物完整，cohort_story / group_stories / executive_summary 全填模板
2. vertex/gemini 模式下成功调 LLM，返回 status=`ok`，所有 LLM 输出页面/字段在输入数据中可追溯
3. `uids` 空列表返回 status=`insufficient_uids`，LLM 不调
4. 失败比例 ≥ 50% 返回 status=`insufficient_uids`（分母为去重后 total_uids，见 §9）
5. 失败比例 < 50%（且 > 0）返回 status=`partial`，failed_uids 列出具体原因
6. **复合场景**：mock 模式 + 0 < failure_rate < 50% → status=`partial`（按 §9 优先级，partial 高于 model_unavailable），叙述字段仍填模板
7. **复合场景**：聚合层异常 + 任何其他条件 → status=`error`
8. `group_by=none` 时 groups 长度 1，key=`"all"`
9. `group_by=churn_root_cause` 时桶 key 为 6 候选值之一（含 `no_clear_signal`）
10. token 护栏单测：构造大量 sample_traces 触发降级，`model_trace.fallback_reason` 记录 truncation
11. 白名单单测：mock LLM 返回不在白名单的页面 → 该字段被替换为模板兜底
12. 全量测试 `pytest tests/ -v` 通过（≥ 现有 206 passed）
13. 不修改 E1 trace_analyzer 任何 .py（git diff 验证；token 估算函数复用方案见 §8.3 / §10）
14. 不修改 ops_advice / behavior_profile 任何文件（git diff 验证）
15. 不修改 BatchAnalysisService（git diff 验证）
