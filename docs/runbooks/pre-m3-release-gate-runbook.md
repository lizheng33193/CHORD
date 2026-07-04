# Pre-M3 Release Gate Runbook

## Purpose

This runbook explains how to execute the PR-C Pre-M3 production gate before any M3 runtime rollout.

It covers:

- Risk QA regression execution
- SQL semantic validator execution
- worker health verification
- manifest activation verification
- failed / stale indexing job handling
- rollback steps
- Data Agent HITL boundary verification

## 1. Run Risk QA Regression

- Use the PR-C Risk QA golden-set runner under `app/risk_knowledge/evaluation`.
- Minimum expectation before release:
  - citation validity remains `100%`
  - context isolation remains `100%`
  - insufficient-evidence refusal cases continue to refuse
- If regression output shows forbidden source leakage or invalid citations:
  - do not proceed
  - treat the release gate as `FAIL` or `BLOCKED` depending on the failing check profile

## 2. Run SQL Semantic Validation

- SQL semantic validation runs under `app/data_agent/semantic_validation`.
- Validate representative cohort-query and bucket-writeback paths.
- At minimum verify:
  - country scope mismatch blocks
  - UID boundary gaps block
  - risky write operations block
  - broad behavior-table scans block
- If validator output is `blocked`:
  - candidate SQL must not be approved
  - candidate SQL must not become executable

## 3. Run The Release Gate

- Formal entrypoint:

```bash
python -m app.release.pre_m3_gate --profile pr_acceptance
```

- Production release posture:

```bash
python -m app.release.pre_m3_gate --profile production_release --strict
```

- Expected status semantics:
  - `PASS`: required checks passed
  - `WARN`: non-blocking checks or missing full regression in PR acceptance mode
  - `FAIL`: required checks failed
  - `BLOCKED`: production release must not proceed

## 4. Confirm Worker Health

- Verify the worker facade reports healthy external-worker posture.
- Confirm production defaults remain:
  - `RISK_KNOWLEDGE_WORKER_MODE=external`
  - `RISK_KNOWLEDGE_IN_PROCESS_WORKER_FALLBACK_ENABLED=false`
- If worker health is missing, stale, or fallback-only:
  - do not treat the system as production ready

## 5. Confirm Manifest State

- Verify the active manifest is the expected manifest for retrieval.
- Confirm manifest activation / rollback APIs remain available.
- If manifest activation state is unclear:
  - stop the release
  - verify the previous known-good active manifest pointer before retrying

## 6. Handle Failed Or Stale Jobs

- Failed jobs:
  - inspect job error details
  - retry only after the underlying runtime issue is understood
- Stale jobs:
  - confirm heartbeat / lease status
  - use the existing stale recovery / retry flow
  - do not assume a queued/running state is healthy without checking worker freshness

## 7. Rollback Procedure

- If Risk QA regression, semantic validation, or manifest validation fails after a change:
  - stop rollout
  - restore the previous known-good manifest if manifest activation changed
  - keep in-process fallback disabled unless explicitly required for a controlled emergency path
- If the release gate is `BLOCKED`:
  - do not override with a manual “looks fine” judgment
  - resolve the blocking check first

## 8. Confirm HITL Boundaries

- Data Agent semantic validation is a pre-execution semantic gate only.
- Confirm:
  - blocked SQL is not approvable
  - passed SQL still requires the existing human review / approval path
  - no PR-C change bypasses `approved_sql` / `approved_by` governance

## 9. Production No-Go Checklist

- Do not proceed if:
  - Risk QA citations are invalid
  - context isolation is broken
  - semantic validator blocks representative SQL
  - worker health is missing
  - manifest state is not verified
  - full repository regression is not run for production release
