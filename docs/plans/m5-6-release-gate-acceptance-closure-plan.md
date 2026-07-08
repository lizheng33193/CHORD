# M5-6 Release Gate & Acceptance Closure Plan

## Goal
- Close `M5` by promoting `production_release` to the full deterministic 7-suite release gate and by publishing final M5 acceptance artifacts.

## Deliverables
- `production_release` expanded to the same ordered 7-suite list as `pr_acceptance`
- `strict_by_default=True` retained for `production_release`
- additive runner preflight commands:
  - `--list-suites`
  - `--list-profiles`
- `tests/eval/` coverage for release-gate profile closure and preflight CLI behavior
- `docs/specs/m5-release-gate-policy.md`
- `docs/reviews/m5-6-release-gate-acceptance-closure-review.md`
- `docs/reviews/m5-acceptance-closure.md`
- `PLANNING.md` / `TASK.md` status sync to `M5 completed` and `M6 not started`

## Explicit Constraints
- Do not add new domain eval suites in `M5-6`.
- Do not change suite evaluator logic, fixtures, or metrics.
- Do not modify Memory, Data Agent, Risk QA, or Profile DAG runtime behavior.
- `--list-suites` and `--list-profiles` must not execute evaluators, read case files, write reports, or create output directories.
- Release-gate documentation must record actual verification results rather than aspirational outcomes.
