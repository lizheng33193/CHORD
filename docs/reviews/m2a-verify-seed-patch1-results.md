# M2A-Verify Seed Patch 1 Results

## Scope

本轮只做 `Seed Patch 1`，严格限定在知识层：

- catalog / field seed 补齐
- glossary seed 补齐
- SQL example seed 补齐
- error case seed 补齐
- seed importer 支持 `ph/error_cases.yaml`

本轮明确没有做：

- Safety Gate unresolved placeholder 检测
- Data Acquisition JSON schema validation fallback
- retriever scoring 算法改造
- 向量检索 / rerank

## Seed Patch 1.1 Follow-up

在 `Seed Patch 1` 结果复盘后，我们识别出一个非阻塞但重要的知识资产风险：

- `example:behavior-writeback` 虽然补上了 behavior source table 与行为字段，但 active SQL pattern 仍是“直接扫 behavior 表 + LIMIT 100”
- 这会向模型传递一个过宽的 few-shot 模式：把 `LIMIT` 当作控制边界，而不是先限定 target cohort / uid 集合

`Seed Patch 1.1` 已对该风险做最小收口，且仍然只改 seed 与验证文档：

- 保持 `example:behavior-writeback` 为 `active`
- 把 SQL example 收紧为 `target_users -> JOIN behavior table by uid -> output behavior fields` 的 cohort-constrained pattern
- 把 `pattern_summary` 收紧为显式安全约束，明确禁止无 cohort/uid 限制扫描 behavior 表，禁止把 `LIMIT` 当作主要安全边界

## Patch Contents

本轮实际补齐了这些知识资产：

1. `ph_apply_orders.loan_count`
2. `dwd_w_apply.loan_count`
3. `dwd_w_apply.risk_level`
4. `dwd_w_apply.apply_time`
5. `dwb_b1_data_burying_point` behavior source table
6. behavior writeback 相关字段：`uid / timestamp_ / eventname`
7. `高风险用户` glossary
8. `最近7天` glossary
9. `behavior writeback` active example
10. `ph` 国家差异 error case seed：`case:ph-withdraw-uuid`
11. `behavior writeback` active example 已在 `Seed Patch 1.1` 中从 broad scan pattern 收紧为 cohort-constrained pattern

## Verification Method

与 Round 1 相同，本轮在隔离的临时 auth DB 中真实执行：

- seed import
- `DataKnowledgeRetriever`
- `PromptContextAssembler`
- `DataAcquisitionOrchestrator.generate(...)`
- `run_sql_safety_gate(...)`

## Headline Result

Seed Patch 1 的总体结论是：

- 5 条样例本轮全部获得了结构化生成结果，不再出现上一轮 2/5 的 schema validation fail。
- `ph` 的 `loan_count` field gap 已关闭。
- `ph` 的 error case recall 不再依赖手工注入。
- `mx` 的高风险和 behavior writeback 场景都有明显改善。
- 仍然保留的问题，已经收敛到“后续独立工程项”，而不是继续归因给 seed 缺失。

## Case-by-Case Delta

### 1. `mx-high-risk-cohort`

Before:

- 误召回 writeback glossary
- 没有风险字段、没有时间窗口字段
- 生成阶段直接 `schema validation failed`

After:

- glossary 命中：
  - `高风险用户`
  - `最近7天`
- fields 命中：
  - `dwd_w_apply.risk_level`
  - `dwd_w_apply.apply_time`
- 生成成功，Safety Gate `passed`

Remaining gaps:

- `dwb_b1_data_burying_point` 仍被 catalog 召回，属于 table-level false positive
- 生成 SQL 使用了 `user_uuid / apply_create_at`，与 seed 中的 `uid / apply_time` 命名仍有漂移

Conclusion:

- `Seed Patch 1` 已显著改善该样例
- 剩余问题更接近 `retriever scoring` 和 `model generation drift`

### 2. `mx-behavior-writeback`

Before:

