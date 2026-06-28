# M2B-6 Hybrid Eval Gate

## Goal

定义 future hybrid retrieval 从离线原型进入 runtime implementation 前的门槛。

原则：

- 不满足 gate，不得进入更高 mode
- 不允许“先上线再观察”

## Gate A: Implement `hybrid_shadow`

进入 runtime shadow-only implementation 前，至少满足：

- offline hybrid `fail=0`
- hybrid 不回退任何 deterministic case
- 至少 2 个 case 有稳定改善
- accepted / rejected supplement 审计字段完整
- fallback reason contract 明确

## Gate B: Enable `hybrid_candidate`

进入 future `hybrid_candidate` 前，至少满足：

- scope 只允许 `MX + query_only + cohort_query`
- shadow run / fallback 全链路完整
- trace completeness `>=95%`
- vector/hybrid 异常导致请求失败率 `=0`
- 不增加 SQL safety blocked / repair / reject 的异常波动
- 不改变 public API schema

## Gate C: Enable `hybrid_enabled`

进入 future `hybrid_enabled` 前，至少满足：

- reviewer 结果无退化
- safety 结果无退化
- execute 前审批与执行边界无退化
- fallback rate、unexpected candidate rate、trace completeness 达到更严格阈值
- rollout allowlist sign-off 完成

## Rollout Gate by Scope

### MX `bucket_writeback`

`MX + query_only + bucket_writeback` 必须单列更严格 gate：

- writeback audit schema
- HITL approval required
- rollback policy
- idempotency key
- write result diff
- dry-run mode
- target table allowlist
- write volume cap
- operator confirmation
- post-write verification

## TH `cohort_query`

`TH + query_only + cohort_query` 必须单列国家隔离 gate：

- TH golden set
- TH schema alias review
- TH glossary review
- TH table/field allowlist
- TH country-specific baseline
- TH shadow run no-regression
- country-specific fallback report

## Hard Stop Rules

任何以下条件不满足，都只能停留在更低 mode：

- trace 不完整
- fallback contract 不清晰
- vector/hybrid 异常不可安全回退
- SQL safety boundary 未确认
- rollout scope 超过 allowlist

## Runtime Safety Principle

> Hybrid retrieval is a grounding enhancement, not an execution authority.

这意味着：

- hybrid retrieval 不能授权 SQL 执行
- hybrid retrieval 不能绕过 SQL HITL
- hybrid retrieval 不能降低 approve / execute 边界
