# M7B Backup / Restore / Rollback Plan

## Current State

- `M7-0 scope lock completed`
- `M7A Deployment & Runtime Readiness completed`
- `M7 implementation in progress`
- `M7B Backup / Restore / Rollback not started`
- `Next step: M7B Backup / Restore / Rollback`

## Goal

Deliver the minimum local state backup, restore, and rollback readiness needed for a commercial handoff without expanding into cloud backup, disaster recovery infrastructure, or runtime refactors.

## Implementation Changes

- add a local backup script with an explicit allowlist, manifest output, and archive `sha256`
- add a local restore script with dry-run support, default non-overwrite behavior, overwrite opt-in, and path traversal protection
- document the protected local state boundary, excluded secrets, symlink policy, and rollback flow
- update status tracking in `PLANNING.md` and `TASK.md`

## Scripts

- `scripts/backup_local_state.py`
  - default targets:
    - `outputs/memory/`
    - `outputs/risk_knowledge/`
    - `outputs/orchestrator_sessions/`
    - `outputs/evals/`
    - `storage/risk_knowledge/`
  - optional target:
    - `data/` only via `--include-data`
- `scripts/restore_local_state.py`
  - validates archive entry paths
  - skips or rejects link entries conservatively
  - defaults to non-overwrite mode

## Runbooks

- `docs/runbooks/backup-restore-runbook.md`
  - what is backed up
  - what is excluded
  - how to create and verify a backup
  - how to dry-run and apply a restore
  - how to validate recovery with M7A bootstrap and smoke steps
- `docs/runbooks/rollback-runbook.md`
  - when rollback is required
  - why a fresh backup must be taken first
  - how to combine code rollback and local state restore

## Validation

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `python scripts/bootstrap_runtime_dirs.py`
- `rm -rf /tmp/chord-m7b-backups /tmp/chord-restore-check`
- `python scripts/backup_local_state.py --output-dir /tmp/chord-m7b-backups`
- `python scripts/restore_local_state.py --archive "$ARCHIVE" --target-root /tmp/chord-restore-check --dry-run`
- `python scripts/restore_local_state.py --archive "$ARCHIVE" --target-root /tmp/chord-restore-check`
- `python scripts/restore_local_state.py --archive "$ARCHIVE" --target-root /tmp/chord-restore-check --dry-run`
- `python scripts/restore_local_state.py --archive "$ARCHIVE" --target-root /tmp/chord-restore-check --overwrite`
- unsafe archive validation with `../unsafe.txt` must fail
- `git diff --check`

## Go Criteria

- backup archive and manifest are created successfully
- archive `sha256` is recorded
- backup default scope matches the allowlist
- secrets are excluded
- restore dry-run works
- restore default non-overwrite behavior works
- restore `--overwrite` works
- path traversal protection works
- rollback runbook is complete
- no runtime or test changes are introduced

## No-Go Criteria

- backup archive includes `.env`, `key.json`, or certificate files
- restore allows path traversal
- restore overwrites existing files by default
- manifest is missing
- rollback runbook is missing
- scope expands into runtime behavior, cloud backup, scheduled backup, or CI / monitoring work
- any document marks `M7 completed`

## Known Limitations

- M7B does not back up operator-owned external databases
- M7B does not manage secrets or secret rotation
- M7B does not promise cross-version schema downgrade or index artifact compatibility
- M7B does not provide an automated rollback controller

## Next Step

- `M7C Monitoring / Alerting / Audit Boundary`
