# M2B-2.2 Targeted Deterministic Grounding Patch

## Summary

- `M2B-2.2` 固定为最后一轮 seed-level deterministic grounding patch，不进入 embedding / vector / hybrid retrieval。
- 本阶段从 `m2b_legacy_v2` 的 deterministic baseline 缺口出发，生成完整替代 patch `m2b_legacy_v3.yaml`，并在同一版 baseline runner 下复跑 `v2` 与 `v3`，保证 A/B 对比公平。
- patch 只允许改 seed 文本、glossary synonym、field business meaning、example pattern guidance、baseline matcher 的 normalization / dedupe / comparison，不允许改 runtime retriever scoring 或新增 synthetic retrieval。

## Scope

- 版本策略：
  - `m2b_legacy_v1`：M2B-2 历史诊断基线
  - `m2b_legacy_v2`：M2B-2.1 alias / synonym grounding patch
  - `m2b_legacy_v3`：M2B-2.2 targeted field / asset / mob1 grounding patch
- 每次 baseline 只允许：
  - `mx/ph/common + m2b_legacy_v2`
  - `mx/ph/common + m2b_legacy_v3`
- 不允许 `v2 + v3` 同次叠加导入。

## Targeted Gaps

- 重点修补：
  - `withdraw_uuid`
  - `user_uuid / uid`
  - `overdue_days / max_overdue_days / asset_overdue_days / real_overdue_days`
  - `asset_grant_at / asset_finish_at / asset_status / asset_*`
  - `mob1 / fully_settled / seven_day_no_reborrow_churn`
  - `behavior_writeback_pattern`
  - 尾部 `no_apply / no_withdraw / successful_withdraw / settled_over_3m / collection_behavior / contact_outcome`
- 每个 enrichments 都必须能追溯到至少一个 `v2 missing_expected`、weak match 或 priority golden case gap。

## Guardrails

- 不改 `app/data_knowledge/retriever.py` scoring / top-k / filtering。
- 不改 `app/data_agent/service.py`、`app/data_agent/sql_plan.py`、`data_acquisition_agent/orchestrator.py`。
- 不调用 LLM，不生成 SQL，不执行 SQL。
- `uid` 和 `user_uuid` 不能全局等价，只允许在 behavior writeback / join 场景中保留关联语义。
- `dt` 继续只作为 partition field，不作为 `recent_7d / apply / asset` business time 的强替代字段。
- `mob1` 不能简化为 `first_loan`；runtime-visible 语义必须同时覆盖 `first_loan + fully_settled + settlement_over_7d + no_reborrow_within_7d`。

## Expected Outputs

- `data_knowledge_seed/m2b/m2b_legacy_v3.yaml`
- `data_knowledge_eval/m2b/seed_promotion_manifest.v3.yaml`
- `data_knowledge_eval/m2b/baseline_results.m2b_legacy_v2.deterministic.json`
- `data_knowledge_eval/m2b/baseline_results.m2b_legacy_v3.deterministic.json`
- `data_knowledge_eval/m2b/deterministic_coverage.m2b_legacy_v2.yaml`
- `data_knowledge_eval/m2b/deterministic_coverage.m2b_legacy_v3.yaml`
- `docs/reviews/m2b-2-2-missing-grounding-analysis.md`
- `docs/reviews/m2b-2-2-targeted-grounding-results.md`
- `docs/reviews/m2b-2-2-v2-v3-baseline-comparison.md`

## Success Criteria

- `v2` 与 `v3` baseline 必须由同一版 runner 复跑生成。
- `v3` 相比 `rerun_v2` 不回退。
- `fail` 保持 `0`。
- `pass` 从 `3` 进一步提升，或 `withdraw / overdue / asset / mob1` 关键 gap 明显收敛。
- 不出现 raw docs / secrets / dirty SQL。
- 不引入 runtime retriever / Data Agent runtime 改动。
