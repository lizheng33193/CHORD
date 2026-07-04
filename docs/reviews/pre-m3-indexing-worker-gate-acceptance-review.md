# Pre-M3 PR-B Indexing Worker + Job Observability Gate Review

## Review Scope

- planning acceptance baseline plus runtime in-progress review snapshot
- runtime implementation has started on the dedicated PR-B runtime branch

## Baseline

- `main@aab6e83`
- `PR-A` is frozen as `implemented; pending final acceptance`
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

- `implementation in progress`
- runtime branch currently adds:
  - production indexing job facade routes
  - production manifest activate / rollback facade routes
  - production worker health route
  - durable idempotency-key persistence for production job submission
  - manifest rollback path that restores the previous active pointer
  - external-worker-first startup gate with explicit in-process fallback helper
- runtime implementation is not yet accepted or merged at this review stage

## Runtime Verification

- targeted runtime verification executed on the runtime branch:
  - `pytest tests/risk_knowledge/test_indexing_worker.py tests/risk_knowledge/test_indexing_job_api.py tests/risk_knowledge/test_manifest_activation_rollback.py tests/risk_knowledge/test_stale_job_detection.py tests/risk_knowledge/test_indexing_job_idempotency.py -q`
  - `pytest tests/knowledge_base/test_schemas.py tests/knowledge_base/test_sqlalchemy_repositories.py tests/knowledge_base/test_services.py tests/risk_knowledge/admin/test_admin_api_routes.py tests/risk_knowledge/admin/test_indexing_admin_service.py -q`
- runtime verification remains targeted only; full repository regression has not run

## Planning Verification

- `git diff --check`

## Known Limitations

- runtime implementation is still in progress and not yet accepted
- full repository regression not run
- worker presence / observability remains polling-oriented; no SSE / WebSocket work is introduced here
- polling remains the planned observability baseline; no SSE / WebSocket work is introduced here

## Next Step

- continue PR-B runtime implementation and validation on the dedicated runtime branch until acceptance criteria are met
