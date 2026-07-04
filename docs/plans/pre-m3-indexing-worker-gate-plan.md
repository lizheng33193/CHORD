# Pre-M3 PR-B Indexing Worker + Job Observability Gate Plan

## 1. Summary

- Status for this PR:
  - `Approved for docs-only planning execution.`
  - `Runtime implementation must not start in this PR.`
- PR-B upgrades the current indexing runtime from the already-landed single-process durable worker loop into an external-worker-first production architecture.
- The target outcome is stronger job observability, clearer public production facades, and safer manifest activation / rollback behavior.
- This PR is docs-only and must not modify runtime code, tests, scripts, migrations, or runtime configuration.

## 2. Baseline And Branch Boundary

- Fixed baseline:
  - `main` merge commit `aab6e83`
  - `PR-A` frozen as `implemented; pending final acceptance`
  - `codex/pre-m3-risk-qa-production-gate` is closed for further runtime or docs evolution
- PR-B execution branch:
  - `codex/pre-m3-indexing-worker-gate`
- Allowed file changes in this PR:
  - `docs/plans/pre-m3-indexing-worker-gate-plan.md`
  - `docs/reviews/pre-m3-indexing-worker-gate-acceptance-review.md`
  - `PLANNING.md`
  - `TASK.md`

## 3. Current Runtime Truth

- `main` already contains:
  - a single-process durable worker loop
  - durable job state in MySQL
  - retry / rebuild flow
  - heartbeat and stale recovery behavior
  - manifest persistence and activation
- PR-B is not a greenfield queue design.
- PR-B must be framed as an evolution of the current indexing runtime toward an external-worker-first production architecture with stronger observability and manifest safety boundaries.

## 4. Scope

- Plan the next production gate for risk knowledge indexing.
- Define the public API boundary for job submission, job status, manifest lifecycle, and worker visibility.
- Define queue, job, event, lease, stale recovery, idempotency, and manifest guard policies.
- Define the runtime PR test plan, acceptance criteria, and no-go criteria.
- Keep existing admin consumers supported through a compatibility strategy.

## 5. Explicit Out Of Scope

- runtime implementation
- worker module creation
- API route implementation
- test implementation or execution beyond `git diff --check`
- SSE / WebSocket
- full observability dashboard
- M3 DAG runtime work
- PR-A Risk QA reopening
- Data Agent HITL changes
- M2C validator work
- distributed autoscaling design beyond the minimum worker presence / heartbeat model

## 6. API Boundary Strategy: Compat Layer

- Keep `/api/risk-knowledge/admin/*` as the compatibility management surface.
- Plan the future production-oriented facades under:
  - `/api/risk-knowledge/indexing/*`
  - `/api/risk-knowledge/manifests/*`
  - `/api/risk-knowledge/workers/*`
- Future implementation may let existing admin endpoints delegate through aliases or adapters to the new production facades.
- PR-B runtime implementation must not remove, rename, or silently repurpose existing admin routes in a breaking way.

## 7. Worker Deployment Strategy: External + Fallback

- Production primary path:
  - independent worker process / entrypoint
  - API submits jobs and exposes status / control / visibility surfaces only
- Compatibility fallback:
  - existing in-process worker manager remains available for local, dev, test, or explicit emergency fallback only
  - default-off in production
- Required worker fallback policy:
  - `RISK_KNOWLEDGE_WORKER_MODE=external`
  - `RISK_KNOWLEDGE_IN_PROCESS_WORKER_FALLBACK_ENABLED=false`
  - no silent fallback when no external worker is alive
  - fallback use must emit `IN_PROCESS_WORKER_FALLBACK_USED` warning / event / audit data

## 8. State Ownership

### 8.1 MySQL Durable Truth

- MySQL remains the durable lifecycle truth for:
  - jobs
  - manifests
  - manifest activation
  - manifest rollback
  - audit and event persistence
- Idempotency decisions must be made against MySQL durable state, not Redis alone.

### 8.2 Redis Queue / Control / Live-State Plane

- Redis is the operational plane for:
  - queue
  - processing set
  - dead-letter set
  - per-job live state
  - per-job event stream
  - per-document-version lock
  - per-worker heartbeat / presence
  - short-lived progress cache
