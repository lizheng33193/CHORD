# M2C Status Reconciliation Review

## Summary

Current project-level status for `M2C` should be recorded as:

> `M2C: partially covered by FU4-FU7 / M2B; standalone governance & semantic validator not formally reconciled`

中文表述：

> `M2C：部分能力已由 FU4-FU7 / M2B 覆盖；作为独立阶段的知识治理与 SQL 语义校验尚未正式启动。`

This review is a status-reconciliation document only. It does not introduce a new validator, does not change runtime behavior, and does not start `M2D`.

## What FU4-FU7 Already Covered

The `M2A-RQ-FU4` through `FU7` sequence already implemented several `M2C-like` controls on the Data Agent harness side:

- `FU4`
  - canonical field policy
  - prompt-side `sql_intent_plan`
  - warning-only `NON_CANONICAL_FIELD`
- `FU5`
  - deterministic post-generation `PLAN_*` review
  - plan-to-SQL consistency checking
- `FU6`
  - bounded one-shot repair for repairable `PLAN_*` drift
  - repair trace kept inside reviewable runtime metadata
- `FU7`
  - pre-generation `structured_sql_plan`
  - deterministic planning gate
  - invalid plans blocked before SQL generation

These capabilities mean the repo already has substantial SQL planning / validation / repair controls, even though they were delivered under the `M2A-RQ-FU*` line rather than a standalone `M2C` label.

## What M2B Already Covered

The `M2B` line already covered several governance / grounding / provenance capabilities that overlap with the original intent of a future `M2C` governance stage:

- `M2B-6`
  - hybrid retrieval governance contract
  - rollout / fallback / safety boundary design
- `M2B-7` to `M2B-9.1`
  - runtime fallback enforcement
  - candidate / final-attempt provenance
  - bounded trace / observability / rollout readiness
  - explicit rule that retrieval is grounding enhancement, not execution authority

This means retrieval governance, audit boundary, fallback semantics, and rollout discipline are no longer “missing from the program” in a broad sense; they exist, but they landed under `M2B`.

## What Standalone M2C Still Does Not Have

`M2C` should **not** be marked `completed`, because the repo still does **not** contain a separately reconciled `M2C` stage with its own formal implementation boundary.

Still missing as an independent `M2C` stage:

- a standalone phase artifact that explicitly owns “knowledge governance + SQL semantic validator” end to end
- a reconciled stage definition that separates `M2C` from `M2A-RQ-FU4`~`FU7` and `M2B`
- a formally named and independently tracked semantic-validator/governance deliverable under `M2C`
- a dedicated `M2C` closure review showing that these controls were intentionally consolidated rather than historically scattered

So the right reading is:

- `M2C` is **partially covered**
- `M2C` is **not independently implemented as a clean standalone phase**
- `M2C` is **not blocked by missing runtime basics**

## Why M2C Is Not Completed

`M2C` cannot be called `completed` because the project never shipped a clean, self-contained `M2C` phase with:

- explicit phase scope
- explicit deliverables
- explicit closure review
- explicit status reconciliation against the already-shipped `FU4-FU7` and `M2B` controls

The right project status is therefore:

- not `not started`, because important pieces already exist
- not `completed`, because no standalone reconciled phase was actually closed
- `partially covered by FU4-FU7 / M2B`

## Why M2C Does Not Block M2D

The remaining `M2C` gap is primarily a **stage-governance / ownership / reconciliation gap**, not a missing runtime prerequisite for the next knowledge stage.

`M2D Risk Domain Knowledge RAG` can start later without a standalone `M2C` implementation first because:

- SQL planning / validation / bounded repair already exist through `FU4-FU7`
- retrieval governance / fallback / provenance / rollout controls already exist through `M2B`
- `M2D` can build on the current harness contracts instead of waiting for a renamed or re-packaged validator phase

In other words:

> `M2C` is not cleanly closed as an independent stage, but its residual gap is not a hard blocker for `M2D`.

## Reconciled Project Status

The project-level snapshot should be read as:

- `M2A-RQ`: completed
- `M2B`: completed through `M2B-9.1`
- `M2C`: partially covered by `FU4-FU7 / M2B`; standalone governance & semantic validator not formally reconciled
- `M2D`: not started

## Final Decision

- Do not start `M2C` implementation work from this review.
- Do not mark `M2C` as `completed`.
- Do not let `M2C` status ambiguity block later `M2D` planning.
- Treat this review as the official reconciliation note that cleans up the roadmap state before `M2D` planning begins.