- 只有 `dwd_w_apply` + `uid`
- 没有 behavior source table
- 没有 writeback example
- 生成 SQL 带 `{uid_str}` unresolved placeholder

After:

- table 命中：
  - `dwb_b1_data_burying_point`
- fields 命中：
  - `uid`
  - `timestamp_`
  - `eventname`
- example 命中：
  - `example:behavior-writeback`
- `Seed Patch 1.1` 后该 example 的 active pattern 已收紧为：
  - 先定义 `target_users`
  - behavior 表通过 `uid` join `target_users`
  - 输出 `uid / timestamp_ / eventname`
  - 不再保留“无 cohort 约束 + LIMIT 100”的 active SQL
- 生成成功，Safety Gate `passed`

Remaining gaps:

- 生成 SQL 仍带 `{uid_list_placeholder}`
- SQL 仍明显依赖 few-shot 风格的固定日期范围

Conclusion:

- knowledge coverage 已经补上
- active example 的 broad scan 风险已作为知识资产问题收口
- 当前阻塞点不再是 seed 缺失，而是 `model generation` 与 `safety gate` 的后续工程项

### 3. `ph-first-loan-never-overdue`

Before:

- `loan_count` 只存在于 glossary/example，不在 catalog field

After:

- `ph_apply_orders.loan_count` 已进入 retrieved fields
- 生成成功，Safety Gate `passed`

Conclusion:

- `ph loan_count` field gap 已关闭

### 4. `mx-glossary-combo-writeback`

Before:

- glossary 组合命中，但缺 writeback example
- 缺 behavior source table
- 生成阶段 `schema validation failed`

After:

- 命中 behavior source table
- 命中 `loan_count / max_overdue_days / uid / eventname / timestamp_`
- 命中 writeback example
- 生成成功，Safety Gate `passed`

Remaining gaps:

- 生成 SQL 仍 heavily shaped by few-shot / historical patterns
- 使用了 `withdraw_uuid / user_uuid` 等更复杂字段体系，说明模型仍会向熟悉的 few-shot 结构回退

Conclusion:

- 该样例从“生成失败”提升到了“可生成、可审阅”
- 剩余问题属于生成质量优化，而不是 seed 覆盖问题

### 5. `ph-error-case-repair-recall`

Before:

- 依赖手工插入 `open` error case

After:

- 直接由 seed importer 导入 `case:ph-withdraw-uuid`
- retriever 正常召回 error case
- 生成成功，Safety Gate `passed`

Conclusion:

- `ph` 国家差异 error case seed 已具备最小自然基线

## Confirmed Improvements

本轮已被真实样例确认的改善：

1. `ph loan_count` field gap 已关闭
2. behavior source table / fields / example 已进入 writeback context
3. behavior writeback active example 已收紧为 cohort-constrained pattern
4. `mx` 高风险与时间窗口知识已进入 context
5. `ph` error case recall 不再依赖手工注入
6. glossary-level `writeback_behavior` 误召回已压下，不再出现在高风险样例里

## Remaining Gaps Kept Out of This Patch

这几项仍然存在，但按约定没有纳入 Seed Patch 1：

1. table-level false positive，尤其 `dwb_b1_data_burying_point` 被高风险 query 命中
2. unresolved placeholder 仍不会被 Safety Gate 拦截
3. 复杂 writeback / combo 场景仍会受 few-shot 历史结构强影响
4. Data Acquisition 的结构化输出稳定性仍需独立工程项跟进

## Recommended Next Step

完成 Seed Patch 1 后，建议下一步拆成两个独立方向，不要混在一起：

1. `M2A-Verify Round 2`
   - 基于当前 seed patch 再跑一轮真实样例
   - 确认是否还需要第二批 seed 精修

2. `M2A-Followup Runtime Quality`
   - unresolved placeholder safety check
   - structured JSON fallback / repair
   - retriever scoring 精修

当前判断：

- `Seed Patch 1` 已达成目标
- 后续剩余问题不应再继续伪装成“知识层没补全”
