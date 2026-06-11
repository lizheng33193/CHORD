# 经营层 Skill（ProductAdvice + OpsAdvice）— 技术方案文档

> 项目：Agent User Profile（墨西哥市场多 Agent 用户画像后端）
> 模块：经营层 Skill（ProductAdviceSkill + OpsAdviceSkill）
> 模块类型：A — 代码实现模块
> 语言/框架：Python 3.x + FastAPI + Pydantic
> 核心文件数：19 个源文件 + 5 个测试文件（38 新增测试，全量 316 passed）
> 开发日期：2026-04-30
> 定位：面试技术方案沉淀

---

## 1. 需求背景

### 1.0 问题是怎么发现的

| 步骤 | 内容 |
|------|------|
| **观察到什么** | 画像系统有 4 个 Skill（App/Behavior/Credit/Comprehensive）能输出用户的 S1-S6 分层，但没有"基于分层给出具体经营策略"的能力——分层结果停留在画像层，业务团队不知道对 S2 用户该续贷还是提额、该 WhatsApp 还是 Push |
| **为什么这是个问题** | 方案文档 §八 定义了 S1-S6 每个客群的核心经营策略（续贷/提额/催收/流失预警），但这些策略只存在文档里，没有变成系统输出 |
| **做了什么验证** | 确认 ComprehensiveSkill 已输出 `metrics.segment = "S4"`（S1-S6 分层完整），经营层 Skill 只需消费这个分层结果 + 查表 |
| **为什么决定这样解决** | 新增 2 个 stage=2 Skill，消费 Comprehensive 输出，按 country_pack 的 S1-S6 策略表查表输出。规则引擎保底，LLM 增强话术 |

### 1.1 目标
- ProductAdviceSkill：基于 S1-S6 输出续贷策略/提额建议/利率方案/触达渠道
- OpsAdviceSkill：基于 S1-S6 输出催收策略/流失预警/挽回方案/触达渠道
- mock 模式 100% deterministic，LLM 只增强不改变结构化字段
- 上游缺失时降级为 data_missing，不抛异常

### 1.2 验收标准
- 316 passed, 1 skipped, 0 failed
- 6 个 segment 全覆盖，端到端验证 6/6 status=ok
- UserAnalysisResult 新增 product_advice / ops_advice 字段（Optional，向后兼容）

---

## 2. 技术架构

### 2.0 在系统全局中的位置

```
stage 0（并行）          stage 1（串行）           stage 2（并行）
App / Behavior / Credit → Comprehensive          → ProductAdvice / OpsAdvice
                           ↓ S1-S6 分层              ↓ 经营策略
                           metrics.segment           renewal / collection / churn
```

| 角色 | 是谁 | 数据格式 |
|------|------|---------|
| 上游 | ComprehensiveProfileSkill 的 AgentOutput | `structured_result.metrics.segment = "S4"` |
| 下游 | API 响应 / 前端 Dashboard | `UserAnalysisResult.product_advice / .ops_advice` |

### 2.1 六步管线（与 App/Behavior/Credit 完全对齐）

```
comprehensive_profile_result
  → data_access（提取 segment + tags）
  → feature_builder（normalize）
  → decision_engine（查 country_pack S1-S6 策略表）
  → explainer（mock 跳过 / real LLM 生成话术）
  → assembler（合并规则+LLM → AgentOutput）
```

### 2.2 核心组件

| 组件 | ProductAdvice | OpsAdvice |
|------|-------------|-----------|
| 入口 | `product_advice_agent.py` (47行) | `ops_advice_agent.py` (47行) |
| 策略表 | `country_packs/mx/product_advice_rules.py` | `country_packs/mx/ops_advice_rules.py` |
| 核心输出 | renewal_strategy / credit_line_action / rate_plan | collection_strategy / churn_warning / retention_offer |
| 特殊逻辑 | S5 不提额、渠道 override | churn_risk="高" → churn_warning 升一档 |

---

## 3. 核心技术细节

### 3.1 S1-S6 策略表查表

规则引擎不做推理——纯查表。`decision_engine.decide()` 用 `deepcopy(MX_PRODUCT_ADVICE_RULES[segment])` 拿到策略，唯一动态调整是 `contact_channel` 从上游覆盖（S5 除外，强制 SMS）。

### 3.2 churn 升级机制（OpsAdvice 独有）

```python
_LEVEL_ORDER = ["无", "轻", "中", "强"]

if churn_risk == "高":
    churn_warning.level = 升一档（无→轻→中→强，已强不变）
    不动 collection_strategy（催收强度不因画像侧流失信号改变）
```

### 3.3 segment 字段兼容

端到端验证发现 Comprehensive 输出 `metrics.segment`，但 Plan 的 Worked Example 写的是 `metrics.recommended_segment`。修复：data_access 两路兜底读取。

---

## 4. 设计决策

| 决策点 | 选了什么 | 为什么不选另一个 |
|--------|---------|----------------|
| 策略表位置 | country_packs/mx/ Python 常量 | YAML 多一个加载层，与现有 country_pack 风格不一致 |
| 对外暴露 | 扩展 UserAnalysisResult（Optional 字段） | 独立 endpoint 工作量大且隔离过度 |
| 两个 Skill 结构 | 完全同构六步管线 | 合并为一个 Skill 会让 Prompt 和输出混乱 |
| mock 模式 | explainer 第一行检查 mode=="mock" 直接返回 | 走 LLM 后 mock 返回不确定，测试不稳定 |

