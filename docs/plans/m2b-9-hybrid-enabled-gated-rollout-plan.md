# M2B-9 Hybrid Enabled Gated Rollout Plan

## Goal

`M2B-9` 的目标是在明确 gate、allowlist、kill switch 和回滚规则都就位后，允许 `hybrid_enabled` 在极小范围内成为 `effective_mode`。

`M2B-9 may allow hybrid_enabled to become an effective mode only under explicit gated rollout.`

`It must not make hybrid_enabled the global default.`

## Non-goals

- not global default
- not writeback
- not TH
- not public API change
- not SQL auto-execution
- not bypassing HITL
- not real vector DB integration

## Initial Rollout Scope

`M2B-9` 初始范围固定为：

- `country=mx`
- `run_type=cohort_query`
- `sql_kind=query_only`
- `HYBRID_RETRIEVAL_ENABLED=true`
- `HYBRID_RETRIEVAL_MODE=hybrid_enabled`
- rollout allowlist 命中
- eval gate 已满足

任何超出以上范围的请求都必须回退到 `deterministic_only`。

## Required Gates

`hybrid_enabled` 只有在以下条件同时满足时才允许进入 gated rollout：

- rollout allowlist sign-off 完成
- pre-rollout eval gate 通过
- fallback / rollback / kill switch contract 明确
- trace completeness 可验证
- public API / HITL / approve / execute no-regression 证明存在

## Runtime Fallback Behavior

`hybrid_enabled` 不是新的执行授权，只是 grounding enhancement。

以下任一条件不满足时，runtime 必须回退到 `deterministic_only`：

- rollout allowlist 未命中
- `country` / `run_type` / `sql_kind` 不支持
- vector artifact 不可读
- accepted supplements 不可用
- audit trace 不可写
- eval gate 未满足
- kill switch 被触发

## HITL / Approval Boundary

`M2B-9` 不得改变以下边界：

- SQL 仍必须进入现有 SQL HITL
- `approve` / `execute` 语义不变
- `review_only` / safety boundary 不变
- `hybrid_enabled` 不得绕过审批、执行或人工审核

## Audit Requirements

每次 `hybrid_enabled` gated rollout 都必须保留可审核轨迹，至少包括：

- configured mode
- effective mode
- prompt injection mode
- final generation pass
- fallback applied / fallback reason
- rollout gate passed
- kill switch applied

审计字段是上线前条件，不是上线后补录项。

## Rollback Strategy

`M2B-9` 必须支持立即回退到 `deterministic_only`。

首批回滚入口至少包括：

- `HYBRID_RETRIEVAL_ENABLED=false`
- `HYBRID_RETRIEVAL_MODE=deterministic_only`
- rollout allowlist 清空
- operator manual rollback

一旦触发 safety regression、trace missing、fallback rate 异常或 SQL 审核拒绝率异常上升，必须可以立即停用 `hybrid_enabled`。

## What M2B-9 May Change

`M2B-9` 允许做的变化仅限于：

- 在严格 gate 下让 `configured_mode=hybrid_enabled` 成为 `effective_mode=hybrid_enabled`
- 增加 rollout allowlist 读取与判定
- 增加 rollout / rollback 审计字段
- 增加 gated rollout 的验证与运维合同

## What M2B-9 Must Not Change

`M2B-9` 不允许做以下变化：

- 让 `hybrid_enabled` 成为全局默认
- 扩大到 `TH` 或多国家
- 打开 writeback / bucket writeback
- 修改 public API schema
- 修改 SQL HITL / approve / execute 行为
- 接入真实 vector DB 并把其视为执行授权
