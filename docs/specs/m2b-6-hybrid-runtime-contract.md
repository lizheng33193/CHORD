# M2B-6 Hybrid Runtime Contract

## Goal

定义未来 hybrid retrieval 进入 runtime 前的内部 contract，统一 mode、config、fallback 和 snapshot 扩展方式。

本文件是 future runtime-facing design，不代表当前仓库已实现这些字段。

## Contract Style

- 运行时配置风格承接 `app/core/config.py`
- 使用 env-backed settings 风格
- 不把 runtime 行为配置放进 `config.yaml`

## Hybrid Retrieval Config V1

建议 future runtime contract 使用如下配置对象：

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

- `enabled=false` 优先级最高
- 只要 `enabled=false`，无论 mode 或 sample rate 如何，都必须：
  - `effective_mode=deterministic_only`
- `allow_countries=[]` 默认表示不允许任何 runtime hybrid
- `allow_project_ids=[]` 默认表示不允许任何 runtime hybrid
- country allowlist 与 project allowlist 必须同时满足
- 任一不满足则必须降级 `deterministic_only`

## Priority Order

future runtime 计算 `effective_mode` 时遵循以下优先级：

1. `enabled=false`
2. `retrieval_mode=deterministic_only`
3. allowlist 不命中
4. `unsupported_sql_kind` / `unsupported_run_type`
5. `shadow_sample_rate`
6. vector / fusion availability
7. audit trace persistence

## Shadow Sample Rate

- `shadow_sample_rate` 只在以下条件同时满足时生效：
  - `enabled=true`
  - `retrieval_mode=hybrid_shadow`
  - allowlist 命中
- 否则 sample rate 必须被忽略

## Future Integration Touchpoints

M2B-7 若实现 runtime hybrid，只允许从以下入口接入：

- `DataAgentService.create_run()`
- `DataAgentService.revise_run()`

不允许：

- 接 orchestrator 自动路由
- 改 public `GenerateRequest`
- 改 approve / execute 语义

## API Boundary

future runtime 即便进入 `hybrid_candidate` 或 `hybrid_enabled`，也必须保持：

- 不改变 public `GenerateRequest` shape
- 不改变 API response schema
- 不向前端公开 vector/hybrid 内部候选结构
- 不把 internal hybrid debug fields 暴露为 public payload

## Retrieval Snapshot Compatibility

future runtime 若扩展 `retrieval_snapshot_json`，必须遵循：

- 保留现有 deterministic snapshot 字段
- 新增可选 `hybrid_trace` 子对象
- 不删除现有字段
- 不重命名现有字段

建议 future snapshot shape：

```text
retrieval_snapshot_json
  context_hash
  table_ids
  field_ids
  glossary_ids
  example_ids
  error_case_ids
  section_counts
  trimmed
  country
  project_id
  hybrid_trace?   # new optional object
```

## Allowed SQL Shapes

M2B-6 的首个 runtime rollout 只为 future 设计以下组合：

- `country=mx`
- `sql_kind=query_only`
- `run_type=cohort_query`

因此 future runtime contract 需要支持显式拒绝：

- unsupported country
- unsupported `sql_kind`
- unsupported `run_type`

并强制回退 deterministic-only。
