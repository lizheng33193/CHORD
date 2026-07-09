# M7 Commercial Delivery Checklist

## 1. Environment Checklist

- `.env.example` exists and documents a mock-first default
- operator understands `.env` is local-only and must not be committed
- runtime directories can be bootstrapped before startup
- external auth DB, real model credentials, and deployment overrides are operator-owned inputs

## 2. Startup Checklist

- `docker compose up -d` is the minimum startup path
- `/health` startup smoke is defined and repeatable
- operator knows where to inspect `docker compose logs` on failure
- runtime status snapshot can be collected after startup

## 3. Backup / Restore Checklist

- local backup command exists
- backup manifest and `archive_sha256` are produced
- secrets are not included in the local backup archive
- restore supports `--dry-run`
- restore rejects path traversal and unsafe archive paths
- external database backup remains operator responsibility outside M7 scripts

## 4. Monitoring / Alerting Checklist

- runtime status snapshot command exists
- required versus advisory monitoring signals are documented
- `P0` / `P1` / `P2` alert severity is defined
- operator knows where the monitoring and alerting runbook lives

## 5. Audit Boundary Checklist

- audit boundary and high-risk action inventory are documented
- operator understands there is no DB audit stream in M7
- request correlation / request ID expectations are documented

## 6. Release Gate Checklist

- canonical release gate is `python -m app.eval.runner --profile production_release --strict`
- `scripts/run_m7d_release_check.py` wraps startup smoke, runtime status, load smoke, and strict release gate
- load smoke scope is GET-only and bounded to safe endpoints
- `app.release.pre_m3_gate` is treated as legacy / compatibility reference only

## 7. Rollback Checklist

- rollback runbook exists
- operator can create a fresh backup before rollback
- operator can identify the target commit or release candidate
- post-rollback startup smoke and runtime snapshot are documented

## 8. Security / Secrets Checklist

- `.env`, certificates, and keys are excluded from local backup archives
- credentials are not written into docs, logs, or committed artifacts
- operator-owned secret storage remains outside M7 local scripts

## 9. Operator Handoff Checklist

- operator has the quickstart runbook
- operator has the commercial delivery handoff runbook
- operator has the final acceptance review
- operator knows the known limitations and explicit non-goals

## 10. Final Go / No-Go Checklist

- fresh M7E rerun passed on latest `main`
- final acceptance review records concrete evidence paths
- README, PLANNING, TASK, and the M7 master plan agree on final status
- old M7E naming has been removed or corrected
- no runtime, script, test, CI, or Docker behavior was changed during M7E