- Redis must not become the only durable source for lifecycle truth.

## 9. Planned Public Facades

### 9.1 Indexing APIs

- `POST /api/risk-knowledge/indexing/jobs`
- `GET /api/risk-knowledge/indexing/jobs/{job_id}`
- `POST /api/risk-knowledge/indexing/jobs/{job_id}/retry`
- `POST /api/risk-knowledge/indexing/rebuild`

### 9.2 Manifest APIs

- `GET /api/risk-knowledge/manifests/{manifest_id}`
- `POST /api/risk-knowledge/manifests/{manifest_id}/activate`
- `POST /api/risk-knowledge/manifests/{manifest_id}/rollback`

### 9.3 Worker Health APIs

- `GET /api/risk-knowledge/workers/health`
- worker health must expose whether an external worker is currently live enough for production pickup

### 9.4 Existing Admin Compatibility Surface

- `/api/risk-knowledge/admin/*` remains available for compatibility.
- Admin routes stay management-oriented and may delegate to the new facades after runtime implementation starts.

## 10. Redis Namespace

- planned namespace coverage:
  - queue
  - processing
  - dead-letter
  - per-job state
  - per-job events
  - per-document-version lock
  - per-worker heartbeat / presence
- canonical example keys:
  - `risk_knowledge:indexing:queue`
  - `risk_knowledge:indexing:processing`
  - `risk_knowledge:indexing:dead`
  - `risk_knowledge:indexing:jobs:{job_id}`
  - `risk_knowledge:indexing:events:{job_id}`
  - `risk_knowledge:indexing:lock:{document_version_id}`
  - `risk_knowledge:indexing:workers:{worker_id}`

## 11. Job Schema

- required fields:
  - `job_id`
  - `job_type`
  - `document_id`
  - `document_version_id`
  - `manifest_id`
  - `idempotency_key`
  - `status`
  - `attempt`
  - `max_attempts`
  - `created_at`
  - `started_at`
  - `finished_at`
  - `heartbeat_at`
  - `progress`
  - `error_code`
  - `error_message`
- recommended interpretation:
  - `job_type` distinguishes initial index, retry, and rebuild intent
  - `progress` is additive live-state data and must not replace durable status truth

## 12. Job Lifecycle

- required durable lifecycle states:
  - `queued`
  - `running`
  - `retrying`
  - `succeeded`
  - `failed`
  - `dead`
  - `stale`
  - `cancelled`
- required meaning:
  - `queued`: durable job exists and is waiting for worker claim
  - `running`: worker lease is active and heartbeat is advancing
  - `retrying`: retryable failure has been recognized and requeue is in flight
  - `succeeded`: indexing completed and manifest flow reached terminal success
  - `failed`: non-retryable failure or failed attempt pending terminal handling
  - `dead`: retry ceiling exceeded and manual intervention is required
  - `stale`: running job lost lease or heartbeat and needs recovery handling
  - `cancelled`: job was explicitly cancelled before terminal success

## 13. Job Event Taxonomy

- minimum event taxonomy:
  - `queued`
  - `started`
  - `parse_started`
  - `parse_completed`
  - `chunk_started`
  - `chunk_completed`
  - `embedding_started`
  - `embedding_progress`
  - `embedding_completed`
  - `index_build_started`
  - `index_build_completed`
  - `manifest_saved`
  - `manifest_activated`
  - `succeeded`
  - `failed`
  - `retry_scheduled`
  - `dead`
  - `rollback_started`
  - `rollback_completed`
- polling remains the observability baseline in PR-B.

## 14. Worker Lifecycle

- worker responsibilities:
  - register worker presence
  - claim one queued job
  - acquire document-version lock
  - set job to running
  - emit heartbeat
  - execute parse / chunk / embed / FAISS build / manifest save
  - either complete activation flow or record failure / retry / dead-letter outcome
- planned primary entrypoint is an external worker process rather than FastAPI startup-owned execution.

## 15. Worker Lease / Heartbeat / Stale Recovery

- claim semantics must explicitly define:
  - lease acquisition
  - lease TTL
  - heartbeat-based lease extension
  - stale detection on lease expiry
