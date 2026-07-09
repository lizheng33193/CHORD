# M7C Monitoring / Alerting Runbook

## Scope

This runbook defines the minimum monitoring, readiness, and alerting boundary for CHORD under M7C.

It does not deploy a full observability platform.

## What M7C Monitors

Required:

- API `/health`
- runtime directory readiness
- disk availability

Advisory:

- `/docs`
- optional subsystem probes
- latest backup manifest presence
- `outputs/` size
- `storage/` size
- memory vector artifacts when discoverable
- latest shared eval report path when discoverable

## Readiness Boundary

M7C does not add `/ready`.

Current readiness is defined by:

- `/health`
- runtime directory readiness
- disk availability
- advisory probe context

## Required Checks

- `GET /health` must return `200`
- required runtime directories must exist
- disk free percent must stay at or above `5%`

## Advisory Checks

- `/docs`
- optional probes passed with `--probe`
- latest backup manifest and `archive_sha256`
- `outputs/` and `storage/` size scans
- memory vector artifact availability
- latest shared eval report path

## Structured Log Expectations

M7C expects operators to prefer logs with:

- `timestamp`
- `level`
- `component` or `logger`
- `request_id` when available
- `user_id`, `project_id`, `country` when available
- `event_type`, `action` when available
- `error_code` when available

M7C does not refactor runtime logging.

## Request ID Correlation

Use `request_id` to correlate:

- API errors
- runtime logs
- audit events
- execution traces when available

## Alert Severity

- `P0`: immediate service availability or safety issue
- `P1`: degraded core capability that must be handled the same day
- `P2`: operational risk accumulation

## Alert Catalog

Minimum alert catalog:

- API health check failed
- Redis unavailable
- Risk Knowledge worker stale job
- Memory DB write failed
- Memory vector sync failed
- `production_release --strict` failed
- Data Agent execution failed
- SQL blocker suddenly spikes
- LLM provider failure rate high
- disk usage high for `outputs/` or `storage/`

## P0 Playbook

Examples:

- `/health` failing
- API container not starting
- Redis unavailable for a deployment that depends on it
- restore followed by smoke failure
- disk free percent below `5%`

Actions:

- stop rollout or operator changes
- inspect `docker compose logs`
- run startup smoke again if needed
- use rollback or restore runbooks when required

## P1 Playbook

Examples:

- `/docs` or key route `5xx`
- Risk Knowledge worker stale
- backup manifest missing checksum
- Memory DB unreadable or write failure
- Memory vector sync failure
- disk free percent between `5%` and `10%`

Actions:

- investigate the same day
- record the issue and mitigation in operator notes
- decide whether feature downgrade or recovery action is needed

## P2 Playbook

Examples:

- optional probe warnings
- `/docs` not `200` but not `5xx`
- symlink warning in size scans
- missing latest shared eval report path
- warning-only snapshot results

Actions:

- record and schedule follow-up
- include in M7D or M7E follow-up if unresolved

## Runtime Status Snapshot

Standard run:

```bash
python scripts/collect_runtime_status.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-m7c-monitoring \
  --timeout-seconds 30
```

Optional probes:

```bash
python scripts/collect_runtime_status.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-m7c-monitoring \
  --probe /api/data-acquisition/healthz \
  --probe /api/risk-knowledge/workers/health \
  --timeout-seconds 30
```

Stdout-only:

```bash
python scripts/collect_runtime_status.py \
  --base-url http://127.0.0.1:8000 \
  --no-write \
  --timeout-seconds 30
```

## Webhook Placeholder

M7C does not deliver alerts to webhook targets.

Suggested future payload shape:

- `severity`
- `alert_name`
- `status`
- `service`
- `environment`
- `request_id`
- `snapshot_path`
- `runbook_url`
- `next_action`

## Troubleshooting

- treat optional probe `401/403/404/501` as advisory, not required failure
- do not use external URLs in `--probe`
- investigate symlink warnings before trusting size totals

## Known Limitations

- no `/ready` endpoint
- no full logging rollout
- no Grafana / Prometheus deployment
- no DB audit stream
- no webhook delivery
