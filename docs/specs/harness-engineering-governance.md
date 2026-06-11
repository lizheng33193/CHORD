# Harness Engineering 项目治理指南

> 状态：项目级开发治理文档  
> 入口：`AGENTS.md`  
> 适用对象：Codex / Claude Code / 人类开发者  
> 非目标：不是运行时业务 Prompt，不注入用户画像 LLM 请求

## 1. 为什么需要这份文档

本项目不是一组孤立脚本，而是一套面向用户画像的 Agent Harness。

如果每次改功能都只看局部代码，很容易出现：
- Prompt 越改越长，但数据契约没有变清楚。
- 前端展示补丁越来越多，但后端输出形状不稳定。
- 新能力绕过现有注册表、Schema、测试和降级路径。
- 同一个问题在不同模块里重复实现，最后项目失去结构。

Harness Engineering 的目标是避免这种“补丁式开发”。每次改动都要先问：它属于 Harness 的哪一层？应该复用哪个已有机制？如何验证？失败后如何恢复？

## 2. 文档分层

项目开发指南采用三层渐进式披露，不把所有规则塞进 `AGENTS.md`。

| 层级 | 文件 | 作用 |
| --- | --- | --- |
| L1 宪法入口 | `AGENTS.md` | Codex 每次默认读取；只放高层原则、硬边界、检查门 |
| L2 架构状态 | `PLANNING.md` | 当前架构、模块状态、已知约束、Surgical Boundary |
| L3 方法细则 | `docs/specs/harness-engineering-governance.md` | 本文档；解释如何把 Harness 思想落到每次开发 |

`TASK.md` 不承载原则，只记录任务状态和开发中发现。

`CLAUDE.md` 不承载原则，只作为 Claude Code 历史兼容桥。

## 3. Harness 六层模型

本项目采用六层模型来判断改动位置：

| Harness 层 | 关注问题 | 本项目常见落点 |
| --- | --- | --- |
| 信息边界 | Agent 该知道什么、不该知道什么 | `AGENTS.md`、Prompt 输入、知识库注入、上下文裁剪 |
| 工具接口 | Agent 如何调用外部能力 | `ModelClient`、SkillRegistry、API routes、orchestrator tools |
| 执行编排 | 多步骤任务如何串起来 | `AnalysisOrchestrator`、stage / depends_on、agent_loop |
| 记忆/状态 | 中间结果、缓存、会话如何保存 | module cache、session store、memory tools、outputs |
| 评估/观测 | 如何知道做对了没有 | pytest、Golden Test、rubric、日志、model_trace |
| 约束/恢复 | 出错时如何阻断、降级、恢复 | mock fallback、UID 校验、SQL 审核、redactor、scanner、MAX_ROUNDS |

一次改动可以影响多层。影响层数越多，越不应该直接写代码。

## 4. 每次改动的 Harness Impact Card

非平凡改动开始前，Codex 应在思考或计划中回答以下问题。小修可以简化，但不能违背这些判断。

```md
### Harness Impact Card
- 改动类型：小修 / 模块内改动 / 跨层改动 / 新能力
- 影响层：信息边界 / 工具接口 / 执行编排 / 记忆状态 / 评估观测 / 约束恢复
- 复用机制：现有入口、契约、Schema、注册表、六步管线、测试或降级路径
- 需要更新的文档：无 / PLANNING.md / TASK.md / docs/specs / docs/plans
- 验证方式：pytest / Golden Test / API smoke / UI 验证 / 日志检查
- 失败策略：mock fallback / fixed error / 422/4xx / 人工审核 / 不执行 / 保留旧路径
```

这张卡不是形式主义，它的作用是防止“看见一个文件就改一个文件”的冲动。

## 5. 改动分级

### 5.1 小修

示例：
- typo 修复。
- 注释或文档小改。
- 单个函数内明显 bug。
- 不改变输入输出契约的局部重构。

要求：
- 可直接修改。
- 跑定向验证。
- 不需要新增 Design Doc。
- 若发现影响范围扩大，升级为模块内改动或跨层改动。

### 5.2 模块内改动

示例：
- 修改某个 Skill 的 `decision_engine.py`。
- 增加一个字段，但只在同一模块内部消费。
- 调整某个 assembler 的报告结构。

