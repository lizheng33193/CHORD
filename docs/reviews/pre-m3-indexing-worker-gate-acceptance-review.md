# Pre-M3 PR-B Indexing Worker + Job Observability Gate Review

## Review Scope

- planning acceptance baseline plus runtime branch evidence, followed by final acceptance repair closure
- runtime implementation is complete on the dedicated PR-B runtime branch and is now accepted for Pre-M3 scope

## Baseline

- `main@aab6e83`
- `PR-A` is frozen as `accepted for Pre-M3 scope`
- `codex/pre-m3-risk-qa-production-gate` is closed for further runtime or docs evolution

## Planning Decision

- `PR-B Indexing Worker + Job Observability Gate planned; implementation not started`
- this PR records the planning boundary for the next pre-M3 production gate

## API Strategy Decision

- `Compat Layer` selected
- `/api/risk-knowledge/admin/*` remains the compatibility management surface
- future production-oriented facades are planned under:
  - `/api/risk-knowledge/indexing/*`
  - `/api/risk-knowledge/manifests/*`
  - `/api/risk-knowledge/workers/*`

## Worker Deployment Decision

- `External + Fallback` selected
- production primary path will be an external worker process / entrypoint
- in-process worker manager remains local / dev / test / emergency fallback only
- fallback is default-off and must never silently auto-take over production jobs

## State Ownership Decision

- MySQL remains the durable lifecycle truth for jobs, manifests, activation, rollback, and audit
- Redis is planned as the queue / control / live-state plane
- idempotency decisions must use MySQL durable state, not Redis only

## Runtime Implementation Status

- `PR-B Indexing Worker + Job Observability Gate accepted for Pre-M3 scope`
- runtime branch currently adds:
  - production indexing job facade routes
  - production manifest activate / rollback facade routes
  - production worker health route
  - durable idempotency-key persistence for production job submission
  - manifest rollback path that restores the previous active pointer
  - external-worker-first startup gate with explicit in-process fallback helper
- runtime branch commit: `b3f6da398108cf0f8fdc647716f16a04bc42a36f`
- runtime implementation is ready for PR review but is not yet finally accepted or merged at this review stage

## Runtime Verification

- targeted runtime verification executed on the runtime branch:
  - `pytest tests/risk_knowledge/test_indexing_worker.py tests/risk_knowledge/test_indexing_job_api.py tests/risk_knowledge/test_manifest_activation_rollback.py tests/risk_knowledge/test_stale_job_detection.py tests/risk_knowledge/test_indexing_job_idempotency.py -q`
  - `pytest tests/knowledge_base/test_schemas.py tests/knowledge_base/test_sqlalchemy_repositories.py tests/knowledge_base/test_services.py tests/risk_knowledge/admin/test_admin_api_routes.py tests/risk_knowledge/admin/test_indexing_admin_service.py -q`
- targeted runtime result:
  - `68 passed, 6 warnings`
- additional verification:
  - `python -m compileall -q app tests`
  - `git diff --check`
- runtime verification remains targeted only for the runtime branch snapshot; later full-repository final acceptance closure did run and failed

## Production Risk Checks

- route registration confirmed for:
  - existing `/api/risk-knowledge/admin/*`
  - `/api/risk-knowledge/indexing/*`
  - `/api/risk-knowledge/manifests/*`
  - `/api/risk-knowledge/workers/*`
- runtime defaults confirmed:
  - `RISK_KNOWLEDGE_WORKER_MODE=external`
  - `RISK_KNOWLEDGE_IN_PROCESS_WORKER_FALLBACK_ENABLED=false`
- no silent in-process fallback is the intended default runtime posture
- no repo-managed migration files were added in this PR; durable schema evolution remains a final deployment acceptance concern

## Planning Verification

- `git diff --check`

## Known Limitations

- runtime implementation is complete on the branch and historical targeted evidence remains part of the record
- the first final acceptance closure attempt ran `pytest -q` and failed with `110 failed, 1462 passed, 11 skipped, 33 warnings`
- worker presence / observability remains polling-oriented; no SSE / WebSocket work is introduced here
- polling remains the planned observability baseline; no SSE / WebSocket work is introduced here
- migration/deployment acceptance remains pending because the PR adds durable schema usage without introducing repo-managed migration files

## Final Acceptance Closure Attempt

Executed on `2026-07-04` from `codex/pre-m3-final-acceptance-closure`:

- `pytest -q`
  - result: `110 failed, 1462 passed, 11 skipped, 33 warnings`
- `python -m compileall -q app tests`
  - result: passed
- `git diff --check`
  - result: passed

Acceptance outcome:

- PR-B remained `implemented; pending final acceptance`
- Pre-M3 acceptance was not closed
- Pre-M3 gates were not yet ready for M3 entry

## Final Acceptance Repair Closure

Executed later on `2026-07-04` from `codex/pre-m3-regression-triage`:

- `pytest -q`
  - result: `1575 passed, 11 skipped, 33 warnings`
- `python -m compileall -q app tests data_acquisition_agent conftest.py`
  - result: passed
- `git diff --check`
  - result: passed
- `python -m app.release.pre_m3_gate --profile production_release --strict --full-regression-status passed --output-json /tmp/pre_m3_gate_production_release_passed.json`
  - result: `PASS`

Final outcome:

- PR-B is accepted for Pre-M3 scope
- Pre-M3 final acceptance is closed
- Pre-M3 gates are ready for M3 entry

## Next Step

- resolve full-repository regression failures before attempting final acceptance closure again
- complete schema/deployment acceptance after the repository-level regression baseline is green
