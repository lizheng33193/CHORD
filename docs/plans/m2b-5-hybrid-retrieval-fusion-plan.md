# M2B-5 Hybrid Retrieval Fusion

## Summary

- 本阶段固定为离线 hybrid baseline，不改 runtime retriever，不接 Data Agent runtime。
- 输入只使用现有：
  - `baseline_results.m2b_legacy_v3.deterministic.json`
  - `vector_results.m2b_legacy_v3.json`
  - `vector_coverage.m2b_legacy_v3.yaml`
  - `golden_set.yaml`
- 目标是验证 `deterministic 主召回 + vector 受控补充` 是否稳定优于 deterministic-only。

## Implementation

- 新增 `scripts/run_m2b_hybrid_baseline.py`，实现 `primary_merge_v1`：
  - deterministic 保持主结果，不删除、不覆盖、不重排已有候选
  - vector 只补 deterministic candidate set 中不存在的新候选
  - fusion 决策只看：
    - `rank`
    - `score`
    - `asset_family`
    - dedupe key
    - family cap
    - case cap
    - deterministic pass guard
  - fusion 决策不得读取：
    - `expected_*`
    - `matched_expected`
    - `missing_expected`

- conservative defaults 固定为：
  - `rank <= 8`
  - family thresholds:
    - `catalog_table >= 0.18`
    - `catalog_field >= 0.16`
    - `glossary_term >= 0.17`
    - `sql_example >= 0.15`
  - family caps:
    - table `<= 1`
    - field `<= 2`
    - glossary `<= 1`
    - sql example `<= 1`
  - per-case supplement cap：`<= 3`
  - `deterministic_judgment=pass` 时默认不接受 vector supplement

- 输出：
  - `hybrid_results.m2b_legacy_v3.json`
  - `hybrid_coverage.m2b_legacy_v3.yaml`
  - `hybrid_manifest.m2b_legacy_v3.yaml`
  - `docs/reviews/m2b-5-deterministic-vs-vector-vs-hybrid-comparison.md`
  - `docs/reviews/m2b-5-hybrid-retrieval-fusion-results.md`

## Output Contract

- 每个 hybrid case 至少包含：
  - `retrieved_tables`
  - `retrieved_fields`
  - `retrieved_glossary_terms`
  - `retrieved_examples`
  - `retrieved_error_cases`
  - `vector_supplements`
  - `rejected_vector_candidates`
  - `matched_expected`
  - `missing_expected`
  - `unexpected`
  - `judgment`
  - `notes`

- `vector_supplements` 记录：
  - `record_id`
  - `source_key`
  - `asset_family`
  - `title`
  - `score`
  - `rank`
  - `accepted_reason`

- `rejected_vector_candidates` 记录：
  - `record_id`
  - `source_key`
  - `asset_family`
  - `title`
  - `score`
  - `rank`
  - `rejected_reason`

## Validation

```bash
python -m compileall -q app data_acquisition_agent tests scripts

python scripts/run_m2b_hybrid_baseline.py \
  --golden-set data_knowledge_eval/m2b/golden_set.yaml \
  --deterministic-baseline data_knowledge_eval/m2b/baseline_results.m2b_legacy_v3.deterministic.json \
  --vector-baseline data_knowledge_eval/m2b/vector_results.m2b_legacy_v3.json \
  --output data_knowledge_eval/m2b/hybrid_results.m2b_legacy_v3.json \
  --coverage-yaml data_knowledge_eval/m2b/hybrid_coverage.m2b_legacy_v3.yaml \
  --manifest-output data_knowledge_eval/m2b/hybrid_manifest.m2b_legacy_v3.yaml \
  --comparison-output docs/reviews/m2b-5-deterministic-vs-vector-vs-hybrid-comparison.md \
  --generated-at 2026-06-28T00:00:00Z

pytest tests/test_m2b_hybrid_baseline.py \
       tests/test_m2b_vector_index.py \
       tests/test_m2b_vector_baseline.py \
       tests/test_m2b_embedding_text_builder.py \
       tests/test_m2b_seed_promotion.py \
       tests/test_m2b_deterministic_baseline.py \
       tests/data_knowledge/test_data_knowledge_service.py \
       tests/data_knowledge/test_data_knowledge_retriever.py -q
```

## Success Criteria

- hybrid 不回退任何 deterministic case
- `fail = 0`
- 至少 2 个 case 的 `missing_expected` 下降
- 至少 2 个有效 vector-only useful matches 被 hybrid 吸收
- `unexpected` 不明显增加
- 若收益稳定，下一步进入更 runtime-facing 的 hybrid 设计，而不是直接上线
