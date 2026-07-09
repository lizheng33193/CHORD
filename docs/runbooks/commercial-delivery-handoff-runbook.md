# Commercial Delivery Handoff Runbook

## 1. Scope

This runbook explains how to hand off CHORD after M7 as a minimum commercial operating package.

It focuses on startup, validation, backup, restore, monitoring, release checks, rollback references, and known limitations.

It does not claim enterprise production certification, full disaster recovery, full observability platform delivery, or a full performance engineering program.

## 2. What Is Delivered

M7 delivers a documented minimum commercial operating boundary:

- Docker / local startup readiness
- startup smoke and runtime status snapshot
- local backup / restore / rollback boundary
- monitoring / alerting / audit boundary
- release gate / load smoke boundary
- final acceptance review, checklist, and operator handoff docs

## 3. What Is Not Delivered

M7 does not deliver:

- full cloud backup
- scheduled backup automation
- Kubernetes rollout
- CD / auto deploy
- full Grafana / Prometheus / SIEM platform
- full-scale load-testing infrastructure
- runtime feature expansion beyond the existing M7A-D scope

## 4. Repository Entry Points

Start with:

- `README.md`
- `docs/runbooks/m7-operator-quickstart-runbook.md`
- `docs/reviews/m7-final-acceptance-review.md`
- `docs/checklists/m7-commercial-delivery-checklist.md`

Reference runbooks:

- `docs/runbooks/deployment-runbook.md`
- `docs/runbooks/local-demo-runbook.md`
- `docs/runbooks/backup-restore-runbook.md`
- `docs/runbooks/rollback-runbook.md`
- `docs/runbooks/monitoring-alerting-runbook.md`
- `docs/runbooks/audit-boundary-runbook.md`
- `docs/runbooks/operator-checklist-runbook.md`
- `docs/runbooks/release-gate-runbook.md`
- `docs/runbooks/load-smoke-runbook.md`

## 5. Minimum Startup Flow

1. Copy `.env.example` to `.env` and apply operator-owned overrides.
2. Start the minimum stack with `docker compose up -d`.
3. Run startup smoke:

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

4. Collect a runtime status snapshot:

```bash
python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-runtime-status --timeout-seconds 30
```

## 6. Backup / Restore Flow

Create a local state backup:

```bash
python scripts/backup_local_state.py --output-dir /tmp/chord-backups
```

Dry-run restore against a safe temporary target:

```bash
ARCHIVE=$(ls /tmp/chord-backups/chord-state-backup-*.tar.gz | tail -1)
python scripts/restore_local_state.py --archive "$ARCHIVE" --target-root /tmp/chord-restore-check --dry-run
```

The local archive excludes `.env`, certificates, keys, and external DB state. External DB backup remains operator-owned.

## 7. Monitoring / Alerting Flow

- use the M7C runtime snapshot to capture required and advisory signals
- interpret alert severity as `P0` / `P1` / `P2`
- use the M7C runbooks for readiness and audit-boundary follow-up

## 8. Release Gate Flow

Canonical strict release gate:

```bash
python -m app.eval.runner --profile production_release --strict
```

Recommended combined wrapper:

```bash
python scripts/run_m7d_release_check.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-release-check \
  --run-production-release \
  --timeout-seconds 30 \
  --production-release-timeout-seconds 600
```

`app.release.pre_m3_gate` remains legacy / compatibility guidance only.

## 9. Rollback Flow

- create a fresh backup before rollback
- record the current commit or release candidate
- follow `docs/runbooks/rollback-runbook.md`
- re-run startup smoke and runtime status after rollback or restore

## 10. Operator Responsibilities

Operators remain responsible for:

- local `.env` management
- real model credentials and external auth / DB configuration
- secret storage outside repo and outside local backup archives
- release decision review when warnings appear
- external database backup and restore
- post-release monitoring and escalation follow-up

If a local `.env` enables `AUTH_ENABLED=true`, startup depends on a reachable auth database and is outside the M7 mock-first minimum startup boundary.

## 11. Known Limitations

- mock-first remains the default local posture
- M7 does not include enterprise observability tooling
- M7 does not include cloud backup automation
- M7 does not include Kubernetes deployment or CD
- M7 does not certify high-scale production load behavior

## 12. Escalation / Next Engineering Work

- treat `P0` alerts or strict release gate failures as no-go
- use the final acceptance review to understand what was verified in M7E
- treat M8 as a separate phase; do not expand M7E into new runtime scope
