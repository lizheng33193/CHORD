# M2B-4 向量索引原型

## 阶段定位

`M2B-4` 固定为离线、可复现、可评估的 vector prototype：

```text
embedding_records.m2b_legacy_v3.jsonl
  -> local deterministic vectorizer
  -> offline vector index
  -> vector baseline
  -> deterministic vs vector comparison
```

本阶段不做：

- 真实 embedding API
- 生产向量库
- hybrid retrieval fusion
- runtime retriever / Data Agent runtime 改造
- 修改 `m2b_legacy_v3` seed 或 `embedding_records`

## 输入

- `data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl`
- `data_knowledge_eval/m2b/embedding_manifest.m2b_legacy_v3.yaml`
- `data_knowledge_eval/m2b/golden_set.yaml`
- `data_knowledge_eval/m2b/baseline_results.m2b_legacy_v3.deterministic.json`

## 输出

- `data_knowledge_eval/m2b/vector_index.m2b_legacy_v3.json`
- `data_knowledge_eval/m2b/vector_index_manifest.m2b_legacy_v3.yaml`
- `data_knowledge_eval/m2b/vector_results.m2b_legacy_v3.json`
- `data_knowledge_eval/m2b/vector_coverage.m2b_legacy_v3.yaml`
- `docs/reviews/m2b-4-vector-index-prototype-results.md`
- `docs/reviews/m2b-4-deterministic-vs-vector-comparison.md`

## 向量化策略

- vectorizer: `local_hashing_bow_v1`
- vector_dim: `512`
- vector_format: `sparse_hash_weight_map`
- normalization: `l2`
- similarity: `cosine`
- input_fields:
  - `title`
  - `embedding_text`
  - `search_hints`
- field_weights:
  - `title: 2.0`
  - `search_hints: 2.0`
  - `embedding_text: 1.0`

## tokenizer 规则

- lowercase + unicode normalize
- 保留原始 `snake_case` token，同时拆分子 token
- 支持英文 token
- 支持中文 bigram
- `search_hints` 作为高权重输入

## baseline 规则

- 只做 comparison normalization，不改 runtime retrieval 行为
- 允许：
  - 表名 short/full normalize
  - field exact / alias-aware match
  - glossary term / synonym match
  - `source_key` exact match
- 不允许：
  - synthetic retrieved assets
  - LLM 判断匹配
  - semantic rerank
  - runtime retriever 改造

## 对照输出

comparison 固定比较：

- deterministic: `baseline_results.m2b_legacy_v3.deterministic.json`
- vector: `vector_results.m2b_legacy_v3.json`

每个 case 输出：

- `deterministic_only_matches`
- `vector_only_matches`
- `shared_matches`
- `hybrid_potential`

## 验证

```bash
python -m compileall -q app data_acquisition_agent tests scripts

python scripts/build_m2b_embedding_text.py \
  --seed-patch data_knowledge_seed/m2b/m2b_legacy_v3.yaml \
  --output data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl \
  --manifest-output data_knowledge_eval/m2b/embedding_manifest.m2b_legacy_v3.yaml \
  --preview-output data_knowledge_eval/m2b/embedding_preview.m2b_legacy_v3.md \
  --generated-at 2026-06-25T00:00:00Z \
  --strict

python scripts/build_m2b_vector_index.py \
  --records data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl \
  --manifest data_knowledge_eval/m2b/embedding_manifest.m2b_legacy_v3.yaml \
  --output data_knowledge_eval/m2b/vector_index.m2b_legacy_v3.json \
  --index-manifest data_knowledge_eval/m2b/vector_index_manifest.m2b_legacy_v3.yaml \
  --vector-dim 512 \
  --generated-at 2026-06-25T00:00:00Z

python scripts/run_m2b_vector_baseline.py \
  --golden-set data_knowledge_eval/m2b/golden_set.yaml \
  --records data_knowledge_eval/m2b/embedding_records.m2b_legacy_v3.jsonl \
  --index data_knowledge_eval/m2b/vector_index.m2b_legacy_v3.json \
  --index-manifest data_knowledge_eval/m2b/vector_index_manifest.m2b_legacy_v3.yaml \
  --deterministic-baseline data_knowledge_eval/m2b/baseline_results.m2b_legacy_v3.deterministic.json \
  --output data_knowledge_eval/m2b/vector_results.m2b_legacy_v3.json \
  --coverage-yaml data_knowledge_eval/m2b/vector_coverage.m2b_legacy_v3.yaml \
  --comparison-output docs/reviews/m2b-4-deterministic-vs-vector-comparison.md \
  --top-k 10 \
  --generated-at 2026-06-25T00:00:00Z
```

## 成功标准

- vector index / manifest / results / coverage / comparison 均可重复生成
- index 与 baseline 重复运行稳定
- 能识别 `vector_only_matches`
- `unexpected` 不明显爆炸
- 不改 runtime retriever / Data Agent runtime
- 能明确判断是否进入 `M2B-5 Hybrid Retrieval Fusion`
