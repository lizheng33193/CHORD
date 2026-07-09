# M7C Monitoring / Alerting / Audit Boundary Plan

## Current State

- `M7-0 scope lock completed`
- `M7A Deployment & Runtime Readiness completed`
- `M7B Backup / Restore / Rollback completed`
- `M7 implementation in progress`
- `M7C Monitoring / Alerting / Audit Boundary not started`
- `Next step: M7C Monitoring / Alerting / Audit Boundary`

## Goal

Deliver the minimum monitoring, alerting, readiness, and audit boundary needed for commercial handoff without introducing a full observability platform or runtime refactor.

## Implementation Changes

- add a local runtime status snapshot script
- define required vs advisory monitoring signals
- define a readiness boundary without adding a `/ready` endpoint
- document structured log and request ID expectations
- define alert severity and minimum alert catalog
- document audit boundary, existing audit coverage, and future DB audit stream boundary

## Runtime Status Script

- `scripts/collect_runtime_status.py`
- required checks:
  - `/health`
  - runtime directories
  - disk availability
- advisory checks:
  - `/docs`
  - optional probes
  - latest backup manifest
  - `outputs/` / `storage/` size
  - memory vector artifacts if available
  - latest shared eval report path if available

## Monitoring Boundary

- minimum required health stays intentionally small
- advisory checks capture operator awareness without blocking readiness
- optional probes remain advisory only

## Readiness Boundary

- no `/ready` endpoint is added in M7C
- readiness is derived from required snapshot checks plus advisory context

## Alerting Boundary

- `P0`, `P1`, `P2` severity model
- operator playbooks for each level
- explicit minimum alert catalog for API, Redis, memory, Data Agent, release gate, and disk usage signals

## Audit Boundary

- high-risk action inventory
- current `audit_events` coverage
- future recommended audit fields
- no DB audit stream implementation in M7C

## Validation

- `docker compose up -d`
- `python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30`
- `python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7c-monitoring --timeout-seconds 30`
- `python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7c-monitoring --probe /api/data-acquisition/healthz --probe /api/risk-knowledge/workers/health --timeout-seconds 30`
- `python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --no-write --timeout-seconds 30`
- `docker compose down`
- `python -m compileall -q app data_acquisition_agent tests scripts`
- `git diff --check`

## Go Criteria

- monitoring boundary docs exist
- alert boundary docs exist
- audit boundary docs exist
- operator checklist exists
- snapshot script works in write and no-write modes
- required checks map correctly to exit codes
- advisory probes do not become required failures
- no runtime or test changes are introduced

## No-Go Criteria

- snapshot script calls LLM, SQL, profile analysis, indexing, backup, or restore
- advisory endpoint failure blocks required pass
- docs claim a full observability platform exists
- docs claim a DB audit stream exists
- runtime behavior or tests are modified
- M7C is marked as `M7 completed`

## Known Limitations

- no `/ready` endpoint
- no full structured logging rollout
- no alert delivery platform
- no DB audit stream
- memory vector status is artifact-based, not API-backed

## Next Step

- `M7D CI / Release Gate / Load Smoke`
