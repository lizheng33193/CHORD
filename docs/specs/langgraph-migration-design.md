# LangGraph 迁移评估：当前暂不迁移

- **状态**：评估完成 — 决定不迁移
- **日期**：2026-04-30
- **关联任务**：TASK.md → P3 LangGraph 迁移
- **决策方案**：方案 A（保持现有 SkillRegistry）

---

## 1. 背景与评估目标

TASK.md 中的 P3 条目原计划将 `app/services/orchestrator.py` 的多 Skill 调度从自研 `SkillRegistry`（`app/runtime_skills/base.py`）迁移到 LangGraph 的 `StateGraph`。`base.py` 顶部注释已声明该模块"designed as the single place to swap in LangGraph later"，把 LangGraph 作为预留的接缝。

随着 stage 2 的 ProductAdvice / OpsAdvice 在现有架构下顺利落地（2026-04-30，348 tests passed），P3 的前置假设——"现有调度难以扩展"——需要被重新检验。本文档的评估目标：

- 在不写代码的前提下，判断是否应在当前阶段执行迁移
- 给出明确结论与触发条件，避免后续反复重启同一讨论
- 把"接缝"和"是否应该使用接缝"两件事分开：保留接缝是设计选择，使用接缝需要业务理由

本评估覆盖编排层（orchestrator + SkillRegistry + BaseSkill）。Skill 内部六步管线（contracts / data_access / feature_builder / decision_engine / explainer / assembler）以及 `data_acquisition_agent/` 子项目不在评估范围内。

---

## 2. 当前编排架构现状

### 2.1 调度模型

`AnalysisOrchestrator._analyze_single_user(uid)` 调用 `SkillRegistry.run_all(uid, repository, application_time)`。Registry 按 `stage` 升序逐层执行：

- **stage 0**（`max_workers=3` 并行）：AppProfileSkill / BehaviorProfileSkill / CreditProfileSkill
- **stage 1**（单 Skill 自动串行）：ComprehensiveProfileSkill，`depends_on=["app_profile","behavior_profile","credit_profile"]`
- **stage 2**（并行 2 个）：ProductAdviceSkill / OpsAdviceSkill，均 `depends_on=["comprehensive_profile"]`

依赖注入约定：上游 Skill 输出在下游 `analyze(uid, **kwargs)` 中以 `<dep_name>_result` 键注入。

### 2.2 关键代码规模

- `app/runtime_skills/base.py`：141 行（BaseSkill 抽象 + SkillRegistry 调度，含 ThreadPoolExecutor 并行）
- `app/services/orchestrator.py`：116 行（含 `_build_registry()`、`analyze()`、`_analyze_single_user()`、`_init_repository()`）
- 6 个 Skill 入口文件均为薄层（≤ 95 行），统一签名 `analyze(uid, **kwargs) -> dict[str, Any]`

### 2.3 输出契约

`UserAnalysisResult`（`app/schemas/final_response.py`）包含 4 个必选 `AgentOutput` 字段（app/behavior/credit/comprehensive_profile）+ 2 个 Optional（product_advice / ops_advice）+ standardized_labels。该形状是对外 API 兼容性目标，任何编排层重构都不得改变它。

### 2.4 验证状态

- 测试：348 passed（含端到端、Skill 单元、stage 调度）
- 真实 LLM：vertex 模式打通验证（2026-04-28，gemini-3.1-pro-preview）
- stage 2 ProductAdvice / OpsAdvice 已在 SkillRegistry 下落地（2026-04-30），证明现有架构对新增 Skill / 新增 stage 的扩展路径可行。

---

## 3. 不迁移 LangGraph 的理由

### 3.1 当前架构没有可定位的代码层面痛点

`base.py` 141 行已实现 LangGraph 在当前规模下能提供的全部能力：DAG 拓扑（按 `stage` + `depends_on`）、同 stage 并行执行、依赖输出注入。每加一个 Skill 仍是 `registry.register(NewSkill(model_client))` 一行，新 stage 自动按 `stage` 字段排序进入调度。

### 3.2 LangGraph 的差异化价值在当前业务中不存在

LangGraph 相对于自研 DAG 调度器的核心增量功能：

- **Streaming** token / event 给前端实时推送
- **Checkpointer** 支持长任务中断 / 恢复
- **Interrupt / human-in-the-loop** 支持审批流
- **Conditional edges** 支持运行时动态路由
- **Send API** 支持 map-reduce / 动态 fan-out
- **Time-travel** 调试与状态回放

当前业务输入是 UID 列表、输出是 JSON 报告，全程不需要中断、不需要回放、不需要前端流式渲染、不需要根据中间结果动态决定下游分支。上述特性在当前没有产品需求支撑。

