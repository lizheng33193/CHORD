# Pre-M3 PR-B Indexing Worker + Job Observability Gate Planning Review

## Review Scope

- docs-only planning review
- runtime implementation must not start in this PR

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

- not started
- no worker modules, route handlers, test files, migrations, or runtime configuration changes were introduced in this PR

## Runtime Verification

- not executed because this PR is docs-only

## Planning Verification

- `git diff --check`

## Known Limitations

- no runtime code changed
- full repository regression not run
- worker implementation remains a future PR
- polling remains the planned observability baseline; no SSE / WebSocket work is introduced here

## Next Step

- open a later runtime implementation PR from `main` after this docs-only planning boundary is accepted
