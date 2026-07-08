# M5-4 Risk QA Groundedness Eval Suite Plan

## Goal
- Land a deterministic Risk QA groundedness regression suite on the shared eval platform.

## Deliverables
- `app/eval/evaluators/risk_qa.py`
- `risk_qa_groundedness` suite registration
- deterministic `tests/eval_cases/risk_qa_groundedness.yaml`
- `pr_acceptance` profile expansion only
- targeted `tests/eval/` coverage plus Risk QA deterministic non-regression verification

## Explicit Constraints
- Reuse deterministic Risk QA seams first, thin adapters second, eval-only last resort.
- Do not run full LLM-backed Risk QA generation flows.
- Do not call embedding providers, FAISS, Redis workers, indexing, rebuild, activate, or rollback.
- Preserve raw runtime codes and raw source labels alongside normalized eval report codes.
- Keep `production_release` smoke-only in `M5-4`.
