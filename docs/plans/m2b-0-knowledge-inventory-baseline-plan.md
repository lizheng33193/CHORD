# M2B-0 Knowledge Inventory & Retrieval Baseline Plan

## Goal

Deliver the first `M2B` substage without touching runtime retrieval logic.

## Boundaries

This phase does:

- inventory raw knowledge files
- classify extractable knowledge asset types
- define a retrieval golden set
- define baseline output schema
- add a template-only baseline runner stub

This phase does not:

- run the real retriever
- modify `app/data_knowledge/retriever.py`
- modify `DataAgentService`
- modify SQL HITL, approve, execute, or orchestrator bridge
- build embeddings or vector indices
- commit raw legacy documents

## Implementation Steps

1. Protect `docs/knowledge-base/` with README and `.gitignore` rules.
2. Add `scripts/knowledge_base_inventory.py` and generate `docs/reviews/m2b-legacy-knowledge-inventory.md`.
3. Define the M2B knowledge asset taxonomy and stage design docs.
4. Add `docs/evals/m2b-retrieval-golden-set.md` and `data_knowledge_eval/m2b/golden_set.yaml`.
5. Add `scripts/run_m2b_retrieval_baseline.py` with template-only mode.
6. Generate `data_knowledge_eval/m2b/baseline_results.template.json`.
7. Write `docs/reviews/m2b-retrieval-baseline-results.md` to explain the template-only baseline.
8. Update `PLANNING.md` and `TASK.md`.

## Verification

- `git status --short`
- `git ls-files docs/knowledge-base`
- `python scripts/knowledge_base_inventory.py --source-dir docs/knowledge-base --output docs/reviews/m2b-legacy-knowledge-inventory.md`
- `python scripts/run_m2b_retrieval_baseline.py --golden-set data_knowledge_eval/m2b/golden_set.yaml --output data_knowledge_eval/m2b/baseline_results.template.json --mode template`
- `python -m compileall -q app data_acquisition_agent tests scripts`
- `pytest tests/test_m2b_inventory_tools.py tests/data_knowledge/test_data_knowledge_retriever.py tests/data_knowledge/test_prompt_context.py data_acquisition_agent/tests/test_prompt_assembler.py tests/data_agent/test_api.py tests/data_agent/test_sql_plan.py tests/data_agent/test_plan_review.py tests/data_agent/test_repair.py -q`
- `git diff --check`

## Exit Criteria

- raw docs remain untracked
- inventory report contains metadata only
- taxonomy is defined with fixed runtime enums
- golden set exists with the requested first batch
- baseline runner works in template mode only
- baseline report clearly states that no real retriever was executed
