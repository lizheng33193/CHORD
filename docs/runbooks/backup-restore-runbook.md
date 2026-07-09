# M7B Backup / Restore Runbook

## Scope

This runbook explains how to create, verify, dry-run, and restore the minimum local CHORD state protected by M7B.

It does not cover cloud backup, scheduled backup, external database backup, secret vault management, or Kubernetes recovery.

## What Is Backed Up

Default local backup targets:

- `outputs/memory/`
- `outputs/risk_knowledge/`
- `outputs/orchestrator_sessions/`
- `outputs/evals/`
- `storage/risk_knowledge/`

Optional target:

- `data/` only when `--include-data` is explicitly passed

## What Is Not Backed Up

The local backup archive does not include:

- `.env`
- `.env.*`
- `key.json`
- `app/key.json`
- `*.pem`
- `*.key`
- `*.crt`
- `*.p12`
- `*.p8`
- operator-owned external databases

## Secret Handling

Secrets must not be stored in ordinary local backup archives.

Use a secure secret manager or controlled vault for credentials, API keys, and certificates.

If `AUTH_ENABLED=1` or `AUTH_DATABASE_URL` points to an external DB, that auth database must be backed up outside M7B local state scripts.

## Create Backup

Example command:

```bash
python scripts/backup_local_state.py --output-dir backups
```

Optional `data/` inclusion:

```bash
python scripts/backup_local_state.py --output-dir backups --include-data
```

Acceptance validation should prefer a temporary directory:

```bash
rm -rf /tmp/chord-m7b-backups
python scripts/backup_local_state.py --output-dir /tmp/chord-m7b-backups
```

## Verify Backup

Confirm both files exist:

- `chord-state-backup-YYYYMMDD-HHMMSS.tar.gz`
- `chord-state-backup-YYYYMMDD-HHMMSS.manifest.json`

Check archive checksum:

```bash
ARCHIVE=$(ls /tmp/chord-m7b-backups/chord-state-backup-*.tar.gz | tail -1)
MANIFEST=$(ls /tmp/chord-m7b-backups/chord-state-backup-*.manifest.json | tail -1)
python - <<'PY' "$MANIFEST"
import json, sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["archive_sha256"])
PY
```

## Dry-run Restore

```bash
python scripts/restore_local_state.py \
  --archive "$ARCHIVE" \
  --target-root /tmp/chord-restore-check \
  --dry-run
```

## Restore

```bash
rm -rf /tmp/chord-restore-check
python scripts/restore_local_state.py \
  --archive "$ARCHIVE" \
  --target-root /tmp/chord-restore-check
```

## Overwrite Restore

Restore defaults to non-overwrite mode. Existing files are skipped unless `--overwrite` is passed.

```bash
python scripts/restore_local_state.py \
  --archive "$ARCHIVE" \
  --target-root /tmp/chord-restore-check \
  --overwrite
```

## Post-restore Validation

```bash
python scripts/bootstrap_runtime_dirs.py
docker compose up -d
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
docker compose down
```

## Safety Checks

- restore rejects path traversal entries
- restore rejects archive entries that resolve outside the target root
- symlink and hardlink entries are skipped by default
- unsafe link targets must never be restored

Example unsafe archive validation:

```bash
python - <<'PY'
import tarfile
from pathlib import Path

out = Path("/tmp/chord-unsafe-archive.tar.gz")
payload = Path("/tmp/chord-unsafe-payload.txt")
payload.write_text("unsafe", encoding="utf-8")

with tarfile.open(out, "w:gz") as tar:
    tar.add(payload, arcname="../unsafe.txt")

print(out)
PY

python scripts/restore_local_state.py \
  --archive /tmp/chord-unsafe-archive.tar.gz \
  --target-root /tmp/chord-restore-check
```

The restore command must fail with a non-zero exit code.

## Troubleshooting

- missing allowlist directories produce warnings instead of a hard failure
- existing files are skipped unless `--overwrite` is set
- external DB backup must be handled separately by the operator

## Known Limitations

- no cloud backup support
- no scheduled backup support
- no secret vault integration
- no external database backup automation
- no schema downgrade framework
