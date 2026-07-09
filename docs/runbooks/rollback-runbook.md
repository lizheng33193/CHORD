# M7B Rollback Runbook

## Goal

This runbook explains the minimum rollback process for CHORD after a failed deployment, broken local state, or an invalid post-change runtime posture.

## When To Roll Back

Rollback is appropriate when:

- a deployment introduces a startup failure
- restored local state is incompatible with the current code version
- required smoke checks fail after a rollout
- operator inspection shows the current state is not a known-good support posture

## Rollback Principles

- always take a fresh backup of current local state before rollback
- treat code rollback and local state restore as separate steps
- preserve secret handling and external DB handling outside M7B scripts
- verify the restored posture with M7A bootstrap and smoke checks

## Minimum Rollback Flow

### 1. Back Up Current State First

```bash
python scripts/backup_local_state.py --output-dir backups
```

### 2. Stop Running Services

```bash
docker compose down
```

### 3. Roll Back Code To A Known-good Revision

```bash
git checkout <known-good-commit-or-tag>
```

### 4. Restore Local State If Required

```bash
python scripts/restore_local_state.py \
  --archive backups/chord-state-backup-YYYYMMDD-HHMMSS.tar.gz \
  --target-root . \
  --overwrite
```

### 5. Rebuild Required Runtime Directories

```bash
python scripts/bootstrap_runtime_dirs.py
```

### 6. Restart The Minimum Stack

```bash
docker compose up -d
```

### 7. Re-run Startup Smoke

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

## Post-rollback Checks

- confirm the service starts
- confirm `/health` returns `200`
- confirm `/docs` does not fail with `5xx`
- confirm conservative defaults remain unchanged
- confirm the rollback decision is recorded in operator notes

## External Systems

The following remain operator-owned outside M7B automation:

- secret recovery
- external auth database recovery
- any other external database recovery
- external object storage recovery

## Explicit Non-goals

M7B rollback does not provide:

- automated deployment rollback controllers
- Kubernetes rollback
- database schema downgrade automation
- cross-version compatibility guarantees for every local index artifact
