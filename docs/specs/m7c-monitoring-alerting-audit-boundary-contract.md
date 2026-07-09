# M7C Monitoring / Alerting / Audit Boundary Contract

## Scope

M7C defines the minimum monitoring, alerting, readiness, and audit boundaries for CHORD.

It adds a local runtime status snapshot script and operator-facing runbooks without introducing a full observability platform.

## Monitoring Boundary

M7C monitors the minimum signals needed to decide whether the current local deployment is healthy enough for commercial operation under explicit limitations.

## Required Signals

- API `/health`
- runtime directory readiness
- project-root disk availability

## Advisory Signals

- `/docs`
- optional subsystem probes
- latest backup manifest presence
- `outputs/` size growth
- `storage/` size growth
- memory vector artifact status if discoverable
- latest shared eval / release gate report path if discoverable

## Readiness Boundary

M7C does not add a `/ready` endpoint.

The minimum readiness boundary is provided by the runtime status snapshot:

- `/health`
- runtime directory readiness
- disk availability
- advisory probes

If a future `/ready` endpoint exists, operators may add it to the runbook later.

## Structured Logs Boundary

M7C documents minimum structured log expectations only.

Recommended log fields:

- `timestamp`
- `level`
- `component` or `logger`
- `request_id` when available
- `user_id`, `project_id`, `country` when available
- `event_type`, `action` when available
- `error_code` when available

M7C does not implement a runtime logging refactor.

## Request ID Correlation Boundary

`request_id` is an operator troubleshooting correlation key.

Operators should use `request_id` to link:

- API errors
- runtime logs
- audit events
- execution traces when available

M7C does not change request ID propagation.

## Alert Severity Model

M7C uses three alert levels:

- `P0`: immediate availability or safety problem
- `P1`: core capability degraded and must be handled the same day
- `P2`: accumulating operational risk that should be scheduled

## Audit Boundary

M7C defines the audit boundary and high-risk action inventory.

M7C does not implement a persistent DB audit stream.

M7C does not change current runtime audit behavior.

## High-risk Action Inventory

Minimum inventory:

- auth login / logout / register
- profile run / batch run / export / degraded result
- Data Agent generate / approve / reject / execute / fail
- Risk Knowledge upload / indexing / retry / cancel / manifest activate / rollback
- memory create / archive / restore / delete / semantic context decision
- operations backup / restore / rollback / runtime status snapshot collection

## Runtime Status Snapshot Contract

`collect_runtime_status.py` must:

- support required and advisory checks
- emit `overall_status` as `pass`, `warn`, or `fail`
- return `0` for `pass` and `warn`
- return `1` for required failure
- return `2` for script/config error
- reject external probe URLs
- support `--no-write` stdout-only mode
- avoid following symlinks when scanning directory sizes

## Non-goals

M7C does not implement:

- full observability platform
- Prometheus / Alertmanager / Grafana deployment
- SIEM integration
- DB audit stream
- distributed tracing
- runtime logging refactor
- runtime behavior changes

## Validation Contract

M7C can be marked completed only if:

- the snapshot script generates valid output
- required checks drive exit codes correctly
- advisory probes do not block required pass
- runbooks clearly define monitoring, alerting, readiness, and audit boundaries
- M7C does not introduce runtime or test changes