### 3.3 迁移成本明显大于收益

- **测试影响**：348 测试中凡是直接断言 stage 调度顺序或 mock SkillRegistry 的部分都需要回归
- **依赖膨胀**：引入 `langgraph` 会传递引入 `langchain-core` 及关联包（具体大小 / 包数 Step 3 / Plan 阶段验证）
- **学习成本**：团队需掌握 `StateGraph` / `add_node` / `add_edge` / `compile()` 的心智模型，并理解其与现有 `BaseSkill.analyze(uid, **kwargs)` 的对齐方式
- **收益**：用户不可感知 — 输出形状不变、性能不变、稳定性不变

### 3.4 与项目原则一致

CLAUDE.md "编码行为"明确写入 YAGNI："Don't design for hypothetical future requirements"。在没有具体业务驱动的情况下迁移到 LangGraph，正是 YAGNI 警告的反例 — 为可能永远不会到来的未来需求支付 100% 当下成本。

### 3.5 接缝已经预留，迁移成本是有界的

`base.py` 的 SkillRegistry 已被设计为"single place to swap in LangGraph later" — 这意味着即使未来需要迁移，也只需要替换 `run_all` 内部，对外 API 与 6 个 Skill 内部不受影响。**保留接缝**是已完成的设计动作；**使用接缝**是另一个独立决策，应该由具体业务事件触发。

---

## 4. 未来触发迁移的条件

满足以下任一条件时，应重新评估是否启动 LangGraph 迁移：

1. **Streaming 需求**：产品要求前端按 Skill 完成进度实时推送（SSE / WebSocket），且自研 streaming 改造成本超过引入 LangGraph 的成本
2. **长任务 Checkpoint / Resume**：单次分析变为长流程（分钟级以上），需要中断恢复或失败重试到具体节点
3. **Human-in-the-loop**：流程中出现人工审批节点（如分析师审核中间结果后再继续下游 Skill），与 `data_acquisition_agent` 的"分析师审核 SQL"流程类似但发生在 SkillRegistry 内部
4. **条件分支调度**：根据 comprehensive_profile 输出动态决定是否触发 ProductAdvice / OpsAdvice，或动态选择不同下游 Skill 子集
5. **Skill 规模与图复杂度**：Skill 数 ≥ 12 且依赖图变成非线性多入边 DAG，`<dep>_result` kwargs 注入约定开始让调用方混乱
6. **跨 UID Map-Reduce**：需要在单个图执行中对多个 UID 做动态 fan-out（LangGraph `Send` API）
7. **调试与可观测性需求升级**：需要 time-travel debug / 状态快照 / 节点级 trace 接入到现有日志体系，自研改造成本高于引入 LangGraph
8. **多国上线（≥3 国）且 Skill 内部需要 Agent Loop**：当业务扩展到 3 个以上国家，每国 Skill 因业务复杂度需要独立的 Agent Loop（多轮 LLM 推理 + 工具调用 + 条件分支），现有 BaseSkill.analyze() 单次调用签名无法承载时，应将 Skill 升级为 Agent 并用 LangGraph StateGraph 编排

任一条件成立时，应重新走 Step 2 流程产出新的 Design Doc，而不是直接进入实现。

---

## 5. 当前 SkillRegistry 应保持的不变量

为保留未来迁移的低成本接缝，下列不变量在 SkillRegistry 演进过程中必须维持：

1. **BaseSkill.analyze 签名**：`analyze(self, uid: str, **kwargs: Any) -> dict[str, Any]`，不允许改为位置参数或绑定到具体框架的 state 对象
2. **统一返回形状**：每个 Skill 返回 `AgentOutput` 兼容的 dict（含 `summary` / `structured_result` / `charts` / `report_markdown`），不得返回框架专属对象
3. **依赖注入约定**：`depends_on` 中声明的上游 Skill 输出以 `<dep_name>_result` kwargs 形式注入；新增依赖必须先在被依赖 Skill 的 `name` 字段暴露
4. **stage 字段语义**：lower runs first；同 stage 并行；下一 stage 在当前 stage 全部完成后启动
5. **Skill 注册唯一入口**：所有 Skill 必须在 `AnalysisOrchestrator._build_registry()` 内 `registry.register(...)`；不允许其他位置创建并行的注册路径
6. **LLM 调用走 ModelClient**：Skill 不直接 import google-genai；与 LangGraph 的潜在 LLM 抽象层无关
7. **对外 API 输出形状不变**：`UserAnalysisResult` 字段集合（含 Optional 字段语义）保持稳定 — 这是无论是否迁移都必须遵守的兼容性边界
8. **测试结构稳定**：Skill 单元测试与 stage 调度测试分层清晰；调度测试不耦合 Skill 内部实现细节

