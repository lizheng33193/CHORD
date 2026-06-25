# M2B-3 Embedding Text Builder Results

## Summary

- `M2B-3` 已完成为 `m2b_legacy_v3` seed patch 生成统一 embedding text records。
- 本阶段产出：
  - `data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl`
  - `data_knowledge_eval/m2b/embedding_manifest.m2b_legacy_v3.yaml`
  - `data_knowledge_eval/m2b/embedding_preview.m2b_legacy_v3.md`
  - `scripts/build_m2b_embedding_text.py`
  - `tests/test_m2b_embedding_text_builder.py`
- 本阶段继续保持不变：
  - 不调用 embedding API
  - 不生成 vector
  - 不建 FAISS / Milvus / pgvector
  - 不改 runtime retriever / Data Agent runtime
  - 不读取 `docs/knowledge-base` raw docs

## Output Snapshot

- source namespace: `m2b_legacy_v3`
- generated_at: `2026-06-25T00:00:00Z`
- record count: `101`
- family counts:
  - `catalog_table`: `10`
  - `catalog_field`: `61`
  - `glossary_term`: `28`
  - `sql_example`: `2`
  - `sql_error_case`: `0`
- skipped counts:
  - `unsupported_family`: `0`
  - `inactive_status`: `0`
  - `empty_embedding_text`: `0`

## Validation Notes

- JSONL 输出顺序固定为 `asset_family -> country -> source_key`，重复运行同一输入会生成一致内容。
- `record_id` 使用稳定资产身份：
  - `sha256(source_namespace + source_key + asset_family)`
- `sql_example` records 已明确标记：
  - `Non-executable pattern guidance.`
  - `This record is not executable SQL.`
- records 已通过脱敏约束：
  - 不含 `host / user / password / jdbc / pymysql.connect / create_engine`
  - 不含 `dm_model.yx_tmp_*`、固定历史日期或 raw dirty SQL 片段
- preview 已覆盖：
  - `mob1`
  - `withdraw_uuid`
  - `user_uuid`
  - `asset_finish_at`
  - `credit_profile`

## Conclusion

- `M2B-3` 已为 `M2B-4 Vector Index Prototype` 准备好统一、稳定、可审查的 embedding text 输入。
- 当前建议下一步进入 `M2B-4`，在继续保持 runtime 隔离的前提下，对这些 records 做离线 vector index prototype。