要求：
- 先确认六步管线位置。
- 优先改 TypedDict / Pydantic / tests，而不是只改调用方。
- 跑该模块定向测试。
- 如输出契约变化，更新相关 spec / frontend mapping / tests。

### 5.3 跨层改动

示例：
- 新 API route。
- 新 Skill。
- 修改 `AgentOutput` 形状。
- 修改 orchestrator stage / depends_on。
- 修改 Prompt 输出 JSON 契约。
- 修改 `ModelClient`、provider、fallback、token budget、UID 校验。

要求：
- 先读 `PLANNING.md` 的已知约束和 Surgical Boundary。
- 必须新增或更新 `docs/specs/`。
- 必须新增或更新 `docs/plans/`。
- 必须说明 Harness Impact Card。
- 必须设计验证路径和失败策略。

## 6. 本项目的默认复用路径

### 新画像能力

默认路径：
- `app/runtime_skills/{domain}_agent.py`
- `app/runtime_skills/{domain}/contracts.py`
- `data_access.py`
- `feature_builder.py`
- `decision_engine.py`
- `explainer.py`
- `assembler.py`
- `app/services/orchestrator.py::_build_registry()`
- `tests/test_{domain}_*.py`

不要绕过 `BaseSkill` 和 `SkillRegistry`，除非设计文档明确说明这是旁路能力。

### 新 Prompt 或 Prompt 契约变化

默认路径：
- Prompt 模板放 `app/prompts/`。
- 结构化输出必须有 fallback。
- LLM 调用必须走 `ModelClient`。
- 契约变化要同步 tests、schemas、前端消费方。
- 不要只靠自然语言约束模型输出。

### 新数据能力

默认路径：
- 数据准备和采集优先放 `data_acquisition_agent/` 或 `app/scripts/data_prep/`。
- 运行时读取优先走 repository / data_access 层。
- SQL / Python artifact 仍需人工审核和安全扫描。
- 不要让画像 Skill 直接承担取数编排。

### 新前端展示

默认路径：
- 先确认后端输出契约是否稳定。
- 前端只消费结构化字段，不在 UI 中补业务判断。
- 图表或面板字段映射要有测试或清晰 fallback。
- 不要通过前端 if/else 修复后端契约不清。

## 7. 反模式

以下做法默认视为高风险：
- 为了修一个显示问题，在前端硬编码业务规则。
- 为了修一个模型输出问题，只改 Prompt，不补 schema / fallback / test。
- 新增一个工具但不接入注册表、权限、日志、失败返回。
- 新增一个模块但不说明 stage、depends_on、输出契约。
- 修改公共基础设施但不跑相关回归。
- 绕过 `ModelClient` 直接调用模型 SDK。
- 让 LLM 输出直接驱动 SQL 执行。
- 把 Codex 开发规则、运行时业务 Prompt、项目文档混在一个文件里。

## 8. 什么时候更新哪些文件

| 变化 | 必须更新 |
| --- | --- |
| Codex 工作规则变化 | `AGENTS.md` |
| Harness 方法论变化 | 本文档 |
| 当前架构、模块状态、已知约束变化 | `PLANNING.md` |
| 任务状态、待办、开发发现变化 | `TASK.md` |
| 新能力设计或跨层契约变化 | `docs/specs/` |
| 已确认设计的实施步骤 | `docs/plans/` |
| 审计、复盘、风险评估 | `docs/reviews/` |

## 9. Codex 执行口径

Codex 不需要每次都完整读取本文档。

推荐口径：
- 默认读取 `AGENTS.md`。
- 涉及架构或跨层行为时读取 `PLANNING.md`。
- 涉及复杂改动或项目治理判断时读取本文档。
- 涉及具体功能时读取对应 spec / plan / source files。

这样既保证每次开发遵循 Harness Engineering，又避免把上下文窗口塞满。

## 10. 最终原则

每次改动都应该让系统更可追踪、更可验证、更可恢复，而不是只让眼前的问题暂时消失。

如果一个改动无法说清楚它属于哪一层、复用了什么契约、如何验证、失败如何处理，那么它还没有准备好进入实现。
