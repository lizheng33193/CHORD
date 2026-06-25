# M2B-3 Embedding Text Builder

## Summary

- `M2B-3` 固定为把 `data_knowledge_seed/m2b/m2b_legacy_v3.yaml` 中已稳定的 runtime seed 资产转换成统一、可校验、可审查的 embedding text records。
- 本阶段只做：
  - `seed patch -> embedding JSONL`
  - `manifest / preview / validation`
  - 为 `M2B-4 Vector Index Prototype` 准备输入
- 本阶段明确不做：
  - embedding API / vector index / hybrid retrieval
  - `app/data_knowledge/retriever.py` 或 Data Agent runtime 改动
  - raw docs / extracted assets 再次读取
  - `m2b_legacy_v3` seed 内容修补

## Implementation Changes

- 新增 `scripts/build_m2b_embedding_text.py`：
  - 输入只接受单个 `--seed-patch`
  - 输出 JSONL records、manifest、preview
  - `--strict` 默认开启
  - `--generated-at` 可控，支持固定时间生成可复现产物
- 只支持 runtime-importable families：
  - `catalog_tables`
  - `catalog_fields`
  - `glossary_terms`
  - `sql_examples`
  - `sql_error_cases`
- embedding record 固定字段：
  - `record_id`
  - `source_namespace`
  - `source_key`
  - `asset_family`
  - `country`
  - `title`
  - `embedding_text`
  - `search_hints`
  - `metadata`
- `record_id` 使用稳定资产身份：
  - `sha256(source_namespace + source_key + asset_family)`
- `embedding_text` 使用结构化模板，不使用自由散文：
  - `catalog_table`：table/domain/description/purpose/grain/join keys/time/partition/physical names/notes
  - `catalog_field`：table/field/type/description/business meaning/join hint/aliases/usage
  - `glossary_term`：term/definition/synonyms/mapped tables/mapped fields/suggested filters
  - `sql_example`：request/pattern summary/tables/fields/run type/output bucket + 明确 non-executable
  - `sql_error_case`：error type/safe summary/risk/expected fix/bad pattern category
- `search_hints` 只保留短词，去重、去空、长度受限，不包含 raw SQL 或 `source_files`
- `metadata` 只保留回链和调试字段，不复制整份 seed 文本

## Test Plan

- 新增 `tests/test_m2b_embedding_text_builder.py`，至少覆盖：
  - JSONL 每行合法 JSON
  - `record_id` 全局唯一且稳定
  - 输出顺序 deterministic
  - manifest 计数与 JSONL 一致
  - `embedding_text` 非空
  - 不含 secrets / raw docs / dirty SQL
  - `sql_example` 明确 non-executable
  - `mob1 / withdraw_uuid / user_uuid / asset_finish_at / credit_profile` 出现在 records 或 preview
- 验证命令：
  - `python -m compileall -q app data_acquisition_agent tests scripts`
  - `python scripts/validate_m2b_extracted_assets.py --assets-dir data_knowledge_eval/m2b/extracted_assets --golden-set data_knowledge_eval/m2b/golden_set.yaml --coverage-output docs/reviews/m2b-1-golden-set-coverage.md --coverage-yaml data_knowledge_eval/m2b/extracted_assets/extraction_coverage.yaml`
  - `python scripts/build_m2b_embedding_text.py --seed-patch data_knowledge_seed/m2b/m2b_legacy_v3.yaml --output data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl --manifest-output data_knowledge_eval/m2b/embedding_manifest.m2b_legacy_v3.yaml --preview-output data_knowledge_eval/m2b/embedding_preview.m2b_legacy_v3.md --generated-at 2026-06-25T00:00:00Z --strict`
  - `pytest tests/test_m2b_embedding_text_builder.py tests/test_m2b_seed_promotion.py tests/test_m2b_deterministic_baseline.py tests/data_knowledge/test_data_knowledge_service.py tests/data_knowledge/test_data_knowledge_retriever.py -q`
  - `git diff --check`
  - `git ls-files docs/knowledge-base`

## Assumptions

- `M2B-2.2` 已经是当前稳定 deterministic seed 基线，因此 `M2B-3` 不再继续做 seed patch。
- builder 实现保持对任意单 seed patch 通用，但本阶段唯一正式输入是 `m2b_legacy_v3`。
- 真正的 embedding 调用、vector index 构建和 semantic retrieval 实验统一留到 `M2B-4`。
