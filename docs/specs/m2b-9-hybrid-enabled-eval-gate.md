# M2B-9 Hybrid Enabled Eval Gate

## Default State

`hybrid_enabled` 默认仍然关闭。

只有当以下三个配置同时允许时，runtime 才可能进入 enabled rollout：

- `HYBRID_RETRIEVAL_ENABLED=true`
- `HYBRID_RETRIEVAL_MODE=hybrid_enabled`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=true`

如果没有显式 eval gate，`hybrid_enabled` 不得默认开启。

## Runtime Rollout Scope

本阶段 rollout scope 固定为：

- `country=mx`
- `run_type=cohort_query`
- request-scope `sql_kind=query_only`
- normalized `ctx.project_id` 命中 rollout allowlist

任何超出该范围的请求都必须回退到 `deterministic_only`。

## Required Runtime Controls

进入 rollout 前，至少需要以下运行控制项：

- `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH`

`HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=true` 时必须无条件回退，不允许继续观察。

## Required Regression Evidence

在允许 rollout 前，至少应具备：

- no public API regression
- no SQL HITL / approve / execute regression
- no deterministic primary regression
- no hybrid candidate regression
- trace completeness verification

## Runtime Monitoring Gates

进入 rollout 后，至少持续观测以下指标：

- fallback rate
- candidate discard rate
- SQL review rejection rate
- audit trace completeness
- any safety regression signal

这些指标不是优化项，而是保留 rollout 的门槛。

## Rollback Triggers

以下任一情况出现时，必须触发回滚或立即停用 `hybrid_enabled`：

- kill switch applied
- fallback rate too high
- candidate discard rate too high
- audit trace missing / serialization failure
- SQL review rejection rate increases
- any safety regression

回滚动作必须优先选择 `deterministic_only`。