---

## 5. 踩坑记录

### 坑 1: segment 字段名不一致

| 维度 | 内容 |
|------|------|
| **现象** | 端到端验证 product_advice / ops_advice 输出 data_missing |
| **根因** | Comprehensive 输出 `metrics.segment`，data_access 期望 `metrics.recommended_segment` |
| **解决** | data_access 加 `metrics.get("segment")` fallback |
| **教训** | Plan 的 Worked Example 必须基于真实上游输出构造，不能假设字段名 |

### 坑 2: Plan Phase C 省略代码

| 维度 | 内容 |
|------|------|
| **现象** | Plan 写"与 B 同构省略完整代码" |
| **根因** | 想节省 Plan 篇幅 |
| **解决** | 执行时给窗口 B 补了指令"按差异表推断" |
| **教训** | Plan 不能省代码——已记入持久记忆准则 |

### 坑 3: 16 个碎 commit

| 维度 | 内容 |
|------|------|
| **现象** | Plan 设计每 Task 一个 commit，共 16 个 |
| **根因** | 照搬 V2 Plan 风格，但经营层 Skill 更简单不需要这么碎 |
| **解决** | 执行完了没改，但记入准则"每 Phase 一个 commit" |
| **教训** | commit 粒度按 Phase 而不是 Task |

---

## 6. 项目目录结构（经营层新增部分）

```
app/runtime_skills/
├── product_advice_agent.py          ← 薄入口（47 行）
├── product_advice/
│   ├── contracts.py                 ← 6 个 TypedDict + run_context builder
│   ├── data_access.py               ← 从 comprehensive 提取字段
│   ├── feature_builder.py           ← normalize segment/tags
│   ├── decision_engine.py           ← 查 S1-S6 策略表
│   ├── explainer.py                 ← mock 跳过 / real LLM 话术
│   └── assembler.py                 ← 合并 → AgentOutput
├── ops_advice_agent.py              ← 薄入口（47 行）
└── ops_advice/                      ← 同构
    ├── contracts.py / data_access.py / feature_builder.py
    ├── decision_engine.py           ← +churn 升级
    ├── explainer.py / assembler.py
app/country_packs/mx/
├── segments.py                      ← S1-S6 枚举 + 中文名
├── product_advice_rules.py          ← S1-S6 续贷/提额策略表
└── ops_advice_rules.py              ← S1-S6 催收/流失策略表
app/schemas/
├── product_advice.py                ← ProductAdviceStructuredResult
└── ops_advice.py                    ← OpsAdviceStructuredResult
tests/
├── test_product_advice_rules.py     ← 4 tests
├── test_ops_advice_rules.py         ← 4 tests
├── test_product_advice_phase1.py    ← 14 tests
├── test_ops_advice_phase1.py        ← 15 tests
└── test_orchestrator_stage2_phase1.py ← 1 test
```

---

## 7. 结果总览

### 7.1 量化效果

| 指标 | 改进前 | 改进后 |
|------|-------|-------|
| 经营策略输出 | 无（只有 S1-S6 分层标签） | 每个 UID 自动输出续贷/提额/催收/流失预警 + 触达渠道建议 |
| 新增测试 | 0 | 38（全量 316 passed） |
| 端到端验证 | 4/4 Skill ok | 6/6 Skill ok |

### 7.2 对下游的价值

| 下游 | 消费什么 | 没有经营层会怎样 |
|------|---------|----------------|
| 业务团队 | product_advice.renewal_strategy / ops_advice.churn_warning | 看到 S4 分层但不知道该做什么 |
| 前端 Dashboard | product_advice + ops_advice JSON section | 画像卡只有四维画像，没有经营建议 |

---

## 8. 面试怎么讲

### 8.1 口述（STAR，30 秒补充到 data_acquisition_agent 总述后面）

> 画像系统输出 S1-S6 分层后，我新增了两个 stage=2 经营层 Skill——ProductAdvice 和 OpsAdvice。核心设计是规则引擎查表：S1-S6 的续贷/提额/催收/流失策略预定义在 country_pack 里（墨西哥本地化），decision_engine 纯查表不做推理，LLM 只增强话术不改变结构化字段。一个设计亮点是 OpsAdvice 的 churn 升级机制——如果行为画像侧的 churn_risk 是"高"，即使 S2 的基础策略是"无流失预警"，也会升一档到"轻预警"，但不动催收强度。端到端验证 6/6 Skill 全部 ok。

### 8.2 追问 Q&A

| 面试官怎么问 | 回答方向 |
|------------|---------|
| 为什么用规则引擎不用 LLM？ | 经营策略是确定性的（S4 就是挽回续贷，不需要 LLM 判断）；LLM 只增强话术 |
| churn 升级为什么不动催收？ | 催收由 S1-S6 分层决定（全局判断），churn 是行为侧信号（局部判断），不应覆盖全局 |
| 端到端 segment 字段不一致怎么发现的？ | 跑真实 LLM 端到端验证，发现 product_advice 输出 data_missing，查 comprehensive 的 structured_result 发现字段名是 segment 不是 recommended_segment |
