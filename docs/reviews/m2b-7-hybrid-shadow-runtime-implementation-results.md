# M2B-7 Hybrid Shadow Runtime Implementation Results

## Outcome

- `M2B-7` 已落地为 shadow-only runtime skeleton。
- deterministic retrieval 仍是唯一生效输入。
- hybrid 只生成 bounded internal trace，并写入 `retrieval_snapshot_json.hybrid_trace`。
- 默认配置保持关闭，不影响现有 prompt、SQL 生成、approve/execute 或 public API。

## What Changed

- `app/core/config.py`
  - 新增 hybrid shadow raw env-backed settings。
- `app/data_agent/hybrid_runtime.py`
  - 新增 config parsing、mode evaluation、shadow-only vector reader、bounded trace builder、post-generation fallback helper。
- `app/data_agent/service.py`
  - `create_run()` / `revise_run()` 接入 shadow trace wiring。
  - 不改变 deterministic retrieval、prompt assembly、structured SQL plan、validation 主路径。
- tests
  - 新增 `tests/data_agent/test_hybrid_shadow_config.py`
  - 新增 `tests/data_agent/test_hybrid_shadow_runtime.py`

## Runtime Guarantees

- `enabled=false` 时不写 `hybrid_trace`。
- `hybrid_candidate` / `hybrid_enabled` 在 M2B-7 中不会生效，只会 fallback。
- `bucket_writeback` 直接 `unsupported_run_type`。
- `sql_kind != query_only` 在 post-generation 强制 fallback `unsupported_sql_kind`。
- vector index 缺失或损坏不会导致请求失败。
- `prompt_context.rendered_text` 与 deterministic-only 保持一致。
- public API response 仍不暴露 `retrieval_snapshot_json`。

## Experimental Dependency Boundary

- runtime 读取 `data_knowledge_eval/m2b/vector_index.<namespace>.json` 仅作为 shadow-only experimental dependency。
- 这不表示 `data_knowledge_eval/` 成为正式 runtime artifact directory。
- 生产级 vector artifact packaging 仍需后续阶段单独设计。

## Verification Snapshot

- targeted shadow tests:
  - `tests/data_agent/test_hybrid_shadow_config.py`
  - `tests/data_agent/test_hybrid_shadow_runtime.py`
- broader regression set:
  - `tests/data_agent/test_api.py`
  - `tests/data_agent/test_plan_review.py`
  - `tests/data_knowledge/test_data_knowledge_service.py`
  - `tests/data_knowledge/test_data_knowledge_retriever.py`

## Current Limits

- shadow trace 只做内部审计，不证明 runtime hybrid 已具备收益。
- supplements 不进入 prompt，不进入 SQL plan，不影响审核路径。
- TH / writeback 仍全部 fallback。
- `Hybrid retrieval` 在本阶段依然只是审计型 grounding augmentation，不是 execution authority。
