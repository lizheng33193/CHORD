# M5 Memory Governance Eval Suite

## Summary
- `M5-2` adds `memory_governance` as the first real domain suite on top of `app/eval/`.
- The suite is contract-backed and reuses existing M4 memory seams for use validation, retrieval boundaries, context rendering, and promotion validation.
- `pr_acceptance` now runs `release_gate_smoke` plus `memory_governance`.
- `production_release` remains smoke-only until `M5-6`.

## Boundary
- Keep M4 runtime contracts authoritative:
  - `app.services.memory.isolation.validate_memory_use`
  - `app.services.memory.retrieval.MemoryRetrievalService`
  - `app.services.memory.context_builder.build_memory_context_bundle`
  - `app.services.memory.promotion.validate_memory_promotion`
- Do not mutate Memory runtime behavior in `M5-2`.
- Extend `app/eval/` only as much as needed for additive multi-suite profile execution and suite-scoped reporting.

## Suite Shape
- Suite id: `memory_governance`
- Profile integration:
  - `pr_acceptance = ["release_gate_smoke", "memory_governance"]`
  - `production_release = ["release_gate_smoke"]`
- Case groups:
  - `use_policy`
  - `retrieval_policy`
  - `context_rendering`
  - `promotion_policy`

## Result Semantics
- `EvalResult.status` reports eval pass/fail for this suite.
- Runtime policy decisions are preserved separately in `metrics` and `artifacts`.
- `artifacts` must preserve:
  - `policy_source`
  - `raw_decision`
  - `raw_reason_code`
  - `normalized_reason_code`
  - `check_kind`

## Report Additions
- `EvalReport` now supports additive multi-suite fields:
  - `selected_suites`
  - `suite_summaries`
  - `suite_metrics`
- Single-suite CLI behavior remains compatible.

## Non-Goals
- No `production_release` integration for `memory_governance` in this phase.
- No eval-owned parallel memory policy engine.
- No dashboard, CI replacement, or online monitoring expansion.
