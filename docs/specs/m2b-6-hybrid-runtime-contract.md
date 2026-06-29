# M2B-6 Hybrid Runtime Contract

## Goal

定义 `M2B` hybrid retrieval 进入 Data Agent runtime 后的正式内部 contract，统一 mode、config、fallback、prompt 注入和 final output provenance 约束。

本文件最初在 `M2B-6` 建立治理边界，并在 `M2B-8` 更新为当前已落地的 runtime contract。

## Contract Style

- 运行时配置承接 `app/core/config.py`
- 使用 env-backed settings 风格
- 不把 runtime 行为配置放进 `config.yaml`
- public API schema 不随 hybrid mode 改变

## Hybrid Retrieval Config V1

```text
HybridRetrievalConfigV1
  enabled: bool = false
  retrieval_mode: HybridRetrievalMode = deterministic_only
  source_namespace: str = m2b_legacy_v3
  allow_countries: list[str] = []
  allow_project_ids: list[str] = []
  vector_rank_limit: int = 8
  family_score_thresholds: dict[str, float]
  family_caps: dict[str, int]
  total_vector_supplement_cap: int = 3
  deterministic_pass_guard: bool = true
  shadow_sample_rate: float = 0.0
```

## Default Rules

- `enabled=false` 优先级最高，必须：
  - `effective_mode=deterministic_only`
- `allow_countries=[]` 默认拒绝所有 runtime hybrid
- `allow_project_ids=[]` 默认拒绝所有 runtime hybrid
- country allowlist 与 project allowlist 必须同时命中
- 任一不满足都必须降级 `deterministic_only`

## Retrieval Mode Semantics

### `deterministic_only`

- 只运行 deterministic retrieval
- 不运行 vector supplement 注入
- prompt / SQL generation 完全等同既有 deterministic 路径

### `hybrid_shadow`

- 运行 deterministic retrieval、vector candidate ranking 和 supplement selection
- hybrid 结果只写入 `retrieval_snapshot_json.hybrid_trace`
- prompt 不注入 hybrid section
- SQL 生成与 final output provenance 仍是 deterministic-only

### `hybrid_candidate`

- 只允许在 `MX + cohort_query` 的严格 gate 下进入
- accepted supplements 可以作为 `supplemental_candidates_v1` 独立区块追加进内部 prompt
- deterministic 仍是 primary grounding source
- `hybrid_candidate` 不依赖 `shadow_sample_rate`
- 只要 final output 未保留 candidate 结果，就必须 deterministic rerun

### `hybrid_enabled`

- 在 `M2B-8` 仍然禁止启用
- 当前 contract 固定：
  - `effective_mode=deterministic_only`
  - `fallback_reason=mode_forced_deterministic`

## Priority Order

runtime 计算 `effective_mode` 和 candidate eligibility 时遵循：

1. `enabled=false`
2. `retrieval_mode=deterministic_only`
3. allowlist 不命中
4. unsupported scope（当前只允许 `MX + cohort_query`）
5. `hybrid_shadow` 才使用 `shadow_sample_rate`
6. vector artifact / fusion / accepted supplements availability
7. prompt injection safety
8. audit trace persistence

## Shadow Sample Rate

- `shadow_sample_rate` 只在以下条件同时满足时生效：
  - `enabled=true`
  - `retrieval_mode=hybrid_shadow`
  - allowlist 命中
- `hybrid_candidate` 必须忽略 sample rate

## Pre-gate and Post-gate

### Pre-generation gate

- 用于提前排除明显不适合 `hybrid_candidate` 的请求
- 只能拒绝明显 unsupported intent，例如明显建表、物化、写回、沉淀结果表
- pre-gate 不能证明请求一定是 `query_only`

### Post-generation gate

- 最终是否保留 candidate result，必须以后置 `sql_kind` gate 为准
- 如果 candidate attempt 产出 `sql_kind != query_only`：
  - candidate attempt 必须丢弃
  - final generation pass 必须切换为 `deterministic_rerun`
  - final `effective_mode=deterministic_only`

## Final Output Provenance Invariant

```text
最终采用的 SQL / SQL plan / SQL version，
必须来自 final effective_mode 对应的 prompt。
```

也就是：

- `effective_mode=hybrid_candidate`
  - final SQL 才允许来自 hybrid candidate prompt
- `effective_mode=deterministic_only`
  - final SQL 必须来自 deterministic-only prompt

## Candidate Runtime Flow

`M2B-8` 的 candidate contract 固定为：

1. 先构造 deterministic retrieval 和 deterministic prompt
2. 只有 `hybrid_candidate` 且 gate 全通过时，才构造 `supplemental_candidates_v1`
3. candidate attempt 使用：
   - deterministic prompt
   - `+ supplemental_candidates_v1`
4. 若 candidate result `sql_kind == query_only`
   - `final_generation_pass=hybrid_candidate`
   - 允许持久化该结果
5. 若 candidate result `sql_kind != query_only` 或 candidate attempt 失败
   - candidate attempt 丢弃
   - `final_generation_pass=deterministic_rerun`
   - 用 deterministic-only prompt 重跑
   - 只持久化 rerun 结果

## Future Integration Touchpoints

当前 hybrid runtime 只允许从以下入口接入：

- `DataAgentService.create_run()`
- `DataAgentService.revise_run()`

不允许：

- 接 orchestrator 自动路由
- 改 public `GenerateRequest`
- 改 approve / execute 语义

## API Boundary

无论哪个 mode，都必须保持：

- 不改变 public `GenerateRequest` shape
- 不改变 API response schema
- 不向前端公开 vector/hybrid 内部候选结构
- 不把 internal hybrid debug fields 暴露为 public payload

## Retrieval Snapshot Compatibility

`retrieval_snapshot_json` 继续保留 deterministic snapshot 现有字段，并新增可选 `hybrid_trace`。

当前 `hybrid_trace` 至少允许包含：

```text
hybrid_trace
  schema_version
  configured_mode
  effective_mode
  source_namespace
  fallback_applied
  fallback_reason
  config_snapshot
  prompt_injection_mode
  prompt_candidate_count
  final_generation_pass
  candidate_counts
  candidate_attempt
  deterministic_candidates
  vector_candidates
  accepted_supplements
  rejected_candidates
```

### `candidate_attempt`

```text
candidate_attempt
  attempted
  attempted_mode
  prompt_injection_mode
  prompt_candidate_count
  output_sql_kind
  output_sql_hash
  discarded
  discard_reason
```

## Persistence Rule

- 只允许 final attempt 创建 public SQL version
- discarded candidate attempt：
  - 不能创建 reviewable SQL version
  - 不能进入 HITL approval flow
  - 不能暴露给前端

## Allowed SQL Shapes

当前 rollout 只允许 candidate attempt 发生在：

- `country=mx`
- `run_type=cohort_query`

但 final result 仍必须保留既有 SQL HITL 行为：

- `query_only` 继续进入正常审核路径
- `build_table_script` 仍然只能 review-only
- hybrid retrieval 不能绕过 approve / execute / SQL HITL
