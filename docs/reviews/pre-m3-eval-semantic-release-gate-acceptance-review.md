# Pre-M3 PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate Planning Review

## 1. Review Scope

- docs-only planning review
- no runtime implementation review is included in this document

## 2. Baseline

- latest `main` after the PR-B docs-only follow-up was reconciled onto `main`
- `PR-B` runtime landed via `PR #56`
- `PR-B` docs-only follow-up landed onto `main` via commit `09ce55b`
- `PR-A` remains frozen as `implemented; pending final acceptance`
- `PR-B` remains `implemented; pending final acceptance`

## 3. Planning Decision

- `PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate planned; implementation not started`
- this PR records the planning boundary for the final Pre-M3 production gate

## 4. Selected Approach

- additive reuse of existing harness seams was selected
- Risk QA regression extends `app/risk_knowledge/evaluation/`
- SQL semantic validator is planned under `app/data_agent/semantic_validation/`
- release gate is planned under `app/release/`
- formal release-gate entrypoint is:
  - `python -m app.release.pre_m3_gate`

## 5. Runtime Implementation Status

- not started
- this PR must not implement release gate runtime, semantic validator runtime, runbook, tests, or contract code

## 6. Runtime Verification

- not executed because this PR is docs-only

## 7. Planning Verification

- `git diff --check`

## 8. Required Runtime Spec

- PR-C2 must add or update a dedicated contract spec before code changes:
  - `docs/specs/pre-m3-eval-semantic-release-gate-contract.md`
- the runtime spec must lock:
  - Risk QA eval case schema
  - SQL semantic validation result contract
  - release gate report contract
  - release gate status semantics
  - Data Agent integration boundary

## 9. Known Limitations

- no `app/`, `tests/`, `scripts/`, `migrations/`, or `docs/runbooks/` changes are allowed in this PR
- no runtime behavior is changed in this PR
- full repository regression was not run for this docs-only planning PR
- runtime implementation, runtime tests, and runbook authoring remain future PR-C2 work

## 10. Next Step

- merge PR-C1 planning
- start `PR-C2` runtime implementation from latest `main`
- add or update the dedicated PR-C2 contract spec before code changes
