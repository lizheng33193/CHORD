# M5-2 Memory Governance Eval Plan

## Goal
- Land `memory_governance` as the first contract-backed domain suite on the shared eval foundation.

## Deliverables
- `app/eval/evaluators/memory.py`
- `memory_governance` suite registration
- additive multi-suite profile support in `app/eval/runner.py`
- additive suite-scoped report summaries and metrics
- deterministic `tests/eval_cases/memory_governance.yaml`
- targeted `tests/eval/` coverage

## Explicit Constraints
- Inspect and reuse actual M4 seams; do not assume names.
- Keep single-suite CLI behavior unchanged.
- Keep `production_release` smoke-only in `M5-2`.
- Preserve raw runtime reason codes alongside normalized eval reason codes.
- Do not change Memory runtime behavior.
- Keep eval-only fallback exceptional; avoid it when runtime or adapter seams exist.