破坏上述任一不变量都会显著抬高未来迁移成本，等同于把"已预留的接缝"变成"需要重新挖的坑"。

---

## 6. 后续重新评估时需要确认的问题

当第 4 节任一触发条件出现，启动新 Design Doc 时应回答：

1. **驱动迁移的具体业务事件是什么**？（不能是"看起来更先进"，必须是具体的产品需求或线上事故）
2. **LangGraph 的哪个具体功能解决该问题**？streaming / checkpoint / interrupt / conditional edges / Send / time-travel —— 写明对应 API
3. **该问题是否能用更小成本的方案解决**？（在 SkillRegistry 内部加 streaming hook、加 checkpoint adapter、加 conditional gate）
4. **迁移范围**：方案 B（adapter 模式，保留 BaseSkill 与 \_build\_registry，仅替换 run\_all 调度引擎）还是方案 C（全面替换 BaseSkill 抽象）
5. **State schema 设计**：单一 dict / TypedDict / Pydantic model；是否暴露给 Skill 内部代码
6. **错误处理策略**：节点抛异常是否中断整图、降级 fallback 在哪里实现、与现有 mock 降级机制如何对齐
7. **依赖版本**：`langgraph` 与 `langchain-core` 的具体版本范围、与现有 `google-genai` / `pydantic` 的兼容性（不要凭记忆猜测，到 Plan 阶段实际安装验证）
8. **测试迁移路径**：348 测试中哪些需要回归、新增哪些图级别测试、CI 时长影响
9. **观测性接入**：日志格式、duration 度量、model_trace 字段在新调度引擎下的暴露路径是否一致
10. **回滚预案**：迁移落地后如出现稳定性问题，能否快速回退到 SkillRegistry（取决于改动是否进入了 Skill 内部）

---

## 7. Out of Scope

下列内容明确不在本评估范围：

- Skill 内部六步管线（contracts / data_access / feature_builder / decision_engine / explainer / assembler）的任何重构
- `data_acquisition_agent/` 顶层独立子项目的任何调度变化（其有独立的 V1/V2 设计文档）
- Streaming / SSE / WebSocket 前端实时推送的实现
- 长任务 checkpoint / resume 的存储后端选型
- 跨 UID 批量编排（当前由 `AnalysisOrchestrator.analyze` 简单循环实现）
- LLM provider 抽象层与 LangChain `ChatModel` / `Runnable` 接口的对齐
- `app/ui/live_frontend.py` 前后端分离重构
- LangGraph 之外的其他 DAG 框架（Prefect / Temporal / Airflow / Ray Workflows）的对比评估 — 当未来触发条件出现时再做横向对比

---

## 8. 迁移实施计划

### 8.1 迁移顺序建议
按 stage 反序升级（依赖最多的先升级，降低适配成本）：
1. Phase 1：comprehensive（stage 1）— 依赖 app/behavior/credit 三个上游，升级后可验证 StateGraph 的 depends_on 机制
2. Phase 2：product_advice + ops_advice（stage 2）— 依赖 comprehensive，Phase 1 验证通过后再升级
3. Phase 3：app_profile / behavior_profile / credit_profile（stage 0）— 基础 Skill，影响面最大，最后升级

### 8.2 接口变化
| 现有签名 | LangGraph 签名 | 适配方式 |
|---|---|---|
| BaseSkill.analyze(uid, **kwargs) -> dict | Agent.run(state: TypedDict) -> TypedDict | Adapter wrapper 桥接 |
| SkillRegistry.run_all() 按 stage 调度 | StateGraph.compile().invoke(initial_state) | 替换 orchestrator._analyze_single_user |
| <dep>_result kwargs 注入 | StateGraph 的 state 字段自动传递 | TypedDict state 定义包含所有 profile 字段 |

### 8.3 兼容策略
用 Adapter Wrapper 让旧 Skill 和新 Agent 共存：SkillAgentAdapter(BaseSkill) 包装 LangGraph Agent，对外仍暴露 analyze(uid, **kwargs) 签名。支持 feature flag：LANGGRAPH_ENABLED_SKILLS=["comprehensive"]

### 8.4 测试策略
每升级一个 Skill → Agent：
1. 跑 Golden Test Set 对比升级前后分数
2. 旧 Skill 和新 Agent 各跑 10 个 UID，逐字段 diff structured_result
3. 分数持平或提升 → 合入；分数下降 → 回退

### 8.5 回滚方案
- Feature flag 切换：LANGGRAPH_ENABLED_SKILLS=[] → 秒回全部旧 Skill，0 代码改动
- 每个 Phase 完成后打 git tag，极端情况 revert 到 tag
