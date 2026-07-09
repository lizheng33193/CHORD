# M7E Final Acceptance & Commercial Delivery Docs Plan

## Current State

- `M7-0 scope lock completed`
- `M7A Deployment & Runtime Readiness completed`
- `M7B Backup / Restore / Rollback completed`
- `M7C Monitoring / Alerting / Audit Boundary completed`
- `M7D CI / Release Gate / Load Smoke completed`
- `M7 implementation in progress`
- `M7E Final Acceptance & Commercial Delivery Docs not started`
- next step is `M7E Final Acceptance & Commercial Delivery Docs`

## Goal

Close M7 as a minimum commercial delivery package by producing the final acceptance review, operator handoff docs, commercial checklist, quickstart entrypoint, and consistent project state updates.

M7E does not add runtime capability. It closes the commercial handoff boundary around evidence, runbooks, status tracking, and known limitations.

## Implementation Changes

- add the M7E plan artifact
- add the final acceptance review
- add the commercial delivery checklist
- add the commercial delivery handoff runbook
- add the operator quickstart runbook
- update `README.md`, `PLANNING.md`, and `TASK.md`
- apply a docs-only naming correction to `docs/plans/m7-minimum-commercial-production-readiness-plan.md`

## Final Acceptance Review

`docs/reviews/m7-final-acceptance-review.md` is the primary M7 closure artifact.

It must:

- summarize the final M7 scope
- record an acceptance matrix for `M7-0`, `M7A`, `M7B`, `M7C`, `M7D`, and `M7E`
- use fresh M7E rerun evidence as primary evidence
- reference M7A-D plans, runbooks, and merged artifacts as secondary context
- state the final outcome as `Minimum Commercial Production Readiness`

It must not:

- claim enterprise production certification
- imply full disaster recovery or full observability platform coverage
- hide known limitations or deferred infrastructure work

## Commercial Delivery Checklist

`docs/checklists/m7-commercial-delivery-checklist.md` must cover:

- environment readiness
- startup and health checks
- backup / restore / rollback boundary
- monitoring / alerting / audit boundary
- release gate boundary
- security / secret handling
- operator handoff
- final Go / No-Go criteria

## Handoff Runbooks

`docs/runbooks/commercial-delivery-handoff-runbook.md` must explain:

- what M7 delivers
- what M7 explicitly does not deliver
- which repository documents are the handoff entrypoints
- operator responsibilities for startup, validation, backup, restore, release, rollback, and escalation

`docs/runbooks/m7-operator-quickstart-runbook.md` must provide the shortest repeatable operator sequence for:

- environment preparation
- `docker compose up -d`
- startup smoke
- runtime status snapshot
- local backup
- load smoke
- release check wrapper
- stop / cleanup

## README / Status Updates

`README.md` must receive only minimal M7E updates:

- fix stale `M7 not started` statements
- add a small M7 commercial readiness section
- point readers to the quickstart, handoff, final review, and checklist
- state that the canonical production release gate is `python -m app.eval.runner --profile production_release --strict`
- keep `app.release.pre_m3_gate` as legacy / compatibility reference only

`PLANNING.md` and `TASK.md` must only move to:

- `M7E Final Acceptance & Commercial Delivery Docs completed`
- `M7 completed`
- `M8 not started`

after the fresh rerun passes.

## Validation

M7E final acceptance evidence must be generated on latest `main` via:

```bash
python -m compileall -q app data_acquisition_agent tests scripts
docker compose up -d
python scripts/run_m7d_release_check.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-m7e-release-check \
  --run-production-release \
  --timeout-seconds 30 \
  --production-release-timeout-seconds 600
docker compose down
rm -rf /tmp/chord-m7e-backups /tmp/chord-m7e-restore-check
python scripts/backup_local_state.py --output-dir /tmp/chord-m7e-backups
ARCHIVE=$(ls /tmp/chord-m7e-backups/chord-state-backup-*.tar.gz | tail -1)
python scripts/restore_local_state.py \
  --archive "$ARCHIVE" \
  --target-root /tmp/chord-m7e-restore-check \
  --dry-run
git diff --check
git status --short
grep -R "m7-minimum-commercial-production-readiness-review\|final-commercial-delivery-checklist\|final-system-architecture\|final-runtime-flow" README.md PLANNING.md TASK.md docs || true
```

## Go Criteria

- all M7E docs exist and link to the actual M7A-D runbooks
- fresh rerun passes on latest `main`
- the final review records concrete evidence paths
- old M7E naming does not remain as a competing entrypoint
- `README.md`, `PLANNING.md`, `TASK.md`, and the M7 master plan agree on the final state

## No-Go Criteria

- fresh rerun was skipped
- startup, load smoke, or strict production release failed
- backup generation or restore dry-run failed
- stale old naming still points to non-existent M7E documents
- documentation claims exceed minimum commercial readiness

## Final Status

If validation passes:

- `M7E Final Acceptance & Commercial Delivery Docs completed`
- `M7 completed`
- `M8 not started`

If validation does not pass:

- keep `M7 implementation in progress`
- record the blocking evidence in the final review
- do not write `M7 completed`
