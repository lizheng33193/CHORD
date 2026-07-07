# M5 Eval Regression Foundation

## Summary
- `M5-1` adds a shared eval foundation under `app/eval/`.
- It does not migrate existing domain-owned eval code.
- The only runnable shared suite in this phase is `release_gate_smoke`.

## Boundary
- Keep `app/risk_knowledge/evaluation` authoritative for Risk QA regression.
- Keep `tests/golden/memory_eval.py` authoritative for Memory offline evaluation.
- Keep `app/release/pre_m3_gate.py` authoritative for release-gate behavior and CLI semantics.
- Shared eval in `app/eval/` is additive and future-facing.

## Shared Contracts
- `EvalCase`: shared case schema for suite input/expected payloads.
- `EvalResult`: shared per-case output schema with actual status plus explicit failure reasons.
- `EvalSuite`: shared suite registry contract.
- `EvalProfile`: shared profile registry contract.
- `EvalReport`: shared JSON/Markdown artifact contract for runner output.

## M5-1 Scope
- Add shared schema, loader, suite/profile registries, report writer, and runner CLI.
- Implement `release_gate_smoke` as a thin adapter over existing release-gate code.
- Generate JSON and Markdown artifacts.
- Expose gate-friendly exit codes:
  - `0` for pass or non-strict warn
  - `1` for fail, blocked, or strict warn
  - `2` for runner/config/evaluator errors

## Non-Goals
- No Risk / Memory / Data / Profile suite migration.
- No dashboard, CI wiring, or production observability platform.
- No rewrite of release-gate status logic.
