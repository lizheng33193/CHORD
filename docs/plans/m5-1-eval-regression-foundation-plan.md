# M5-1 Eval Regression Foundation Plan

## Goal
- Land a shared eval foundation that can run one smoke suite without changing domain-owned eval entrypoints.

## Deliverables
- `app/eval/` shared foundation.
- `release_gate_smoke` suite and two profiles: `pr_acceptance`, `production_release`.
- Shared JSON and Markdown report artifacts.
- Targeted `tests/eval/` coverage.

## Explicit Constraints
- Keep existing Risk / Memory / Release eval entrypoints authoritative.
- Do not migrate existing domain evaluators in this phase.
- Make the default suite non-failing for direct CLI smoke.
- Put PASS/WARN/FAIL/BLOCKED matrix coverage in test-only fixtures.