- stale recovery policy must explicitly define:
  - how a lost lease becomes `stale`
  - whether stale recovery requeues or fails the job
  - how duplicate execution is prevented during recovery
- worker visibility fields should include:
  - `worker_id`
  - `claimed_at`
  - `heartbeat_at`
  - lease expiry timestamp

## 16. Idempotency And Lock Policy

- same `idempotency_key` + same `job_type` + same `document_version_id` must return the existing applicable job rather than create a duplicate job.
- same `document_version_id` must not run concurrent index / rebuild jobs while the document-version lock is active.
- explicit rebuild must remain a distinct job intent and must still honor lock semantics.
- idempotency checks must be based on MySQL durable job state and must not rely on Redis-only live state.

## 17. Manifest Commit Guard

- manifest lifecycle states must include:
  - `building`
  - `built`
  - `activation_pending`
  - `active`
  - `failed`
  - `archived`
  - `rolled_back`
- manifest policy must remain two-phase:
  - build phase
    - parse / chunk / embed / build / save completes
    - manifest reaches `built`
  - activation phase
    - only `built` manifests may activate
    - previous active manifest must be recorded before switch
- a failed or partially successful build must never silently contaminate the active retrieval pointer.

## 18. Activation And Rollback Policy

- activation rules:
  - only `built` manifests may activate
  - previous active manifest id must be recorded before pointer switch
  - activation must be auditable
- rollback rules:
  - rollback restores the active pointer only
  - rollback does not delete historical manifests or index artifacts by default
  - rolled-back and failed manifests remain auditable

## 19. Audit And Event Requirements

- durable audit / event requirements:
  - job submission
  - worker claim
  - lease loss or stale detection
  - retry scheduling
  - dead-letter transition
  - manifest activation
  - manifest rollback
  - in-process fallback usage
- fallback audit must capture:
  - `IN_PROCESS_WORKER_FALLBACK_USED`
  - environment
  - reason
  - job id
  - operator / trigger identity when available

## 20. Runtime PR Test Plan

- required future test files:
  - `tests/risk_knowledge/test_indexing_worker.py`
  - `tests/risk_knowledge/test_indexing_job_api.py`
  - `tests/risk_knowledge/test_manifest_activation_rollback.py`
  - `tests/risk_knowledge/test_stale_job_detection.py`
  - `tests/risk_knowledge/test_indexing_job_idempotency.py`
- required future scenarios:
  - submit job creates one queued job
  - worker drives `queued -> running -> succeeded`
  - failed job records `error_code` and `error_message`
  - failed job retry requeues correctly
  - stale running job is detected and recovered
  - duplicate `idempotency_key` does not create duplicate jobs
  - only built manifests can activate
  - failed manifests cannot activate
  - activation failure restores previous active manifest
  - concurrent rebuilds on one document version are blocked by lock

## 21. Acceptance Criteria

- planning is accepted only if:
  - PR-B is framed as an evolution of current `main`, not a rewrite
  - compat-layer API strategy is documented
  - external-plus-fallback worker strategy is documented
  - MySQL / Redis ownership is documented
  - queue, job, event, lease, stale recovery, idempotency, manifest, rollback, and audit policies are all specified
  - runtime PR test plan and acceptance gates are listed
  - the PR remains docs-only

## 22. No-Go Criteria

- no runtime implementation in this PR
- no changes under `app/`, `tests/`, `scripts/`, migrations, or runtime config
- no breaking removal or rename of `/api/risk-knowledge/admin/*`
- no silent production fallback from missing external workers into in-process execution
- no Redis-only lifecycle truth
- no manifest activation from failed or incomplete builds

## 23. Known Limitations

- this PR does not validate runtime behavior
- this PR does not introduce route handlers, worker entrypoints, or storage migrations
- full repository regression remains out of scope
- polling remains the observability baseline; no SSE / WebSocket planning is added here

## 24. Implementation Readiness Decision

- `PR-B Indexing Worker + Job Observability Gate planned; implementation not started`
- This planning PR is ready to hand off into a later runtime implementation PR after docs-only acceptance.
