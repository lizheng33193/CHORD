# Behavior / Credit Schema 补全 — 白盒审计报告

> 审计基线：`6fad5cb` → HEAD `b5f165e`
> 关联 Plan：[docs/plans/behavior-credit-schema-plan.md](../plans/behavior-credit-schema-plan.md)
> 关联 Design：[docs/specs/standardized-labels-design.md](../specs/standardized-labels-design.md)
> 审计日期：2026-04-30

---

## 1. 概述

P1 任务把 `behavior_profile` / `credit_profile` 两个画像 Skill 的 Pydantic schema 从"字段稀疏 + 关键级别藏在 `metrics: dict[str, Any]`"升级为"4 + 4 强类型子模型 + 顶层 level 镜像字段"，同时把 `app/services/label_builder.py` 的字段抽取链改造为"新路径子模型 → 顶层 level 镜像 → 旧 metrics fallback"三层优先级。`metrics` 字段保留并标注 DEPRECATED，本期不清理 — 旧调用方与既有 13 条 standardized-labels 测试不受影响。

产出：348 passed，0 failed；新增 schema 单测 7 + path-priority 测试 5；既有测试零回归；既有 17 维 standardized_labels 形状不变。

## 2. 技术路线

- **Q1=B / Q2=C / Q3=A 三决策**已落定：B 强类型子模型；C 完全保留 metrics（DEPRECATED 注释，本期不清理）；A label_builder 新路径优先 → 旧路径 fallback，不引入双源告警。
- **零侵入边界**：不动 `decision_engine.py` / `explainer.py` / `contracts.py` / 6 个 Skill agent 入口；assembler 仅做"再写一份到顶层"的镜像回填，把 `decision_result` 已有的 dict 块通过 Pydantic 构造再产出强类型副本。
- **三层路径优先级**：`_first_non_empty(子模型.level, 顶层 level 镜像, metrics.xxx_level)`，新路径未产出时仍能跑通旧路径 — 既消除 metrics 黑盒，又不破坏向后兼容。
- **`borrow_hunger` 特别处理**：保留 `metrics.borrowing_hunger_level` 作为 legacy fallback 的最末位（系统主 key 是 `urgency`）。

## 3. 变更文件清单

来源：`git diff 6fad5cb..b5f165e --stat`，502 insertions / 8 deletions / 7 files。

| 类型 | 文件 | 行数变动 | 说明 |
|---|---|---|---|
| Modify | [app/schemas/behavior_profile.py](../../app/schemas/behavior_profile.py) | +42 | 4 子模型（RepaymentWillingness / ProductSensitivity / ChurnRisk / ContactPreference）+ 3 顶层 level 镜像 |
| Modify | [app/schemas/credit_profile.py](../../app/schemas/credit_profile.py) | +50 | 4 子模型（FinancialMaturity / DebtPressure / CreditStability / BorrowingUrgency）+ 5 顶层 level 镜像（含 risk_level） |
| Modify | [app/runtime_skills/behavior_profile/assembler.py](../../app/runtime_skills/behavior_profile/assembler.py) | +18 | `build_fallback_structured` 回填顶层 level + 子模型 |
| Modify | [app/runtime_skills/credit_profile/assembler.py](../../app/runtime_skills/credit_profile/assembler.py) | +24 | 同上 |
| Modify | [app/services/label_builder.py](../../app/services/label_builder.py) | +57 / -8 | 三层路径优先 + `_first_non_empty` 包裹；`borrow_hunger` 保留 legacy fallback |
| Create | [tests/test_behavior_credit_schema.py](../../tests/test_behavior_credit_schema.py) | +194 | 默认构造 / 子模型 dict 构造 / metrics 共存 / assembler 回填 |
| Modify | [tests/test_standardized_labels.py](../../tests/test_standardized_labels.py) | +125 | G 组：新路径胜出 / 顶层镜像胜出 / legacy fallback / 三层优先级 / outreach 三源 |

## 4. 正确性判断

- **TDD 覆盖**：D1 schema 单测（7 case）+ D2 path-priority 测试（5 case），分别覆盖默认构造、dict→子模型 coercion、顶层与 metrics 共存、assembler 回填、三层路径切换。
- **向后兼容**：所有新增字段都有默认值（业务枚举 → `"unknown"` / 展示字段 → `""` / 数值 → `0` / 列表 → `[]`），`metrics` 字段未删，旧消费方读 `metrics.repayment_willingness_level` 仍工作。
- **类型安全**：子模型字段类型与 `decision_engine` 输出口径对齐（int / float / bool / str / list），Pydantic v2 dict→model coercion 在 assembler 边界上自动完成；测试用例 D1-B 显式覆盖 dict 入参路径。
- **零回归**：348 passed 包括既有 13 条 standardized-labels 测试，G 组追加后总数 18 — 与 Plan §8.2 验收公式一致。

