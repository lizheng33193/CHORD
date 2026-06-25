# M2B-2 Seed Promotion & Deterministic Retrieval Baseline Plan

## Goal

Promote a safe subset of `M2B-1` candidate assets into an isolated runtime seed patch and run the first real deterministic retrieval baseline against `data_knowledge_eval/m2b/golden_set.yaml`.

## Boundaries

- Do not add embeddings, vector indices, or hybrid retrieval.
- Do not modify `DataAgentService`, SQL HITL, approve/execute, or orchestrator bridge behavior.
- Do not import `docs/knowledge-base/` raw docs into runtime prompt or Git.
- Do not change the public `SeedImportRequest(bundle=mx|ph|common)` contract.
- Do not change `app/data_knowledge/retriever.py` scoring, top-k, or filtering in this phase.

## Implementation

1. Review all `M2B-1` candidate assets and write `data_knowledge_eval/m2b/seed_promotion_manifest.yaml`.
2. Promote only runtime-safe assets into `data_knowledge_seed/m2b/m2b_legacy_v1.yaml`.
3. Keep `business_rule`, `cohort_definition`, and `needs_human_review` canonical policies out of runtime seed import.
4. Add an internal `import_seed_patch(...)` helper that reuses existing seed upsert logic without changing the public bundle API.
5. Extend `scripts/run_m2b_retrieval_baseline.py` with `--mode deterministic` and run it only inside an isolated temporary SQLite/auth DB.
6. Produce deterministic baseline JSON, YAML coverage, and markdown review artifacts.

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `python scripts/validate_m2b_extracted_assets.py --assets-dir data_knowledge_eval/m2b/extracted_assets --golden-set data_knowledge_eval/m2b/golden_set.yaml --coverage-output docs/reviews/m2b-1-golden-set-coverage.md --coverage-yaml data_knowledge_eval/m2b/extracted_assets/extraction_coverage.yaml`
- `python scripts/promote_m2b_extracted_assets.py --assets-dir data_knowledge_eval/m2b/extracted_assets --manifest data_knowledge_eval/m2b/seed_promotion_manifest.yaml --seed-output data_knowledge_seed/m2b/m2b_legacy_v1.yaml --review-output docs/reviews/m2b-2-seed-promotion-review.md`
- `python scripts/run_m2b_retrieval_baseline.py --golden-set data_knowledge_eval/m2b/golden_set.yaml --output data_knowledge_eval/m2b/baseline_results.deterministic.json --mode deterministic`
- `pytest tests/test_m2b_inventory_tools.py tests/test_m2b_extracted_assets.py tests/test_m2b_seed_promotion.py tests/test_m2b_deterministic_baseline.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_sql_plan.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py -q`
- `git diff --check`
- `git ls-files docs/knowledge-base`
- `git diff --name-only main...HEAD`
