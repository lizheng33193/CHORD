# M2B-2.1 Seed / Alias / Deterministic Grounding Patch

## Summary

- `M2B-2.1` 固定为 deterministic grounding patch，而不是 embedding / vector / hybrid retrieval 阶段。
- 本阶段只做：
  - 基于 `m2b_legacy_v1` 生成完整替代 patch `m2b_legacy_v2`
  - 用 glossary synonyms、field business meaning、table/field normalization 修补 deterministic grounding
  - 对 `mx/ph/common + m2b_legacy_v1` 和 `mx/ph/common + m2b_legacy_v2` 跑同一套 golden set，输出 A/B baseline 对比
- 本阶段不做：
  - `app/data_knowledge/retriever.py` scoring/top-k/filtering 调整
  - Data Agent runtime、SQL generation、SQL HITL、approve/execute、orchestrator bridge 改造
  - embedding / vector index / hybrid retrieval

## Implementation

- 在 `scripts/promote_m2b_extracted_assets.py` 中支持生成 `source_namespace=m2b_legacy_v2` 的完整 seed patch：
  - 保留 `m2b_legacy_v1` 不变
  - `m2b_legacy_v2.yaml` 独立可导入，不依赖 `v1`
  - `seed_promotion_manifest.v2.yaml` 独立输出
- v2 patch 只改 seed 文本与映射质量，不改 runtime schema：
  - glossary：增强 `high_risk`、`recent_7d`、`first_loan`、`never_overdue`、`credit_profile`、`no_apply`、`recent_30d`
  - field：增强 `withdraw_uuid`、`apply_create_at`、`asset_grant_at`、`asset_finish_at`、`user_uuid`、credit 相关字段的 `description / business_meaning / aliases`
  - 继续保持 pattern example 为 non-executable
- 在 `scripts/run_m2b_retrieval_baseline.py` 中：
  - 增加 `--seed-patch`
  - 增加 `--coverage-yaml`
  - deterministic mode 继续只跑隔离临时 DB
  - 对 retrieved lists 做去重
  - 用 seed patch glossary alias 做 baseline matcher 规范化
  - 当检测到 v2 baseline 时，自动生成 v1/v2 comparison review

## Acceptance

- `docs/knowledge-base` 仍只追踪 `README.md`
- `m2b_legacy_v2.yaml` 干净且可被隔离 temp DB 导入
- `baseline_results.m2b_legacy_v1.deterministic.json` 与 `baseline_results.m2b_legacy_v2.deterministic.json` 都能真实跑出
- 唯一 `fail` case 至少降为 `partial`
- `high_risk / recent_7d` glossary grounding 改善
- `withdraw_uuid / apply_create_at / asset_*` 相关字段召回改善或缺口更明确
- 输出 `M2B-2.1` 结果文档与 `v1/v2` comparison report，并明确下一步是 `M2B-3` 还是 `M2B-2.2`

## Assumptions

- `m2b_legacy_v2` 仍是 isolated evaluation namespace，不加入公开 `mx/ph/common` bundle。
- `business_rule / cohort_definition / canonical_field_policy` 继续不进入 runtime seed family。
- 如果 v2 仍只有局部改善，则下一步进入 `M2B-2.2`，而不是直接进入 `M2B-3`。
