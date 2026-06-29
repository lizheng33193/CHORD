# M2B-9 Hybrid Enabled Eval Gate

## Pre-rollout Gates

`hybrid_enabled` 进入任何 gated rollout 前，至少满足以下门槛：

- no SQL safety regression
- no public API regression
- no approve / execute regression
- no deterministic pass -> hybrid fail regression
- manual review artifact exists

如果没有可运行的 eval report 或明确的 manual review artifact，`hybrid_enabled` 不得默认开启。

`hybrid_enabled cannot be enabled by default unless this gate is satisfied by a runnable eval report or explicit manual review artifact.`

## Runtime Monitoring Gates

进入 rollout 后，运行中至少持续观测以下指标：

- candidate discard rate
- fallback rate
- SQL review rejection rate
- audit trace completeness
- safety regression signals

这些指标不是优化项，而是继续保留 rollout 的门槛。

## Rollback Triggers

以下任一情况出现时，必须触发回滚或立即停用 `hybrid_enabled`：

- candidate discard rate too high
- fallback rate too high
- SQL review rejection rate increases
- audit trace missing rate above threshold
- any safety regression

回滚动作必须优先选择 `deterministic_only`，而不是继续观察。

## Manual Review Requirements

在允许任何 rollout 之前，必须存在人工审核结论，至少覆盖：

- rollout scope 是否仍限定为 `MX + cohort_query + query_only`
- no-regression 结论
- rollback entrypoints 是否可操作
- 审计字段是否完整
- 是否存在 operator sign-off

## Required Artifacts

允许 `hybrid_enabled` 进入 rollout 前，至少应具备：

- runnable eval report 或等效手工评审报告
- rollout allowlist 决策记录
- rollback / kill switch 操作说明
- safety / reviewer / execute no-regression 证明
- trace completeness 证明