## 5. 安全扫描

- **凭据风险**：本次改动只触及 schema / assembler / label_builder，不涉及 LLM prompt、不引入外部 I/O、不读环境变量、不打印日志，凭据传播面 = 0。
- **输入验证**：所有新字段均有 Pydantic 默认值，调用方传入异常类型会在 Pydantic 边界抛 ValidationError；不会向上抛出未受控异常进入 orchestrator 主链路。
- **注入风险**：N/A — 无字符串拼接 SQL、无 shell、无文件路径构造。
- **OWASP 合规**：本期不引入新攻击面；`metrics` 仍为 `dict[str, Any]`，不会被序列化到外部 API 时触发 schema 信息泄漏（与既有形态一致）。

## 6. 性能考量

- **运行时增量**：assembler 多调一次 Pydantic 构造（几个嵌套子模型），耗时 ~<1ms / uid，相对 LLM ~163s/uid 端到端可忽略。
- **内存增量**：每个 structured_result 多 8 个子模型 + 8 个顶层字符串，单 uid 增量 << 1KB。
- **label_builder 三层 fallback**：每个维度最多 3 次字典 lookup，O(1) 复杂度，无 I/O。

## 7. 测试覆盖

| 文件 | 用例数 | 维度 |
|---|---|---|
| `tests/test_behavior_credit_schema.py` | 7 | 默认构造（A 2）/ dict→子模型（B 2）/ metrics 共存（C 1）/ assembler 回填（D 2）|
| `tests/test_standardized_labels.py` G 组 | 5 | 新路径胜出 / 顶层镜像胜出 / legacy fallback / 三层 priority / outreach 顶层 contact_preference |
| 既有 phase18 / phase17 | 不变 | 0 回归（assembler 改动只是新增字段） |
| 全量回归 | 348 passed | 含 D1+D2 共 12 条新增 |

测试不调 real LLM、不读 `data/`、不连库 — 纯单测 + 内存 fixture。

## 8. 风险排查

| ID | 风险 | 状态 |
|---|---|---|
| RC1 | 旧消费方读 `metrics.xxx_level` | ✅ metrics 不动，零影响 |
| RC2 | Pydantic v2 dict→model 强校验异常 | ✅ assembler 入参来自 decision_engine 已规整化输出，类型对齐 |
| RC3 | `model_dump_compat` 序列化嵌套子模型 → dict | ✅ 与既有 ModelTrace 等子模型行为一致 |
| RC4 | 既有测试断言整 dict 形状 | ✅ phase18/17 测试断言旧字段，未触发新字段引入的回归 |
| RT1 | G 组 5 用例覆盖度 | ✅ 已覆盖 4 个核心场景（新路径 / 顶层 / legacy / outreach 多源） |
| RR4 | data_missing 路径未回填新字段 | ✅ 默认值 = "unknown"，符合 Design Doc 不变量 |

无遗留 P0/P1 风险。

## 9. 运行时链路

```
Skill.analyze(uid)
  → data_access → feature_builder → decision_engine
  → DecisionResult dict（metrics + 各子块 dict）
  → assembler.build_fallback_structured(decision_result)
       │
       ├── 顶层 level 镜像：从 metrics.xxx_level 复制到 structured_result 顶层
       └── 子模型构造：把 decision_result["xxx"] dict 传给 Pydantic 自动 coerce
  → BehaviorProfileStructuredResult / CreditProfileStructuredResult
  → model_dump_compat → AgentOutput.structured_result（dict）
  → orchestrator → label_builder.build_standardized_labels(...)
       └── _first_non_empty(子模型.level, 顶层 level, metrics.xxx_level)
  → standardized_labels 17 key（形状不变）
  → UserAnalysisResult / AnalyzeResponse
```

## 10. 遗留项

- **`metrics` 仍未清理**：DEPRECATED 注释已就位，但实际删除留待未来 schema cleanup（Q2=C 决策）。删除前需要扫描所有读 `metrics.xxx_level` 的下游代码（comprehensive、chart_builder、report_renderer），不在本期范围。
- **Pydantic v1 `@root_validator` 迁移**：TASK.md "开发中发现" 已记录 deprecation warning；迁移落点待 P3 LangGraph 阶段集中处理。
- **comprehensive_profile.py 同步**：comprehensive 仍读 `credit.metrics.xxx_level`，未升级到新路径 — 不在本期范围（Plan §RR3）。
- **LangGraph 迁移（P3）**：未启动；schema 强类型化为 P3 创造了更好的输入口径。
