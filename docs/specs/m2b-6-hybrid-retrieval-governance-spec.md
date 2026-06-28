# M2B-6 Hybrid Retrieval Governance Spec

## Goal

在不修改 runtime retriever、不接入 Data Agent runtime 的前提下，为未来 hybrid retrieval 接入 runtime 前定义治理合同。

本阶段只定义治理，不定义实现。

## Phase Boundary

M2B-6 固定为：

- retrieval governance design
- runtime-facing contract design
- audit / gate / rollout / safety design

M2B-6 明确不做：

- runtime implementation
- `app/data_knowledge/retriever.py` 改造
- `app/data_knowledge/service.py` 改造
- `app/data_agent/service.py` 改造
- `app/data_agent/sql_plan.py` 改造
- `data_acquisition_agent/orchestrator.py` 改造
- LLM 调用
- SQL 生成或执行
- embedding API / vector infra 接入

## Retrieval Modes

### `deterministic_only`

- 只运行 deterministic retrieval。
- 不触发 vector retrieval。
- 不生成 hybrid supplement。
- prompt / retrieval context 完全等同现有 deterministic 路径。

### `hybrid_shadow`

- 运行 deterministic retrieval、vector retrieval 和 fusion。
- hybrid 结果只写入 audit trace / retrieval snapshot。
- hybrid 结果不进入 prompt。
- hybrid 结果不影响 SQL 生成。

### `hybrid_candidate`

- 运行 deterministic retrieval、vector retrieval 和 fusion。
- accepted supplements 可进入内部 retrieval snapshot / prompt context 的 experimental 区段。
- 不改变 public `GenerateRequest` shape。
- 不改变公开 API response schema。
- 不向前端暴露 vector/hybrid 内部候选。
- 必须显式标记为 experimental runtime mode。

### `hybrid_enabled`

- 运行 deterministic retrieval、vector retrieval 和 fusion。
- accepted supplements 可进入正式 retrieval context。
- 仍必须保留 deterministic primary、fallback、SQL HITL 全边界。
- hybrid retrieval 只是 grounding 增强，不是执行授权来源。

## Configured Mode vs Effective Mode

`configured_mode` 表示配置意图。`effective_mode` 表示本次请求实际生效的模式。

原则：

- `effective_mode` 只能等于或低于 `configured_mode`
- 任何异常、越界、allowlist 不满足、审计失败、vector/hybrid 不可用，都只能降级
- 绝不允许自动升级

降级矩阵：

| configured_mode | allowed effective_mode |
|---|---|
| `deterministic_only` | `deterministic_only` |
| `hybrid_shadow` | `hybrid_shadow` / `deterministic_only` |
| `hybrid_candidate` | `hybrid_candidate` / `hybrid_shadow` / `deterministic_only` |
| `hybrid_enabled` | `hybrid_enabled` / `hybrid_candidate` / `hybrid_shadow` / `deterministic_only` |

## Rollout Scope Matrix

| Scope | Current Status | Notes |
|---|---|---|
| `MX + query_only + cohort_query` | `shadow-only` | 首个实际 runtime rollout boundary，只允许从 `deterministic_only` 或 `hybrid_shadow` 起步 |
| `MX + query_only + bucket_writeback` | `design-only` | 需要更严格 writeback gate，M2B-6 不启用 |
| `TH + query_only + cohort_query` | `design-only` | 需要 TH 专属 eval gate、schema alias review、country allowlist |
| `TH + query_only + bucket_writeback` | `out-of-scope` | 不属于 M2B-6 |

## First Runtime Rollout Boundary

首个实际 rollout boundary 固定收口在：

- `country=mx`
- `sql_kind=query_only`
- `run_type=cohort_query`

默认要求：

- 初始 mode 为 `deterministic_only` 或 `hybrid_shadow`
- 不允许 `bucket_writeback`
- 不允许 `th`
- 不影响 approve / execute / SQL HITL / writeback

## Future Gated Scope

### MX bucket_writeback

`MX bucket_writeback` 在 M2B-6 只保留 future gated design。

未来启用前至少要满足：

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

### TH cohort_query

`TH cohort_query` 在 M2B-6 只保留 future gated design。

未来启用前至少要满足：

- TH golden set
- TH schema alias review
- TH glossary review
- TH table/field allowlist
- TH country-specific baseline
- TH shadow run no-regression
- country-specific fallback report

## Prompt Injection Boundary

- `deterministic_only`：无 hybrid prompt 注入
- `hybrid_shadow`：无 hybrid prompt 注入
- `hybrid_candidate`：只允许 experimental supplemental candidates 区段进入内部 prompt context
- `hybrid_enabled`：accepted supplements 可进入正式 retrieval context

无论哪个 mode，都必须满足：

- deterministic 仍是 primary grounding source
- vector/hybrid 不得绕过 SQL HITL
- vector/hybrid 不得直接触发 SQL 执行

## SQL Safety Boundary

核心原则：

> Hybrid retrieval is a grounding enhancement, not an execution authority.

中文约束：

> Hybrid retrieval 只是 grounding 增强，不是 SQL 执行授权来源。

因此：

- hybrid retrieval 不能绕过 SQL HITL
- hybrid retrieval 不能直接生成或执行 SQL
- hybrid retrieval 不能降低现有 deterministic review
- hybrid retrieval 不能放宽 schema validation / dangerous SQL scan / approval / execute 边界

## M2B-7 Boundary

M2B-6 结束后，任何以下工作都必须进入 `M2B-7` 或新阶段单独 PR：

- runtime hybrid integration
- mode/config wiring
- retrieval snapshot runtime writes
- audit trace runtime persistence
- prompt context runtime changes
- rollout / shadow / candidate runtime execution
